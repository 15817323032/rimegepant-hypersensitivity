# -*- coding: utf-8 -*-
"""Build the Drug Safety (Springer/Adis) submission package.

Produces
  docs/manuscript_drugsafety.md          single source of truth for this journal
  submission_drugsafety/main_manuscript.docx
  submission_drugsafety/Table_*.docx|xlsx  (copied from submission/tables)
  submission_drugsafety/Figure_*.png       (copied from submission/figures)
  submission_drugsafety/Supplementary_Table_S1_READUS-PV.docx

Formatting applied per the journal's instructions:
  Times New Roman 12 pt, double-spaced, page numbers, continuous line numbers,
  decimal-numbered headings, structured abstract, Key Points, numbered
  Declarations, running head <= 100 characters.
"""
import importlib.util
import os
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Inches

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "submission_drugsafety"
SRC = DOCS / "manuscript_en.md"

# reuse the md->docx helpers already used for the Headache package
spec = importlib.util.spec_from_file_location("mk", ROOT / "tools/make_submission.py")
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)

TITLE = ("Oral and hypersensitivity-spectrum adverse events of rimegepant orally "
         "disintegrating tablets: a disproportionality analysis of the FDA Adverse Event "
         "Reporting System (FAERS), 2020\u20132026, with machine-learning, "
         "network-toxicology and docking follow-up")
RUNNING_HEAD = "Rimegepant oral/hypersensitivity signals in FAERS: a disproportionality analysis"

KEY_POINTS = [
    ("In the US adverse event database, rimegepant orally disintegrating tablets generated a "
     "reproducible and internally consistent cluster of oral, pharyngeal and systemic "
     "hypersensitivity reports\u2014swollen tongue, throat swelling and oral paraesthesia among "
     "them\u2014that is corroborated by four independent published analyses and is not explained "
     "by the 2025 label change."),
    ("The rapid onset (median same day) and the pathway-level analysis point to local activation "
     "of mast cells and complement in the mouth and throat, rather than to off-target effects on "
     "the CGRP receptor; docking excluded a direct SYK-level interaction."),
    ("Characteristics recorded in spontaneous reports cannot identify which patients are at risk, "
     "so prospective treatment registries are needed, and the Chinese label does not yet carry "
     "these oropharyngeal warnings."),
]

DECLARATIONS = [
    ("I. Funding",
     "This work was supported by the 2025 HaiYa Young Scientist Foundation of Shenzhen "
     "University General Hospital (Grant No. 2025-HY007)."),
    ("II. Conflicts of interest",
     "The authors have no relevant financial or non-financial interests to disclose."),
    ("III. Availability of data and material",
     "The FAERS/AEMS quarterly ASCII extracts analysed here are publicly available from the US "
     "Food and Drug Administration (https://fis.fda.gov/content/Exports/faers_ascii_YYYYQn.zip) "
     "and are not redistributed by the authors. All derived counts, tables and figures generated "
     "during this study are included in the electronic supplementary material."),
    ("IV. Ethics approval",
     "FAERS/AEMS is a public, de-identified spontaneous-report database containing no identifiable "
     "personal information. Under 45 CFR 46.102 this study is non-human-subjects research and is "
     "exempt from institutional review board approval."),
    ("V. Consent to participate",
     "Not applicable."),
    ("VI. Consent for publication",
     "Not applicable."),
    ("VII. Code availability",
     "The complete analysis pipeline, configuration files and pre-specified case definitions are "
     "openly available at https://github.com/15817323032/rimegepant-hypersensitivity and "
     "permanently archived at Zenodo (DOI 10.5281/zenodo.24134724, version 1.0.1) under an MIT "
     "licence."),
    ("VIII. Author contributions",
     "LiQing Chen: conceptualization, methodology, software, formal analysis, data curation, "
     "visualization, writing\u2014original draft, and guarantor of the study. Yunfan Luo: "
     "validation, investigation, writing\u2014review and editing, supervision. Qing Yuan: "
     "investigation, resources, writing\u2014review and editing. Xiaoyan Zhang: data curation, "
     "project administration, writing\u2014review and editing. All authors read and approved the "
     "final manuscript."),
]

EXTRA_REFS = []

READUS_SENTENCE = (
    "Reporting follows the READUS-PV guideline for disproportionality analyses based on individual "
    "case safety reports [14,15], and the completed checklist is provided as Supplementary "
    "Table S1."
)


def split_source():
    """Cut manuscript_en.md into (abstract, body 1-5, availability, references)."""
    s = SRC.read_text(encoding="utf-8")
    i_abs = s.index("# Abstract")
    i_body = s.index("# 1. Introduction")
    i_avail = s.index("# Data and code availability")
    i_refs = s.index("# References")
    i_tail = s.index("# \u00a7Journal fit")
    abstract = s[i_abs:i_body]
    body = s[i_body:i_avail]
    availability = s[i_avail:i_refs]
    refs = s[i_refs:i_tail]
    return abstract, body, availability, refs


def clean(md):
    md = md.replace("# Abstract", "").replace("# Data and code availability", "")
    md = re.sub(r"^# References.*$", "", md, flags=re.M)
    return md.strip()


def build_markdown():
    abstract, body, availability, refs = split_source()

    # drop the keywords line (Drug Safety: keywords not required)
    abstract = re.sub(r"^\*\*Keywords:\*\*.*$", "", abstract, flags=re.M)
    abstract = abstract.strip()

    # READUS-PV statement at the end of Methods 2.1
    anchor = "## 2.2 Data processing and deduplication"
    body = body.replace(anchor, READUS_SENTENCE + "\n\n" + anchor, 1)

    refs_body = re.sub(r"^# References.*$", "", refs, flags=re.M).strip()
    refs_lines = [ln for ln in refs_body.splitlines() if ln.strip()]
    refs_lines += EXTRA_REFS

    table_titles = [f"**Table {n}.** {mk.TITLES[n][0]}" for n in sorted(mk.TITLES)]
    table_notes = [f"*Table {n} footnote.* {mk.TITLES[n][1]}" for n in sorted(mk.TITLES)]

    # 词数口径：与 Word / 投稿系统的空白分词一致；正文不含内嵌表格（期刊按“不含表格”计），
    # 摘要不含 Keywords（已在上面剔除）。
    body_prose = re.sub(r"(?m)^\|.*$", "", body)
    body_words = len(body_prose.split())
    abs_words = len(abstract.split())

    parts = []
    parts.append(f"**Title:** {TITLE}\n")
    parts.append(f"**Running head:** {RUNNING_HEAD}\n")
    parts.append("**Authors:** LiQing Chen, MD\u00b9*; Yunfan Luo, MD\u00b9*; "
                 "Qing Yuan, MD\u00b9; Xiaoyan Zhang, BS\u00b9\n")
    parts.append("\u00b9 Department of Otolaryngology, Head and Neck Surgery, Shenzhen University "
                 "General Hospital, No. 1298 Xueyuan Boulevard, Xili University Town, Shenzhen, "
                 "Guangdong 518055, China")
    parts.append("**Corresponding author:** LiQing Chen, MD (ORCID 0000-0002-2285-3704), "
                 "Department of Otolaryngology, Head and Neck Surgery, Shenzhen University General "
                 "Hospital, No. 1298 Xueyuan Boulevard, Xili University Town, Shenzhen, Guangdong "
                 "518055, China. Tel +86 137 6047 9274; E-mail 2536020202@stu.ahmu.edu.cn\n")
    parts.append("**Co-corresponding author:** Yunfan Luo, MD (ORCID 0000-0001-5370-6777), "
                 "Department of Otolaryngology, Head and Neck Surgery, Shenzhen University General "
                 "Hospital, Shenzhen, China; E-mail 786675880@qq.com\n")
    parts.append("**Article type:** Original Research Article\n")
    n_refs = len([ln for ln in refs_lines if re.match(r"^\d+\.\s", ln)])
    parts.append(f"**Word count:** abstract {abs_words}; main text {body_words}; "
                 f"tables 12; figures 4; references {n_refs}\n")
    parts.append("* Joint first authors\n")

    parts.append("# Key Points\n")
    for kp in KEY_POINTS:
        parts.append(f"- {kp}")
    parts.append("")

    parts.append("# Abstract\n")
    parts.append(clean(abstract))

    parts.append("\n" + body.strip())

    parts.append("\n# Declarations\n")
    for head, text in DECLARATIONS:
        parts.append(f"## {head}")
        parts.append(text + "\n")

    parts.append("# References\n")
    parts.append("\n".join(refs_lines))

    parts.append("\n# Tables\n")
    for n in sorted(mk.TITLES):
        parts.append(f"**Table {n}.** {mk.TITLES[n][0]}")
        parts.append(f"*Table {n} footnote.* {mk.TITLES[n][1]}")
        parts.append("")

    parts.append("# Figure legends\n")
    for tag, txt in mk.LEGENDS:
        parts.append(f"**{tag}** {txt}\n")
    parts.append("# Supplementary figure legend\n")
    for tag, txt in mk.SUPP_LEGENDS:
        parts.append(f"**{tag}** {txt}\n")

    md = "\n".join(parts)
    out = DOCS / "manuscript_drugsafety.md"
    out.write_text(md, encoding="utf-8")
    print("wrote", out, f"({len(md.split())} words)")
    return md


def safe_save(doc, path):
    """写临时文件再替换：Word/预览面板可能锁住目标文件，替换失败则另存改名。"""
    path = Path(path)
    tmp = path.with_name(path.stem + ".tmp.docx")
    doc.save(tmp)
    try:
        os.replace(tmp, path)
    except PermissionError:
        alt = path.with_name(path.stem + "_updated.docx")
        os.replace(tmp, alt)
        print(f"  [warn] {path.name} 被占用（预览中），已另存为 {alt.name}")
        return alt
    return path


def add_line_numbers(doc, only_first=True):
    targets = doc.sections[:1] if only_first else doc.sections
    for sec in targets:
        _ln(sec)


def _ln(sec):
    sectPr = sec._sectPr
    if sectPr.find(qn("w:lnNumType")) is not None:
        return
    ln = OxmlElement("w:lnNumType")
    ln.set(qn("w:countBy"), "1")
    ln.set(qn("w:restart"), "continuous")
    ln.set(qn("w:distance"), "360")
    cols = sectPr.find(qn("w:cols"))
    if cols is not None:
        cols.addprevious(ln)
    else:
        sectPr.append(ln)


def add_page_numbers(doc):
    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._r.addnext(fld)


def md_to_docx(md, out_path):
    doc = Document()
    mk.set_normal_style(doc, spacing=2.0)
    mk.style_heading(doc)
    doc.sections[0].left_margin = Inches(1)
    doc.sections[0].right_margin = Inches(1)
    add_line_numbers(doc)
    add_page_numbers(doc)

    lines = md.splitlines()
    i = 0
    page_break_before = {"References", "Tables", "Figure legends"}
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
            i += 1
            continue
        if line.startswith("# "):
            name = line[2:].strip()
            if name in page_break_before and doc.paragraphs:
                doc.add_page_break()
            doc.add_heading(name, level=1)
            i += 1
            continue
        if line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            mk.add_runs(p, line[2:].strip())
            p.paragraph_format.line_spacing = 2.0
            i += 1
            continue
        m = re.match(r"^\*\*Table (\d+)\.\*\* ", line)
        if m:
            n = int(m.group(1))
            if n > 1:
                doc.add_page_break()
            mk.add_para(doc, line, spacing=1.0)
            kind, path, sheet, cap = mk.SOURCES[n]
            rows = (mk.xlsx_rows(path, sheet, cap) if kind == "xlsx"
                    else mk.csv_rows(path, cap))
            rows = mk.translate_rows(rows)
            if len(rows) > mk.ROW_LIMIT_DOCX:
                mk.add_para(doc, f"(This table has {len(rows)} rows; the complete "
                                 f"table is provided as the electronic supplementary "
                                 f"file Table_{n:02d}.xlsx.)", spacing=1.0, size=9)
            else:
                mk.add_md_table(doc, rows,
                                landscape=(max(len(r) for r in rows) > 8),
                                font_size=8)
            i += 1
            continue
        m = re.match(r"^\*Table (\d+) footnote\.\* ", line)
        if m:
            mk.add_para(doc, re.sub(r"^\*Table (\d+) footnote\.\*\s*",
                                    r"Table \1 footnote. ", line),
                        spacing=1.0, size=8)
            i += 1
            continue
        mk.add_para(doc, line)
        i += 1

    add_line_numbers(doc, only_first=False)
    safe_save(doc, out_path)
    print("saved", out_path)


def copy_assets():
    tdir = OUT / "tables"
    fdir = OUT / "figures"
    tdir.mkdir(parents=True, exist_ok=True)
    fdir.mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "submission/tables").glob("Table_*")):
        shutil.copy2(f, tdir / f.name)
    for f in sorted((ROOT / "submission/figures").glob("Figure_*")):
        shutil.copy2(f, fdir / f.name)
    sup_src = ROOT / "submission/supplementary"
    if sup_src.exists():
        for f in sorted(sup_src.glob("Supplementary_*")):
            shutil.copy2(f, OUT / f.name)
    print("copied tables:", len(list(tdir.iterdir())), "figures:", len(list(fdir.iterdir())))


def build_supplementary_readus():
    md = (DOCS / "readus_pv_checklist.md").read_text(encoding="utf-8")
    doc = Document()
    mk.set_normal_style(doc, spacing=1.0)
    mk.style_heading(doc)
    for line in md.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if s.startswith("## "):
            doc.add_heading(s[3:].strip(), level=2)
        elif s.startswith("# "):
            doc.add_heading(s[2:].strip(), level=1)
        elif s.startswith("|"):
            continue  # tables are rebuilt below
        else:
            mk.add_para(doc, s, spacing=1.0)

    # rebuild the item table from the markdown pipe table
    rows = []
    for line in md.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    if rows:
        doc.add_page_break()
        doc.add_heading("READUS-PV checklist (manuscript body, 14 items)", level=2)
        mk.add_md_table(doc, rows, landscape=True, font_size=8)
    out = OUT / "Supplementary_Table_S1_READUS-PV.docx"
    safe_save(doc, out)
    print("saved", out)


def build_cover_letter():
    src = DOCS / "cover_letter_drugsafety.md"
    if not src.exists():
        return
    doc = Document()
    mk.set_normal_style(doc, spacing=1.15)
    mk.style_heading(doc)
    for line in src.read_text(encoding="utf-8").splitlines():
        t = line.rstrip()
        if not t.strip():
            continue
        if t.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            mk.add_runs(p, t[2:].strip())
            continue
        mk.add_para(doc, t, spacing=1.15)
    out = OUT / "cover_letter.docx"
    safe_save(doc, out)
    print("saved", out)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    md = build_markdown()
    md_to_docx(md, OUT / "main_manuscript.docx")
    copy_assets()
    build_supplementary_readus()
    build_cover_letter()


if __name__ == "__main__":
    main()
