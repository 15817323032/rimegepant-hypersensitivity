# -*- coding: utf-8 -*-
"""FAERS(AEMS) 季度数据下载器。

URL 规律（已实测验证，2026-11）：
    https://fis.fda.gov/content/Exports/faers_ascii_<YYYY>Q<n>.zip
    https://fis.fda.gov/content/Exports/faers_xml_<YYYY>Q<n>.zip

特点：
  * 直链无需登录/条款确认（官方批量下载页即此链接的集合）；
  * 大小写不敏感（faers_ascii_2020q2.zip 与 2020Q2.zip 等价）；
  * 不存在的季度返回 404，可用于校验；
  * ASCII 版每季度约 150-250 MB 压缩，解压后约 1-2 GB。

用法（在工程根目录、venv 环境下）：
    # 只打印下载计划，不下载
    python src/download_faers.py --list-only

    # 下载 2020Q2-2026Q2 的 ASCII 包并解压到 data/raw/<季度>/
    python src/download_faers.py --start 2020Q2 --end 2026Q2

    # 断点续传（对已存在的 .part 文件用 Range 续传；完整文件跳过）
    python src/download_faers.py --start 2020Q2 --end 2026Q2 --resume

    # 只下载部分季度（空格分隔）
    python src/download_faers.py --quarters 2020Q2 2020Q3 2024Q1

    # 改用 XML 格式（本流水线默认读 ASCII，不建议）
    python src/download_faers.py --format xml

    # 下载后校验 zip 完整性（默认开启）
    python src/download_faers.py --start 2020Q2 --end 2026Q2 --no-verify  # 跳过校验
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (research download; pharmacovigilance)"}

TABLES = ("DEMO", "DRUG", "REAC", "OUTC", "THER", "INDI", "RPSR", "LABEL")


def quarter_list(start: str, end: str) -> list[str]:
    """把 '2020Q2'-'2026Q2' 展开为季度列表。"""
    def qnum(q: str) -> int:
        m = re.match(r"(\d{4})Q([1-4])$", q.upper())
        if not m:
            raise ValueError(f"季度格式应为 YYYYQn，收到: {q}")
        return int(m.group(1)) * 4 + int(m.group(2)) - 1

    a, b = qnum(start), qnum(end)
    if b < a:
        raise ValueError("end 早于 start")
    return [f"{n // 4}Q{n % 4 + 1}" for n in range(a, b + 1)]


def url_for(q: str, fmt: str) -> str:
    return f"https://fis.fda.gov/content/Exports/faers_{fmt}_{q}.zip"


def exists(url: str) -> bool:
    try:
        r = requests.head(url, headers=UA, timeout=30, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


def download(q: str, fmt: str, out_dir: Path, resume: bool,
             max_tries: int = 5) -> Path:
    url = url_for(q, fmt)
    dst = out_dir / f"faers_{fmt}_{q}.zip"
    tmp = dst.with_suffix(".zip.part")

    if dst.exists() and dst.stat().st_size > 0:
        print(f"  [skip] {dst.name} 已存在（{dst.stat().st_size / 1e6:.0f} MB）")
        return dst

    last_err: Exception | None = None
    for attempt in range(1, max_tries + 1):
        try:
            headers = {"User-Agent": UA["User-Agent"],
                       # 关键：禁用传输层 gzip。服务器对 Range 续传做 gzip 编码时
                       # 流无法解码，必须要求 identity。
                       "Accept-Encoding": "identity"}
            pos = 0
            if resume and tmp.exists():
                pos = tmp.stat().st_size
                headers["Range"] = f"bytes={pos}-"
                print(f"  [resume] {q} 从 {pos / 1e6:.0f} MB 续传（第 {attempt} 次尝试）")
            else:
                tmp.unlink(missing_ok=True)

            t0 = time.time()
            with requests.get(url, headers=headers, stream=True,
                              timeout=(30, 180)) as r:
                if resume and pos and r.status_code == 416:  # 已下完
                    tmp.rename(dst)
                    return dst
                r.raise_for_status()
                mode = "ab" if (resume and pos and r.status_code == 206) else "wb"
                total = int(r.headers.get("content-length", 0)) + \
                    (pos if mode == "ab" else 0)
                with open(tmp, mode) as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            tmp.rename(dst)
            dt = time.time() - t0
            size = dst.stat().st_size / 1e6
            print(f"  [done] {dst.name}: {size:.0f} MB"
                  f"（{dt:.0f} s，{size / max(dt, 0.1):.1f} MB/s）")
            return dst
        except Exception as e:
            last_err = e
            wait = min(20 * attempt, 120)
            print(f"  [retry {attempt}/{max_tries}] {q}: {e} -> {wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"{q} 重试 {max_tries} 次仍失败: {last_err}")


def verify_and_extract(zip_path: Path, out_dir: Path, fmt: str) -> None:
    q = re.search(r"(\d{4}Q[1-4])", zip_path.name).group(1)
    folder = out_dir / q
    folder.mkdir(exist_ok=True)

    # 完整性校验
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f"{zip_path.name} 损坏于 {bad}，请删除后 --resume 重下")
        names = z.namelist()
        print(f"  [verify] {zip_path.name} OK，{len(names)} 个文件")
        for info in z.infolist():
            # 新版包内带 ascii/ 目录；按季度解压到统一目录
            target = folder / Path(info.filename).name
            with z.open(info) as src, open(target, "wb") as dstf:
                dstf.write(src.read())

    got = sorted(p.name for p in folder.glob("*.txt"))
    missing = [t for t in TABLES
               if not any(g.upper().startswith(t) for g in got)]
    if missing:
        print(f"  [warn] {q} 缺少表: {missing}（RPSR/LABEL 常缺，属正常）")
    print(f"  [extract] {folder}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="2020Q2")
    ap.add_argument("--end", default="2026Q2")
    ap.add_argument("--quarters", nargs="*", help="显式季度列表，覆盖 start/end")
    ap.add_argument("--format", choices=["ascii", "xml"], default="ascii")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--resume", action="store_true", help="断点续传")
    ap.add_argument("--list-only", action="store_true", help="只打印计划")
    ap.add_argument("--no-verify", action="store_true", help="跳过 zip 校验")
    ap.add_argument("--no-extract", action="store_true", help="只下载不解压")
    a = ap.parse_args()

    quarters = a.quarters or quarter_list(a.start, a.end)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"格式: {a.format} | 季度: {len(quarters)} 个（{quarters[0]} ~ {quarters[-1]}）")
    print(f"目标目录: {out_dir}\n")

    if a.list_only:
        for q in quarters:
            u = url_for(q, a.format)
            ok = exists(u)
            print(f"  {q}  {u}  {'OK' if ok else '404/不可达'}")
        print(f"\n预计总量（{a.format}）: 约 {len(quarters) * 0.2:.1f} GB 压缩")
        return

    fails = []
    for q in quarters:
        print(f"\n=== {q} ===")
        try:
            zp = download(q, a.format, out_dir, a.resume)
            if not a.no_verify and not a.no_extract:
                verify_and_extract(zp, out_dir, a.format)
        except Exception as e:
            print(f"  [FAIL] {q}: {e}")
            fails.append(q)
            time.sleep(5)

    print("\n" + "=" * 60)
    if fails:
        print(f"失败 {len(fails)} 个季度: {fails}\n重跑同一命令即可续传/重试。")
    else:
        print("全部完成。下一步：")
        print("  python src/run_module1.py --raw data/raw "
              "--quarters " + " ".join(quarters))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
