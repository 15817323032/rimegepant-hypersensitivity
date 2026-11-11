# -*- coding: utf-8 -*-
"""
FAERS ASCII 季度文件读取与 FDA 标准去重

FDA FAERS ASCII 格式要点（易踩坑，务必照此实现）：
1. 分隔符是 **美元符号 `$`**，不是逗号/制表符；行尾亦带 `$`，因此最后一列为空列。
2. 2014Q3 之后的文件**首行为表头**（primaryid$caseid$...）；更早的文件无表头。
3. 编码混杂（latin-1 可全覆盖），必须 dtype=str 全字段读入再转数值。
4. 列集合随季度演变，不能按位置索引，必须按列名取用。
5. 去重规则（FDA 官方推荐）：按 caseid 分组，依次以
   fda_dt DESC → primaryid DESC 排序，保留首条；
   即同一病例的最新版本覆盖历史版本。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

# 各表核心列（缺失的列自动跳过，不报错）
CORE_COLS: Dict[str, List[str]] = {
    "DEMO": [
        "primaryid", "caseid", "caseversion", "fda_dt", "event_dt",
        "rept_cod", "age", "age_cod", "age_grp", "sex", "wt", "wt_cod",
        "reporter_country", "occp_cod", "rept_dt", "init_fda_dt", "mfr_sndr",
    ],
    "DRUG": [
        "primaryid", "caseid", "drug_seq", "role_cod", "drugname", "prod_ai",
        "route", "dose_vbm", "dose_form", "dose_freq", "nda_num",
    ],
    "REAC": ["primaryid", "caseid", "pt", "drug_rec_act"],
    "OUTC": ["primaryid", "caseid", "outc_cod"],
    "INDI": ["primaryid", "caseid", "indi_pt", "indi_drug_seq"],
    "THER": ["primaryid", "caseid", "dsg_drug_seq", "start_dt", "end_dt", "dur", "dur_cod"],
    "RPSR": ["primaryid", "caseid", "rpsr_cod"],
}

_TABLE_ALIASES = {
    "DEMO": ["DEMO", "demo"],
    "DRUG": ["DRUG", "drug"],
    "REAC": ["REAC", "reac"],
    "OUTC": ["OUTC", "outc"],
    "INDI": ["INDI", "indi"],
    "THER": ["THER", "ther"],
    "RPSR": ["RPSR", "rpsr"],
}


def parse_faers_date(s: pd.Series) -> pd.Series:
    """FAERS 日期为 YYYYMMDD 字符串，含 0/空值；无法解析的置 NaT。"""
    s = s.astype("string").str.strip()
    s = s.where(s.str.fullmatch(r"\d{8}"), pd.NA)
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")


def _locate(raw_dir: Path, table: str, quarter: str) -> Optional[Path]:
    """
    在 raw_dir 中查找某季度某表文件，容忍大小写与前后缀差异。
    官方命名为 e.g. DEMO24Q1.txt（两位年份），亦兼容 DEMO2024Q1.txt。
    """
    q = quarter.upper()
    short = f"{q[2:4]}Q{q[-1]}" if len(q) >= 5 and q[4] == "Q" else q
    # 搜索目录：顶层 + 按季度命名的子目录（download_faers.py 的默认布局）
    search_dirs = [raw_dir]
    for sub in (q, short):
        p = raw_dir / sub
        if p.is_dir():
            search_dirs.append(p)
    for d in search_dirs:
        for alias in _TABLE_ALIASES[table]:
            for tag in (short, q):
                for pat in (f"{alias}{tag}.txt", f"{alias.lower()}{tag.lower()}.txt",
                            f"{alias}{tag}.TXT", f"*{alias}*{tag}*.txt"):
                    hits = sorted(d.glob(pat))
                    if hits:
                        return hits[0]
    return None


def iter_chunks(raw_dir: Path, table: str, quarter: str,
                usecols: Optional[List[str]] = None,
                chunksize: int = 2_000_000):
    """
    分块流式读取某季度某表（大表用，避免 25 季度全量载入爆内存）。

    yield pd.DataFrame（列名已清洗为小写、无 \r）。
    """
    fp = _locate(Path(raw_dir), table, quarter)
    if fp is None:
        return
    header = fp.open("r", encoding="latin-1", newline="").readline()
    has_header = header.lower().startswith("primaryid")
    crlf = header.endswith("\r\n")
    want = usecols or CORE_COLS[table]
    kw = dict(sep="$", dtype=str, encoding="latin-1", engine="c",
              lineterminator="\n", on_bad_lines="skip", index_col=False,
              chunksize=chunksize)

    if has_header:
        cols = [c.strip().lower() for c in header.rstrip("\r\n").split("$")]
        avail = [c for c in want if c in cols]
        if not avail:
            print(f"  [skip] {table} {quarter}: 表头无可识别列")
            return
        it = pd.read_csv(fp, header=0, names=cols, usecols=avail, **kw)
    else:
        it = pd.read_csv(fp, header=None, names=[f"c{i}" for i in range(40)], **kw)

    for ch in it:
        ch = ch.loc[:, [c for c in ch.columns if not c.startswith("Unnamed")]]
        if crlf:
            for c in ch.columns:
                if pd.api.types.is_string_dtype(ch[c]):
                    ch[c] = ch[c].str.rstrip("\r")
        yield ch


def read_table(raw_dir: Path, table: str, quarters: Iterable[str],
               usecols: Optional[List[str]] = None) -> pd.DataFrame:
    """
    读取多个季度的某张表并纵向拼接。

    quarters: e.g. ['2020Q2', '2021Q1', ...]
    """
    frames = []
    for q in quarters:
        fp = _locate(raw_dir, table, q)
        if fp is None:
            print(f"  [skip] {table}: 未找到季度文件 {q}")
            continue

        header = fp.open("r", encoding="latin-1", newline="").readline()
        has_header = header.lower().startswith("primaryid")
        # 行尾不一致：部分季度为 CRLF，用 lineterminator="\n" 时末列的 "\r" 会残留，
        # 导致 usecols/列名匹配失败。统一按 "\n" 读，随后清洗（见下）。
        crlf = header.endswith("\r\n")

        want = usecols or CORE_COLS[table]
        read_kw = dict(sep="$", dtype=str, encoding="latin-1", engine="c",
                       lineterminator="\n", on_bad_lines="skip", index_col=False)
        if has_header:
            cols = [c.strip().lower() for c in header.rstrip("\r\n").split("$")]
            avail = [c for c in want if c in cols]
            if not avail:
                print(f"  [skip] {table} {q}: 表头无可识别列 {cols[:5]}...")
                continue
            # 显式传入清洗后的列名，彻底规避 \r / 大小写差异导致的匹配失败
            df = pd.read_csv(fp, header=0, names=cols, usecols=avail, **read_kw)
        else:
            df = pd.read_csv(
                fp, header=None, names=[f"c{i}" for i in range(40)], **read_kw)
            # 无表头时按 FAERS 已知列序尽力映射（仅 DEMO/DRUG/REAC 可靠）
            pos = {"DEMO": {"primaryid": 0, "caseid": 1, "caseversion": 2,
                            "event_dt": 4, "fda_dt": 7, "rept_cod": 8,
                            "age": 13, "age_cod": 14, "sex": 16, "wt": 18},
                   "DRUG": {"primaryid": 0, "caseid": 1, "drug_seq": 2, "role_cod": 3,
                            "drugname": 4, "route": 7, "dose_vbm": 8},
                   "REAC": {"primaryid": 0, "caseid": 1, "pt": 2},
                   "OUTC": {"primaryid": 0, "caseid": 1, "outc_cod": 2},
                   "INDI": {"primaryid": 0, "caseid": 1, "indi_pt": 2,
                            "indi_drug_seq": 3}}.get(table, {})
            df = df.rename(columns={f"c{i}": n for n, i in pos.items()})
            df = df[[c for c in pos if c in df.columns]]

        df = df.loc[:, [c for c in df.columns if not c.startswith("Unnamed")]]
        if crlf:
            # 清理 CRLF 文件残留的行尾 "\r"（主要落在末列，个别短行会前移）
            for c in df.columns:
                if pd.api.types.is_string_dtype(df[c]):
                    df[c] = df[c].str.rstrip("\r")
        df["_quarter"] = q
        frames.append(df)
        print(f"  [read] {table} {q}: {len(df):,} 行  <- {fp.name}")

    if not frames:
        return pd.DataFrame(columns=(usecols or CORE_COLS[table]) + ["_quarter"])
    return pd.concat(frames, ignore_index=True)


def deduplicate(demo: pd.DataFrame) -> pd.DataFrame:
    """
    FDA 标准去重：每个 caseid 只保留最新版本。
    返回去重后的 DEMO（含 _primaryid 保留列）。
    """
    d = demo.copy()
    # 仅用临时数值列排序，不改变原列 dtype（下游一律以字符串 primaryid 关联）
    for c in ("caseid", "fda_dt", "primaryid"):
        d[f"_num_{c}"] = pd.to_numeric(d.get(c), errors="coerce").fillna(0)
    d = d.sort_values(["_num_caseid", "_num_fda_dt", "_num_primaryid"],
                      ascending=[True, False, False])
    kept = d.drop_duplicates(subset=["caseid"], keep="first")
    kept = kept.drop(columns=[c for c in kept.columns if c.startswith("_num_")])
    print(f"  [dedup] DEMO {len(demo):,} -> {len(kept):,} 例 "
          f"(剔除 {len(demo) - len(kept):,} 条历史版本)")
    return kept


def keep_only(cases: pd.DataFrame, table_df: pd.DataFrame) -> pd.DataFrame:
    """以去重后的 primaryid 白名单过滤其他表。"""
    ids = set(cases["primaryid"].astype(str))
    return table_df[table_df["primaryid"].astype(str).isin(ids)].copy()


def load_faers(raw_dir: str | Path, quarters: List[str]) -> Dict[str, pd.DataFrame]:
    """
    一次性加载并去重，返回干净的各表。
    返回 dict: DEMO(去重后) / DRUG / REAC / OUTC / INDI / THER
    """
    raw_dir = Path(raw_dir)
    print(f"[FAERS] 读取 {len(quarters)} 个季度: {quarters[0]} ... {quarters[-1]}")
    demo_raw = read_table(raw_dir, "DEMO", quarters)
    demo = deduplicate(demo_raw)

    out: Dict[str, pd.DataFrame] = {"DEMO": demo}
    for t in ("DRUG", "REAC", "OUTC", "INDI", "THER"):
        df = read_table(raw_dir, t, quarters)
        if not df.empty:
            df = keep_only(demo, df)
        out[t] = df
    return out


# ---------------------------------------------------------------------------
# 下载引导（不代下载，仅生成清单与命令）
# ---------------------------------------------------------------------------
def write_download_manifest(quarters: List[str], out_dir: str | Path) -> Path:
    """生成季度文件下载清单（FDA 官网需人工在浏览器确认条款，故不自动抓）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / "download_manifest.txt"
    base = "https://fis.fda.gov/content/Exports/"
    lines = [
        "# FAERS ASCII 季度文件下载清单",
        "# 官方入口: https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html",
        "# 解压后把 DEMO/DRUG/REAC/OUTC/INDI/THER/RPSR 七个 txt 放入 data/raw/",
        "",
    ]
    for q in quarters:
        lines.append(f"{base}aers_ascii_{q}.zip")
    fp.write_text("\n".join(lines), encoding="utf-8")
    print(f"[manifest] 已写出 {fp}")
    return fp
