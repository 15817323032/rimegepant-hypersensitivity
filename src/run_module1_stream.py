# -*- coding: utf-8 -*-
"""
Module 1（流式版）：25 季度全窗口信号挖掘

与 run_module1.py 的差别只在数据供给方式：
  run_module1.py        全量载入 DataFrame（适合 1-4 个季度）
  run_module1_stream.py 多遍流式聚合计数（25 季度 / 11 GB 全窗口）

用法：
    python src/run_module1_stream.py --raw data/raw --out results_full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.pt_sets import (  # noqa: E402
    COMPOSITE_SET, DRUG_PATTERNS, INDICATION_SET, normalize,
)
from src.stream_cache import build  # noqa: E402
from src.stats_disproportionality import compute_signals_from_counts  # noqa: E402
from src.run_module1 import (  # noqa: E402
    annotate_focus, plot_forest, table1, table4_tto, table5_subgroup,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="results_full")
    ap.add_argument("--chunksize", type=int, default=2_000_000)
    ap.add_argument("--quarters", nargs="*", default=None,
                    help="指定季度（默认扫描 data/raw 下全部季度目录）")
    a = ap.parse_args()

    quarters = a.quarters or sorted(
        p.name for p in Path(a.raw).glob("20*Q*")
        if p.is_dir() and len(p.name) == 6)
    if not quarters:
        sys.exit("data/raw 下未找到季度目录（形如 2020Q2）")
    print(f"[FAERS] 季度: {len(quarters)} 个（{quarters[0]} ~ {quarters[-1]}）")

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)

    c = build(Path(a.raw), quarters, DRUG_PATTERNS, chunksize=a.chunksize,
              cache_dir=ROOT / "data/interim/stream_cache")
    n_total = c["n_total"]
    demo, reac, outc, ther = (c["demo_drug"], c["reac_drug"],
                              c["outc_drug"], c["ther_drug"])
    ids = c["ids"]
    print(f"[drug] 目标药病例: PS={len(ids['PS']):,}  PS+SS={len(ids['PS+SS']):,}  "
          f"ALL={len(ids['ALL']):,}  / 全库 {n_total:,}")

    # 主分析：PS 口径
    print("[signal] 计算全谱 PT 信号（PS 口径）...")
    sig_all = compute_signals_from_counts(c["a"]["PS"], c["pt_total"],
                                          len(ids["PS"]), n_total)
    print(f"  -> {len(sig_all)} 个 PT (a>=3)，阳性 {int(sig_all['is_signal'].sum())} 个，"
          f"稳健阳性 {int(sig_all['is_robust_signal'].sum())} 个")

    sig_focus = annotate_focus(sig_all, reac, ids["PS"])
    focus_tbl = (sig_focus[sig_focus["in_focus"]]
                 .sort_values("ROR025", ascending=False).copy())

    t1 = table1(demo, ids["PS"], reac, outc)
    t4 = table4_tto(demo, ther, reac, ids["PS"])
    t5 = table5_subgroup(demo, reac, ids["PS"])

    # 敏感性分析（全部由计数派生，无需重扫数据）
    sens = []
    for label, key in (("主分析 PS", "PS"), ("PS+SS", "PS+SS"), ("全部角色 ALL", "ALL")):
        s = compute_signals_from_counts(c["a"][key], c["pt_total"],
                                        len(ids[key]), n_total)
        n_focus = int(s[s["PT"].map(lambda p: normalize(p) in COMPOSITE_SET)]
                      ["is_signal"].sum())
        sens.append(dict(口径=label, 病例数=len(ids[key]),
                         阳性PT数=int(s["is_signal"].sum()), 切口阳性=n_focus))

    # 排除适应证 PT：从分子分母同时剔除该 PT，等价于用过滤后的 REAC 重算
    keep_idx = [p for p in c["pt_total"].index
                if normalize(p) not in INDICATION_SET]
    s_wo = compute_signals_from_counts(c["a"]["PS"].reindex(keep_idx).dropna(),
                                       c["pt_total"].loc[keep_idx],
                                       len(ids["PS"]), n_total)
    sens.append(dict(口径="PS + 排除适应证PT", 病例数=len(ids["PS"]),
                     阳性PT数=int(s_wo["is_signal"].sum()),
                     切口阳性=int(s_wo[s_wo["PT"].map(
                         lambda p: normalize(p) in COMPOSITE_SET)]["is_signal"].sum())))
    t6 = pd.DataFrame(sens)

    files = {
        "table1_baseline.csv": t1,
        "table2_all_signals.csv": sig_all,
        "table3_focus_signals.csv": focus_tbl,
        "table4_tto.csv": t4,
        "table5_subgroup.csv": t5,
        "table6_sensitivity.csv": t6,
    }
    for fn, df in files.items():
        df.to_csv(out / fn, index=False, encoding="utf-8-sig")
        print(f"  [out] {fn}  ({len(df)} 行)")

    with pd.ExcelWriter(out / "all_tables.xlsx", engine="openpyxl") as w:
        for fn, df in files.items():
            df.to_excel(w, sheet_name=fn.replace(".csv", "")[:31], index=False)

    fig = out / "forest_focus.png"
    plot_forest(focus_tbl, fig,
                "Rimegepant — oral / hypersensitivity signals (FAERS 2020Q2-2026Q2)")
    print(f"  [fig] {fig}")

    print("\n===== 切口阳性信号 Top 15 =====")
    cols = ["PT", "a", "ROR", "ROR025", "PRR", "IC025", "EB05",
            "subset", "severity_tier"]
    if len(focus_tbl):
        print(focus_tbl.head(15)[[x for x in cols if x in focus_tbl.columns]]
              .to_string(index=False))
    else:
        print("（无）")

    print("\n===== 敏感性分析 =====")
    print(t6.to_string(index=False))


if __name__ == "__main__":
    main()
