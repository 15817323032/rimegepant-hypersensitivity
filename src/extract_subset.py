# -*- coding: utf-8 -*-
"""
从全量 FAERS 中抽取瑞美吉泮 PS 病例子集，供 Module 2（ML）与后续分析使用。

DEMO/REAC/OUTC/THER 直接复用流式缓存（stream_cache 的 4 个 pkl），
DRUG 需补一次流式扫描（缓存里没存目标药病例的用药行）。
输出布局：data/interim/rime_subset/RIME/{DEMO,DRUG,REAC,OUTC,THER}RIME.txt
        （RIME 为伪季度名，load_faers(raw, ["RIME"]) 可直接读取）
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.faers_io import CORE_COLS, iter_chunks  # noqa: E402


def _write(df: pd.DataFrame, fp: Path) -> None:
    fp.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.to_csv(fp, sep="$", index=False, lineterminator="\n",
               encoding="latin-1", columns=[c for c in out.columns
                                            if not c.startswith("_")])
    print(f"  [write] {fp.name}: {len(out):,} 行", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/interim/stream_cache")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/interim/rime_subset")
    a = ap.parse_args()

    cd = ROOT / a.cache
    with open(cd / "meta.pkl", "rb") as f:
        meta = pickle.load(f)
    ps_kept = set(meta["ids"]["PS"])
    print(f"[subset] 目标药 PS 病例（去重后）: {len(ps_kept):,}")

    out_dir = ROOT / a.out / "RIME"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in ("demo_drug", "reac_drug", "outc_drug", "ther_drug"):
        df = pd.read_pickle(cd / f"{name}.pkl")
        table = name.split("_")[0].upper()
        _write(df, out_dir / f"{table}RIME.txt")

    # ---- DRUG：流式扫描补齐目标药病例的用药行 ----
    parts = []
    quarters = meta["quarters"]
    for q in quarters:
        n = 0
        for ch in iter_chunks(ROOT / a.raw, "DRUG", q, CORE_COLS["DRUG"]):
            ch = ch.copy()
            ch["pid_norm"] = pd.to_numeric(ch["primaryid"], errors="coerce") \
                .astype("Int64").astype(str)
            sub = ch[ch["pid_norm"].isin(ps_kept)].drop(columns=["pid_norm"])
            if len(sub):
                parts.append(sub)
            n += len(sub)
        print(f"  [DRUG {q}] 命中 {n:,} 行", flush=True)
    drug = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    drug = drug.drop_duplicates(subset=["primaryid", "drug_seq"], keep="first")
    _write(drug, out_dir / "DRUGRIME.txt")
    print(f"[subset] 完成 -> {out_dir}")


if __name__ == "__main__":
    main()
