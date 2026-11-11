# -*- coding: utf-8 -*-
"""
不成比例分析（disproportionality analysis）四算法实现

2x2 表约定（针对"目标药 × 目标PT"）：
                PT = p        PT != p      合计
  药 = d         a             b           a+b
  药 != d        c             d           c+d
  合计          a+c           b+d            N

四种算法与阳性判定阈值（均要求 a >= 3，即报告数下限）：
  1. ROR  : ROR = ad / bc ; ROR025 > 1                       （报告比值比）
  2. PRR  : PRR = a(c+d) / (c(a+b)) ; PRR >= 2 且 χ² >= 4      （比例报告比）
  3. BCPNN: IC = log2( a*N / ((a+b)(a+c)) ) ; IC025 > 0        （贝叶斯置信传播）
  4. MGPS : EBGM = (a+α)/(E+β) ; EB05 > 2                      （多项伽马泊松收缩）

关于 BCPNN 与 MGPS 的实现说明（必须在论文 Methods 中如实交代）
----------------------------------------------------------------
- ROR / PRR 为精确闭式公式，与文献完全一致。
- IC025 采用 delta 法近似：Var(ln ROR) = 1/a - 1/(a+b) + 1/c - 1/(c+d)
  （Rothman 标准式），再除以 (ln2)^2 换算到 log2 尺度，IC025 = IC - 1.96*SD。
  严格 BCPNN 需用 Norén 2006 的贝叶斯先验做后验积分，两者在 a>=3 时高度接近，
  但若审稿人要求，请用 R 包 PhViD::BCPNN 复核（见 docs/R_crosscheck.R）。
- EBGM 采用矩估计（method-of-moments）拟合 Gamma 先验的收缩估计，
  属 DuMouchel GPS 的简化实现；正式发表建议用 R 包 openEBGM 复核。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

Z = 1.959963984540054
LN2 = np.log(2.0)


# ---------------------------------------------------------------------------
# 单格计算
# ---------------------------------------------------------------------------
def ror(a: float, b: float, c: float, d: float):
    """ROR 及 95%CI（Haldane-Anscombe 校正避免零格）。"""
    a_, b_, c_, d_ = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    est = (a_ * d_) / (b_ * c_)
    se = np.sqrt(1 / a_ + 1 / b_ + 1 / c_ + 1 / d_)
    lo, hi = np.exp(np.log(est) - Z * se), np.exp(np.log(est) + Z * se)
    return est, lo, hi


def prr(a: float, b: float, c: float, d: float):
    """PRR 及 χ²（含 Yates 连续性校正）。"""
    # 全库量级下 2x2 表乘积可达 1e19 以上，先转 float 避免 int64 溢出
    a, b, c, d = float(a), float(b), float(c), float(d)
    n = a + b + c + d
    if a + b == 0 or c + d == 0:
        return np.nan, np.nan, np.nan
    est = (a / (a + b)) / (c / (c + d)) if c > 0 else np.inf
    lo, hi = np.nan, np.nan
    if a > 0 and c > 0:
        se = np.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
        lo, hi = np.exp(np.log(est) - Z * se), np.exp(np.log(est) + Z * se)
    # Yates 校正 χ²
    num = n * (abs(a * d - b * c) - n / 2) ** 2
    den = (a + b) * (c + d) * (a + c) * (b + d)
    chi2 = num / den if den > 0 else np.nan
    return est, chi2, lo


def bcpnn(a: float, b: float, c: float, d: float):
    """BCPNN: IC 与 IC025（delta 法近似，见模块 docstring）。"""
    n = a + b + c + d
    if min(a + b, a + c) == 0:
        return np.nan, np.nan
    ic = np.log2((a * n) / ((a + b) * (a + c))) if a > 0 else -np.inf
    if a == 0 or c == 0 or b == 0 or d == 0:
        a_, b_, c_, d_ = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    else:
        a_, b_, c_, d_ = a, b, c, d
    var_ln = 1 / a_ - 1 / (a_ + b_) + 1 / c_ - 1 / (c_ + d_)
    var_ic = max(var_ln, 0) / (LN2 ** 2)
    ic025 = ic - Z * np.sqrt(var_ic)
    return ic, ic025


def ebgm(a: float, b: float, c: float, d: float, alpha: float, beta: float):
    """Gamma-Poisson 收缩：EBGM 与 EB05。E = (a+b)(a+c)/N 为期望数。"""
    n = a + b + c + d
    e = (a + b) * (a + c) / n if n > 0 else np.nan
    if not np.isfinite(e) or e <= 0:
        return np.nan, np.nan
    eb = (a + alpha) / (e + beta)
    eb05 = stats.gamma.ppf(0.05, a + alpha, scale=1.0 / (e + beta))
    return eb, eb05


def fit_gamma_prior(rr: np.ndarray, trim_q=(0.01, 0.99)) -> tuple:
    """
    矩估计拟合 Gamma(α, β) 先验：
      观测 RR 近似服从 Gamma(α,β)（均值≈1，方差=1/α）。
    对极端值做分位裁剪以避免长尾污染方差估计。
    """
    rr = rr[np.isfinite(rr) & (rr > 0)]
    if rr.size < 100:
        return 0.5, 0.5          # 数据不足时的保守默认
    lo, hi = np.quantile(rr, trim_q)
    r = np.clip(rr, lo, hi)
    m, v = r.mean(), r.var()
    if m <= 0 or v <= m:
        return 0.5, 0.5
    alpha = m ** 2 / (v - m)
    beta = m / (v - m)
    alpha = float(np.clip(alpha, 0.05, 50))
    beta = float(np.clip(beta, 0.05, 50))
    return alpha, beta


# ---------------------------------------------------------------------------
# 批量：目标药 × 全部 PT
# ---------------------------------------------------------------------------
def compute_all_signals(drug_ids: set, reac: pd.DataFrame, n_total: int,
                        min_reports: int = 3,
                        gamma_prior: tuple | None = None) -> pd.DataFrame:
    """
    对目标药报告集合与全部 PT 做四算法计算。

    drug_ids : 目标药相关的 primaryid 集合（已按 role_cod 过滤）
    reac     : 去重后的 REAC 表（primaryid, pt）
    n_total  : 去重后总病例数 N
    返回按 ROR025 降序的信号表
    """
    reac = reac.copy()
    reac["pt"] = reac["pt"].astype(str).str.strip().str.upper()
    reac = reac[reac["pt"].ne("") & reac["pt"].ne("NAN")]

    # 每个病例的 PT 去重（同一病例同一 PT 只计一次）
    reac_u = reac.drop_duplicates(subset=["primaryid", "pt"])

    drug_mask = reac_u["primaryid"].astype(str).isin({str(i) for i in drug_ids})
    a_s = reac_u.loc[drug_mask].groupby("pt").size()              # a
    c_s = reac_u.loc[~drug_mask].groupby("pt").size()             # c

    n_drug = len({str(i) for i in drug_ids})
    pt_total = pd.DataFrame({"a": a_s}).join(
        pd.DataFrame({"c": c_s}), how="outer").fillna(0).sum(axis=1)
    return compute_signals_from_counts(a_s, pt_total, n_drug, n_total,
                                       min_reports=min_reports,
                                       gamma_prior=gamma_prior)


def compute_signals_from_counts(a_s: pd.Series, pt_total: pd.Series,
                                n_drug: int, n_total: int,
                                min_reports: int = 3,
                                gamma_prior: tuple | None = None) -> pd.DataFrame:
    """
    由「已聚合计数」直接算四算法信号（流式读取用，避免载入全量 REAC）。

    a_s      : 目标药病例中各 PT 的报告数（病例内同一 PT 已去重）
    pt_total : 全库各 PT 的报告数（含目标药）
    n_drug   : 目标药病例数
    n_total  : 全库去重病例数
    """
    tbl = pd.DataFrame({"a": a_s}).join(
        pd.DataFrame({"tot": pt_total}), how="outer").fillna(0).astype(int)
    tbl = tbl[tbl["a"] >= min_reports].copy()

    tbl["c"] = tbl["tot"] - tbl["a"]
    tbl["b"] = n_drug - tbl["a"]
    tbl["c_total"] = tbl["c"]
    tbl["d"] = n_total - tbl["a"] - tbl["b"] - tbl["c"]
    tbl = tbl[["a", "b", "c", "d", "c_total"]]

    if gamma_prior is None:
        # 用全部 PT 的粗 RR 拟合先验
        coarse = ((tbl["a"] + 0.5) / (tbl["b"] + 0.5)) / \
                 ((tbl["c"] + 0.5) / (tbl["d"] + 0.5))
        gamma_prior = fit_gamma_prior(coarse.values)
    alpha, beta = gamma_prior

    recs = []
    for pt, r in tbl.iterrows():
        a, b, c, d = r["a"], r["b"], r["c"], r["d"]
        ror_v, ror_lo, ror_hi = ror(a, b, c, d)
        prr_v, chi2, prr_lo = prr(a, b, c, d)
        ic, ic025 = bcpnn(a, b, c, d)
        eb, eb05 = ebgm(a, b, c, d, alpha, beta)
        recs.append((pt, a, b, c, d, ror_v, ror_lo, ror_hi,
                     prr_v, chi2, prr_lo, ic, ic025, eb, eb05))

    out = pd.DataFrame(recs, columns=[
        "PT", "a", "b", "c", "d", "ROR", "ROR025", "ROR975",
        "PRR", "chi2", "PRR025", "IC", "IC025", "EBGM", "EB05"])

    # 阳性判定（四种算法分别标注 + 满足其一/满足其二）
    out["sig_ROR"] = (out["ROR025"] > 1) & (out["a"] >= min_reports)
    out["sig_PRR"] = (out["PRR"] >= 2) & (out["chi2"] >= 4) & (out["a"] >= min_reports)
    out["sig_BCPNN"] = (out["IC025"] > 0) & (out["a"] >= min_reports)
    out["sig_MGPS"] = (out["EB05"] > 2) & (out["a"] >= min_reports)
    out["n_algo"] = out[["sig_ROR", "sig_PRR", "sig_BCPNN", "sig_MGPS"]].sum(axis=1)
    out["is_signal"] = out["n_algo"] > 0
    out["is_robust_signal"] = out["n_algo"] >= 2

    # Benjamini-Hochberg FDR（以 χ² 转 p 值）
    from statsmodels.stats.multitest import multipletests
    p = np.asarray(stats.chi2.sf(out["chi2"].fillna(0).to_numpy(dtype=float), df=1))
    out["p_value"] = p
    out["q_BH"] = multipletests(p, method="fdr_bh")[1]
    out = out.sort_values(["ROR025", "a"], ascending=False).reset_index(drop=True)
    out.attrs["gamma_prior"] = (alpha, beta)
    return out
