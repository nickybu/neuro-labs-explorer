#!/usr/bin/env python3
"""Enrich the PI graph with research methods, model systems and publication titles.

The main crawl (``collect_neuro.py``) reduces each work at crawl time and
throws the title text away, so nothing in that cache can say whether a lab
does patch clamp in mice. This script runs a second, independent crawl over
the same year slices that keeps the **raw OpenAlex record** (title, abstract,
MeSH, authorships), then tags each PI's last-authored works against the
vocabulary in ``vocab.py``.

Three subcommands:

    crawl  --years 2026:2019      fetch raw works into data/cache/*.full.jsonl.gz
                                  (resumable per page; a 429 costs one page)
    tag                           stream the cache -> data/tags_neuro.json (+ .gz)
                                  and data/works_neuro.json (+ .gz), including
                                  co-author affiliations (non-last-author papers)
    audit  [--tag ID] [--n 8]     print sample titles per tag for vocabulary tuning

The crawl stores every selected field verbatim. Reduction only happens in
``tag``, so re-tuning the vocabulary is a re-run of ``tag`` (minutes), never
another crawl.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import sys
import time
import zlib
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import collect_neuro as CN  # noqa: E402
from vocab import (CATEGORY_ORDER, GROUPS, VOCAB_VERSION, categories,  # noqa: E402
                   compile_vocab, labels, normalise)

ROOT, CACHE = CN.ROOT, CN.CACHE
DEFAULT_GRAPH = os.path.join(ROOT, "data", "graph_neuro.json")
DEFAULT_TAGS = os.path.join(ROOT, "data", "tags_neuro.json")
DEFAULT_WORKS = os.path.join(ROOT, "data", "works_neuro.json")
AUDIT_FILE = os.path.join(CACHE, "tags_audit.json")

# Title + year (what the user asked to keep) plus the three fields the tagger
# cannot work without. Everything selected is stored whole; nothing is dropped.
FULL_SELECT = ("id,title,publication_year,publication_date,type,authorships,"
               "abstract_inverted_index,mesh")
WORKS_GZ_CAP_BYTES = 34_000_000       # above this, shrink the co-authored lists
AUDIT_SAMPLES = 40
CO_MIN_PAPERS = 2                     # co-author affiliation needs >= this many papers
CO_PAPERS = 5                         # most recent non-last-author papers kept per PI
REFRESH_WINDOW_DAYS = 30              # trailing publication window re-checked by `refresh`
STATE_FILE = os.path.join(CACHE, "refresh_state.json")


# ---------------------------------------------------------------------------
# crawl
# ---------------------------------------------------------------------------
def _full_paths(year: int) -> tuple[str, str, str]:
    stem = os.path.join(CACHE, f"works_{CN.FIELD_NEUROSCIENCE}_world_{year}.full")
    return stem + ".jsonl.gz", stem + ".part.jsonl.gz", stem + ".state.json"


def crawl_full_slice(year: int, max_pages: int | None = None) -> bool:
    """Same resumable mechanics as collect_neuro.crawl_slice, raw records out."""
    os.makedirs(CACHE, exist_ok=True)
    cache_file, part_file, state_file = _full_paths(year)
    if os.path.exists(cache_file):
        return True

    filt = (f"primary_topic.field.id:{CN.FIELD_NEUROSCIENCE},"
            f"from_publication_date:{year}-01-01,"
            f"to_publication_date:{year}-12-31")
    n, cursor = 0, "*"
    if os.path.exists(part_file) and os.path.exists(state_file):
        st = json.load(open(state_file))
        cursor, n = st.get("cursor") or "*", st.get("n", 0)
        print(f"      {year}: resuming at {n:,} works", flush=True)
        _heal_part_file(part_file)

    total = CN._get("works", {"filter": filt, "select": "id", "per-page": 1})["meta"]["count"]
    need = max(total - n, 0) // CN.PAGE + 1
    cred, _ = CN._budget()
    print(f"  [{year}] {total:,} works | ~{need:,} pages | budget {cred:,}", flush=True)
    if 0 <= cred < need:
        print(f"        ! budget short by ~{need - cred:,}; will checkpoint and stop", flush=True)

    page, t0, complete = 0, time.time(), False
    out = gzip.open(part_file, "at")
    try:
        while cursor:
            d = CN._get("works", {"filter": filt, "select": FULL_SELECT,
                                  "per-page": CN.PAGE, "cursor": cursor})
            page += 1
            for w in d["results"]:
                out.write(json.dumps(w, separators=(",", ":")) + "\n")
                n += 1
            cursor = d["meta"].get("next_cursor")
            out.flush()
            CN._atomic_write_json(state_file, {"cursor": cursor, "n": n})
            if page % 50 == 0:
                mb = os.path.getsize(part_file) / 1e6
                print(f"        page {page:>5,} | {n:>7,}/{total:,} "
                      f"({n / max(time.time() - t0, 1):.0f}/s) | {mb:.0f} MB", flush=True)
            if max_pages and page >= max_pages:
                print(f"        stopping after {page} pages (--max-pages); checkpointed", flush=True)
                break
            time.sleep(0.05)
        else:
            complete = True
    except CN.BudgetExhausted as e:
        print(f"\n      ! {e}\n        {year} checkpointed at {n:,}/{total:,}; re-run to resume.",
              flush=True)
    except KeyboardInterrupt:
        print(f"\n      interrupted; {year} checkpointed at {n:,}.", flush=True)
    finally:
        out.close()

    if complete:
        os.replace(part_file, cache_file)
        os.remove(state_file)
        print(f"        {year} done -> {os.path.getsize(cache_file) / 1e6:.1f} MB", flush=True)
    return complete


def _gzip_ok(path: str) -> bool:
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1 << 24):
                pass
        return True
    except (OSError, EOFError, zlib.error):
        return False


def _heal_part_file(part_file: str) -> None:
    """Repair a part file left torn by a hard kill before appending to it.

    A SIGKILL skips ``out.close()``, leaving an unterminated gzip member.
    Appending a new member after it makes the whole file unreadable past that
    point (zlib "invalid block type"). A 429 or Ctrl-C closes cleanly and never
    needs this. Salvage keeps every complete record; duplicates of the page
    re-fetched after the last checkpoint are removed later by `tag`.
    """
    if _gzip_ok(part_file):
        return
    import repair_gz
    kept, members, _ = repair_gz.salvage(part_file)
    os.replace(part_file + ".repaired", part_file)
    print(f"      healed torn part file: {kept:,} records kept from {members} member(s)",
          flush=True)


def full_years(include_partial: bool = False) -> list[int]:
    """Years with a complete raw slice (optionally also in-flight part files)."""
    out = set()
    if not os.path.isdir(CACHE):
        return []
    for fn in os.listdir(CACHE):
        if fn.startswith(f"works_{CN.FIELD_NEUROSCIENCE}_world_"):
            if fn.endswith(".full.jsonl.gz"):
                out.add(int(fn.split("_")[3][:4]))
            elif include_partial and fn.endswith(".full.part.jsonl.gz"):
                out.add(int(fn.split("_")[3][:4]))
    return sorted(out)


def iter_full(years: list[int], include_partial: bool = False):
    for y in years:
        cache_file, part_file, _ = _full_paths(y)
        path = cache_file if os.path.exists(cache_file) else (
            part_file if include_partial and os.path.exists(part_file) else None)
        if not path:
            continue
        try:
            with gzip.open(path, "rt") as f:
                for line in f:
                    if line.strip():
                        yield json.loads(line)
        except EOFError:
            # A .part file is being appended to by a running crawl; its last
            # gzip member is unfinished. Stop at the boundary (development only).
            if path != part_file:
                raise
            print(f"      {y}: reached the in-flight end of the part file", flush=True)


# ---------------------------------------------------------------------------
# tag
# ---------------------------------------------------------------------------
def last_author_id(w: dict) -> str:
    for a in w.get("authorships") or []:
        if a.get("author_position") == "last":
            return CN._sid((a.get("author") or {}).get("id"))
    return ""


def abstract_text(idx: dict | None) -> str:
    if not idx:
        return ""
    pairs = [(p, word) for word, poss in idx.items() for p in poss]
    pairs.sort()
    return " ".join(word for _, word in pairs)


def load_graph_index(graph_path: str) -> tuple[dict[str, set[str]], dict[str, dict]]:
    """({pi_id: {institution ids already on the PI node}}, {institution id: node meta}).

    The graph is ~116 MB of JSON; only these two small indices survive the call.
    """
    with open(graph_path) as f:
        g = json.load(f)
    pis = {n["id"]: {a["id"] for a in n.get("institutions") or []}
           for n in g["nodes"] if n["type"] == "pi"}
    insts = {n["id"]: {"label": n.get("label"), "cc": n.get("cc"), "type": n.get("instType"),
                       "city": n.get("city")}
             for n in g["nodes"] if n["type"] == "institution"}
    return pis, insts


def _write_json_gz(path: str, obj) -> tuple[float, float]:
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    with open(path, "rb") as src, gzip.open(path + ".gz", "wb", 6) as dst:
        dst.writelines(src)
    return os.path.getsize(path) / 1e6, os.path.getsize(path + ".gz") / 1e6


def tag(graph_path: str, tags_out: str, works_out: str, years: list[int] | None,
        include_partial: bool, quick: int | None, cap: int | None,
        cap_co: int = CO_PAPERS) -> None:
    pis, graph_insts = load_graph_index(graph_path)
    years = years or full_years(include_partial)
    if not years:
        print("no raw slices in cache; run `crawl` first.")
        return
    vocab = compile_vocab()
    print(f"[tag] {len(pis):,} PIs in graph | years {years[0]}-{years[-1]} | "
          f"{len(vocab)} tags (vocab {VOCAB_VERSION})", flush=True)

    seen: set[int] = set()
    seen_ids: set[str] = set()     # a hard-killed crawl re-appends its last page
    stats: dict[str, dict] = defaultdict(lambda: {"m": Counter(), "o": Counter(), "n": 0})
    works: dict[str, list] = defaultdict(list)
    tag_works: Counter = Counter()
    samples: dict[str, list] = defaultdict(list)       # reservoir per tag (+ "_untagged")
    # Co-author affiliations: institutions on a graph PI's NON-last authorships
    # that are not already on their PI node. (pi, inst) -> distinct papers.
    co: dict[tuple[str, str], dict] = {}
    co_meta: dict[str, dict] = {}
    # Papers the PI co-authored (not last author). Years stream oldest-first, so a
    # bounded deque keeps the most recent ones without holding millions of rows.
    co_works: dict[str, deque] = defaultdict(lambda: deque(maxlen=max(cap_co, 0)))
    co_works_n: Counter = Counter()
    seen_co: set[int] = set()
    n_scan = n_in = n_dupe = n_tagged = 0
    rng = random.Random(28)
    t0 = time.time()

    for w in iter_full(years, include_partial):
        n_scan += 1
        if quick and n_scan > quick:
            break
        if n_scan % 100_000 == 0:
            print(f"      {n_scan:,} scanned, {n_in:,} in-graph, {len(stats):,} PIs, "
                  f"{len(co):,} co-affiliation pairs ({time.time() - t0:.0f}s)", flush=True)
        wid = w.get("id") or ""
        if wid in seen_ids:
            n_dupe += 1
            continue
        seen_ids.add(wid)
        title = (w.get("title") or "").strip()
        t = CN._norm_title(title)
        year = w.get("publication_year") or 0

        la = ""
        for a in w.get("authorships") or []:
            aid = CN._sid((a.get("author") or {}).get("id"))
            if not aid or aid not in pis:
                continue
            if a.get("author_position") == "last":
                la = aid
                continue
            # Not the last author: record the paper (capped) so the panel can show
            # what the PI contributed to, clearly separated from what they led.
            if cap_co:
                ckey = hash((t, aid)) if t else hash((wid, aid))
                if ckey not in seen_co:
                    seen_co.add(ckey)
                    co_works_n[aid] += 1
                    entry = [year, title, [], wid.rsplit("/", 1)[-1],
                             "f" if a.get("author_position") == "first" else "m"]
                    if w.get("publication_date"):
                        entry.append(w["publication_date"])
                    co_works[aid].append(entry)
            insts = [i for i in (a.get("institutions") or []) if CN._sid(i.get("id"))]
            # One affiliation string mapped to several institutions usually means
            # the publisher merged everyone's affiliations - weaker evidence.
            merged = len(a.get("raw_affiliation_strings") or []) == 1 and len(insts) > 1
            paper = hash(t) if t else hash(wid)       # preprint + published count once
            for i in insts:
                iid = CN._sid(i.get("id"))
                # Umbrella parents (CNRS, Inserm, University of London...) say
                # nothing about where someone works, so they are not co-author
                # affiliations either.
                if iid in pis[aid] or iid in CN.UMBRELLA_INSTITUTIONS:
                    continue
                rec = co.get((aid, iid))
                if rec is None:
                    rec = co[(aid, iid)] = {"papers": set(), "y0": year, "y1": year, "merged": 0}
                if paper in rec["papers"]:
                    continue
                rec["papers"].add(paper)
                rec["y0"], rec["y1"] = min(rec["y0"], year), max(rec["y1"], year)
                rec["merged"] += merged
                if iid not in co_meta:
                    co_meta[iid] = {"label": i.get("display_name"), "cc": i.get("country_code"),
                                    "type": i.get("type")}

        if not la:
            continue
        if t:
            key = hash((t, la))
            if key in seen:
                n_dupe += 1
                continue
            seen.add(key)
        n_in += 1
        text = normalise(title + " " + abstract_text(w.get("abstract_inverted_index")))
        mesh = {m.get("descriptor_name") for m in (w.get("mesh") or [])}
        hits = []
        for group, tid, _label, rx, ms in vocab:
            if (rx and rx.search(text)) or (ms and (ms & mesh)):
                hits.append((group, tid))
        s = stats[la]
        s["n"] += 1
        for group, tid in hits:
            s["m" if group == "methods" else "o"][tid] += 1
            tag_works[tid] += 1
        if hits:
            n_tagged += 1
        led = [year, title, [tid for _, tid in hits], wid.rsplit("/", 1)[-1], "l"]
        if w.get("publication_date"):
            led.append(w["publication_date"])
        works[la].append(led)
        # Reservoir samples for `audit`
        for bucket in ([tid for _, tid in hits] or ["_untagged"]):
            lst = samples[bucket]
            k = tag_works[bucket] if bucket != "_untagged" else (n_in - n_tagged)
            if len(lst) < AUDIT_SAMPLES:
                lst.append([year, title[:140]])
            elif k > 0 and rng.random() < AUDIT_SAMPLES / k:
                lst[rng.randrange(AUDIT_SAMPLES)] = [year, title[:140]]

    print(f"      {n_scan:,} scanned | {n_in:,} last-authored by a graph PI | "
          f"{n_dupe:,} dupes | {n_tagged:,} tagged | {len(stats):,} PIs ({time.time() - t0:.0f}s)",
          flush=True)

    # Keep co-author affiliations with at least CO_MIN_PAPERS distinct papers.
    co_by_pi: dict[str, list] = defaultdict(list)
    used_insts: set[str] = set()
    for (aid, iid), rec in co.items():
        n = len(rec["papers"])
        if n < CO_MIN_PAPERS:
            continue
        co_by_pi[aid].append([iid, n, rec["y0"], rec["y1"], rec["merged"]])
        used_insts.add(iid)
    del co
    for lst in co_by_pi.values():
        lst.sort(key=lambda x: (-x[1], -x[3]))
    co_institutions = {}
    for iid in used_insts:
        meta = dict(graph_insts.get(iid) or co_meta.get(iid) or {"label": iid})
        meta["inGraph"] = iid in graph_insts
        co_institutions[iid] = {k: v for k, v in meta.items() if v not in (None, "")}
    print(f"      co-author affiliations: {sum(len(v) for v in co_by_pi.values()):,} links for "
          f"{len(co_by_pi):,} PIs across {len(used_insts):,} institutions "
          f"(>= {CO_MIN_PAPERS} papers)", flush=True)

    lab, cats = labels(), categories()
    tag_pis = {g: Counter() for g in GROUPS}
    for s in stats.values():
        for tid in s["m"]:
            tag_pis["methods"][tid] += 1
        for tid in s["o"]:
            tag_pis["organisms"][tid] += 1
    pi_ids = set(stats) | set(co_by_pi)
    pis_doc = {}
    for pid in pi_ids:
        s = stats.get(pid)
        rec = {"m": dict(s["m"].most_common()) if s else {},
               "o": dict(s["o"].most_common()) if s else {},
               "n": s["n"] if s else 0}
        if pid in co_by_pi:
            rec["ca"] = co_by_pi[pid]
        pis_doc[pid] = rec
    tags_doc = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "years": years, "vocabVersion": VOCAB_VERSION,
            "worksScanned": n_scan, "worksLastAuthorInGraph": n_in,
            "duplicatesCollapsed": n_dupe, "worksTagged": n_tagged, "pisTagged": len(stats),
            "coAffiliation": {"minPapers": CO_MIN_PAPERS, "pis": len(co_by_pi),
                              "links": sum(len(v) for v in co_by_pi.values()),
                              "fields": ["institutionId", "papers", "firstYear", "lastYear",
                                         "papersFromMergedAffiliationString"]},
            "categories": CATEGORY_ORDER,
            "notes": ("m/o: last-authored works in the window that matched a tag by regex over "
                      "title+abstract or by MeSH descriptor. n: last-authored works in the "
                      "window (all regions, so it can exceed the graph's in-region `works`). "
                      "ca: co-author affiliations - institutions on the PI's first/middle-author "
                      "papers in the window that are not on their PI node, with at least "
                      "minPapers distinct papers. They are labelled separately in the UI and "
                      "never used for placement."),
        },
        "tags": {g: [{"id": tid, "label": lab[g][tid], "category": cats[g][tid],
                      "pis": tag_pis[g][tid], "works": tag_works[tid]} for tid in GROUPS[g]]
                 for g in GROUPS},
        "coInstitutions": co_institutions,
        "pis": pis_doc,
    }
    mb, gz = _write_json_gz(tags_out, tags_doc)
    print(f"wrote {tags_out} ({mb:.1f} MB, {gz:.1f} MB gzipped)")

    for lst in works.values():
        lst.sort(key=lambda x: -x[0])
    n_led = sum(len(v) for v in works.values())
    co_listed = 0
    if cap_co:
        for pid, dq in co_works.items():
            if pid not in works and pid not in stats:
                works[pid] = []
            rows = sorted(dq, key=lambda x: -x[0])
            works[pid].extend(rows)
            co_listed += len(rows)
    works_doc = {"meta": {"generated": tags_doc["meta"]["generated"], "years": years,
                          "worksListed": n_led + co_listed, "ledListed": n_led,
                          "coauthorListed": co_listed, "coauthorCapPerPI": cap_co,
                          "capPerPI": None,
                          "fields": ["year", "title", "tagIds", "openalexWorkId",
                                     "position (l=last, f=first, m=middle)", "publicationDate (if known)"],
                          "notes": ("Entries with position 'l' are papers the PI last-authored in the "
                                    "window; only those carry tagIds and feed the method/model-system "
                                    "counts. Other positions are the most recent coauthorCapPerPI "
                                    "papers the PI contributed to; coTotals gives the full count.")},
                 "coTotals": {pid: n for pid, n in co_works_n.items() if n},
                 "pis": dict(works)}
    print(f"      publications: {n_led:,} led + {co_listed:,} co-authored "
          f"(cap {cap_co}/PI, {len(co_works_n):,} PIs have co-authored papers)", flush=True)
    if cap:
        _apply_cap(works_doc, cap)
    mb, gz = _write_json_gz(works_out, works_doc)
    shrink = cap_co
    while gz * 1e6 > WORKS_GZ_CAP_BYTES and shrink > 1:
        shrink = max(1, shrink // 2)
        _apply_cap(works_doc, shrink)
        mb, gz = _write_json_gz(works_out, works_doc)
        print(f"      over {WORKS_GZ_CAP_BYTES / 1e6:.0f} MB gz; co-authored papers "
              f"capped at {shrink}/PI -> {gz:.1f} MB gz")
    print(f"wrote {works_out} ({mb:.1f} MB, {gz:.1f} MB gzipped)")

    with open(AUDIT_FILE, "w") as f:
        json.dump({"vocabVersion": VOCAB_VERSION, "tagWorks": dict(tag_works),
                   "tagPIs": {g: dict(c) for g, c in tag_pis.items()},
                   "samples": samples, "worksLastAuthorInGraph": n_in}, f)


def _pos(w: list) -> str:
    return w[4] if len(w) > 4 else "l"


def _apply_cap(doc: dict, cap: int) -> None:
    """Trim CO-AUTHORED papers only. Papers the PI led are never dropped: they
    carry the tags and are the point of the list."""
    led_n = co_n = 0
    for pid, lst in doc["pis"].items():
        led = [w for w in lst if _pos(w) == "l"]
        co = [w for w in lst if _pos(w) != "l"][:cap]
        doc["pis"][pid] = led + co
        led_n += len(led); co_n += len(co)
    doc["meta"]["coauthorCapPerPI"] = cap
    doc["meta"]["ledListed"] = led_n
    doc["meta"]["coauthorListed"] = co_n
    doc["meta"]["worksListed"] = led_n + co_n


# ---------------------------------------------------------------------------
# refresh - pull just what published since the last run
# ---------------------------------------------------------------------------
def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _cached_ids(year: int) -> set[str]:
    """Work ids already in a year's raw cache (for the new-work diff)."""
    ids: set[str] = set()
    cache_file, part_file, _ = _full_paths(year)
    for path in (cache_file, part_file):
        if not os.path.exists(path):
            continue
        try:
            with gzip.open(path, "rt") as f:
                for line in f:
                    i = line.find('"id":"')
                    if i >= 0:
                        # stored ids are full URLs ("https://openalex.org/W…"),
                        # so compare on the bare id
                        ids.add(line[i + 6:line.index('"', i + 6)].rsplit("/", 1)[-1])
        except (OSError, EOFError, zlib.error):
            print(f"      ! {os.path.basename(path)} unreadable; run repair_gz.py", flush=True)
    return ids


def refresh(since: str | None, window_days: int, dry_run: bool, do_tag: bool,
            graph_path: str, tags_out: str, works_out: str, cap_co: int) -> None:
    """Crawl the trailing publication window and keep only genuinely new works.

    `from_created_date` / `from_updated_date` would be the natural filters but
    they are gated to paid OpenAlex plans (the API answers 429 "Plan upgrade
    required"), so we re-check a window of publication dates and diff by work
    id instead. That also picks up records back-dated inside the window.
    """
    today = datetime.now(timezone.utc).date()
    state = _load_state()
    since = since or str(today - timedelta(days=window_days))
    filt = (f"primary_topic.field.id:{CN.FIELD_NEUROSCIENCE},"
            f"from_publication_date:{since},to_publication_date:{today}")
    total = CN._get("works", {"filter": filt, "select": "id", "per-page": 1})["meta"]["count"]
    pages = max(total - 1, 0) // CN.PAGE + 1
    cred, _ = CN._budget()
    print(f"[refresh] published {since} .. {today}: {total:,} works | ~{pages:,} pages | "
          f"budget {cred:,} | last run {state.get('lastRun', 'never')}", flush=True)
    if dry_run:
        print("      --dry-run: nothing fetched or written")
        return

    known: dict[int, set[str]] = {}
    fresh: dict[int, list[str]] = defaultdict(list)
    cursor, seen, n_new = "*", 0, 0
    try:
        while cursor:
            d = CN._get("works", {"filter": filt, "select": FULL_SELECT,
                                  "per-page": CN.PAGE, "cursor": cursor})
            for w in d["results"]:
                seen += 1
                year = w.get("publication_year") or today.year
                if year not in known:
                    known[year] = _cached_ids(year)
                    print(f"      {year}: {len(known[year]):,} works already cached", flush=True)
                wid = CN._sid(w.get("id"))
                if wid in known[year]:
                    continue
                known[year].add(wid)
                fresh[year].append(json.dumps(w, separators=(",", ":")))
                n_new += 1
            cursor = d["meta"].get("next_cursor")
            time.sleep(0.05)
    except CN.BudgetExhausted as e:
        print(f"      ! {e}; writing what was fetched", flush=True)

    for year, lines in sorted(fresh.items()):
        cache_file, _, _ = _full_paths(year)
        with gzip.open(cache_file, "at") as out:      # a new gzip member, readers concatenate
            out.write("\n".join(lines) + "\n")
        print(f"      {year}: +{len(lines):,} new works -> {os.path.basename(cache_file)}", flush=True)
    print(f"      {seen:,} works checked, {n_new:,} new", flush=True)

    CN._atomic_write_json(STATE_FILE, {**state, "lastRun": str(today), "since": since,
                                       "checked": seen, "new": n_new})
    if do_tag and n_new:
        tag(graph_path, tags_out, works_out, None, False, None, None, cap_co)
    elif do_tag:
        print("      nothing new; skipping re-tag")


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------
def audit(only: str | None, n: int) -> None:
    if not os.path.exists(AUDIT_FILE):
        print("no audit file; run `tag` first.")
        return
    a = json.load(open(AUDIT_FILE))
    lab = labels()
    print(f"vocab {a['vocabVersion']} | {a['worksLastAuthorInGraph']:,} in-graph works\n")
    for g in GROUPS:
        for tid in GROUPS[g]:
            if only and tid != only:
                continue
            works = a["tagWorks"].get(tid, 0)
            pis = a["tagPIs"][g].get(tid, 0)
            print(f"== {lab[g][tid]} [{tid}]  {works:,} works · {pis:,} PIs")
            for y, t in a["samples"].get(tid, [])[:n]:
                print(f"     {y}  {t}")
    if not only:
        print(f"\n== untagged sample")
        for y, t in a["samples"].get("_untagged", [])[:n]:
            print(f"     {y}  {t}")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("crawl", help="fetch raw works into the .full cache")
    c.add_argument("--years", required=True, help="e.g. '2026:2019' (newest first)")
    c.add_argument("--max-pages", type=int, help="stop each year after N pages (smoke test)")

    t = sub.add_parser("tag", help="tag PIs from the .full cache")
    t.add_argument("--graph", default=DEFAULT_GRAPH)
    t.add_argument("--out", default=DEFAULT_TAGS)
    t.add_argument("--works-out", default=DEFAULT_WORKS)
    t.add_argument("--years", help="restrict to these years, e.g. '2019:2026'")
    t.add_argument("--include-partial", action="store_true",
                   help="also read in-flight .part slices (for development)")
    t.add_argument("--quick", type=int, metavar="N", help="stop after N records")
    t.add_argument("--cap", type=int, help="max led works per PI in works_neuro.json")
    t.add_argument("--coauthor-papers", type=int, default=CO_PAPERS,
                   help=f"most recent non-last-author papers kept per PI (default {CO_PAPERS}, 0 = none)")

    rf = sub.add_parser("refresh", help="crawl the trailing publication window, then re-tag")
    rf.add_argument("--since", help="publication date to crawl from (default: today - window)")
    rf.add_argument("--window-days", type=int, default=REFRESH_WINDOW_DAYS)
    rf.add_argument("--dry-run", action="store_true", help="report size only, fetch nothing")
    rf.add_argument("--no-tag", action="store_true", help="fetch only, do not rebuild the tag files")
    rf.add_argument("--graph", default=DEFAULT_GRAPH)
    rf.add_argument("--out", default=DEFAULT_TAGS)
    rf.add_argument("--works-out", default=DEFAULT_WORKS)
    rf.add_argument("--coauthor-papers", type=int, default=CO_PAPERS)

    a = sub.add_parser("audit", help="print sample titles per tag")
    a.add_argument("--tag", help="only this tag id")
    a.add_argument("--n", type=int, default=8)

    args = ap.parse_args()
    if args.cmd == "crawl":
        want = CN.parse_years(args.years)
        done = []
        for y in want:
            try:
                if crawl_full_slice(y, args.max_pages):
                    done.append(y)
                elif not args.max_pages:
                    break
            except CN.BudgetExhausted as e:
                print(f"      ! {e}", flush=True)
                break
        print(f"{len(done)}/{len(want)} year slices complete"
              + ("" if len(done) == len(want) else "; re-run the same command to resume."))
    elif args.cmd == "refresh":
        refresh(args.since, args.window_days, args.dry_run, not args.no_tag,
                args.graph, args.out, args.works_out, args.coauthor_papers)
    elif args.cmd == "tag":
        years = CN.parse_years(args.years) if args.years else None
        tag(args.graph, args.out, args.works_out, years, args.include_partial,
            args.quick, args.cap, args.coauthor_papers)
    else:
        audit(args.tag, args.n)


if __name__ == "__main__":
    main()
