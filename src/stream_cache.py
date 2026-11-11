# -*- coding: utf-8 -*-
"""
FAERS 流式聚合缓存（25 季度全窗口用）

全量 25 季度约 4500 万行 DRUG、3500 万行 REAC，一次性载入会耗尽内存。
本模块用「多遍流式扫描 + 计数聚合」替代全量 DataFrame：

  Pass 1  DRUG  → 目标药病例 primaryid（PS / PS+SS / ALL 三口径）
  Pass 2  DEMO  → 病例去重骨架（仅 4 个数值列）→ 保留的 primaryid 集合 + N
  Pass 3  REAC  → 按 PT 聚合计数（全库 total、各口径 a），并留存目标药病例的逐条 PT
  Pass 4  DEMO  → 目标药病例的人口学行（供 Table 1 / TTO / 亚组）
  Pass 5  OUTC / THER → 目标药病例的结局与用药行

输出为普通小 DataFrame + 计数 Series，下游 compute_signals_from_counts 直接消费。
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.faers_io import CORE_COLS, iter_chunks, _locate  # noqa: E402


def _norm_ids(s: pd.Series) -> pd.Series:
    """primaryid 统一为无小数点的字符串。"""
    return pd.to_numeric(s, errors="coerce").astype("Int64").astype(str)


def _drug_mask(ch: pd.DataFrame, patterns: List[str]) -> pd.Series:
    names = ch["drugname"].fillna("").astype(str).str.upper()
    ai = ch.get("prod_ai", pd.Series("", index=ch.index)).fillna("").astype(str).str.upper()
    regex = "|".join(f"(?:{p})" for p in patterns)   # 单次匹配，避免多次全表扫描
    return (names.str.contains(regex, regex=True, na=False) |
            ai.str.contains(regex, regex=True, na=False))


def build(raw_dir: str | Path, quarters: List[str], patterns: List[str],
          chunksize: int = 2_000_000, verbose: bool = True,
          cache_dir: str | Path | None = None) -> Dict:
    raw_dir = Path(raw_dir)
    t_all = time.time()

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    # 缓存复用：25 季度重扫需 5-6 分钟，命中磁盘缓存则秒级返回
    if cache_dir:
        cd = Path(cache_dir)
        marker = cd / "meta.pkl"
        if marker.exists():
            import pickle
            with open(marker, "rb") as f:
                meta = pickle.load(f)
            if meta.get("quarters") == sorted(quarters):
                log(f"[cache] 命中磁盘缓存 {cd}（{len(quarters)} 季度）")
                meta.update({
                    "demo_drug": pd.read_pickle(cd / "demo_drug.pkl"),
                    "reac_drug": pd.read_pickle(cd / "reac_drug.pkl"),
                    "outc_drug": pd.read_pickle(cd / "outc_drug.pkl"),
                    "ther_drug": pd.read_pickle(cd / "ther_drug.pkl"),
                })
                return meta
        cd.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ Pass 1
    log("[cache] Pass 1/5 扫描 DRUG 表，识别目标药病例 ...")
    ids = {"PS": set(), "PS+SS": set(), "ALL": set()}
    for q in quarters:
        n_chunk = 0
        for ch in iter_chunks(raw_dir, "DRUG", q, ["primaryid", "role_cod",
                                                  "drugname", "prod_ai"], chunksize):
            n_chunk += len(ch)
            m = _drug_mask(ch, patterns)
            if not m.any():
                continue
            pid = _norm_ids(ch.loc[m, "primaryid"])
            role = ch.loc[m, "role_cod"].fillna("").astype(str).str.upper().values
            ids["ALL"].update(pid.tolist())
            ids["PS+SS"].update(pid[role == "PS"].tolist() + pid[role == "SS"].tolist())
            ids["PS"].update(pid[role == "PS"].tolist())
        log(f"  {q}: 扫描 {n_chunk:,} 行 DRUG | 累计 PS={len(ids['PS']):,}")
    if not ids["PS"]:
        raise RuntimeError("未检出目标药报告，请检查 DRUG_PATTERNS")

    # ------------------------------------------------------------------ Pass 2
    log("[cache] Pass 2/5 扫描 DEMO 表，执行 FDA 标准去重 ...")
    parts = []
    for q in quarters:
        for ch in iter_chunks(raw_dir, "DEMO", q,
                              ["primaryid", "caseid", "caseversion", "fda_dt"], chunksize):
            parts.append(ch)
    sk = pd.concat(parts, ignore_index=True)
    parts.clear()
    for c in ("primaryid", "caseid", "caseversion", "fda_dt"):
        sk[c] = pd.to_numeric(sk[c], errors="coerce")
    sk = sk.dropna(subset=["caseid", "primaryid"])
    sk = sk.sort_values(["caseid", "fda_dt", "primaryid"],
                        ascending=[True, False, False])
    sk = sk.drop_duplicates("caseid", keep="first")
    n_total = len(sk)
    kept = set(sk["primaryid"].astype("int64").astype(str))
    del sk, parts
    log(f"  去重后全库病例数 N = {n_total:,}")

    ps_kept = ids["PS"] & kept
    psss_kept = ids["PS+SS"] & kept
    all_kept = ids["ALL"] & kept
    log(f"  目标药病例（去重后）: PS={len(ps_kept):,}  "
        f"PS+SS={len(psss_kept):,}  ALL={len(all_kept):,}")

    # ------------------------------------------------------------------ Pass 3
    log("[cache] Pass 3/5 扫描 REAC 表，按 PT 聚合计数 ...")
    totals: Counter = Counter()
    a_cnt = {k: Counter() for k in ("PS", "PS+SS", "ALL")}
    reac_drug = []
    for q in quarters:
        for ch in iter_chunks(raw_dir, "REAC", q,
                              ["primaryid", "caseid", "pt"], chunksize):
            ch["pt"] = ch["pt"].fillna("").astype(str).str.strip().str.upper()
            ch = ch[ch["pt"].ne("") & ch["pt"].ne("NAN")]
            ch["primaryid"] = pd.to_numeric(ch["primaryid"], errors="coerce") \
                .astype("Int64").astype(str)
            ch = ch[ch["primaryid"].isin(kept)]
            ch = ch.drop_duplicates(["primaryid", "pt"])
            if ch.empty:
                continue
            totals.update(ch.groupby("pt").size().to_dict())
            for k, idset in (("PS", ps_kept), ("PS+SS", psss_kept), ("ALL", all_kept)):
                sub = ch[ch["primaryid"].isin(idset)]
                if len(sub):
                    a_cnt[k].update(sub.groupby("pt").size().to_dict())
            sub = ch[ch["primaryid"].isin(ps_kept)]
            if len(sub):
                reac_drug.append(sub[["primaryid", "caseid", "pt"]])
        log(f"  {q}: 累计 PT 数 {len(totals):,}")
    reac_drug = (pd.concat(reac_drug, ignore_index=True)
                 if reac_drug else pd.DataFrame(columns=["primaryid", "caseid", "pt"]))

    # ------------------------------------------------------------------ Pass 4
    log("[cache] Pass 4/5 提取目标药病例的人口学行 ...")
    demo_drug = []
    for q in quarters:
        for ch in iter_chunks(raw_dir, "DEMO", q, CORE_COLS["DEMO"], chunksize):
            ch = ch.copy()
            ch["pid_norm"] = pd.to_numeric(ch["primaryid"], errors="coerce") \
                .astype("Int64").astype(str)
            sub = ch[ch["pid_norm"].isin(ps_kept)].drop(columns=["pid_norm"])
            if len(sub):
                demo_drug.append(sub)
    demo_drug = (pd.concat(demo_drug, ignore_index=True)
                 if demo_drug else pd.DataFrame(columns=CORE_COLS["DEMO"]))

    # ------------------------------------------------------------------ Pass 5
    log("[cache] Pass 5/5 提取目标药病例的结局 / 用药行 ...")
    outc_drug, ther_drug = [], []
    for table, bucket, cols in (("OUTC", outc_drug, CORE_COLS["OUTC"]),
                                ("THER", ther_drug, CORE_COLS["THER"])):
        for q in quarters:
            for ch in iter_chunks(raw_dir, table, q, cols, chunksize):
                ch = ch.copy()
                ch["pid_norm"] = pd.to_numeric(ch["primaryid"], errors="coerce") \
                    .astype("Int64").astype(str)
                sub = ch[ch["pid_norm"].isin(ps_kept)].drop(columns=["pid_norm"])
                if len(sub):
                    bucket.append(sub)
    outc_drug = (pd.concat(outc_drug, ignore_index=True) if outc_drug
                 else pd.DataFrame(columns=CORE_COLS["OUTC"]))
    ther_drug = (pd.concat(ther_drug, ignore_index=True) if ther_drug
                 else pd.DataFrame(columns=CORE_COLS["THER"]))

    log(f"[cache] 完成，用时 {time.time() - t_all:.0f} s")
    result = dict(
        n_total=n_total,
        ids={"PS": ps_kept, "PS+SS": psss_kept, "ALL": all_kept},
        a={k: pd.Series(v, dtype="int64") for k, v in a_cnt.items()},
        pt_total=pd.Series(totals, dtype="int64"),
        demo_drug=demo_drug,
        reac_drug=reac_drug,
        outc_drug=outc_drug,
        ther_drug=ther_drug,
    )
    if cache_dir:
        import pickle
        cd = Path(cache_dir)
        for k in ("demo_drug", "reac_drug", "outc_drug", "ther_drug"):
            result[k].to_pickle(cd / f"{k}.pkl")
        meta = {k: v for k, v in result.items()
                if k not in ("demo_drug", "reac_drug", "outc_drug", "ther_drug")}
        meta["quarters"] = sorted(quarters)
        with open(cd / "meta.pkl", "wb") as f:
            pickle.dump(meta, f)
        log(f"[cache] 已写入磁盘缓存 {cd}")
    return result
