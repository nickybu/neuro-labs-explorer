#!/usr/bin/env python3
"""Collect UK research institutions, their PIs, and career links from OpenAlex.

Builds ``data/graph.json`` with three node tiers (institution -> lab -> PI) and
three link kinds (has_lab, led_by, previously_at). Everything is real OpenAlex
data; relevance filtering rules live in ``config.py``.

Usage
-----
    python3 pipeline/collect.py                 # full UK run (exhaustive breadth)
    python3 pipeline/collect.py --limit 8       # first 8 institutions (quick test)
    python3 pipeline/collect.py --max-pis 15    # override PIs kept per institution
    python3 pipeline/collect.py --out data/sample.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(ROOT, "data", "graph.json")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _get(path: str, params: dict) -> dict:
    """GET an OpenAlex endpoint with the polite pool and basic retry."""
    params = {**params, "mailto": C.MAILTO}
    url = f"{C.API_ROOT}/{path}?{urllib.parse.urlencode(params)}"
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"neuro-labs-explorer ({C.MAILTO})"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - network flakiness; retry with backoff
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed after retries: {url}\n{last_err}")


def _short_id(openalex_url: str) -> str:
    """'https://openalex.org/I40120149' -> 'I40120149'."""
    return openalex_url.rstrip("/").split("/")[-1] if openalex_url else ""


# ---------------------------------------------------------------------------
# Relevance classification (mirrors config.py; pure functions of a PI's topics)
# ---------------------------------------------------------------------------
def _topic_relevant(topic: dict) -> bool:
    field_id = str(topic.get("field", {}).get("id", "")).split("/")[-1]
    if field_id in C.ALWAYS_RELEVANT_FIELDS:
        return True
    if field_id in C.KEYWORD_GATED_FIELDS:
        text = f"{topic.get('display_name','')} {topic.get('subfield',{}).get('display_name','')}".lower()
        return any(k in text for k in C.RELEVANCE_KEYWORDS)
    return False


def _areas_for(topics: list[dict]) -> list[str]:
    """Map a PI's topics to the coarse research areas used for UI filtering."""
    text = " ".join(
        f"{t.get('display_name','')} {t.get('subfield',{}).get('display_name','')}"
        for t in topics
    ).lower()
    areas = [area for area, kws in C.AREA_RULES.items() if any(k in text for k in kws)]
    return areas


def _author_is_relevant(topics: list[dict]) -> bool:
    """Relevant only if the leading research is in scope, not a stray topic.

    True when the primary topic is relevant, or when at least
    ``MIN_RELEVANT_TOPICS`` of the top ``TOPIC_WINDOW`` topics are relevant.
    """
    if not topics:
        return False
    window = topics[:C.TOPIC_WINDOW]
    if _topic_relevant(window[0]):
        return True
    return sum(_topic_relevant(t) for t in window) >= C.MIN_RELEVANT_TOPICS


# ---------------------------------------------------------------------------
# Collection stages
# ---------------------------------------------------------------------------
def fetch_institutions(limit: int | None) -> list[dict]:
    """All UK institutions of the configured types, above a size floor."""
    out: list[dict] = []
    for inst_type in C.INSTITUTION_TYPES:
        cursor = "*"
        while cursor:
            data = _get("institutions", {
                "filter": f"country_code:GB,type:{inst_type},works_count:>{C.INSTITUTION_MIN_WORKS}",
                "select": "id,ror,display_name,type,homepage_url,works_count,cited_by_count",
                "sort": "works_count:desc",
                "per-page": 200,
                "cursor": cursor,
            })
            for i in data["results"]:
                out.append({
                    "id": _short_id(i["id"]),
                    "ror": i.get("ror"),
                    "label": i["display_name"],
                    "instType": i.get("type"),
                    "homepage": i.get("homepage_url"),
                    "works": i.get("works_count", 0),
                    "citations": i.get("cited_by_count", 0),
                })
            cursor = data["meta"].get("next_cursor")
            if limit and len(out) >= limit:
                return out[:limit]
    # Sort by output so the most significant institutions are processed first.
    out.sort(key=lambda x: x["works"], reverse=True)
    return out[:limit] if limit else out


def fetch_pis(inst: dict, max_pis: int) -> list[dict]:
    """Top-cited authors currently at an institution that pass the relevance test."""
    data = _get("authors", {
        "filter": (f"last_known_institutions.id:{inst['id']},"
                   f"works_count:{C.AUTHOR_MIN_WORKS}-{C.AUTHOR_MAX_WORKS},"
                   f"cited_by_count:>{C.AUTHOR_MIN_CITATIONS}"),
        "select": "id,display_name,orcid,works_count,cited_by_count,summary_stats,affiliations,topics",
        "sort": "cited_by_count:desc",
        "per-page": C.CANDIDATES_PER_INSTITUTION,
    })
    pis = []
    for a in data.get("results", []):
        topics = a.get("topics", [])
        if not _author_is_relevant(topics):
            continue
        areas = _areas_for(topics)
        if not areas:
            continue
        pis.append({
            "id": _short_id(a["id"]),
            "label": a["display_name"],
            "orcid": a.get("orcid"),
            "works": a.get("works_count", 0),
            "citations": a.get("cited_by_count", 0),
            "hindex": (a.get("summary_stats") or {}).get("h_index"),
            "areas": areas,
            "topics": [t.get("display_name") for t in topics[:6]],
            "primaryTopic": topics[0].get("display_name") if topics else None,
            "affiliations": a.get("affiliations", []),
        })
        if len(pis) >= max_pis:
            break
    return pis


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
def build_graph(limit: int | None, max_pis: int) -> dict:
    print(f"[1/3] fetching UK institutions (types={C.INSTITUTION_TYPES}) ...", flush=True)
    institutions = fetch_institutions(limit)
    print(f"      -> {len(institutions)} institutions", flush=True)

    nodes: dict[str, dict] = {}
    links: list[dict] = []
    inst_ids = {i["id"] for i in institutions}

    for inst in institutions:
        nodes[inst["id"]] = {
            "id": inst["id"], "type": "institution", "label": inst["label"],
            "instType": inst["instType"], "homepage": inst["homepage"],
            "ror": inst["ror"], "works": inst["works"], "citations": inst["citations"],
            "areas": set(),
        }

    print(f"[2/3] fetching PIs per institution (<= {max_pis} each) ...", flush=True)
    claimed: set[str] = set()  # a PI belongs to one institution (the first/most prominent)
    for n, inst in enumerate(institutions, 1):
        try:
            pis = fetch_pis(inst, max_pis)
        except Exception as e:  # noqa: BLE001 - keep going if one org errors
            print(f"      ! {inst['label']}: {e}", flush=True)
            continue
        pis = [p for p in pis if p["id"] not in claimed]
        print(f"      [{n}/{len(institutions)}] {inst['label'][:42]:42} -> {len(pis)} PIs", flush=True)
        for pi in pis:
            claimed.add(pi["id"])
            lab_id = f"lab:{pi['id']}"
            # Lab node = the PI's research group (OpenAlex has no lab entity).
            nodes[lab_id] = {
                "id": lab_id, "type": "lab",
                "label": f"{pi['label'].split()[-1]} Group",
                "institution": inst["id"], "pi": pi["id"],
                "primaryTopic": pi["primaryTopic"], "areas": list(pi["areas"]),
            }
            nodes[pi["id"]] = {
                "id": pi["id"], "type": "pi", "label": pi["label"],
                "institution": inst["id"], "lab": lab_id,
                "orcid": pi["orcid"], "works": pi["works"], "citations": pi["citations"],
                "hindex": pi["hindex"], "areas": list(pi["areas"]),
                "topics": pi["topics"], "primaryTopic": pi["primaryTopic"],
            }
            links.append({"source": inst["id"], "target": lab_id, "rel": "has_lab"})
            links.append({"source": lab_id, "target": pi["id"], "rel": "led_by"})
            nodes[inst["id"]]["areas"].update(pi["areas"])

            # Career edges: previous UK institutions in our node set.
            for aff in pi["affiliations"]:
                prev = _short_id(aff.get("institution", {}).get("id", ""))
                years = aff.get("years", [])
                if prev and prev != inst["id"] and prev in inst_ids:
                    links.append({
                        "source": pi["id"], "target": prev,
                        "rel": "previously_at", "years": sorted(years),
                    })
        time.sleep(0.2)  # be polite

    # Prune institutions that ended up with no relevant labs, and finalise areas.
    kept_insts = {l["source"] for l in links if l["rel"] == "has_lab"}
    for inst_id in list(nodes):
        node = nodes[inst_id]
        if node["type"] == "institution":
            if inst_id not in kept_insts:
                del nodes[inst_id]
            else:
                node["areas"] = sorted(node["areas"])

    # Drop career edges whose target institution was pruned.
    live = set(nodes)
    links = [l for l in links if l["source"] in live and l["target"] in live]

    counts = {
        "institutions": sum(1 for x in nodes.values() if x["type"] == "institution"),
        "labs": sum(1 for x in nodes.values() if x["type"] == "lab"),
        "pis": sum(1 for x in nodes.values() if x["type"] == "pi"),
        "career_links": sum(1 for l in links if l["rel"] == "previously_at"),
    }
    print(f"[3/3] assembled graph: {counts}", flush=True)

    return {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "source": "OpenAlex (https://openalex.org)",
            "scope": "United Kingdom",
            "counts": counts,
            "areas": list(C.AREA_RULES.keys()),
            "notes": ("Labs are derived from each PI's OpenAlex research group; "
                      "'previously_at' edges are institution-level career moves "
                      "(within the UK institution set)."),
        },
        "nodes": list(nodes.values()),
        "links": links,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="max institutions (test runs)")
    ap.add_argument("--max-pis", type=int, default=C.MAX_PIS_PER_INSTITUTION)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    graph = build_graph(args.limit, args.max_pis)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(graph, f, indent=None, separators=(",", ":"))
    size_kb = os.path.getsize(args.out) / 1024
    print(f"wrote {args.out} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
