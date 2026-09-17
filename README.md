# Neuro Labs Explorer

A local, graph-based tool for finding **neuroscience labs** and the principal
investigators (PIs) who run them: which methods they use, which model systems
they work on, where they are, and what they have published recently.

Two views:

- **Graph** (`web/index.html`) — starts **empty**. Pick methods, model systems, a
  country / city, or type free text, and the matching PIs appear with their
  institutions, positioned on a precomputed layout. Click a lab for its tags,
  recent publications, affiliations and funders. The URL hash carries the whole
  query, so any view can be bookmarked or shared.
- **Search** (`web/search.html`) — the same index as ranked cards: PI name,
  institution, topics, method / model-system tags, place and paper titles.

## Quick start

```bash
python3 serve.py                 # http://localhost:8000/web/index.html
```

The app loads `data/graph_neuro.json` plus the two optional enrichment files
(`data/tags_neuro.json`, `data/works_neuro.json`). Without the enrichment files
the graph still works, but the method / model-system facets are empty.

## Data

Everything is **real data from the [OpenAlex](https://openalex.org) API** — no
fabricated names, affiliations or histories. No websites are scraped.

- **PIs** — a *last author* on ≥ 2 neuroscience works (OpenAlex field 28) since
  1996, affiliated to an in-region institution. Status (`active`,
  `winding_down`, `inactive`) comes from the year of the most recent
  last-authored work.
- **Institutions** — from authorship records, with city / region / coordinates
  / ROR / homepage from the `/institutions` endpoint. Umbrella organisations
  (CNRS, Inserm, University of London…) never become a PI's primary institution
  while a real employer exists (`pipeline/umbrellas.json`).
- **Funders** — from grant records, their own node tier.
- **Methods and model systems** — tags derived from each PI's last-authored
  works 2019–2026: a regex vocabulary over title + abstract, plus MeSH
  descriptors where present (`pipeline/vocab.py`). Every count is the number of
  works that matched.
- **Publications** — title, year and tags of every in-window last-authored work.

### Modelling notes (honest limitations)

- **"Lab" = a PI's research group.** OpenAlex has no lab concept; each PI is one
  lab (`labLabel` = "*Surname* Group").
- **Career edges are institution-level**, drawn only for current affiliations;
  the full history is on each PI node.
- **Tags are only as good as the vocabulary.** Preprints carry no MeSH and ~16%
  of works have no abstract, so recall on title-only works is lower. A PI with
  no last-authored work since 2019 has no tags at all. Run the `audit`
  subcommand below to tune patterns.

## Pipeline

All crawls are resumable: every page is appended to a gzip cache with the cursor
checkpointed, so a daily-budget 429 costs one page and re-running the same
command continues. Set your key in `OPENALEX_API_KEY` or in a `.openalex_key`
file at the project root (free key ≈ 10,000 requests/day).

```bash
# 1. PI graph (worldwide crawl once, region chosen at build time)
python3 pipeline/collect_neuro.py --years 2026:1996                 # crawl (multi-day)
python3 pipeline/collect_neuro.py --region euna --out data/graph_neuro.json
node --max-old-space-size=8192 scripts/layout.mjs data/graph_neuro.json

# 2. Institution geo (47 requests), merged in place - no re-layout
python3 pipeline/fetch_institutions.py

# 3. Methods / model systems / publication titles
python3 pipeline/enrich_text.py crawl --years 2026:2019             # raw works, ~5,500 requests
python3 pipeline/enrich_text.py tag                                 # -> data/tags_neuro.json, data/works_neuro.json
python3 pipeline/enrich_text.py audit --tag optogenetics --n 15     # tune pipeline/vocab.py, re-run tag

# 4. Serve (restart after editing serve.py - a stale process silently serves the old files)
python3 serve.py
```

`pipeline/inspect_graph.py` audits the result (`--by-country`, `--inst "Crick"`,
`--pi "Friston"`).

### Caches (`data/cache/`)

- `works_28_world_<year>.jsonl.gz` — reduced work records for the PI graph
  (title normalised, last / corresponding authors, funders, awards).
- `works_28_world_<year>.full.jsonl.gz` — **raw** OpenAlex records for the
  enrichment window (title, year, type, authorships, abstract, MeSH). Nothing is
  dropped at crawl time, so re-tuning the vocabulary never needs another crawl.
- `institutions.jsonl.gz` — raw institution records.
- `tags_audit.json` — sample titles per tag written by the last `tag` run.

A crawl killed hard (SIGKILL, or the OS under memory pressure) leaves an
unterminated gzip member that makes the rest of the file unreadable. `crawl`
heals its own part file on resume. For a finished slice, run
`python3 pipeline/repair_gz.py <file>`: it trusts a torn member only up to its
last sync-flush marker, because decoding past a tear yields phantom records
that still parse as valid JSON.

## Layout

```
pipeline/collect_neuro.py     worldwide works crawl -> PI graph
pipeline/enrich_text.py       raw works crawl -> tags + publication lists
pipeline/vocab.py             method / model-system vocabulary (regex + MeSH)
pipeline/fetch_institutions.py institution geo -> merged into the graph
pipeline/inspect_graph.py     CLI audit of a built graph
pipeline/repair_gz.py         salvage a gzip cache torn by a hard kill
pipeline/umbrellas.json       umbrella institutions demoted from "primary"
scripts/layout.mjs            offline ForceAtlas2, bakes x/y into the graph
data/                         graph_neuro.json (+.gz), tags_neuro.json, works_neuro.json, cache/
web/                          index.html (graph), search.html, data.js, styles.css, vendor/
serve.py                      threaded static server that serves pre-built .gz siblings
```
