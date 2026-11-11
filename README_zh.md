# 瑞美吉泮口腔/超敏谱不良反应 —— 四层分析流水线

FAERS 信号挖掘 → 机器学习风险特征 → 网络毒理学 → 分子对接

针对 **rimegepant（Nurtec ODT / 瑞美吉泮口崩片）** 的**口腔/口咽/超敏**信号切口，
全部用 Python 实现，可直接复现。研究方案见 [`docs/protocol.md`](docs/protocol.md)。

---

## 为什么做这个切口

四篇独立 FAERS 研究在口腔/口咽部位反复检出说明书未载明的信号（肿舌、口部感觉异常、
咽部肿胀、舌不适、赋形剂反应），且 FDA 已于 2025-08 因 anaphylaxis 信号修订标签。
但现有 9 篇研究**全部止步于比例失衡**：无一篇做风险特征建模、无一篇做机制探索、
数据窗口全部止于 2025Q1。这三处空白就是本流水线的落点。

---

## 目录结构

```
rimegepant_hypersensitivity/
├── config/
│   └── pt_sets.py              ★ MedDRA PT 病例定义（五子集 + 三严重性层级）
├── src/
│   ├── faers_io.py             FAERS ASCII 读取（$ 分隔、表头兼容、FDA 标准去重）
│   ├── stats_disproportionality.py   四算法 + BH-FDR
│   ├── run_module1.py          主流程 → Table 1-6 + 森林图
│   ├── ml_risk.py              Module 2 → Table 7-8 + ROC/PR + SHAP
│   ├── network_tox.py          Module 3 → 靶点/PPI/富集
│   ├── dock_prep.py            Module 4 → 配体/受体/Vina 配置
│   └── make_demo_data.py       合成数据生成（自检用）
├── docs/
│   ├── protocol.md             研究方案（可直接改写成 Methods）
│   └── R_crosscheck.R          IC025 / EBGM 的 R 包交叉校验
├── data/{raw,demo,interim}     原始数据 / 演示数据 / 缓存
└── results/                    所有表格与图
```

---

## 快速开始

```bash
# 0) 环境（已建好 .venv）
.venv/Scripts/python.exe -m pip install -r requirements.txt   # 或手动装

# 1) 先跑合成数据自检（3 分钟，不下载任何大文件）
.venv/Scripts/python.exe src/make_demo_data.py
.venv/Scripts/python.exe src/run_module1.py --demo
.venv/Scripts/python.exe src/ml_risk.py --demo

# 2) 真实数据
#    从 https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html
#    下载 2020Q2–2026Q2 全部 aers_ascii_*.zip，解压后把
#    DEMO/DRUG/REAC/OUTC/INDI/THER/RPSR 的 txt 全部平铺放进 data/raw/
.venv/Scripts/python.exe src/run_module1.py --raw data/raw \
    --quarters 2020Q2 2020Q3 2020Q4 2021Q1 ... 2026Q2
.venv/Scripts/python.exe src/ml_risk.py --raw data/raw --quarters 2020Q2 ... 2026Q2
.venv/Scripts/python.exe src/network_tox.py
.venv/Scripts/python.exe src/dock_prep.py --targets CALCRL RAMP1 SYK BTK
```

> **数据量提示**：25 个季度全库约 40–60 GB，`run_module1` 全量跑约 1–3 小时（内存峰值
> 约 8–12 GB）。机器内存 <16 GB 建议按年分批跑，再用 `--out results/2020` 等分目录合并。

---

## 各模块产出

| 模块 | 关键文件 | 说明 |
|---|---|---|
| 1 | `results/table1..6_*.csv` | 基线、全谱信号、切口信号、TTO、亚组、敏感性 |
| 1 | `figures/forest_focus.png` | 切口信号森林图（300 dpi） |
| 2 | `results/ml_model_comparison.csv` | 4 模型 × 5 折 × 3 次重复 CV |
| 2 | `results/ml_shap_importance.csv` / `figures/shap_summary.png` | 可解释性归因 |
| 3 | `results/network_tox/*` | 靶点（实测+相似性）、**桥接基因**、PPI、GO/KEGG 富集 |
| 4 | `results/docking/*` | 配体 3D、清洗后受体、Vina 配置、批处理脚本 |

---

## 三个必须知道的实现细节

**1. FAERS 文件是 `$` 分隔，不是逗号。**
且 2014Q3 后才有表头，列集合逐季演变，必须按列名取用而非位置索引。
`faers_io.py` 已处理；若您看到"整行一列"的情况，基本就是分隔符问题。

**2. 四算法的统计量是近似的，发表前须交叉校验。**
ROR/PRR 为闭式精确公式；IC₀₂₅ 用 delta 法近似；EBGM 用矩估计 Gamma 先验。
`docs/R_crosscheck.R` 用 `PhViD` / `openEBGM` 给出对照，Methods 中须写明实现方式。

**3. 高选择性药物走"桥接模式"，不走经典交集。**
瑞美吉泮在 ChEMBL 实测 + 相似性推断合计只有 ≤5 个靶点，与事件基因集的交集仅 2–3 个
基因——这是高选择性小分子的普遍情形。`network_tox.py` 在交集 <3 时自动切换为桥接模式：
在"靶点 ∪ 事件模块"的 STRING 网络（score≥700）上做 BFS，输出桥接基因。
预实验已给出可解释的桥接基因（GNG2/GNB1=受体下游 G 蛋白、C3/C5=补体/血管性水肿、
PLCG1/MAPK1/SRC=肥大细胞信号）。

**4. `n_aes`（事件总数）默认排除在 ML 特征之外。**
它与标签定义同源（事件越多越可能命中复合终点），属机械性泄漏。
`--include-naes` 可开启，但只应作为敏感性分析。

---

## 外部数据源可用性（2026-11 实测）

| 源 | 状态 | 用途 |
|---|---|---|
| ChEMBL REST | ✅ | 药物解析、MoA、相似化合物、生物活性 → 靶点推断 |
| KEGG REST | ✅ | 通路基因集（权威可引用） |
| STRING API | ✅ | PPI 与 hub 排序 |
| Enrichr | ✅ | GO-BP / KEGG 富集（替代 DAVID） |
| CTD / Open Targets / STITCH | ❌ 当前网络不可达 | 若您网络可访问可自行启用；否则用 `--disease-genes` 传入自备基因表 |

`network_tox.py` 在外部源全失败时会退回内置文献 curated 基因集——那**只用于流程自检**，
发表前必须替换为 KEGG 自动抓取或自备的 CTD/GeneCards 导出表。

---

## 已知边界（写进 Limitations）

- 自发报告无分母，不能计算发生率；比例失衡只提示统计关联。
- 靶点来自相似性推断而非实验测定，网络毒理学结果属**假设生成**。
- 本仓库不含任何真实患者数据；`data/demo/` 全部为随机模拟，数值无科学意义。
