# 表格 / 图件契约与结果段写作规范

> 适用：Drug Safety 投稿稿（rimegepant FAERS）。两类问题分别治：
> **表/图内容错** → 契约 + 交付级校验（`tools/audit_tables.py`）；
> **结果写法不统一** → 数值格式规约 + 句式模板 + `tools/check_results_style.py`。
> 一句话原则：**校验对象必须是交付对象**，不是中间产物。

---

## 一、表格契约（真源 + 不变量）

⚠️ **文件名与表号错位**是最大的坑：表 2 的真源叫 `table3_focus_slim`，表 3 的叫 `table4_tto`，
表 4 的叫 `table5_subgroup`。**改表前先查本表，不要按文件名猜。**

| 表 | 真源（文件 + sheet） | 关键不变量 |
|---|---|---|
| Table 1 | `results_full/table1_with_reference.csv` | 三列分母不同（全库/指示匹配/队列）；年龄、性别分母=有记录者 |
| Table 2 | `results_full/table3_focus_slim.xlsx` → `table3_focus_slim` | 按 ROR 降序；a ≥ 3；robust = ≥2/4 算法；49 簇内 19 阳性、18 robust |
| Table 3 | `results_full/all_tables.xlsx` → **`table4_tto`** | 分箱固定 `0 / 1 / 2–7 / 8–30 / 31–90 / >90` 天；0 天 ≠ 1 天，不得合并 |
| Table 4 | `results_full/all_tables.xlsx` → `table5_subgroup` | 亚组方向一致性；Wilson 95% CI |
| Table 5 | `results_full/all_tables.xlsx` → `table6_sensitivity` | 三暴露角色 PS / PS+SS / ALL |
| Table 6 | `results_full/all_tables_full.xlsx` → `T7_ML_models` | 23 特征；5×3 CV；null AUC 0.500 |
| Table 7 | `results/network_tox/bridge_genes.csv` | bridge_count 可重复计数；in_ae_set 0/1 |
| Table 8 | `results_full/all_tables_supplement.xlsx` → `T11_docking` | Δ = 目标 − CALCRL；阈值 2 kcal/mol |
| Table 9 | `results_full/all_tables_full.xlsx` → `T12_label_prepost` | 主分析排除 2025Q3；q 值跨 6 家族 BH |
| Table 10 | `results_full/table13_bridge_assignment.csv` | 模块归属为 curated，不是机制结论 |
| S1 | READUS-PV checklist（正文条目 + 标题同步） | 条目 4b/8a 引 Supplementary Fig S2 |
| S2 | 438 行 PT 全表（`all_tables` 相关 sheet） | a ≥ 3；BH q 仅描述性 |
| S3 | `results_ml_real/ml_shap_importance.csv` | 23 特征（敏感性 21） |
| S4 | KEGG enrichment（`results/` 对应文件） | q 值科学计数法 |

## 二、图件契约

| 图 | 内容 | 唯一渲染目录 | 不变量 |
|---|---|---|---|
| Fig 1 | 核心信号 forest plot | `figures_r/` | 10 个核心信号；ROR + 95% CI |
| Fig 2 | 季度趋势 small multiples | `figures_r/` | 共享 0–40 轴；2025Q3 着色；Wilson 区间 + 分母 |
| Fig 3 | SHAP 重要性 + 分布 | `figures_r/` | top 15 of 21 非冗余特征（23 主模型 −2 镜像/重复） |
| Fig 4 | 网络毒理三联图（ChEMBL） | `figures_r/` | KEGG 富集 q 值；基因数不变 |
| Supp Fig S1 | ROC / PR 曲线 | `figures_r/` | 四模型 + null |
| Supp Fig S2 | 病例流程图 | `tools/make_flow_diagram.py` | 数字与 8,962 / 848 / 1,060 对账 |

**铁律**：
1. 渲染产物只允许一个目录（`figures_r/`），打包脚本只从这里复制；
2. `presubmit_check.py` 做 Fig1–4 + S1 与 `figures_r/` 的**字节级**比对；
3. 删掉或永不引用任何旧渲染路径（曾因 `results_label_change/` 残留导致 Fig 2 裁切两次复发）。

## 三、数值格式规约（结果段强制）

| 项目 | 规则 | 示例 |
|---|---|---|
| p 值 | ≥0.01 用 2 位；<0.01 用 3 位或科学计数；永不写 `p = 0.000` | `p = 0.18`、`p = 0.009` |
| q 值 | ≥0.001 用 3 位；更小用科学计数 | `q = 0.056`、`q = 6.9e-127` |
| 百分比 | 1 位小数；<0.1% 可 2 位 | `59.6%`、`3.1%` |
| 比值（ROR/PRR/post-pre） | 2 位 + 95% CI | `2.28 (95% CI 1.21–4.31)` |
| AUC | 3 位 + `± SD` + **必须点明模型变体** | `0.621 ± 0.015 (full 23-feature model)` |
| 对接 ΔG | 2 位 + 单位；Δ 用 U+2212 | `−8.45 kcal/mol`、`Δ = +5.3` |
| 计数 | 千分位逗号；`x of N (y%)` 或 `x/N` 二选一 | `505 of 848 (59.6%)` |
| 减号 | 正文数值一律 U+2212，不用 ASCII `-` | `−1.06` |

## 四、结果段句式模板（每类分析固定三段式）

1. **结论句**：`[指标] was [方向] in [人群]，[效应量 (95% CI)]。`
2. **参照句**：`Against [参照人群]，[对比值] (SMD [值])。`
3. **归属句**：`(Table N; Fig N)` —— 每段至少挂一处表/图锚点。

禁止事项：
- 无 CI 的比值单独成句（表里有的必须带出，或明确 "Table N lists full estimates"）；
- 无模型变体标签的 AUC；
- `significant` 裸用（必须 `nominal(ly)` 或否定）；
- `focus signal`（统一 `core signal`）；
- 图引用混用 `Fig` / `Fig.` / `Figure`（全稿择一，当前用 `Fig`）。

**两层写法约定（图注 ≠ 正文引用，勿混改）**：

| 位置 | 写法 | 例 |
|---|---|---|
| 正文引用 | `Fig N` / `Fig S2`（无点号，短式） | "…as shown in Fig 2" |
| 图注标题行 | `Figure N.` / `Supplementary Figure S2.`（全称 + 点号） | "**Figure 2.** Quarterly trends…" |

理由：图注是独立标题块，期刊排版按全称；正文引用短式可省版面。两层各自内部必须一致——正文不许出现 `Supplementary Figure S2`，图注标题不许出现 `Fig 2`。linter（R5）只约束正文，图注标题行不参与多数式判定。

## 五、变更协议（改任何数字/标题/图之后必做）

1. 改**真源**，不改中间产物；`make_submission.py` → `build_drugsafety.py` 顺序不可颠倒。
2. 全局搜旧值：`grep -rn "旧数字" docs/ submission_drugsafety/README.md`，出现次数应与预期一致。
3. 跑全闸门：`.venv/Scripts/python.exe tools/gate_all.py`
4. 打包：`tools/pack_zip.py`；投稿前 `tools/presubmit_check.py`。

**闸门顺序**（`gate_all.py` 自动执行）：表格交付级审计 → 结果写法 lint → 数值回源 → docx 清洁 → presubmit。
