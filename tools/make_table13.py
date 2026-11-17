# -*- coding: utf-8 -*-
"""Generate Table 13 (bridge-gene module -> mechanistic assignment).

Reads results/network_tox/bridge_genes.csv (the Table 9 source) and emits
results_full/table13_bridge_assignment.csv. Gene groups, hop counts and the
interpretive assignment column are curated; bridge counts are taken from the
archived Table 9 data so the two tables cannot drift apart.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results/network_tox/bridge_genes.csv"
OUT = ROOT / "results_full/table13_bridge_assignment.csv"

# curated: module label -> (gene list, assignment)
MODULES = [
    ("GNG2 / GNB1 / GNAS",
     ("GNG2", "GNB1", "GNAS"),
     "CGRP-receptor downstream G-protein axis (on-target background)"),
    ("C3 / C5",
     ("C3", "C5"),
     "Complement activation, plausibly driving angioedema and pharyngeal swelling"),
    ("PLCG1 / SRC / MAPK1",
     ("PLCG1", "SRC", "MAPK1"),
     "FcεRI-downstream mast-cell activation"),
    ("CCL2 / CX3CL1 / CCR7",
     ("CCL2", "CX3CL1", "CCR7"),
     "Chemokine axis (enrichment-dominated; no single dominant bridge gene)"),
]


def main() -> None:
    counts: dict[str, tuple[str, str]] = {}
    with SRC.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            counts[row["gene"]] = (row["bridge_count"], row["min_hops"])

    rows = [["bridge_gene_module", "bridge_counts", "min_hops",
             "mechanistic_assignment"]]
    for label, genes, assignment in MODULES:
        missing = [g for g in genes if g not in counts]
        if missing:
            raise SystemExit(f"genes not in {SRC.name}: {missing}")
        parts, hops = [], []
        for g in genes:
            c, h = counts[g]
            parts.append(c)
            hops.append(int(h))
        hop_txt = (str(min(hops)) if min(hops) == max(hops)
                   else f"{min(hops)}–{max(hops)}")
        rows.append([label, "/".join(parts), hop_txt, assignment])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"saved {OUT} ({len(rows)-1} rows)")
    for r in rows[1:]:
        print("  ", r)


if __name__ == "__main__":
    main()
