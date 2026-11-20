# -*- coding: utf-8 -*-
"""Supplementary Figure S2: study flow diagram (review round 2, item #9).

Shows the case flow from the raw quarterly FAERS/AEMS extracts through
deduplication, drug matching and exposure-role filtering to the 8,962
primary-suspect analysis cohort, plus the two downstream subsets
(composite-endpoint label for the ML module; usable time-to-onset dates).

Run: .venv/Scripts/python.exe tools/make_flow_diagram.py
Out:  results_full/Supplementary_Figure_S2_flow.png  (preview)
      submission_drugsafety/Supplementary_Figure_S2.png (submission copy)
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parent.parent

INK    = "#1F1F1F"
MUTED  = "#767676"
ACCENT = "#3E6C9E"
FILL   = "#EDF2F7"
FILL2  = "#F7F1EC"
EDGE   = "#9FB3C8"

BOXES = [
    ("FAERS/AEMS public ASCII quarterly extracts",
     "25 quarters, 2020Q2 \u2013 2026Q2", FILL),
    ("FDA-recommended deduplication",
     "latest fda_dt / primaryid per caseid \u2192 N = 9,094,154 cases", FILL),
    ("Rimegepant drug match (DRUG drugname / prod_ai)",
     "RIMEGEPANT, RIMEGEPANT SULFATE, RIMEGEPANT BENZOATE,\n"
     "NURTEC, VYDURA, BMS-927711", FILL),
    ("Exposure-role selection (sensitivity axis)",
     "primary suspect (PS) 8,962 \u00b7 PS + secondary suspect (SS) 9,691 \u00b7 "
     "all roles 13,190", FILL2),
    ("Analysis cohort: rimegepant primary-suspect cases",
     "n = 8,962", FILL2),
]

SIDE = [
    ("Machine-learning module: composite-endpoint label",
     "932 cases (10.4% of the cohort)"),
    ("Time-to-onset subset: both dates recorded",
     "1,060 cases (11.8%); after excluding 208 negative\n"
     "intervals and 4 intervals > 730 days: 848 (9.5%)"),
]

W, H = 7.2, 7.6
fig, ax = plt.subplots(figsize=(W, H))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

n = len(BOXES)
top, bottom = 0.895, 0.30
ys = [top - i * (top - bottom) / (n - 1) for i in range(n)]
BH, BW = 0.105, 0.78
cx = 0.44

for (title, sub, col), yc in zip(BOXES, ys):
    box = FancyBboxPatch((cx - BW / 2, yc - BH / 2), BW, BH,
                         boxstyle="round,pad=0.008,rounding_size=0.012",
                         fc=col, ec=EDGE, lw=0.8)
    ax.add_patch(box)
    ax.text(cx, yc + 0.022, title, ha="center", va="center",
            fontsize=8.6, color=INK, fontweight="bold")
    ax.text(cx, yc - 0.026, sub, ha="center", va="center",
            fontsize=7.4, color=MUTED)

for y0, y1 in zip(ys[:-1], ys[1:]):
    ax.add_patch(FancyArrowPatch((cx, y0 - BH / 2 - 0.004),
                                 (cx, y1 + BH / 2 + 0.004),
                                 arrowstyle="-|>", mutation_scale=12,
                                 color=ACCENT, lw=1.1))

# two downstream branches from the cohort box
bx = [0.44, 0.44]
branch_y = 0.145
for i, (title, sub) in enumerate(SIDE):
    bxc = 0.27 if i == 0 else 0.71
    box = FancyBboxPatch((bxc - 0.21, branch_y - 0.075), 0.42, 0.15,
                         boxstyle="round,pad=0.008,rounding_size=0.012",
                         fc="#FFFFFF", ec=EDGE, lw=0.8, ls="--")
    ax.add_patch(box)
    ax.text(bxc, branch_y + 0.038, title, ha="center", va="center",
            fontsize=7.6, color=INK, fontweight="bold")
    ax.text(bxc, branch_y - 0.028, sub, ha="center", va="center",
            fontsize=7.0, color=MUTED)
    ax.add_patch(FancyArrowPatch((cx, ys[-1] - BH / 2 - 0.004),
                                 (bxc, branch_y + 0.075),
                                 connectionstyle="arc3,rad=0.18" if i == 1
                                 else "arc3,rad=-0.18",
                                 arrowstyle="-|>", mutation_scale=11,
                                 color=ACCENT, lw=1.0, ls="--"))

ax.text(0.5, 0.995, "Study flow: from quarterly extracts to the analysis sets",
        ha="center", va="top", fontsize=9.5, color=INK, fontweight="bold")

fig.subplots_adjust(left=0.01, right=0.99, top=0.985, bottom=0.005)
for out in [ROOT / "results_full/Supplementary_Figure_S2_flow.png",
            ROOT / "submission_drugsafety/Supplementary_Figure_S2.png"]:
    fig.savefig(out, dpi=450, facecolor="white")
    print("saved", out)
