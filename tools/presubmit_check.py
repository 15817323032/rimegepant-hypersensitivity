# -*- coding: utf-8 -*-
"""Pre-submission final check for submission_drugsafety package.
Covers: cleanliness (Chinese/placeholders), identity info (emails/ORCIDs/dagger),
cross-consistency (figure/table refs vs files, DOIs, titles), zip parity."""
import re, sys, zipfile, os, hashlib
from pathlib import Path
from docx import Document

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "submission_drugsafety"
FAILS, WARNS, OKS = [], [], []

def scan_docx(path):
    """Return (paragraph_text, table_text) of a docx."""
    d = Document(str(path))
    paras = [p.text for p in d.paragraphs]
    tabs = []
    for t in d.tables:
        for row in t.rows:
            tabs.append("\t".join(c.text for c in row.cells))
    return paras, tabs

def all_text(path):
    paras, tabs = scan_docx(path)
    return "\n".join(paras) + "\n" + "\n".join(tabs)

zh = re.compile(r"[一-鿿]")
PLACEHOLDERS = ["待补", "待定", "TODO", "FIXME", "XXX", "0000-0000-0000-0000",
                "to be filled", "[insert", "[Insert", "placeholder"]
DEPRECATED = ["786675880@qq.com", "sugh@szu.edu.cn", "389171138@qq.com"]

print("=" * 78)
print("1) CLEANLINESS SCAN (all docx in package)")
print("=" * 78)
docx_files = sorted(PKG.rglob("*.docx"))
for f in docx_files:
    txt = all_text(f)
    zh_hits = zh.findall(txt)
    ph_hits = [p for p in PLACEHOLDERS if p in txt]
    dep_hits = [d for d in DEPRECATED if d in txt]
    if zh_hits or ph_hits or dep_hits:
        FAILS.append(f"{f.name}: zh={len(zh_hits)} placeholders={ph_hits} deprecated={dep_hits}")
        print(f"[FAIL] {f.name}: zh={len(zh_hits)} placeholders={ph_hits} deprecated={dep_hits}")
    else:
        print(f"[ok  ] {f.name}: clean")

print()
print("=" * 78)
print("2) IDENTITY INFO (main manuscript title page + cover letter)")
print("=" * 78)
mm = all_text(PKG / "main_manuscript.docx")
cl = all_text(PKG / "cover_letter.docx")
checks = [
    ("Luo corresponding email lyf92@szu.edu.cn", "lyf92@szu.edu.cn", mm),
    ("Chen co-corresponding email 2536020202@stu.ahmu.edu.cn", "2536020202@stu.ahmu.edu.cn", mm),
    ("Luo ORCID 0000-0001-5370-6777", "0000-0001-5370-6777", mm),
    ("Chen ORCID 0000-0002-2285-3704", "0000-0002-2285-3704", mm),
    ("co-first dagger mark (†)", "†", mm),
    ("Corresponding-author block in cover letter", "lyf92@szu.edu.cn", cl),
    ("Chen listed among authors in cover letter", "LiQing Chen", cl),
]
for name, needle, hay in checks:
    (OKS if needle in hay else FAILS).append(name)
    print(f"[{'ok  ' if needle in hay else 'FAIL'}] {name}")

print()
print("=" * 78)
print("3) CROSS-CONSISTENCY (manuscript refs vs package files)")
print("=" * 78)
mm_paras, _ = scan_docx(PKG / "main_manuscript.docx")
mm_text = "\n".join(mm_paras)
refs = re.findall(r"Table S?\d+", mm_text)
figs = re.findall(r"Figure S?\d+", mm_text)
need_tab = {f"Table {i}" for i in range(1, 11)} | {"Table S1", "Table S2", "Table S3", "Table S4"}
need_fig = {"Figure 1", "Figure 2", "Figure 3", "Figure 4", "Figure S1"}
have_tab = set(refs); have_fig = set(figs)
missing_tab = need_tab - have_tab
missing_fig = need_fig - have_fig
stale = [r for r in refs if r in ("Table 11", "Table 12", "Table 13")]
if missing_tab: FAILS.append(f"tables never cited: {missing_tab}")
if missing_fig: FAILS.append(f"figures never cited: {missing_fig}")
if stale: FAILS.append(f"stale table refs: {stale}")
print(f"[{'ok  ' if not missing_tab else 'FAIL'}] Tables 1-10 + S1-S4 all cited (missing: {sorted(missing_tab) or 'none'})")
print(f"[{'ok  ' if not missing_fig else 'FAIL'}] Figures 1-4 + S1 all cited (missing: {sorted(missing_fig) or 'none'})")
print(f"[{'ok  ' if not stale else 'FAIL'}] No stale Table 11/12/13 refs")

files_present = {p.name for p in PKG.rglob("*") if p.is_file()}
for i in range(1, 11):
    n = f"Table_{i:02d}.docx"
    (OKS if n in files_present else FAILS).append(n)
    if n not in files_present: print(f"[FAIL] missing file {n}")
for i in range(1, 5):
    n = f"Figure_{i}.png"
    (OKS if n in files_present else FAILS).append(n)
    if n not in files_present: print(f"[FAIL] missing file {n}")
if not (FAILS and any("missing file" in x for x in FAILS)): print("[ok  ] all 10 numbered tables + 4 figures present as files")

doi = "10.5281/zenodo.24134724"
(OKS if doi in mm_text else FAILS).append("Zenodo concept DOI in data availability")
print(f"[{'ok  ' if doi in mm_text else 'FAIL'}] Data availability cites concept DOI {doi}")

# titles must match between manuscript and cover letter
def extract_title_mm():
    for p in mm_paras:
        t = p.strip()
        if t.startswith("Title:"):
            return t[len("Title:"):].strip()
    return None
def extract_title_cl():
    m = re.search(r'entitled\s+"(.+?)"', cl)
    return m.group(1).strip() if m else None
t_mm, t_cl = extract_title_mm(), extract_title_cl()
if t_mm and t_cl and t_mm == t_cl:
    print("[ok  ] Title identical in manuscript and cover letter")
    print(f"       \"{t_mm[:90]}...\"")
elif t_mm and t_cl:
    WARNS.append("titles differ between manuscript and cover letter")
    print(f"[WARN] Title differs:\n  MM: {t_mm[:90]}\n  CL: {t_cl[:90]}")
else:
    WARNS.append("title auto-extraction failed")
    print(f"[WARN] title extraction: MM={bool(t_mm)} CL={bool(t_cl)}")

# journal name in cover letter
if "Drug Safety" in cl:
    print("[ok  ] Cover letter addresses Drug Safety")
else:
    FAILS.append("cover letter missing journal name")
    print("[FAIL] Cover letter missing 'Drug Safety'")

print()
print("=" * 78)
print("4) PACKAGE PARITY (zip vs folder)")
print("=" * 78)
_zips = sorted(ROOT.parent.glob("submission_drugsafety_*.zip"),
               key=lambda p: p.stat().st_mtime)
if not _zips:
    sys.exit("no submission_drugsafety_*.zip found next to the project folder")
zp = _zips[-1]
print(f"archive under check: {zp.name}")
with zipfile.ZipFile(zp) as z:
    znames = set(z.namelist())
    bad = z.getinfo("submission_drugsafety/main_manuscript_updated.docx") if "submission_drugsafety/main_manuscript_updated.docx" in znames else None
    fnames = {"submission_drugsafety/" + str(p.relative_to(PKG)).replace("\\", "/")
              for p in PKG.rglob("*") if p.is_file() and not p.name.startswith(".")}
    only_zip = znames - fnames
    only_dir = fnames - znames
    if bad: FAILS.append("_updated intermediate in zip")
    if only_zip: WARNS.append(f"in zip only: {sorted(only_zip)}")
    if only_dir: WARNS.append(f"in dir only: {sorted(only_dir)}")
    print(f"zip entries: {len(znames)} | folder files: {len(fnames)}")
    print(f"[{'ok  ' if not only_zip else 'WARN'}] zip-only extras: {sorted(only_zip) or 'none'}")
    print(f"[{'ok  ' if not only_dir else 'WARN'}] folder-only (not zipped): {sorted(only_dir) or 'none'}")

    # byte-level: the manuscript inside the archive must be the folder copy.
    # Filename parity alone cannot see a stale archive (rebuilt after packing).
    with zipfile.ZipFile(zp) as z2:
        _zm = z2.read("submission_drugsafety/main_manuscript.docx")
    _dm = (PKG / "main_manuscript.docx").read_bytes()
    if _zm != _dm:
        FAILS.append("main_manuscript.docx inside the archive is stale "
                     "(archive packed before the last rebuild) -- repack")
        print("[FAIL] zip manuscript == folder manuscript: NO (stale archive)")
    else:
        OKS.append("archive manuscript identical to folder")
        print("[ok  ] zip manuscript == folder manuscript")

# All figures in package == latest figures_r renders (single source of truth)
def md5(p): return hashlib.md5(Path(p).read_bytes()).hexdigest()[:10]
for _n in (1, 2, 3, 4):
    _a, _b = md5(PKG / "figures" / f"Figure_{_n}.png"), md5(ROOT / "figures_r" / f"Figure_{_n}.png")
    print(f"[{'ok  ' if _a == _b else 'WARN'}] Figure_{_n}.png == figures_r render ({_a})")
    if _a != _b:
        WARNS.append(f"Figure_{_n} in package differs from figures_r render")
if (ROOT / "figures_r" / "Supplementary_Figure_S1.png").exists():
    _s1 = PKG / "Supplementary_Figure_S1.png"      # S1 位于包根目录
    if not _s1.exists():
        _s1 = PKG / "supplementary" / "Supplementary_Figure_S1.png"
    _a, _b = md5(_s1), md5(ROOT / "figures_r" / "Supplementary_Figure_S1.png")
    print(f"[{'ok  ' if _a == _b else 'WARN'}] Supplementary_Figure_S1.png == figures_r render ({_a})")
    if _a != _b:
        WARNS.append("Supplementary_Figure_S1 in package differs from figures_r render")

print()
print("=" * 78)
print(f"RESULT: OK {len(OKS)} | WARN {len(WARNS)} | FAIL {len(FAILS)}")
for w in WARNS: print("  WARN:", w)
for f in FAILS: print("  FAIL:", f)
sys.exit(1 if FAILS else 0)
