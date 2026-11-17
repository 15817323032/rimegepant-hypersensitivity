# -*- coding: utf-8 -*-
"""Assemble figures + tables into ONE reading copy (Figures_Tables_reading_copy.docx).

Purpose: reviewing the visual material without flipping between 17 separate
files. Not a submission artefact -- the journal gets figures and tables as
separate files, exactly as the submission suite already provides.

Everything is pulled from the same sources the submission suite uses
(TITLES / SOURCES / LEGENDS in tools/make_submission.py), so the reading copy
can never drift from the submitted numbers.

Run: .venv/Scripts/python.exe tools/build_review_packet.py
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm, Inches, Pt
from PIL import Image

ROOT = Path(r"C:/Users/wu-ke/WorkBuddy/2026-11-09-16-31-05/rimegepant_hypersensitivity")
OUT = ROOT / "Figures_Tables_reading_copy.docx"

FIGS = [
    ("Figure 1.", ROOT / "submission/figures/Figure_1.png"),
    ("Figure 2.", ROOT / "submission/figures/Figure_2.png"),
    ("Figure 3.", ROOT / "submission/figures/Figure_3.png"),
    ("Figure 4.", ROOT / "submission/figures/Figure_4.png"),
    ("Supplementary Figure S1.", ROOT / "submission/supplementary/Supplementary_Figure_S1.png"),
]

PREVIEW_ROWS = 100     # same cut-off as ROW_LIMIT_DOCX: only the tables delivered as
                       # .xlsx for submission (Table 2, 437 rows) get a preview here
MAX_W, MAX_H = 6.4, 7.6  # inches available for an image beside its legend

# A few tables still carry their result-file column names; the submission tables
# keep them (machine-readable supplements), the reading copy should not.
HEADER_PRETTY = {
    # Table 8
    "feature": "Feature", "mean_abs_shap": "Mean |SHAP|",
    # Table 9
    "gene": "Bridge gene", "bridge_count": "Shortest-path traversals",
    "min_hops": "Min. hops from anchor", "connects": "Connects (module)",
    "in_ae_set": "In event module",
    # Table 10
    "library": "Library", "term": "Term", "p_value": "P", "z_score": "z-score",
    "combined_score": "Combined score", "n_overlap": "Overlap",
    "genes": "Genes", "adj_p_value": "q (BH)",
    # Table 12
    "family": "Family", "pre_cases": "Pre, n", "pre_pct": "Pre, %",
    "pre_ci_lo": "Pre 95% CI low", "pre_ci_hi": "Pre 95% CI high",
    "post_cases": "Post, n", "post_pct": "Post, %",
    "post_ci_lo": "Post 95% CI low", "post_ci_hi": "Post 95% CI high",
    "ratio_post_vs_pre": "Post/pre ratio", "ratio_lo": "Ratio 95% CI low",
    "ratio_hi": "Ratio 95% CI high", "p_fisher": "P (Fisher)",
    # Table 11
    "pdb": "PDB", "n_modes": "Modes", "box_volume_A3": "Box volume (Å³)",
    "exhaustiveness": "Exhaustiveness", "seed": "Seed", "receptor": "Receptor file",
}


def load_make_submission():
    spec = importlib.util.spec_from_file_location(
        "mk", ROOT / "tools" / "make_submission.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mk"] = mod
    spec.loader.exec_module(mod)
    return mod


def page_setup(doc):
    sec = doc.sections[0]
    sec.orientation = 0
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin = sec.bottom_margin = Cm(2.0)


def add_footer(doc, text):
    p = doc.sections[0].footer.paragraphs[0]
    p.text = text
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in p.runs:
        r.font.size = Pt(8)
        r.font.name = "Times New Roman"


def caption(doc, tag, text, mk, size=9.5):
    p = doc.add_paragraph()
    r = p.add_run(tag + " ")
    r.bold = True
    r.font.size = Pt(size)
    mk.add_runs(p, text)
    for r in p.runs:
        r.font.size = Pt(size)
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(10)
    return p


def figure_block(doc, tag, path, text, mk, first=False):
    if not first:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    w, h = Image.open(path).size
    aspect = h / w
    width = min(MAX_W, MAX_H / aspect)
    ip = doc.add_paragraph()
    ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ip.add_run().add_picture(str(path), width=Inches(width))
    ip.paragraph_format.space_after = Pt(8)
    caption(doc, tag, text, mk)


def table_block(doc, n, rows, title, footnote, landscape, mk, total_rows=None):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    p = doc.add_paragraph()
    r = p.add_run(f"Table {n}.")
    r.bold = True
    r.font.size = Pt(13)
    p.paragraph_format.space_after = Pt(2)

    tp = doc.add_paragraph()
    tr = tp.add_run(title)
    tr.bold = True
    tr.font.size = Pt(10)
    tp.paragraph_format.space_after = Pt(6)

    ncols = max(len(r_) for r_ in rows) if rows else 1
    wide = landscape or ncols > 8
    mk.add_md_table(doc, rows, landscape=wide, font_size=9 if ncols <= 8 else 7.5)

    doc.add_paragraph()
    if total_rows and total_rows > len(rows) - 1:
        pv = doc.add_paragraph()
        pr = pv.add_run(f"Preview: first {len(rows) - 1} of {total_rows} data rows. "
                        f"Full table: submission/tables/Table_{n:02d}.xlsx.")
        pr.italic = True
        pr.font.size = Pt(8.5)
    fp = doc.add_paragraph()
    mk.add_runs(fp, footnote)
    for r in fp.runs:
        r.font.size = Pt(8.5)
    fp.paragraph_format.line_spacing = 1.15


def main():
    mk = load_make_submission()
    doc = Document()
    mk.set_normal_style(doc, spacing=1.3)
    mk.style_heading(doc)
    page_setup(doc)
    add_footer(doc, "Figures & Tables — internal reading copy "
                    f"({date.today().isoformat()}); not for submission")

    # ---------------------------------------------------------- cover block
    p = doc.add_paragraph()
    r = p.add_run("Figures and Tables")
    r.bold = True
    r.font.size = Pt(22)
    p.paragraph_format.space_after = Pt(4)

    p = doc.add_paragraph()
    r = p.add_run("Reading copy — rimegepant oral/hypersensitivity FAERS study")
    r.font.size = Pt(13)
    r.italic = True
    p.paragraph_format.space_after = Pt(14)

    sub = doc.add_paragraph()
    r = sub.add_run("Oral and hypersensitivity-spectrum adverse events of rimegepant orally "
                    "disintegrating tablets: a disproportionality analysis of the FDA Adverse "
                    "Event Reporting System (FAERS), 2020–2026, with machine-learning, "
                    "network-toxicology and docking follow-up")
    r.font.size = Pt(11)
    sub.paragraph_format.space_after = Pt(14)

    note = doc.add_paragraph()
    mk.add_runs(note, (
        f"Contents: 4 main figures + 1 supplementary figure, {len(mk.TITLES)} numbered tables. Figures are the R/ggplot2 "
        "renders at 450 dpi (Arial, house palette); table content is read from the same result "
        "files that feed the submission suite. Figure and table numbers match the manuscript. "
        "This file exists so the visual material can be reviewed in one pass; the journal receives "
        "figures and tables as separate files (`submission/figures`, `submission/tables`)."))
    for r in note.runs:
        r.font.size = Pt(9.5)
    note.paragraph_format.line_spacing = 1.3

    # ---------------------------------------------------------------- figures
    hdr = doc.add_paragraph()
    hdr.add_run().add_break(WD_BREAK.PAGE)
    hp = doc.add_paragraph()
    hr = hp.add_run("Figures")
    hr.bold = True
    hr.font.size = Pt(16)
    hp.paragraph_format.space_after = Pt(10)

    legends = dict(mk.LEGENDS)
    legends.update(dict(mk.SUPP_LEGENDS))
    for tag, path in FIGS:
        figure_block(doc, tag, path, legends[tag], mk)

    # ----------------------------------------------------------------- tables
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    hp = doc.add_paragraph()
    hr = hp.add_run("Tables")
    hr.bold = True
    hr.font.size = Pt(16)
    hp.paragraph_format.space_after = Pt(6)

    for n in sorted(mk.TITLES):
        title, footnote, landscape = mk.TITLES[n]
        kind, path, sheet, cap = mk.SOURCES[n]
        rows = (mk.xlsx_rows(path, sheet, cap) if kind == "xlsx"
                else mk.csv_rows(path, cap))
        rows = mk.translate_rows(rows)
        if rows:
            rows[0] = [HEADER_PRETTY.get(str(c), c) for c in rows[0]]
        total = len(rows) - 1 if rows else 0          # data rows, excluding header
        clipped = rows[:PREVIEW_ROWS + 1] if len(rows) > PREVIEW_ROWS + 1 else rows
        print(f"  table {n:2d}: {total} rows" + (" (preview)" if clipped is not rows else ""))
        table_block(doc, n, clipped, title, footnote, landscape, mk, total_rows=total)

    doc.save(OUT)
    print(f"saved {OUT}")
    print(f"  figures: {len(FIGS)}  tables: {len(mk.TITLES)}")


if __name__ == "__main__":
    main()
