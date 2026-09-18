#!/usr/bin/env python3
"""Collect neuroscience PIs from OpenAlex, keyed on last-authorship.

An earlier "top-cited authors per institution" approach truncated before
filtering and so returned fewer PIs for Oxford than for Edge Hill. Here a PI is
defined by what they actually publish:

    a last author on >= MIN_LAST_AUTHOR_WORKS neuroscience works
    within the collection window, affiliated to an in-region institution

Rather than paging authors per institution, this makes ONE pass over works and
buckets authors by institution afterwards, removing the sampling bias entirely.

Two properties make this affordable at global scale:

* **The crawl is region-agnostic.** We fetch worldwide and decide region at
  aggregation time from the ``cc`` already stored on every institution. Adding
  a country is then a re-run from cache, not another 14,574 API requests.
* **Everything streams.** Works are never materialised as a list; the UK cache
  alone peaks at 852 MB that way, and worldwide would need ~13 GB.

Crawling is sliced by publication year. Each slice is an independently cached,
permanent artefact, so a multi-day crawl resumes at slice granularity and a
later refresh re-fetches one year rather than the whole corpus.

Usage
-----
    python3 pipeline/collect_neuro.py --years 2026:1996        # worldwide crawl
    python3 pipeline/collect_neuro.py --years 2026:2016        # recent years only
    python3 pipeline/collect_neuro.py --region euna            # build from cache
    python3 pipeline/collect_neuro.py --region gb --legacy-cache
"""
from __future__ import annotations

import argparse
import gzip
import itertools
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(ROOT, "data", "graph_neuro.json")

# OpenAlex polite pool: identify ourselves on every request.
MAILTO = "you@example.com"
API_ROOT = "https://api.openalex.org"
CACHE = os.path.join(ROOT, "data", "cache")

# --- collection window / scope -------------------------------------------
FIELD_NEUROSCIENCE = "28"
FROM_DATE = "1996-01-01"          # 30-year window
MIN_LAST_AUTHOR_WORKS = 2
# Institutions that are primary for fewer PIs than this are dropped - the long
# tail is mostly OpenAlex affiliation-parsing junk ("Department for Transport").
MIN_PIS_PER_INSTITUTION = 2

# --- activity model (year of most recent last-authored work) --------------
ACTIVE_FROM = 2023                # >= this  -> actively running a lab
WINDING_FROM = 2018               # >= this  -> winding down
#                                   otherwise -> inactive / retired

# Institution types that can plausibly employ a PI. Funders get their own tier
# (OpenAlex funder IDs are F-prefixed, so they never collide with institutions).
EMPLOYER_TYPES = {"education", "facility", "healthcare", "government",
                  "nonprofit", "company", "other"}


def _load_umbrellas() -> set[str]:
    """Parent orgs that shadow their members (CNRS, Inserm, University of London).

    Demoted rather than dropped - see ``_rank_inst``. Kept in a data file so the
    list can be tuned from per-country audits without touching code.
    """
    path = os.path.join(HERE, "umbrellas.json")
    try:
        with open(path) as f:
            return set(json.load(f)["umbrellas"])
    except (OSError, KeyError, ValueError) as e:
        print(f"! could not read {path} ({e}); umbrella demotion is OFF", flush=True)
        return set()


UMBRELLA_INSTITUTIONS = _load_umbrellas()

# Region presets, applied at aggregation time against each institution's country
# code. The crawl itself is worldwide, so switching region costs no API calls.
REGIONS: dict[str, set[str] | None] = {
    "world": None,
    "gb": {"GB"},
    "euna": {
        # Europe
        "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CY", "CZ", "DK", "EE",
        "FI", "FR", "DE", "GR", "HU", "IS", "IE", "IT", "LV", "LI", "LT", "LU",
        "MT", "MD", "MC", "ME", "NL", "MK", "NO", "PL", "PT", "RO", "RS", "SK",
        "SI", "ES", "SE", "CH", "UA", "GB", "XK", "SM", "VA",
        # North America
        "US", "CA", "MX",
    },
}

PAGE = 200


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class BudgetExhausted(RuntimeError):
    """OpenAlex daily credit budget is spent (HTTP 429). Resumable, not fatal."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        hrs = retry_after / 3600
        super().__init__(f"OpenAlex daily credit budget exhausted; resets in ~{hrs:.1f}h")


# Optional API key. Anonymous callers get $0.10/day; a free key raises it to $1/day.
# Never hard-code it here - export OPENALEX_API_KEY, or put the key on its own
# in a `.openalex_key` file at the project root (read below, never logged).
def _load_api_key() -> str:
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(os.path.join(ROOT, ".openalex_key")) as f:
            return f.read().strip()
    except OSError:
        return ""


API_KEY = _load_api_key()


def _safe(url: str) -> str:
    """Redact the API key before a URL reaches a log or traceback."""
    return re.sub(r"(api_key=)[^&]*", r"\1***", url)


def _get(path: str, params: dict) -> dict:
    """GET an OpenAlex endpoint with the polite pool and backoff.

    Raises BudgetExhausted on 429 so callers can checkpoint and resume tomorrow
    rather than losing the crawl.
    """
    params = {**params, "mailto": MAILTO}
    if API_KEY:
        params["api_key"] = API_KEY
    url = f"{API_ROOT}/{path}?{urllib.parse.urlencode(params)}"
    last_err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": f"neuro-labs-explorer ({MAILTO})"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 400:  # a bad filter will never succeed; fail loudly
                raise RuntimeError(
                    f"bad request: {_safe(url)}\n{e.read().decode()[:400]}") from e
            if e.code == 429:  # out of credits - retrying today cannot help
                raise BudgetExhausted(int(e.headers.get("X-RateLimit-Reset") or 0)) from e
            last_err = e
            time.sleep(2.0 * (attempt + 1))
        except Exception as e:  # noqa: BLE001 - network flakiness
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"request failed after retries: {_safe(url)}\n{last_err}")


def _budget() -> tuple[int, float]:
    """Remaining credits and USD on the current key, via a cheap singleton call."""
    url = f"{API_ROOT}/works/W2741809807?select=id&mailto={MAILTO}"
    if API_KEY:
        url += f"&api_key={API_KEY}"
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "nle"}), timeout=30) as r:
            h = r.headers
            return int(h.get("X-RateLimit-Remaining") or 0), \
                float(h.get("X-RateLimit-Remaining-USD") or 0)
    except urllib.error.HTTPError as e:
        return 0, 0.0
    except Exception:  # noqa: BLE001
        return -1, -1.0


def _sid(url: str | None) -> str:
    """'https://openalex.org/I40120149' -> 'I40120149'."""
    return (url or "").rstrip("/").split("/")[-1]


def _norm_title(t: str | None) -> str:
    """Normalised title, used to collapse a preprint and its published version."""
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())[:120]


# ---------------------------------------------------------------------------
# Stage 1 - crawl works
# ---------------------------------------------------------------------------
SELECT_FIELDS = ("id,title,publication_year,type,cited_by_count,"
                 "primary_topic,authorships,funders,awards")


def _atomic_write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def _slice_paths(year: int) -> tuple[str, str, str]:
    stem = os.path.join(CACHE, f"works_{FIELD_NEUROSCIENCE}_world_{year}")
    return stem + ".jsonl.gz", stem + ".part.jsonl.gz", stem + ".state.json"


def crawl_slice(year: int, use_cache: bool = True) -> bool:
    """Fetch one publication year worldwide into its own cache file.

    Pages append to a gzip part file with the cursor checkpointed alongside, so
    a 429 or Ctrl-C costs one page. Returns True if the slice is complete.
    """
    os.makedirs(CACHE, exist_ok=True)
    cache_file, part_file, state_file = _slice_paths(year)
    if use_cache and os.path.exists(cache_file):
        return True

    filt = (f"primary_topic.field.id:{FIELD_NEUROSCIENCE},"
            f"from_publication_date:{year}-01-01,"
            f"to_publication_date:{year}-12-31")

    n = 0
    cursor = "*"
    if use_cache and os.path.exists(part_file) and os.path.exists(state_file):
        st = json.load(open(state_file))
        cursor, n = st.get("cursor") or "*", st.get("n", 0)
        if not cursor:
            return True
        print(f"      {year}: resuming at {n:,} works", flush=True)

    total = _get("works", {"filter": filt, "select": "id", "per-page": 1})["meta"]["count"]
    need = max(total - n, 0) // PAGE + 1
    cred, _ = _budget()
    print(f"  [{year}] {total:,} works | ~{need:,} pages | budget {cred:,}", flush=True)
    if 0 <= cred < need:
        print(f"        ! budget short by ~{need - cred:,}; will checkpoint and stop",
              flush=True)

    page, t0, complete = 0, time.time(), False
    out = gzip.open(part_file, "at")
    try:
        while cursor:
            d = _get("works", {"filter": filt, "select": SELECT_FIELDS,
                               "per-page": PAGE, "cursor": cursor})
            page += 1
            for w in d["results"]:
                out.write(json.dumps(_extract(w)) + "\n")
                n += 1
            cursor = d["meta"].get("next_cursor")
            out.flush()
            _atomic_write_json(state_file, {"cursor": cursor, "n": n})
            if page % 100 == 0:
                print(f"        page {page:>5,} | {n:>7,}/{total:,} "
                      f"({n / max(time.time() - t0, 1):.0f}/s)", flush=True)
            time.sleep(0.05)
        complete = True
    except BudgetExhausted as e:
        print(f"\n      ! {e}\n        {year} checkpointed at {n:,}/{total:,}; "
              f"re-run to resume.", flush=True)
    except KeyboardInterrupt:
        print(f"\n      interrupted; {year} checkpointed at {n:,}.", flush=True)
    finally:
        out.close()

    if complete:
        os.replace(part_file, cache_file)   # gzip members concatenate cleanly
        os.remove(state_file)
        print(f"        {year} done -> {os.path.getsize(cache_file)/1e6:.1f} MB",
              flush=True)
    return complete


def crawl_years(years: list[int], use_cache: bool = True) -> list[int]:
    """Crawl each year slice. Returns the years that completed."""
    print(f"[1/3] crawling {len(years)} year slice(s): "
          f"{min(years)}-{max(years)}", flush=True)
    done = []
    for y in years:
        try:
            if crawl_slice(y, use_cache):
                done.append(y)
            else:
                break        # out of budget; later slices would fail too
        except BudgetExhausted as e:
            print(f"      ! {e}", flush=True)
            break
    return done


def cached_years() -> list[int]:
    """Years with a complete slice on disk."""
    if not os.path.isdir(CACHE):
        return []
    out = []
    for fn in os.listdir(CACHE):
        m = re.fullmatch(rf"works_{FIELD_NEUROSCIENCE}_world_(\d{{4}})\.jsonl\.gz", fn)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def iter_works(years: list[int] | None = None, legacy_cache: str | None = None):
    """Stream work extracts from the slice caches, never materialising them."""
    if legacy_cache:
        with gzip.open(legacy_cache, "rt") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
        return
    for y in (years if years is not None else cached_years()):
        path, _, _ = _slice_paths(y)
        if not os.path.exists(path):
            continue
        with gzip.open(path, "rt") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def _extract(w: dict) -> dict:
    """Reduce a full work to the fields the graph needs."""
    seniors = []
    for a in w.get("authorships") or []:
        if a.get("author_position") != "last" and not a.get("is_corresponding"):
            continue
        aid = _sid((a.get("author") or {}).get("id"))
        if not aid:
            continue
        insts = [
            {"id": _sid(i.get("id")), "name": i.get("display_name"),
             "type": i.get("type"), "cc": i.get("country_code")}
            for i in (a.get("institutions") or []) if _sid(i.get("id"))
        ]
        seniors.append({
            "id": aid,
            "name": (a.get("author") or {}).get("display_name") or "?",
            "last": a.get("author_position") == "last",
            "corr": bool(a.get("is_corresponding")),
            "insts": insts,
        })
    pt = w.get("primary_topic") or {}
    return {
        "t": _norm_title(w.get("title")),
        "y": w.get("publication_year") or 0,
        "type": w.get("type"),
        "cites": w.get("cited_by_count") or 0,
        "topic": pt.get("display_name"),
        "sub": ((pt.get("subfield") or {}).get("display_name")),
        "seniors": seniors,
        "funders": [{"id": _sid(f.get("id")), "name": f.get("display_name")}
                    for f in (w.get("funders") or []) if _sid(f.get("id"))],
        "awards": [{"funder": _sid(a.get("funder_id")), "award": a.get("funder_award_id")}
                   for a in (w.get("awards") or []) if _sid(a.get("funder_id"))],
    }


# ---------------------------------------------------------------------------
# Stage 2 - aggregate into PIs
# ---------------------------------------------------------------------------
def status_for(last_year: int) -> str:
    if last_year >= ACTIVE_FROM:
        return "active"
    if last_year >= WINDING_FROM:
        return "winding_down"
    return "inactive"


def aggregate(works, region: str) -> tuple[dict, dict, dict, int]:
    """Fold streamed work extracts into author, institution and funder tallies.

    Takes an iterable, not a list: at worldwide scale the works never all exist
    in memory at once.
    """
    allow = REGIONS[region]
    print(f"[2/3] aggregating (region={region}, "
          f"{'worldwide' if allow is None else str(len(allow)) + ' countries'}) ...",
          flush=True)

    # Dedup on (title, last-author) rather than title alone. A preprint and its
    # published version share both; two unrelated papers titled "Autism" do not.
    # Title-only silently destroyed real last-authorship evidence at scale.
    seen: set[int] = set()
    dupe_titles: Counter = Counter()
    dupes = n_works = 0

    by_author: dict[str, dict] = defaultdict(
        lambda: {"name": "?", "insts": defaultdict(lambda: {"years": [], "n": 0}),
                 "years": [], "corr": 0, "cites": 0, "topics": Counter(),
                 "funders": defaultdict(int), "awards": {}})
    inst_meta: dict[str, dict] = {}
    funder_meta: dict[str, dict] = {}

    for r in works:
        n_works += 1
        if n_works % 250_000 == 0:
            print(f"      {n_works:,} works, {len(by_author):,} authors ...", flush=True)

        lasts = [s for s in r["seniors"] if s["last"]]
        if r["t"]:
            key = hash((r["t"], lasts[0]["id"] if lasts else ""))
            if key in seen:
                dupes += 1
                dupe_titles[r["t"][:48]] += 1
                continue
            seen.add(key)

        in_region = False
        for s in lasts:
            keep = [i for i in s["insts"]
                    if (allow is None or i["cc"] in allow)
                    and i["type"] in EMPLOYER_TYPES]
            if not keep:
                continue
            in_region = True
            a = by_author[s["id"]]
            a["name"] = s["name"]
            a["years"].append(r["y"])
            a["cites"] += r.get("cites") or 0
            if r.get("topic"):
                a["topics"][r["topic"]] += 1
            if s["corr"]:
                a["corr"] += 1
            for i in keep:
                inst_meta.setdefault(i["id"], {"id": i["id"], "label": i["name"],
                                               "instType": i["type"], "cc": i["cc"]})
                slot = a["insts"][i["id"]]
                slot["years"].append(r["y"])
                slot["n"] += 1
            for f in r["funders"]:
                a["funders"][f["id"]] += 1
            for aw in r["awards"]:
                if aw["award"]:
                    a["awards"].setdefault(aw["funder"], set()).add(aw["award"])

        if in_region:
            for f in r["funders"]:
                funder_meta.setdefault(f["id"], {"id": f["id"], "label": f["name"]})

    print(f"      {n_works:,} works streamed")
    print(f"      collapsed {dupes:,} preprint/published duplicates")
    if dupe_titles:
        # Audit: these should be recognisably editorial junk. Real-looking
        # titles here mean the dedup key is eating genuine evidence.
        top = ", ".join(f"{t}({c})" for t, c in dupe_titles.most_common(8))
        print(f"      most collapsed: {top}")
    print(f"      {len(by_author):,} distinct in-region last-authors")
    return by_author, inst_meta, funder_meta, n_works


# ---------------------------------------------------------------------------
# Stage 3 - build the graph
# ---------------------------------------------------------------------------
def _rank_inst(iid: str, slot: dict) -> tuple:
    """Sort key for choosing a PI's primary institution.

    Umbrellas sort last so CNRS or "University of London" never becomes a PI's
    primary while a real employer is available - but they remain in the PI's
    association list, because the affiliation is genuine. When an umbrella is
    the only candidate it still wins, which is correct.

    Then recency (a place they still publish from beats a bigger old one),
    then volume, then latest year.
    """
    last = max(slot["years"]) if slot["years"] else 0
    return (0 if iid in UMBRELLA_INSTITUTIONS else 1,
            1 if last >= ACTIVE_FROM else 0, slot["n"], last)


def build_graph(by_author: dict, inst_meta: dict, funder_meta: dict,
                min_works: int, min_pis_per_inst: int, region: str = "world") -> dict:
    nodes: dict[str, dict] = {}
    links: list[dict] = []

    pis = {aid: a for aid, a in by_author.items() if len(a["years"]) >= min_works}
    print(f"[3/3] {len(pis):,} PIs with >= {min_works} last-authored works", flush=True)

    # Drop thin institutions, then re-pick each PI's primary from what survives.
    # One extra pass settles the churn from reassignment.
    keep_insts: set[str] = set(inst_meta)
    for _ in range(2):
        tally: dict[str, int] = defaultdict(int)
        for a in pis.values():
            cand = {i: s for i, s in a["insts"].items() if i in keep_insts}
            if cand:
                tally[max(cand.items(), key=lambda kv: _rank_inst(*kv))[0]] += 1
        keep_insts = {i for i, n in tally.items() if n >= min_pis_per_inst}
    dropped = len(inst_meta) - len(keep_insts)
    print(f"      dropped {dropped:,} institutions with < {min_pis_per_inst} PIs "
          f"({len(keep_insts):,} kept)", flush=True)

    used_funders: set[str] = set()
    orphans = 0

    for aid, a in pis.items():
        cand = {i: s for i, s in a["insts"].items() if i in keep_insts}
        if not cand:                      # only ever published from thin institutions
            orphans += 1
            continue
        primary = max(cand.items(), key=lambda kv: _rank_inst(*kv))[0]
        years = sorted(y for y in a["years"] if y)
        last_year = max(years) if years else 0
        st = status_for(last_year)

        # Every association is kept ON THE NODE; `current` marks the ones still
        # live, so the detail panel can show a full career while the graph only
        # draws current edges. Joint appointments mean there can be several.
        assoc = []
        for iid, slot in sorted(cand.items(), key=lambda kv: -_rank_inst(*kv)[2]):
            ys = sorted(set(y for y in slot["years"] if y))
            assoc.append({
                "id": iid, "works": slot["n"],
                "firstYear": ys[0] if ys else None,
                "lastYear": ys[-1] if ys else None,
                "current": bool(ys and ys[-1] >= ACTIVE_FROM),
                "primary": iid == primary,
            })

        funders = sorted(a["funders"].items(), key=lambda kv: -kv[1])
        # The lab tier used to be a separate node, 1:1 with the PI and carrying
        # only "{Surname} Group". It was 21% of the payload for no information,
        # so it is now just a label on the PI.
        nodes[aid] = {
            "id": aid, "type": "pi", "label": a["name"],
            "labLabel": f"{a['name'].split()[-1]} Group",
            "institution": primary,
            "institutions": assoc,
            "currentInstitutions": [x["id"] for x in assoc if x["current"]],
            "funders": [{"id": f, "works": n} for f, n in funders[:8]],
            "works": len(a["years"]),          # last-authored, in-scope
            "corresponding": a["corr"],
            "citations": a.get("cites", 0),
            "topics": [t for t, _ in a["topics"].most_common(5)],
            "primaryTopic": (a["topics"].most_common(1) or [(None,)])[0][0],
            "firstYear": min(years) if years else None,
            "lastYear": last_year or None,
            "status": st,
            "areas": ["Neuroscience"],
        }

        # Edges are 54% of the payload, so the graph draws only the live ones:
        # current affiliations and the single strongest funder. Full history is
        # on the node above, and the UI can expand a focused subgraph from it.
        for x in assoc:
            if not x["current"] and x["id"] != primary:
                continue
            links.append({
                "source": aid, "target": x["id"], "rel": "affiliated_with",
                "years": [x["firstYear"], x["lastYear"]],
                "works": x["works"], "current": x["current"], "primary": x["primary"],
            })

        # Nodes for every funder the PI node references (funder nodes are tiny),
        # but an edge only for the strongest - otherwise the detail panel would
        # print raw IDs like "F4320311904" for the other seven.
        used_funders.update(f for f, _ in funders[:8])
        for fid, n in funders[:1]:
            links.append({"source": aid, "target": fid, "rel": "funded_by",
                          "works": n, "awards": sorted(a["awards"].get(fid, []))[:5]})

    if orphans:
        print(f"      dropped {orphans:,} PIs with no surviving institution", flush=True)

    for iid in keep_insts:
        m = inst_meta.get(iid, {"id": iid, "label": iid, "instType": None})
        nodes[iid] = {**m, "type": "institution", "areas": ["Neuroscience"]}
    for fid in used_funders:
        m = funder_meta.get(fid, {"id": fid, "label": fid})
        nodes[fid] = {**m, "type": "funder"}

    live = set(nodes)
    links = [l for l in links if l["source"] in live and l["target"] in live]

    by_status: dict[str, int] = defaultdict(int)
    for n in nodes.values():
        if n["type"] == "pi":
            by_status[n["status"]] += 1

    counts = {
        "institutions": sum(1 for x in nodes.values() if x["type"] == "institution"),
        "pis": sum(1 for x in nodes.values() if x["type"] == "pi"),
        "funders": sum(1 for x in nodes.values() if x["type"] == "funder"),
        "nodes": len(nodes),
        "links": len(links),
        "affiliations": sum(1 for l in links if l["rel"] == "affiliated_with"),
        "funding_links": sum(1 for l in links if l["rel"] == "funded_by"),
        "pis_by_status": dict(by_status),
    }
    print(f"      {counts}", flush=True)

    return {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "source": "OpenAlex (https://openalex.org)",
            "scope": f"{region} - neuroscience (OpenAlex field 28)",
            "region": region,
            "window": {"from": FROM_DATE, "minLastAuthoredWorks": min_works},
            "activityModel": {"active": f">= {ACTIVE_FROM}",
                              "winding_down": f"{WINDING_FROM}-{ACTIVE_FROM - 1}",
                              "inactive": f"< {WINDING_FROM}"},
            "counts": counts,
            "areas": ["Neuroscience"],
            "notes": ("A PI is a last author on >= 2 in-region neuroscience works. "
                      "Status is derived from the most recent last-authored work. "
                      "Preprints (bioRxiv, medRxiv, arXiv) are included; a preprint and "
                      "its published version collapse on (title, last author). "
                      "Funders come from OpenAlex funders/awards, not affiliation strings. "
                      "Graph edges are current affiliations plus the top funder; each PI's "
                      "full affiliation and funding history is on the node itself."),
        },
        "nodes": list(nodes.values()),
        "links": links,
    }


def parse_years(spec: str) -> list[int]:
    """'2026:1996' -> [2026, 2025, ... 1996]; '2024' -> [2024]; '2020,2021' -> both."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if ":" in part:
            a, b = (int(x) for x in part.split(":"))
            step = 1 if b >= a else -1
            out.extend(range(a, b + step, step))
        elif part:
            out.append(int(part))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", help="year slices to crawl, e.g. '2026:1996' "
                                    "(omit to build from cache without crawling)")
    ap.add_argument("--region", default="euna", choices=sorted(REGIONS),
                    help="which countries to keep when building (default: euna)")
    ap.add_argument("--min-works", type=int, default=MIN_LAST_AUTHOR_WORKS)
    ap.add_argument("--min-pis-per-inst", type=int, default=MIN_PIS_PER_INSTITUTION)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--legacy-cache", action="store_true",
                    help="build from the pre-slicing UK cache (regression testing)")
    ap.add_argument("--crawl-only", action="store_true")
    ap.add_argument("--quick", type=int, metavar="N",
                    help="stop after N works (smoke test)")
    args = ap.parse_args()

    legacy = None
    if args.legacy_cache:
        legacy = os.path.join(CACHE, f"works_{FIELD_NEUROSCIENCE}_{FROM_DATE}.jsonl.gz")
        if not os.path.exists(legacy):
            print(f"no legacy cache at {legacy}")
            return

    years_done = None
    if args.years:
        want = parse_years(args.years)
        years_done = crawl_years(want, use_cache=not args.no_cache)
        if len(years_done) < len(want):
            print(f"NOTE: {len(years_done)}/{len(want)} year slices complete. "
                  f"Re-run the same command after the budget resets.", flush=True)
        if args.crawl_only:
            return

    have = cached_years()
    if not legacy and not have:
        print("no cached year slices; pass --years to crawl first.")
        return

    works = iter_works(None if legacy else have, legacy_cache=legacy)
    if args.quick:
        works = itertools.islice(works, args.quick)

    by_author, inst_meta, funder_meta, n_works = aggregate(works, args.region)
    if not by_author:
        print("no in-region last-authors found; nothing to build.")
        return
    graph = build_graph(by_author, inst_meta, funder_meta,
                        args.min_works, args.min_pis_per_inst, args.region)
    graph["meta"]["worksCollected"] = n_works
    graph["meta"]["yearsCollected"] = ("legacy-uk-cache" if legacy else have)
    # A run is partial when ANY year in the window is missing, not merely when
    # the earliest is late - a cache of {1996, 2023..2026} still has a 26-year
    # hole, and every PI's work count and status is understated until it fills.
    if legacy:
        graph["meta"]["partial"] = False
    else:
        want = set(range(int(FROM_DATE[:4]), datetime.now(timezone.utc).year + 1))
        missing = sorted(want - set(have))
        graph["meta"]["partial"] = bool(missing)
        graph["meta"]["missingYears"] = missing
        if missing:
            print(f"      PARTIAL: {len(missing)} year(s) not yet crawled "
                  f"({missing[0]}-{missing[-1]}); work counts and status are "
                  f"understated.", flush=True)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(graph, f, separators=(",", ":"))
    mb = os.path.getsize(args.out) / 1e6
    with open(args.out, "rb") as src, gzip.open(args.out + ".gz", "wb", 6) as dst:
        dst.writelines(src)
    gz = os.path.getsize(args.out + ".gz") / 1e6
    print(f"wrote {args.out} ({mb:.1f} MB, {gz:.1f} MB gzipped)")


if __name__ == "__main__":
    main()
