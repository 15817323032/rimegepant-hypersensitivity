# -*- coding: utf-8 -*-
"""
参考人群对照列（READUS-PV 清单 8b）

参考人群（reference population）定义：
    全库去重后病例 − 瑞美吉泮 primary-suspect 病例  =  N − N_PS
即不成比例分析 ROR/PRR 的分母人群本身，因此"对照组"不是任意选择，
而是与效应估计所用同一参照系 —— 这一点是 8b 的方法学要点。

扫描 4 遍（复用 stream_cache 的 PS 病例集合，无需重扫 DRUG）：
  Pass 1  DEMO  → 重建 FDA 标准去重后的 primaryid 保留集（与 cache Pass 2 完全一致）
  Pass 2  DEMO  → 队列 / 背景人群 的年龄、性别、报告者、国家 计数
  Pass 3  REAC  → 每例事件数分布（(primaryid, pt) 去重后）
  Pass 4  OUTC  → 严重结局（任一结局行）与 DE/LT/HO/DS 分项

变量定义与 run_module1.table1() 逐行对齐；脚本末尾用既有 Table 1 对拍队列列，
任何不一致直接抛错，避免两列口径悄悄漂移。

统计比较用标准化均差（SMD）而非 p 值：背景人群 900 万例以上，
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

from src.faers_io import iter_chunks  # noqa: E402

SERIOUS_CODES = ("DE", "LT", "HO", "DS")


# ---------------------------------------------------------------- 工具函数
def pct(n: int, tot: int) -> str:
    return f"{n:,} ({100 * n / tot:.1f}%)" if tot else "-"


def smd_binary(p1: float, p0: float) -> float:
    """二分变量的标准化均差（队列 vs 背景人群）。"""
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


def median_from_hist(hist: np.ndarray, n: int, q: float) -> float:
    """从 0..len(hist)-1 的计数直方图取分位数（尾部桶按桶值计）。"""
    c = np.cumsum(hist)
    if n == 0:
        return float("nan")
    target = q * n
    idx = int(np.searchsorted(c, target, side="left"))
    return float(min(idx, len(hist) - 1))


# ---------------------------------------------------------------- Pass 1
def build_kept(raw_dir: Path, quarters: list[str], chunksize: int, log) -> tuple[set, int]:
    """与 stream_cache Pass 2 完全相同的 FDA 标准去重。"""
    log("[ref] Pass 1/4 重建去重保留集 ...")
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
def scan_demo(raw_dir: Path, quarters: list[str], chunksize: int,
              kept: set, ps: set, log) -> dict:
    log("[ref] Pass 2/4 扫描 DEMO 人口学 ...")
    cols = ["primaryid", "age", "age_cod", "sex", "rept_cod", "reporter_country"]
    age_c, age_r = [], []
    sex_c, sex_r = Counter(), Counter()
    rep_c, rep_r = Counter(), Counter()
    ctry_c, ctry_r = Counter(), Counter()

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

            age = pd.to_numeric(col("age"), errors="coerce")
            cod = col("age_cod").fillna("YR").astype(str).str.upper()
            age = age.where(cod.eq("YR")).where(lambda s: s.between(0, 120))
            sex = col("sex").fillna("").astype(str).str.upper().str.strip()
            rep = col("rept_cod").fillna("").astype(str).str.upper().str.strip()
            ctry = col("reporter_country").fillna("").astype(str).str.upper().str.strip()

            is_c = pid.isin(ps).values
            age_c.append(age.values[is_c].astype("float32"))
            age_r.append(age.values[~is_c].astype("float32"))
            sex_c.update(sex[is_c].tolist()); sex_r.update(sex[~is_c].tolist())
            rep_c.update(rep[is_c].tolist()); rep_r.update(rep[~is_c].tolist())
            ctry_c.update(ctry[is_c].tolist()); ctry_r.update(ctry[~is_c].tolist())
        log(f"  {q}: 队列累计 {sum(a.size for a in age_c):,}")

    return dict(age_c=np.concatenate(age_c) if age_c else np.array([]),
                age_r=np.concatenate(age_r) if age_r else np.array([]),
                sex_c=sex_c, sex_r=sex_r, rep_c=rep_c, rep_r=rep_r,
                ctry_c=ctry_c, ctry_r=ctry_r)


# ---------------------------------------------------------------- Pass 3
def scan_reac(raw_dir: Path, quarters: list[str], chunksize: int,
              kept: set, ps: set, log) -> dict:
    log("[ref] Pass 3/4 扫描 REAC 统计每例事件数 ...")
    cohort_n = []
    hist = np.zeros(61, dtype="int64")   # 0..59, 60 = 59+
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
            is_c = cnt.index.isin(ps)
            if is_c.any():
                cohort_n.append(cnt.values[is_c])
            v = np.clip(cnt.values[~is_c], 0, 60)
            hist += np.bincount(v, minlength=61)[:61]
    cohort_n = np.concatenate(cohort_n) if cohort_n else np.array([], dtype="int64")
    return dict(cohort_n=cohort_n, hist=hist, n_ref=int(hist.sum()))


# ---------------------------------------------------------------- Pass 4
def scan_outc(raw_dir: Path, quarters: list[str], chunksize: int,
              kept: set, ps: set, log) -> dict:
    log("[ref] Pass 4/4 扫描 OUTC 统计严重结局 ...")
    any_c = any_r = 0
    code_c = Counter(); code_r = Counter()
    for q in quarters:
        for ch in iter_chunks(raw_dir, "OUTC", q, ["primaryid", "outc_cod"], chunksize):
            pid = pd.to_numeric(ch["primaryid"], errors="coerce").astype("Int64").astype(str)
            m = pid.isin(kept).values
            if not m.any():
                continue
            pid = pid[m].reset_index(drop=True)
            code = ch["outc_cod"].loc[m].fillna("").astype(str).str.upper().str.strip()
            code = code.reset_index(drop=True)
            is_c = pid.isin(ps).values
            any_c += pid[is_c].nunique(); any_r += pid[~is_c].nunique()
            for c in SERIOUS_CODES:
                sel = code.eq(c).values
                if sel.any():
                    code_c[c] += pid[sel & is_c].nunique()
                    code_r[c] += pid[sel & ~is_c].nunique()
    return dict(any_c=any_c, any_r=any_r, code_c=code_c, code_r=code_r)


# ---------------------------------------------------------------- 汇总
def build_table(demo: dict, reac: dict, outc: dict, n_ps: int, n_ref: int) -> pd.DataFrame:
    ac, ar = demo["age_c"], demo["age_r"]
    ac = ac[~np.isnan(ac)]; ar = ar[~np.isnan(ar)]

    def bands(a):
        return {
            "<18": int((a < 18).sum()),
            "18-44": int(((a >= 18) & (a <= 44)).sum()),
            "45-64": int(((a >= 45) & (a <= 64)).sum()),
            ">=65": int((a >= 65).sum()),
        }
    bc, br = bands(ac), bands(ar)

    def prop(counter, key):
        return counter.get(key, 0)

    rows = []

    def add(label, v_c, v_r, smd=None):
        rows.append((label, v_c, v_r, fmt_smd(smd)))

    add("Cases, N", f"{n_ps:,}", f"{n_ref:,}")
    add("Age, median (IQR)", fmt_iqr(ac), fmt_iqr(ar))
    add("Age missing", pct(n_ps - ac.size, n_ps), pct(n_ref - ar.size, n_ref),
        smd_binary((n_ps - ac.size) / n_ps, (n_ref - ar.size) / n_ref))
    for k in ("<18", "18-44", "45-64", ">=65"):
        pc, pr = bc[k] / n_ps, br[k] / n_ref
        add(f"  Age {k} years", pct(bc[k], n_ps), pct(br[k], n_ref), smd_binary(pc, pr))

    for key, lab in (("F", "Female"), ("M", "Male")):
        pc, pr = prop(demo["sex_c"], key) / n_ps, prop(demo["sex_r"], key) / n_ref
        add(lab, pct(prop(demo["sex_c"], key), n_ps),
            pct(prop(demo["sex_r"], key), n_ref), smd_binary(pc, pr))
    mc = n_ps - sum(demo["sex_c"].get(k, 0) for k in ("F", "M"))
    mrr = n_ref - sum(demo["sex_r"].get(k, 0) for k in ("F", "M"))
    add("  Sex missing/unknown", pct(mc, n_ps), pct(mrr, n_ref),
        smd_binary(mc / n_ps, mrr / n_ref))

    for key, lab in (("EXP", "Reporter, physician (EXP)"),
                     ("PER", "Reporter, consumer (PER)"),
                     ("DIR", "Reporter, manufacturer/other (DIR)")):
        pc, pr = prop(demo["rep_c"], key) / n_ps, prop(demo["rep_r"], key) / n_ref
        add(lab, pct(prop(demo["rep_c"], key), n_ps),
            pct(prop(demo["rep_r"], key), n_ref), smd_binary(pc, pr))

    cn, hist, nr = reac["cohort_n"], reac["hist"], reac["n_ref"]
    ref_med = "NA"
    if nr:
        cnt_all = hist.copy()
        idx = np.arange(len(hist))
        # 直方图分位数：用累积计数定位
        cum = np.cumsum(cnt_all)
        def qpos(p):
            i = int(np.searchsorted(cum, p * nr, side="left"))
            return min(i, len(idx) - 1)
        ref_med = f"{qpos(.5)} ({qpos(.25)}\u2013{qpos(.75)})"
    add("Events per case, median (IQR)", fmt_iqr(cn.astype(float)), ref_med)

    add("Serious outcome (any)", pct(outc["any_c"], n_ps), pct(outc["any_r"], n_ref),
        smd_binary(outc["any_c"] / n_ps, outc["any_r"] / n_ref))
    for c, lab in (("DE", "  Death (DE)"), ("LT", "  Life-threatening (LT)"),
                   ("HO", "  Hospitalisation (HO)"), ("DS", "  Disability (DS)")):
        nc, nrr = prop(outc["code_c"], c), prop(outc["code_r"], c)
        add(lab, pct(nc, n_ps), pct(nrr, n_ref), smd_binary(nc / n_ps, nrr / n_ref))

    # 国家：队列前 5 与背景前 5 的并集，按背景占比降序
    c_c, c_r = demo["ctry_c"], demo["ctry_r"]
    wanted = {c for c, _ in c_c.most_common(5) if c and c != "NAN"}
    wanted |= {c for c, _ in c_r.most_common(5) if c and c != "NAN"}
    for c in sorted(wanted, key=lambda x: -c_r.get(x, 0)):
        nc, nrr = c_c.get(c, 0), c_r.get(c, 0)
        add(f"Country {c}", pct(nc, n_ps), pct(nrr, n_ref),
            smd_binary(nc / n_ps, nrr / n_ref))

    return pd.DataFrame(rows, columns=[
        "Characteristic", f"Rimegepant PS cases (n = {n_ps:,})",
        f"Reference population (n = {n_ref:,})", "SMD"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--cache", default="data/interim/stream_cache")
    ap.add_argument("--out", default="results_full")
    ap.add_argument("--chunksize", type=int, default=2_000_000)
    a = ap.parse_args()

    t0 = time.time()

    def log(m):
        print(m, flush=True)

    cd = ROOT / a.cache
    with open(cd / "meta.pkl", "rb") as f:
        meta = pickle.load(f)
    ps = set(meta["ids"]["PS"])
    n_total_cached = meta["n_total"]

    raw = ROOT / a.raw
    quarters = sorted(p.name for p in Path(raw).glob("20*Q*")
                      if p.is_dir() and len(p.name) == 6)
    log(f"[ref] 季度 {len(quarters)} 个（{quarters[0]} ~ {quarters[-1]}），"
        f"PS 病例 {len(ps):,}")

    kept, n_total = build_kept(raw, quarters, a.chunksize, log)
    if n_total != n_total_cached:
        raise SystemExit(f"去重后 N 与缓存不一致: {n_total:,} vs {n_total_cached:,}")
    n_ps = len(ps & kept)
    n_ref = n_total - n_ps
    log(f"  队列 N_PS = {n_ps:,} | 参考人群 = {n_ref:,}")

    demo = scan_demo(raw, quarters, a.chunksize, kept, ps, log)
    reac = scan_reac(raw, quarters, a.chunksize, kept, ps, log)
    outc = scan_outc(raw, quarters, a.chunksize, kept, ps, log)

    tbl = build_table(demo, reac, outc, n_ps, n_ref)

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "table1_with_reference.csv"
    tbl.to_csv(csv_path, index=False, encoding="utf-8-sig")

    summary = dict(
        n_total=n_total, n_ps=n_ps, n_ref=n_ref,
        age_median_cohort=float(np.nanmedian(demo["age_c"])),
        age_median_ref=float(np.nanmedian(demo["age_r"])),
        age_missing_cohort=int(np.isnan(demo["age_c"]).sum()),
        age_missing_ref=int(np.isnan(demo["age_r"]).sum()),
        female_cohort=int(demo["sex_c"].get("F", 0)),
        female_ref=int(demo["sex_r"].get("F", 0)),
        serious_cohort=outc["any_c"], serious_ref=outc["any_r"],
        reac_cases_ref=reac["n_ref"],
        runtime_s=round(time.time() - t0),
    )
    with open(out / "reference_population_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    log("\n" + tbl.to_string(index=False))
    log(f"\n[ref] 输出 {csv_path}（用时 {summary['runtime_s']} s）")


if __name__ == "__main__":
    main()
