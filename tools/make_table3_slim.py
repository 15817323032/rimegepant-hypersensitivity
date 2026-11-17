# -*- coding: utf-8 -*-
"""Slim Table 3 for the main text: 28 raw columns -> 5 journal columns.

Source: results_full/all_tables.xlsx!table3_focus_signals (full 28-col sheet
stays in the repository; the 437-signal master list is Table 2/Supp S2).
Output: results_full/table3_focus_slim.xlsx  (consumed by make_submission)
Columns: PT | Cases (a) | ROR (95% CI) | Algorithms positive (of 4) | Endpoint subset
"""
from pathlib import Path
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results_full" / "all_tables.xlsx"
SHEET = "table3_focus_signals"
DST = ROOT / "results_full" / "table3_focus_slim.xlsx"


def fmt1(x):
    return f"{x:.1f}" if abs(x) >= 100 else f"{x:.3f}".rstrip("0").rstrip(".")


def main():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb[SHEET]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    hdr, body = rows[0], rows[1:]
    ix = {name: j for j, name in enumerate(hdr)}

    out = [["Preferred term", "Cases (a)", "ROR (95% CI)",
            "Algorithms positive (of 4)", "Endpoint subset"]]
    for r in body:
        pt = r[ix["PT"]]
        a = int(r[ix["a"]])
        ror, lo, hi = r[ix["ROR"]], r[ix["ROR025"]], r[ix["ROR975"]]
        n_algo = int(r[ix["n_algo"]])
        subset = r[ix["subset"]] or ""
        out.append([pt.capitalize(), str(a),
                    f"{fmt1(ror)} ({fmt1(lo)}–{fmt1(hi)})",
                    f"{n_algo} / 4", subset])

    wdst = openpyxl.Workbook()
    sheet = wdst.active
    sheet.title = "table3_focus_slim"
    for r in out:
        sheet.append(r)
    wdst.save(DST)
    print(f"saved {DST}  rows={len(out)-1}  cols={len(out[0])}")


if __name__ == "__main__":
    main()
