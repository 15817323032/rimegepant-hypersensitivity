# -*- coding: utf-8 -*-
"""Render the four main figures from canonical result files with the house style.

Data sources (single source of truth, same as the figure-data package):
  Fig 1  results_full/table3_focus_signals.csv      (25 highest-ROR focus PTs)
  Fig 2  results_label_change/ts_quarterly_family.csv
  Fig 3  results_ml_real/ml_shap_values.csv + ml_feature_table.csv
  Fig 4  results/network_tox/*.csv

Output: figures_restyled/ (preview; copy into submission after approval)
Run:    .venv/Scripts/python.exe tools/make_figures.py [--out DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import figstyle as fs  # noqa: E402  (src/ on path)

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

OUT = ROOT / "figures_restyled"


# ------------------------------------------------------------------ Fig 1 ---
def fig1_forest() -> None:
    d = pd.read_csv(ROOT / "results_full" / "table3_focus_signals.csv")
    d = d.dropna(subset=["ROR", "ROR025", "ROR975"])
    d = d[np.isfinite(d["ROR"]) & (d["ROR"] > 0)]
    d = d.sort_values("ROR", ascending=True).tail(25).reset_index(drop=True)
    d = d.rename(columns={"ROR025": "ROR_95CI_low", "ROR975": "ROR_95CI_high",
                          "is_robust_signal": "robust_signal"})
    d["label"] = d["PT"].str.title()

    XMAX = 150.0
    off = d["ROR_95CI_high"] > XMAX          # rows whose CI runs off the axis
    plot_r = d["ROR"].clip(upper=XMAX * 0.93)
    lo = d["ROR_95CI_low"].clip(lower=0.3, upper=XMAX)
    hi = d["ROR_95CI_high"].clip(upper=XMAX)

    h = 0.235 * len(d) + 0.9
    fig, ax = plt.subplots(figsize=(fs.W_DOUBLE, h))
    y = np.arange(len(d))

    ax.hlines(y, lo, hi, color="#B9BEC4", lw=1.1, zorder=2)
    colors = [fs.SIGNAL if s else fs.NEUTRAL for s in d["robust_signal"]]
    ax.scatter(plot_r, y, s=22, c=colors, zorder=3, linewidths=0)
    for i in np.where(off)[0]:
        ax.annotate("", xy=(XMAX * 0.99, y[i]), xytext=(XMAX * 0.93, y[i]),
                    arrowprops=dict(arrowstyle="-|>", color="#B9BEC4", lw=1.0))

    ax.axvline(1, color=fs.MUTED, ls=(0, (4, 3)), lw=0.8, zorder=1)
    ax.set_xscale("log")
    ax.set_xlim(0.3, XMAX * 1.02)
    ax.set_ylim(-0.8, len(d) - 0.2)
    ax.set_yticks(y)
    ax.set_yticklabels(d["label"])
    ax.set_xlabel("Reporting odds ratio (log scale; whiskers, 95% CI)")
    fs.light_grid(ax)

    # right-hand count columns, aligned to rows
    trans = ax.get_yaxis_transform()
    for i, r in d.iterrows():
        ax.text(1.030, i, f"{int(r['a']):,}", transform=trans,
                fontsize=fs.S_SMALL, ha="left", va="center", color=fs.MUTED)
        ax.text(1.115, i, f"{int(r['c']):,}", transform=trans,
                fontsize=fs.S_SMALL, ha="left", va="center", color=fs.MUTED)
    ax.text(1.030, len(d) + 0.3, "Cases", transform=trans, fontsize=fs.S_SMALL,
            ha="left", va="bottom", color=fs.INK, fontweight="bold")
    ax.text(1.115, len(d) + 0.3, "Rest of database", transform=trans,
            fontsize=fs.S_SMALL, ha="left", va="bottom", color=fs.INK,
            fontweight="bold")

    handles = [Line2D([], [], marker="o", ls="", ms=5, color=fs.SIGNAL,
                      label="Robust signal (4/4 algorithms)"),
               Line2D([], [], marker="o", ls="", ms=5, color=fs.NEUTRAL,
                      label="Signal not robust"),
               Line2D([], [], color=fs.MUTED, ls=(0, (4, 3)), lw=0.8,
                      label="ROR = 1 (null)"),
               Line2D([], [], color="#B9BEC4", lw=1.1,
                      label="95% CI (truncated at axis edge)")]
    ax.legend(handles=handles, loc="lower right", fontsize=fs.S_SMALL,
              handletextpad=0.4, borderaxespad=0.3)

    fs.save(fig, OUT / "Figure_1.png")


# ------------------------------------------------------------------ Fig 2 ---
def fig2_trend() -> None:
    ts = pd.read_csv(ROOT / "results_label_change" / "ts_quarterly_family.csv")
    quarters = ts["quarter"].tolist()
    labels = {"Anaphylactoid": "Anaphylactoid reactions",
              "Systemic hypersensitivity": "Systemic hypersensitivity",
              "Oral mucosal": "Oral mucosal",
              "Oral sensory": "Oral sensory",
              "Pharyngeal/airway": "Pharyngeal/airway",
              "Excipient reaction": "Excipient reaction"}
    fams = list(labels)

    fig, ax = plt.subplots(figsize=(fs.W_DOUBLE, 3.6))
    x = np.arange(len(quarters))

    # shaded post-revision period instead of a dashed line
    i_cut = quarters.index("2025Q3")
    ax.axvspan(i_cut - 0.5, len(quarters) - 0.5, color=fs.BAND, zorder=0)
    ax.text(i_cut + 0.2, 22.3, "Post-label revision", fontsize=fs.S_SMALL,
            color=fs.MUTED, style="italic", ha="left")

    ends = {}
    for fam in fams:
        c = fs.FAMILY_COLORS[labels[fam]]
        ax.plot(x, ts[f"{fam}_pct"], color=c, lw=1.15, marker="o", ms=2.3,
                markeredgewidth=0, zorder=2)
        ends[fam] = ts[f"{fam}_pct"].iloc[-1]

    # direct end labels with collision nudge
    order = sorted(ends, key=ends.get)
    min_gap = 0.9
    placed = []
    for fam in order:
        yy = ends[fam]
        if placed and yy - placed[-1] < min_gap:
            yy = placed[-1] + min_gap
        placed.append(yy)
        c = fs.FAMILY_COLORS[labels[fam]]
        ax.annotate(labels[fam], xy=(len(quarters) - 1 + 0.35, yy),
                    fontsize=fs.S_SMALL, color=c, va="center",
                    fontweight="bold")

    ax.set_xlim(-0.5, len(quarters) + 5.2)
    ax.set_ylim(-0.6, 23.5)
    ax.set_xticks(x)
    ax.set_xticklabels(quarters, rotation=60, ha="right")
    ax.set_ylabel("Proportion of rimegepant reports (%)")
    ax.set_xlabel("FAERS quarter")
    fs.light_grid(ax, axis="y")

    fs.save(fig, OUT / "Figure_2.png")


# ------------------------------------------------------------------ Fig 3 ---
SHAP_DROP = {"sex_male", "report_year_centered"}   # mirror / redundant features


def fig3_shap() -> None:
    sv = pd.read_csv(ROOT / "results_ml_real" / "ml_shap_values.csv")
    ft = pd.read_csv(ROOT / "results_ml_real" / "ml_feature_table.csv")
    feats = [c for c in sv.columns if c not in SHAP_DROP]
    sv = sv[feats]
    order = sv.abs().mean().sort_values(ascending=True).index.tolist()
    sv = sv[order]

    n_feat = len(feats)
    h = 0.26 * n_feat + 1.9
    fig, ax = plt.subplots(figsize=(fs.W_15, h))

    rng = np.random.default_rng(42)
    NBINS = 60
    LEVELS = 13          # vertical slots per row (±0.32 at 0.055 step)
    STEP = 0.055
    for i, f in enumerate(order):        # iterate in the SAME order as labels
        x = sv[f].to_numpy()
        v = ft[f].to_numpy(dtype=float)
        uniq = np.unique(v[~np.isnan(v)])
        is_binary = uniq.size <= 2
        vmax = np.nanmax(v) if np.isfinite(v).any() else 1.0
        v = v / vmax if vmax else v * 0
        # NaN（如缺失的 age/weight/tto）会命中 colormap 的 bad color，
        # 与 collection alpha 叠加后渲染成纯黑点 → 统一映射到色图中部浅灰
        v = np.where(np.isnan(v), 0.5, v)
        if is_binary:
            # nudge the two value groups apart so colours stay legible where
            # their SHAP values coincide near zero
            x = x + (v - 0.5) * 0.03
        bins = np.quantile(x, np.linspace(0, 1, NBINS + 1))
        idx = np.clip(np.digitize(x, bins[1:-1]), 0, NBINS - 1)
        for b in range(NBINS):
            m = idx == b
            n = int(m.sum())
            if n == 0:
                continue
            # cycle through vertical slots: lens-shaped swarm, no hard edge rows
            offs = (np.arange(n) % LEVELS - (LEVELS - 1) / 2) * STEP
            ax.scatter(x[m], i + offs, s=1.2, linewidths=0,
                       c=fs.SHAP_CMAP(v[m]), alpha=0.40,
                       rasterized=True, zorder=2)

    ax.axvline(0, color=fs.MUTED, lw=0.8, zorder=1)
    ax.set_yticks(range(n_feat))
    ax.set_yticklabels([fs_label(f) for f in order])
    ax.set_xlabel("SHAP value (impact on model output)")
    ax.set_ylim(-0.9, n_feat - 0.1)
    fs.light_grid(ax, axis="x")

    # colourbar for feature magnitude
    sm = plt.cm.ScalarMappable(cmap=fs.SHAP_CMAP,
                               norm=plt.Normalize(0, 1))
    cax = ax.inset_axes([1.02, 0.02, 0.025, 0.55])
    cb = fig.colorbar(sm, cax=cax)
    cb.set_ticks([0, 1])
    cb.set_ticklabels(["Low", "High"])
    cb.ax.tick_params(labelsize=fs.S_SMALL, length=0)
    cb.set_label("Feature value", fontsize=fs.S_SMALL)
    cb.outline.set_visible(False)

    ax.text(0.0, -0.135,
            "Positivity in the top vs bottom quartile of the leading feature "
            "(female sex): 12.9% vs 6.2%.",
            transform=ax.transAxes, fontsize=fs.S_SMALL, color=fs.MUTED)

    fs.save(fig, OUT / "Figure_3.png")


def fs_label(f: str) -> str:
    return FEATURE_LABELS.get(f, f)


FEATURE_LABELS = {
    "sex_female": "Female sex", "sex_missing": "Sex missing",
    "age": "Age", "age_missing": "Age missing", "age_lt18": "Age < 18",
    "age_ge65": "Age ≥ 65", "weight": "Weight", "report_year": "Report year",
    "country_us": "Country: United States", "n_drugs": "Number of drugs",
    "n_aes": "Number of AEs", "tto_days": "Time to onset (days)",
    "tto_missing": "Time to onset missing",
    "combo_antihistamine": "Concomitant antihistamine",
    "combo_corticosteroid": "Concomitant corticosteroid",
    "combo_nsaid": "Concomitant NSAID", "combo_triptan": "Concomitant triptan",
    "combo_ppi": "Concomitant PPI", "combo_ssri_snri": "Concomitant SSRI/SNRI",
    "combo_betablocker": "Concomitant β-blocker",
    "combo_anticonvulsant": "Concomitant antiepileptic",
    "combo_cgrp_mab": "Concomitant CGRP mAb",
}


# ------------------------------------------------------------------ Fig 4 ---
def fig4_network() -> None:
    ntd = ROOT / "results" / "network_tox"
    tgt = pd.read_csv(ntd / "predicted_targets.csv").head(3)
    hubs = pd.read_csv(ntd / "ppi_hubs.csv").head(12)
    go = pd.read_csv(ntd / "enrichment_go_bp.csv").head(10)

    fig, axes = plt.subplots(1, 3, figsize=(fs.W_DOUBLE, 3.1),
                             gridspec_kw={"width_ratios": [1.0, 1.1, 1.3]})

    ax = axes[0]
    y = np.arange(len(tgt))[::-1]
    ax.barh(y, tgt["score"], color=fs.ACCENT, height=0.55)
    hi = int(np.argmax(tgt["score"].to_numpy()))
    ax.barh(y[hi], tgt["score"].iloc[hi], color=fs.SIGNAL, height=0.55)
    ax.set_yticks(y)
    ax.set_yticklabels(tgt["gene"], fontsize=fs.S_TICK)
    ax.set_xlabel("Similarity score")
    ax.set_title("Predicted targets\n(ChEMBL similarity)", loc="left",
                 fontsize=fs.S_TITLE, fontweight="bold")

    ax = axes[1]
    y = np.arange(len(hubs))[::-1]
    ax.barh(y, hubs["degree"], color=fs.ACCENT, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(hubs["gene"], fontsize=fs.S_TICK)
    ax.set_xlabel("STRING degree")
    ax.set_title("PPI hub genes", loc="left", fontsize=fs.S_TITLE,
                 fontweight="bold")

    ax = axes[2]
    go = go.assign(nlp=-np.log10(go["adj_p_value"].clip(lower=1e-300)))
    import textwrap
    y = np.arange(len(go))[::-1]
    ax.barh(y, go["nlp"], color=fs.ACCENT, height=0.6)
    ax.set_yticks(y)
    wrapped = [textwrap.fill(t, 24) for t in
               go["term"].str.replace(r"\s*\(GO:\d+\)", "", regex=True)]
    ax.set_yticklabels(wrapped, fontsize=fs.S_SMALL)
    ax.set_xlabel(r"$-\log_{10}P_{\mathrm{adj}}$")
    ax.set_title("GO-BP enrichment", loc="left", fontsize=fs.S_TITLE,
                 fontweight="bold")

    for ax in axes:
        fs.despine(ax)
        fs.light_grid(ax, axis="x")
        ax.tick_params(axis="y", length=0)

    fig.subplots_adjust(wspace=0.80, left=0.07, right=0.985, top=0.80,
                        bottom=0.14)
    fs.save(fig, OUT / "Figure_4.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--install", action="store_true",
                    help="also copy the restyled figures to the canonical "
                         "paths consumed by make_submission.py / "
                         "build_figure_package.py")
    a = ap.parse_args()
    globals()["OUT"] = Path(a.out)
    fs.apply()
    print(f"渲染到 {OUT}")
    fig1_forest()
    fig2_trend()
    fig3_shap()
    fig4_network()

    if a.install:
        import shutil
        canon = {
            "Figure_1.png": ROOT / "results_full/forest_focus.png",
            "Figure_2.png": ROOT / "results_label_change/label_change_trend.png",
            "Figure_3.png": ROOT / "figures/shap_summary.png",
            "Figure_4.png": ROOT / "results/network_tox/figures/network_tox_summary.png",
        }
        for src_name, dst in canon.items():
            shutil.copy2(OUT / src_name, dst)
            print(f"  [install] {dst.relative_to(ROOT)} <- {src_name}")


if __name__ == "__main__":
    main()
