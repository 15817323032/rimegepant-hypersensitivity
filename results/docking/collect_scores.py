# -*- coding: utf-8 -*-
"""汇总 Vina 结果：从 *.log 提取 mode 1 亲和力"""
import re, sys
from pathlib import Path
import pandas as pd

d = Path(__file__).resolve().parent
rows = []
for log in sorted(d.glob("*.log")):
    txt = log.read_text(errors="replace")
    m = re.findall(r"^\s*(\d+)\s+(-?\d+\.\d+)\s+", txt, re.M)
    if not m:
        continue
    mode, aff = m[0]
    rows.append(dict(target=log.stem, mode1_affinity_kcal=float(aff)))
df = pd.DataFrame(rows).sort_values("mode1_affinity_kcal")
df.to_csv(d / "docking_scores.csv", index=False, encoding="utf-8-sig")
print(df.to_string(index=False))
