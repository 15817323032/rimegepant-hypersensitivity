# -*- coding: utf-8 -*-
"""Run every pre-submission gate in the correct order and summarise.

Why this exists: each gate used to be run by hand, and the one that was
forgotten was always the one that would have caught the bug (a stale table
copy, a figure from an old render directory, an out-of-sync title). One
command, fixed order, non-zero exit on any failure.

Gates (order matters):
  1. audit_tables        delivered package vs source, cell by cell + stale-copy
  2. check_results_style reporting-convention lint (whole manuscript)
  3. verify_claims       every number re-derived from archived results (--strict)
  4. check_submission    docx cleanliness, placeholders, word count
  5. presubmit_check     cross-file consistency, figure bytes, zip parity

Usage:
    python tools/gate_all.py            # all gates
    python tools/gate_all.py --fast     # skip presubmit (zip rebuild not needed)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:/Users/wu-ke/WorkBuddy/2026-11-09-16-31-05/rimegepant_hypersensitivity")
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

GATES = [
    ("tables", ["tools/audit_tables.py"]),
    ("style", ["tools/check_results_style.py", "--section", "all", "--strict"]),
    ("claims", ["tools/verify_claims.py", "--strict"]),
    ("docx", ["tools/check_submission.py", "submission_drugsafety/main_manuscript.docx"]),
    ("presubmit", ["tools/presubmit_check.py"]),
]

ap = argparse.ArgumentParser()
ap.add_argument("--fast", action="store_true", help="skip the presubmit gate")
args = ap.parse_args()

results = []
for name, cmd in GATES:
    if args.fast and name == "presubmit":
        continue
    t0 = time.time()
    print(f"\n{'=' * 70}\n>>> {name}: {' '.join(cmd)}\n{'=' * 70}", flush=True)
    p = subprocess.run([PY] + cmd, cwd=str(ROOT))
    dt = time.time() - t0
    results.append((name, p.returncode, dt))

print(f"\n{'=' * 70}\nGATE SUMMARY\n{'=' * 70}")
bad = 0
for name, code, dt in results:
    flag = "PASS" if code == 0 else "FAIL"
    if code:
        bad += 1
    print(f"[{flag}] {name:<10} {dt:6.1f}s  (exit {code})")
print(f"\n{bad} gate(s) failed" if bad else "\nALL GATES PASSED")
sys.exit(1 if bad else 0)
