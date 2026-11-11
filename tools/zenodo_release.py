# -*- coding: utf-8 -*-
"""Publish a repository archive to Zenodo and return the DOI.

Usage:
    set ZENODO_TOKEN=xxx
    python tools/zenodo_release.py --file submission/rimegepant-hypersensitivity_v1.0.0.zip

Steps: create deposition -> upload file to bucket -> publish -> print DOI.
"""
import argparse, json, os, sys
import requests

API = "https://zenodo.org/api"
TOKEN = os.environ.get("ZENODO_TOKEN")
if not TOKEN:
    sys.exit("ZENODO_TOKEN not set")

S = requests.Session()
S.headers.update({"Authorization": f"Bearer {TOKEN}"})

GITHUB_URL = "https://github.com/15817323032/rimegepant-hypersensitivity"

METADATA = {
    "upload_type": "software",
    "publication_type": "software",
    "title": ("Rimegepant ODT Oral/Hypersensitivity FAERS Pipeline: disproportionality, "
              "machine learning, bridged network toxicology, and molecular docking"),
    "description": (
        "<p>Four-layer, fully reproducible Python pipeline for post-marketing safety analysis of "
        "rimegepant orally disintegrating tablets using FAERS/AEMS 2020Q2&ndash;2026Q2 "
        "(25 quarters, N = 9,094,154 deduplicated cases; n = 8,962 primary-suspect cases).</p>"
        "<p>Layers: (1) four-algorithm disproportionality analysis (ROR, PRR, BCPNN, MGPS; BH-FDR) "
        "against a pre-specified five-subset oral/hypersensitivity composite endpoint; "
        "(2) machine-learning reporting-feature profiling (LR/RF/XGBoost/LightGBM, repeated "
        "5&times;3 CV, SHAP, TRIPOD+AI); (3) bridged network toxicology (ChEMBL anchors &rarr; "
        "STRING BFS &rarr; Enrichr GO-BP/KEGG); (4) AutoDock Vina 1.2.5 molecular docking "
        "(CALCRL 6Z2V positive control; SYK 1A81 / BTK 1B55 off-target tests); plus a pre/post "
        "2025Q3 label-revision notoriety-bias comparison.</p>"
        "<p>FAERS/AEMS raw extracts are not redistributed; all derived tables and figures are included.</p>"
    ),
    "creators": [
        {"name": "Chen, LiQing",
         "affiliation": "Department of Otolaryngology, Head and Neck Surgery, "
                        "Shenzhen University General Hospital, Shenzhen, China",
         "orcid": "0000-0002-2285-3704"},
        {"name": "Luo, Yunfan", "orcid": "0000-0001-5370-6777"},
    ],
    "keywords": ["pharmacovigilance", "FAERS", "rimegepant", "CGRP antagonist",
                 "disproportionality analysis", "machine learning", "network toxicology",
                 "molecular docking", "hypersensitivity"],
    "license": "MIT",
    "access_right": "open",
    "version": os.environ.get("RELEASE_VERSION", "1.0.1"),
    "language": "eng",
    "related_identifiers": [
        {"identifier": GITHUB_URL, "relation": "isSupplementTo", "resource_type": "software"}
    ],
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="submission/rimegepant-hypersensitivity_v1.0.0.zip")
    ap.add_argument("--deposition", type=int, default=None,
                    help="reuse an existing unpublished deposition id")
    ap.add_argument("--newversion-of", type=int, default=None,
                    help="create a new version draft from this published deposition id")
    args = ap.parse_args()

    # 1) create (or reuse) deposition
    if args.newversion_of:
        nv = S.post(f"{API}/deposit/depositions/{args.newversion_of}/actions/newversion", timeout=120)
        if nv.status_code not in (200, 201):
            sys.exit(f"newversion failed {nv.status_code}: {nv.text[:500]}")
        latest = nv.json()["links"]["latest_draft"]
        g = S.get(latest, timeout=60)
        if g.status_code != 200:
            sys.exit(f"fetch draft failed {g.status_code}: {g.text[:500]}")
        dep = g.json()
        S.put(f"{API}/deposit/depositions/{dep['id']}", json={"metadata": METADATA}, timeout=120)
        # the new-version draft inherits the previous files; clear them first
        for f in dep.get("files", []):
            S.delete(f"{API}/deposit/depositions/{dep['id']}/files/{f['id']}", timeout=60)
            print("cleared inherited file:", f.get("filename"))
    elif args.deposition:
        g = S.get(f"{API}/deposit/depositions/{args.deposition}", timeout=60)
        if g.status_code != 200:
            sys.exit(f"fetch failed {g.status_code}: {g.text[:500]}")
        dep = g.json()
        # metadata may need a refresh if the first attempt never uploaded
        S.put(f"{API}/deposit/depositions/{dep['id']}", json={"metadata": METADATA}, timeout=120)
    else:
        r = S.post(f"{API}/deposit/depositions", json={"metadata": METADATA}, timeout=120)
        if r.status_code not in (200, 201):
            sys.exit(f"create failed {r.status_code}: {r.text[:500]}")
        dep = r.json()
    dep_id = dep["id"]
    bucket = dep["links"]["bucket"]
    print("deposition:", dep_id)

    # 2) upload archive to bucket
    name = os.path.basename(args.file)
    with open(args.file, "rb") as fh:
        up = S.put(f"{bucket}/{name}", data=fh, timeout=600,
                   headers={"Content-Type": "application/octet-stream"})
    if up.status_code not in (200, 201):
        sys.exit(f"upload failed {up.status_code}: {up.text[:500]}")
    print("uploaded:", name, up.status_code)

    # 3) publish
    p = S.post(f"{API}/deposit/depositions/{dep_id}/actions/publish", timeout=180)
    if p.status_code not in (200, 202):
        sys.exit(f"publish failed {p.status_code}: {p.text[:500]}")
    rec = p.json()
    doi = rec.get("doi")
    concept = rec.get("conceptdoi")
    print("DOI:", doi)
    print("CONCEPT_DOI:", concept)
    print("URL:", rec.get("links", {}).get("html"))
    json.dump({"doi": doi, "conceptdoi": concept, "id": dep_id,
               "url": rec.get("links", {}).get("html")},
              open("submission/zenodo_doi.json", "w"), indent=2)

if __name__ == "__main__":
    main()
