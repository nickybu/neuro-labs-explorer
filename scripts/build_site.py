#!/usr/bin/env python3
"""Build the static site payload for GitHub Pages into ``site/``.

The local app loads 46 MB gzipped, which is far too heavy for a public page.
This writes a trimmed copy: active labs only, integer coordinates, fields the
UI never reads removed, and publication lists capped.

GitHub Pages (Fastly) gzips JSON on the fly, so the files stay **plain .json**.
A pre-gzipped ``.gz`` would be served as an opaque binary with no
``Content-Encoding`` and would forfeit that.

    python3 scripts/build_site.py                 # -> site/data/*.json
    python3 scripts/build_site.py --statuses active,winding_down

The workflow in .github/workflows/pages.yml does not run this: the built data
is uploaded once to a GitHub Release and downloaded at deploy time, because a
115 MB file cannot live in git.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "site", "data")

# Verified unread by web/index.html, web/data.js and web/search.html.
DROP_PI_FIELDS = ("labLabel", "areas", "corresponding")
DROP_INST_FIELDS = ("areas",)
LED_CAP = 10                      # most recent led papers kept per PI
CO_CAP = 2                        # most recent co-authored papers kept per PI


def _load(name: str) -> dict:
    path = os.path.join(DATA, name)
    with open(path) as f:
        return json.load(f)


def _write(name: str, obj: dict) -> tuple[float, float]:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    raw = os.path.getsize(path)
    # Only to report what a visitor will actually download; not shipped.
    with open(path, "rb") as src:
        gz = len(gzip.compress(src.read(), 6))
    print(f"  {name:<22} {raw / 1e6:7.1f} MB raw   {gz / 1e6:6.1f} MB over the wire")
    return raw / 1e6, gz / 1e6


def build_graph(graph: dict, statuses: set[str]) -> tuple[dict, set[str]]:
    pis = [n for n in graph["nodes"] if n["type"] == "pi" and n["status"] in statuses]
    keep_pi = {n["id"] for n in pis}
    keep_inst, keep_funder = set(), set()
    for n in pis:
        keep_inst.add(n["institution"])
        keep_inst.update(n.get("currentInstitutions") or [])
        keep_inst.update(a["id"] for a in n.get("institutions") or [])   # career history
        keep_funder.update(f["id"] for f in n.get("funders") or [])

    nodes = []
    for n in graph["nodes"]:
        t = n["type"]
        if t == "pi" and n["id"] not in keep_pi:
            continue
        if t == "institution" and n["id"] not in keep_inst:
            continue
        if t == "funder" and n["id"] not in keep_funder:
            continue
        n = dict(n)
        for f in (DROP_PI_FIELDS if t == "pi" else DROP_INST_FIELDS if t == "institution" else ()):
            n.pop(f, None)
        n["x"], n["y"] = round(n["x"]), round(n["y"])
        nodes.append(n)

    live = {n["id"] for n in nodes}
    links = [l for l in graph["links"] if l["source"] in live and l["target"] in live]

    by_status = Counter(n["status"] for n in nodes if n["type"] == "pi")
    counts = {
        "institutions": sum(1 for n in nodes if n["type"] == "institution"),
        "pis": len(keep_pi),
        "funders": sum(1 for n in nodes if n["type"] == "funder"),
        "nodes": len(nodes), "links": len(links),
        "affiliations": sum(1 for l in links if l["rel"] == "affiliated_with"),
        "funding_links": sum(1 for l in links if l["rel"] == "funded_by"),
        "pis_by_status": dict(by_status),
    }
    meta = {**graph["meta"], "counts": counts,
            "build": {"variant": "+".join(sorted(statuses)) + f", led<={LED_CAP}, co<={CO_CAP}",
                      "generated": datetime.now(timezone.utc).isoformat(),
                      "source": "data/graph_neuro.json"}}
    return {"meta": meta, "nodes": nodes, "links": links}, keep_pi


def build_tags(tags: dict, keep_pi: set[str]) -> dict:
    pis = {p: rec for p, rec in tags["pis"].items() if p in keep_pi}
    # Facet counts must be recomputed for the subset or every chip overstates.
    tag_pis, tag_works = Counter(), Counter()
    used_inst = set()
    for rec in pis.values():
        for g in ("m", "o"):
            for tid, k in (rec.get(g) or {}).items():
                tag_pis[tid] += 1
                tag_works[tid] += k
        for ca in rec.get("ca") or []:
            used_inst.add(ca[0])
    out_tags = {g: [{**t, "pis": tag_pis[t["id"]], "works": tag_works[t["id"]]} for t in lst]
                for g, lst in tags["tags"].items()}
    co_links = sum(len(rec.get("ca") or []) for rec in pis.values())
    meta = {**tags["meta"], "pisTagged": len(pis),
            "coAffiliation": {**tags["meta"].get("coAffiliation", {}),
                              "pis": sum(1 for r in pis.values() if r.get("ca")), "links": co_links}}
    return {"meta": meta, "tags": out_tags,
            "coInstitutions": {i: m for i, m in (tags.get("coInstitutions") or {}).items() if i in used_inst},
            "pis": pis}


def build_works(works: dict, keep_pi: set[str]) -> dict:
    pos = lambda w: w[4] if len(w) > 4 else "l"
    out, led_totals = {}, {}
    n_led = n_co = 0
    for pid, rows in works["pis"].items():
        if pid not in keep_pi:
            continue
        led = [w for w in rows if pos(w) == "l"]
        co = [w for w in rows if pos(w) != "l"][:CO_CAP]
        if len(led) > LED_CAP:
            led_totals[pid] = len(led)
            led = led[:LED_CAP]
        out[pid] = led + co
        n_led += len(led); n_co += len(co)
    return {"meta": {**works["meta"], "ledCapPerPI": LED_CAP, "coauthorCapPerPI": CO_CAP,
                     "ledListed": n_led, "coauthorListed": n_co, "worksListed": n_led + n_co},
            "ledTotals": led_totals,
            "coTotals": {p: n for p, n in (works.get("coTotals") or {}).items() if p in keep_pi},
            "pis": out}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--statuses", default="active",
                    help="comma-separated PI statuses to publish (default: active)")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    statuses = {s.strip() for s in args.statuses.split(",") if s.strip()}
    globals()["OUT"] = args.out

    print(f"[build_site] statuses={sorted(statuses)} led<={LED_CAP} co<={CO_CAP}")
    graph, keep_pi = build_graph(_load("graph_neuro.json"), statuses)
    tags = build_tags(_load("tags_neuro.json"), keep_pi)
    works = build_works(_load("works_neuro.json"), keep_pi)

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    total_raw = total_gz = 0
    for name, obj in (("graph_neuro.json", graph), ("tags_neuro.json", tags),
                      ("works_neuro.json", works)):
        raw, gz = _write(name, obj)
        total_raw += raw; total_gz += gz

    c = graph["meta"]["counts"]
    print(f"  {c['pis']:,} labs · {c['institutions']:,} institutions · {c['funders']:,} funders · "
          f"{c['links']:,} links")
    print(f"  total {total_raw:.1f} MB raw, {total_gz:.1f} MB over the wire "
          f"(Pages gzips these for us)")


if __name__ == "__main__":
    main()
