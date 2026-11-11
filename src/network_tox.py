# -*- coding: utf-8 -*-
"""
Module 3 —— 网络毒理学：靶点推断 → 交集 → PPI hub → 通路富集

⚠️ 关于"网络毒理学"的方法学定位（写论文必须照此表述）
------------------------------------------------------
本模块输出的是 **假设生成（hypothesis-generating）** 结果，不是机制证明。
理由：靶点来自相似性推断（非实验测定），疾病/事件基因集来自通路数据库
（非该 ADR 的专属基因集），两者的交集只能提示"可能存在共同分子事件"。
因此结论必须写成 "may involve / suggests a plausible link"，
并在 Limitations 中明确未做实验验证。

数据源（2026-11 实测可用性）
--------------------------
✅ ChEMBL REST      —— 药物解析、作用机制、相似化合物、生物活性
✅ KEGG REST        —— 通路基因集（权威、可引用）
✅ STRING API       —— PPI 网络与 degree 排序
✅ Enrichr API      —— GO/KEGG 富集（替代不可达的 DAVID）
❌ CTD / Open Targets / STITCH —— 当前网络环境下接口不可达（HTML 错误页或 404），
   如您的网络可访问，可在 `EXTRA_DISEASE_SOURCES` 中启用；否则用
   `--disease-genes <csv>` 传入自己从 CTD/GeneCards 导出的基因表。

输出 (results/network_tox/)
---------------------------
drug_info.json              药物解析结果与作用机制
predicted_targets.csv       相似性推断靶点（含权重）
ae_gene_sets.csv            事件相关通路基因集
intersection_genes.csv      药物靶点 ∩ 事件基因
ppi_edges.csv / ppi_hubs.csv
enrichment_go_bp.csv / enrichment_kegg.csv
figures/network_tox_summary.png
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data/interim/cache"
CACHE.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (research; rimegepant-safety-pipeline)"}
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

# 瑞美吉泮游离碱（ChEMBL CHEMBL2178422 规范 SMILES；用于相似性检索）
RIMEGEPANT_SMILES = ("N[C@@H]1c2cccnc2[C@H](OC(=O)N2CCC(n3c(=O)[nH]c4ncccc43)CC2)"
                     "CC[C@H]1c1cccc(F)c1F")

# 事件相关的 KEGG 通路（每条都要在论文里给出选择理由）
# 选择依据：口腔/超敏切口的病理生理学环节
AE_PATHWAYS = {
    "hsa04664": ("Fc epsilon RI signaling pathway", "肥大细胞 IgE 受体活化 —— I 型超敏核心"),
    "hsa04610": ("Complement and coagulation cascades", "补体/激肽系统 —— 血管性水肿与咽部肿胀"),
    "hsa04750": ("Inflammatory mediator regulation of TRP channels", "TRPV1/TRPA1 —— 口部灼烧感与感觉异常"),
    "hsa04620": ("Toll-like receptor signaling pathway", "固有免疫活化 —— 佐剂样炎症放大"),
    "hsa04062": ("Chemokine signaling pathway", "肥大细胞/嗜碱粒细胞趋化"),
    "hsa05310": ("Asthma", "气道高反应性参照通路"),
    "hsa04672": ("Intestinal immune network for IgA production", "黏膜免疫，解释口咽部黏膜反应"),
    "hsa04970": ("Salivary secretion", "唾液腺反应（口干/唾液增多）"),
    "hsa04080": ("Neuroactive ligand-receptor interaction", "CGRP 受体下游与神经源性炎症"),
}

# 网络受限时的兜底基因集（文献curated，仅用于流程自检，发表须替换）
FALLBACK_SEED = [
    "FCER1A", "MS4A2", "KIT", "CPA3", "TPSAB1", "HDC", "HRH1", "HRH4",
    "LYN", "SYK", "BTK", "PLCG1", "PLCG2", "PRKCB", "PIK3CD", "AKT1",
    "MAPK1", "MAPK3", "CARD11", "MALT1", "BCL10", "NFKB1", "TNF", "IL4",
    "IL5", "IL13", "IL6", "IL33", "TSLP", "ALOX5", "ALOX5AP", "LTC4S",
    "CYSLTR1", "CYSLTR2", "PTGS1", "PTGS2", "CALCA", "CALCRL", "RAMP1",
    "TAC1", "TACR1", "TRPV1", "TRPA1", "NGF", "EDN1", "NOS2", "NOS3",
    "SERPING1", "F12", "KNG1", "BDKRB2", "ACE", "CMA1", "CTSG", "ELANE",
    "C3", "C5", "C5AR1", "SELE", "VCAM1", "ICAM1", "CCL2", "CCL5", "CXCL8",
]


# ---------------------------------------------------------------------------
# HTTP 工具
# ---------------------------------------------------------------------------
def _fetch(url: str, params: dict | None = None, timeout: int = 60,
           as_json: bool = True, retries: int = 2):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    import hashlib
    key = CACHE / (hashlib.md5(url.encode("utf-8")).hexdigest() + ".cache")
    if key.exists():
        try:
            raw = key.read_text(encoding="utf-8")
            return json.loads(raw) if as_json else raw
        except Exception:
            pass
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                raw = r.read().decode("utf-8", "replace")
            key.write_text(raw, encoding="utf-8")
            return json.loads(raw) if as_json else raw
        except Exception as e:
            if attempt == retries:
                print(f"    [http] 失败 {url[:90]}... ({type(e).__name__})")
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# 1. 药物解析
# ---------------------------------------------------------------------------
def resolve_drug(name="rimegepant") -> dict:
    print("[1/5] 解析药物 ...")
    d = _fetch("https://www.ebi.ac.uk/chembl/api/data/molecule/search.json",
               {"q": name, "limit": 5})
    if not d or not d.get("molecules"):
        return {}
    # 优先选名称完全匹配的游离碱
    cands = d["molecules"]
    best = next((m for m in cands if (m.get("pref_name") or "").upper() == name.upper()),
                cands[0])
    cid = best["molecule_chembl_id"]
    active = best.get("molecule_hierarchy", {}).get("active_chembl_id", cid)

    rec = _fetch(f"https://www.ebi.ac.uk/chembl/api/data/molecule/{active}.json") or best
    props = rec.get("molecule_properties") or {}
    out = {
        "pref_name": rec.get("pref_name"),
        "chembl_id_salt": cid,
        "chembl_id_active": active,
        "max_phase": rec.get("max_phase"),
        "first_approval": rec.get("first_approval"),
        "formula": props.get("full_molformula"),
        "mw": props.get("full_mwt"),
        "alogp": props.get("alogp"),
        "hbd": props.get("hbd"),
        "hba": props.get("hba"),
        "smiles": (rec.get("molecule_structures") or {}).get("canonical_smiles"),
    }
    mech = _fetch("https://www.ebi.ac.uk/chembl/api/data/mechanism.json",
                  {"molecule_chembl_id": cid})
    moa = []
    for m in (mech or {}).get("mechanisms", []):
        moa.append({"action": m.get("action_type"),
                    "mechanism": m.get("mechanism_of_action"),
                    "target_chembl_id": m.get("target_chembl_id")})
    out["mechanisms_of_action"] = moa
    print(f"    {out['pref_name']} ({active})  MoA: "
          f"{moa[0]['mechanism'] if moa else 'n/a'}")
    return out


def known_target_genes(drug: dict) -> set:
    genes = set()
    for m in drug.get("mechanisms_of_action", []):
        t = m.get("target_chembl_id")
        if t:
            g = target_genes(t)
            genes |= g
    return genes


def target_genes(target_chembl_id: str, _cache={}) -> set:
    if target_chembl_id in _cache:
        return _cache[target_chembl_id]
    d = _fetch(f"https://www.ebi.ac.uk/chembl/api/data/target/{target_chembl_id}.json")
    out = set()
    for comp in (d or {}).get("target_components", []):
        for syn in comp.get("target_component_synonyms", []):
            if syn.get("syn_type") == "GENE_SYMBOL":
                out.add(syn["component_synonym"].upper())
        if not out and comp.get("component_description"):
            out.add(comp["component_description"].split()[0].upper())
    _cache[target_chembl_id] = out
    return out


# ---------------------------------------------------------------------------
# 2. 相似性靶点推断（SwissTargetPrediction 的 ChEMBL 等价实现）
# ---------------------------------------------------------------------------
def similarity_targets(smiles: str, threshold: int = 50, max_neighbors: int = 60,
                       pchembl_cut: float = 6.0) -> pd.DataFrame:
    print(f"[2/5] 相似性靶点推断 (Tanimoto >= {threshold}%) ...")
    enc = urllib.parse.quote(smiles, safe="")
    d = _fetch(f"https://www.ebi.ac.uk/chembl/api/data/similarity/{enc}/{threshold}.json",
               {"limit": max_neighbors})
    if not d:
        return pd.DataFrame()
    mols = d.get("molecules", [])
    print(f"    相似化合物 {len(mols)} 个")

    rows = []
    for m in mols:
        mid = m["molecule_chembl_id"]
        sim = float(m.get("similarity") or 0) / 100.0
        act = _fetch("https://www.ebi.ac.uk/chembl/api/data/activity.json",
                     {"molecule_chembl_id": mid, "pchembl_value__gte": pchembl_cut,
                      "limit": 300})
        for a in (act or {}).get("activities", []):
            tid = a.get("target_chembl_id")
            if not tid:
                continue
            for g in target_genes(tid):
                rows.append(dict(gene=g, neighbor=mid, similarity=sim,
                                 pchembl=float(a.get("pchembl_value") or 0),
                                 assay_type=a.get("assay_type"),
                                 target_name=a.get("target_pref_name")))
    if not rows:
        print("    未获得活性记录（相似化合物可能无 pChEMBL>=6 数据）")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    agg = (df.groupby("gene")
             .agg(n_neighbors=("neighbor", "nunique"),
                  max_pchembl=("pchembl", "max"),
                  mean_pchembl=("pchembl", "mean"),
                  sim_weighted=("similarity", "sum"),
                  target_name=("target_name", "first"))
             .reset_index())
    # 综合打分：相似度加权 + 活性强度
    agg["score"] = (agg["sim_weighted"] *
                    np.clip((agg["max_pchembl"] - 5.0) / 4.0, 0.1, 1.0))
    agg = agg.sort_values("score", ascending=False).reset_index(drop=True)
    print(f"    推断靶点 {len(agg)} 个基因")
    return agg


def measured_targets(chembl_id: str, pchembl_cut: float = 5.0) -> pd.DataFrame:
    """
    该分子自身在 ChEMBL 中被实验测定过的全部靶点（pChEMBL >= 5）。
    与相似性推断互补：相似性看"邻居打了谁"，这一路看"自己实测打了谁"。
    """
    print(f"[2b/5] 实测活性靶点 (pChEMBL >= {pchembl_cut}) ...")
    d = _fetch("https://www.ebi.ac.uk/chembl/api/data/activity.json",
               {"molecule_chembl_id": chembl_id, "pchembl_value__gte": pchembl_cut,
                "limit": 1000})
    rows = []
    for a in (d or {}).get("activities", []):
        tid = a.get("target_chembl_id")
        if not tid:
            continue
        for g in target_genes(tid):
            rows.append(dict(gene=g, target_chembl_id=tid,
                             pchembl=float(a.get("pchembl_value") or 0),
                             assay_type=a.get("assay_type"),
                             target_name=a.get("target_pref_name")))
    if not rows:
        print("    未获得实测活性记录")
        return pd.DataFrame()
    df = (pd.DataFrame(rows)
          .groupby("gene")
          .agg(n_records=("target_chembl_id", "nunique"),
               max_pchembl=("pchembl", "max"),
               target_name=("target_name", "first"))
          .reset_index()
          .sort_values("max_pchembl", ascending=False))
    print(f"    实测靶点 {len(df)} 个基因: {', '.join(df['gene'].head(12))}")
    return df


# ---------------------------------------------------------------------------
# 3. 事件相关基因集
# ---------------------------------------------------------------------------
def kegg_gene_set(pathway_id: str) -> list:
    txt = _fetch(f"https://rest.kegg.jp/get/{pathway_id}", as_json=False)
    if not txt or "GENE" not in txt:
        return []
    genes, in_block = [], False
    for line in txt.splitlines():
        if line.startswith("GENE"):
            in_block = True
        elif line.startswith(("COMPOUND", "MOTIF", "DBLINKS", "REL_PATHWAY",
                              "KO_PATHWAY", "REFERENCE", "///")):
            in_block = False
        if in_block and line.startswith("            "):
            parts = line.strip().split()
            if len(parts) >= 2:
                sym = parts[1].rstrip(";,")
                if sym.isupper() or "(" in sym:
                    genes.append(sym.split("(")[0])
    return sorted(set(g for g in genes if 2 <= len(g) <= 12))


def build_ae_genesets(use_kegg=True) -> pd.DataFrame:
    print("[3/5] 构建事件相关基因集 ...")
    rows = []
    if use_kegg:
        for pid, (pname, rationale) in AE_PATHWAYS.items():
            gs = kegg_gene_set(pid)
            print(f"    {pid} {pname}: {len(gs)} 个基因")
            for g in gs:
                rows.append(dict(source=f"KEGG:{pid}", pathway=pname,
                                 rationale=rationale, gene=g))
    if not rows:
        print("    ⚠️ KEGG 不可达，使用内置文献 curated 兜底基因集（仅供流程自检）")
        for g in FALLBACK_SEED:
            rows.append(dict(source="FALLBACK:curated", pathway="hypersensitivity seed",
                             rationale="文献 curated（发表前须替换为 KEGG/CTD 正式基因集）",
                             gene=g))
    df = pd.DataFrame(rows).drop_duplicates(subset=["source", "gene"])
    return df


# ---------------------------------------------------------------------------
# 4. PPI（STRING）
# ---------------------------------------------------------------------------
def string_ppi(genes: list, score_cut: int = 400) -> tuple:
    print(f"[4/5] STRING PPI ({len(genes)} 基因) ...")
    if len(genes) < 3:
        return pd.DataFrame(), pd.DataFrame()
    d = _fetch("https://string-db.org/api/json/network",
               {"identifiers": "\r".join(genes), "species": 9606,
                "required_score": score_cut, "caller_identity": "rimegepant_pipeline"})
    if not d:
        return pd.DataFrame(), pd.DataFrame()
    rows = [dict(a=x["preferredName_A"], b=x["preferredName_B"], score=x["score"])
            for x in d]
    edges = pd.DataFrame(rows)
    if edges.empty:
        return edges, pd.DataFrame()

    deg = pd.concat([edges.groupby("a").size(), edges.groupby("b").size()],
                    axis=1).fillna(0)
    deg["degree"] = deg.sum(axis=1)
    hubs = (deg[["degree"]].sort_values("degree", ascending=False)
            .reset_index().rename(columns={"index": "gene"}))
    hubs["betweenness_proxy"] = hubs["degree"] / max(hubs["degree"].max(), 1)
    print(f"    边 {len(edges)}，节点 {len(hubs)}，Top hub: "
          f"{', '.join(hubs.head(5)['gene'].tolist())}")
    return edges, hubs


# ---------------------------------------------------------------------------
# 4b. 桥接分析（针对高选择性药物的核心方法）
# ---------------------------------------------------------------------------
def bridge_analysis(drug_genes: set, ae_genes: set, edges: pd.DataFrame,
                    max_hops: int = 4) -> pd.DataFrame:
    """
    对高选择性药物（交集过小）的标准解法：
    在 drug anchor ∪ AE 模块的 STRING 网络上做 BFS，
    找出连接"药物靶点"与"事件基因模块"的桥接基因（bridge genes）。

    打分 = 该基因作为最短路径中间节点的次数（被多少个 AE 基因经由它连到锚点）
    """
    import networkx as nx

    g = nx.Graph()
    for _, r in edges.iterrows():
        g.add_edge(r["a"], r["b"], weight=float(r["score"]))
    anchors = [x for x in drug_genes if x in g]
    targets = [x for x in ae_genes if x in g]
    if not anchors or not targets:
        return pd.DataFrame()

    recs = {}
    for t in targets:
        try:
            paths = nx.single_source_shortest_path(g, t, cutoff=max_hops)
        except Exception:
            continue
        for a in anchors:
            p = paths.get(a)
            if not p:
                continue
            for node in p[1:-1]:          # 中间节点
                recs.setdefault(node, dict(bridge_count=0, min_hops=99,
                                           connects=[]))
                recs[node]["bridge_count"] += 1
                recs[node]["min_hops"] = min(recs[node]["min_hops"], len(p) - 1)
                if len(recs[node]["connects"]) < 5:
                    recs[node]["connects"].append(t)

    df = pd.DataFrame([dict(gene=k, **v) for k, v in recs.items()])
    if df.empty:
        return df
    df["in_ae_set"] = df["gene"].isin(ae_genes).astype(int)
    df = df.sort_values(["bridge_count", "min_hops"], ascending=[False, True])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 5. 富集（Enrichr）
# ---------------------------------------------------------------------------
ENRICHR = "https://maayanlab.cloud/Enrichr"


def enrichr(genes: list, libs=("GO_Biological_Process_2023", "KEGG_2021_Human")):
    print(f"[5/5] Enrichr 富集 ({len(genes)} 基因) ...")
    out = {}
    try:
        import requests
        r = requests.post(f"{ENRICHR}/addList", timeout=60, headers=UA,
                          files={"list": (None, "\n".join(genes)),
                                 "description": (None, "rimegepant_oral_hyp")})
        r.raise_for_status()
        uid = r.json()["userListId"]
    except Exception as e:
        print(f"    [Enrichr] addList 失败: {e}")
        return out

    for lib in libs:
        d = _fetch(f"{ENRICHR}/enrich", {"userListId": uid, "backgroundType": lib})
        if not isinstance(d, dict):
            continue
        # 实测返回结构: {lib: [[rank, term, p, z, combined, [genes], adj_p, ...], ...]}
        recs = []
        for row in d.get(lib, []):
            if not isinstance(row, list) or len(row) < 7:
                continue
            try:
                recs.append(dict(library=lib, term=str(row[1]),
                                 p_value=float(row[2]), z_score=float(row[3]),
                                 combined_score=float(row[4]),
                                 n_overlap=len(row[5]) if isinstance(row[5], list) else 0,
                                 genes=";".join(row[5]) if isinstance(row[5], list) else "",
                                 adj_p_value=float(row[6])))
            except (TypeError, ValueError):
                continue
        if recs:
            df = pd.DataFrame(recs).sort_values("p_value").head(25)
            out[lib] = df
            print(f"    {lib}: {len(df)} 条（p 最小 {df['p_value'].min():.2e}）")
    return out


# ---------------------------------------------------------------------------
# 汇总图
# ---------------------------------------------------------------------------
def plot_summary(targets, hubs, enr_bp, fp: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4), dpi=300)

    if targets is not None and len(targets):
        t = targets.head(12).iloc[::-1]
        axes[0].barh(t["gene"], t["score"], color="#3b7dd8", height=0.65)
        axes[0].set_title("Predicted targets (ChEMBL similarity)", fontsize=9, loc="left")
        axes[0].set_xlabel("Score", fontsize=8)

    if hubs is not None and len(hubs):
        h = hubs.head(12).iloc[::-1]
        axes[1].barh(h["gene"], h["degree"], color="#c0392b", height=0.65)
        axes[1].set_title("PPI hub genes (STRING degree)", fontsize=9, loc="left")
        axes[1].set_xlabel("Degree", fontsize=8)

    if enr_bp is not None and len(enr_bp):
        e = enr_bp.head(10).copy().iloc[::-1]
        e["logp"] = -np.log10(e["p_value"].clip(lower=1e-30))
        lbl = e["term"].str.replace(r"\s*\(GO:\d+\)", "", regex=True).str[:46]
        axes[2].barh(lbl, e["logp"], color="#27ae60", height=0.65)
        axes[2].set_title("GO-BP enrichment", fontsize=9, loc="left")
        axes[2].set_xlabel("-log10 P", fontsize=8)

    for ax in axes:
        ax.tick_params(labelsize=7)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    plt.tight_layout()
    fp.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(fp, bbox_inches="tight")
    plt.close(fig)
    print(f"    [fig] {fp.name}")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/network_tox")
    ap.add_argument("--similarity", type=int, default=50)
    ap.add_argument("--disease-genes", default=None,
                    help="自定义事件基因 CSV（列名 gene，可选 source/pathway），"
                         "优先于在线源")
    ap.add_argument("--use-kegg", action="store_true", default=True)
    a = ap.parse_args()

    out = ROOT / a.out
    (out / "figures").mkdir(parents=True, exist_ok=True)
    log = []

    drug = resolve_drug("rimegepant")
    (out / "drug_info.json").write_text(
        json.dumps(drug, ensure_ascii=False, indent=2), encoding="utf-8")
    if not drug:
        print("药物解析失败，终止"); return

    smiles = drug.get("smiles") or RIMEGEPANT_SMILES
    drug_targets = similarity_targets(smiles, a.similarity)
    measured = measured_targets(drug["chembl_id_active"] or drug["chembl_id_salt"])
    moa_genes = known_target_genes(drug)
    print(f"    已知 MoA 靶点基因: {sorted(moa_genes)}")

    if len(drug_targets):
        drug_targets.to_csv(out / "predicted_targets.csv", index=False,
                            encoding="utf-8-sig")
    if len(measured):
        measured.to_csv(out / "measured_targets.csv", index=False,
                        encoding="utf-8-sig")
    drug_set = set(drug_targets["gene"]) if len(drug_targets) else set()
    drug_set |= (set(measured["gene"]) if len(measured) else set())
    drug_set |= moa_genes
    log.append(f"药物靶点 {len(drug_set)} 个基因"
               f"（实测 {measured['gene'].nunique() if len(measured) else 0} 个 + "
               f"相似性 {drug_targets['gene'].nunique() if len(drug_targets) else 0} 个 + "
               f"MoA {len(moa_genes)} 个）")

    # 相似性召回不足时自动降阈值重试
    if len(drug_set) < 10 and a.similarity > 40:
        lo = max(40, a.similarity - 10)   # ChEMBL 不接受 <40% 的阈值
        print(f"    [recall] 靶点过少，自动降低相似性阈值至 {lo}% 重试 ...")
        drug_targets2 = similarity_targets(smiles, lo)
        if len(drug_targets2):
            drug_targets2.to_csv(out / "predicted_targets_relaxed.csv", index=False,
                                 encoding="utf-8-sig")
            drug_set |= set(drug_targets2["gene"])
            log.append(f"放宽阈值 {lo}% 后新增 "
                       f"{drug_targets2['gene'].nunique()} 个靶点")

    # 事件基因集
    if a.disease_genes:
        ae = pd.read_csv(a.disease_genes)
        ae = ae.rename(columns={ae.columns[0]: "gene"})
        if "source" not in ae: ae["source"] = "user_csv"
        if "pathway" not in ae: ae["pathway"] = ""
        if "rationale" not in ae: ae["rationale"] = ""
    else:
        ae = build_ae_genesets(a.use_kegg)
    ae.to_csv(out / "ae_gene_sets.csv", index=False, encoding="utf-8-sig")
    ae_set = set(ae["gene"].str.upper())
    log.append(f"事件基因集 {len(ae_set)} 个基因，来源 {ae['source'].nunique()} 个")

    # 交集
    inter = sorted(drug_set & ae_set)
    pd.DataFrame({"gene": inter}).to_csv(out / "intersection_genes.csv",
                                         index=False, encoding="utf-8-sig")
    print(f"\n[交集] 药物靶点 ∩ 事件基因 = {len(inter)} 个: {', '.join(inter[:30])}")
    log.append(f"交集基因 {len(inter)} 个")

    if len(inter) < 3:
        print("⚠️ 交集基因过少 —— 这是高选择性药物的典型情形。"
              "自动启用【桥接模式】：在 靶点∪事件基因 的 STRING 网络上找桥接基因。")

    # 桥接模式：把事件基因集核心模块拉进网络
    core_pathways = ["KEGG:hsa04664", "KEGG:hsa04610", "KEGG:hsa04750",
                     "KEGG:hsa04062"]          # FcεRI/补体/TRP/趋化因子
    ae_core = set(ae.loc[ae["source"].isin(core_pathways), "gene"].str.upper())
    combined = sorted(drug_set | ae_core)
    print(f"\n[桥接] 网络节点 = 靶点 {len(drug_set)} ∪ 核心事件模块 {len(ae_core)} "
          f"= {len(combined)} 个基因")
    edges, hubs = string_ppi(combined, score_cut=700)
    if len(edges):
        edges.to_csv(out / "ppi_edges.csv", index=False, encoding="utf-8-sig")
        if len(hubs):
            hubs.to_csv(out / "ppi_hubs.csv", index=False, encoding="utf-8-sig")
        try:
            import networkx  # noqa: F401
            brid = bridge_analysis(drug_set, ae_core, edges)
            if len(brid):
                brid.to_csv(out / "bridge_genes.csv", index=False, encoding="utf-8-sig")
                log.append(f"桥接基因 {len(brid)} 个；Top: "
                           f"{', '.join(brid.head(10)['gene'].tolist())}")
                print(f"    桥接基因 Top10: {', '.join(brid.head(10)['gene'].tolist())}")
        except ImportError:
            print("    （未安装 networkx，跳过桥接分析：pip install networkx）")
    else:
        hubs = pd.DataFrame()

    enr = enrichr(inter if len(inter) >= 5 else sorted(drug_set | ae_core)[:150])
    for lib, df in enr.items():
        fn = "enrichment_go_bp.csv" if "GO" in lib else "enrichment_kegg.csv"
        df.to_csv(out / fn, index=False, encoding="utf-8-sig")

    plot_summary(drug_targets, hubs,
                 enr.get("GO_Biological_Process_2023"),
                 out / "figures/network_tox_summary.png")

    (out / "run_log.txt").write_text(
        "网络毒理学模块运行记录\n" + "\n".join(f"- {x}" for x in log) +
        "\n\n方法学提示：本结果属假设生成，需实验验证。\n", encoding="utf-8")
    print(f"\n[done] 结果目录: {out}")


if __name__ == "__main__":
    main()
