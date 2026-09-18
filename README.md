# Neuro Labs Explorer

A local, graph-based tool for finding **neuroscience labs** and the principal
investigators (PIs) who run them: which methods they use, which model systems
they work on, where they are, and what they have published recently.

One page (`web/index.html`): **search is the landing view**, the graph opens beside it on demand.

- **Search** — one box: as you type it suggests **methods**, **model systems**,
  **institutions** and **labs**, each grouped under its category, plus a
  "Search for …" entry that matches names, topics, institutions and paper
  titles. Accepting a suggestion **adds** a removable filter pill, so searches
  stack: several typed phrases (all must match), several tags (any may match,
  or all with "require all"), and several institutions (any may match). Typing
  a tag's exact name and pressing Enter picks that tag; picking it again
  removes it. Country, city,
  status and minimum papers are separate controls in the sidebar. The **i**
  button next to the box opens a legend of every tag, grouped by category with
  counts; clicking a chip there applies it as a filter.
- **Graph** — click any result card and the graph opens on the right, focused on
  that lab, with its institutions and the rest of the result set. Clicks snap to
  the nearest dot or its label. The side panel shows a lab's tags, affiliations,
  co-author affiliations, linked publications and funders, or an institution's
  labs, with back navigation (Esc closes the panel, then the graph). The graph is
  built the first time it is opened, so the landing page stays fast.
- **State** — removable pills show every active filter and the URL hash carries
  the whole query plus the selected lab, so any view can be bookmarked or shared.
  `web/search.html` now redirects to the single page.

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
- **Publications** — title, year, date, tags and OpenAlex link of every
  in-window work the PI **last-authored**, plus the most recent papers they
  co-authored (first or middle author), labelled with the position. Only
  last-authored papers carry tags and feed the method / model-system counts.
- **Co-author affiliations** — institutions on a PI's *first- or middle-author*
  papers 2019–2026 that are not among their own affiliations, kept when they
  appear on ≥ 2 papers (umbrella organisations excluded). They are labelled
  separately, searchable and drawn as optional teal links, but **never used to
  place a lab** (country, city, primary institution). A warning marks links
  that come from one combined affiliation string shared by several
  institutions, where the affiliation may belong to a co-author.

### Modelling notes (honest limitations)

- **"Lab" = a PI's research group.** OpenAlex has no lab concept; each PI is one
  lab (`labLabel` = "*Surname* Group").
- **Career edges are institution-level**, drawn only for current affiliations;
  the full history is on each PI node.
- **Tags are only as good as the vocabulary.** 108 tags (40 model systems, 68
  methods in 9 categories) live in `pipeline/vocab.py` with an audit history. Preprints carry no MeSH and ~16%
  of works have no abstract, so recall on title-only works is lower. A PI with
  no last-authored work since 2019 has no tags at all. Run the `audit`
  subcommand below to tune patterns.

## Pipeline

All crawls are resumable: every page is appended to a gzip cache with the cursor
checkpointed, so a daily-budget 429 costs one page and re-running the same
command continues. Set your key in `OPENALEX_API_KEY` or in a `.openalex_key`
file at the project root (free key ≈ 10,000 requests/day). For OpenAlex's
polite pool, set `OPENALEX_MAILTO` or put a contact address in
`.openalex_mailto`. Both files are untracked, so no personal details live in
the repository.

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

# 3b. Keep it current (OpenAlex is ~1 day behind publication)
python3 pipeline/enrich_text.py refresh --dry-run                   # how much is new, fetches nothing
python3 pipeline/enrich_text.py refresh                             # crawl the new window, then re-tag
scripts/refresh_daily.sh                                            # same, logged; see the file for a cron line

# 4. Serve (restart after editing serve.py - a stale process silently serves the old files)
python3 serve.py
```

Refresh notes: OpenAlex ingests a median of **1 day** after publication and
already carries bioRxiv/medRxiv preprints, so a daily refresh is as fresh as
this data gets. `from_created_date` / `from_updated_date` would be cheaper but
are gated to paid OpenAlex plans, so `refresh` re-checks a trailing publication
window (default 30 days, ~70 pages) and diffs by work id. It updates
publications and tags for PIs already in the graph; new PIs need the full
rebuild in step 1.

Google Scholar is deliberately **not** used: it has no API, automated access
breaks Google's terms, it carries no identifier to join to OpenAlex authors,
and it is no fresher. The lab panel links out to a Scholar search instead.

`pipeline/inspect_graph.py` audits the result (`--by-country`, `--inst "Crick"`,
`--pi "Friston"`).

Open data-quality work is written up as plans (not yet implemented):
`docs/plans/junk-institutions.md` (mis-resolved and non-employer institutions)
and `docs/plans/non-neuroscientists.md` (PIs outside neuroscience).

### Caches (`data/cache/`)

- `works_28_world_<year>.jsonl.gz` — reduced work records for the PI graph
  (title normalised, last / corresponding authors, funders, awards).
- `works_28_world_<year>.full.jsonl.gz` — **raw** OpenAlex records for the
  enrichment window (title, year, type, authorships, abstract, MeSH). Nothing is
  dropped at crawl time, so re-tuning the vocabulary never needs another crawl.
- `institutions.jsonl.gz` — raw institution records merged into the graph;
  `institutions_full.jsonl.gz` — the same with roles and alternative names
  (junk audit); `authors.jsonl.gz` — raw author records (topic shares, used by
  the non-neuroscientist audit).
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
data/                         graph_neuro.json (+.gz), tags_neuro.json, works_neuro.json, cache/, backups/
docs/plans/                   written-up plans for data-quality work
web/                          index.html (graph), search.html, data.js, styles.css, vendor/
serve.py                      threaded static server that serves pre-built .gz siblings
```
