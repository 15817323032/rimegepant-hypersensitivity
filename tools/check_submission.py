# -*- coding: utf-8 -*-
"""投稿 docx 终检：中文残留 / 占位符 / 关键数字可读性。"""
import re
import sys

from docx import Document


def main(path: str) -> int:
    d = Document(path)
    paras = [p.text for p in d.paragraphs if p.text.strip()]
    fails = 0

    print(f"文件: {path}")
    print(f"段落(非空) {len(paras)} | 表格 {len(d.tables)}")

    zh = [t for t in paras if re.search(r"[\u4e00-\u9fff]", t)]
    print(f"\n中文行: {len(zh)}")
    for t in zh:
        print("  -", t[:110])

    ph = re.compile(r"(待补|配套期刊|to be filled|0000-0000-0000-0000|TODO|TBD)")
    hits = [t for t in paras if ph.search(t)]
    print(f"占位残留: {len(hits)}")
    if hits:
        fails += 1
        for t in hits:
            print("  -", t[:140])

    for probe in ("49.8% vs 43.2%", "15.6% vs 19.0%", "SMD \u22120.45",
                  "converting every non-year code", "38.8% aged 65"):
        ok = any(probe in t for t in paras)
        print(f"[{'ok' if ok else 'MISSING'}] {probe}")
        if not ok:
            fails += 1

    for t in paras:
        if t.startswith("Word count:"):
            print("\n" + t)

    t1 = d.tables[0]
    print("\n表1 年龄/性别行:")
    for r in t1.rows:
        c = r.cells[0].text.strip()
        if "Age" in c or "Sex" in c:
            print("  " + " | ".join(x.text.strip() for x in r.cells))

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "submission_drugsafety/main_manuscript.docx"))
