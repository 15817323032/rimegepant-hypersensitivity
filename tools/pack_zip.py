# -*- coding: utf-8 -*-
"""重打投稿压缩包（与 presubmit_check.py 的 PARITY 检查对齐）。

用法: python tools/pack_zip.py
输出: ../submission_drugsafety_2026-11-20.zip（即工作区根目录）
"""
import hashlib
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # rimegepant_hypersensitivity/
SRC = ROOT / "submission_drugsafety"
DST = ROOT.parent / "submission_drugsafety_2026-11-20.zip"

SKIP = {"main_manuscript_updated.docx"}

files = sorted(
    p for p in SRC.rglob("*")
    if p.is_file() and p.name not in SKIP
)
with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, str(p.relative_to(ROOT)))

data = DST.read_bytes()
print("packed", len(files), "files ->", DST)
print("size", len(data), "sha256", hashlib.sha256(data).hexdigest()[:16] + "...")
