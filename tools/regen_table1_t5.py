# -*- coding: utf-8 -*-
"""用已提取的 PS 子集重算表 1 / 表 5，并对照旧值打印差异。

用途：年龄口径修正（src/ageutil.py 单位换算）后，无需重扫 11 GB 原始数据即可
把队列侧两张表刷新到新口径。参照人群侧另由
``python src/reference_population.py --rescan-demo`` 刷新。

运行:
    python tools/regen_table1_t5.py --dry-run     # 只打印差异
    python tools/regen_table1_t5.py               # 写回 results_full/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.run_module1 import table1, table5_subgroup  # noqa: E402

SUBSET = ROOT / "data/interim/rime_subset/RIME"


def load(name: str) -> pd.DataFrame:
    fp = SUBSET / f"{name}RIME.txt"
    df = pd.read_csv(fp, sep="$", dtype=str, encoding="latin-1",
                     low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.drop(columns=[c for c in df.columns if c == ""], errors="ignore")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results_full")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    demo, reac, outc = load("DEMO"), load("REAC"), load("OUTC")
    ids = set(demo["primaryid"].astype(str))
    print(f"[load] 子集病例 {len(ids):,} | REAC 行 {len(reac):,} | OUTC 行 {len(outc):,}")

    t1 = table1(demo, ids, reac, outc)
    t5 = table5_subgroup(demo, reac, ids)

    out = ROOT / a.out
    pairs = [("table1_baseline.csv", t1), ("table5_subgroup.csv", t5)]
    for fn, new in pairs:
        fp = out / fn
        old = pd.read_csv(fp, encoding="utf-8-sig") if fp.exists() else None
        print(f"\n=== {fn} ===")
        if old is not None and len(old) == len(new):
            key = [c for c in ("指标", "变量", "水平") if c in new.columns]
            val = [c for c in new.columns if c not in key]
            diff = []
            for i in range(len(new)):
                for c in val:
                    o, n = str(old.iloc[i][c]), str(new.iloc[i][c])
                    if o != n:
                        diff.append((i, c, o, n))
            if diff:
                for i, c, o, n in diff:
                    tag = " / ".join(str(new.iloc[i][k]) for k in key)
                    print(f"  [{tag}] {c}: {o}  ->  {n}")
            else:
                print("  无变化")
        else:
            print(f"  行数不同或旧文件缺失（old={None if old is None else len(old)} new={len(new)}）")

        if not a.dry_run:
            new.to_csv(fp, index=False, encoding="utf-8-sig")
            print(f"  [write] {fp.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
