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
SUP = OUT / "supplementary"
for d in (TBL, FIG, SUP):
    d.mkdir(parents=True, exist_ok=True)

FONT = "Times New Roman"

# ---------------------------------------------------------------- style helpers
_QN = __import__("docx").oxml.ns.qn

# 数值样式单元（居中列判定用）：纯数字、百分数、±均值、科学计数、带比较符/缺失符
_NUM_RE = re.compile(r"[<>≤≥±~]?\s*[-−+]?\d[\d,.]*(\s*[eE][-+]?\d+|\s*×\s*10)?\s*%?"
                     r"(\s*±\s*\d[\d,.]*\s*(%?)\s*(\s*[eE][-+]?\d+)?)?")
_NEUTRAL_RE = re.compile(r"^(—|–|-|NA|N/A|n/a|Ref\.?|reference|)$", re.I)


def _set_tbl_borders(t, header_rows=1):
    """三线表：顶线 1.5pt、表头底线 1pt、底线 1.5pt，无竖线、无内部横线。"""
    tblPr = t._tbl.tblPr
    borders = tblPr.find(_QN("w:tblBorders"))
    if borders is None:
        borders = tblPr.makeelement(_QN("w:tblBorders"), {})
        tblPr.append(borders)
    spec = {"w:top": ("single", 12), "w:bottom": ("single", 12),
            "w:left": ("none", 0), "w:right": ("none", 0),
            "w:insideH": ("none", 0), "w:insideV": ("none", 0)}
    for tag, (val, sz) in spec.items():
        el = borders.find(_QN(tag))
        if el is None:
            el = borders.makeelement(_QN(tag), {})
            borders.append(el)
        el.set(_QN("w:val"), val)
        el.set(_QN("w:sz"), str(sz))
        el.set(_QN("w:color"), "000000")
    # 表头底线：只写在表头行单元格的 tcBorders 上（单元格边框覆盖表级 insideH）；
    # 正文格不逐格处理——437 行 x 24 列的大表逐格写 XML 会拖垮构建
    for ri in range(min(header_rows, len(t.rows))):
        for c in t.rows[ri].cells:
            tcPr = c._tc.get_or_add_tcPr()
            tcb = tcPr.find(_QN("w:tcBorders"))
            if tcb is None:
                tcb = tcPr.makeelement(_QN("w:tcBorders"), {})
                tcPr.append(tcb)
            bt = tcb.find(_QN("w:bottom"))
            if bt is None:
                bt = tcb.makeelement(_QN("w:bottom"), {})
                tcb.append(bt)
            bt.set(_QN("w:val"), "single")
            bt.set(_QN("w:sz"), "8")
            bt.set(_QN("w:color"), "000000")


def _set_cell_margins(t, top=40, bottom=40, left=100, right=100):
    """单元格内边距（dxa = 1/1440 英寸），默认上下 0.07cm、左右 0.18cm。"""
    tblPr = t._tbl.tblPr
    mar = tblPr.find(_QN("w:tblCellMar"))
    if mar is None:
        mar = tblPr.makeelement(_QN("w:tblCellMar"), {})
        tblPr.append(mar)
    for tag, v in (("w:top", top), ("w:left", left), ("w:bottom", bottom),
                   ("w:right", right)):
        el = mar.find(_QN(tag))
        if el is None:
            el = mar.makeelement(_QN(tag), {})
            mar.append(el)
        el.set(_QN("w:w"), str(v))
        el.set(_QN("w:type"), "dxa")


def _column_aligns(rows):
    """按列内容判定对齐：数值列居中、文本列左对齐（首列一律左对齐）。"""
    body = rows[1:]
    aligns = ["left"]  # 首列（标签列）永远左对齐
    for j in range(1, len(rows[0])):
        col = [r[j].strip() for r in body if len(r) > j]
        col = [c for c in col if c]
        if not col:
            aligns.append("left"); continue
        neutral = sum(1 for c in col if _NEUTRAL_RE.match(c))
        numeric = sum(1 for c in col if _NUM_RE.fullmatch(c))
        judged = [c for c in col if not _NEUTRAL_RE.match(c)]
        if judged and numeric / len(judged) >= 0.7:
            aligns.append("center")
        elif neutral and not judged:
            aligns.append("center")
        else:
            aligns.append("left")
    return aligns


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
    aligns = _column_aligns(rows)
    _set_tbl_borders(t)
    _set_cell_margins(t)
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            c = t.cell(i, j)
            c.text = ""
            p = c.paragraphs[0]
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            if aligns[j] == "center":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_runs(p, str(cell))
            for r in p.runs:
                r.font.size = Pt(font_size)
                r.font.name = "Arial"
                r._element.rPr.rFonts.set(_QN("w:eastAsia"), "Arial")
                if i == 0:
                    r.bold = True
    # 表头跨页重复（Table 2 有 437 行，翻页不能丢表头）
    trPr = t.rows[0]._tr.get_or_add_trPr()
    trPr.append(trPr.makeelement(_QN("w:tblHeader"), {}))
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
        rows.append(["" if v is None else
                     (_fmt_float(v) if isinstance(v, float) else str(v))
                     for v in r])
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
    # 字符串形式的数值同样格式化；无法安全转 float 的标识符（3N7S、hsa04664、
    # "0.621 ± 0.015"、基因列表等）原样保留。
    out = []
    for r in rows:
        row = []
        for c in r:
            try:
                row.append(_fmt_float(float(c)))
            except (ValueError, TypeError):
                row.append(c)
        out.append(row)
    return out

TITLES = {
    1: ("Baseline characteristics of rimegepant primary-suspect reports compared with full-database and indication-matched reference populations",
        "Cohort = rimegepant primary-suspect cases (n = 8,962). Full database = all other deduplicated reports in the same 25 quarterly extracts (n = 9,085,192), i.e. the denominator of the disproportionality analysis. Indication-matched = deduplicated reports whose INDI (indication) records contained a migraine term, excluding rimegepant primary-suspect cases (n = 75,155); this comparator absorbs confounding by indication, asking whether a contrast survives when the cohort is compared with other migraine-treatment reports rather than with the database at large. Percentages for composition rows (missing, reporter, country) take all reports in the column as denominator; for age bands and sex the denominator is reports with that variable recorded, so that differential completeness does not leak into the SMD. SMD, standardised mean difference (cohort minus the comparator in the same row) calculated on row proportions; |SMD| > 0.10 indicates a meaningful imbalance. Only a selection of countries/regions is shown individually (the United States and the most frequently reported countries of the full database, plus the regional code EU and Chile); reports from all other countries are not listed separately, so country rows do not sum to the full column total. p values are deliberately not reported: against more than nine million reference reports, any difference regardless of size reaches significance. \u2014 = not applicable.", False),
    2: ("Core disproportionality signals in the oral/hypersensitivity focus cluster",
        "Sorted by ROR. a = number of deduplicated rimegepant primary-suspect reports with the PT; ROR (95% CI) computed on the 2 x 2 table against the full database; algorithms = number of the four disproportionality algorithms (ROR, PRR, BCPNN/IC025, MGPS/EB05) reaching their positivity threshold. Signals with at least two algorithms positive are classed as robust; the ten robust core signals highlighted in the text (\u00a73.2) were selected for clinical relevance across the five pre-specified subsets after inspection and were not pre-registered. The complete ranked list of all tested PTs is given in Supplementary Table S2.",
        False),
    3: ("Time-to-onset distribution of composite-endpoint events",
        "TTO = event date \u2212 start date of the first-listed drug (rimegepant in all cases analysed), in days. Of the 8,962 primary-suspect cases, 1,060 (11.8%) had both dates recorded; 208 negative intervals, in which the event was dated before drug start, and 4 intervals longer than 730 days were excluded, leaving 848 (9.5%) in the analysis. Dates are recorded at day-level resolution, so an interval of 0 days denotes same-calendar-day occurrence and cannot resolve onset within 24 hours; the subset with usable dates may be selectively incomplete.", False),
    4: ("Focus-cluster signals by subgroup (sex, age group, report year)",
        "Within-drug reporting proportions with Wilson 95% CIs. Reporter codes: PER = consumer, EXP = physician, DIR = manufacturer/other health-care professional. Report-year rows cover 2020\u20132025 in full; 2026 covers the first two quarters only (the analysis window ends 2026Q2).", False),
    5: ("Sensitivity analyses: indication-PT exclusion and triple exposure roles",
        "Indication-bias control: migraine-symptom PTs (nausea, vomiting, headache, migraine, photophobia, phonophobia) excluded in recalculation. Exposure roles: PS (primary), PS+SS, ALL.", False),
    6: ("Machine-learning model comparison (repeated stratified 5-fold × 3 cross-validation)",
        "Label = composite-endpoint positivity (932/8,962, 10.4%); 23 features (demographics, report year and country, concomitant drug classes, time to onset and its missing indicators); serious outcomes and event counts excluded (leakage control). Sensitivity models: including reporter category and formulation reached a random-forest AUC of 0.618 ± 0.017 (no model changing by more than 0.01 AUC); excluding the two time-to-onset features, which are available only after the event, gave a random-forest AUC of 0.602 ± 0.014 with female sex still the leading feature (\u00a73.3). AUC, area under the ROC curve (mean ± SD); AP, average precision; Brier, Brier score computed after restoring the predicted probabilities to the observed 10.4% prevalence, because class weighting for an imbalanced label inflates them (uncorrected values are kept in the archived results file). Null model = a constant prediction at the observed prevalence, which has AUC 0.500 and AP equal to the prevalence by construction.", False),
    7: ("Bridge genes from the bridged network-toxicology analysis",
        "BFS \u2264 4 hops from drug anchors (CALCRL/RAMP1/CALCA) on the anchor \u222a event-module STRING network (score \u2265 700). bridge_count = number of shortest anchor-to-event paths (BFS depth \u2264 4) that traverse the gene, used to rank genes; min_hops = length in hops of the shortest anchor-to-event path through the gene; connects = the three most frequently traversed neighbour nodes immediately downstream of the gene on shortest paths (repeated entries indicate multiple distinct shortest paths through the same neighbour); in_ae_set = 1 if the gene itself belongs to an event gene set (KEGG hsa04664/hsa04610/hsa04750/hsa04062) and 0 if it is an intermediate bridging node. Genes are not deduplicated across paths, so traversal counts can exceed the number of paths.", False),
    8: ("Molecular docking results (AutoDock Vina 1.2.5, exhaustiveness 16, seed 42)",
         "Pre-registered criteria: CALCRL \u0394G \u2264 \u22128 kcal/mol validates the docking system; off-target \u0394 = \u0394G(target) \u2212 \u0394G(CALCRL) \u2265 2 kcal/mol = no evidence of off-target binding to the tested construct; \u0394 < 2 = grey zone. Receptor constructs: SYK PDB 1A81 (tandem SH2 domains) and BTK PDB 1B55 (PH domain); neither contains a kinase catalytic domain, so the results concern binding to the tested domains only and do not assess kinase inhibition.", False),
    9: ("Reporting proportions of hypersensitivity families before vs after the August 2025 label revision",
         "Primary comparison: pre = 2020Q2\u20132025Q2 (n = 8,283), post = 2025Q4\u20132026Q2 (n = 418); the transition quarter 2025Q3, which contains both pre- and post-revision reports (the revision took effect in August 2025), is excluded. Within-drug proportions among rimegepant primary-suspect reports; Wilson 95% CIs and Fisher exact test. q = Benjamini\u2013Hochberg-adjusted p across the six family comparisons reported in this table (the six families were treated as equally ranked comparisons); the oral mucosal increase is therefore nominally significant only (raw p = 0.009, q = 0.056). Sensitivity analysis retaining 2025Q3 in the post period (post n = 679): ratios 1.00\u20132.03, all p > 0.05.", False),
    10: ("Leading bridge-gene modules and their mechanistic assignment",
         "Module membership is curated from the highest-ranked bridge genes of each event module; bridge counts are the STRING-network traversal counts of the individual genes (Table 7) and min hops is the shortest anchor-to-event path. Mechanistic statements are plausible-link assignments, not confirmed mechanisms (cf. §2.8). The chemokine module has no single dominant bridge gene and is represented through KEGG pathway enrichment (Fig 4; Supplementary Table S4).", False),
}

SOURCES = {
    1: ("csv", ROOT / "results_full/table1_with_reference.csv", None, None),
    2: ("xlsx", ROOT / "results_full/table3_focus_slim.xlsx", "table3_focus_slim", None),
    3: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table4_tto", None),
    4: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table5_subgroup", None),
    5: ("xlsx", ROOT / "results_full/all_tables.xlsx", "table6_sensitivity", None),
    6: ("xlsx", ROOT / "results_full/all_tables_full.xlsx", "T7_ML_models", None),
    7: ("csv", ROOT / "results/network_tox/bridge_genes.csv", None, None),
    8: ("xlsx", ROOT / "results_full/all_tables_supplement.xlsx", "T11_docking", None),
    9: ("xlsx", ROOT / "results_full/all_tables_full.xlsx", "T12_label_prepost", None),
    10: ("csv", ROOT / "results_full/table13_bridge_assignment.csv", None, None),
}

ROW_LIMIT_DOCX = 100  # larger tables go out as .xlsx (journal accepts xlsx supplements)

ZH_MAP = {
    "bridge_gene_module": "Bridge-gene module", "bridge_counts": "Bridge counts",
    "min_hops": "Min hops", "mechanistic_assignment": "Mechanistic assignment",
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
    "两日期均完整": "Both dates recorded", "可分析 TTO 的病例数": "Cases in TTO analysis",
    "<=1d": "≤ 1 day", "2-7d": "2–7 days", "8-30d": "8–30 days",
    "31-90d": "31–90 days", ">90d": "> 90 days",
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

def _fmt_float(v: float) -> str:
    """Journal-facing float formatting: >=100 -> 1 dp, else 3 dp fixed;
    |v| < 1e-3 keeps scientific notation; integral values lose the .0."""
    if v != v or v in (float("inf"), float("-inf")):
        return str(v)
    a = abs(v)
    if a == int(a) and a < 1e12:
        return str(int(v))
    if a != 0 and a < 1e-3:
        return f"{v:.2e}"
    s = f"{v:.1f}" if a >= 100 else f"{v:.3f}"
    return s

def translate_rows(rows):
    out = []
    for r in rows:
        row = [c for c in r]
        for i, c in enumerate(row):
            if isinstance(c, float):
                row[i] = _fmt_float(c)
        out.append([ZH_MAP.get(str(c).strip(), ZH_MAP.get(str(c), c)) for c in row])
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

LEGENDS = [
    ("Figure 1.", "Forest plot of the 25 highest-ROR preferred terms within the oral/hypersensitivity focus cluster (49 PTs; FAERS/AEMS 2020Q2\u20132026Q2, primary-suspect role). Points represent ROR; horizontal bars represent 95% CIs (truncated with an arrowhead where they extend beyond the axis); the vertical dashed line marks ROR = 1. Red points are robust positive signals (positive under at least two of the four algorithms); dark blue points did not meet the signal criterion. The right-hand columns give the number of primary-suspect rimegepant cases and the number of reports in the rest of the database. All 19 positive signals of the cluster are shown (18 of them robust)."),
    ("Figure 2.", "Quarterly reporting proportions of the six hypersensitivity-spectrum families, 2020Q2\u20132026Q2, shown as small multiples on a shared 0\u201340% scale with 95% Wilson intervals (shaded ribbons). The shaded band marks 2025Q3, the transition quarter that contains the August 2025 label revision and is excluded from the primary pre/post comparison (Table 9). The bottom panel shows the quarterly report denominators underlying all proportions."),
    ("Figure 3.", "SHAP analysis of the best-performing model (random forest; AUC 0.621 ± 0.015). Left: mean absolute SHAP value per feature (top 15 of the 21 plotted features; the male-sex mirror of female sex and the centred duplicate of report year are omitted; the full 23-feature list is given in Supplementary Table S3). Right: SHAP contributions of individual cases; the horizontal axis is the SHAP value in log-odds of the composite endpoint; colour encodes the feature value (red high, blue low; pale grey marks missing values). No feature dominates, and the largest mean absolute SHAP value is 0.031. Composite-endpoint positivity was 12.9% in the highest and 6.2% in the lowest quartile of the female-sex SHAP contribution."),
    ("Figure 4.", "Bridged network-toxicology overview. Top left: predicted targets (max Tanimoto similarity to the drug's ChEMBL anchors; CALCRL highlighted). Top centre: PPI hub genes by STRING degree. Top right: top-10 GO biological-process enrichment of the bridged network. Bottom: KEGG pathway enrichment of the bridged genes (top 12, Enrichr with Benjamini–Hochberg correction; bubble size = bridged genes in pathway, colour = adjusted p). The x-axis of the bottom panel is broken for readability: chemokine signaling is orders of magnitude more enriched than the remaining pathways, so the leading pathways are displayed on a compressed right-hand segment (the full top-20 list is given in Supplementary Table S4). Drug anchors CALCRL/RAMP1/CALCA and bridge genes GNG2/GNB1/GNAS, C3/C5 and PLCG1/SRC/MAPK1 connect the drug layer to the chemokine and leukocyte-chemotaxis modules."),
]

SUPP_LEGENDS = [
    ("Supplementary Figure S1.", "Receiver operating characteristic (left) and precision\u2013recall (right) curves of the four machine-learning models under repeated stratified 5-fold \u00d7 3 cross-validation, computed from out-of-fold predictions. The dashed diagonal is the no-discrimination line in the ROC panel; the dashed horizontal line is chance precision at the observed prevalence of 10.4% in the precision\u2013recall panel. All four curves lie close to chance, which is the result reported in Table 6."),
    ("Supplementary Figure S2.", "Study flow from the raw quarterly FAERS/AEMS extracts to the analysis sets: 25 quarters (2020Q2\u20132026Q2), FDA-recommended deduplication (N = 9,094,154), rimegepant drug matching, exposure-role selection (PS 8,962; PS+SS 9,691; all roles 13,190), and the two downstream subsets used by the machine-learning module (composite-endpoint label, 932 cases, 10.4%) and the time-to-onset analysis (1,060 with both dates recorded, 848 retained after excluding 208 negative and 4 over-long intervals)."),
]

def add_figure_legends(doc):
    doc.add_heading("Figure legends", level=1)
    for tag, txt in LEGENDS:
        p = doc.add_paragraph()
        r = p.add_run(tag + " "); r.bold = True
        add_runs(p, txt)
        p.paragraph_format.line_spacing = 2.0

def copy_figures():
    figs = {
        1: ROOT / "results_full/forest_focus.png",
        2: ROOT / "results_label_change/label_change_trend.png",
        3: ROOT / "figures/shap_summary.png",
        4: ROOT / "results/network_tox/figures/network_tox_summary.png",
    }
    for n, src in figs.items():
        dst = FIG / f"Figure_{n}.png"
        shutil.copy2(src, dst)
        print("copied", dst.name, "<-", src.name)

    # ROC/PR 曲线改为补充材料图 S1（正文只留 SHAP）
    SUP.mkdir(parents=True, exist_ok=True)
    s1 = ROOT / "figures/roc_pr_curves.png"
    if s1.exists():
        shutil.copy2(s1, SUP / "Supplementary_Figure_S1.png")
        print("copied Supplementary_Figure_S1.png <-", s1.name)

    # 清理旧编号残留（原 Figure_5 已顺移为 Figure_4）
    stale = FIG / "Figure_5.png"
    if stale.exists():
        stale.unlink()
        print("removed stale Figure_5.png")

SUPP_TITLES = {
    "S2": ("Supplementary Table S2. All tested preferred terms for rimegepant with at least three reports (a \u2265 3; 437 PTs)",
           "The table lists every tested PT, whether or not it reached a positivity threshold: 102 of the 437 PTs were positive under at least one algorithm and 94 under at least two (robust). "
           "ROR, reporting odds ratio; PRR, proportional reporting ratio; IC025, lower bound of the Bayesian confidence "
           "propagation neural network information component; EB05, lower bound of the empirical Bayes geometric mean. "
           "Positive: ROR025 > 1, PRR \u2265 2 & \u03c7\u00b2 \u2265 4, IC025 > 0, EB05 > 2. 'Robust' = positive in \u2265 2 algorithms; signals positive under all four are described in the text as showing four-algorithm concordance. "
           "Benjamini\u2013Hochberg q values are reported as a descriptive multiple-testing adjustment and do not enter the positivity or robustness criteria. "
           "Focus = within the pre-specified oral/hypersensitivity composite endpoint.",
           ("xlsx", ROOT / "results_full/all_tables.xlsx", "table2_all_signals", None)),
    "S3": ("Supplementary Table S3. SHAP global feature importance of the best model (random forest)",
           "Mean absolute SHAP values over cross-validation folds; all 23 features of the primary model are shown. "
           "The top 15 are rendered as the left panel of Fig 3. Reporter category, formulation and country completeness "
           "were not entered in the primary model because they describe how a report reached the database rather than "
           "the patient; they were evaluated in the sensitivity model (Table 6 footnote).",
           ("xlsx", ROOT / "results_full/all_tables_full.xlsx", "T8_SHAP_top15", None)),
    "S4": ("Supplementary Table S4. KEGG pathway enrichment of the bridged network (Enrichr, BH-corrected)",
           "Top 20 terms by adjusted p (q) value. The top 12 are rendered as the lower panel of Fig 4.",
           ("csv", ROOT / "results/network_tox/enrichment_kegg.csv", None, 21)),
}
SUPP_SUFFIX = {"S2": "all_signals", "S3": "shap_importance", "S4": "kegg_enrichment"}

def build_supplementary_tables():
    SUP.mkdir(parents=True, exist_ok=True)
    for tag, (title, footnote, spec) in SUPP_TITLES.items():
        kind, path, sheet, cap = spec
        rows = (xlsx_rows(path, sheet, cap) if kind == "xlsx" else csv_rows(path, cap))
        rows = translate_rows(rows)
        doc = Document()
        set_normal_style(doc, spacing=1.0); style_heading(doc)
        add_para(doc, f"Supplementary Table {tag[1:]}.", bold=True, spacing=1.0)
        add_para(doc, title.split(". ", 1)[1], bold=True, spacing=1.0)
        doc.add_paragraph()
        ncols = max(len(r) for r in rows) if rows else 0
        add_md_table(doc, rows, landscape=(ncols > 8), font_size=8)
        doc.add_paragraph()
        add_para(doc, footnote, spacing=1.0)
        out = SUP / f"Supplementary_Table_{tag}_{SUPP_SUFFIX.get(tag, 'misc')}.docx"
        doc.save(out)
        print("saved", out.name, f"({len(rows)-1} rows x {ncols} cols)")

if __name__ == "__main__":
    copy_figures()
    build_table_files()
    build_supplementary_tables()
    build_main_manuscript()
    print("DONE")
