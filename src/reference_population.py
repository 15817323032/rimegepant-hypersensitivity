# -*- coding: utf-8 -*-
"""
参考人群对照列（READUS-PV 清单 8b）

两层参照系，用于回答"这些差异是瑞美吉泮特有的，还是偏头痛用药报告本来就长这样"：

  参照系 A｜全库参考人群（full-database reference）
      全库去重后病例 − 瑞美吉泮 primary-suspect 病例 = N − N_PS
      即不成比例分析 ROR/PRR 的分母人群本身，与效应估计共用同一参照系。

  参照系 B｜适应证匹配参考人群（indication-matched reference）
      全库去重病例中，INDI 表记录有偏头痛适应证（indication）的病例，
      且排除瑞美吉泮 primary-suspect 病例。
      目的：把"偏头痛患者本来就年轻、女性多、消费者自报多、非严重结局多"
      这层适应证混杂（confounding by indication）从对比中吸收掉 ——
      与 A 的差异若在 B 中明显缩小，说明该差异由适应证驱动而非药物驱动。

扫描 5 遍（复用 stream_cache 的 PS 病例集合，无需重扫 DRUG）：
  Pass 1  DEMO  → 重建 FDA 标准去重后的 primaryid 保留集（与 cache Pass 2 完全一致）
  Pass 2  INDI  → 偏头痛适应证病例集（参照系 B 的成员资格）
  Pass 3  DEMO  → 队列 / A / B 及队列∩B 的年龄、性别、报告者、国家 计数
  Pass 4  REAC  → 每例事件数分布（(primaryid, pt) 去重后）
  Pass 5  OUTC  → 严重结局（任一结局行）与 DE/LT/HO/DS 分项

变量定义与 run_module1.table1() 逐行对齐；脚本末尾用既有 Table 1 对拍队列列，
任何不一致直接抛错，避免两列口径悄悄漂移。Pass 3 另设"队列 ∩ 适应证"通路（cm），
用于检验敏感性：把队列本身也限定为偏头痛适应证后，与 B 的差异是否仍成立。

统计比较用标准化均差（SMD）而非 p 值：参照人群百万例以上，
任何差异都会 p<0.001，p 值在此完全失去区分力；SMD 不受样本量影响，
|SMD| > 0.10 作为"有意义的不均衡"阈值（Austin 2011 的通行标准）。

用法：
    python src/reference_population.py --raw data/raw --out results_full
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ageutil import age_years  # noqa: E402
from src.faers_io import iter_chunks  # noqa: E402

SERIOUS_CODES = ("DE", "LT", "HO", "DS")

# 偏头痛适应证词族：MIGRAINE / MIGRAINES / MIGRAINOUS / 各亚型（with aura、hemiplegic、
# vestibular、abdominal、menstrual ...）均以内含 "MIGRAIN" 覆盖；
# "HEADACHE" / "CLUSTER HEADACHE" 不纳入（特异性不足，会把紧张性头痛等混入）。
MIGRAINE_TOKEN = "MIGRAIN"

# 四条统计通路：c 队列 / cm 队列∩偏头痛 / r 全库参考 / m 适应证匹配参考
ROUTES = ("c", "cm", "r", "m")


# ---------------------------------------------------------------- 工具函数
def pct(n: int, tot: int) -> str:
    return f"{n:,} ({100 * n / tot:.1f}%)" if tot else "-"


def smd_binary(p1: float, p0: float) -> float:
    """二分变量的标准化均差（队列 vs 参照人群）。"""
    den = np.sqrt((p1 * (1 - p1) + p0 * (1 - p0)) / 2)
    return 0.0 if den == 0 else (p1 - p0) / den


def fmt_smd(v: float | None) -> str:
    """两位小数；负号用 U+2212，与正文排印一致。"""
    if v is None:
        return "\u2014"
    return f"{v:+.2f}".replace("-", "\u2212")


def fmt_iqr(x: np.ndarray) -> str:
    if x.size == 0:
        return "NA"
    q1, q2, q3 = np.percentile(x, [25, 50, 75])
    return f"{q2:.0f} ({q1:.0f}\u2013{q3:.0f})"


def routes_of(pid: pd.Series, ps: set, mig: set) -> dict[str, np.ndarray]:
    """把一块 primaryid 映射到四条统计通路的布尔掩码。

    mig 为"INDI 命中偏头痛"的全集（含队列），因此 cm 与 m 两路互斥且都不为空：
        cm = 队列 ∩ 偏头痛     m = 偏头痛 − 队列
    """
    is_ps = pid.isin(ps).values
    is_mig = pid.isin(mig).values
    return {"c": is_ps, "cm": is_ps & is_mig, "r": ~is_ps, "m": is_mig & ~is_ps}


# ---------------------------------------------------------------- Pass 1
def build_kept(raw_dir: Path, quarters: list[str], chunksize: int, log) -> tuple[set, int]:
    """与 stream_cache Pass 2 完全相同的 FDA 标准去重。"""
    log("[ref] Pass 1/5 重建去重保留集 ...")
    parts = []
    for q in quarters:
        for ch in iter_chunks(raw_dir, "DEMO", q,
                              ["primaryid", "caseid", "caseversion", "fda_dt"], chunksize):
            parts.append(ch)
    sk = pd.concat(parts, ignore_index=True)
    parts.clear()
    for c in ("primaryid", "caseid", "caseversion", "fda_dt"):
        sk[c] = pd.to_numeric(sk[c], errors="coerce")
    sk = sk.dropna(subset=["caseid", "primaryid"])
    sk = sk.sort_values(["caseid", "fda_dt", "primaryid"],
                        ascending=[True, False, False])
    sk = sk.drop_duplicates("caseid", keep="first")
    n_total = len(sk)
    kept = set(sk["primaryid"].astype("int64").astype(str))
    del sk
    log(f"  去重后 N = {n_total:,}")
    return kept, n_total


# ---------------------------------------------------------------- Pass 2
def scan_indi(raw_dir: Path, quarters: list[str], chunksize: int,
              kept: set, ps: set, log) -> tuple[set, int]:
    """INDI 命中偏头痛适应证的病例全集（含队列），及其中属于队列的例数。

    返回全集是为了让外层一次筛出两条通路：cm = 队列∩偏头痛、m = 偏头痛−队列。
    """
    log("[ref] Pass 2/5 扫描 INDI 构建适应证匹配参考集 ...")
    mig: set[str] = set()
    n_ps_mig: set[str] = set()
    n_hits = 0
    for q in quarters:
        for ch in iter_chunks(raw_dir, "INDI", q, ["primaryid", "indi_pt"], chunksize):
            if "indi_pt" not in ch.columns or "primaryid" not in ch.columns:
                continue
            ind = ch["indi_pt"].fillna("").astype(str).str.upper()
            hit = ind.str.contains(MIGRAINE_TOKEN, regex=False).values
            if not hit.any():
                continue
            pid = (pd.to_numeric(ch["primaryid"], errors="coerce")
                   .astype("Int64").astype(str))
            pid_hit = pid[hit]
            pid_hit = pid_hit[pid_hit.isin(kept)]
            if pid_hit.empty:
                continue
            n_hits += pid_hit.size
            pids = set(pid_hit.tolist())
            mig |= pids
            n_ps_mig |= (pids & ps)
    log(f"  偏头痛适应证命中 {n_hits:,} 行 | 命中病例全集 = {len(mig):,} "
        f"| 其中队列 {len(n_ps_mig):,} | 参照系 B = {len(mig) - len(n_ps_mig):,}")
    return mig, len(n_ps_mig)


# ---------------------------------------------------------------- Pass 3
def scan_demo(raw_dir: Path, quarters: list[str], chunksize: int,
              kept: set, ps: set, mig: set, log) -> dict:
    log("[ref] Pass 3/5 扫描 DEMO 人口学 ...")
    cols = ["primaryid", "age", "age_cod", "sex", "rept_cod", "reporter_country"]
    age = {k: [] for k in ROUTES}
    sex = {k: Counter() for k in ROUTES}
    rep = {k: Counter() for k in ROUTES}
    ctry = {k: Counter() for k in ROUTES}

    for q in quarters:
        for ch in iter_chunks(raw_dir, "DEMO", q, cols, chunksize):
            pid = pd.to_numeric(ch["primaryid"], errors="coerce").astype("Int64").astype(str)
            m_keep = pid.isin(kept).values
            if not m_keep.any():
                continue
            ch = ch.loc[m_keep].reset_index(drop=True)
            pid = pid[m_keep].reset_index(drop=True)

            def col(name):
                return (ch[name] if name in ch
                        else pd.Series("", index=ch.index))

            a = age_years(col("age"), col("age_cod"))
            sx = col("sex").fillna("").astype(str).str.upper().str.strip()
            rp = col("rept_cod").fillna("").astype(str).str.upper().str.strip()
            ct = col("reporter_country").fillna("").astype(str).str.upper().str.strip()

            for k, mask in routes_of(pid, ps, mig).items():
                if mask.any():
                    age[k].append(a.values[mask].astype("float32"))
                    sex[k].update(sx[mask].tolist())
                    rep[k].update(rp[mask].tolist())
                    ctry[k].update(ct[mask].tolist())
        log(f"  {q}: 队列累计 {sum(x.size for x in age['c']):,}")

    return dict(
        age={k: (np.concatenate(v) if v else np.array([])) for k, v in age.items()},
        sex=sex, rep=rep, ctry=ctry)


# ---------------------------------------------------------------- Pass 4
def scan_reac(raw_dir: Path, quarters: list[str], chunksize: int,
              kept: set, ps: set, mig: set, log) -> dict:
    log("[ref] Pass 4/5 扫描 REAC 统计每例事件数 ...")
    cohort_n = []
    hist = {k: np.zeros(61, dtype="int64") for k in ("r", "m")}   # 0..59, 60 = 59+
    for q in quarters:
        for ch in iter_chunks(raw_dir, "REAC", q, ["primaryid", "pt"], chunksize):
            ch["pt"] = ch["pt"].fillna("").astype(str).str.strip().str.upper()
            ch = ch[ch["pt"].ne("") & ch["pt"].ne("NAN")]
            ch["pid"] = (pd.to_numeric(ch["primaryid"], errors="coerce")
                         .astype("Int64").astype(str))
            ch = ch[ch["pid"].isin(kept)]
            if ch.empty:
                continue
            ch = ch.drop_duplicates(["pid", "pt"])
            cnt = ch.groupby("pid").size()
            idx = cnt.index
            is_c = idx.isin(ps)
            if is_c.any():
                cohort_n.append(cnt.values[is_c])
            is_m = idx.isin(mig) & ~is_c
            for k, sel in (("r", ~is_c), ("m", is_m)):
                if sel.any():
                    v = np.clip(cnt.values[sel], 0, 60)
                    hist[k] += np.bincount(v, minlength=61)[:61]
    cohort_n = np.concatenate(cohort_n) if cohort_n else np.array([], dtype="int64")
    return dict(cohort_n=cohort_n, hist=hist,
                n_ref={k: int(h.sum()) for k, h in hist.items()})


# ---------------------------------------------------------------- Pass 5
def scan_outc(raw_dir: Path, quarters: list[str], chunksize: int,
              kept: set, ps: set, mig: set, log) -> dict:
    log("[ref] Pass 5/5 扫描 OUTC 统计严重结局 ...")
    any_ = {k: 0 for k in ROUTES}
    code_ = {k: Counter() for k in ROUTES}
    for q in quarters:
        for ch in iter_chunks(raw_dir, "OUTC", q, ["primaryid", "outc_cod"], chunksize):
            pid = pd.to_numeric(ch["primaryid"], errors="coerce").astype("Int64").astype(str)
            m = pid.isin(kept).values
            if not m.any():
                continue
            pid = pid[m].reset_index(drop=True)
            code = ch["outc_cod"].loc[m].fillna("").astype(str).str.upper().str.strip()
            code = code.reset_index(drop=True)
            for k, mask in routes_of(pid, ps, mig).items():
                if not mask.any():
                    continue
                any_[k] += pid[mask].nunique()
                for c in SERIOUS_CODES:
                    sel = code.eq(c).values & mask
                    if sel.any():
                        code_[k][c] += pid[sel].nunique()
    return dict(any=any_, code=code_)


# ---------------------------------------------------------------- 汇总
def hist_quantile(hist: np.ndarray, n: int, q: float) -> int:
    if n == 0:
        return 0
    cum = np.cumsum(hist)
    i = int(np.searchsorted(cum, q * n, side="left"))
    return min(i, len(hist) - 1)


def build_table(demo: dict, reac: dict, outc: dict,
                n: dict[str, int]) -> pd.DataFrame:
    """三列构成 + 两列 SMD。

    比例的分母一律明示：构成行（缺失率）用列内全部病例，分组行（年龄段、性别）
    用"该变量有记录者"。否则缺失率的差异会灌进分组 SMD——
    例如全库性别缺失 15.8%、队列 26.8%，用全列作分母会把女性的真实 SMD
    +0.65 稀释成 +0.28，凭空造出一个"中等不均衡"。
    """
    n_ps, n_ref, n_mig = n["c"], n["r"], n["m"]
    rows: list[tuple] = []

    def add(label, v_c, v_r, s_r, v_m, s_m):
        rows.append((label, v_c, v_r, s_r, v_m, s_m))

    def row(label, nc, nr, nm, dc, dr, dm):
        pc, pr, pm = nc / dc, nr / dr, nm / dm
        add(label, pct(nc, dc), pct(nr, dr),
            fmt_smd(smd_binary(pc, pr)), pct(nm, dm), fmt_smd(smd_binary(pc, pm)))

    add("Cases, N", f"{n_ps:,}", f"{n_ref:,}", "\u2014", f"{n_mig:,}", "\u2014")

    age = {k: v[~np.isnan(v)] for k, v in demo["age"].items()}
    add("Age, median (IQR), years",
        fmt_iqr(age["c"]), fmt_iqr(age["r"]), "\u2014", fmt_iqr(age["m"]), "\u2014")

    def bands(a):
        # 半开区间，避免单位换算后的小数年龄（如 44.5 岁）落不进任何一档，
        # 造成四档合计 ≠ 有记录例数
        return {"<18": int((a < 18).sum()), "18-44": int(((a >= 18) & (a < 45)).sum()),
                "45-64": int(((a >= 45) & (a < 65)).sum()), ">=65": int((a >= 65).sum())}
    bc, br, bm = bands(age["c"]), bands(age["r"]), bands(age["m"])
    ac, ar, am = age["c"].size, age["r"].size, age["m"].size
    row("Age missing", n_ps - ac, n_ref - ar, n_mig - am, n_ps, n_ref, n_mig)
    for k in ("<18", "18-44", "45-64", ">=65"):
        row(f"  Age {k} years (of recorded)", bc[k], br[k], bm[k], ac, ar, am)

    def cg(cnt, key):
        return cnt.get(key, 0)

    sc = {k: sum(cg(demo["sex"][k], x) for x in "FM") for k in ROUTES}
    row("Sex missing/unknown", n_ps - sc["c"], n_ref - sc["r"], n_mig - sc["m"],
        n_ps, n_ref, n_mig)
    for key, lab in (("F", "Female (of sex recorded)"), ("M", "Male (of sex recorded)")):
        row(lab, cg(demo["sex"]["c"], key), cg(demo["sex"]["r"], key),
            cg(demo["sex"]["m"], key), sc["c"], sc["r"], sc["m"])

    for key, lab in (("EXP", "Reporter, physician"),
                     ("PER", "Reporter, consumer"),
                     ("DIR", "Reporter, manufacturer/other")):
        row(lab, cg(demo["rep"]["c"], key), cg(demo["rep"]["r"], key),
            cg(demo["rep"]["m"], key), n_ps, n_ref, n_mig)

    cn = reac["cohort_n"].astype(float)
    med_r = f"{hist_quantile(reac['hist']['r'], reac['n_ref']['r'], .5)}" \
            f" ({hist_quantile(reac['hist']['r'], reac['n_ref']['r'], .25)}" \
            f"\u2013{hist_quantile(reac['hist']['r'], reac['n_ref']['r'], .75)})"
    med_m = f"{hist_quantile(reac['hist']['m'], reac['n_ref']['m'], .5)}" \
            f" ({hist_quantile(reac['hist']['m'], reac['n_ref']['m'], .25)}" \
            f"\u2013{hist_quantile(reac['hist']['m'], reac['n_ref']['m'], .75)})"
    add("Events per case, median (IQR)", fmt_iqr(cn), med_r, "\u2014", med_m, "\u2014")

    o = outc
    row("Serious outcome (any)", o["any"]["c"], o["any"]["r"], o["any"]["m"],
        n_ps, n_ref, n_mig)
    for c, lab in (("DE", "  Death"), ("LT", "  Life-threatening"),
                   ("HO", "  Hospitalisation"), ("DS", "  Disability")):
        row(lab, cg(o["code"]["c"], c), cg(o["code"]["r"], c), cg(o["code"]["m"], c),
            n_ps, n_ref, n_mig)

    # 国家：三路前 5 的并集，按全库参考降序
    cc, cr, cm = demo["ctry"]["c"], demo["ctry"]["r"], demo["ctry"]["m"]
    wanted = set()
    for cnt in (cc, cr, cm):
        wanted |= {c for c, _ in cnt.most_common(5) if c and c != "NAN"}
    for c in sorted(wanted, key=lambda x: -cr.get(x, 0)):
        row(f"Country {c}", cg(cc, c), cg(cr, c), cg(cm, c), n_ps, n_ref, n_mig)

    return pd.DataFrame(rows, columns=[
        "Characteristic",
        "Rimegepant, n (%)",
        "Full database, n (%)",
        "SMD",
        "Indication-matched, n (%)",
        "SMD"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--cache", default="data/interim/stream_cache")
    ap.add_argument("--out", default="results_full")
    ap.add_argument("--chunksize", type=int, default=2_000_000)
    ap.add_argument("--quarters", nargs="*", default=None,
                    help="仅用于快速调试：只跑指定季度，并跳过总例数对拍")
    ap.add_argument("--reuse", action="store_true",
                    help="复用上次扫描的中间统计（只重算表格），用于调整呈现口径")
    ap.add_argument("--rescan-demo", action="store_true",
                    help="保留归档的 REAC/OUTC 统计，只重扫 DEMO+INDI 以刷新人口学"
                         "（年龄单位归一化后使用；比全量重扫省掉最重的 REAC 通道）")
    a = ap.parse_args()

    t0 = time.time()

    def log(m):
        print(m, flush=True)

    cd = ROOT / a.cache
    with open(cd / "meta.pkl", "rb") as f:
        meta = pickle.load(f)
    ps = set(meta["ids"]["PS"])
    n_total_cached = meta["n_total"]

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    inter_fp = out / "ref_intermediate.pkl"

    if a.rescan_demo and inter_fp.exists():
        with open(inter_fp, "rb") as f:
            st = pickle.load(f)
        n, reac, outc = st["n"], st["reac"], st["outc"]
        n_total = st["n_total"]
        log(f"[ref] 保留归档 REAC/OUTC 统计，重扫人口学（Pass 1/2/3）")
        raw = ROOT / a.raw
        quarters = sorted(p.name for p in Path(raw).glob("20*Q*")
                          if p.is_dir() and len(p.name) == 6)
        kept, n_total_fresh = build_kept(raw, quarters, a.chunksize, log)
        if n_total_fresh != n_total:
            raise SystemExit(f"重扫后 N 与归档不一致: {n_total_fresh:,} vs {n_total:,}")
        mig, _ = scan_indi(raw, quarters, a.chunksize, kept, ps, log)
        demo = scan_demo(raw, quarters, a.chunksize, kept, ps, mig, log)
        with open(inter_fp, "wb") as f:
            pickle.dump(dict(n=n, demo=demo, reac=reac, outc=outc,
                             n_total=n_total), f, protocol=4)
        log(f"[ref] 中间统计已更新 {inter_fp.name}")
    elif a.reuse and inter_fp.exists():
        with open(inter_fp, "rb") as f:
            st = pickle.load(f)
        n, demo, reac, outc = st["n"], st["demo"], st["reac"], st["outc"]
        n_total = st["n_total"]
        log(f"[ref] 复用中间统计 {inter_fp.name}（跳过扫描）")
    else:
        raw = ROOT / a.raw
        quarters = sorted(p.name for p in Path(raw).glob("20*Q*")
                          if p.is_dir() and len(p.name) == 6)
        if a.quarters:
            quarters = [q for q in quarters if q in set(a.quarters)]
            log(f"[ref] 调试模式：仅 {quarters}")
        log(f"[ref] 季度 {len(quarters)} 个（{quarters[0]} ~ {quarters[-1]}），"
            f"PS 病例 {len(ps):,}")

        kept, n_total = build_kept(raw, quarters, a.chunksize, log)
        if a.quarters is None and n_total != n_total_cached:
            raise SystemExit(f"去重后 N 与缓存不一致: {n_total:,} vs {n_total_cached:,}")

        mig, n_ps_mig = scan_indi(raw, quarters, a.chunksize, kept, ps, log)

        n = dict(c=len(ps & kept), r=n_total - len(ps & kept),
                 m=len(mig) - n_ps_mig, cm=n_ps_mig)
        log(f"  队列 N_PS = {n['c']:,} | 全库参考 = {n['r']:,} "
            f"| 适应证匹配参考 = {n['m']:,} | 队列∩偏头痛 = {n['cm']:,}")

        demo = scan_demo(raw, quarters, a.chunksize, kept, ps, mig, log)
        reac = scan_reac(raw, quarters, a.chunksize, kept, ps, mig, log)
        outc = scan_outc(raw, quarters, a.chunksize, kept, ps, mig, log)

        with open(inter_fp, "wb") as f:
            pickle.dump(dict(n=n, demo=demo, reac=reac, outc=outc, n_total=n_total),
                        f, protocol=4)
        log(f"[ref] 中间统计已存档 {inter_fp.name}")

    tbl = build_table(demo, reac, outc, n)

    csv_path = out / "table1_with_reference.csv"
    tbl.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # ---- 敏感性分析：把队列本身也限定为偏头痛适应证（cm）后，与参照系 B 的差异是否仍在
    # 性别同样只用"有记录者"作分母，否则缺失率差异会主导结果
    def frac(cnt, key, den):
        return cnt.get(key, 0) / den if den else float("nan")

    sc_cm = sum(demo["sex"]["cm"].get(x, 0) for x in "FM")
    sc_m = sum(demo["sex"]["m"].get(x, 0) for x in "FM")

    sens = {
        "female": (float(smd_binary(frac(demo["sex"]["cm"], "F", sc_cm),
                                    frac(demo["sex"]["m"], "F", sc_m)))
                   if sc_cm and sc_m else float("nan")),
        "consumer_reporter": (float(smd_binary(frac(demo["rep"]["cm"], "PER", n["cm"]),
                                               frac(demo["rep"]["m"], "PER", n["m"])))
                              if n["cm"] and n["m"] else float("nan")),
        "country_us": (float(smd_binary(frac(demo["ctry"]["cm"], "US", n["cm"]),
                                        frac(demo["ctry"]["m"], "US", n["m"])))
                       if n["cm"] and n["m"] else float("nan")),
        "serious_any": (float(smd_binary(outc["any"]["cm"] / n["cm"],
                                         outc["any"]["m"] / n["m"]))
                        if n["cm"] and n["m"] else float("nan")),
    }

    summary = dict(
        n_total=n_total, n_ps=n["c"], n_ref=n["r"], n_mig=n["m"], n_ps_mig=n["cm"],
        age_median_cohort=float(np.nanmedian(demo["age"]["c"])),
        age_median_ref=float(np.nanmedian(demo["age"]["r"])),
        age_median_mig=float(np.nanmedian(demo["age"]["m"])),
        age_missing_cohort=int(np.isnan(demo["age"]["c"]).sum()),
        age_missing_ref=int(np.isnan(demo["age"]["r"]).sum()),
        age_missing_mig=int(np.isnan(demo["age"]["m"]).sum()),
        female_cohort=int(demo["sex"]["c"].get("F", 0)),
        female_ref=int(demo["sex"]["r"].get("F", 0)),
        female_mig=int(demo["sex"]["m"].get("F", 0)),
        serious_cohort=outc["any"]["c"], serious_ref=outc["any"]["r"],
        serious_mig=outc["any"]["m"],
        reac_cases_ref=reac["n_ref"]["r"], reac_cases_mig=reac["n_ref"]["m"],
        smd_sensitivity_cm_vs_m={k: round(v, 4) for k, v in sens.items()},
        runtime_s=round(time.time() - t0),
    )
    with open(out / "reference_population_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    log("\n" + tbl.to_string(index=False))
    log(f"\n[ref] 敏感性（队列∩偏头痛 vs 适应证匹配参考）: "
        + ", ".join(f"{k}={v:+.2f}" for k, v in sens.items()))
    log(f"\n[ref] 输出 {csv_path}（用时 {summary['runtime_s']} s）")


if __name__ == "__main__":
    main()
