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
                                  and data/works_neuro.json (+ .gz)
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
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import collect_neuro as CN  # noqa: E402
from vocab import GROUPS, VOCAB_VERSION, compile_vocab, labels, normalise  # noqa: E402

ROOT, CACHE = CN.ROOT, CN.CACHE
DEFAULT_GRAPH = os.path.join(ROOT, "data", "graph_neuro.json")
DEFAULT_TAGS = os.path.join(ROOT, "data", "tags_neuro.json")
DEFAULT_WORKS = os.path.join(ROOT, "data", "works_neuro.json")
AUDIT_FILE = os.path.join(CACHE, "tags_audit.json")

# Title + year (what the user asked to keep) plus the three fields the tagger
# cannot work without. Everything selected is stored whole; nothing is dropped.
FULL_SELECT = "id,title,publication_year,type,authorships,abstract_inverted_index,mesh"
WORKS_GZ_CAP_BYTES = 25_000_000       # above this, cap works per PI (see tag())
WORKS_PER_PI_CAP = 40
AUDIT_SAMPLES = 40


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


def load_pi_ids(graph_path: str) -> set[str]:
    with open(graph_path) as f:
        g = json.load(f)
    return {n["id"] for n in g["nodes"] if n["type"] == "pi"}


def _write_json_gz(path: str, obj) -> tuple[float, float]:
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    with open(path, "rb") as src, gzip.open(path + ".gz", "wb", 6) as dst:
        dst.writelines(src)
    return os.path.getsize(path) / 1e6, os.path.getsize(path + ".gz") / 1e6


def tag(graph_path: str, tags_out: str, works_out: str, years: list[int] | None,
        include_partial: bool, quick: int | None, cap: int | None) -> None:
    pis = load_pi_ids(graph_path)
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
    n_scan = n_in = n_dupe = n_tagged = 0
    rng = random.Random(28)
    t0 = time.time()

    for w in iter_full(years, include_partial):
        n_scan += 1
        if quick and n_scan > quick:
            break
        if n_scan % 100_000 == 0:
            print(f"      {n_scan:,} scanned, {n_in:,} in-graph, {len(stats):,} PIs "
                  f"({time.time() - t0:.0f}s)", flush=True)
        la = last_author_id(w)
        if not la or la not in pis:
            continue
        wid = w.get("id") or ""
        if wid in seen_ids:
            n_dupe += 1
            continue
        seen_ids.add(wid)
        title = (w.get("title") or "").strip()
        t = CN._norm_title(title)
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
        year = w.get("publication_year") or 0
        works[la].append([year, title, [tid for _, tid in hits]])
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

    lab = labels()
    tag_pis = {g: Counter() for g in GROUPS}
    for s in stats.values():
        for tid in s["m"]:
            tag_pis["methods"][tid] += 1
        for tid in s["o"]:
            tag_pis["organisms"][tid] += 1
    tags_doc = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "years": years, "vocabVersion": VOCAB_VERSION,
            "worksScanned": n_scan, "worksLastAuthorInGraph": n_in,
            "duplicatesCollapsed": n_dupe, "worksTagged": n_tagged, "pisTagged": len(stats),
            "notes": ("Counts are last-authored works in the window that matched a tag by "
                      "regex over title+abstract or by MeSH descriptor. A PI absent here "
                      "has no last-authored works in the window. Unlike the graph's "
                      "`works`, which counts only in-region works, `n` counts every "
                      "last-authored work, so it can exceed `works` for PIs who also "
                      "publish from outside the region."),
        },
        "tags": {g: [{"id": tid, "label": lab[g][tid], "pis": tag_pis[g][tid],
                      "works": tag_works[tid]} for tid in GROUPS[g]] for g in GROUPS},
        "pis": {pid: {"m": dict(s["m"].most_common()), "o": dict(s["o"].most_common()),
                      "n": s["n"]} for pid, s in stats.items()},
    }
    mb, gz = _write_json_gz(tags_out, tags_doc)
    print(f"wrote {tags_out} ({mb:.1f} MB, {gz:.1f} MB gzipped)")

    for lst in works.values():
        lst.sort(key=lambda x: -x[0])
    works_doc = {"meta": {"generated": tags_doc["meta"]["generated"], "years": years,
                          "worksListed": sum(len(v) for v in works.values()),
                          "capPerPI": None},
                 "pis": dict(works)}
    if cap:
        _apply_cap(works_doc, cap)
    mb, gz = _write_json_gz(works_out, works_doc)
    if not cap and gz * 1e6 > WORKS_GZ_CAP_BYTES:
        _apply_cap(works_doc, WORKS_PER_PI_CAP)
        mb, gz = _write_json_gz(works_out, works_doc)
        print(f"      works list exceeded {WORKS_GZ_CAP_BYTES / 1e6:.0f} MB gz; "
              f"capped at {WORKS_PER_PI_CAP} most recent per PI")
    print(f"wrote {works_out} ({mb:.1f} MB, {gz:.1f} MB gzipped)")

    with open(AUDIT_FILE, "w") as f:
        json.dump({"vocabVersion": VOCAB_VERSION, "tagWorks": dict(tag_works),
                   "tagPIs": {g: dict(c) for g, c in tag_pis.items()},
                   "samples": samples, "worksLastAuthorInGraph": n_in}, f)


def _apply_cap(doc: dict, cap: int) -> None:
    for pid, lst in doc["pis"].items():
        if len(lst) > cap:
            doc["pis"][pid] = lst[:cap]
    doc["meta"]["capPerPI"] = cap
    doc["meta"]["worksListed"] = sum(len(v) for v in doc["pis"].values())


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
    t.add_argument("--cap", type=int, help="max works per PI in works_neuro.json")

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
    elif args.cmd == "tag":
        years = CN.parse_years(args.years) if args.years else None
        tag(args.graph, args.out, args.works_out, years, args.include_partial,
            args.quick, args.cap)
    else:
        audit(args.tag, args.n)


if __name__ == "__main__":
    main()
