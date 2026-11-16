"""Build the RAW data package: FAERS source rows for the rimegepant cohort + provenance.

The full FAERS ASCII library is 11 GB across 25 quarters and is NOT shipped.
Instead we ship every raw row that the study actually reads, in original FAERS
`$`-delimited form plus UTF-8 CSV, with the case-ID inclusion flags so any
reviewer can re-derive the cohort.

Run: .venv/Scripts/python.exe tools/build_raw_data_package.py [--skip-scan]
"""
from __future__ import annotations

import argparse
import json
import pickle
import shutil
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "raw_data_package"
RAW = ROOT / "data" / "raw"

TABLES = ["DEMO", "DRUG", "REAC", "INDI", "OUTC", "RPSR", "THER"]


def load_ids() -> dict[str, set[str]]:
    with open(ROOT / "data" / "interim" / "stream_cache" / "meta.pkl", "rb") as f:
        meta = pickle.load(f)
    return {k: {str(x).strip() for x in v} for k, v in meta["ids"].items()}


def quarter_tag(q: str) -> str:
    """'2020Q2' -> '20Q2' (FAERS file naming)."""
    return q[2:]


def scan_table(table: str, ids: set[str], quarters: list[str], out_dir: Path) -> int:
    """Stream one table across all quarters, keep rows whose primaryid is in `ids`."""
    header = None
    kept = 0
    tmp = out_dir / f"{table}.txt"
    with open(tmp, "w", encoding="latin-1", newline="\n") as fh:
        for q in quarters:
            fp = RAW / q / f"{table}{quarter_tag(q)}.txt"
            if not fp.exists():
                print(f"  [miss] {fp.name}")
                continue
            with open(fp, "r", encoding="latin-1", errors="replace") as f:
                head = f.readline()
                if header is None:
                    header = head
                    fh.write(head)
                for line in f:
                    if not line.strip():
                        continue
                    pid = line.split("$", 1)[0].strip()
                    if pid in ids:
                        fh.write(line if line.endswith("\n") else line + "\n")
                        kept += 1
    print(f"  [scan] {table}: kept {kept:,} rows -> {tmp.name}")
    return kept


def to_csv(txt: Path, out_csv: Path) -> int:
    df = pd.read_csv(txt, sep="$", dtype=str, encoding="latin-1", on_bad_lines="skip")
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return len(df)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-scan", action="store_true", help="reuse existing INDI/RPSR extracts")
    args = ap.parse_args()

    RAWOUT = PKG / "01_faers_source_rows"
    RAWOUT.mkdir(parents=True, exist_ok=True)
    ids = load_ids()
    with open(ROOT / "data" / "interim" / "stream_cache" / "meta.pkl", "rb") as f:
        quarters = pickle.load(f)["quarters"]
    print(f"cases: PS {len(ids['PS']):,} | PS+SS {len(ids['PS+SS']):,} | ALL {len(ids['ALL']):,}")

    # ---------- 1. source rows ----------
    # All 7 tables are re-scanned at the WIDEST cohort (any role, 13,190 cases) so that
    # every table in the package covers the same case set. Which rows belong to the PS /
    # PS+SS analysis cohorts is then decided by 02_case_id_map, not by how the file was cut.
    all_ids = ids["ALL"]
    for t in TABLES:
        tmp = RAWOUT / f"{t}.txt"
        if args.skip_scan and tmp.exists():
            print(f"  [skip] {t}.txt exists")
            continue
        scan_table(t, all_ids, quarters, RAWOUT)

    rows = {}
    for t in TABLES:
        fp = RAWOUT / f"{t}.txt"
        if not fp.exists():
            print(f"  [warn] {t} missing")
            continue
        rows[t] = to_csv(fp, RAWOUT / f"{t}.csv")

    # ---------- 2. case-ID inclusion map ----------
    IDS = PKG / "02_case_id_map"
    IDS.mkdir(parents=True, exist_ok=True)
    allu = sorted(all_ids, key=lambda x: (len(x), x))
    idmap = pd.DataFrame({
        "primaryid": allu,
        "in_primary_suspect": [p in ids["PS"] for p in allu],
        "in_primary_or_secondary": [p in ids["PS+SS"] for p in allu],
        "in_any_role": True,
    })
    idmap.to_csv(IDS / "case_id_inclusion_map.csv", index=False, encoding="utf-8-sig")

    # ---------- 3. reference-population counts ----------
    REF = PKG / "03_reference_population"
    REF.mkdir(parents=True, exist_ok=True)
    summ = json.loads((ROOT / "results_full" / "reference_population_summary.json").read_text(encoding="utf-8"))
    flat = [{"metric": k, "value": json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}
            for k, v in summ.items()]
    pd.DataFrame(flat).to_csv(REF / "reference_population_summary.csv", index=False, encoding="utf-8-sig")
    print(f"  [ref] cohort {summ['n_ps']:,} | ref {summ['n_ref']:,} | indication-matched {summ['n_mig']:,}")

    # ---------- 4. download manifest (how to rebuild the 11 GB library) ----------
    MAN = PKG / "04_download_manifest"
    MAN.mkdir(parents=True, exist_ok=True)
    recs = []
    for q in quarters:
        tag = quarter_tag(q)
        for t in TABLES:
            fp = RAW / q / f"{t}{tag}.txt"
            if not fp.exists():
                continue
            with open(fp, "rb") as f:
                nlines = 0
                while True:
                    buf = f.read(8 << 20)
                    if not buf:
                        break
                    nlines += buf.count(b"\n")
                nlines -= 1  # header
            recs.append({
                "quarter": q,
                "table": t,
                "filename": fp.name,
                "bytes": fp.stat().st_size,
                "rows_excl_header": nlines,
                "quarter_zip_url": f"https://fis.fda.gov/content/Exports/faers_ascii_{q[:4]}q{q[-1]}.zip",
            })
    man = pd.DataFrame(recs)
    try:
        man.to_csv(MAN / "faers_source_manifest.csv", index=False, encoding="utf-8-sig")
    except PermissionError:
        # 文件可能正被表格编辑器打开；内容未变（季度清单稳定），跳过即可
        print("  [manifest] target locked by another app; keeping the existing copy")
    print(f"  [manifest] {len(man)} files, {man.bytes.sum()/1e9:.1f} GB across {man.quarter.nunique()} quarters")

    # ---------- 5. code ----------
    CODE = PKG / "05_code"
    CODE.mkdir(parents=True, exist_ok=True)
    for fn in ("ageutil.py", "download_faers.py", "faers_io.py", "extract_subset.py",
               "reference_population.py",
               "run_module1.py", "label_change.py", "ml_risk.py", "network_tox.py", "dock_prep.py"):
        shutil.copy2(ROOT / "src" / fn, CODE / fn)

    # ---------- 6. README ----------
    readme = (ROOT / "tools" / "raw_package_readme.md").read_text(encoding="utf-8")
    readme = (readme.replace("{{DATE}}", date.today().isoformat())
                    .replace("{{ROWS_DEMO}}", f"{rows.get('DEMO', 0):,}")
                    .replace("{{ROWS_DRUG}}", f"{rows.get('DRUG', 0):,}")
                    .replace("{{ROWS_REAC}}", f"{rows.get('REAC', 0):,}")
                    .replace("{{ROWS_INDI}}", f"{rows.get('INDI', 0):,}")
                    .replace("{{ROWS_RPSR}}", f"{rows.get('RPSR', 0):,}")
                    .replace("{{ROWS_OUT}}", f"{rows.get('OUTC', 0):,}")
                    .replace("{{ROWS_THER}}", f"{rows.get('THER', 0):,}")
                    .replace("{{N_FILES}}", f"{len(man):,}")
                    .replace("{{GB}}", f"{man.bytes.sum()/1e9:.1f}"))
    (PKG / "README.md").write_text(readme, encoding="utf-8")

    # ---------- 7. zip ----------
    zpath = ROOT / f"rimegepant_raw_data_package_{date.today().isoformat()}.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(PKG.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(PKG.parent))
    mb = zpath.stat().st_size / 1024 / 1024
    print(f"\npackage: {PKG}\nzip    : {zpath.name} ({mb:.1f} MB)")
    print("rows:", rows)


if __name__ == "__main__":
    main()
