# 分子对接（Table 11）逐步操作指引

> 本指引覆盖两条路径：**A. 本机 Vina（已完成自动化，含复现步骤）** 与
> **B. CB-Dock2 网页版（零安装备选）**。换靶点、换配体时同样适用。
> 更新日期：2026-11-11。

---

## 0. 对接包目录总览

```
results/docking/
├── ligand.pdbqt            # 瑞美吉泮 50 构象（RDKit ETKDGv3 + MMFF94s，meeko 转换）
├── 6Z2V_rec.pdbqt          # CGRP 受体（CALCRL+RAMP1）柔性侧链已预处理  ← 受体
├── 1A81_rec.pdbqt          # SYK tandem SH2
├── 1B55_rec.pdbqt          # BTK 激酶域
├── vina_CALCRL.txt 等      # 三个对接配置（盒子中心/尺寸/exhaustiveness/seed）
├── out_<TARGET>.pdbqt      # Vina 输出构象（跑完后生成）
├── vina_log_<TARGET>.txt   # Vina 运行日志（含打分表）
└── docking_manifest.json   # 靶点/盒子元数据
```

三个靶点的角色：
- **CALCRL（6Z2V）**：on-target 阳性对照——瑞美吉泮共晶受体，打分应最强；
- **SYK（1A81）/ BTK（1B55）**：off-target 检验——肥大细胞活化激酶，
  若瑞美吉泮对它们打分显著弱于 CALCRL（ΔG 差 > 2 kcal/mol），
  支持"超敏谱非受体直接 off-target"的结论。

## 1. 路径 A：本机 Vina（本次已全自动执行）

### 1.1 环境（一次性）

```bash
# Python 包（venv 内已有）：rdkit、meeko、openpyxl
.venv/Scripts/python.exe -m pip install rdkit meeko openpyxl

# Vina 独立版（无需编译，1.2 MB）
curl -L -o tools/vina.exe \
  "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.5/vina_1.2.5_win.exe"
tools/vina.exe --version        # 应输出 AutoDock Vina v1.2.5
```

### 1.2 受体准备（新靶点时重复本步）

原始 PDB 从 RCSB 下载（保留共晶配体以确定盒子），清洗后转 PDBQT：

```bash
cd results/docking
# ① 转换（--allow_bad_res 自动剔除模板不匹配残基；--charge_model zero 因
#    Vina 打分不使用电荷，zero 最快且不引入误差）
../../.venv/Scripts/mk_prepare_receptor.exe \
    --read_pdb <PDBID>_clean.pdb \
    -o <PDBID>_rec -p <PDBID>_rec.pdbqt \
    --default_altloc A --allow_bad_res --forgive_extra_bonds --charge_model zero
```

注意：`_clean.pdb` 必须已去除水、共晶配体与离子（`dock_prep.py` 已处理）；
若含大量 HETATM 残基，meeko 会逐一报模板错误，逐个确认后再决定保留与否。

### 1.3 对接盒子设定（本次的口径，写 Methods 用）

| 靶点 | 盒子中心 (x,y,z) | 尺寸 (Å) | exhaustiveness | 依据 |
|---|---|---|---|---|
| CALCRL | 78.52, 14.07, 93.58 | 34.8×24.1×37.4 | 16 | 共晶配体包围盒（三靶点统一 ex=16 保证可比性） |
| SYK | 34.03, 69.30, 73.43 | 22.5³ | 16 | 共晶配体中心 + 标准盒（原包围盒 86 Å 过大） |
| BTK | 2.33, 3.32, 54.43 | 22.5³ | 16 | 同上 |

seed 固定 42（可复现）；num_modes 9；energy_range 4。

### 1.4 运行与收分

```bash
# 单靶点（约 10-40 分钟/个，取决于盒子大小）
cd results/docking
../../tools/vina.exe --config vina_CALCRL.txt --out out_CALCRL.pdbqt \
    > vina_log_CALCRL.txt 2>&1

# 打分汇总（从日志抓 Vina result 表）
../../.venv/Scripts/python.exe collect_scores.py    # → docking_scores.csv
```

### 1.5 结果判定标准（预注册在 protocol，勿事后更改）

1. **阳性对照有效性**：CALCRL 打分应 ≤ −8 kcal/mol（文献中 rimegepant–CGRP
   受体共晶结合很强）；若 > −7，先检查盒子是否覆盖配体结合位点。
2. **Off-target 判定**：SYK/BTK 最优打分弱于 CALCRL 达 2 kcal/mol 以上
   → 支持"无受体级 off-target"；若强于 CALCRL，需做结合模式人工检查
   （PyMOL/ChimeraX 叠加原共晶配体）再下结论，不可只看数值。
3. **不应比较不同靶点间的绝对分值来排序毒性**——对接打分只能作
   假设生成证据，文字表述用"suggests / hypothesize"，与 FAERS/网毒
   证据链互相印证，不单独下因果结论。

## 2. 路径 B：CB-Dock2 网页版（零安装备选）

1. 打开 https://cadd.labshare.cn/cb-dock2/php/index.php
2. **Ligand** 页上传 `results/docking/ligand_best.sdf`（瑞美吉泮 3D 构象）；
3. **Receptor** 页分别上传 `6Z2V_clean.pdb` / `1A81_clean.pdb` / `1B55_clean.pdb`
   （CB-Dock2 自动找 cavity，无需手动设盒子——与本地 Vina 的差异需在
   Methods 注明）；
4. 提交后任务排队 1–4 小时，邮箱/页面取结果：关注 **Vina score** 与
   **cavity volume / center**；
5. 判定标准同 §1.5；CB-Dock2 与本地 Vina 分值可能有 1–2 kcal/mol 系统差
   （cavity 定义不同），报告时注明工具与版本，不做跨工具绝对比较。

## 3. Table 11 回填流程（本次自动执行）

1. `vina_log_<TARGET>.txt` 中 mode 1 分值 → `docking_scores.csv`；
2. `docs/results_draft.md` §3.6 更新为真实分值 + 判定结论；
3. 对接构象 `out_<TARGET>.pdbqt` 留档（审稿补充材料可附 PyMOL 渲染图）。

## 4. 常见坑

- **Python 3.13 无法 `pip install vina`**（无预编译 wheel）→ 用独立 exe（本指引路径 A）。
- meeko 报 "Template matching failed" → 加 `--allow_bad_res`；
  报多 altloc → `--default_altloc A`。
- 盒子过大（共晶配体是肽类/辅因子时包围盒可 > 60 Å）→ 改为中心 + 22.5 Å
  标准盒，否则 exhaustiveness 32 也要跑数小时。
- `collect_scores.py` 依赖日志格式，Vina 版本变化时先看 `vina_log_*.txt`
  里的 "mode | affinity" 表。
