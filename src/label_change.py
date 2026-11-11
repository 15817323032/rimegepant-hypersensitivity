# -*- coding: utf-8 -*-
"""
标签变更前后对比（2025Q3 为界）

背景：FDA 2025-04~06 季度「潜在严重风险」通报列入 Nurtec ODT 的
anaphylactic reaction，2025-08 修订【禁忌】与【警告及注意事项】（迟发型
严重超敏、高血压、Raynaud），TGA 2025-12 跟进。

分析内容（仅用瑞美吉泮 PS 病例自身，属于 within-drug 报告行为分析）：
  A. 季度时间序列：超敏谱（anaphylactoid / SYSTEMIC_HYPER / 口腔超敏）
     各 PT 家族的报告比例随季度变化
  B. 前（≤2025Q2）vs 后（≥2025Q3）：
     - 各家族报告比例 + Fisher 精确检验
     - 比例比（reporting proportion ratio）及其 95% CI
  C. 逐 PT 明细表（超敏谱内每个 PT 的前后计数与比例）
解读要点：比例上升可能混合真实风险上升与 notoriety bias（标签修订后
报告者对已知信号更敏感），不能单方面归因。

输出：results_label_change/ 下 3 个 csv + 1 张趋势图
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.pt_sets import (CORE_ORAL, EXCIPIENT,  # noqa: E402
                            PHARYNGEAL_AIRWAY, SENSORY, SYSTEMIC_HYPER,
                            normalize)
from src.faers_io import parse_faers_date  # noqa: E402

# 过敏性休克/速发严重超敏谱（FDA 2025-08 标签修订的核心触发 PT）
ANAPHYLACTOID = {
    "ANAPHYLACTIC REACTION", "ANAPHYLACTIC SHOCK", "ANAPHYLAXIS",
    "ANAPHYLACTOID REACTION", "ANGIOEDEMA", "ANGIONEUROTIC OEDEMA",
    "HYPERSENSITIVITY", "DRUG HYPERSENSITIVITY", "TYPE I HYPERSENSITIVITY",
    "STRIDOR", "BRONCHOSPASM", "LARYNGEAL OEDEMA", "THROAT TIGHTNESS",
    "SWOLLEN TONGUE", "PHARYNGEAL SWELLING", "ORAL OEDEMA",
    "SWELLING FACE", "URTICARIA",
}
CUTOFF = "2025Q3"          # fda_dt >= 2025-07-01 视为「标签修订后」
FAMILIES = {
    "Anaphylactoid": set(ANAPHYLACTOID),
    "Systemic hypersensitivity": set(SYSTEMIC_HYPER),
    "Oral mucosal": set(CORE_ORAL),
    "Oral sensory": set(SENSORY),
    "Pharyngeal/airway": set(PHARYNGEAL_AIRWAY),
    "Excipient reaction": set(EXCIPIENT),
}


def pct_ci(k: int, n: int):
    """Wilson 95% CI for proportion."""
    if n == 0:
        return (np.nan, np.nan)
    z = 1.96
    p = k / n
    den = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return (max(0, c - h), min(1, c + h))


def main():
    cd = ROOT / "data/interim/stream_cache"
    with open(cd / "meta.pkl", "rb") as f:
        meta = pickle.load(f)
    demo = pd.read_pickle(cd / "demo_drug.pkl")
    reac = pd.read_pickle(cd / "reac_drug.pkl")
    print(f"[label] PS 病例 {len(meta['ids']['PS']):,} | DEMO 行 {len(demo):,} "
          f"| REAC 行 {len(reac):,}")

    out = ROOT / "results_label_change"
    out.mkdir(exist_ok=True)

    # 病例级：pid -> fda_dt（日期）与季度
    demo = demo.copy()
    demo["pid"] = pd.to_numeric(demo["primaryid"], errors="coerce") \
        .astype("Int64").astype(str)
    dt = parse_faers_date(demo["fda_dt"])
    demo["fda_date"] = dt
    cutoff_date = pd.Timestamp("2025-07-01")
    demo["post"] = (demo["fda_date"] >= cutoff_date).astype(int)
    demo["quarter"] = demo["fda_date"].dt.year.astype(str) + "Q" + \
        demo["fda_date"].dt.quarter.astype(str)
    n_pre, n_post = int((demo["post"] == 0).sum()), int((demo["post"] == 1).sum())
    print(f"[label] 前期(≤2025Q2) {n_pre:,} 例 | 后期(≥2025Q3) {n_post:,} 例")
    print(f"[label] 日期范围 {demo['fda_date'].min()} ~ {demo['fda_date'].max()}")

    # 病例级 PT 集合
    reac = reac.copy()
    reac["pid"] = pd.to_numeric(reac["primaryid"], errors="coerce") \
        .astype("Int64").astype(str)
    reac["pt_n"] = reac["pt"].astype(str).map(normalize)
    pt_by_pid = reac.groupby("pid")["pt_n"].apply(set).to_dict()

    post_map = dict(zip(demo["pid"], demo["post"]))
    q_map = dict(zip(demo["pid"], demo["quarter"]))

    # ---------- A. 季度时间序列 ----------
    rows = []
    for pid, pts in pt_by_pid.items():
        q = q_map.get(pid)
        if q is None:
            continue
        row = {"quarter": q, "n": 1}
        for fam, s in FAMILIES.items():
            row[fam] = int(bool(pts & s))
        rows.append(row)
    ts = pd.DataFrame(rows).groupby("quarter", as_index=False).sum()
    qorder = sorted(ts["quarter"].unique(), key=lambda x: (x[:4], x[-1]))
    ts = ts.set_index("quarter").reindex(qorder).fillna(0).reset_index()
    ts["total"] = ts["n"]
    for fam in FAMILIES:
        ts[f"{fam}_pct"] = 100 * ts[fam] / ts["total"]
    ts.to_csv(out / "ts_quarterly_family.csv", index=False, encoding="utf-8-sig")
    print("[label] 季度序列 -> ts_quarterly_family.csv")

    # ---------- B. 前 vs 后：家族比例 + Fisher + 比例比 ----------
    comp = []
    for fam, s in FAMILIES.items():
        k_pre = sum(1 for pid, pts in pt_by_pid.items()
                    if pts & s and post_map.get(pid) == 0)
        k_post = sum(1 for pid, pts in pt_by_pid.items()
                     if pts & s and post_map.get(pid) == 1)
        p_pre, p_post = k_pre / n_pre, k_post / n_post
        ci_pre, ci_post = pct_ci(k_pre, n_pre), pct_ci(k_post, n_post)
        # Fisher 精确检验（2x2）
        table = [[k_pre, n_pre - k_pre], [k_post, n_post - k_post]]
        _, p_fisher = stats.fisher_exact(table)
        # 比例比（post/pre）的 95%CI（对数尺度）
        rr = p_post / p_pre if p_pre > 0 else np.nan
        se = np.sqrt(1 / max(k_pre, 1) - 1 / n_pre + 1 / max(k_post, 1) - 1 / n_post)
        lo, hi = np.exp(np.log(rr) - 1.96 * se), np.exp(np.log(rr) + 1.96 * se)
        comp.append(dict(family=fam, pre_cases=k_pre, pre_pct=100 * p_pre,
                         pre_ci_lo=100 * ci_pre[0], pre_ci_hi=100 * ci_pre[1],
                         post_cases=k_post, post_pct=100 * p_post,
                         post_ci_lo=100 * ci_post[0], post_ci_hi=100 * ci_post[1],
                         ratio_post_vs_pre=rr, ratio_lo=lo, ratio_hi=hi,
                         p_fisher=p_fisher))
    dfc = pd.DataFrame(comp)
    dfc.to_csv(out / "prepost_family_comparison.csv", index=False,
               encoding="utf-8-sig")
    print("[label] 前/后对比 -> prepost_family_comparison.csv")

    # ---------- C. 逐 PT 明细（超敏谱内 PT） ----------
    all_pts = set().union(*FAMILIES.values())
    detail = []
    for pt in sorted(all_pts):
        k_pre = sum(1 for pid, pts in pt_by_pid.items()
                    if pt in pts and post_map.get(pid) == 0)
        k_post = sum(1 for pid, pts in pt_by_pid.items()
                     if pt in pts and post_map.get(pid) == 1)
        if k_pre + k_post < 3:
            continue
        table = [[k_pre, n_pre - k_pre], [k_post, n_post - k_post]]
        _, p_fisher = stats.fisher_exact(table)
        detail.append(dict(pt=pt, pre=k_pre, pre_pct=100 * k_pre / n_pre,
                           post=k_post, post_pct=100 * k_post / n_post,
                           ratio=(k_post / n_post) / (k_pre / n_pre)
                           if k_pre else np.nan,
                           p_fisher=p_fisher))
    pd.DataFrame(detail).to_csv(out / "prepost_pt_detail.csv", index=False,
                                encoding="utf-8-sig")
    print(f"[label] 逐 PT 明细 -> prepost_pt_detail.csv（{len(detail)} 个 PT）")

    # ---------- 趋势图 ----------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.6))
    labels = {"Anaphylactoid": "Anaphylactoid reactions",
              "Systemic hypersensitivity": "Systemic hypersensitivity",
              "Oral mucosal": "Oral mucosal",
              "Oral sensory": "Oral sensory",
              "Pharyngeal/airway": "Pharyngeal/airway",
              "Excipient reaction": "Excipient reaction"}
    for fam, color in zip(FAMILIES, ["#C0392B", "#E67E22", "#2980B9",
                                     "#16A085", "#8E44AD", "#7F8C8D"]):
        ax.plot(qorder, ts[f"{fam}_pct"], marker="o", ms=3.5, lw=1.4,
                color=color, label=labels[fam])
    ax.axvline(qorder.index("2025Q2") + 0.5, color="black", ls="--", lw=1)
    ax.annotate("FDA label revision\n(Aug 2025)",
                xy=(qorder.index("2025Q2") + 0.5, ax.get_ylim()[1] * 0.9),
                fontsize=8, ha="left", va="top")
    ax.set_ylabel("Proportion of rimegepant reports (%)")
    ax.set_xlabel("FAERS quarter")
    ax.tick_params(axis="x", rotation=60, labelsize=7.5)
    ax.legend(fontsize=7.5, ncol=3, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "label_change_trend.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("[label] 图 -> label_change_trend.png")

    # 控制台摘要
    print("\n===== 前 vs 后摘要 =====")
    print(dfc[["family", "pre_cases", "pre_pct", "post_cases", "post_pct",
               "ratio_post_vs_pre", "p_fisher"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
