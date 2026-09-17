#!/usr/bin/env python3
"""Fetch institution geo (city, region, country, lat/lon) plus ROR and homepage.

The works crawl only sees the institution stub embedded in each authorship
(id, name, type, country code). City and coordinates live on the
``/institutions`` endpoint, which accepts 100 ids per request - so the whole
graph costs ~47 requests. Records are cached raw and the merge writes only the
handful of fields the UI needs onto the institution nodes, in place, without
touching x/y (no layout re-run).

    python3 pipeline/fetch_institutions.py                    # fetch missing, then merge
    python3 pipeline/fetch_institutions.py --fetch-only
    python3 pipeline/fetch_institutions.py --merge-only
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import collect_neuro as CN  # noqa: E402

ROOT, CACHE = CN.ROOT, CN.CACHE
DEFAULT_GRAPH = os.path.join(ROOT, "data", "graph_neuro.json")
CACHE_FILE = os.path.join(CACHE, "institutions.jsonl.gz")
SELECT = ("id,display_name,type,country_code,geo,ror,homepage_url,lineage,"
          "works_count,cited_by_count,ids")
BATCH = 100


def load_cache() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if os.path.exists(CACHE_FILE):
        with gzip.open(CACHE_FILE, "rt") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    out[r["id"]] = r
    return out


def graph_institution_ids(graph_path: str) -> list[str]:
    with open(graph_path) as f:
        g = json.load(f)
    return [n["id"] for n in g["nodes"] if n["type"] == "institution"]


def fetch(ids: list[str], retry_missing: bool = False) -> None:
    os.makedirs(CACHE, exist_ok=True)
    cached = load_cache()
    todo = [i for i in ids if i not in cached or (retry_missing and cached[i].get("missing"))]
    print(f"[fetch] {len(ids):,} institutions | {len(cached):,} cached | {len(todo):,} to fetch "
          f"(~{(len(todo) + BATCH - 1) // BATCH} requests)", flush=True)
    if not todo:
        return
    got = 0
    with gzip.open(CACHE_FILE, "at") as out:
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            try:
                d = CN._get("institutions", {"filter": "ids.openalex:" + "|".join(batch),
                                             "select": SELECT, "per-page": BATCH})
            except CN.BudgetExhausted as e:
                print(f"      ! {e}; {got:,} fetched so far, re-run to resume", flush=True)
                return
            seen = set()
            for r in d["results"]:
                r["id"] = CN._sid(r.get("id"))
                seen.add(r["id"])
                out.write(json.dumps(r, separators=(",", ":")) + "\n")
                got += 1
            for iid in batch:
                if iid not in seen:          # merged/deleted upstream
                    out.write(json.dumps({"id": iid, "missing": True}) + "\n")
            out.flush()
            print(f"      batch {i // BATCH + 1}: {len(seen)}/{len(batch)} found", flush=True)
    print(f"      fetched {got:,}; cache now {os.path.getsize(CACHE_FILE) / 1e3:.0f} KB")


def geo_fields(rec: dict) -> dict:
    geo = rec.get("geo") or {}
    out = {
        "city": geo.get("city"), "region": geo.get("region"), "country": geo.get("country"),
        "lat": geo.get("latitude"), "lon": geo.get("longitude"),
        "ror": rec.get("ror"), "homepage": rec.get("homepage_url"),
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def _fingerprint(nodes: list[dict]) -> str:
    h = hashlib.md5()
    for n in nodes:
        h.update(f"{n['id']}:{n.get('x')}:{n.get('y')};".encode())
    return h.hexdigest()


def merge(graph_path: str) -> None:
    cached = load_cache()
    with open(graph_path) as f:
        g = json.load(f)
    before = _fingerprint(g["nodes"])
    n_inst = n_city = n_nogeo = 0
    for n in g["nodes"]:
        if n["type"] != "institution":
            continue
        n_inst += 1
        rec = cached.get(n["id"])
        if not rec or rec.get("missing"):
            n_nogeo += 1
            continue
        fields = geo_fields(rec)
        n.update(fields)
        if "city" in fields:
            n_city += 1
    g["meta"]["enriched"] = {**(g["meta"].get("enriched") or {}),
                             "institutions": datetime.now(timezone.utc).isoformat(),
                             "withCity": n_city}
    after = _fingerprint(g["nodes"])
    assert before == after, "x/y fingerprint changed during merge - aborting"

    tmp = graph_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(g, f, separators=(",", ":"))
    os.replace(tmp, graph_path)
    gz = graph_path + ".gz"
    with open(graph_path, "rb") as src, gzip.open(gz + ".tmp", "wb", 6) as dst:
        dst.writelines(src)
    os.replace(gz + ".tmp", gz)
    print(f"[merge] {n_inst:,} institutions | {n_city:,} with city | {n_nogeo:,} without a "
          f"record | positions fingerprint {before[:10]} unchanged | "
          f"{os.path.getsize(graph_path) / 1e6:.1f} MB / {os.path.getsize(gz) / 1e6:.1f} MB gz")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", default=DEFAULT_GRAPH)
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--retry-missing", action="store_true")
    args = ap.parse_args()
    if not args.merge_only:
        fetch(graph_institution_ids(args.graph), args.retry_missing)
    if not args.fetch_only:
        merge(args.graph)


if __name__ == "__main__":
    main()
