#!/usr/bin/env python
"""
verify_claims.py — 稿件数值声明的回源校验器

防止三类已经发生过的错误复发：
  1) 稿件里的数字在源文件中找不到（或对不上）              -> FAIL
  2) 派生值算错（Δ = ΔG(target) − ΔG(on-target)、SMD、
     百分比 = n/分母 等）                                   -> FAIL
  3) 选择性引用：源里有两个相关数（rmsd l.b./u.b.），
     稿件只引对自己有利的那个且未标注界别                   -> WARN

覆盖范围：
  docking  受体存在性、盒子与 manifest、mode-1 判据、Δ 自洽、RMSD 引用
  signals  计数（437/102/94/49/19）与逐个 PT 的 ROR
  ml       四个模型的 AUC
  label    六个过敏家族的 post/pre 比
  counts   队列与参照规模、TTO 筛选链
  smd      表 1 两列 + INDI 子集敏感性；并用「a% vs b%」反算 SMD 查错配
  pct      表 1/4/5 内部算术；正文每个百分比必须可回源或显式登记为外部值

用法：
  python tools/verify_claims.py                 # 终端报告
  python tools/verify_claims.py --write-report  # 另写 docs/claim_audit.md
  python tools/verify_claims.py --strict        # WARN 也失败（发布前 gate）

退出码：0 全通过；1 有 FAIL（--strict 时含 WARN）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "manuscript_en.md"
TBLDIR = ROOT / "submission" / "tables"
DOCK = ROOT / "results" / "docking"
FULL = ROOT / "results_full"
BOOK = FULL / "all_tables_full.xlsx"

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def rendered_tables_text() -> str:
    """编号表格（submission/tables/Table_*.docx|xlsx）的全部单元格文本。

    编号表由数据文件直接渲染，其数值不再出现在正文段落里（如 T7 各模型
    AUC、T12 逐家族 post/pre），因此回源语料必须包含渲染产物，否则这些
    归档数字会被误判为「未在稿件中出现」。
    """
    import openpyxl
    from docx import Document

    parts: list[str] = []
    for f in sorted(TBLDIR.glob("Table_*.docx")):
        d = Document(f)
        parts += [p.text for p in d.paragraphs]
        parts += [c.text for t in d.tables for r in t.rows for c in r.cells]
    for f in sorted((ROOT / "submission" / "supplementary").glob("Supplementary_Table_*.docx")):
        d = Document(f)
        parts += [p.text for p in d.paragraphs]
        parts += [c.text for t in d.tables for r in t.rows for c in r.cells]
    for f in sorted(TBLDIR.glob("Table_*.xlsx")):
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                parts += [str(v) for v in row if v is not None]
        wb.close()
    return norm("\n".join(parts))
TAG = {PASS: "  ok ", WARN: " warn", FAIL: " FAIL"}

TARGET_ALIAS = {
    "CALCRL_3N7S": ["CALCRL", "CGRP receptor"],
    "SYK": ["SYK"],
    "BTK": ["BTK"],
}


@dataclass
class Finding:
    level: str
    area: str
    claim: str
    detail: str = ""


findings: list[Finding] = []


def add(level: str, area: str, claim: str, detail: str = "") -> None:
    findings.append(Finding(level, area, claim, detail))


# ------------------------------------------------------------------ 工具
MINUS = "\u2212\u2013\u2014"


def norm(text: str) -> str:
    for ch in MINUS:
        text = text.replace(ch, "-")
    return re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)


def has_num(text: str, value: float, decimals: int) -> bool:
    token = f"{value:.{decimals}f}"
    return re.search(rf"(?<![\d.]){re.escape(token)}(?![\d])", text) is not None


def read_table(name: str) -> pd.DataFrame:
    csv = FULL / f"{name}.csv"
    if csv.exists():
        return pd.read_csv(csv)
    return pd.read_excel(BOOK, sheet_name=name)


def sentences(md: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;])\s+", md) if s.strip()]


# ------------------------------------------------------------- 1. 对接
@dataclass
class VinaRun:
    key: str
    modes: list[tuple[int, float, float, float]] = field(default_factory=list)
    cfg: dict[str, float] = field(default_factory=dict)
    config_path: Path | None = None


def parse_log(path: Path) -> list[tuple[int, float, float, float]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*(\d+)\s+(-?\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s*$", line)
        if m:
            out.append((int(m.group(1)), float(m.group(2)),
                        float(m.group(3)), float(m.group(4))))
    return out


def parse_cfg(path: Path) -> dict[str, float]:
    cfg = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*(\w+)\s*=\s*(-?\d+\.?\d*)\s*$", line)
        if m:
            cfg[m.group(1)] = float(m.group(2))
    return cfg


def audit_docking(md: str) -> dict[str, float]:
    manifests = {}
    mpath = DOCK / "docking_manifest.json"
    if mpath.exists():
        manifests = {m["target"]: m for m in json.loads(mpath.read_text(encoding="utf-8"))}
    scores = None
    spath = DOCK / "docking_scores.csv"
    if spath.exists():
        scores = pd.read_csv(spath)

    runs: dict[str, VinaRun] = {}
    for log in sorted(DOCK.glob("vina_log_*.txt")):
        key = log.stem.replace("vina_log_", "")
        run = VinaRun(key=key, modes=parse_log(log))
        run.config_path = DOCK / f"vina_{key}.txt"
        if run.config_path.exists():
            run.cfg = parse_cfg(run.config_path)
        runs[key] = run

        if not run.modes:
            add(FAIL, "docking", f"{key} log", "解析不到 mode 表")
            continue

        # a) 受体文件必须存在（幽灵配置检测）
        rec = None
        if run.config_path.exists():
            m = re.search(r"^\s*receptor\s*=\s*(\S+)",
                          run.config_path.read_text(encoding="utf-8", errors="replace"), re.M)
            rec = m.group(1) if m else None
        if rec and not (DOCK / rec).exists():
            add(FAIL, "docking", f"{key} receptor", f"{rec} 不存在（幽灵配置）")
        elif rec:
            add(PASS, "docking", f"{key} receptor", rec)

        # b) 盒子必须与 manifest 一致
        base = key.replace("_3N7S", "")
        if {"size_x", "size_y", "size_z"} <= run.cfg.keys():
            vol = run.cfg["size_x"] * run.cfg["size_y"] * run.cfg["size_z"]
            man = manifests.get(base)
            if not man:
                add(WARN, "docking", f"{base} box", "manifest 缺该靶点")
            else:
                mv = 1.0
                for s in man["size"]:
                    mv *= s
                if abs(mv - vol) > 1:
                    add(FAIL, "docking", f"{base} box",
                        f"manifest {mv:.0f} Å³ ≠ 实跑 {vol:.0f} Å³")
                else:
                    add(PASS, "docking", f"{base} box", f"{vol:.0f} Å³ 与 manifest 一致")

    # c) on-target 判据
    on = None
    for key, run in runs.items():
        if key.startswith("CALCRL") and run.modes:
            on = run.modes[0][1]
            add(PASS if on <= -8 else FAIL, "docking", "CALCRL mode-1",
                f"{on:.3f} kcal/mol（判据 ≤ -8）")

    # d) Δ 方向与自洽：Δ = ΔG(target) − ΔG(on-target)
    if on is not None and scores is not None:
        for key, run in runs.items():
            base = key.replace("_3N7S", "")
            if base == "CALCRL" or not run.modes:
                continue
            delta = run.modes[0][1] - on
            row = scores[scores["target"] == base]
            if not row.empty:
                src = float(row.iloc[0]["delta_vs_on_target"])
                if abs(src - round(delta, 3)) > 0.02:
                    add(FAIL, "docking", f"{base} Δ",
                        f"scores.csv {src} ≠ 计算 {delta:.3f}")
                else:
                    add(PASS, "docking", f"{base} Δ", f"{delta:+.2f} kcal/mol 自洽")
            if not has_num(md, delta, 1):
                add(FAIL, "docking", f"{base} Δ 未在稿件", f"期望 {delta:+.1f}")

    # e) 选择性引用：只在“含靶点名的句子”内判定
    sents = sentences(md)
    for key, run in runs.items():
        aliases = TARGET_ALIAS.get(key, [key])
        for sent in sents:
            if not any(a.lower() in sent.lower() for a in aliases):
                continue
            if not re.search(r"rmsd|mode-?\s?[2-9]|binding mode", sent, re.I):
                continue
            for mode, _aff, lb, ub in run.modes:
                if mode == 1 or abs(lb - ub) < 0.5:
                    continue
                cited = [(lb, "lower", ub), (ub, "upper", lb)]
                hits = [(v, w, o) for v, w, o in cited if has_num(sent, v, 1)]
                if not hits:
                    continue
                labelled = re.search(
                    r"upper[-\s]?bound|lower[-\s]?bound|rmsd\s*[lu]\.?\s?b", sent, re.I)
                for val, which, other in hits:
                    if labelled:
                        add(PASS, f"docking:{key} mode-{mode}",
                            f"引用 {val:.1f} Å（已标注 {which} bound）")
                    elif has_num(sent, other, 1):
                        add(PASS, f"docking:{key} mode-{mode}",
                            f"{lb:.1f}/{ub:.1f} Å 均引用")
                    else:
                        add(WARN, f"docking:{key} mode-{mode}",
                            f"只引 {which} 界 {val:.1f} Å，另一界 {other:.1f} Å 缺失且未标注",
                            "选择性引用：应写区间或标注 upper/lower bound")
    return {k: (v.modes[0][1] if v.modes else float("nan")) for k, v in runs.items()}


# ------------------------------------------------------------- 2. 信号
def audit_signals(md: str) -> None:
    # 表格行（| PT | a | ROR |）会污染邻近匹配：PT 后紧跟的是 a 值，
    # 且 ROR 列还带 CI。表格本身由 table3 保证，这里只在正文中做邻近校验。
    prose = re.sub(r"^\|.*$", "", md, flags=re.M)
    t3 = read_table("table3_focus_signals")
    n_focus = len(t3)
    n_pos = int(t3["is_signal"].sum()) if "is_signal" in t3 else None

    # 只校验稿件确实引用的计数（focus 簇 49 与阳性 19）
    for label, value in (("focus PT 数", n_focus), ("其中阳性", n_pos)):
        if value is None:
            continue
        lvl = PASS if has_num(md, value, 0) else FAIL
        add(lvl, "signals", label, f"{value} {'已回源' if lvl == PASS else '未在稿件中出现'}")

    t2 = read_table("table2_all_signals")
    lvl = PASS if has_num(md, len(t2), 0) else FAIL
    add(lvl, "signals", "a>=3 PT 数", f"{len(t2)} {'已回源' if lvl == PASS else '未出现'}")

    # 稿件提及某 PT 时，紧邻处若给了 ROR，必须与本行一致
    checked = 0
    for _, row in t3.iterrows():
        pt = str(row["PT"]).lower()
        if pt not in prose.lower():
            continue
        idx = prose.lower().find(pt)
        # 只接受“紧跟 PT 名”的数字，避免抓到相邻 PT 或括号内的 CI：
        #   "paraesthesia oral (ROR 4.64)"  "hypoaesthesia oral (4.34)"  "swollen tongue 3.55"
        window = prose[idx + len(pt): idx + len(pt) + 34]
        m = re.match(r"\s*\(?\s*(?:ROR\s*)?(-?\d+\.\d+)", window, re.I)
        if not m:
            m = re.search(r"ROR\s*(-?\d+\.\d+)", window, re.I)
        if not m:
            checked += 1
            add(PASS, "signals", row["PT"], f"提及但未给 ROR（表值 {row['ROR']:.2f}）")
            continue
        cited = float(m.group(1))
        dec = len(m.group(1).split(".")[1])          # 按稿件给出的小数位对齐
        src_ror = round(float(row["ROR"]), dec)
        if abs(cited - src_ror) <= 1e-9:
            checked += 1
            add(PASS, "signals", row["PT"], f"ROR {cited:.2f} 与表一致")
        else:
            checked += 1
            add(FAIL, "signals", row["PT"], f"稿件 {cited:.2f} ≠ 表 {row['ROR']:.2f}")


# ------------------------------------------------------------- 3. 模型
def audit_models(md: str) -> None:
    # 以 ml_model_comparison.csv 为源（T7 工作表是它的论文版式渲染，不是源头）
    comp_path = ROOT / "results_ml_real/ml_model_comparison.csv"
    if comp_path.exists():
        t7 = pd.read_csv(comp_path)
        mod_col, auc_col = "model", "auc_mean"
    else:  # 退化路径：旧版工作簿
        t7 = read_table("T7_ML_models")
        mod_col, auc_col = "model", "auc_mean"
    for _, row in t7.iterrows():
        if str(row[mod_col]).startswith("Null"):
            continue
        auc = float(row[auc_col])
        lvl = PASS if has_num(md, auc, 3) else WARN
        add(lvl, "ml", f"{row[mod_col]} AUC",
            f"{auc:.3f} {'已回源' if lvl == PASS else '未在稿件中出现'}")


# ------------------------------------------------------------- 4. 标签前后
def audit_label(md: str) -> None:
    t12 = read_table("T12_label_prepost")
    for _, row in t12.iterrows():
        fam = str(row["family"])
        ratio = float(row["ratio_post_vs_pre"])
        p = float(row["p_fisher"])
        # 正文按 2 位小数引用（表内保留全精度），3 位或 2 位命中均可
        lvl = PASS if (has_num(md, ratio, 3) or has_num(md, ratio, 2)) else WARN
        add(lvl, "label", fam, f"post/pre={ratio:.2f}, p={p:.2f}")


# ------------------------------------------------------------- 5. 关键计数
def audit_counts(md: str) -> None:
    t4 = read_table("table4_tto")
    blob = " | ".join(str(v) for v in t4["值"])
    pairs = []
    for value in t4["值"]:
        for num in re.findall(r"\d[\d,]*", str(value)):
            pairs.append(int(num.replace(",", "")))
    for target in (1060, 848):
        if target in pairs:
            lvl = PASS if has_num(md, target, 0) else FAIL
            add(lvl, "counts", f"TTO {target}",
                "已回源" if lvl == PASS else "未在稿件中出现")

    # 队列与参照规模
    for label, value in (("cohort PS", 8962), ("PS+SS", 9691), ("all roles", 13190),
                         ("full DB", 9094154), ("reference", 9085192),
                         ("indication-matched", 75155)):
        lvl = PASS if has_num(md, value, 0) else WARN
        add(lvl, "counts", label, f"{value} {'已回源' if lvl == PASS else '未出现'}")


# ------------------------------------------------------------- 6. SMD
SMD_TOKEN = re.compile(r"([+\-]\d\.\d{2})")
PAIR_PCT = re.compile(r"(\d+(?:\.\d+)?)%\s*(?:vs\.?|and)\s*(\d+(?:\.\d+)?)%")
CELL = re.compile(r"([\d,]+)\s*\(\s*(\d+(?:\.\d+)?)%\s*\)")
T1_COLS = ["Rimegepant, n (%)", "Full database, n (%)", "Indication-matched, n (%)"]


def _int_of(text) -> int | None:
    m = re.search(r"[\d,]+", str(text))
    return int(m.group(0).replace(",", "")) if m else None


def _smd_of(value) -> float | None:
    try:
        return float(str(value).replace("\u2212", "-").replace("+", "").strip())
    except ValueError:
        return None


def smd_binary(p1: float, p0: float) -> float:
    """二分变量 SMD，与 src/reference_population.py 完全一致。"""
    den = ((p1 * (1 - p1) + p0 * (1 - p0)) / 2) ** 0.5
    return 0.0 if den == 0 else (p1 - p0) / den


def smd_index() -> dict[float, list[str]]:
    """SMD 源值（两位小数）-> 出处。含表 1 两列与 INDI 子集敏感性 JSON。"""
    idx: dict[float, list[str]] = {}
    t1 = read_table("table1_with_reference")
    for _, r in t1.iterrows():
        char = str(r["Characteristic"]).strip()
        for col, lab in (("SMD", "vs 全库"), ("SMD.1", "vs 适应证匹配")):
            v = _smd_of(r[col])
            if v is not None:
                idx.setdefault(round(v, 2), []).append(f"表1 {char} {lab}")
    p = FULL / "reference_population_summary.json"
    if p.exists():
        sens = json.loads(p.read_text(encoding="utf-8")).get("smd_sensitivity_cm_vs_m", {})
        for k, v in sens.items():
            idx.setdefault(round(float(v), 2), []).append(f"INDI 子集敏感性 {k}")
    return idx


def audit_smd(md: str) -> None:
    idx = smd_index()

    # a) 存在性：稿件里每个 SMD 数值都必须能在源里找到
    cited: dict[float, int] = {}
    for sent in sentences(md):
        if "smd" not in sent.lower():
            continue
        for tok in SMD_TOKEN.findall(sent):
            v = round(float(tok), 2)
            cited[v] = cited.get(v, 0) + 1

    missing = sorted(v for v in cited if v not in idx)
    for v in missing:
        add(FAIL, "smd", f"SMD {v:+.2f}", "表 1 与敏感性 JSON 均无此值")
    if not missing:
        add(PASS, "smd", f"{len(cited)} 个 SMD 引用",
            "全部可回源（表 1 两列 + INDI 子集敏感性）")
    for v in sorted(cited):
        if v in idx:
            add(PASS, "smd", f"SMD {v:+.2f}", "；".join(idx[v][:2]))

    # b) 自洽：由同句的「a% vs b%」重算 SMD，防止百分比与 SMD 错配
    n_pairs, bad = 0, []
    for m in PAIR_PCT.finditer(md):
        tail = md[m.end(): m.end() + 60]
        sm = re.search(r"SMD\s*([+\-]\d\.\d{2})", tail)
        if not sm or "%" in tail[: sm.start()]:
            continue                      # 中间还有别的百分比 -> 配对不可靠，跳过
        calc = smd_binary(float(m.group(1)) / 100, float(m.group(2)) / 100)
        got = float(sm.group(1))
        n_pairs += 1
        if abs(abs(calc) - abs(got)) > 0.02:     # 允许方向相反（稿件可能先写参照系）
            bad.append(f"{m.group(1)}% vs {m.group(2)}% 应得 {calc:+.2f}，稿件 {got:+.2f}")
    for b in dict.fromkeys(bad):
        add(FAIL, "smd", "百分比-SMD 错配", b)
    if n_pairs and not bad:
        add(PASS, "smd", f"{n_pairs} 组百分比对", "重算 SMD 与稿件一致（±0.02）")

    # c) INDI 子集敏感性（JSON 是本项目唯一来源）
    p = FULL / "reference_population_summary.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        n_sub = d.get("n_ps_mig")
        if n_sub:
            lvl = PASS if has_num(md, n_sub, 0) else FAIL
            add(lvl, "smd", "INDI 子集病例数", f"{n_sub:,} {'已回源' if lvl == PASS else '未出现'}")
        for key, lab in (("female", "female"), ("consumer_reporter", "consumer"),
                         ("country_us", "US"), ("serious_any", "serious")):
            v = (d.get("smd_sensitivity_cm_vs_m") or {}).get(key)
            if v is None:
                continue
            lvl = PASS if has_num(md, round(float(v), 2), 2) else FAIL
            add(lvl, "smd", f"敏感性 {lab}", f"{float(v):+.2f} {'已回源' if lvl == PASS else '未出现'}")


# ------------------------------------------------------------- 7. 百分比
PCT_TOKEN = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)%")


def table1_pcts() -> set[float]:
    """表 1 三个 n(%) 列的全部百分比；顺带校验内部算术与分组求和。"""
    t = read_table("table1_with_reference")
    rows = {str(r["Characteristic"]).strip(): r for _, r in t.iterrows()}
    tot = {c: _int_of(rows["Cases, N"][c]) for c in T1_COLS}
    den = {}
    for c in T1_COLS:
        age_miss = _int_of(rows["Age missing"][c])
        sex_miss = _int_of(rows["Sex missing/unknown"][c])
        den[c] = {"all": tot[c], "age": tot[c] - age_miss, "sex": tot[c] - sex_miss}

    stated: set[float] = set()
    checked, bad = 0, []
    for char, r in rows.items():
        if "of sex recorded" in char:
            kind = "sex"
        elif "of recorded" in char:
            kind = "age"
        else:
            kind = "all"
        for c in T1_COLS:
            m = CELL.search(str(r[c]))
            if not m:
                continue
            n, p = int(m.group(1).replace(",", "")), float(m.group(2))
            stated.add(p)
            checked += 1
            exp = 100 * n / den[c][kind] if den[c][kind] else float("nan")
            if abs(p - exp) > 0.06:
                bad.append(f"{char} · {c.split(',')[0]}：{p}% vs 重算 {exp:.1f}%")

    # 分组求和：age 四档 = 有年龄记录者；F+M = 有性别记录者
    def cell_n(char, c):
        m = CELL.search(str(rows[char][c]))
        return int(m.group(1).replace(",", "")) if m else 0
    for c in T1_COLS:
        s_age = sum(cell_n(f"Age {k} years (of recorded)", c) for k in ("<18", "18-44", "45-64", ">=65"))
        if s_age != den[c]["age"]:
            bad.append(f"{c.split(',')[0]}：年龄四档合计 {s_age} ≠ 有记录 {den[c]['age']}")
        s_sex = cell_n("Female (of sex recorded)", c) + cell_n("Male (of sex recorded)", c)
        if s_sex != den[c]["sex"]:
            bad.append(f"{c.split(',')[0]}：性别 F+M {s_sex} ≠ 有记录 {den[c]['sex']}")

    for b in bad:
        add(FAIL, "pct:table1", "内部算术", b)
    if not bad:
        add(PASS, "pct:table1", f"{checked} 个 n(%) 单元格",
            "分母重算一致，四档求和与有记录数一致")
    return stated


def audit_table_pcts() -> set[float]:
    """表 4（TTO）与表 5（亚组）的百分比重算，返回其声明值集合。"""
    out: set[float] = set()

    t4 = read_table("table4_tto")
    kv = dict(zip(t4["指标"].astype(str), t4["值"].astype(str)))
    base = {"两日期均完整": 8962, "可分析 TTO 的病例数": 8962,
            "0d": 848, "1d": 848, "2-7d": 848, "8-30d": 848, "31-90d": 848, ">90d": 848}
    bad4 = []
    for k, v in kv.items():
        m = CELL.search(v)
        if not m or k not in base:
            continue
        n, p = int(m.group(1).replace(",", "")), float(m.group(2))
        out.add(p)
        exp = 100 * n / base[k]
        if abs(p - exp) > 0.06:
            bad4.append(f"{k}：{p}% vs 重算 {exp:.1f}%")
    for b in bad4:
        add(FAIL, "pct:table4", "TTO 百分比", b)
    if not bad4:
        add(PASS, "pct:table4", f"{len(out)} 个 TTO 百分比", "分母 8,962 / 848 重算一致")

    t5 = read_table("table5_subgroup")
    bad5 = []
    for _, r in t5.iterrows():
        m = re.match(r"(\d+(?:\.\d+)?)%", str(r["占比"]))
        if not m:
            continue
        p, n, k = float(m.group(1)), int(r["报告数"]), int(r["切口事件数"])
        out.add(p)
        exp = 100 * k / n if n else float("nan")
        if abs(p - exp) > 0.06:
            bad5.append(f"{r['变量']}={r['水平']}：{p}% vs 重算 {exp:.1f}%")
        lo, hi = (float(x) for x in str(r["Wilson95CI"]).split("-"))
        if not (lo <= p <= hi):
            bad5.append(f"{r['变量']}={r['水平']}：{p}% 不在 CI {lo}–{hi} 内")
    for b in bad5:
        add(FAIL, "pct:table5", "亚组百分比", b)
    if not bad5:
        add(PASS, "pct:table5", f"{len(t5)} 个亚组", "占比=k/n 重算一致，均在 Wilson CI 内")
    return out


def derived_pcts() -> tuple[dict[float, str], list[str]]:
    """稿件里由计数派生的百分比：现场复算，不硬编码。"""
    out: dict[float, str] = {}
    notes: list[str] = []

    fp = ROOT / "results_ml_real" / "ml_feature_table.csv"
    if fp.exists():
        y = pd.read_csv(fp, usecols=["y"])["y"]
        out[round(100 * y.mean(), 1)] = f"复合终点 {int(y.sum())}/{len(y)}"

    sp = ROOT / "results_ml_real" / "ml_top_feature_strata.csv"
    if sp.exists():
        s = pd.read_csv(sp)
        for _, r in s[s["feature"] == "sex_female"].iterrows():
            out[round(100 * float(r["positive_rate"]), 1)] = f"sex_female {r['quartile']} 阳性率"

    # pre/post 标签比较（主分析 + 保留 Q3 敏感性）的家族百分比
    for tag in ("prepost_family_comparison_primary", "prepost_family_comparison_sens_keepq3"):
        fp = ROOT / "results_label_change" / f"{tag}.csv"
        if fp.exists():
            d = pd.read_csv(fp)
            for _, r in d.iterrows():
                out[float(r["pre_pct"])] = f"{tag} {r['family']} pre%"
                out[float(r["post_pct"])] = f"{tag} {r['family']} post%"

    raw = ROOT / "raw_data_package" / "01_faers_source_rows"
    cmap = ROOT / "raw_data_package" / "02_case_id_map" / "case_id_inclusion_map.csv"
    if raw.exists() and cmap.exists():
        cm = pd.read_csv(cmap, dtype=str)
        ps = set(cm.loc[cm["in_primary_suspect"] == "True", "primaryid"])
        indi_f, drug_f = raw / "INDI.csv", raw / "DRUG.csv"
        if indi_f.exists():
            d = pd.read_csv(indi_f, dtype=str, usecols=["primaryid", "indi_pt"], low_memory=False)
            d = d[d["primaryid"].isin(ps)]
            share = 100 * d["indi_pt"].fillna("").str.upper().str.contains("MIGRAIN").mean()
            out[round(share, 1)] = f"队列 INDI 行含偏头痛 {share:.2f}%"
        if drug_f.exists():
            g = pd.read_csv(drug_f, dtype=str, usecols=["primaryid", "role_cod", "dose_form"],
                            low_memory=False)
            g = g[g["primaryid"].isin(ps) & (g["role_cod"].fillna("").str.upper() == "PS")]
            f = g["dose_form"].fillna("").str.upper()
            odt = f.str.contains("DISINTEGRAT|ORODISPERS|ODT")
            share = 100 * odt.mean()
            out[round(share, 1)] = f"PS 用药行 ODT 剂型 {share:.1f}%"
            blank = f == ""
            share_blank = 100 * blank.mean()
            out[round(share_blank, 1)] = f"PS 用药行剂型未记录 {share_blank:.1f}%"
            tab = (~odt) & (~blank) & f.str.contains("TABLET")
            share_tab = 100 * tab.mean()
            out[round(share_tab, 1)] = f"PS 用药行记录为普通片剂 {share_tab:.1f}%"
            share_rec = 100 * (~blank).mean()
            out[round(share_rec, 1)] = f"PS 用药行剂型有记录 {share_rec:.1f}%"
    else:
        notes.append("原始数据包缺失：48.4% / 79% / 18% / 3% / 97% 等剂型与 INDI 项未校验")
    return out, notes


# 非本项目产出的百分比：必须显式登记，否则一律 FAIL（防止悄悄引入无源数字）
EXTERNAL_PCT = {
    86.6: "文献 [7] 报告值（3,839 例）",
    63.6: "文献 [9] 报告值（10,550 例）",
    95.0: "置信区间名义水平，非数据值",
}


def audit_pct_coverage(md: str, stated: set[float]) -> None:
    allowed: dict[float, str] = {p: "表1" for p in stated}

    derived, notes = derived_pcts()
    allowed.update(derived)
    for note in notes:
        add(WARN, "pct:derived", "派生值未校验", note)

    allowed.update(EXTERNAL_PCT)

    # 稿件正文（跳过 markdown 表格行：表内数字由表 1/4/5 各自校验）
    cited: dict[tuple[float, int], tuple[str, int]] = {}
    for line in md.splitlines():
        if line.lstrip().startswith("|"):
            continue
        for m in PCT_TOKEN.finditer(line):
            raw = m.group(1)
            dec = len(raw.split(".")[1]) if "." in raw else 0
            key = (float(raw), dec)
            prev = cited.get(key)
            cited[key] = (raw, (prev[1] if prev else 0) + 1)

    miss = []
    for (v, dec), (raw, k) in cited.items():
        if any(round(a, dec) == v for a in allowed):
            continue
        miss.append(f"{raw}%（出现 {k} 次）")
    for s in miss:
        add(FAIL, "pct:coverage", "无源百分比", s + "：表 1/4/5 均无，且未登记为外部值")
    if not miss:
        add(PASS, "pct:coverage", f"{len(cited)} 个百分比",
            f"全部可回源（表内 {len(stated)} 值 + 派生 {len(derived)} 值 + 外部登记 3 值）")


def audit_cross_table() -> None:
    """跨表口径：同一年龄/性别口径在表 1 与表 5 必须一致。"""
    t1 = read_table("table1_with_reference")
    rows = {str(r["Characteristic"]).strip(): r for _, r in t1.iterrows()}
    t5 = read_table("table5_subgroup")

    def n1(char):
        m = CELL.search(str(rows[char]["Rimegepant, n (%)"]))
        return int(m.group(1).replace(",", "")) if m else None

    m18 = CELL.search(str(rows["Age <18 years (of recorded)"]["Rimegepant, n (%)"]))
    if m18:
        v1 = int(m18.group(1).replace(",", ""))
        sub = t5[(t5["变量"] == "年龄组") & (t5["水平"] == "<18")]
        v5 = int(sub["报告数"].iloc[0]) if not sub.empty else None
        if v5 is None:
            add(WARN, "cross-table", "年龄<18", "表 5 无该水平")
        elif v5 != v1:
            add(WARN, "cross-table", "表1/表5 年龄<18",
                f"表1 {v1} vs 表5 {v5}——两表须共用 src/ageutil.age_years 的口径"
                f"（age_cod 单位归一化），出现差异说明有一处绕过了该函数")
        else:
            add(PASS, "cross-table", "年龄<18",
                f"{v1} 两表一致（均按 age_cod 单位归一化）")

    sex1 = (n1("Female (of sex recorded)") or 0) + (n1("Male (of sex recorded)") or 0)
    sg = t5[t5["变量"] == "性别"]["报告数"].sum()
    if int(sg) == sex1:
        add(PASS, "cross-table", "性别分母", f"{sex1} 两表一致")
    else:
        add(WARN, "cross-table", "性别分母", f"表1 {sex1} vs 表5 {int(sg)}")


def audit_percentages(md: str) -> None:
    stated = table1_pcts()
    stated |= audit_table_pcts()
    audit_pct_coverage(md, stated)
    audit_pct_pairing(md)
    audit_cross_table()


def audit_pct_pairing(md: str) -> None:
    """「a% vs b%」必须真的是同一行内的两列，或同一列内的两行。

    单值回源只能保证每个数在表里存在；若把 57.8% 误写成 58.7%（表里也有），
    单值检查发现不了。配对结构检查能抓到这种“错位引用”。
    """
    t1 = read_table("table1_with_reference")
    rows = []
    for _, r in t1.iterrows():
        cells = [CELL.search(str(r[c])) for c in T1_COLS]
        vals = [float(m.group(2)) for m in cells if m]
        if len(vals) == 3:
            rows.append(vals)
    if not rows:
        return

    def same_row(a: float, b: float) -> bool:
        for c, f, i in rows:
            for x, y in ((c, f), (c, i), (f, i)):
                if (round(x, 1), round(y, 1)) == (a, b) or (round(y, 1), round(x, 1)) == (a, b):
                    return True
        return False

    def same_col(a: float, b: float) -> bool:
        for k in range(3):
            hits = [r[k] for r in rows]
            if any(round(x, 1) == a for x in hits) and any(round(y, 1) == b for y in hits):
                return True
        return False

    # 表 5 内部：同一变量的不同水平
    t5 = read_table("table5_subgroup")
    t5p: dict[str, set[float]] = {}
    for _, r in t5.iterrows():
        m = re.match(r"(\d+(?:\.\d+)?)%", str(r["占比"]))
        if m:
            t5p.setdefault(str(r["变量"]), set()).add(round(float(m.group(1)), 1))

    def t5_pair(a: float, b: float) -> bool:
        return any(a in v and b in v for v in t5p.values())

    bad = []
    for m in PAIR_PCT.finditer(md):
        a, b = round(float(m.group(1)), 1), round(float(m.group(2)), 1)
        if abs(a - b) < 1e-9:
            continue
        if same_row(a, b) or same_col(a, b) or t5_pair(a, b):
            continue
        bad.append(f"{m.group(1)}% vs {m.group(2)}%")
    for b in dict.fromkeys(bad):
        if b in ALLOWED_PAIRS:
            add(PASS, "pct:pairing", "登记配对", b + "：" + ALLOWED_PAIRS[b])
        else:
            add(WARN, "pct:pairing", "配对可疑", b + "：两值均在表内，但不属同一行/同一列")

    if not bad:
        add(PASS, "pct:pairing", "百分比配对", "每个「a% vs b%」都能对应到表中同一行或同一列")


# 表结构覆盖不到的合法配对：SHAP 四分位阳性率对比（sex_female 最高/最低
# 四分位来自 ml_top_feature_strata 的不同行，属设计使然而非错位引用）
ALLOWED_PAIRS = {
    "12.9% vs 6.2%": "sex_female SHAP 最高 vs 最低四分位阳性率（ml_top_feature_strata Q4/Q1）",
}


def audit_reference_binding(md: str) -> None:
    """文献基准三方对齐：正文引用编号 ↔ 引用处数值 ↔ 参考文献条目；编号须连续。

    数值型声明分两类：本项目的数（回源到结果文件）与文献的数（无法回源，
    只能锁定"哪个数配哪条引用"）。后者一旦被改写而引用未变，这里会拦住。
    """
    block = md.split("# References", 1)[1]
    block = re.split(r"\n# ", block, maxsplit=1)[0]
    nums = [int(x) for x in re.findall(r"(?m)^(\d+)\.\s", block)]
    if nums == list(range(1, len(nums) + 1)):
        add(PASS, "references", "参考文献编号", f"1-{len(nums)} 连续，共 {len(nums)} 条")
    else:
        add(FAIL, "references", "参考文献编号", f"编号不连续：{nums}")

    cited = [s for s in sentences(md) if "[31]" in s]
    if not cited:
        add(WARN, "references", "基准引用 [31]", "正文未出现该引用")
    else:
        s = cited[0]
        ok = ("398" in s) and has_num(s, 0.69, 2) and ("OMOP" in s)
        add(PASS if ok else FAIL, "references", "基准引用 [31]",
            "OMOP 398 对 / AUC 0.69 与编号同位" if ok else "数值与编号不同位")

    entry = "\n".join(ln for ln in block.splitlines() if ln.startswith("31."))
    ok_ref = ("Pham" in entry) and ("Drug Saf" in entry) and ("s40264-018-00792-0" in entry)
    add(PASS if ok_ref else FAIL, "references", "条目 31 完整性",
        "Pham 2019 Drug Saf 42(6):743-750" if ok_ref else (entry[:70] or "缺失"))


# ------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-report", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    md = norm(MD.read_text(encoding="utf-8"))
    md += "\n" + rendered_tables_text()

    audit_docking(md)
    audit_signals(md)
    audit_models(md)
    audit_label(md)
    audit_counts(md)
    audit_smd(md)
    audit_percentages(md)
    audit_reference_binding(md)

    order = {FAIL: 0, WARN: 1, PASS: 2}
    findings.sort(key=lambda f: (order[f.level], f.area))

    for f in findings:
        print(f"[{TAG[f.level]}] {f.area:<26} {f.claim:<30} {f.detail}")

    n_fail = sum(f.level == FAIL for f in findings)
    n_warn = sum(f.level == WARN for f in findings)
    n_pass = sum(f.level == PASS for f in findings)
    print(f"\n合计：PASS {n_pass} | WARN {n_warn} | FAIL {n_fail}")

    if args.write_report:
        out = ROOT / "docs" / "claim_audit.md"
        lines = [
            "# 稿件数值回源审计\n",
            f"源：`docs/manuscript_en.md`；工具：`tools/verify_claims.py`\n",
            f"结果：PASS {n_pass} / WARN {n_warn} / FAIL {n_fail}\n",
            "| 级别 | 区域 | 声明 | 说明 |",
            "|---|---|---|---|",
        ]
        lines += [f"| {f.level} | {f.area} | {f.claim} | {f.detail} |" for f in findings]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"报告：{out}")

    return 1 if n_fail or (args.strict and n_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
