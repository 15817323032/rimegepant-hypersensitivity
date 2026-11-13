# 原始数据包 — Rimegepant 口腔/超敏信号研究

**生成日期**：{{DATE}}
**数据来源**：FDA FAERS / AEMS 公开 ASCII 数据库，2020Q2–2026Q2 共 25 个季度
**本包性质**：FAERS **原始记录行**（未做任何统计变换）+ 队列纳入标记 + 复原清单

---

## 0. 先说清楚：为什么包里没有 11 GB

全库解压后共 **{{GB}} GB / {{N_FILES}} 个源文件**（25 季度 × 7 张表），绝大部分与本课题无关——我们只用了其中 13,190 例提及 rimegepant 的报告。

因此本包采取「**只给研究实际读取的行 + 给复原方法**」的策略：

- **需要复核数据** → 用 `01_faers_source_rows/`，这就是原始行，字段与 FDA 文件一一对应，未改一字
- **需要从零重建全库** → 用 `04_download_manifest/`，里面有每个源文件的官方下载链接、字节数、行数

任何人拿到本包，都能独立重算 8,962 例队列、75,155 例适应证匹配参照系和全部表格。

---

## 1. 目录结构

```
raw_data_package/
├── README.md                              ← 本文件
├── 01_faers_source_rows/                  ← FAERS 原始行（双格式：.txt 为原始 $ 分隔，.csv 为同一份数据的 UTF-8 版）
│   ├── DEMO.txt / DEMO.csv                ← 人口学 {{ROWS_DEMO}} 行
│   ├── DRUG.txt / DRUG.csv                ← 用药 {{ROWS_DRUG}} 行
│   ├── REAC.txt / REAC.csv                ← 不良事件 {{ROWS_REAC}} 行
│   ├── INDI.txt / INDI.csv                ← 适应证 {{ROWS_INDI}} 行
│   ├── OUTC.txt / OUTC.csv                ← 结局 {{ROWS_OUT}} 行
│   ├── RPSR.txt / RPSR.csv                ← 报告来源 {{ROWS_RPSR}} 行
│   └── THER.txt / THER.csv                ← 治疗史 {{ROWS_THER}} 行
├── 02_case_id_map/
│   └── case_id_inclusion_map.csv          ← 13,190 个 primaryid 及其纳入标记（PS / PS+SS / ALL）
├── 03_reference_population/
│   └── reference_population_summary.csv   ← 全库、参照系、适应证匹配三套分母的计数
├── 04_download_manifest/
│   └── faers_source_manifest.csv          ← 25 季度 × 7 表的文件名、字节数、行数、官方 zip 链接
└── 05_code/                               ← 从下载到出表的完整流水线（9 个脚本）
```

> **各表覆盖范围一致**：七张表都按**最宽口径**（任何角色，13,190 例）抽取，因此同一 `primaryid` 在每张表里都能找到对应行。哪一例属于 PS 主分析队列（8,962）或 PS+SS 敏感性队列（9,691），由 `02_case_id_map/case_id_inclusion_map.csv` 标记决定——**不要在读取阶段再按行数去推口径**。
>
> 行数多于例数是正常的：`DRUG` 一例多药、`REAC` 一例多 PT、`INDI` 一例多适应证（本队列平均 3.3 个）。`RPSR` 仅 511 行，因为 FDA 只对部分报告提供报告来源记录；主分析的「报告者类型」用的是 `DEMO.rept_cod`，不依赖 `RPSR`，不影响任何结果复算。

---

## 2. 三种队列口径（包内 `02_case_id_map` 已逐例标好）

| 标记 | 例数 | 含义 | 用途 |
|---|---|---|---|
| `in_primary_suspect` | **8,962** | rimegepant 为**主要怀疑药**（`role_cod = PS`），按 caseid 去重保留最新版本 | 主分析队列（全部结果表的口径） |
| `in_primary_or_secondary` | **9,691** | 主要 + 次要怀疑药（PS + SS） | 敏感性分析 |
| `in_any_role` | **13,190** | 任何角色（含伴随用药 C） | 药物相互作用探索 |

分母：全库去重后 **9,094,154** 例；剔除 rimegepant 队列后参照系 **9,085,192** 例；适应证含偏头痛的匹配参照系 **75,155** 例（其中 PS 口径 4,477 例）。

---

## 3. 字段字典（FAERS ASCII 标准，仅列本研究使用的字段）

### DEMO — 病例人口学（1 行/报告版本）

| 字段 | 含义 |
|---|---|
| `primaryid` | 报告唯一编号（FAERS primary ID）——**所有表的主键** |
| `caseid` | 病例编号（同一病例的多个版本共用） |
| `caseversion` | 版本号 |
| `fda_dt` | FDA 收到日期（YYYYMMDD） |
| `event_dt` | 事件发生日期 |
| `rept_cod` | 报告者类型：`EXP` 消费者 / `PER` 医务人员 / `DIR` 药企 / `OTH` 其他 |
| `age` / `age_cod` / `age_grp` | 年龄、年龄单位（YR/DEC）、年龄段 |
| `sex` | 性别（M/F/UNK） |
| `wt` / `wt_cod` | 体重及单位（KG） |
| `reporter_country` | 报告国家（ISO 代码） |
| `occp_cod` | 职业 |
| `rept_dt` / `init_fda_dt` | 报告日期、首次 FDA 收到日期 |
| `mfr_sndr` | 生产企业/发送方名称 |

### DRUG — 用药（1 行/药）

| 字段 | 含义 |
|---|---|
| `primaryid` / `caseid` | 关联键 |
| `drug_seq` | 该报告内的用药序号 |
| `role_cod` | **角色**：`PS` 主要怀疑 / `SS` 次要怀疑 / `C` 伴随 / `I` 相互作用 |
| `drugname` | 药名（原样自由文本）。本队列中 rimegepant 以**商品名 `NURTEC ODT`** 为主（13,416 行），通用名 `RIMEGEPANT` 502 行 |
| `prod_ai` | 活性成分（含 `RIMEGEPANT` 的 13,988 行——**识别目标药最稳的字段**） |
| `route` | 给药途径 |
| `dose_vbm` | 剂量描述（自由文本） |
| `dose_form` | 剂型。全表 `ORODISPERSIBLE TABLET` 7,639 行 / `TABLET` 9,873 行 / 空值 41,011 行（空值绝大多数是**伴随用药**行）；**rimegepant 行内空值仅 4.9%** |
| `dose_freq` | 频次 |
| `nda_num` | NDA 号 |

> **剂型（ODT）判定口径**（`ml_risk.py` 实际执行，可原样复核）：
> `dose_form` 命中 `DISINTEGRAT｜ORODISPERS｜ODT` → 记为 ODT；无命中即「未记录为 ODT」，**不填补、不按药名推断**。
> 在 PS 队列的 9,703 行 rimegepant 用药记录中：`dose_form` 空白仅 4.9%，判为 ODT 的 7,524 行（77.5%）；落到个案层面，8,962 例中 7,093 例（79.1%）有 ODT 记录。剩余以 `TABLET`/`UNKNOWN` 为主。
> 剂型与报告者类型、报告国家一起被移出主模型（它们描述的是报告渠道而非患者风险），只在 `--with-reporter` 敏感性模型中出现——主稿 Methods 已就此声明。

### REAC — 不良事件（1 行/PT）

| 字段 | 含义 |
|---|---|
| `primaryid` / `caseid` | 关联键 |
| `pt` | MedDRA 首选语（大写） |
| `drug_rec_act` | 药企采取的措施（自由文本） |

### INDI — 适应证（1 行/适应证）

| 字段 | 含义 |
|---|---|
| `primaryid` / `caseid` | 关联键 |
| `indi_drug_seq` | 对应 `DRUG.drug_seq` |
| `indi_pt` | 适应证原文（如 `MIGRAINE PROPHYLAXIS`）——**适应证匹配参照系的筛选字段** |

### OUTC — 结局（1 行/结局代码）

| 字段 | 含义 |
|---|---|
| `primaryid` / `caseid` | 关联键 |
| `outc_cod` | `DE` 死亡 / `LT` 危及生命 / `HO` 住院 / `DS` 致残 / `CA` 先天异常 / `RI` 需干预 / `OT` 其他严重 |

### RPSR — 报告来源

| 字段 | 含义 |
|---|---|
| `primaryid` / `caseid` | 关联键 |
| `rpsr_cod` | `HP` 医疗专业人员 / `CN` 消费者 / `CSM` 企业与监管机构 / `OTH` / `UF` 用户机构 |

### THER — 治疗史

| 字段 | 含义 |
|---|---|
| `primaryid` / `caseid` | 关联键 |
| `dsg_drug_seq` | 对应用药序号 |
| `start_dt` / `end_dt` / `dur` / `dur_cod` | 起止日期、持续时间及单位 |

> **THER 里包含该病例的「全部用药」行，不只是瑞美吉泮**（12,983 行 / 5,536 例）。THER 表本身没有药名列，`dsg_drug_seq` 需回连 `DRUG.drug_seq` 才能知道是哪一种药。做 TTO 时必须只取瑞美吉泮那一行（`dsg_drug_seq` = 该病例 `DRUG` 中 `drugname`/`prod_ai` 命中 RIMEGEPANT/NURTEC 的 `drug_seq`），否则会把合并用药的开始日期当成瑞美吉泮的开始日期，算出的病例数与 Table 4 不符。
>
> **TTO 复算的完整口径**（与 `src/run_module1.py::table4_tto` 及 `src/ml_risk.py` 一致，可得表内 848 例）：
> ① 限定 PS 队列（`02_case_id_map`，8,962 例）；② `DEMO.event_dt` 与瑞美吉泮行的 `start_dt` 都必须是**完整 8 位日期** `YYYYMMDD`——FAERS 中大量日期只精确到月（`YYYYMM`），这类记录按缺失处理，不插值；③ TTO = event_dt − start_dt；④ 剔除负值（事件早于用药，208 例）与 >730 天（4 例）。
> 链条：8,962 → 两日期完整 1,060（11.8%）→ 可分析 848（9.5%），中位 0 天（IQR 0–5），67.3% 在 1 天内。
> 注意：若不做 ②（用宽松解析把 `YYYYMM` 当月初）或 ④（保留负值），会分别多出约 200 例，这是复算时最常出现的两处偏差。

> **编码说明**：`.txt` 与 FDA 原件完全一致（`$` 分隔、latin-1）；`.csv` 是同一份数据转 UTF-8-BOM 后的版本（Excel 可直接打开）。二者内容等价，行数相同。空值在 FAERS 里就是空字符串，不是 `NA`。

---

## 4. 从零复原全库（如果需要）

```bash
# 1) 下载 25 季度官方压缩包（URL 见 04_download_manifest/faers_source_manifest.csv）
python 05_code/download_faers.py --start 2020Q2 --end 2026Q2 --out data/raw

# 2) 抽取 rimegepant 病例子集（生成 DEMO/DRUG/REAC/OUTC/THER 子集）
python 05_code/extract_subset.py --raw data/raw --cache data/interim/stream_cache

# 3) 计算三套参照系（全库 / 去药 / 适应证匹配）
python 05_code/reference_population.py --raw data/raw --out results_full

# 4) 主分析 → 表 1–6、Figure 1
python 05_code/run_module1.py --raw data/raw
```

> 步骤 2 依赖 `stream_cache/*.pkl`（首次需先跑一遍 `run_module1.py` 生成缓存）。完整依赖与顺序见 `05_code/` 各脚本 docstring。

---

## 5. 版本与合规

- **数据截点**：2026Q2（2026 年 7–9 月发布的最新季度文件）
- **数据库更名**：FDA 已于 **2026-03-11** 以 **AEMS**（Adverse Event Monitoring System）取代 FAERS，本包沿用官方原始文件与字段名，正文采用「FAERS/AEMS」双名表述
- **去重规则**：按 `caseid` 保留 `caseversion` 最高（最新）版本，删除 FDA 已删除病例（`ADRxxQxDeletedCases.txt` / `DELETExxQx.txt` 中列出的 primaryid）
- **伦理**：FAERS 为公开去标识化数据，无需伦理审批（主稿 Declarations 已声明）
- **许可**：数据本身为美国联邦政府公开数据（public domain）；本包的整理结构与字段标注以 CC BY 4.0 提供，引用请指向主稿与 Zenodo 存档

---

## 6. 与其它交付包的关系

| 包 | 内容 | 用途 |
|---|---|---|
| **本包（raw_data_package）** | FAERS 原始行 + 纳入标记 + 复原清单 | 数据可核查性（审稿人复核 8,962 例怎么来的） |
| `rimegepant_figure_data_package_*.zip` | 5 张图实际绘制的整理数值 | 图表数值核对 |
| `submission_drugsafety/` | 投稿四件套（主稿、cover letter、附表、图表） | 直接投出去 |
