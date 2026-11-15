# 稿件数值回源审计

源：`docs/manuscript_en.md`；工具：`tools/verify_claims.py`

结果：PASS 73 / WARN 1 / FAIL 0

| 级别 | 区域 | 声明 | 说明 |
|---|---|---|---|
| WARN | cross-table | 表1/表5 年龄<18 | 表1 42（仅 age_cod=YR）vs 表5 85（任何数值化年龄）——口径不同，需脚注或统一 |
| PASS | counts | TTO 1060 | 已回源 |
| PASS | counts | TTO 848 | 已回源 |
| PASS | counts | cohort PS | 8962 已回源 |
| PASS | counts | PS+SS | 9691 已回源 |
| PASS | counts | all roles | 13190 已回源 |
| PASS | counts | full DB | 9094154 已回源 |
| PASS | counts | reference | 9085192 已回源 |
| PASS | counts | indication-matched | 75155 已回源 |
| PASS | cross-table | 性别分母 | 6562 两表一致 |
| PASS | docking | BTK receptor | 1B55_rec.pdbqt |
| PASS | docking | BTK box | 11391 Å³ 与 manifest 一致 |
| PASS | docking | CALCRL_3N7S receptor | 3N7S_rec.pdbqt |
| PASS | docking | CALCRL box | 24225 Å³ 与 manifest 一致 |
| PASS | docking | SYK receptor | 1A81_rec.pdbqt |
| PASS | docking | SYK box | 11391 Å³ 与 manifest 一致 |
| PASS | docking | CALCRL mode-1 | -8.450 kcal/mol（判据 ≤ -8） |
| PASS | docking | BTK Δ | +1.38 kcal/mol 自洽 |
| PASS | docking | SYK Δ | +5.26 kcal/mol 自洽 |
| PASS | docking:BTK mode-2 | 引用 12.1 Å（已标注 upper bound） |  |
| PASS | label | Anaphylactoid | post/pre=1.08, p=0.63 |
| PASS | label | Systemic hypersensitivity | post/pre=1.00, p=1.00 |
| PASS | label | Oral mucosal | post/pre=1.62, p=0.09 |
| PASS | label | Oral sensory | post/pre=1.06, p=0.87 |
| PASS | label | Pharyngeal/airway | post/pre=1.05, p=0.83 |
| PASS | label | Excipient reaction | post/pre=2.03, p=0.16 |
| PASS | ml | RandomForest AUC | 0.621 已回源 |
| PASS | ml | LogisticRegression AUC | 0.611 已回源 |
| PASS | ml | XGBoost AUC | 0.610 已回源 |
| PASS | ml | LightGBM AUC | 0.583 已回源 |
| PASS | pct:coverage | 40 个百分比 | 全部可回源（表内 81 值 + 派生 7 值 + 外部登记 3 值） |
| PASS | pct:pairing | 百分比配对 | 每个「a% vs b%」都能对应到表中同一行或同一列 |
| PASS | pct:table1 | 72 个 n(%) 单元格 | 分母重算一致，四档求和与有记录数一致 |
| PASS | pct:table4 | 7 个 TTO 百分比 | 分母 8,962 / 848 重算一致 |
| PASS | pct:table5 | 16 个亚组 | 占比=k/n 重算一致，均在 Wilson CI 内 |
| PASS | signals | focus PT 数 | 49 已回源 |
| PASS | signals | 其中阳性 | 19 已回源 |
| PASS | signals | a>=3 PT 数 | 437 已回源 |
| PASS | signals | REACTION TO FOOD ADDITIVE | ROR 185.70 与表一致 |
| PASS | signals | REACTION TO EXCIPIENT | 提及但未给 ROR（表值 16.20） |
| PASS | signals | PARAESTHESIA ORAL | ROR 4.64 与表一致 |
| PASS | signals | HYPOAESTHESIA ORAL | ROR 4.34 与表一致 |
| PASS | signals | SWOLLEN TONGUE | ROR 3.55 与表一致 |
| PASS | signals | NASAL OEDEMA | 提及但未给 ROR（表值 6.15） |
| PASS | signals | PHARYNGEAL SWELLING | ROR 3.36 与表一致 |
| PASS | signals | MOUTH SWELLING | ROR 3.96 与表一致 |
| PASS | signals | HYPERSENSITIVITY | 提及但未给 ROR（表值 2.09） |
| PASS | signals | URTICARIA | 提及但未给 ROR（表值 1.36） |
| PASS | signals | ANAPHYLACTIC REACTION | 提及但未给 ROR（表值 1.27） |
| PASS | signals | DYSPHAGIA | 提及但未给 ROR（表值 0.62） |
| PASS | smd | 17 个 SMD 引用 | 全部可回源（表 1 两列 + INDI 子集敏感性） |
| PASS | smd | SMD -1.15 | 表1 Serious outcome (any) vs 全库 |
| PASS | smd | SMD -1.06 | 表1 Reporter, physician vs 全库 |
| PASS | smd | SMD -0.69 | 表1 Reporter, physician vs 适应证匹配；表1 Serious outcome (any) vs 适应证匹配 |
| PASS | smd | SMD -0.44 | 表1 Age >=65 years (of recorded) vs 全库 |
| PASS | smd | SMD -0.30 | 表1 Disability vs 适应证匹配 |
| PASS | smd | SMD -0.28 | 表1 Age <18 years (of recorded) vs 全库；表1 Life-threatening vs 适应证匹配 |
| PASS | smd | SMD -0.18 | 表1 Life-threatening vs 全库；表1 Country GB vs 适应证匹配 |
| PASS | smd | SMD -0.11 | 表1 Disability vs 全库 |
| PASS | smd | SMD -0.02 | 表1 Female (of sex recorded) vs 适应证匹配 |
| PASS | smd | SMD +0.00 | INDI 子集敏感性 female |
| PASS | smd | SMD +0.09 | 表1 Age >=65 years (of recorded) vs 适应证匹配 |
| PASS | smd | SMD +0.12 | 表1 Age missing vs 全库 |
| PASS | smd | SMD +0.27 | 表1 Sex missing/unknown vs 全库 |
| PASS | smd | SMD +0.65 | 表1 Female (of sex recorded) vs 全库 |
| PASS | smd | SMD +0.72 | 表1 Reporter, consumer vs 适应证匹配 |
| PASS | smd | SMD +0.84 | 表1 Country US vs 全库 |
| PASS | smd | SMD +1.13 | 表1 Reporter, consumer vs 全库 |
| PASS | smd | 10 组百分比对 | 重算 SMD 与稿件一致（±0.02） |
| PASS | smd | INDI 子集病例数 | 4,477 已回源 |
| PASS | smd | 敏感性 female | +0.00 已回源 |
| PASS | smd | 敏感性 consumer | +0.63 已回源 |
| PASS | smd | 敏感性 US | +0.64 已回源 |
| PASS | smd | 敏感性 serious | -0.61 已回源 |
