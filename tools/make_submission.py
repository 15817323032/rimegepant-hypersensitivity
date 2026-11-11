# -*- coding: utf-8 -*-
"""Build the Headache/ScholarOne submission suite from manuscript_en.md + result sources.

Outputs (submission/):
  main_manuscript.docx          Title page + Abstract + body + Figure legends + References
                                (Times New Roman 12, double-spaced; numbered tables replaced
                                by placeholders, tables delivered as separate files)
  tables/Table_01..12.docx      One Word file per table (landscape when wide)
  figures/Figure_1..5.png       Figure files
"""
import csv, re, shutil
from pathlib import Path
import openpyxl
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT

ROOT = Path(r"C:/Users/wu-ke/WorkBuddy/2026-11-09-16-31-05/rimegepant_hypersensitivity")
OUT = ROOT / "submission"
TBL = OUT / "tables"
FIG = OUT / "figures"
for d in (TBL, FIG):
    d.mkdir(parents=True, exist_ok=True)

FONT = "Times New Roman"

# ---------------------------------------------------------------- style helpers
def set_normal_style(doc, spacing=2.0):
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(12)
    st.element.rPr.rFonts.set(
        __import__("docx").oxml.ns.qn("w:eastAsia"), FONT)
    pf = st.paragraph_format
    pf.line_spacing = spacing
    pf.space_after = Pt(6)

def style_heading(doc):
    for name, size in (("Heading 1", 14), ("Heading 2", 12), ("Heading 3", 12)):
        h = doc.styles[name]
        h.font.name = FONT
        h.font.size = Pt(size)
        h.font.bold = True
        h.font.color.rgb = RGBColor(0, 0, 0)
        h.paragraph_format.line_spacing = 2.0
        h.paragraph_format.space_before = Pt(12)
        h.paragraph_format.space_after = Pt(6)

def add_runs(p, text):
    """Render **bold** and *italic* inline markdown into runs."""
    tokens = re.split(r"(\*\*.+?\*\*|\*[^*]+?\*)", text)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            r = p.add_run(tok[2:-2]); r.bold = True
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            r = p.add_run(tok[1:-1]); r.italic = True
        else:
            p.add_run(tok)

def add_para(doc, text, align=None, bold=False, size=None, spacing=2.0):
    p = doc.add_paragraph()
    add_runs(p, text)
    if bold or size:
        for r in p.runs:
            if bold: r.bold = True
            if size: r.font.size = Pt(size)
    if align: p.alignment = align
    p.paragraph_format.line_spacing = spacing
    return p

def add_md_table(doc, rows, landscape=False, font_size=10):
    if landscape:
        sec = doc.add_section()
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
        sec.left_margin = sec.right_margin = Cm(1.5)
        sec.top_margin = sec.bottom_margin = Cm(1.5)
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            c = t.cell(i, j)
            c.text = ""
            p = c.paragraphs[0]
            add_runs(p, str(cell))
            p.paragraph_format.line_spacing = 1.0
            for r in p.runs:
                r.font.size = Pt(font_size)
                if i == 0: r.bold = True
    if landscape:  # back to portrait for subsequent content
        sec = doc.add_section()
        sec.orientation = WD_ORIENT.PORTRAIT
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
        sec.left_margin = sec.right_margin = Cm(2.5)
        sec.top_margin = sec.bottom_margin = Cm(2.5)

# ---------------------------------------------------------------- table sources
def xlsx_rows(path, sheet, max_rows=None):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = []
    for r in ws.iter_rows(values_only=True):
        rows.append(["" if v is None else str(v) for v in r])
        if max_rows and len(rows) >= max_rows:
            break
    wb.close()
    # trim trailing empty columns
    if rows:
        w = max(len(r) for r in rows)
        keep = 0
        for j in range(w - 1, -1, -1):
            if any(len(r) > j and r[j].strip() for r in rows):
                keep = j + 1; break
        rows = [r[:keep] + [""] * (keep - len(r)) for r in rows]
    return rows

def csv_rows(path, max_rows=None):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if max_rows: rows = rows[:max_rows]
    return rows

TITLES = {
    1: ("Baseline characteristics of rimegepant primary-suspect reports (n = 8,962)",
        "FAERS/AEMS 2020Q2–2026Q2 after FDA-recommended deduplication (N = 9,094,154); exposure role primary suspect (PS). Percentages are of non-missing values.", False),
    2: ("All positive disproportionality signals for rimegepant (a ≥ 3, BH-FDR corrected)",
        "ROR, reporting odds ratio; PRR, proportional reporting ratio; IC025, lower bound of the Bayesian confidence propagation neural network information component; EB05, lower bound of the empirical Bayes geometric mean. Positive: ROR025 > 1, PRR ≥ 2 & χ² ≥ 4, IC025 > 0, EB05 > 2. 'Robust' = positive in ≥ 2 algorithms. Focus = within the pre-specified oral/hypersensitivity composite endpoint.", True),
    3: ("Core disproportionality signals in the oral/hypersensitivity focus cluster",
        "Sorted by ROR. a = number of deduplicated rimegepant primary-suspect reports with the PT; ROR025 = lower bound of the 95% CI.", False),
    4: ("Time-to-onset distribution of composite-endpoint events",
        "TTO = event date − drug start date, in days, among reports with both dates complete (completeness 9.5%).", False),
    5: ("Focus-cluster signals by subgroup (sex, age group, report year)",
        "Within-drug reporting proportions with Wilson 95% CIs.", False),
    6: ("Sensitivity analyses: indication-PT exclusion and triple exposure roles",
        "Indication-bias control: migraine-symptom PTs (nausea, vomiting, headache, migraine, photophobia, phonophobia) excluded in recalculation. Exposure roles: PS (primary), PS+SS, ALL.", False),
    7: ("Machine-learning model comparison (repeated stratified 5-fold × 3 cross-validation)",
        "Label = composite-endpoint positivity (932/8,962, 10.4%); 29 features; serious outcomes and event counts excluded (leakage control). AUC, area under the ROC curve (mean ± SD); AP, average precision; Brier, Brier score.", False),
    8: ("SHAP global feature importance of the best model (random forest), top 15",
        "Mean absolute SHAP values over cross-validation folds.", False),
    9: ("Bridge genes from the bridged network-toxicology analysis",
        "BFS ≤ 4 hops from drug anchors (CALCRL/RAMP1/CALCA) on the anchor ∪ event-module STRING network (score ≥ 700); ranked by shortest-path traversal counts.", False),
    10: ("KEGG pathway enrichment of the bridged network (Enrichr, BH-corrected)",
         "Top 20 terms by adjusted p (q) value.", True),
    11: ("Molecular docking results (AutoDock Vina 1.2.5, exhaustiveness 16, seed 42)",
         "Pre-registered criteria: CALCRL ΔG ≤ −8 kcal/mol validates the docking system; off-target Δ = ΔG(CALCRL) − ΔG(target) ≥ 2 kcal/mol = no receptor-level off-target evidence; Δ < 2 = grey zone.", False),
    12: ("Reporting proportions of hypersensitivity families before vs after the August 2025 label revision (2025Q3 cut-off)",
         "Within-drug proportions among rimegepant primary-suspect reports (pre n = 8,283; post n = 679); Fisher exact test.", False),
}

SOURCES = {
    1: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table1_baseline", None),
    2: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table2_all_signals", None),
    3: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table3_focus_signals", None),
    4: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table4_tto", None),
    5: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table5_subgroup", None),
    6: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table6_sensitivity", None),
    7: ("xlsx", ROOT / "results_full/all_tables_full.xlsx", "T7_ML_models", None),
    8: ("xlsx", ROOT / "results_full/all_tables_full.xlsx", "T8_SHAP_top15", None),
    9: ("csv", ROOT / "results/network_tox/bridge_genes.csv", None, None),
    10: ("csv", ROOT / "results/network_tox/enrichment_kegg.csv", None, 21),
    11: ("xlsx", ROOT / "results_full/all_tables_supplement.xlsx", "T11_docking", None),
    12: ("xlsx", ROOT / "results_full/all_tables_full.xlsx", "T12_label_prepost", None),
}

ROW_LIMIT_DOCX = 100  # larger tables go out as .xlsx (journal accepts xlsx supplements)

ZH_MAP = {
    "特征": "Characteristic", "值": "Value", "病例数 N": "Cases, N",
    "年龄 中位数 (IQR)": "Age, median (IQR)", "年龄缺失": "Age missing",
    "女性": "Female", "男性": "Male", "性别缺失/未知": "Sex missing/unknown",
    "报告者 医师 (EXP)": "Reporter, physician (EXP)",
    "报告者 消费者 (PER)": "Reporter, consumer (PER)",
    "报告者 厂商/其他 (DIR)": "Reporter, manufacturer/other (DIR)",
    "事件数 中位数 (IQR)": "Events per case, median (IQR)",
    "严重结局 合计": "Serious outcomes, total",
    "  死亡 (DE)": "  Death (DE)", "死亡 (DE)": "Death (DE)",
    "  危及生命 (LT)": "  Life-threatening (LT)", "危及生命 (LT)": "Life-threatening (LT)",
    "  住院 (HO)": "  Hospitalisation (HO)", "住院 (HO)": "Hospitalisation (HO)",
    "  致残 (DS)": "  Disability (DS)", "致残 (DS)": "Disability (DS)",
    "国家 US": "Country, US", "国家 GB": "Country, GB", "国家 CL": "Country, CL",
    "国家 EU": "Country, EU", "国家 JP": "Country, JP",
    "指标": "Metric", "可计算 TTO 的病例数": "Cases with computable TTO",
    "TTO 中位数 (IQR)": "TTO, median (IQR)", "0 (0-5) 天": "0 (0–5) days",
    "TTO 报告完整率": "TTO reporting completeness",
    "变量": "Variable", "水平": "Level", "报告数": "Reports, n",
    "切口事件数": "Focus events, n", "占比": "Proportion", "Wilson95CI": "Wilson 95% CI",
    "性别": "Sex", "年龄组": "Age group", "报告者": "Reporter", "报告年份": "Report year",
    "口径": "Analysis", "主分析 PS": "Primary analysis (PS)", "PS+SS": "PS + SS",
    "全部角色 ALL": "All roles (ALL)", "PS + 排除适应证PT": "PS + indication-PT exclusion",
    "病例数": "Cases, n", "阳性PT数": "Positive PTs", "切口阳性": "Focus-positive PTs",
    "on-target 阳性对照（≤−8 判据通过）": "On-target positive control (≤ −8 kcal/mol criterion met)",
    "无受体级 off-target（弱于 CALCRL ≥2 kcal/mol）": "No receptor-level off-target (≥ 2 kcal/mol weaker than CALCRL)",
    "Δ<2 kcal/mol：不能单凭分值下结论，需结合药物警戒证据": "Δ < 2 kcal/mol: score alone inconclusive; interpret jointly with pharmacovigilance evidence",
    "interpretation": "Interpretation", "target": "Target", "best_affinity": "Best affinity (kcal/mol)",
    "mean_top3": "Top-3 mean (kcal/mol)", "delta_vs_on_target": "Δ vs on-target (kcal/mol)",
}

def translate_rows(rows):
    out = []
    for r in rows:
        out.append([ZH_MAP.get(str(c).strip(), ZH_MAP.get(str(c), c)) for c in r])
    return out

def build_table_files():
    for n, (title, footnote, landscape) in TITLES.items():
        kind, path, sheet, cap = SOURCES[n]
        rows = (xlsx_rows(path, sheet, cap) if kind == "xlsx"
                else csv_rows(path, cap))
        rows = translate_rows(rows)
        if len(rows) > ROW_LIMIT_DOCX:
            import openpyxl as _oxl
            wb = _oxl.Workbook()
            ws = wb.active
            ws.append([f"Table {n}. {title}"])
            for r in rows:
                ws.append(r)
            ws.append([])
            ws.append([footnote])
            out = TBL / f"Table_{n:02d}.xlsx"
            wb.save(out)
            print("saved", out.name, f"({len(rows)} rows, xlsx)")
            continue
        doc = Document()
        set_normal_style(doc, spacing=1.0); style_heading(doc)
        # Table number + title
        add_para(doc, f"Table {n}.", bold=True, spacing=1.0)
        add_para(doc, title, bold=True, spacing=1.0)
        doc.add_paragraph()
        ncols = max(len(r) for r in rows) if rows else 0
        add_md_table(doc, rows, landscape=(landscape or ncols > 8), font_size=9)
        doc.add_paragraph()
        add_para(doc, footnote, spacing=1.0)
        for r in doc.paragraphs:
            for run in r.runs:
                run.font.name = FONT; run.font.size = run.font.size or Pt(12)
        out = TBL / f"Table_{n:02d}.docx"
        doc.save(out)
        print("saved", out.name, f"({len(rows)} rows x {ncols} cols)")

# ---------------------------------------------------------------- main manuscript
DROP_TABLES = [  # (header signature, table number placeholder)
    (("ROR (95% CI lower)", "Subset / tier"), 3),
    (("Model", "AUC", "AP", "Brier"), 7),
    (("Family", "Pre %", "Post %"), 12),
    (("Bridge gene", "Bridge count"), 9),
    (("Target (PDB)", "Role"), 11),
]

def build_main_manuscript():
    text = (ROOT / "docs/manuscript_en.md").read_text(encoding="utf-8")
    lines = text.splitlines()

    doc = Document()
    set_normal_style(doc); style_heading(doc)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.5)
    sec.top_margin = sec.bottom_margin = Cm(2.5)

    i = 0
    in_title = False
    started = False
    while i < len(lines):
        line = lines[i]; s = line.strip()
        if not started:
            if s.startswith("# Title"):
                started = True; in_title = True
            i += 1; continue
        if s.startswith("# §Journal fit"):
            break
        if s in ("---", ""):
            i += 1; continue
        if s.startswith(">"):  # skip remaining blockquote notes
            i += 1; continue

        # table block?
        if s.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in row):
                    tbl.append(row)
                i += 1
            if tbl:
                hdr = tuple(tbl[0])
                hit = next((n for sig, n in DROP_TABLES
                            if all(x in hdr for x in sig)), None)
                if hit:
                    p = add_para(doc, f"[Table {hit} near here — separate file]",
                                 align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
                else:  # unnumbered inline table (algorithm thresholds)
                    add_md_table(doc, tbl)
            continue

        # headings
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            lvl, txt = len(m.group(1)), m.group(2)
            in_title = False
            if txt.strip() == "Title":
                in_title = True
                i += 1; continue
            if re.match(r"^References", txt):
                add_figure_legends(doc)   # legends go before References
                doc.add_heading("References", level=1)
                i += 1; continue
            if txt.startswith("Figures:"):
                # replace with a proper Figure legends section
                doc.add_heading("Figure legends", level=1)
                i += 1; continue
            if lvl == 1:
                doc.add_heading(txt, level=1)
            else:
                doc.add_heading(txt.lstrip("0123456789. "), level=lvl)
            i += 1; continue

        # title page block
        if in_title:
            if s.startswith("**Authors:**"):
                add_para(doc, s.replace("**Authors:**", "").strip())
            elif s.startswith("*Correspondence"):
                add_para(doc, s.strip("*"))
            elif s.startswith("Running title"):
                add_para(doc, s)
            elif s.startswith("Oral and hypersensitivity"):
                add_para(doc, s.strip("*"), align=WD_ALIGN_PARAGRAPH.CENTER,
                         bold=True, size=14)
            elif re.match(r"^[¹²]|^(Department|\()", s) or "(affiliation" in s:
                add_para(doc, s, size=10)
            else:
                add_para(doc, s)
            i += 1; continue

        # references entries
        if re.match(r"^\d+\.\s", s):
            p = add_para(doc, s, spacing=1.5)
            p.paragraph_format.left_indent = Cm(0.75)
            p.paragraph_format.first_line_indent = Cm(-0.75)
            i += 1; continue

        add_para(doc, s)
        i += 1

    out = OUT / "main_manuscript.docx"
    doc.save(out)
    print("saved", out)

def add_figure_legends(doc):
    doc.add_heading("Figure legends", level=1)
    legends = [
        ("Figure 1.", "Forest plot of positive disproportionality signals within the oral/hypersensitivity focus cluster (FAERS/AEMS 2020Q2–2026Q2, primary-suspect role). Points represent ROR; horizontal bars represent 95% CIs; the vertical line marks ROR = 1."),
        ("Figure 2.", "Quarterly reporting proportions of the six hypersensitivity-spectrum families, 2020Q2–2026Q2. The dashed vertical line marks the August 2025 label revision (2025Q3 cut-off)."),
        ("Figure 3.", "Receiver operating characteristic (left) and precision–recall (right) curves of the four machine-learning models under repeated stratified 5-fold × 3 cross-validation. Random forest performed best (AUC 0.622 ± 0.017)."),
        ("Figure 4.", "SHAP summary plot of the best-performing model (random forest). Female sex dominates global feature importance; positivity was 12.9% in the top SHAP quartile vs 6.2% in the bottom quartile."),
        ("Figure 5.", "Bridged network-toxicology overview: drug anchors (CALCRL/RAMP1/CALCA), bridge genes (GNG2/GNB1/GNAS; C3/C5; PLCG1/SRC/MAPK1), event modules (FcεRI signalling, complement and coagulation cascades, inflammatory mediator regulation of TRP channels), and KEGG enrichment of the bridged network."),
    ]
    for tag, txt in legends:
        p = doc.add_paragraph()
        r = p.add_run(tag + " "); r.bold = True
        add_runs(p, txt)
        p.paragraph_format.line_spacing = 2.0

def copy_figures():
    figs = {
        1: ROOT / "results_full/forest_focus.png",
        2: ROOT / "results_label_change/label_change_trend.png",
        3: ROOT / "figures/roc_pr_curves.png",
        4: ROOT / "figures/shap_summary.png",
        5: ROOT / "results/network_tox/figures/network_tox_summary.png",
    }
    for n, src in figs.items():
        dst = FIG / f"Figure_{n}.png"
        shutil.copy2(src, dst)
        print("copied", dst.name, "<-", src.name)

if __name__ == "__main__":
    copy_figures()
    build_table_files()
    build_main_manuscript()
    print("DONE")
