"""Build the figure source-data package (figures + tidy data + dictionary + scripts).

Output: figure_data_package/  and  rimegepant_figure_data_package_<date>.zip
Run:    .venv/Scripts/python.exe tools/build_figure_package.py
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "figure_data_package"
FIG = PKG / "figures"
SRC = PKG / "source_data"
CODE = PKG / "code"

FIGS = [
    ("Figure_1.png", "Figure_1_forest_focus.png",
     "results_full/forest_focus.png"),
    ("Figure_2.png", "Figure_2_label_change_trend.png",
     "results_label_change/label_change_trend.png"),
    ("Figure_3.png", "Figure_3_shap_summary.png",
     "figures/shap_summary.png"),
    ("Figure_4.png", "Figure_4_network_tox.png",
     "results/network_tox/figures/network_tox_summary.png"),
]

# ROC/PR 曲线为补充材料图 S1（位于投稿包根目录，而非 figures/ 子目录）
SUPP_FIGS = [
    ("Supplementary_Figure_S1.png", "Supplementary_Figure_S1_roc_pr_curves.png"),
]


def fig1_table() -> pd.DataFrame:
    """Exactly the rows drawn by run_module1.plot_forest(): the 49 focus-cluster PTs,
    ROR finite & > 0, ascending, last 25 -> the 25 highest-ROR points on Figure 1."""
    d = pd.read_csv(ROOT / "results_full" / "table3_focus_signals.csv")
    d = d.dropna(subset=["ROR", "ROR025", "ROR975"])
    d = d[np.isfinite(d["ROR"]) & (d["ROR"] > 0)]
    d = d.sort_values("ROR", ascending=True).tail(25)
    out = pd.DataFrame({
        "PT": d["PT"],
        "n_reports_case": d["a"].astype(int),
        "n_reports_nondrug": d["c"].astype(int),
        "ROR": d["ROR"].round(3),
        "ROR_95CI_low": d["ROR025"].round(3),
        "ROR_95CI_high": d["ROR975"].round(3),
        "PRR": pd.to_numeric(d["PRR"], errors="coerce").round(2),
        "IC025": d["IC025"].round(2),
        "EB05": d["EB05"].round(2),
        "n_algorithms_positive": d["n_algo"].astype(int),
        "is_signal": d["is_signal"].astype(bool),
        "robust_signal": d["is_robust_signal"].astype(bool),
        "severity_tier": d.get("severity_tier", ""),
        "cluster_subset": d.get("subset", ""),
    })
    return out.sort_values("ROR", ascending=False).reset_index(drop=True)


def main() -> None:
    for p in (FIG, SRC, CODE):
        p.mkdir(parents=True, exist_ok=True)

    # ---------------- figures ----------------
    for src_name, dst_name, _ in FIGS:
        shutil.copy2(ROOT / "submission_drugsafety" / "figures" / src_name, FIG / dst_name)
    for src_name, dst_name in SUPP_FIGS:
        shutil.copy2(ROOT / "submission_drugsafety" / src_name, FIG / dst_name)
    stale = FIG / "Figure_5_network_tox.png"
    if stale.exists():
        stale.unlink()

    # ---------------- Fig 1 ----------------
    t1 = fig1_table()
    t1.to_csv(SRC / "Fig1_forest_focus.csv", index=False, encoding="utf-8-sig")

    # ---------------- Fig 2 ----------------
    lc = ROOT / "results_label_change"
    f2a = pd.read_csv(lc / "prepost_family_comparison.csv")
    f2b = pd.read_csv(lc / "prepost_pt_detail.csv")
    f2c = pd.read_csv(lc / "ts_quarterly_family.csv")
    f2a.to_csv(SRC / "Fig2a_family_pre_post.csv", index=False, encoding="utf-8-sig")
    f2b.to_csv(SRC / "Fig2b_PT_detail.csv", index=False, encoding="utf-8-sig")
    f2c.to_csv(SRC / "Fig2c_quarterly_family.csv", index=False, encoding="utf-8-sig")

    # ---------------- Fig 3（SHAP，正文图） ----------------
    ml = ROOT / "results_ml_real"
    f3a = pd.read_csv(ml / "ml_shap_importance.csv").round(5)
    f3b = pd.read_csv(ml / "ml_top_feature_strata.csv")
    f3a.to_csv(SRC / "Fig3a_shap_importance.csv", index=False, encoding="utf-8-sig")
    f3b.to_csv(SRC / "Fig3b_top_feature_strata.csv", index=False, encoding="utf-8-sig")
    sv = pd.read_csv(ml / "ml_shap_values.csv")
    sv.round(5).to_csv(SRC / "Fig3c_shap_values_per_report.csv", index=False, encoding="utf-8-sig")

    # ---------------- Fig 4（网络毒理，正文图） ----------------
    F4 = SRC / "Fig4_network"
    F4.mkdir(exist_ok=True)
    nt = ROOT / "results" / "network_tox"
    for fn, new in [
        ("bridge_genes.csv", "Fig4a_bridge_genes.csv"),
        ("enrichment_kegg.csv", "Fig4b_KEGG_enrichment.csv"),
        ("enrichment_go_bp.csv", "Fig4c_GO_BP_enrichment.csv"),
        ("ppi_hubs.csv", "Fig4d_PPI_hubs.csv"),
        ("ae_gene_sets.csv", "Fig4e_adverse_event_gene_sets.csv"),
        ("predicted_targets.csv", "Fig4f_predicted_targets.csv"),
        ("measured_targets.csv", "Fig4g_measured_targets.csv"),
        ("intersection_genes.csv", "Fig4h_intersection_genes.csv"),
    ]:
        pd.read_csv(nt / fn).to_csv(F4 / new, index=False, encoding="utf-8-sig")
    shutil.copy2(nt / "drug_info.json", F4 / "Fig4i_drug_info.json")
    stale_net = SRC / "Fig5_network"
    if stale_net.exists():
        shutil.rmtree(stale_net)
    stale_f5 = SRC / "Fig5a_bridge_genes.csv"
    if stale_f5.exists():
        stale_f5.unlink()

    # ---------------- Supplementary Fig S1（模型性能表） ----------------
    s1 = pd.read_csv(ml / "ml_model_comparison.csv")
    s1 = s1[["model", "auc_mean", "auc_sd", "ap_mean", "ap_sd", "brier_mean", "brier_raw_mean"]]
    s1 = s1.rename(columns={
        "model": "model",
        "auc_mean": "AUC_mean", "auc_sd": "AUC_SD",
        "ap_mean": "AP_mean", "ap_sd": "AP_SD",
        "brier_mean": "Brier_prior_corrected", "brier_raw_mean": "Brier_raw_balanced_weights",
    })
    for c in ("AUC_mean", "AUC_SD", "AP_mean", "AP_SD",
              "Brier_prior_corrected", "Brier_raw_balanced_weights"):
        s1[c] = s1[c].round(4)
    s1.to_csv(SRC / "SuppS1_model_performance.csv", index=False, encoding="utf-8-sig")
    stale_f3perf = SRC / "Fig3_model_performance.csv"
    if stale_f3perf.exists():
        stale_f3perf.unlink()
    for old in ("Fig4a_shap_importance.csv", "Fig4b_top_feature_strata.csv",
                "Fig4c_shap_values_per_report.csv"):
        p_old = SRC / old
        if p_old.exists():
            p_old.unlink()

    # ---------------- code ----------------
    for fn in ("run_module1.py", "label_change.py", "ml_risk.py", "network_tox.py"):
        shutil.copy2(ROOT / "src" / fn, CODE / fn)

    # ---------------- workbook ----------------
    sheets = {
        "Fig1_forest": t1,
        "Fig2a_family": f2a,
        "Fig2b_PT_detail": f2b,
        "Fig2c_quarterly": f2c,
        "Fig3a_shap_importance": f3a,
        "Fig3b_strata": f3b,
        "Fig4a_bridge_genes": pd.read_csv(F4 / "Fig4a_bridge_genes.csv"),
        "Fig4b_KEGG": pd.read_csv(F4 / "Fig4b_KEGG_enrichment.csv"),
        "Fig4c_GO_BP": pd.read_csv(F4 / "Fig4c_GO_BP_enrichment.csv"),
        "Fig4d_PPI_hubs": pd.read_csv(F4 / "Fig4d_PPI_hubs.csv").head(100),
        "SuppS1_models": s1,
    }
    with pd.ExcelWriter(PKG / "figure_source_data.xlsx", engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)

    # ---------------- readme ----------------
    readme = (ROOT / "tools" / "figure_package_readme.md").read_text(encoding="utf-8")
    readme = readme.replace("{{DATE}}", date.today().isoformat())
    (PKG / "README.md").write_text(readme, encoding="utf-8")

    # ---------------- zip ----------------
    zpath = ROOT / f"rimegepant_figure_data_package_{date.today().isoformat()}.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(PKG.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(PKG.parent))
    size = zpath.stat().st_size / 1024 / 1024
    print(f"package: {PKG}")
    print(f"zip    : {zpath.name}  ({size:.1f} MB)")
    print(f"fig1 rows drawn: {len(t1)} | shap matrix: {sv.shape}")


if __name__ == "__main__":
    main()
