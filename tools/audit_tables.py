# -*- coding: utf-8 -*-
"""Audit rendered submission tables against their source files, cell by cell.

IMPORTANT: by default this audits the **delivered package**
(`submission_drugsafety/`), not the intermediate build output
(`submission/`). A green audit on an intermediate directory is worthless if
the package shipped a stale copy -- that is exactly how a stale Table 3
reached the package once.

Checks, per table:
  - row / column count vs source
  - every cell equals the source cell after the same translate+format pipeline
  - empty-cell count, duplicate-row count
  - [package mode] delivered copy must be cell-identical to the intermediate build
Exits non-zero if any mismatch is found.

Usage:
    python tools/audit_tables.py                 # audit delivered package
    python tools/audit_tables.py --intermediate  # audit build output only
"""
import argparse
import sys, importlib.util
from pathlib import Path
from docx import Document

ROOT = Path(r"C:/Users/wu-ke/WorkBuddy/2026-11-09-16-31-05/rimegepant_hypersensitivity")
spec = importlib.util.spec_from_file_location("mk", ROOT / "tools" / "make_submission.py")
mk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mk)

PKG = ROOT / "submission_drugsafety"
INT = ROOT / "submission"

ap = argparse.ArgumentParser()
ap.add_argument("--intermediate", action="store_true",
                help="audit submission/ instead of the delivered package")
args = ap.parse_args()

TBL_DIR = (INT / "tables") if args.intermediate else (PKG / "tables")
SUP_DIR = INT if args.intermediate else PKG
print(f"auditing: {'intermediate' if args.intermediate else 'delivered package'} -> {TBL_DIR}")


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


def compare(src_t, got, tag):
    """Print one line; return a problem string or None."""
    ns, ng = len(src_t), len(got)
    cs = max((len(r) for r in src_t), default=0)
    cg = max((len(r) for r in got), default=0)
    bad = 0
    first = None
    for i in range(min(ns, ng)):
        s_row = [norm(x) for x in src_t[i]]
        g_row = [norm(x) for x in got[i]]
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
        print(f"        first mismatch r{first[0]} c{first[1]}: "
              f"src={first[2]!r} docx={first[3]!r}")
    if ns != ng or cs != cg or bad:
        return f"{tag}: r{ns}->{ng} c{cs}->{cg} mismatch {bad}"
    return None


problems = []
print("=" * 78)
for n in sorted(mk.TITLES):
    kind, path, sheet, cap = mk.SOURCES[n]
    src = mk.xlsx_rows(path, sheet, cap) if kind == "xlsx" else mk.csv_rows(path, cap)
    src_t = mk.translate_rows(src)

    docx_p = TBL_DIR / f"Table_{n:02d}.docx"
    if not docx_p.exists():
        problems.append(f"Table {n:02d}: missing {docx_p}")
        print(f"[FAIL] Table {n:02d}: missing {docx_p}")
        continue
    got = docx_rows(docx_p)
    if got is None:
        problems.append(f"Table {n:02d}: no table found in {docx_p.name}")
        continue
    p = compare(src_t, got, f"Table {n:02d}")
    if p:
        problems.append(p)

    # stale-copy guard: delivered vs intermediate must be cell-identical
    if not args.intermediate:
        int_p = INT / "tables" / docx_p.name
        if int_p.exists():
            ig = docx_rows(int_p)
            if ig is not None and ig != got:
                problems.append(
                    f"Table {n:02d}: delivered copy differs from intermediate build "
                    f"({int_p}) -- rebuild: make_submission then build_drugsafety")
                print(f"        STALE: package copy != {int_p}")

# supplementary tables
print("-" * 78)
for tag, (title, footnote, spec_) in mk.SUPP_TITLES.items():
    kind, path, sheet, cap = spec_
    src = mk.xlsx_rows(path, sheet, cap) if kind == "xlsx" else mk.csv_rows(path, cap)
    src_t = mk.translate_rows(src)
    name = f"Supplementary_Table_{tag}_{mk.SUPP_SUFFIX[tag]}.docx"
    fp = SUP_DIR / name
    if not fp.exists():
        problems.append(f"Supp {tag}: missing {fp}")
        print(f"[FAIL] Supp {tag}: missing {name}")
        continue
    got = docx_rows(fp)
    if got is None:
        problems.append(f"Supp {tag}: no table in {fp.name}")
        continue
    p = compare(src_t, got, f"Supp {tag}")
    if p:
        problems.append(p)

    if not args.intermediate:
        int_fp = INT / name
        if int_fp.exists():
            ig = docx_rows(int_fp)
            if ig is not None and ig != got:
                problems.append(f"Supp {tag}: delivered copy differs from intermediate build")
                print(f"        STALE: package copy != {int_fp}")

print("=" * 78)
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print(f"ALL TABLES MATCH SOURCE ({'intermediate' if args.intermediate else 'delivered package'})")
