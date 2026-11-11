# -*- coding: utf-8 -*-
"""
Module 1 —— FAERS 信号挖掘主流程（瑞美吉泮 × 口腔/超敏切口）

运行:
    python src/run_module1.py --raw data/raw --quarters 2020Q2 2020Q3 ... 2026Q2
    python src/run_module1.py --demo          # 用合成数据自检

产出 (results/):
    table1_baseline.csv        病例基线特征
    table2_all_signals.csv     全谱 PT 信号（四算法 + BH-FDR）
    table3_focus_signals.csv   口腔/超敏切口信号（带子集归属与严重性层级）
    table4_tto.csv             发病时间分布
    table5_subgroup.csv        亚组分析
    table6_sensitivity.csv     敏感性分析对照
    figures/forest_focus.png   重点信号森林图
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.pt_sets import (  # noqa: E402
    COMPOSITE_SET, DRUG_PATTERNS, INDICATION_SET, PT_SETS,
    SEVERITY_TIERS, normalize,
)
from src.faers_io import load_faers, parse_faers_date  # noqa: E402
from src.stats_disproportionality import compute_all_signals  # noqa: E402


# ---------------------------------------------------------------------------
# 药物识别
# ---------------------------------------------------------------------------
def flag_drug(drug: pd.DataFrame, patterns, role: str = "PS") -> set:
    """
    返回目标药相关 primaryid 集合。
    role: 'PS' 仅首要怀疑 | 'PS+SS' 首要+次要 | 'ALL' 全部角色（含合并用药）
    """
    names = drug["drugname"].fillna("").astype(str).str.upper()
    ai = drug.get("prod_ai", pd.Series("", index=drug.index)).fillna("").astype(str).str.upper()
    mask = pd.Series(False, index=drug.index)
    for p in patterns:
        mask |= names.str.contains(p, regex=True, na=False)
        mask |= ai.str.contains(p, regex=True, na=False)

    if role == "PS":
        mask &= drug["role_cod"].fillna("").str.upper().eq("PS")
    elif role == "PS+SS":
        mask &= drug["role_cod"].fillna("").str.upper().isin(["PS", "SS"])
    return set(drug.loc[mask, "primaryid"].astype(str))


# ---------------------------------------------------------------------------
# Table 1 基线
# ---------------------------------------------------------------------------
def table1(demo, drug_ids, reac, outc) -> pd.DataFrame:
    ids = {str(i) for i in drug_ids}
    d = demo[demo["primaryid"].astype(str).isin(ids)]

    age = pd.to_numeric(d.get("age"), errors="coerce")
    age_cod = d.get("age_cod", pd.Series("YR", index=d.index)).fillna("YR").astype(str).str.upper()
    age_yr = age.where(age_cod.eq("YR"), np.nan)
    age_yr = age_yr.where(age_yr.between(0, 120))

    agegrp = pd.cut(age_yr, [-1, 17, 44, 64, 200],
                    labels=["<18", "18-44", "45-64", ">=65"])

    reac_s = reac[reac["primaryid"].astype(str).isin(ids)]
    n_ae = reac_s.groupby("primaryid").size()
    outc_s = outc[outc["primaryid"].astype(str).isin(ids)]

    def pct(n, tot):
        return f"{n:,} ({100*n/tot:.1f}%)" if tot else "-"

    n = len(d)
    rows = [
        ("病例数 N", f"{n:,}"),
        ("年龄 中位数 (IQR)", f"{age_yr.median():.0f} ({age_yr.quantile(.25):.0f}-{age_yr.quantile(.75):.0f})"
         if age_yr.notna().any() else "NA"),
        ("年龄缺失", pct(int(age_yr.isna().sum()), n)),
        ("<18", pct(int((agegrp == "<18").sum()), n)),
        ("18-44", pct(int((agegrp == "18-44").sum()), n)),
        ("45-64", pct(int((agegrp == "45-64").sum()), n)),
        (">=65", pct(int((agegrp == ">=65").sum()), n)),
        ("女性", pct(int(d.get("sex", pd.Series(dtype=str)).astype(str).str.upper().eq("F").sum()), n)),
        ("男性", pct(int(d.get("sex", pd.Series(dtype=str)).astype(str).str.upper().eq("M").sum()), n)),
        ("性别缺失/未知", pct(int(d.get("sex", pd.Series(dtype=str)).astype(str).str.upper()
                              .isin(["", "UNK", "NAN"]).sum()), n)),
        # FAERS rept_cod 取值：EXP=医师/专家, PER=消费者, DIR=厂商代表,
        # LAW=律师, CSM=公司医学部, OTH/空=其他
        ("报告者 医师 (EXP)", pct(int(d.get("rept_cod", pd.Series(dtype=str)).astype(str).str.upper().eq("EXP").sum()), n)),
        ("报告者 消费者 (PER)", pct(int(d.get("rept_cod", pd.Series(dtype=str)).astype(str).str.upper().eq("PER").sum()), n)),
        ("报告者 厂商/其他 (DIR)", pct(int(d.get("rept_cod", pd.Series(dtype=str)).astype(str).str.upper().eq("DIR").sum()), n)),
        ("事件数 中位数 (IQR)", f"{n_ae.median():.0f} ({n_ae.quantile(.25):.0f}-{n_ae.quantile(.75):.0f})"
         if len(n_ae) else "NA"),
        ("严重结局 合计", pct(int(outc_s["primaryid"].nunique()), n)),
        ("  死亡 (DE)", pct(int(outc_s[outc_s["outc_cod"].astype(str).str.upper().eq("DE")]["primaryid"].nunique()), n)),
        ("  危及生命 (LT)", pct(int(outc_s[outc_s["outc_cod"].astype(str).str.upper().eq("LT")]["primaryid"].nunique()), n)),
        ("  住院 (HO)", pct(int(outc_s[outc_s["outc_cod"].astype(str).str.upper().eq("HO")]["primaryid"].nunique()), n)),
        ("  致残 (DS)", pct(int(outc_s[outc_s["outc_cod"].astype(str).str.upper().eq("DS")]["primaryid"].nunique()), n)),
    ]
    ctry = d.get("reporter_country")
    if ctry is not None:
        for c, k in ctry.astype(str).str.upper().value_counts().head(5).items():
            rows.append((f"国家 {c}", pct(int(k), n)))
    return pd.DataFrame(rows, columns=["特征", "值"])


# ---------------------------------------------------------------------------
# Table 3 切口信号标注
# ---------------------------------------------------------------------------
def annotate_focus(sig: pd.DataFrame, reac: pd.DataFrame, ids: set) -> pd.DataFrame:
    """给全谱信号表加：是否属于切口、子集、严重性层级、严重结局占比。"""
    m = sig.copy()
    m["in_focus"] = m["PT"].map(lambda p: normalize(p) in COMPOSITE_SET)
    m["is_indication_pt"] = m["PT"].map(lambda p: normalize(p) in INDICATION_SET)

    def subs(pt):
        n = normalize(pt)
        return ",".join(k for k, v in PT_SETS.items() if n in {normalize(x) for x in v})

    def tier(pt):
        n = normalize(pt)
        return ",".join(k for k, v in SEVERITY_TIERS.items()
                        if any(n in {normalize(x) for x in PT_SETS[s]} for s in v))

    m["subset"] = m["PT"].map(subs)
    m["severity_tier"] = m["PT"].map(tier)

    # 该 PT 报告中的严重结局比例
    r = reac[reac["primaryid"].astype(str).isin(ids)].copy()
    r["pt"] = r["pt"].astype(str).str.strip().str.upper()
    return m


# ---------------------------------------------------------------------------
# Table 4 TTO
# ---------------------------------------------------------------------------
def table4_tto(demo, ther, reac, ids, focus_only=True) -> pd.DataFrame:
    ids = {str(i) for i in ids}
    d = demo[demo["primaryid"].astype(str).isin(ids)][["primaryid", "event_dt"]].copy()
    d["event_dt"] = parse_faers_date(d["event_dt"])

    t = ther[ther["primaryid"].astype(str).isin(ids)].copy()
    if "dsg_drug_seq" in t.columns:
        t["seq"] = pd.to_numeric(t["dsg_drug_seq"], errors="coerce")
        t1 = t[t["seq"].eq(1)]
        t = t1 if len(t1) else t
    t["start_dt"] = parse_faers_date(t["start_dt"])
    t = t.dropna(subset=["start_dt"]).drop_duplicates("primaryid")
    mg = d.merge(t[["primaryid", "start_dt"]], on="primaryid", how="inner")
    mg["tto_days"] = (mg["event_dt"] - mg["start_dt"]).dt.days
    mg = mg[(mg["tto_days"] >= 0) & (mg["tto_days"] <= 3650)]

    bins = [-0.1, 1, 7, 30, 90, 3650]
    labels = ["<=1d", "2-7d", "8-30d", "31-90d", ">90d"]
    mg["tto_cat"] = pd.cut(mg["tto_days"], bins, labels=labels)

    tot = len(mg)
    rows = [("可计算 TTO 的病例数", f"{tot:,}")]
    if tot:
        rows += [
            ("TTO 中位数 (IQR)", f"{mg['tto_days'].median():.0f} "
                                 f"({mg['tto_days'].quantile(.25):.0f}-"
                                 f"{mg['tto_days'].quantile(.75):.0f}) 天"),
            ("TTO 报告完整率", f"{tot/len(ids)*100:.1f}%"),
        ]
        for lab in labels:
            k = int((mg["tto_cat"] == lab).sum())
            rows.append((lab, f"{k:,} ({100*k/tot:.1f}%)"))
    return pd.DataFrame(rows, columns=["指标", "值"])


# ---------------------------------------------------------------------------
# Table 5 亚组
# ---------------------------------------------------------------------------
def table5_subgroup(demo, reac, ids) -> pd.DataFrame:
    ids = {str(i) for i in ids}
    r = reac[reac["primaryid"].astype(str).isin(ids)].copy()
    r["pt_n"] = r["pt"].astype(str).str.strip().str.upper()
    r["is_focus"] = r["pt_n"].isin(COMPOSITE_SET)
    hit = set(r.loc[r["is_focus"], "primaryid"].astype(str))

    d = demo[demo["primaryid"].astype(str).isin(ids)].copy()
    d["age_n"] = pd.to_numeric(d.get("age"), errors="coerce")
    d["agegrp"] = pd.cut(d["age_n"], [-1, 17, 44, 64, 200],
                         labels=["<18", "18-44", "45-64", ">=65"])
    d["sex_n"] = d.get("sex", pd.Series(dtype=str)).astype(str).str.upper()
    d["rept_n"] = d.get("rept_cod", pd.Series(dtype=str)).astype(str).str.upper()
    d["year"] = parse_faers_date(d.get("fda_dt", pd.Series(dtype=str))).dt.year
    d["hit"] = d["primaryid"].astype(str).isin(hit)

    recs = []
    for var, label in [("sex_n", "性别"), ("agegrp", "年龄组"),
                       ("rept_n", "报告者"), ("year", "报告年份")]:
        for lv, g in d.groupby(var, observed=True):
            n, k = len(g), int(g["hit"].sum())
            if n < 20:
                continue
            lo, hi = _wilson(k, n)
            recs.append(dict(变量=label, 水平=str(lv), 报告数=n,
                             切口事件数=k, 占比=f"{100*k/n:.1f}%",
                             Wilson95CI=f"{100*lo:.1f}-{100*hi:.1f}"))
    return pd.DataFrame(recs)


def _wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z**2 / n
    c = (p + z**2 / (2*n)) / den
    h = z * np.sqrt(p*(1-p)/n + z**2/(4*n*n)) / den
    return max(0, c-h), min(1, c+h)


# ---------------------------------------------------------------------------
# 绘图
# ---------------------------------------------------------------------------
def plot_forest(df: pd.DataFrame, fp: Path, title: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = df.dropna(subset=["ROR", "ROR025", "ROR975"]).copy()
    d = d[(np.isfinite(d["ROR"])) & (d["ROR"] > 0)]
    d = d.sort_values("ROR", ascending=True).tail(25)
    if d.empty:
        print("  [fig] 无可用数据，跳过")
        return

    fig, ax = plt.subplots(figsize=(7.2, max(3.2, 0.28*len(d)+1.2)), dpi=300)
    y = np.arange(len(d))
    ax.hlines(y, d["ROR025"], d["ROR975"], color="#9aa5b1", lw=1.4)
    ax.scatter(d["ROR"], y, s=26,
               color=["#c0392b" if s else "#2c3e50"
                      for s in d.get("is_robust_signal", [False]*len(d))],
               zorder=3)
    ax.axvline(1, ls="--", lw=0.9, color="#7f8c8d")
    ax.set_yticks(y)
    ax.set_yticklabels(d["PT"].str.title(), fontsize=7)
    ax.set_xscale("log")
    ax.set_xlabel("ROR (95% CI, log scale)", fontsize=9)
    ax.set_title(title, fontsize=10, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="x", ls=":", lw=0.5, alpha=0.6)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(fp, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig] {fp.name}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--demo", action="store_true", help="用 data/demo 合成数据自检")
    ap.add_argument("--quarters", nargs="*", default=None)
    ap.add_argument("--role", default="PS", choices=["PS", "PS+SS", "ALL"])
    ap.add_argument("--out", default="results")
    a = ap.parse_args()

    if a.demo:
        raw = ROOT / "data/demo"
        quarters = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
    else:
        raw = Path(a.raw)
        if not a.quarters:
            sys.exit("请用 --quarters 指定季度，如 2020Q2 2020Q3 ... 2026Q2")
        quarters = a.quarters
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)

    # 1. 读取 + 去重
    d = load_faers(raw, quarters)
    demo, drug, reac, outc, ther = (d["DEMO"], d["DRUG"], d["REAC"],
                                    d["OUTC"], d["THER"])
    n_total = len(demo)

    # 2. 药物识别（多口径）
    ids_ps = flag_drug(drug, DRUG_PATTERNS, "PS")
    ids_all = flag_drug(drug, DRUG_PATTERNS, "ALL")
    ids_psss = flag_drug(drug, DRUG_PATTERNS, "PS+SS")
    print(f"[drug] rimegepant 病例: PS={len(ids_ps):,}  PS+SS={len(ids_psss):,}  "
          f"ALL={len(ids_all):,}  / 全库 {n_total:,}")

    if not ids_ps:
        sys.exit("未检出 rimegepant 报告，请检查 DRUG 表 drugname 与模式串")

    # 3. 四算法信号（主口径 PS）
    print("[signal] 计算全谱 PT 信号 ...")
    sig_all = compute_all_signals(ids_ps, reac, n_total)
    print(f"  -> {len(sig_all)} 个 PT (a>=3)，阳性 {int(sig_all['is_signal'].sum())} 个，"
          f"稳健阳性 {int(sig_all['is_robust_signal'].sum())} 个")

    # 4. 切口标注
    sig_focus = annotate_focus(sig_all, reac, ids_ps)
    focus_tbl = sig_focus[sig_focus["in_focus"]].copy()
    focus_tbl = focus_tbl.sort_values("ROR025", ascending=False)

    # 5. 输出
    t1 = table1(demo, ids_ps, reac, outc)
    t4 = table4_tto(demo, ther, reac, ids_ps)
    t5 = table5_subgroup(demo, reac, ids_ps)

    # 6. 敏感性分析
    sens = []
    for label, ids in [("主分析 PS", ids_ps), ("PS+SS", ids_psss), ("全部角色 ALL", ids_all)]:
        s = compute_all_signals(ids, reac, n_total)
        n_pos = int(s["is_signal"].sum())
        n_focus = int(s[s["PT"].map(lambda p: normalize(p) in COMPOSITE_SET)]["is_signal"].sum())
        sens.append(dict(口径=label, 病例数=len(ids), 阳性PT数=n_pos, 切口阳性=n_focus))

    # 排除适应证 PT 后重算
    reac_wo = reac[~reac["pt"].astype(str).str.strip().str.upper().isin(INDICATION_SET)]
    s_wo = compute_all_signals(ids_ps, reac_wo, n_total)
    sens.append(dict(口径="PS + 排除适应证PT", 病例数=len(ids_ps),
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

    plot_forest(focus_tbl, ROOT / "figures/forest_focus.png",
                "Rimegepant — oral / hypersensitivity signals (FAERS)")

    print("\n===== 切口阳性信号 Top 15 =====")
    cols = ["PT", "a", "ROR", "ROR025", "PRR", "IC025", "EB05", "subset", "severity_tier"]
    if len(focus_tbl):
        print(focus_tbl.head(15)[cols].to_string(index=False))
    else:
        print("（无）")


if __name__ == "__main__":
    main()
