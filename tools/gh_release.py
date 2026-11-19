# -*- coding: utf-8 -*-
"""Create (or update) a GitHub release and upload the archive asset.

Usage:
    GH_TOKEN=xxx python tools/gh_release.py --tag v1.0.3 \
        --file submission/rimegepant-hypersensitivity_v1.0.3.zip --notes-file notes.md

Idempotent: if the release already exists it is updated and the asset is
re-uploaded (replacing a same-named asset).
"""
import argparse
import json
import os
import sys

import requests

REPO = "15817323032/rimegepant-hypersensitivity"
API = "https://api.github.com"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--notes-file", default=None)
    ap.add_argument("--body", default=None)
    args = ap.parse_args()

    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GH_TOKEN not set")

    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    body = args.body or ""
    if args.notes_file:
        with open(args.notes_file, encoding="utf-8") as fh:
            body = fh.read()

    name = args.name or args.tag

    # does the release exist?
    r = s.get(f"{API}/repos/{REPO}/releases/tags/{args.tag}", timeout=60)
    if r.status_code == 200:
        rel = r.json()
        print(f"release exists: {rel['html_url']}")
        ru = s.patch(f"{API}/repos/{REPO}/releases/{rel['id']}",
                     json={"name": name, "body": body}, timeout=60)
        ru.raise_for_status()
        rel = ru.json()
    elif r.status_code == 404:
        rp = s.post(f"{API}/repos/{REPO}/releases",
                    json={"tag_name": args.tag, "name": name, "body": body,
                          "draft": False, "prerelease": False}, timeout=60)
        if rp.status_code >= 300:
            sys.exit(f"create failed {rp.status_code}: {rp.text[:400]}")
        rel = rp.json()
        print(f"release created: {rel['html_url']}")
    else:
        sys.exit(f"lookup failed {r.status_code}: {r.text[:300]}")

    # drop a same-named asset, then upload
    fname = os.path.basename(args.file)
    for a in rel.get("assets", []):
        if a["name"] == fname:
            s.delete(f"{API}/repos/{REPO}/releases/assets/{a['id']}",
                     timeout=60)
            print(f"removed stale asset {fname}")

    up_url = rel["upload_url"].split("{")[0]
    size = os.path.getsize(args.file)
    print(f"uploading {fname} ({size/1048576:.1f} MB) ...")
    with open(args.file, "rb") as fh:
        ru = s.post(f"{up_url}?name={fname}",
                    headers={"Content-Type": "application/zip"},
                    data=fh, timeout=900)
    if ru.status_code >= 300:
        sys.exit(f"upload failed {ru.status_code}: {ru.text[:300]}")
    asset = ru.json()
    print(f"asset uploaded: {asset['name']} {asset['size']/1048576:.1f} MB")
    print(f"release url: {rel['html_url']}")


if __name__ == "__main__":
    main()
