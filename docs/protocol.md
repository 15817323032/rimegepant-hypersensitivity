# 研究方案：瑞美吉泮口崩片口腔/超敏谱不良反应的多层次风险刻画

**FAERS 信号挖掘 → 机器学习风险特征 → 网络毒理学与分子对接**

版本 v1.0 ｜ 2026-11-10 ｜ 目标期刊类型：药物流行病学/头痛专科（如 *J Headache Pain*、*Expert Opin Drug Saf*、*Front Pharmacol*、*Therap Adv Neurol Disord*）

---

## 1. 背景与立题依据

瑞美吉泮（rimegepant，Nurtec ODT / 维达全）为 CGRP 受体拮抗剂口崩片，2020 年 FDA 批准，2024 年中国获批（国药准字 HJ20240004）。其安全性问题在 2025 年出现实质性转折：

1. **FDA 于 2025 年 4–6 月 FAERS 季度"潜在严重风险/新安全性信息"通报中列入 Nurtec ODT 与 Zavzpret 的过敏性反应（anaphylactic reaction）**，并据此于 **2025 年 8 月修订【禁忌】与【警告及注意事项】**；
2. 现行 FDA 标签载明三项警告：**迟发型严重超敏反应（可于给药后数天发生）、高血压、Raynaud 现象**；
3. 中国说明书仅列"恶心（常见 1.2%）"与"超敏反应（偶见）"，**未载高血压与 Raynaud 警告**，存在版本差。

### 1.1 现有 FAERS 研究及其局限

已有至少 9 篇 FAERS/自发报告数据库研究（Battini 2023；Hu 2024；周丽 2024；何华康 2025；Song 2025；Liang 2024；Chen 2026；Giacon 2026 系统综述等），但存在四个共性局限：

| 局限 | 具体表现 |
|---|---|
| **止步于比例失衡** | 全部研究终点为 ROR/PRR/IC/EBGM 阳性信号列表，**无一篇做风险特征建模**（机器学习） |
| **机制层缺位** | **无一篇**对检出的口腔/超敏信号做网络毒理学或分子对接解释 |
| **数据窗口陈旧** | 最晚截止 2025Q1，**未覆盖 2025-08 FDA 标签修订后的报告行为变化** |
| **中国人群与剂型特异性被忽略** | 现有研究 97–99.8% 报告来自北美；ODT 剂型特有的口腔/咽部信号未被系统定义 |

### 1.2 已有信号提示（本研究的起点）

四篇独立研究在口腔/口咽部位反复检出信号：

- 何华康 2025：**肿舌、口部感觉异常、咽部肿胀**（说明书未载明）
- 周丽 2024：**舌不适、赋形剂反应、鼻水肿**
- Hu 2024：**reaction to food additive/excipient**
- Song 2025：feeling abnormal（敏感性分析后 ROR₀₂₅ = 6.46）、alopecia

这些 PT 与 FDA 新增的"迟发型严重超敏反应"高度可能属同一谱系，但**无任何研究做临床或机制层面的验证**。

---

## 2. 研究目的

1. **主目的**：系统刻画瑞美吉泮相关口腔/超敏谱事件的报告特征、时间特征与亚组分布，并与说明书、监管行动做一致性比对。
2. **次要目的 A**：识别与口腔/超敏事件相关的报告层面特征（机器学习），并解释其方向与强度（SHAP）。
3. **次要目的 B**：以网络毒理学与分子对接生成"口崩片局部黏膜/肥大细胞通路"的机制假说。
4. **探索性目的**：评估 2025-08 FDA 标签修订对相关 PT 报告行为的影响（notoriety bias）。

---

## 3. 研究设计

**设计类型**：回顾性药物警戒数据库研究（disproportionation analysis）+ 横断面风险特征建模 + 计算机制探索。

**数据源**：FDA FAERS ASCII 季度文件，**2020Q2（瑞美吉泮首次获批）至 2026Q2**。

> 数据窗口选择理由：起点对齐首次上市；终点覆盖 2025-08 标签修订并预留 ≥3 个季度观察修订后报告行为，是本设计相对现有文献的**唯一时间维度优势**，务必在 Methods 中明示。

**去重**：按 FDA 推荐规则（caseid 分组，fda_dt DESC → primaryid DESC 保留首条）。

**单位**：以去重后的病例（case）为分析单位，非报告版本。

---

## 4. 暴露与结局定义

### 4.1 暴露（目标药）

DRUG 表 drugname / prod_ai 匹配：`RIMEGEPANT`、`RIMEGEPANT SULFATE/BENZOATE`、`NURTEC`、`VYDURA`、`BMS-927711`。

**三重口径**（互为敏感性分析）：
- 主分析：`role_cod = PS`（首要怀疑）
- 敏感性 1：`PS + SS`
- 敏感性 2：`ALL`（含合并用药 C/I）

### 4.2 结局（口腔/超敏复合终点）

按 MedDRA PT 分五个子集（详见 `config/pt_sets.py`），并设三个严重性层级：

| 层级 | 子集 | 临床含义 |
|---|---|---|
| Tier 1 局部 | CORE_ORAL + SENSORY | 舌/唇/口腔黏膜/味觉/口部感觉异常 —— 机制上最可能源自 ODT 剂型的局部接触 |
| Tier 2 气道 | PHARYNGEAL_AIRWAY | 咽部肿胀/喉水肿/吞咽困难 —— 超敏升级为严重事件的转折点 |
| Tier 3 全身 | SYSTEMIC_HYPER | anaphylaxis/angioedema/urticaria —— 对应 FDA 2025-08 标签修订 |
| 辅料 | EXCIPIENT | 赋形剂/食品添加剂反应（明胶、甘露醇、三氯蔗糖、薄荷香精） |

**复合终点** = 五子集并集。**主分析终点用复合终点，子集分析用于机制分层。**

### 4.3 指示证偏倚控制

`NAUSEA / VOMITING / HEADACHE / MIGRAINE / PHOTOPHOBIA / PHONOPHOBIA` 等既属偏头痛症状又属常见 ADR，须做**排除适应证 PT 后重算**的敏感性分析（`table6_sensitivity`）。

---

## 5. 统计分析计划

### 5.1 不成比例分析

四算法并行，阈值预设（**不在看到结果后调整**）：

| 算法 | 统计量 | 阳性阈值 |
|---|---|---|
| ROR | 报告比值比 | ROR₀₂₅ > 1 |
| PRR | 比例报告比 | PRR ≥ 2 且 χ² ≥ 4 |
| BCPNN | IC / IC₀₂₅ | IC₀₂₅ > 0 |
| MGPS | EBGM / EB05 | EB05 > 2 |

共同要求：**a ≥ 3**。另报告 **满足 ≥2 种算法**的"稳健信号"，并做 **Benjamini-Hochberg FDR 校正**（现有文献几乎全部缺失此项，是方法学加分点）。

**实现说明**：ROR/PRR 为闭式精确公式；IC₀₂₅ 采用 delta 法近似（Var(lnROR) 标准式换算至 log2 尺度）；EBGM 采用矩估计 Gamma 先验收缩（DuMouchel GPS 简化实现）。**Methods 中须如实写明**，并用 R 包 `PhViD` / `openEBGM` 交叉校验（脚本见 `docs/R_crosscheck.R`）。

### 5.2 描述性分析

- Table 1 病例基线（年龄/性别/报告者/国家/事件数/严重结局）
- Table 4 发病时间（TTO = event_dt − THER.start_dt），分段 ≤1d / 2–7d / 8–30d / 31–90d / >90d
- Table 5 亚组（性别、年龄组、报告者、年份），Wilson 95%CI

### 5.2b 标签变更前后对比（补充分析，novelty 卖点）

以 2025Q3 为界（FDA 2025-08 标签修订），within-drug 对比超敏谱各家族
报告比例（Wilson CI + Fisher 精确检验 + 后/前比例比），检验 notoriety
bias。脚本 `src/label_change.py`，输出 `results_label_change/`。

### 5.3 机器学习风险特征（次要目的 A）

- **样本**：瑞美吉泮 PS 病例
- **标签**：y = 报告含 ≥1 个复合终点 PT
- **特征**：年龄/性别/体重、报告者类型、国家、报告年份、合并用药数、事件数、合并用药药理类别（抗组胺/激素/NSAID/曲普坦/PPI/SSRI/β阻滞剂/抗癫痫/CGRP mAb）、剂型（ODT）、TTO 及缺失指示
- **模型**：Logistic Regression（基准）、Random Forest、XGBoost、LightGBM
- **验证**：重复分层 5 折 × 3 次交叉验证；报告 **AUC、PR-AUC（类别不平衡下更可靠）、Brier 分数**
- **解释**：SHAP 全局重要性 + summary plot + 连续特征四分位阳性率
- **报告规范**：按 **TRIPOD+AI** 清单
- **明确的边界声明**：本模型为**风险特征刻画**，非临床预测工具，不用于个体化用药决策（必须写入 Discussion）

⚠️ **数据泄漏控制**：严重结局（OUTC）与事件总数**不作为主模型特征**——二者在时间上位于事件之后，且事件数与标签定义同源。

### 5.4 网络毒理学（次要目的 B-1）

> **方法学要点（预实验实测结论，务必照此执行）**：瑞美吉泮是高选择性分子，
> ChEMBL 实测 + 相似性推断合计仅得 CALCRL / RAMP1 / CALCA / ADRB2 等 ≤5 个靶点，
> 与事件基因集的经典"交集"仅 2–3 个基因，不足以支撑网络分析。
> 因此本研究采用**桥接（bridge）模式**，这也是本方案相对范文的第二个方法学差异。

1. **药物锚点（drug anchor）**：三路合并
   - 已知 MoA：CALCRL / RAMP1（ChEMBL mechanism）
   - **实测活性靶点**：自身 pChEMBL ≥ 5 的全部测定记录（`measured_targets.csv`）
   - 相似性推断：Tanimoto ≥ 50%（不足时自动降至 40%），邻居 pChEMBL ≥ 6
2. **事件基因集**：KEGG —— FcεRI 信号（hsa04664）、补体与凝血级联（hsa04610）、
   TRP 通道炎症介质调节（hsa04750）、趋化因子（hsa04062），共约 370 个基因
3. **桥接网络**：在 锚点 ∪ 事件模块 的 STRING 网络（score ≥ 700，高置信）上，
   从锚点做 BFS（≤4 跳），**桥接基因** = 最短路径中间节点，
   按被经由次数排序（`bridge_genes.csv`）
4. **富集**：Enrichr GO-BP / KEGG（返回结构已实测适配；报告 adj-p）

预实验（合成/在线混合环境）已给出生物学上可解释的桥接基因：
GNG2、GNB1、GNAS（CGRP 受体下游 G 蛋白）、**C3、C5**（补体——对应血管性水肿/咽部肿胀）、
PLCG1、MAPK1、SRC（肥大细胞/IgE 下游）、CX3CL1。这些将构成 Discussion 的机制假说骨架。

> ⚠️ **机制结论的表述边界（硬性要求）**：锚点中 ADRB2（pChEMBL<6 的弱测定）与
> 相似性推断靶点均非确证结合，桥接路径只提示**信号转导层面的连通性**，
> 结论必须写 *may involve / suggests a plausible link*，并在 Limitations 声明未做实验验证。

### 5.5 分子对接（次要目的 B-2）

- 配体：瑞美吉泮游离碱，RDKit ETKDGv3 生成 50 构象、MMFF94s 优化取最低能量
- 受体：优先共结晶结构（CGRP 受体 6Z2V），去水去杂原子
- 工具：AutoDock Vina（exhaustiveness 32，seed 42，取 mode 1 亲和力）；零安装替代 CB-Dock2 盲对接（与 Zheng 2026 范文一致）
- 报告：结合能（kcal/mol）+ 关键残基相互作用（PyMOL/LigPlot+ 出图）

> ⚠️ **机制结论的表述边界（硬性要求）**：靶点来自相似性推断而非实验测定，交集仅为"可能存在共同分子事件"。结论必须写 *may involve / suggests a plausible link*，并在 Limitations 声明未做实验验证。

---

## 6. 与现有文献的差异化声明（投稿信核心段落）

1. **首次**将瑞美吉泮的 FAERS 信号从"列表"推进到"风险特征建模"，并给出可解释性归因；
2. **首次**对 ODT 剂型特有的口腔/口咽信号做系统病例定义（五子集 + 三严重性层级）与机制探索；
3. **首个**覆盖 2025-08 FDA 标签修订的数据窗口，可评估监管行动对报告行为的影响；
4. 方法学上补齐 **BH-FDR 多重比较校正**、**指示证偏倚敏感性分析**、**四算法一致性判定**——现有 9 篇研究中三项均未同时做到；
5. **桥接模式**替代经典交集——针对高选择性药物的网络毒理学实现，是与范文（Zheng 2026 FAERS-NetDock 交集路线）的第二个方法学差异；
6. 提供**完整可复现代码**（现有范文代码一律"available upon request"）。

---

## 7. 伦理与数据合规

FAERS 为公开去标识化自发报告数据库，不含可识别个人信息，依 45 CFR 46.102 属**非人类受试者研究**，通常豁免 IRB 审查（须在文中声明；部分期刊仍要求作者单位出具豁免函，建议提前申请）。

---

## 8. 图表清单

| 编号 | 内容 | 来源 |
|---|---|---|
| Table 1 | 病例基线特征 | `table1_baseline.csv` |
| Table 2 | 全谱 PT 信号（四算法 + FDR） | `table2_all_signals.csv` |
| Table 3 | 口腔/超敏切口信号（含子集与层级） | `table3_focus_signals.csv` |
| Table 4 | 发病时间分布 | `table4_tto.csv` |
| Table 5 | 亚组分析 | `table5_subgroup.csv` |
| Table 6 | 敏感性分析（三重口径 + 排除适应证 PT） | `table6_sensitivity.csv` |
| Table 7 | 机器学习模型性能 | `ml_model_comparison.csv` |
| Table 8 | SHAP 全局重要性 Top 15 | `ml_shap_importance.csv` |
| Table 9 | 网络毒理学交集基因与 hub | `intersection_genes.csv` / `ppi_hubs.csv` |
| Table 10 | 富集结果 | `enrichment_go_bp.csv` / `enrichment_kegg.csv` |
| Table 11 | 分子对接打分 | `docking_scores.csv` |
| Table 12 | 标签变更（2025Q3 界）前后超敏谱家族报告比例对比 | `results_label_change/prepost_family_comparison.csv` |
| Figure 1 | 口腔/超敏切口信号森林图 | `results_full/forest_focus.png` |
| Figure 2 | 标签变更前后季度趋势图 | `results_label_change/label_change_trend.png` |
| Figure 3 | ML ROC/PR 曲线 | `results_ml_real/figures/roc_pr_curves.png` |
| Figure 4 | SHAP summary | `results_ml_real/figures/shap_summary.png` |
| Figure 5 | 网络毒理学三联图（靶点/桥接/富集） | `results/network_tox/figures/network_tox_summary.png` |
| Fig 1 | 研究流程图（PRISMA-like） | 手绘/流程图工具 |
| Fig 2 | 重点信号森林图 | `figures/forest_focus.png` |
| Fig 3 | TTO 分布 | 待补 |
| Fig 4 | ROC / PR 曲线 | `figures/roc_pr_curves.png` |
| Fig 5 | SHAP summary | `figures/shap_summary.png` |
| Fig 6 | 网络毒理学三联图 | `figures/network_tox_summary.png` |
| Fig 7 | 对接结合模式 | PyMOL |

---

## 9. 局限性（预先写好，避免审稿人先说）

1. 自发报告存在**报告偏倚、刺激偏倚（notoriety bias）、重复报告**，无法计算真实发生率；
2. **无分母**，不能推断绝对风险；
3. 比例失衡仅提示**统计关联**，不证明因果；
4. 靶点来自**计算推断**，未做实验验证；
5. 现有研究间报告数差异源于去重规则与 primary suspect 定义差异，**不可横向比较**；
6. TTO 报告不完整（文献约 7% 可用），时间分析效力有限；
7. 中国人群报告占比极低，结论外推受限。

---

## 10. 执行清单

- [ ] 下载 FAERS 2020Q2–2026Q2 共 25 个季度文件（约 40–60 GB），解压至 `data/raw/`
- [x] 运行全窗口流式版 `run_module1_stream.py` 产出 Table 1–6（results_full/，2026-11-11 完成）
- [x] 运行 `ml_risk.py`（经 extract_subset.py 子集）产出 Table 7–8（results_ml_real/，2026-11-11 完成）
- [x] 运行 `network_tox.py` 产出 Table 9–10（results/network_tox/，bridge 模式）
- [x] Vina 1.2.5 打分完成（2026-11-11）：CALCRL −8.879（阳性对照通过）/ SYK −3.189 / BTK −7.071 → `results/docking/docking_scores.csv`；复现与 CB-Dock2 指引见 `docs/docking_guide.md`
- [x] 运行 `label_change.py` 产出 Table 12 + Figure 2（results_label_change/，2026-11-11 完成）

Results 草稿见 `docs/results_draft.md`。
- [ ] R 包交叉校验 IC₀₂₅ / EBGM
- [ ] 撰写 Methods（直接对应本文件第 3–5 节）
- [ ] 按 TRIPOD+AI 补 Checklist
