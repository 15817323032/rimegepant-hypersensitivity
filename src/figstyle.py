# -*- coding: utf-8 -*-
"""House figure style for the rimegepant manuscript (Drug Safety submission).

One place for palette, typography and export rules, shared by every figure
script so the four main figures + supplement look like one paper, not four
plotting defaults.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# ---------------------------------------------------------------- palette ---
INK = "#1F1F1F"          # text, spines
MUTED = "#767676"        # secondary text
GRID = "#E8E8E8"         # gridlines
BAND = "#F2F2F2"         # shaded period band

SIGNAL = "#A63446"       # robust signal (crimson, muted)
NEUTRAL = "#4E6E8E"      # non-signal / default data ink (slate blue)
ACCENT = "#3E6C9E"       # single-hue bars, lines

# Okabe-Ito derived, saturation pulled down ~20% -- colour-blind safe
FAMILY_COLORS = {
    "Anaphylactoid reactions": "#B94A2C",
    "Systemic hypersensitivity": "#3E6C9E",
    "Oral mucosal": "#3D8B6E",
    "Oral sensory": "#D19A2F",
    "Pharyngeal/airway": "#8F6793",
    "Excipient reaction": "#8C8C8C",
}

# SHAP diverging: low feature value (slate) -> mid (pale grey) -> high (crimson)
SHAP_CMAP = LinearSegmentedColormap.from_list(
    "shap_muted", ["#3E6C9E", "#D9DDE2", "#A63446"])

# ---------------------------------------------------------------- type ------
FONT = "Arial"
S_LABEL = 8.0     # axis titles
S_TICK = 7.0      # tick labels
S_SMALL = 6.5     # annotations, captions
S_TITLE = 8.5     # panel titles

# journal widths (inches)
W_DOUBLE = 7.2    # double column
W_15 = 5.5        # 1.5 column
W_SINGLE = 3.5    # single column

DPI = 450


def apply() -> None:
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [FONT, "DejaVu Sans"],
        "font.size": S_TICK,
        "axes.edgecolor": INK,
        "axes.linewidth": 0.8,
        "axes.labelcolor": INK,
        "axes.labelsize": S_LABEL,
        "axes.titlesize": S_TITLE,
        "xtick.color": INK, "ytick.color": INK,
        "xtick.labelsize": S_TICK, "ytick.labelsize": S_TICK,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "legend.frameon": False,
        "legend.fontsize": S_SMALL,
        "figure.dpi": 110,
        "savefig.dpi": DPI,
        "svg.fonttype": "none",
    })


def despine(ax, keep=("left", "bottom")) -> None:
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)


def light_grid(ax, axis="x") -> None:
    ax.grid(axis=axis, color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)


def note(fig, text: str, y: float = 0.005, x: float = 0.008) -> None:
    """One-line encoding guide inside the figure (what the marks mean).

    Kept deliberately short and muted: the journal caption says what the
    figure shows, this says how to read it, so the image is self-explanatory
    when a reader meets it out of context.
    """
    fig.text(x, y, text, fontsize=S_SMALL, color=MUTED, ha="left", va="bottom")


def save(fig, path: Path, pad: float = 0.02) -> Path:
    """Tight export; returns the written path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", pad_inches=pad)
    plt.close(fig)
    print(f"  [fig] {path.name}  ({path.stat().st_size/1024:.0f} kB)")
    return path
