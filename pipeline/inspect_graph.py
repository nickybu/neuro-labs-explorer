#!/usr/bin/env python3
"""Eyeball a collected graph: coverage, status split, and per-institution PI lists.

Written to sanity-check the PI list against what a human actually knows about
these institutions - the failure mode we care about is plausible-looking data
that is quietly wrong.

Usage
-----
    python3 pipeline/inspect_graph.py                          # overview
    python3 pipeline/inspect_graph.py --inst "Crick"           # PIs at one place
    python3 pipeline/inspect_graph.py --inst UCL --status active
    python3 pipeline/inspect_graph.py --pi "Friston"           # one PI in detail
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "data", "graph_neuro.json")


def load(path: str):
    with open(path) as f:
        g = json.load(f)
    return g, {n["id"]: n for n in g["nodes"]}


def overview(g: dict, byid: dict) -> None:
    m = g["meta"]
    print(f"generated : {m['generated']}")
    print(f"scope     : {m['scope']}")
    if m.get("partial"):
        miss = m.get("missingYears") or []
        span = f" ({miss[0]}-{miss[-1]})" if miss else ""
        print(f"!! PARTIAL : {len(miss)} year(s) not crawled{span}; "
              f"work counts and status understated")
    print(f"works     : {m.get('worksCollected', 0):,}")
    print(f"window    : {m['window']}")
    print(f"counts    : {json.dumps(m['counts'])}\n")

    pis = [n for n in g["nodes"] if n["type"] == "pi"]
    print("=== PIs by status ===")
    for s, c in Counter(p["status"] for p in pis).most_common():
        print(f"  {c:>7,}  {s}")

    print("\n=== top 20 institutions by PI count ===")
    c = Counter(p["institution"] for p in pis)
    act = Counter(p["institution"] for p in pis if p["status"] == "active")
    for i, n in c.most_common(20):
        print(f"  {n:>5} PIs ({act.get(i,0):>4} active)  {byid[i]['label']}")

    print("\n=== top 15 funders ===")
    fc = Counter(l["target"] for l in g["links"] if l["rel"] == "funded_by")
    for i, n in fc.most_common(15):
        print(f"  {n:>6}  {byid[i]['label']}")

    print("\n=== PI output distribution (last-authored works) ===")
    ws = sorted((p["works"] for p in pis), reverse=True)
    if ws:
        for q, lbl in [(0, "max"), (len(ws)//100, "p99"), (len(ws)//10, "p90"),
                       (len(ws)//2, "median"), (len(ws)-1, "min")]:
            print(f"  {lbl:>6}: {ws[min(q, len(ws)-1)]}")


def by_country(g: dict, byid: dict, limit: int) -> None:
    """PI counts per country - sanity-check regional coverage."""
    pis = [n for n in g["nodes"] if n["type"] == "pi"]
    tot: Counter = Counter()
    act: Counter = Counter()
    for p in pis:
        cc = (byid.get(p["institution"]) or {}).get("cc") or "??"
        tot[cc] += 1
        if p["status"] == "active":
            act[cc] += 1
    print(f"=== PIs by country ({len(tot)} countries) ===")
    for cc, n in tot.most_common(limit):
        print(f"  {cc:>3}  {n:>7,} PIs  ({act.get(cc, 0):>6,} active)")


def top_institutions(g: dict, byid: dict, cc: str | None, limit: int) -> None:
    """Top institutions, optionally for one country.

    This is the umbrella regression test. CNRS and Inserm are the #1 and #3
    institutions in Europe+NA by raw work count, so if either tops France here
    the demotion in ``_rank_inst`` has stopped working and every French lab has
    been swallowed by its parent organisation.
    """
    pis = [n for n in g["nodes"] if n["type"] == "pi"]
    if cc:
        pis = [p for p in pis
               if ((byid.get(p["institution"]) or {}).get("cc") or "").upper() == cc.upper()]
    c = Counter(p["institution"] for p in pis)
    act = Counter(p["institution"] for p in pis if p["status"] == "active")
    print(f"=== top institutions{' in ' + cc.upper() if cc else ''} "
          f"({len(c):,} total) ===")
    for i, n in c.most_common(limit):
        inst = byid.get(i) or {}
        print(f"  {n:>6} PIs ({act.get(i, 0):>5} active)  "
              f"{(inst.get('cc') or '??'):>3}  {inst.get('label')}")


def show_inst(g: dict, byid: dict, needle: str, status: str | None, limit: int) -> None:
    hits = [n for n in g["nodes"] if n["type"] == "institution"
            and needle.lower() in (n["label"] or "").lower()]
    if not hits:
        print(f"no institution matching {needle!r}")
        return
    for inst in hits[:5]:
        pis = [n for n in g["nodes"] if n["type"] == "pi"
               and n["institution"] == inst["id"]
               and (status is None or n["status"] == status)]
        pis.sort(key=lambda p: (-(p.get("lastYear") or 0), -p["works"]))
        print(f"\n=== {inst['label']}  ({len(pis)} PIs"
              f"{', status=' + status if status else ''}) ===")
        print(f"{'status':13}{'n':>4}{'corr':>5}  years        name")
        for p in pis[:limit]:
            print(f"  {p['status']:11}{p['works']:>4}{p.get('corresponding',0):>5}  "
                  f"{p.get('firstYear')}-{p.get('lastYear')}  {p['label']}")
        if len(pis) > limit:
            print(f"  ... {len(pis) - limit} more")


_TAGS: dict | None = None


def _tags() -> dict:
    """Per-PI tag records from data/tags_neuro.json, or {} when not built yet."""
    global _TAGS
    if _TAGS is None:
        path = os.path.join(ROOT, "data", "tags_neuro.json")
        try:
            with open(path) as f:
                _TAGS = json.load(f)["pis"]
        except (OSError, KeyError, ValueError):
            _TAGS = {}
    return _TAGS


def show_pi(g: dict, byid: dict, needle: str) -> None:
    hits = [n for n in g["nodes"] if n["type"] == "pi"
            and needle.lower() in (n["label"] or "").lower()]
    if not hits:
        print(f"no PI matching {needle!r}")
        return
    for p in sorted(hits, key=lambda x: -x["works"])[:8]:
        inst = byid.get(p["institution"], {}).get("label", "?")
        print(f"\n{p['label']}  [{p['id']}]")
        print(f"  {inst}  |  {p['status']}  |  {p['firstYear']}-{p['lastYear']}")
        print(f"  {p['works']} last-authored works, {p.get('corresponding',0)} corresponding")
        loc = byid.get(p["institution"], {})
        if loc.get("city"):
            print(f"  {loc['city']}, {loc.get('country') or loc.get('cc')}")
        rec = _tags().get(p["id"])
        if rec:
            fmt = lambda d: ", ".join(f"{k} x{v}" for k, v in d.items()) or "-"
            print(f"  model systems: {fmt(rec['o'])}")
            print(f"  methods:       {fmt(rec['m'])}  ({rec['n']} works in window)")
        for l in g["links"]:
            if l["source"] != p["id"]:
                continue
            if l["rel"] == "previously_at":
                print(f"    prev: {byid[l['target']]['label']} {l.get('years')} "
                      f"({l.get('works')} works)")
            elif l["rel"] == "funded_by":
                aw = ", ".join(l.get("awards") or [])
                print(f"    funder: {byid[l['target']]['label']} ({l.get('works')})"
                      + (f" [{aw}]" if aw else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", default=DEFAULT)
    ap.add_argument("--inst")
    ap.add_argument("--pi")
    ap.add_argument("--country", metavar="CC",
                    help="two-letter code; with --top-institutions, audit that country")
    ap.add_argument("--by-country", action="store_true",
                    help="PI counts per country")
    ap.add_argument("--top-institutions", action="store_true",
                    help="largest institutions (umbrella regression check)")
    ap.add_argument("--status", choices=["active", "winding_down", "inactive"])
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args()

    if not os.path.exists(a.graph):
        print(f"no graph at {a.graph} - has the crawl finished?")
        return
    g, byid = load(a.graph)
    if a.pi:
        show_pi(g, byid, a.pi)
    elif a.inst:
        show_inst(g, byid, a.inst, a.status, a.limit)
    elif a.by_country:
        by_country(g, byid, a.limit)
    elif a.top_institutions or a.country:
        top_institutions(g, byid, a.country, a.limit)
    else:
        overview(g, byid)


if __name__ == "__main__":
    main()
