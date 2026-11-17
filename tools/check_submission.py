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

    # 内嵌表漏转换防线：docx 中不得有以竖线开头的段落（原始 md 管道表残留）
    pipes = [t for t in paras if t.strip().startswith("|")]
    print(f"管道表残留: {len(pipes)}")
    if pipes:
        fails += 1
        for t in pipes[:10]:
            print("  -", t[:110])

    # 浮点全精度裸奔防线：表格单元格不得出现 str(float) 级全精度（>=6 位小数；
    # 数据文件中刻意保留的 4 位小数如 Brier 0.0912 不受影响）
    import re as _re
    fp = _re.compile(r"\d+\.\d{6,}")
    bad_fp = []
    for ti, tb in enumerate(d.tables, 1):
        for r in tb.rows:
            for c in r.cells:
                m = fp.search(c.text)
                if m:
                    bad_fp.append((ti, m.group(0)))
    print(f"浮点全精度残留: {len(bad_fp)}")
    if bad_fp:
        fails += 1
        for ti, m in bad_fp[:10]:
            print(f"  - Table#{ti}: {m}")

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
