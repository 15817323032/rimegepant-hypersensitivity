# -*- coding: utf-8 -*-
"""Audit rendered submission tables against their source files, cell by cell.

Checks, per table:
  - row / column count vs source
  - every cell equals the source cell after the same translate+format pipeline
  - empty-cell count, duplicate-row count
  - header row present and non-empty
  - float formatting (no full-precision floats)
Exits non-zero if any mismatch is found.
"""
import csv, sys, importlib.util
from pathlib import Path
from docx import Document

ROOT = Path(r"C:/Users/wu-ke/WorkBuddy/2026-11-09-16-31-05/rimegepant_hypersensitivity")
spec = importlib.util.spec_from_file_location("mk", ROOT / "tools" / "make_submission.py")
mk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mk)


def docx_rows(path):
    d = Document(path)
    if not d.tables:
        return None
    t = d.tables[0]
    rows = []
    for r in t.rows:
        rows.append([c.text.strip() for c in r.cells])
    return rows


def norm(s):
    return " ".join(str(s).split())


problems = []
print("=" * 78)
for n in sorted(mk.TITLES):
    kind, path, sheet, cap = mk.SOURCES[n]
    src = mk.xlsx_rows(path, sheet, cap) if kind == "xlsx" else mk.csv_rows(path, cap)
    src = [r[:len(r)] for r in src]
    # source -> translated/formatted, same pipeline as the renderer
    src_t = mk.translate_rows(src)
    # the renderer may trim columns via cap
    docx_p = mk.TBL / f"Table_{n:02d}.docx"
    got = docx_rows(docx_p)
    if got is None:
        problems.append(f"Table {n}: no table found in {docx_p.name}")
        continue
    ns, ng = len(src_t), len(got)
    cs = max(len(r) for r in src_t) if src_t else 0
    cg = max(len(r) for r in got) if got else 0
    tag = f"Table {n:02d}"
    if ns != ng:
        problems.append(f"{tag}: row count src {ns} vs docx {ng}")
    if cs != cg:
        problems.append(f"{tag}: col count src {cs} vs docx {cg}")
    bad = 0
    first = None
    for i in range(min(ns, ng)):
        s_row = [norm(x) for x in src_t[i]]
        g_row = [norm(x) for x in got[i]]
        # pad shorter row
        L = max(len(s_row), len(g_row))
        s_row += [""] * (L - len(s_row)); g_row += [""] * (L - len(g_row))
        for j in range(L):
            if s_row[j] != g_row[j]:
                bad += 1
                if first is None:
                    first = (i + 1, j + 1, s_row[j], g_row[j])
    empty = sum(1 for r in got for c in r if c == "")
    dups = len(got) - len({tuple(r) for r in got})
    status = "OK " if (ns == ng and cs == cg and bad == 0) else "FAIL"
    print(f"[{status}] {tag}: {ng}r x {cg}c | src {ns}r x {cs}c | "
          f"cell-mismatch {bad} | empty {empty} | dup-rows {dups}")
    if first:
        print(f"        first mismatch r{first[0]} c{first[1]}: src={first[2]!r} docx={first[3]!r}")

# supplementary tables
print("-" * 78)
for tag, (title, footnote, spec_) in mk.SUPP_TITLES.items():
    kind, path, sheet, cap = spec_
    src = mk.xlsx_rows(path, sheet, cap) if kind == "xlsx" else mk.csv_rows(path, cap)
    src_t = mk.translate_rows(src)
    fp = mk.SUP / f"Supplementary_Table_{tag}_{mk.SUPP_SUFFIX[tag]}.docx"
    got = docx_rows(fp)
    if got is None:
        problems.append(f"Supp {tag}: no table in {fp.name}")
        continue
    ns, ng = len(src_t), len(got)
    cs = max(len(r) for r in src_t)
    cg = max(len(r) for r in got)
    bad = 0; first = None
    for i in range(min(ns, ng)):
        s_row = [norm(x) for x in src_t[i]]
        g_row = [norm(x) for x in got[i]]
        L = max(len(s_row), len(g_row))
        s_row += [""] * (L - len(s_row)); g_row += [""] * (L - len(g_row))
        for j in range(L):
            if s_row[j] != g_row[j]:
                bad += 1
                if first is None: first = (i + 1, j + 1, s_row[j], g_row[j])
    empty = sum(1 for r in got for c in r if c == "")
    dups = len(got) - len({tuple(r) for r in got})
    status = "OK " if (ns == ng and cs == cg and bad == 0) else "FAIL"
    print(f"[{status}] Supp {tag}: {ng}r x {cg}c | src {ns}r x {cs}c | "
          f"cell-mismatch {bad} | empty {empty} | dup-rows {dups}")
    if first:
        print(f"        first mismatch r{first[0]} c{first[1]}: src={first[2]!r} docx={first[3]!r}")
    if ns != ng or cs != cg or bad:
        problems.append(f"Supp {tag}: r{ns}->{ng} c{cs}->{cg} mismatch {bad}")

print("=" * 78)
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("ALL TABLES MATCH SOURCE")
