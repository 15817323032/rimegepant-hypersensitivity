# -*- coding: utf-8 -*-
"""重算 pre/post 标签修订比较（主分析剔除过渡季 2025Q3）。

审查意见 #5：2025Q3（7–9 月）混合了 8 月修订前后，不能整体视为修订后。
主分析：pre = 2020Q2–2025Q2，post = 2025Q4–2026Q2（Q3 剔除）；
敏感性：保留 Q3（即原 2025Q3 cut-off，post 含 Q3）。

统计口径与 src/label_change.py 完全一致：
Wilson z=1.96、Fisher 2x2、比例比 CI 用 log 尺度 SE。
数据源 results_label_change/ts_quarterly_family.csv（病例级季度聚合，
逐季求和等价于病例级统计）。
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
FAMS = ["Anaphylactoid", "Systemic hypersensitivity", "Oral mucosal",
        "Oral sensory", "Pharyngeal/airway", "Excipient reaction"]


def pct_ci(k: int, n: int):
    if n == 0:
        return (np.nan, np.nan)
    z = 1.96
    p = k / n
    den = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return (max(0, c - h), min(1, c + h))


def compare(pre, post):
    n_pre, n_post = int(pre["n"].sum()), int(post["n"].sum())
    rows = []
    for f in FAMS:
        k_pre, k_post = int(pre[f].sum()), int(post[f].sum())
        p_pre, p_post = k_pre / n_pre, k_post / n_post
        ci_pre, ci_post = pct_ci(k_pre, n_pre), pct_ci(k_post, n_post)
        table = [[k_pre, n_pre - k_pre], [k_post, n_post - k_post]]
        _, p_fisher = stats.fisher_exact(table)
        rr = p_post / p_pre if p_pre > 0 else np.nan
        se = np.sqrt(1 / max(k_pre, 1) - 1 / n_pre
                     + 1 / max(k_post, 1) - 1 / n_post)
        lo, hi = np.exp(np.log(rr) - 1.96 * se), np.exp(np.log(rr) + 1.96 * se)
        rows.append(dict(family=f, pre_cases=k_pre, pre_pct=100 * p_pre,
                         pre_ci_lo=100 * ci_pre[0], pre_ci_hi=100 * ci_pre[1],
                         post_cases=k_post, post_pct=100 * p_post,
                         post_ci_lo=100 * ci_post[0], post_ci_hi=100 * ci_post[1],
                         ratio_post_vs_pre=rr, ratio_lo=lo, ratio_hi=hi,
                         p_fisher=p_fisher))
    df = pd.DataFrame(rows)
    # Benjamini-Hochberg q across the six family comparisons (review round 2, #1)
    pvals = df["p_fisher"].values
    m = len(pvals)
    order = np.argsort(pvals)
    q_sorted = pvals[order] * m / np.arange(1, m + 1)
    q_sorted = np.minimum.accumulate(q_sorted[::-1])[::-1]  # enforce monotonicity
    qv = np.empty(m)
    qv[order] = q_sorted
    df["q_BH"] = qv
    return df, n_pre, n_post


def main():
    q = pd.read_csv(ROOT / "results_label_change/ts_quarterly_family.csv")
    pre = q[q.quarter <= "2025Q2"]
    post = q[(q.quarter >= "2025Q4")]
    sens_post = q[q.quarter >= "2025Q3"]

    df, n_pre, n_post = compare(pre, post)
    df.to_csv(ROOT / "results_label_change/prepost_family_comparison_primary.csv",
              index=False, encoding="utf-8-sig")
    print(f"[primary] pre n={n_pre:,} (2020Q2-2025Q2) | post n={n_post:,} "
          f"(2025Q4-2026Q2, Q3 excluded)")
    print(df[["family", "pre_cases", "pre_pct", "post_cases", "post_pct",
              "ratio_post_vs_pre", "p_fisher"]].round(3).to_string(index=False))

    dfs, _, n_sens = compare(pre, sens_post)
    dfs.to_csv(ROOT / "results_label_change/prepost_family_comparison_sens_keepq3.csv",
               index=False, encoding="utf-8-sig")
    print(f"\n[sensitivity] post n={n_sens:,} (Q3 retained): "
          f"ratios {dfs.ratio_post_vs_pre.min():.2f}-{dfs.ratio_post_vs_pre.max():.2f}, "
          f"all p>0.05: {bool((dfs.p_fisher > 0.05).all())}")

    # 刷新 all_tables_full.xlsx 的 T12_label_prepost sheet（主分析数字）
    p = ROOT / "results_full/all_tables_full.xlsx"
    import openpyxl
    wb = openpyxl.load_workbook(p)
    if "T12_label_prepost" in wb.sheetnames:
        del wb["T12_label_prepost"]
    ws = wb.create_sheet("T12_label_prepost")
    cols = ["family", "pre_cases", "pre_pct", "pre_ci_lo", "pre_ci_hi",
            "post_cases", "post_pct", "post_ci_lo", "post_ci_hi",
            "ratio_post_vs_pre", "ratio_lo", "ratio_hi", "p_fisher", "q_BH"]
    ws.append(cols)
    for _, r in df.iterrows():
        ws.append([r[c] for c in cols])
    wb.save(p)
    print("\n[ok] T12_label_prepost refreshed (primary, Q3 excluded)")


if __name__ == "__main__":
    main()
