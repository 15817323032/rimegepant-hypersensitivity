# -*- coding: utf-8 -*-
"""
生成 FAERS ASCII 格式的合成演示数据（用于流水线自检，非真实数据！）

用途
----
真实 FAERS 完整库约 30-60 GB，下载+去重耗时数小时。本脚本生成一套
**格式完全一致**的小规模数据（默认 6 万例、4 个季度），并人为植入
口腔/超敏信号，使 Module 1-2 可在几分钟内端到端跑通、验证代码正确性。

⚠️ 生成的数据为随机模拟，任何数值结果均无科学意义，仅用于调试。
   正式分析请把 data/raw/ 换成官方 aers_ascii_*.zip 解压内容。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.pt_sets import ORAL_HYP_COMPOSITE, INDICATION_PTS  # noqa: E402

RNG = np.random.default_rng(20261110)

# 背景 PT 池（近似真实 FAERS 的高频事件分布）
BACKGROUND_PTS = [
    ("NAUSEA", 60), ("HEADACHE", 55), ("DIZZINESS", 40), ("FATIGUE", 38),
    ("VOMITING", 30), ("DIARRHOEA", 28), ("INSOMNIA", 25), ("ANXIETY", 24),
    ("PAIN", 30), ("ARTHRALGIA", 20), ("BACK PAIN", 22), ("RASH", 18),
    ("PRURITUS", 16), ("PYREXIA", 15), ("COUGH", 14), ("DYSPNOEA", 14),
    ("ABDOMINAL PAIN", 20), ("CONSTIPATION", 18), ("SOMNOLENCE", 16),
    ("PARAESTHESIA", 15), ("MUSCLE SPASMS", 12), ("HYPERTENSION", 13),
    ("OEDEMA PERIPHERAL", 11), ("WEIGHT DECREASED", 10), ("ALOPECIA", 10),
    ("DRUG INEFFECTIVE", 45), ("PRODUCT DOSE OMISSION", 12),
    ("MIGRAINE", 50), ("PHOTOPHOBIA", 20), ("PHONOPHOBIA", 16),
    ("PALPITATIONS", 12), ("TREMOR", 10), ("DEPRESSED MOOD", 12),
    ("VISION BLURRED", 12), ("DRY MOUTH", 14), ("ABDOMINAL DISCOMFORT", 11),
    ("FEELING ABNORMAL", 13), ("MOTION SICKNESS", 8), ("FEELING DRUNK", 7),
    ("CHILLS", 10), ("NASOPHARYNGITIS", 9), ("URINARY TRACT INFECTION", 9),
    ("PROTEINURIA", 8), ("BLOOD ALANINE AMINOTRANSFERASE INCREASED", 7),
    ("SINUSITIS", 8), ("MYALGIA", 9), ("NECK PAIN", 8), ("TINNITUS", 7),
    ("RAYNAUD'S PHENOMENON", 5), ("ATRIAL FIBRILLATION", 4),
]

# 植入的"真信号"：rimegepant 报告中出现频率被人为抬高
PLANTED = [
    ("SWOLLEN TONGUE", 8.0), ("PARAESTHESIA ORAL", 7.0),
    ("PHARYNGEAL SWELLING", 6.0), ("ANAPHYLACTIC REACTION", 3.0),
    ("REACTION TO EXCIPIENT", 5.0), ("DYSGEUSIA", 4.0),
    ("LIP SWELLING", 4.0), ("THROAT TIGHTNESS", 4.0),
    ("URTICARIA", 3.5), ("ANGIOEDEMA", 2.5), ("TONGUE DISORDER", 3.0),
]

OTHER_DRUGS = [
    ("TOPIRAMATE", 0.12), ("ERENUMAB", 0.10), ("UBROGEPANT", 0.08),
    ("SUMATRIPTAN", 0.14), ("PROPRANOLOL", 0.09), ("AMITRIPTYLINE", 0.08),
    ("GABAPENTIN", 0.08), ("METOPROLOL", 0.07), ("SERTRALINE", 0.07),
    ("OMEPRAZOLE", 0.07), ("ATORVASTATIN", 0.05), ("LEVOTHYROXINE", 0.05),
]

COUNTRIES = [("US", 0.62), ("GB", 0.06), ("JP", 0.05), ("DE", 0.05),
             ("FR", 0.04), ("CA", 0.04), ("CN", 0.03), ("IT", 0.03),
             ("ES", 0.03), ("AU", 0.03), ("BR", 0.02)]


def _pick(names_weights, n):
    nms = [x[0] for x in names_weights]
    w = np.array([x[1] for x in names_weights], dtype=float)
    return RNG.choice(nms, size=n, p=w / w.sum())


def _date_range(start="2020-01-01", end="2026-06-30", n=1):
    s = pd.Timestamp(start).value // 10 ** 9
    e = pd.Timestamp(end).value // 10 ** 9
    ts = RNG.integers(s, e, size=n)
    return pd.to_datetime(ts, unit="s")


def generate(out_dir: Path, n_total: int = 60000, n_rime: int = 900,
             quarters=("2024Q1", "2024Q2", "2024Q3", "2024Q4"),
             seed: int = 20261110):
    global RNG
    RNG = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = {"DEMO": [], "DRUG": [], "REAC": [], "OUTC": [], "INDI": [], "THER": []}
    pid = 100000000
    caseid = 50000000

    for qi, _q in enumerate(quarters):
        n_case = n_total // len(quarters)
        n_rime_q = n_rime // len(quarters)
        is_rime = np.zeros(n_case, dtype=bool)
        is_rime[:n_rime_q] = True
        RNG.shuffle(is_rime)

        for i in range(n_case):
            pid += RNG.integers(1, 40)
            caseid += RNG.integers(1, 9)
            rime = bool(is_rime[i])

            fda_dt = _date_range(f"2024-{(qi*3)+1:02d}-01",
                                 f"2024-{(qi*3)+3:02d}-28", 1)[0]
            event_dt = fda_dt - pd.Timedelta(days=int(RNG.integers(1, 400)))
            age = int(np.clip(RNG.normal(42, 14), 12, 88))
            sex = RNG.choice(["F", "M"], p=[0.78, 0.22])
            country = _pick(COUNTRIES, 1)[0]
            rept = RNG.choice(["MD", "CN", "PH", "OT"], p=[0.35, 0.30, 0.20, 0.15])

            rows["DEMO"].append(dict(
                primaryid=pid, caseid=caseid, caseversion=1,
                fda_dt=fda_dt.strftime("%Y%m%d"),
                event_dt=event_dt.strftime("%Y%m%d"),
                rept_cod=rept, age=age, age_cod="YR", age_grp="A",
                sex=sex, wt=round(float(RNG.normal(72, 15)), 1), wt_cod="KG",
                reporter_country=country, occp_cod=rept,
                rept_dt=fda_dt.strftime("%Y%m%d"),
                init_fda_dt=fda_dt.strftime("%Y%m%d"), mfr_sndr="DEMO",
                _quarter=_q,
            ))

            # ---- DRUG ----
            ds = 1
            if rime:
                rows["DRUG"].append(dict(
                    primaryid=pid, caseid=caseid, drug_seq=ds, role_cod="PS",
                    drugname="NURTEC ODT", prod_ai="RIMEGEPANT SULFATE",
                    route="ORAL", dose_vbm="75 MG", dose_form="TABLET, ORALLY DISINTEGRATING",
                    dose_freq="QD", nda_num="212728", _quarter=_q))
                ds += 1
            for dname in _pick(OTHER_DRUGS, int(RNG.integers(0, 4))):
                rows["DRUG"].append(dict(
                    primaryid=pid, caseid=caseid, drug_seq=ds,
                    role_cod=RNG.choice(["C", "I", "SS"], p=[0.8, 0.1, 0.1]),
                    drugname=dname, prod_ai=dname, route="ORAL",
                    dose_vbm="", dose_form="TABLET", dose_freq="", nda_num="",
                    _quarter=_q))
                ds += 1

            # ---- REAC ----
            n_ae = int(np.clip(RNG.poisson(2.2 if not rime else 2.8), 1, 8))
            pts = set()
            # 背景事件
            while len(pts) < n_ae:
                pts.add(_pick(BACKGROUND_PTS, 1)[0])
            # 植入信号：rimegepant 报告按权重额外抽 0-2 个
            if rime:
                k = RNG.choice([0, 1, 2], p=[0.45, 0.40, 0.15])
                for p_ in _pick([(a, b) for a, b in PLANTED], k):
                    pts.add(p_)
            for p_ in pts:
                rows["REAC"].append(dict(primaryid=pid, caseid=caseid, pt=p_,
                                         drug_rec_act="", _quarter=_q))

            # ---- INDI ----
            if rime:
                rows["INDI"].append(dict(primaryid=pid, caseid=caseid,
                                         indi_pt="MIGRAINE", indi_drug_seq=1,
                                         _quarter=_q))
            for j in range(2, ds):
                rows["INDI"].append(dict(primaryid=pid, caseid=caseid,
                                         indi_pt=RNG.choice(["HEADACHE", "MIGRAINE",
                                                             "HYPERTENSION", "PAIN"]),
                                         indi_drug_seq=j, _quarter=_q))

            # ---- OUTC ----
            n_out = int(RNG.integers(0, 3))
            for oc in RNG.choice(["HO", "LT", "DS", "RI", "OT"], n_out,
                                 p=[0.35, 0.15, 0.15, 0.1, 0.25]):
                rows["OUTC"].append(dict(primaryid=pid, caseid=caseid,
                                         outc_cod=oc, _quarter=_q))

            # ---- THER ----
            start = event_dt - pd.Timedelta(days=int(RNG.integers(1, 180)))
            rows["THER"].append(dict(primaryid=pid, caseid=caseid, dsg_drug_seq=1,
                                     start_dt=start.strftime("%Y%m%d"), end_dt="",
                                     dur="", dur_cod="", _quarter=_q))

    # ---- 写出（FAERS ASCII 格式：$ 分隔 + 行尾 $ + 表头）----
    written = []
    for tbl, recs in rows.items():
        df = pd.DataFrame(recs)
        if df.empty:
            continue
        for q, g in df.groupby("_quarter"):
            g = g.drop(columns=["_quarter"])
            fp = out_dir / f"{tbl}{q[2:4]}Q{q[-1]}.txt"   # 如 DEMO24Q1.txt（对齐官方命名）
            with fp.open("w", encoding="latin-1", newline="") as f:
                f.write("$".join(g.columns) + "$\n")
                for rec in g.itertuples(index=False):
                    vals = ["" if pd.isna(v) else str(v) for v in rec]
                    f.write("$".join(vals) + "$\n")
            written.append(fp)
    print(f"[DEMO] 已生成 {len(written)} 个文件 -> {out_dir}")
    print(f"[DEMO] 总病例 {n_total:,}，其中 rimegepant {n_rime}；"
          f"植入信号 {len(PLANTED)} 个")
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/demo")
    ap.add_argument("--n", type=int, default=60000)
    ap.add_argument("--n-rime", type=int, default=900)
    a = ap.parse_args()
    generate(Path(__file__).resolve().parent.parent / a.out, a.n, a.n_rime)
