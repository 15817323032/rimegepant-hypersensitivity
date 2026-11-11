# -*- coding: utf-8 -*-
"""
Module 4 —— 分子对接准备（配体/受体/参数/批处理）

设计思路
--------
本机无 AutoDock Vina 与 ADFR 套件，因此脚本**只做可自动化的准备工作**，
把不可自动化的重原子受体加氢/赋电荷交给标准工具，并生成可直接执行的批处理脚本。

分工：
  脚本负责          配体 3D 构象（RDKit ETKDGv3 + MMFF94s 优化）→ PDBQT
                    受体 PDB 下载、去水去配体去杂原子、按链切分
                    对接盒中心/尺寸计算（配体已知则取配体几何中心）
                    Vina 配置文件 + 批量运行脚本 + 结果汇总脚本
  您负责            安装 AutoDock Vina 与 ADFR（prepare_receptor4.py）
                    跑批（单核 CPU 几十秒一个靶点）

替代路径（零安装）
----------------
若不想装 ADFR，可直接把 receptor.pdb 与 ligand.pdbqt 上传到
https://cadd.labshare.org/_api/apps/cb-dock2 （CB-Dock2 盲对接），
把返回的 Vina 分数填入 results/docking/docking_scores.csv。
范文 Zheng 2026 正是用 CB-Dock2 完成的，方法学上可直接对标。

用法
----
    python src/dock_prep.py --targets CALCRL RAMP1 --out results/docking
    python src/dock_prep.py --pdb 6Z2V --out results/docking     # 指定结构
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 靶点 → 推荐 PDB 结构（有共结晶配体的优先，便于定义对接盒）
# 说明：CALCRL/RAMP1 的 CGRP 受体结构为 6Z2V（冷冻电镜，含 CGRP 肽）；
# 其他靶点结构需按 Module 3 的交集结果补充，此处给出常用备份。
TARGET_PDB = {
    "CALCRL": ("6Z2V", "CGRP receptor (CALCRL+RAMP1) 冷冻电镜结构"),
    "RAMP1": ("6Z2V", "同上，RAMP1 为共受体"),
    "MS4A2": ("", "无实验结构，建议 AlphaFold DB: AF-P24380-F1"),
    "KIT": ("1T45", "KIT 激酶域 + 抑制剂"),
    "SYK": ("1A81", "SYK  tandem SH2"),
    "BTK": ("1B55", "BTK 激酶域"),
    "PLCG2": ("2FJU", "PLC-gamma2"),
    "HRH1": ("3RZE", "H1 组胺受体 + doxepin"),
    "CYSLTR1": ("", "建议 AlphaFold DB"),
    "TRPV1": ("5IRX", "TRPV1 与 resiniferatoxin"),
    "SERPING1": ("", "建议 AlphaFold DB"),
    "BDKRB2": ("", "建议 AlphaFold DB"),
}

RIMEGEPANT_SMILES = ("N[C@@H]1c2cccnc2[C@H](OC(=O)N2CCC(n3c(=O)[nH]c4ncccc43)CC2)"
                     "CC[C@H]1c1cccc(F)c1F")


def have(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


# ---------------------------------------------------------------------------
# 配体
# ---------------------------------------------------------------------------
def prep_ligand(out_dir: Path, smiles: str) -> Path | None:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        print("  ⚠️ 未安装 RDKit，跳过配体 3D 生成")
        print("     安装: pip install rdkit")
        return None

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print("  ✗ SMILES 解析失败")
        return None
    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    params.useSmallRingTorsions = True
    cids = AllChem.EmbedMultipleConfs(mol, numConfs=50, params=params)
    if not cids:
        print("  ✗ 构象生成失败")
        return None

    # MMFF94s 优化并按能量排序
    res = AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=2000, mmffVariant="MMFF94s")
    energies = [e for _, e in res]
    best = int(min(range(len(energies)), key=lambda i: energies[i]))

    sdf = out_dir / "ligand_best.sdf"
    w = Chem.SDWriter(str(sdf))
    mol.SetProp("_Name", "rimegepant")
    w.write(mol, confId=best); w.close()

    pdb = out_dir / "ligand_best.pdb"
    Chem.MolToPDBFile(mol, str(pdb), confId=best)

    # PDBQT：优先 meeko
    pdbqt = out_dir / "ligand.pdbqt"
    if _try_meeko(sdf, pdbqt):
        print(f"  ✓ 配体 PDBQT (meeko): {pdbqt.name}  最优构象能量 "
              f"{energies[best]:.2f} kcal/mol")
    elif have("obabel"):
        subprocess.run(["obabel", str(sdf), "-O", str(pdbqt), "--partialcharge", "gasteiger"],
                       check=False, capture_output=True)
        print(f"  ✓ 配体 PDBQT (obabel): {pdbqt.name}")
    else:
        print(f"  ✓ 配体 3D: {sdf.name} / {pdb.name}")
        print("     ⚠️ 未生成 PDBQT，请安装 meeko 或 openbabel，")
        print("        或在 MGLTools 中手动转换 ligand_best.sdf → ligand.pdbqt")

    info = {"smiles": smiles, "num_confs": len(cids),
            "best_energy_kcal": float(energies[best])}
    (out_dir / "ligand_info.json").write_text(json.dumps(info, indent=2))
    return pdbqt if pdbqt.exists() else sdf


def _try_meeko(sdf: Path, out: Path) -> bool:
    try:
        from meeko import MoleculePreparation, PDBQTWriterLegacy
        from rdkit import Chem
        mol = Chem.MolFromMolFile(str(sdf), removeHs=False)
        prep = MoleculePreparation()
        setups = prep.prepare(mol)
        txt, ok, err = PDBQTWriterLegacy.write_string(setups[0])
        if ok:
            out.write_text(txt)
            return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# 受体
# ---------------------------------------------------------------------------
def fetch_pdb(pdb_id: str, out_dir: Path) -> Path | None:
    fp = out_dir / f"{pdb_id}.pdb"
    if fp.exists() and fp.stat().st_size > 1000:
        return fp
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    try:
        urllib.request.urlretrieve(url, fp)
        print(f"  ✓ 受体结构 {pdb_id}: {fp.name} ({fp.stat().st_size//1024} KB)")
        return fp
    except Exception as e:
        print(f"  ✗ 下载 {pdb_id} 失败: {e}")
        return None


def clean_receptor(pdb: Path, out_dir: Path, chains: list | None = None) -> Path:
    """去水、去杂原子、去原有配体（HETATM），可只保留指定链。"""
    keep, dropped_het = [], 0
    for line in pdb.read_text(errors="replace").splitlines():
        rec = line[:6].strip()
        if rec == "ATOM":
            if chains and line[21] not in chains:
                continue
            keep.append(line)
        elif rec == "HETATM":
            resn = line[17:20].strip()
            if resn in ("HOH", "WAT", "DOD"):
                continue
            dropped_het += 1          # 共结晶配体/离子一并去除
        elif rec in ("TER", "END"):
            keep.append(line)
    out = out_dir / f"{pdb.stem}_clean.pdb"
    out.write_text("\n".join(keep) + "\nEND\n")
    print(f"  ✓ 清洗受体: {out.name}（保留 {len(keep)} 行，去除 HETATM {dropped_het} 个）")
    return out


def ligand_box(pdb: Path) -> tuple:
    """若结构含共结晶配体，取其几何中心作为对接盒中心。"""
    xs, ys, zs = [], [], []
    for line in pdb.read_text(errors="replace").splitlines():
        if line.startswith("HETATM") and line[17:20].strip() not in ("HOH", "WAT"):
            try:
                xs.append(float(line[30:38])); ys.append(float(line[38:46]))
                zs.append(float(line[46:54]))
            except ValueError:
                continue
    if not xs:
        return None
    c = (round(sum(xs)/len(xs), 2), round(sum(ys)/len(ys), 2), round(sum(zs)/len(zs), 2))
    size = (round(max(xs)-min(xs)+16, 1), round(max(ys)-min(ys)+16, 1),
            round(max(zs)-min(zs)+16, 1))
    return c, size


# ---------------------------------------------------------------------------
# Vina 配置与批处理
# ---------------------------------------------------------------------------
def write_vina_config(center, size, lig: Path, rec: Path, fp: Path):
    fp.write_text(
        f"receptor = {rec.name}\n"
        f"ligand = {lig.name}\n\n"
        f"center_x = {center[0]}\ncenter_y = {center[1]}\ncenter_z = {center[2]}\n"
        f"size_x = {size[0]}\nsize_y = {size[1]}\nsize_z = {size[2]}\n\n"
        f"exhaustiveness = 32\nnum_modes = 9\nenergy_range = 4\nseed = 42\n",
        encoding="utf-8")


def write_runner(out_dir: Path, jobs: list):
    sh = out_dir / "run_vina.sh"
    bat = out_dir / "run_vina.bat"
    lines_sh = ["#!/usr/bin/env bash", "set -e", "cd \"$(dirname \"$0\")\"", ""]
    lines_bat = ["@echo off", "cd /d %~dp0", ""]
    for name, cfg in jobs:
        lines_sh.append(f'vina --config {cfg} --out {name}_out.pdbqt --log {name}.log')
        lines_bat.append(f"vina --config {cfg} --out {name}_out.pdbqt --log {name}.log")
    sh.write_text("\n".join(lines_sh) + "\n", encoding="utf-8")
    bat.write_text("\r\n".join(lines_bat) + "\r\n", encoding="utf-8")
    print(f"  ✓ 批处理脚本: {sh.name} / {bat.name}（{len(jobs)} 个靶点）")


def write_scorer(out_dir: Path):
    """汇总 Vina log 中的最佳打分，生成 docking_scores.csv。"""
    code = '''# -*- coding: utf-8 -*-
"""汇总 Vina 结果：从 *.log 提取 mode 1 亲和力"""
import re, sys
from pathlib import Path
import pandas as pd

d = Path(__file__).resolve().parent
rows = []
for log in sorted(d.glob("*.log")):
    txt = log.read_text(errors="replace")
    m = re.findall(r"^\\s*(\\d+)\\s+(-?\\d+\\.\\d+)\\s+", txt, re.M)
    if not m:
        continue
    mode, aff = m[0]
    rows.append(dict(target=log.stem, mode1_affinity_kcal=float(aff)))
df = pd.DataFrame(rows).sort_values("mode1_affinity_kcal")
df.to_csv(d / "docking_scores.csv", index=False, encoding="utf-8-sig")
print(df.to_string(index=False))
'''
    (out_dir / "collect_scores.py").write_text(code, encoding="utf-8")
    print("  ✓ 打分汇总脚本: collect_scores.py")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="*", default=["CALCRL"])
    ap.add_argument("--pdb", default=None, help="直接指定 PDB ID，覆盖 --targets 映射")
    ap.add_argument("--out", default="results/docking")
    ap.add_argument("--smiles", default=RIMEGEPANT_SMILES)
    a = ap.parse_args()

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)

    print("[1/3] 配体准备")
    lig = prep_ligand(out, a.smiles)

    print("[2/3] 受体准备")
    jobs, meta = [], []
    for t in a.targets:
        pdb_id, note = (a.pdb, "用户指定") if a.pdb else TARGET_PDB.get(
            t.upper(), ("", "未收录"))
        if not pdb_id:
            print(f"  – {t}: 无 PDB 结构（{note}）。建议用 AlphaFold DB 预测结构："
                  f"https://alphafold.ebi.ac.uk/search?q={t}")
            continue
        pdb = fetch_pdb(pdb_id, out)
        if not pdb:
            continue
        rec = clean_receptor(pdb, out)
        box = ligand_box(pdb)
        center, size = box if box else ((0.0, 0.0, 0.0), (22.0, 22.0, 22.0))
        cfg = out / f"vina_{t.upper()}.txt"
        if lig:
            write_vina_config(center, size, lig, rec, cfg)
            jobs.append((f"{t.upper()}", cfg.name))
        meta.append(dict(target=t.upper(), pdb=pdb_id, note=note,
                         center=center, size=size,
                         box_source="co-crystal ligand" if box else "default 22Å cube"))

    print("[3/3] 配置与脚本")
    if jobs:
        write_runner(out, jobs)
    write_scorer(out)
    (out / "docking_manifest.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n下一步（本机未检测到 Vina）：")
    print("  1) 安装 AutoDock Vina: https://github.com/ccsb-scripps/AutoDock-Vina/releases")
    print("  2) 安装 ADFR 或 meeko 生成受体 PDBQT：")
    print("     prepare_receptor4.py -r <rec>_clean.pdb -o <rec>.pdbqt -A hydrogens")
    print("  3) 执行 run_vina.bat（Windows）或 bash run_vina.sh")
    print("  4) python collect_scores.py  → docking_scores.csv")
    print("  零安装替代：把 _clean.pdb 与 ligand.pdbqt 上传 CB-Dock2 盲对接")


if __name__ == "__main__":
    main()
