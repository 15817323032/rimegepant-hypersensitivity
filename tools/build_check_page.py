# -*- coding: utf-8 -*-
"""生成投稿包的「图表核对页」——把 12 张表与全部图并排铺成一页，便于通读校对。

数据源与 ``tools/make_submission.py`` 完全一致（同一 SOURCES / TITLES / ZH_MAP），
因此页面不会再与投稿件脱钩。每次改动结果文件后重跑本脚本即可。

运行:
    python tools/build_check_page.py
"""
from __future__ import annotations

import html
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.make_submission import (SOURCES, TITLES, csv_rows,  # noqa: E402
                                   translate_rows, xlsx_rows)

OUT = ROOT / "submission_drugsafety"
FIG_DIR = OUT / "figures"

STYLE = (
    "body{font-family:'Segoe UI',Arial,sans-serif;max-width:1200px;margin:24px auto;"
    "padding:0 16px;color:#1a1a1a;line-height:1.5}"
    "h1{font-size:22px;border-bottom:3px solid #2c5f8a;padding-bottom:8px}"
    "h2{font-size:17px;color:#2c5f8a;margin-top:40px}"
    ".cap{font-weight:600;margin:14px 0 4px}"
    ".note{font-size:12px;color:#555;margin:6px 0 18px;font-style:italic}"
    "table{border-collapse:collapse;font-size:11.5px;margin-bottom:8px}"
    "th,td{border:1px solid #bbb;padding:3px 7px;text-align:left;vertical-align:top}"
    "th{background:#e8eef4}tr:nth-child(even){background:#f7f9fb}"
    "img{max-width:100%;border:1px solid #ccc;margin:6px 0 4px}"
    ".figblock{margin-top:24px}"
    ".toc{background:#f2f6fa;padding:10px 16px;border-radius:6px;font-size:13px}"
    ".meta{font-size:11px;color:#888}"
)


def table_html(rows: list[list[str]]) -> str:
    if not rows:
        return "<p>(empty)</p>"
    head, body = rows[0], rows[1:]
    out = ["<table><tr>"]
    out += [f"<th>{html.escape(str(c))}</th>" for c in head]
    out.append("</tr>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>")
    out.append("</table>")
    return "".join(out)


def load_rows(n: int) -> list[list[str]]:
    kind, path, sheet, cap = SOURCES[n]
    rows = xlsx_rows(path, sheet, cap) if kind == "xlsx" else csv_rows(path, cap)
    return translate_rows(rows)


def main() -> None:
    figs = sorted(FIG_DIR.glob("Figure_*.png"))
    for name in ("Supplementary_Figure_S1.png", "Supplementary_Figure_S2.png"):
        sup = OUT / name
        if sup.exists():
            figs.append(sup)

    parts = [
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<title>图表核对页 — rimegepant FAERS</title>",
        f"<style>{STYLE}</style></head><body>",
        "<h1>图表核对页 — rimegepant FAERS/AEMS 投稿包（Drug Safety 版）</h1>",
        '<div class="toc">'
        f"共 {len(TITLES)} 张表、{len(figs)} 张图（正文图 {len(figs) - 2} 张 + 补充图 S1/S2）。"
        "本页由 <code>tools/build_check_page.py</code> 直接从投稿件的同一数据源生成，"
        "不另行维护数字；单元格若与 Table_XX 文件不一致，说明结果文件在生成后被改动过，"
        "应重跑 <code>tools/make_submission.py</code> 与 <code>tools/build_drugsafety.py</code>。"
        "</div>",
        f'<div class="meta">generated {date.today().isoformat()}</div>',
    ]

    for f in figs:
        label = f.stem.replace("_", " ")
        if f.parent == OUT:
            label = f.stem.replace("_", " ")  # supplementary figures live at package root
            src = f.name
        else:
            src = f"figures/{f.name}"
        parts.append(
            f'<div class="figblock"><div class="cap">{html.escape(label)}</div>'
            f'<img src="{src}"></div>'
        )

    parts.append(f"<h2>二、表（Tables 1–{max(TITLES)}）</h2>")
    for n in sorted(TITLES):
        title, footnote, _ = TITLES[n]
        rows = load_rows(n)
        parts.append(f'<div class="cap">Table {n}. {html.escape(title)}</div>')
        parts.append(f'<div class="meta">rows: {max(len(rows) - 1, 0)} (+1 header)</div>')
        parts.append(table_html(rows))
        parts.append(f'<div class="note">Footnote. {html.escape(footnote)}</div>')

    parts.append("</body></html>")

    fp = OUT / "图表核对页.html"
    fp.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {fp.relative_to(ROOT)}  ({len(TITLES)} tables, {len(figs)} figures)")


if __name__ == "__main__":
    main()
