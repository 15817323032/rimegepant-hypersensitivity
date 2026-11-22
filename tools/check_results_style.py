# -*- coding: utf-8 -*-
"""Lint the Results section for reporting-convention violations.

Motivation: after five review rounds the recurring complaint was never a wrong
number but inconsistent reporting style -- p-value decimals, percentages with
one vs two decimals, "Fig" vs "Fig.", "core" vs "focus" signals, AUC values
without a model-variant label, effect estimates without 95% CI.

Rules (FAIL unless marked WARN):
  R1  p values: '=' reported to 2 dp when >=0.01, 3 dp or scientific when <0.01
  R2  q values: 3 dp when >=0.001, scientific otherwise
  R3  percentages: 1 dp (2 dp only below 0.1%)
  R4  effect estimates (ratio-like) in text carry 95% CI  [WARN]
  R5  figure citations use 'Fig.' / 'Figure' consistently (no bare 'Fig')
  R6  terminology: 'core signal' (not 'focus signal'); unqualified
      'significant' is not allowed -- must be 'nominal(ly)' or negated
  R7  every AUC value names its model variant in the same sentence
  R8  minus signs are U+2212, not ASCII hyphen, in prose numbers
  R9  multi-table citations are in ascending numeric order
  R10 n/N reporting uses one form ('x of N (y%)' or 'x/N')

Usage:
    python tools/check_results_style.py [--section results|all] [--strict]
Exit code 1 in --strict mode when any FAIL is found.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(r"C:/Users/wu-ke/WorkBuddy/2026-11-09-16-31-05/rimegepant_hypersensitivity")
MD = ROOT / "docs" / "manuscript_en.md"

ap = argparse.ArgumentParser()
ap.add_argument("--section", choices=["results", "all"], default="results")
ap.add_argument("--strict", action="store_true")
args = ap.parse_args()

text = MD.read_text(encoding="utf-8")

# split into sections with their starting line numbers
lines = text.splitlines()
if args.section == "results":
    start = next(i for i, l in enumerate(lines) if l.startswith("## 3.1"))
    end = next(i for i, l in enumerate(lines) if l.startswith("# 4."))
else:
    start, end = 0, len(lines)

fails, warns = [], []


def add(kind, rule, lineno, msg, excerpt):
    rec = (rule, lineno, msg, excerpt.strip()[:110])
    (fails if kind == "FAIL" else warns).append(rec)


def lineno_of(pos):
    return text.count("\n", 0, pos) + 1


def sentences(block):
    """Yield (sentence, offset). Split only on '. ' before a capital/(' so that
    decimal points inside numbers (ROR 4.36) do not break sentences."""
    start = 0
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z(\[])|(?<=\.)\n", block):
        seg = block[start:m.start()]
        if seg.strip():
            yield seg, start
        start = m.end()
    if block[start:].strip():
        yield block[start:], start


section_text = "\n".join(lines[start:end])
base_offset = sum(len(l) + 1 for l in lines[:start])

# ---------- R1 p values ----------
for m in re.finditer(r"\bp\s*([=<>])\s*(\d*\.?\d+(?:e-?\d+)?)", section_text):
    if m.group(1) != "=":
        continue
    val = float(m.group(2))
    s = m.group(2)
    dp = len(s.split(".")[1]) if "." in s else 0
    if val == 0:
        add("FAIL", "R1", lineno_of(base_offset + m.start()),
            f"p = {s}: never report p = 0", m.group(0))
    elif val < 0.01:
        if dp < 3 and "e" not in s:
            add("FAIL", "R1", lineno_of(base_offset + m.start()),
                f"p = {s}: values <0.01 need 3 dp or scientific", m.group(0))
    elif dp != 2:
        add("FAIL", "R1", lineno_of(base_offset + m.start()),
            f"p = {s}: values >=0.01 are reported to 2 dp", m.group(0))

# ---------- R2 q values ----------
for m in re.finditer(r"\bq\s*=\s*(\d*\.?\d+(?:e-?\d+)?)", section_text):
    s = m.group(1)
    val = float(s)
    if "e" in s:
        continue  # scientific notation accepted
    dp = len(s.split(".")[1]) if "." in s else 0
    if val >= 0.001 and dp != 3:
        add("FAIL", "R2", lineno_of(base_offset + m.start()),
            f"q = {s}: >=0.001 reported to 3 dp", m.group(0))

# ---------- R3 percentages ----------
for m in re.finditer(r"(\d+\.?\d*)%", section_text):
    s = m.group(1)
    if "." not in s:
        continue
    dp = len(s.split(".")[1])
    val = float(s)
    if val < 0.1:
        continue
    if dp != 1:
        add("FAIL", "R3", lineno_of(base_offset + m.start()),
            f"{s}%: percentages use 1 dp (except <0.1%)", m.group(0))

# ---------- R4 effect estimates without CI ----------
def _r4_scope(lineno):
    """R4 only applies to Results and Discussion prose, not Methods/Intro."""
    if args.section == "results":
        return True
    res_i = next(i for i, l in enumerate(lines) if l.startswith("## 3.1"))
    disc_end = next((i for i, l in enumerate(lines) if l.startswith("# 5.")), len(lines))
    return (res_i + 1) <= lineno <= disc_end


for sent, off in sentences(section_text):
    if not _r4_scope(lineno_of(base_offset + off)):
        continue
    if re.search(r"\b(?:ROR|PRR|post/pre)\b", sent) and "CI" not in sent \
            and "confidence" not in sent and "Table" not in sent and "Fig" not in sent:
        add("WARN", "R4", lineno_of(base_offset + off),
            "effect estimate without 95% CI in the same sentence", sent)

# ---------- R5 figure citations: consistency, not a house style ----------
# Collect the three forms; flag only the minority form(s). The manuscript may
# legitimately standardise on 'Fig N' or 'Fig. N'; what is not acceptable is
# 'Fig N' + 'Figure N' + 'Fig. N' coexisting.
forms = {
    "Fig": len(re.findall(r"\bFig(?!\.)\s+S?\d", section_text)),
    "Fig.": len(re.findall(r"\bFig\.\s+S?\d", section_text)),
    "Figure": len(re.findall(r"\bFigure\s+S?\d", section_text)),
}
dominant = max(forms, key=forms.get)
for form, cnt in forms.items():
    if form == dominant or cnt == 0:
        continue
    pat = {"Fig": r"\bFig(?!\.)\s+S?\d",
           "Fig.": r"\bFig\.\s+S?\d",
           "Figure": r"\bFigure\s+S?\d"}[form]
    for m in re.finditer(pat, section_text):
        add("FAIL", "R5", lineno_of(base_offset + m.start()),
            f"mixed figure-citation form: '{m.group(0)}' (dominant: '{dominant}')",
            m.group(0))

# ---------- R6 terminology ----------
for m in re.finditer(r"\bfocus[ -]signal", section_text, re.I):
    add("FAIL", "R6", lineno_of(base_offset + m.start()),
        "'focus signal' is not a defined term; use 'core signal'", m.group(0))
for m in re.finditer(r"\bsignificant(?:ly)?\b", section_text):
    pre = section_text[max(0, m.start() - 60):m.start()]
    sent_start = max(section_text.rfind(". ", 0, m.start()), section_text.rfind("\n", 0, m.start()))
    sent = section_text[sent_start + 1:m.start() + 20]
    # negated / qualified / not a hypothesis-test claim (enrichment q values,
    # "absence of significant ...") are allowed
    if re.search(r"\b(?:not|no|non)[- ]", pre[-32:]) or re.search(r"nominally\s+$", pre):
        continue
    if "absence of" in sent.lower() or "enrichment" in sent.lower() or re.search(r"q\s*=", sent):
        continue
    add("FAIL", "R6", lineno_of(base_offset + m.start()),
        "unqualified 'significant' -- use 'nominal(ly)' or negate", pre[-40:] + m.group(0))

# ---------- R7 AUC labelling ----------
LABELS = ("full", "augmented", "no-TTO", "sensitivity", "23-feature", "21-feature",
          "adding", "model", "features")
for sent, off in sentences(section_text):
    if "AUC" not in sent:
        continue
    for m in re.finditer(r"AUC\s*(\d\.\d+)", sent):
        if not any(k.lower() in sent.lower() for k in LABELS):
            add("FAIL", "R7", lineno_of(base_offset + off),
                f"AUC {m.group(1)} does not name its model variant", sent)

# ---------- R8 minus signs ----------
for m in re.finditer(r"(?<![A-Za-z0-9])-(\d+\.\d+)", section_text):
    add("FAIL", "R8", lineno_of(base_offset + m.start()),
        f"ASCII hyphen before numeric value; use U+2212", m.group(0))

# ---------- R9 table citation order ----------
for m in re.finditer(r"\bTables?\s+((?:\d+\s*(?:,|and)\s*)+\d+)", section_text):
    nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
    if nums != sorted(nums):
        add("FAIL", "R9", lineno_of(base_offset + m.start()),
            f"table citations not ascending: {nums}", m.group(0))

# ---------- R10 n/N form ----------
of_form = len(re.findall(r"\d[\d,]*\s+of\s+(?:the\s+)?\d[\d,]*", section_text))
slash_form = len(re.findall(r"\(\d[\d,]*/\d[\d,]*\)", section_text))
if of_form and slash_form:
    add("WARN", "R10", lineno_of(base_offset),
        f"mixed n/N forms: 'x of N' x{of_form} vs 'x/N' x{slash_form}", "")

# ---------- report ----------
def dump(title, recs):
    if not recs:
        return
    print(f"\n{title} ({len(recs)})")
    for rule, ln, msg, exc in sorted(recs, key=lambda r: (r[1], r[0])):
        print(f"  [{rule}] line {ln}: {msg}")
        if exc:
            print(f"        ...{exc}")

print(f"scope: {args.section} section (lines {start + 1}-{end})")
dump("FAIL", fails)
dump("WARN", warns)
print(f"\nsummary: FAIL {len(fails)} | WARN {len(warns)}")
if args.strict and fails:
    sys.exit(1)
