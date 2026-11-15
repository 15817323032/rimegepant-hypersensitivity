# 作图源数据包 — Rimegepant 口腔/超敏信号研究

**生成日期**：{{DATE}}
**对应稿件**：Rimegepant ODT 口腔与超敏相关不良事件的药物警戒研究（Drug Safety 投稿版）
**数据窗口**：FAERS/AEMS 2020Q2–2026Q2（25 个季度），primary-suspect 角色去重报告 8,962 例

本包把 4 张投稿正文图与 1 张补充图背后的**绘图数值**按图拆开整理，任何人拿到 CSV 就能复算图上的每一个点、每一条误差线，不必重新跑 FAERS 全库。

> **2026-11-15 变更**：原正文 Figure 3（ROC/PR 曲线）移为**补充材料图 S1**；Figure 4（SHAP）顺移为 Figure 3、Figure 5（网络毒理）顺移为 Figure 4。Table 7 相应增加 Null 基线行，Brier 分数改为先验校正口径（详见 `SuppS1_model_performance.csv` 两列对比）。

---

## 1. 目录结构

```
figure_data_package/
├── README.md                       ← 本文件（数据字典 + 复现说明）
├── figure_source_data.xlsx         ← 汇总 sheet，供快速翻阅
├── figures/                        ← 投稿用成品图（300 dpi PNG，与投稿包完全一致）
│   ├── Figure_1_forest_focus.png
│   ├── Figure_2_label_change_trend.png
│   ├── Figure_3_shap_summary.png
│   ├── Figure_4_network_tox.png
│   └── Supplementary_Figure_S1_roc_pr_curves.png
├── source_data/                    ← 每张图实际绘制的数值
│   ├── Fig1_forest_focus.csv
│   ├── Fig2a_family_pre_post.csv
│   ├── Fig2b_PT_detail.csv
│   ├── Fig2c_quarterly_family.csv
│   ├── Fig3a_shap_importance.csv
│   ├── Fig3b_top_feature_strata.csv
│   ├── Fig3c_shap_values_per_report.csv
│   ├── Fig4_network/               ← 9 个文件（桥接基因、KEGG/GO、PPI hub 等）
│   └── SuppS1_model_performance.csv
└── code/                           ← 生成上述数据与图的流水线脚本（只读参考）
    ├── run_module1.py   (Fig 1 森林图)
    ├── label_change.py  (Fig 2 标签修订前后趋势)
    ├── ml_risk.py       (Fig 3 SHAP + 补充图 S1 ROC/PR)
    └── network_tox.py   (Fig 4 桥接网络毒理)
```

---

## 2. 图—数据—脚本 对照

| 图 | 画的是什么 | 数据文件 | 生成脚本 |
|---|---|---|---|
| **Fig 1** | 口腔/超敏焦点簇阳性信号的 ROR 森林图（点 = ROR，横线 = 95% CI，竖虚线 = ROR 1） | `Fig1_forest_focus.csv` | `code/run_module1.py` |
| **Fig 2** | 六个超敏家族按季度的报告占比，虚线 = 2025-08 标签修订（2025Q3 断点） | `Fig2a` + `Fig2c`（家族与季度）；`Fig2b` 为 49 个 PT 的明细 | `code/label_change.py` |
| **Fig 3** | 最优模型（随机森林）的 SHAP summary，23 个特征按全局重要性排序（正文图） | `Fig3a`（重要性）+ `Fig3c`（逐报告 SHAP 值）+ `Fig3b`（分层阳性率） | `code/ml_risk.py` |
| **Fig 4** | 桥接网络毒理总览：药物锚点 → 桥接基因 → 事件模块 → KEGG 富集 | `Fig4_network/*` | `code/network_tox.py` |
| **Supp Fig S1** | 4 个模型的 ROC（左）与 PR（右）曲线 + Null 基线，重复分层 5 折 × 3（补充材料） | `SuppS1_model_performance.csv` | `code/ml_risk.py` |

---

## 3. 数据字典

### Fig 1 — `Fig1_forest_focus.csv`（25 行 = 图上 25 个点）

焦点簇共 49 个 PT，绘图代码取 **ROR 最高的 25 个**进入森林图；其中 19 个为阳性信号（`is_signal = TRUE`），全部在图内。

| 列 | 含义 |
|---|---|
| `PT` | MedDRA 首选语（Preferred Term） |
| `n_reports_case` | 该 PT 在 rimegepant 队列中的报告数（a 格） |
| `n_reports_nondrug` | 全库其他药物的该 PT 报告数（c 格） |
| `ROR` / `ROR_95CI_low` / `ROR_95CI_high` | 报告比值比及 95% 置信区间——**图上点的位置与横线** |
| `PRR` | 比例报告比 |
| `IC025` | BCPNN 信息成分下界 |
| `EB05` | MGPS 经验贝叶斯几何均值下界 |
| `n_algorithms_positive` | 四种算法（ROR/PRR/BCPNN/MGPS）中判为阳性的个数（0–4） |
| `is_signal` | 达到阳性信号判据（主稿 §3.2 的"19 个阳性信号"即此列计数） |
| `robust_signal` | 四算法全阳（`n_algorithms_positive = 4`）→ 图上红点；否则深蓝 |
| `severity_tier` | 严重度分层（`tier1_local` = 局部黏膜/口咽表现等） |
| `cluster_subset` | 焦点簇内的亚组归属（`CORE_ORAL`、`SENSORY` 等） |

### Fig 2 — 标签修订前后

**`Fig2a_family_pre_post.csv`**（6 行 = 六个超敏家族）

| 列 | 含义 |
|---|---|
| `family` | 家族名：Anaphylactoid / Systemic hypersensitivity / Oral mucosal / Oral sensory / Pharyngeal/airway / Excipient reaction |
| `pre_cases` / `post_cases` | 修订前（2020Q2–2025Q2）、修订后（2025Q3–2026Q2）该家族报告数 |
| `pre_pct` / `post_pct` | 相应占比（分母为该期总报告数） |
| `pre_ci_lo` / `pre_ci_hi` / `post_ci_lo` / `post_ci_hi` | Wilson 95% CI |
| `ratio_post_vs_pre` / `ratio_lo` / `ratio_hi` | 前后占比比及 95% CI |
| `p_fisher` | Fisher 精确检验 p 值（六家族全部无显著上升 → 排除 notoriety bias） |

**`Fig2c_quarterly_family.csv`**（25 行 = 25 个季度，Fig 2 折线的 X 轴）

| 列 | 含义 |
|---|---|
| `quarter` | 季度标签（`2020Q2` … `2026Q2`） |
| `n` | 该季度队列报告总数（占比的分母） |
| `Anaphylactoid` … `Excipient reaction` | 各家族该季度报告数（6 列） |
| `total` | 六家族合计 |
| `*_pct` | 各家族占 `n` 的百分比（6 列）——**折线的 Y 值** |

**`Fig2b_PT_detail.csv`**（49 行）：修订前后逐 PT 的计数、占比、比值与 Fisher p，用于补充材料与文字描述。

### Fig 3 — SHAP（正文图）

**`Fig3a_shap_importance.csv`**（23 行 = 23 个特征）：`feature` + `mean_abs_shap`（全局重要性，Fig 3 的排序依据）。
**`Fig3c_shap_values_per_report.csv`**（8,962 行 × 23 列）：每份报告每个特征的 SHAP 值，即 Fig 3 每个点的横坐标。
**`Fig3b_top_feature_strata.csv`**：Top 5 特征的 SHAP 四分位分层阳性率（如 `sex_female` Q4 12.9% vs Q1 6.2%，图底部标注即来自此表）。

### Fig 4 — `Fig4_network/`

| 文件 | 内容 |
|---|---|
| `Fig4a_bridge_genes.csv` | 91 个桥接基因：`gene`、`bridge_count`（桥接路径数）、`min_hops`（最小跳数）、`connects`（连接的事件基因）、`in_ae_set` |
| `Fig4b_KEGG_enrichment.csv` | KEGG 富集 25 条：`term`、`p_value`、`adj_p_value`、`combined_score`、`n_overlap`、`genes` |
| `Fig4c_GO_BP_enrichment.csv` | GO-BP 富集 25 条，列同上 |
| `Fig4d_PPI_hubs.csv` | 366 个节点的 `degree` 与 `betweenness_proxy` |
| `Fig4e_adverse_event_gene_sets.csv` | 1,090 行事件基因集（`source`、`pathway`、`rationale`、`gene`），网络构建的输入 |
| `Fig4f/g/h` | 预测靶点、实测靶点、交集基因 |
| `Fig4i_drug_info.json` | 药物锚点信息（CALCRL/RAMP1/CALCA）与 ChEMBL 标识 |

### Supplementary Fig S1 — `SuppS1_model_performance.csv`（5 行 = 4 个模型 + Null 基线）

| 列 | 含义 |
|---|---|
| `model` | RandomForest / LogisticRegression / XGBoost / LightGBM / Null (prevalence) |
| `AUC_mean` / `AUC_SD` | 重复分层 5 折 × 3 的 ROC 曲线下面积均值 ± 标准差（主稿 Table 7 的 0.621 ± 0.015 即 RandomForest 行） |
| `AP_mean` / `AP_SD` | PR 曲线平均精度（阳性率约 10%，故 AP 贴近基线是预期结果） |
| `Brier_prior_corrected` | **投稿表采用的 Brier 分数**：概率先经先验还原（类别权重会把预测概率均值拉到 ~0.42，真实发生率 0.104） |
| `Brier_raw_balanced_weights` | 未做先验还原的原始 Brier（仅供核查；不能与 Null 行直接比较） |

> **关于曲线坐标**：ROC/PR 的逐点坐标由 `ml_risk.py` 内部的 out-of-fold 预测概率即时算出并直接绘入 PNG，未单独落盘。本包提供曲线对应的 AUC/AP/Brier 数值依据；若需逐点坐标，用 `code/ml_risk.py` 重跑即可（随机种子固定，结果可复现）。

---

## 4. 复现

环境：Python 3.11 + `requirements.txt`（pandas / numpy / matplotlib / scikit-learn / shap / openpyxl）。

```bash
# 图 1：森林图（输入 results/table3_focus_signals.csv）
python src/run_module1.py

# 图 2：标签修订前后（输出 results_label_change/）
python src/label_change.py

# 图 3 + 补充图 S1：SHAP 与 ML 曲线（需 data/raw 原始 FAERS 解压文件）
python src/ml_risk.py --raw data/raw

# 图 4：网络毒理（输出 results/network_tox/）
python src/network_tox.py
```

绘图参数（已固定在脚本内，便于逐字复现）：matplotlib `Agg` 后端，`dpi=300`，`bbox_inches="tight"`；Fig 1 图幅 7.2 in 宽、行高 0.28 in；Supp Fig S1 双栏 9.6 × 4.0 in；Fig 3 SHAP 7.4 × 5.4 in，`max_display=15`，图底部标注 Top/Bottom 四分位阳性率。

---

## 5. 口径说明（复算时容易踩的坑）

1. **Fig 1 的 ROR 来自 primary-suspect 去重队列**（8,962 例），不是全库报告口径；对照格为全库 `9,085,192` 例中的非该药报告。复算时注意：ROR/PRR/IC 均带 **Haldane-Anscombe 0.5 校正**（四格各加 0.5 再代入公式），直接用原始四格算会和表内差约 1–2%。
2. **Fig 2 的分母是季度队列总数 `n`**，不是全库；占比因此反映「药物内部构成变化」，这正是要检验的标签效应信号。
3. **Fig 2 的断点定在 2025Q3**，因标签修订公告于 2025-08（FDA 信号清单改版同期），Q3 起为修订后窗口。
4. **Supp Fig S1 的 AUC 全部来自 out-of-fold 预测**，无信息泄漏；四模型共用同一折划分与同一特征矩阵。Null 行的 Brier = 基率 ×（1 − 基率）= 0.0932；四个模型的先验校正 Brier 为 0.0911–0.0927，即模型相对常数预测的净增益 ≤ 0.002——这是主稿"报告层特征不足以分层"结论的数值依据。
5. **Fig 3 的 SHAP 值基于随机森林 TreeExplainer**，`mean_abs_shap` 已按 23 个特征完整排序，与主稿 §3.3 的排序一致（最大 0.030）。
6. **Fig 4 的桥接基因按 `bridge_count` 降序**；KEGG/GO 用 `adj_p_value`（BH 校正）判读，不要只看 `p_value`。

---

## 6. 与投稿包的一致性

本包中的 4 张正文图 PNG 与 `submission_drugsafety/figures/Figure_1..4.png`、补充图与 `submission_drugsafety/Supplementary_Figure_S1.png` **逐字节相同**（同一份文件复制）。若日后修改数据，请先重跑流水线，再执行 `python tools/make_submission.py` 更新投稿包，避免图文不一致。
