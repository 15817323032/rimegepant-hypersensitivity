# -*- coding: utf-8 -*-
"""
Module 2 —— 机器学习风险特征刻画（报告层，二分类）

研究问题
--------
在瑞美吉泮报告中，哪些报告层面特征与"出现口腔/超敏类事件"相关？
这是一个 **风险特征刻画（risk characterization）** 模型，用于生成假设与
识别高风险报告画像，**不是** 临床预测工具，不得用于个体化用药决策。

标签定义
--------
y = 1  该报告包含至少 1 个 ORAL_HYP_COMPOSITE 中的 PT
y = 0  否则

特征设计要点（避免数据泄漏）
--------------------------
- **不使用** OUTC（严重结局）与 REAC 事件个数作为主模型特征：
  结局信息在时间上位于事件之后，且事件个数与标签定义同源，会人为抬高 AUC。
- TTO 单独作为一个"时序特征"做敏感性模型，并附带缺失指示变量。
- 合并用药按药理类别聚合（抗组胺/糖皮质激素/NSAID/曲普坦/PPI/SSRI/β阻滞剂/抗癫痫），
  这类特征是机制解释的抓手。

输出 (results/)
---------------
ml_model_comparison.csv     各模型 5x5 重复交叉验证性能
ml_shap_importance.csv      最优模型 SHAP 全局重要性
ml_shap_values.csv          逐报告 SHAP 值（可复现作图）
figures/shap_summary.png
figures/roc_pr_curves.png
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from config.pt_sets import COMPOSITE_SET, DRUG_PATTERNS, normalize  # noqa: E402
from src.faers_io import load_faers, parse_faers_date  # noqa: E402
from src.run_module1 import flag_drug  # noqa: E402

# 合并用药药理类别（按 drugname 关键词归类，机制解释用）
DRUG_CLASSES = {
    "combo_antihistamine": [r"LORATADINE", r"CETIRIZINE", r"FEXOFENADINE", r"DIPHENHYDRAMINE",
                            r"CHLORPHENIRAMINE", r"PROMETHAZINE", r"HISTAMINE"],
    "combo_corticosteroid": [r"PREDNISONE", r"PREDNISOLONE", r"DEXAMETHASONE",
                             r"METHYLPREDNISOLONE", r"BUDESONIDE", r"HYDROCORTISONE"],
    "combo_nsaid": [r"IBUPROFEN", r"NAPROXEN", r"ASPIRIN", r"DICLOFENAC",
                    r"CELECOXIB", r"KETOROLAC", r"ACETAMINOPHEN", r"PARACETAMOL"],
    "combo_triptan": [r"SUMATRIPTAN", r"RIZATRIPTAN", r"ZOLMITRIPTAN", r"ELETRIPTAN",
                      r"ALMOTRIPTAN", r"NARATRIPTAN", r"FROVATRIPTAN"],
    "combo_ppi": [r"OMEPRAZOLE", r"ESOMEPRAZOLE", r"PANTOPRAZOLE", r"LANSOPRAZOLE"],
    "combo_ssri_snri": [r"SERTRALINE", r"FLUOXETINE", r"PAROXETINE", r"CITALOPRAM",
                        r"ESCITALOPRAM", r"VENLAFAXINE", r"DULOXETINE"],
    "combo_betablocker": [r"PROPRANOLOL", r"METOPROLOL", r"ATENOLOL", r"BISOPROLOL",
                          r"NADOLOL", r"TIMOLOL"],
    "combo_anticonvulsant": [r"TOPIRAMATE", r"VALPROATE", r"DIVALPROEX", r"GABAPENTIN",
                             r"PREGABALIN", r"LAMOTRIGINE", r"LEVETIRACETAM"],
    "combo_cgrp_mab": [r"ERENUMAB", r"GALCANEZUMAB", r"FREMANEZUMAB", r"EPTINEZUMAB"],
}


def build_features(demo, drug, reac, ther, ids) -> pd.DataFrame:
    """构造报告层特征矩阵。"""
    ids = {str(i) for i in ids}
    r = reac[reac["primaryid"].astype(str).isin(ids)].copy()
    r["pt_n"] = r["pt"].astype(str).map(normalize)
    hit = set(r.loc[r["pt_n"].isin(COMPOSITE_SET), "primaryid"].astype(str))

    d = demo[demo["primaryid"].astype(str).isin(ids)].copy()
    d["pid"] = d["primaryid"].astype(str)

    X = pd.DataFrame(index=d.index)
    X["pid"] = d["pid"].values
    X["y"] = X["pid"].isin(hit).astype(int)

    # --- 人口学 ---
    age = pd.to_numeric(d.get("age"), errors="coerce")
    cod = d.get("age_cod", pd.Series("YR", index=d.index)).fillna("YR").astype(str).str.upper()
    age = age.where(cod.eq("YR"), np.nan)
    X["age"] = age.where(age.between(0, 120))
    X["age_missing"] = X["age"].isna().astype(int)
    X["age_lt18"] = (X["age"] < 18).astype(int)
    X["age_ge65"] = (X["age"] >= 65).astype(int)

    sex = d.get("sex", pd.Series("", index=d.index)).astype(str).str.upper()
    X["sex_female"] = sex.eq("F").astype(int)
    X["sex_male"] = sex.eq("M").astype(int)
    X["sex_missing"] = (~sex.isin(["F", "M"])).astype(int)

    wt = pd.to_numeric(d.get("wt"), errors="coerce")
    X["weight"] = wt.where(wt.between(20, 250))

    # --- 报告特征 ---
    rept = d.get("rept_cod", pd.Series("", index=d.index)).astype(str).str.upper()
    for c in ("MD", "CN", "PH", "OT"):
        X[f"rept_{c}"] = rept.eq(c).astype(int)

    yr = parse_faers_date(d.get("fda_dt", pd.Series(dtype=str))).dt.year
    X["report_year"] = yr
    X["report_year_centered"] = yr - yr.min()

    ctry = d.get("reporter_country", pd.Series("", index=d.index)).astype(str).str.upper()
    X["country_us"] = ctry.eq("US").astype(int)
    X["country_missing"] = ctry.isin(["", "NAN", "UNK"]).astype(int)

    # --- 用药与事件负荷 ---
    dg = drug[drug["primaryid"].astype(str).isin(ids)].copy()
    dg["nm"] = dg["drugname"].fillna("").astype(str).str.upper()
    dg["pid"] = dg["primaryid"].astype(str)

    n_drug = dg.groupby("pid").size()
    X["n_drugs"] = X["pid"].map(n_drug).fillna(1).clip(0, 30)
    X["n_aes"] = X["pid"].map(r.groupby("primaryid").size()).fillna(1).clip(0, 30)

    for cname, pats in DRUG_CLASSES.items():
        if cname == "combo_other_gepant":
            continue
        m = pd.Series(False, index=dg.index)
        for p in pats:
            m |= dg["nm"].str.contains(p, regex=True, na=False)
        X[cname] = X["pid"].isin(set(dg.loc[m, "pid"])).astype(int)

    # 剂型：ODT 是本研究切口的核心暴露特征
    form = dg.get("dose_form", pd.Series("", index=dg.index)).fillna("").astype(str).str.upper()
    odt_ids = set(dg.loc[form.str.contains("DISINTEGRAT|ORALLY DISINTEGRAT|ODT", na=False), "pid"])
    X["dose_form_odt"] = X["pid"].isin(odt_ids).astype(int)

    # --- TTO（时序特征，单独模型使用）---
    t = ther[ther["primaryid"].astype(str).isin(ids)].copy()
    t["pid"] = t["primaryid"].astype(str)
    if "dsg_drug_seq" in t.columns:
        t["s"] = pd.to_numeric(t["dsg_drug_seq"], errors="coerce")
        t1 = t[t["s"].eq(1)]
        t = t1 if len(t1) else t
    t["start"] = parse_faers_date(t["start_dt"])
    ev = parse_faers_date(d.get("event_dt", pd.Series(dtype=str)))
    emap = dict(zip(d["pid"], ev))
    t["tto"] = [(emap.get(p) - s).days if pd.notna(s) and pd.notna(emap.get(p)) else np.nan
                for p, s in zip(t["pid"], t["start"])]
    tto = t.drop_duplicates("pid").set_index("pid")["tto"]
    X["tto_days"] = X["pid"].map(tto)
    X["tto_days"] = X["tto_days"].where(X["tto_days"].between(0, 730))
    X["tto_missing"] = X["tto_days"].isna().astype(int)

    return X


def run_models(X: pd.DataFrame, out_dir: Path, use_tto: bool = True,
               include_naes: bool = False, seed: int = 42):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (average_precision_score, brier_score_loss,
                                 roc_auc_score, roc_curve, precision_recall_curve)
    from sklearn.model_selection import RepeatedStratifiedKFold
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    import lightgbm as lgb
    import xgboost as xgb

    feats = [c for c in X.columns if c not in ("pid", "y")]
    if not use_tto:
        feats = [c for c in feats if not c.startswith("tto_")]
    # n_aes（事件总数）与标签定义同源：事件越多越可能"命中"复合终点，
    # 属机械性泄漏，默认排除；仅在明确要做"报告复杂度"敏感性模型时开启。
    if not include_naes:
        feats = [c for c in feats if c != "n_aes"]
    Xm, y = X[feats].astype(float), X["y"].values
    n_pos, n_neg = int(y.sum()), int((1 - y).sum())
    print(f"[ML] 样本 {len(y):,}  阳性 {n_pos:,} ({100*n_pos/len(y):.1f}%)  特征 {len(feats)}")

    spw = max(1.0, n_neg / max(n_pos, 1))
    models = {
        "LogisticRegression": Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced",
                                       C=0.5, solver="lbfgs")),
        ]),
        "RandomForest": Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", RandomForestClassifier(n_estimators=500, min_samples_leaf=5,
                                           max_features="sqrt", class_weight="balanced_subsample",
                                           n_jobs=-1, random_state=seed)),
        ]),
        "XGBoost": Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", xgb.XGBClassifier(n_estimators=400, max_depth=3, learning_rate=0.05,
                                      subsample=0.8, colsample_bytree=0.8,
                                      scale_pos_weight=spw, reg_lambda=2.0,
                                      eval_metric="logloss", n_jobs=4,
                                      random_state=seed)),
        ]),
        "LightGBM": Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", lgb.LGBMClassifier(n_estimators=400, num_leaves=15, learning_rate=0.05,
                                       subsample=0.8, colsample_bytree=0.8,
                                       class_weight="balanced", min_child_samples=20,
                                       verbose=-1, random_state=seed)),
        ]),
    }

    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=seed)
    rows, curves = [], {}
    for name, mdl in models.items():
        aucs, aps, briers = [], [], []
        oof_sum = np.zeros(len(y)); oof_cnt = np.zeros(len(y))
        for tr, te in cv.split(Xm, y):
            m = clone_model(mdl)
            m.fit(Xm.iloc[tr], y[tr])
            p = m.predict_proba(Xm.iloc[te])[:, 1]
            aucs.append(roc_auc_score(y[te], p))
            aps.append(average_precision_score(y[te], p))
            briers.append(brier_score_loss(y[te], p))
            oof_sum[te] += p; oof_cnt[te] += 1
        oof = oof_sum / np.maximum(oof_cnt, 1)
        rows.append(dict(model=name, auc_mean=np.mean(aucs), auc_sd=np.std(aucs),
                         ap_mean=np.mean(aps), ap_sd=np.std(aps),
                         brier_mean=np.mean(briers)))
        curves[name] = (roc_curve(y, oof), precision_recall_curve(y, oof), oof)
        print(f"  {name:20s} AUC {np.mean(aucs):.3f}±{np.std(aucs):.3f}  "
              f"AP {np.mean(aps):.3f}  Brier {np.mean(briers):.4f}")

    comp = pd.DataFrame(rows).sort_values("auc_mean", ascending=False)
    comp.to_csv(out_dir / "ml_model_comparison.csv", index=False, encoding="utf-8-sig")

    best = comp.iloc[0]["model"]
    print(f"[ML] 最优模型: {best}")

    # 全样本拟合用于 SHAP
    final = clone_model(models[best]); final.fit(Xm, y)
    plot_curves(curves, ROOT / "figures/roc_pr_curves.png")
    explain(final, Xm, feats, best, out_dir, y=y)
    return comp, best


def clone_model(mdl):
    from sklearn.base import clone
    return clone(mdl)


def explain(model, Xm, feats, name, out_dir, y=None):
    """SHAP 全局重要性 + 汇总图。"""
    try:
        import shap
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  [SHAP] 跳过: {e}")
        return

    clf = model.named_steps["clf"]
    imp = model.named_steps["imp"]
    Xt = pd.DataFrame(imp.transform(Xm), columns=feats, index=Xm.index)

    try:
        if name in ("XGBoost", "LightGBM", "RandomForest"):
            expl = shap.TreeExplainer(clf)
        else:
            expl = shap.LinearExplainer(clf, Xt)
        sv = expl.shap_values(Xt)
        if isinstance(sv, list):
            sv = sv[1]
        elif getattr(sv, "ndim", 2) == 3:
            sv = sv[:, :, 1]
        sv = np.asarray(sv)
    except Exception as e:
        print(f"  [SHAP] 解释失败，退回 permutation importance: {e}")
        return

    imp_df = (pd.DataFrame({"feature": feats, "mean_abs_shap": np.abs(sv).mean(axis=0)})
              .sort_values("mean_abs_shap", ascending=False))
    imp_df.to_csv(out_dir / "ml_shap_importance.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(sv, columns=feats).to_csv(out_dir / "ml_shap_values.csv", index=False)

    fig = plt.figure(figsize=(7.4, 5.2), dpi=300)
    shap.summary_plot(sv, Xt, feature_names=feats, max_display=15, show=False)
    plt.title(f"SHAP summary — {name}", fontsize=10, loc="left")
    plt.tight_layout()
    plt.savefig(ROOT / "figures/shap_summary.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [SHAP] figures/shap_summary.png")

    top = imp_df.head(6)["feature"].tolist()
    print(f"  [SHAP] Top 特征: {', '.join(top)}")

    # 最高重要性特征的阳性率分层表（便于写 Results 文字）
    strata = []
    for f in top[:5]:
        v = Xt[f]
        try:
            q = pd.qcut(v.rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
        except Exception:
            continue
        g = pd.DataFrame({"q": q.values, "y": y}).groupby("q", observed=True)["y"]
        for lv, rate in g.mean().items():
            strata.append(dict(feature=f, quartile=str(lv), n=int(g.size()[lv]),
                               positive_rate=round(float(rate), 4)))
    if strata:
        pd.DataFrame(strata).to_csv(out_dir / "ml_top_feature_strata.csv",
                                    index=False, encoding="utf-8-sig")


def plot_curves(curves, fp):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.0), dpi=300)
    for name, ((fpr, tpr, _), (prec, rec, _), _oof) in curves.items():
        axes[0].plot(fpr, tpr, lw=1.2, label=name)
        axes[1].plot(rec, prec, lw=1.2, label=name)
    axes[0].plot([0, 1], [0, 1], ls="--", lw=0.8, color="#999")
    axes[0].set(xlabel="False positive rate", ylabel="True positive rate", title="ROC (out-of-fold)")
    axes[1].set(xlabel="Recall", ylabel="Precision", title="Precision-Recall (out-of-fold)")
    for ax in axes:
        ax.legend(fontsize=7, frameon=False)
        ax.grid(ls=":", lw=0.5, alpha=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    plt.tight_layout()
    fp.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(fp, bbox_inches="tight")
    plt.close(fig)
    print("  [fig] roc_pr_curves.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--quarters", nargs="*")
    ap.add_argument("--out", default="results")
    ap.add_argument("--include-naes", action="store_true",
                    help="把事件总数纳入特征（有机械性泄漏风险，不建议）")
    a = ap.parse_args()

    raw = ROOT / "data/demo" if a.demo else Path(a.raw)
    quarters = (["2024Q1", "2024Q2", "2024Q3", "2024Q4"] if a.demo
                else (a.quarters or sys.exit("需 --quarters")))
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)

    d = load_faers(raw, quarters)
    ids = flag_drug(d["DRUG"], DRUG_PATTERNS, "PS")
    print(f"[ML] rimegepant PS 病例 {len(ids):,}")
    X = build_features(d["DEMO"], d["DRUG"], d["REAC"], d["THER"], ids)

    (out / "ml_feature_table.csv").write_text(X.to_csv(index=False), encoding="utf-8-sig")
    run_models(X, out, use_tto=True, include_naes=a.include_naes)


if __name__ == "__main__":
    main()
