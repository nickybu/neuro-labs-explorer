# Junk institutions: audit and cleaning plan

Status: **plan only, nothing implemented.** Audit run 2026-09-17 against `data/graph_neuro.json`
(euna build: 4,681 institutions, 106,709 PIs) and the raw 2024 works slice.

## TL;DR

- Most "junk" is not odd organisations but **OpenAlex resolving an affiliation string to the wrong
  institution**. "Harvard University" goes to *Harvard University Press*, "Lincoln's Inn Fields" (the old
  CRUK London Research Institute address) to *The Honourable Society of Lincoln's Inn*, and "New York State
  Psychiatric Institute" to *New York Psychoanalytic Society and Institute*.
- The most damaging variant is **region leakage**: generic names such as "Ministry of Education" or
  "Academy of Medical Sciences" resolve to an in-region entity (Montenegro, UK), so researchers from China,
  Korea, Russia and Saudi Arabia enter the Europe and North America graph. **61 institutions** fit this
  pattern; 89 to 259 of their primary PIs have no other in-region affiliation, depending on the threshold.
- Funders and publishers used as affiliations (Wellcome Trust, NSF, Society for Neuroscience, OUP) are a
  smaller problem for primaries (80 PIs) but large for secondaries (about 1,100 PIs).
- Name patterns alone over-prune badly. The Polish and Czech academies, NIH intramural institutes, NHS
  Foundation Trusts, IRCCS foundations and "Investigación" institutes all look like junk by name. **Use
  roles, affiliation strings and a curated list; keep name patterns as a review queue only.**

## Method

- Refetched all 4,681 graph institutions with a wide select, including `roles`, `summary_stats`,
  `associated_institutions` and `display_name_alternatives`. Stored raw in
  `data/cache/institutions_full.jsonl.gz`, plus the top 300 outside-graph co-affiliation institutions
  (partial select, tagged `_partial_select`). 4,678 returned; 3 ids are dead.
- For each institution: PIs with it as primary, PIs with it as a secondary association, and roles
  (institution, funder and publisher works counts).
- Scanned the whole 2024 raw slice (135,443 works, every authorship). For each graph institution, measured
  the share of assigned authorships whose `raw_affiliation_strings` name only out-of-region places and
  never the institution's own country or city.
- Co-author affiliations were checked on 2024 only (one year, sampled for memory and time). Multi-year
  thresholds such as "≥ 2 works" are therefore understated here.

## Findings

### 1. Mis-resolved affiliation strings (the dominant junk)

| Institution as resolved | Should be | Primary PIs | Secondary | Evidence |
|---|---|---|---|---|
| Harvard University Press (US, 281,969 works) | Harvard University | 35 (active: Alvarez, Cushman, Caramazza, Greene) | 388 | Same PIs have Harvard University as the other affiliation |
| New York Psychoanalytic Society and Institute | NY State Psychiatric Institute / Columbia (NYSPI is **absent** from the graph) | 26 (Kellendonk, Devanand) | 153 | Other affiliation is Columbia |
| The Honourable Society of Lincoln's Inn (GB) | Cancer Research UK London Research Institute, now the Crick | 4 (Julian Lewis, Sally Leevers, Neil McDonald) | 9 | Other affiliation is Cancer Research UK |
| Research Triangle Park Foundation | EPA / GSK / Hamner at RTP | 16 | 54 | Address string |
| Abbott Fund | Abbott (United States) | 16 | 13 | Abbott / AbbVie chemists |
| META Health | Meta (United States) | 11 | 4 | Reality Labs staff |
| Psychiatry Research Trust (GB charity) | King's College London (IoPPN) | 10 (Michael Rutter) | 83 | Other affiliation is KCL |
| Southwestern Medical Center ×2, one ghost with 0 works and no ROR | UT Southwestern | 28 | 334 | Other affiliation is UTSW |
| The University of Texas Health Science Center (0 works, no ROR) | UTHealth Houston | 19 | 115 | Other affiliation is UTHealth Houston |
| Generic strings: Audiology (US), Neurotech (US), Neurobehavioral Research (US), Chicago Neuropsychology Group, Communication Disorders Technology, Department of Physics, Mathematics and Informatics (BY) | the PI's real department | about 35 | about 140 | e.g. Oliver Tucha (Groningen) under Chicago Neuropsychology Group |

### 2. Region leakage (mis-resolved generic names, out-of-region researchers)

Detector: at least 50% of an institution's 2024 authorships carry raw strings naming only out-of-region
places.

| Tier | Institutions | Primary PIs (active) | Re-homeable | Orphaned: no other in-region affiliation |
|---|---|---|---|---|
| ≥ 80% mismatch | 25 | 135 (77) | 46 | **89** |
| 50–80% mismatch (review) | 36 | 299 (115) | 132 | 167 |

- **≥ 80% examples:** Ministry of Education in Montenegro (56/56) and Portugal (28/29), Ministry of
  Agriculture, National Cancer Center, St. Mary's Hospital (20/20), Regional Clinical Research, Institute
  of Immunology, Institute of Biomedical Science (46/57), Buddhist Tzu Chi Medical Foundation, LG (United
  States), RMIT Europe, Creative Commons (license text parsed as an affiliation).
- **50–80% examples:** Academy of Medical Sciences GB (45/58; Russian and Chinese Academy of Medical
  Sciences), National Clinical Research US (208/270), King University / King Center (King Saud / King
  Abdulaziz), Czech Academy of Sciences Institute of Biophysics (Chinese "Institute of Biophysics"),
  Imaging, Brain, and Neuropsychiatry FR, Schlumberger (Ireland) (13 primary, **351 secondary**, a hub of
  nonsense matches).
- **False positives in the 50–80% tier:** Mount Sinai Beth Israel ("Israel" is in its own name),
  Department of Embryology (Carnegie, which is real), US Department of the Navy. This tier needs human
  review.

### 3. Funders as affiliations (acknowledgements or fellowships parsed as employers)

Automatic signal: type nonprofit or other, with funder-role works ≥ 5× institution-role works. Government
funders are curated.

- **15 institutions:** Wellcome Trust, Simons Foundation, British Heart Foundation, Alzheimer's
  Association, Autism Speaks, Lundbeck Foundation, Fund for Scientific Research (FWO/FNRS), Stanley Medical
  Research Institute, plus curated government funders: MRC (the generic parent, not MRC units), NSF, NIHR,
  CIHR, European Commission, NCATS, and NIH Office of Extramural Research.
- **Impact:** 61 primary PIs (21 active; 42 re-homeable, 19 orphaned) and **892 PIs with one as a
  secondary**.
- Rebecca Jordan and Gülşen Sürmeli (Edinburgh) are filed under Simons Foundation through SCGB funding.
- **Do not auto-apply the role rule to type government or facility.** It catches NIH intramural institutes:
  NCI (46 primary), NIDCD (35), and NIMH, NINDS and NIDA (100–150 each). Those are real employers.

### 4. Publishers and societies (journal or abstract strings)

Signal: publisher-role works ≥ 5× institution-role works.

- **7 institutions:** Society for Neuroscience (3 primary, **209 secondary**, from SfN abstracts), Oxford
  University Press, RELX, AAAS, ASHA, American Academy of Pediatrics, OECD.
- **Impact:** 19 primary PIs (8 re-homeable, 11 orphaned) and 256 secondary.
- **Curated extras** the role rule misses: Harvard University Press (its institution works are inflated by
  the mis-resolution), Physiological Society, International Neuromodulation Society, American Academy of
  Neurology, AACAP, Huntington's Disease Association.
- A publisher role alone is **not** junk. UNED, Adam Mickiewicz University and NIEHS all publish more than
  they author, but are real universities or institutes.

### 5. Weak primaries (per-PI support)

- **Signal:** the primary rests on ≤ 2 works while another non-umbrella affiliation has ≥ 5 and ≥ 3× as
  many. **437 PIs, all active.**
- This is a side effect of `_rank_inst` ranking "current" above volume. A single 2023+ paper wins.
- **Mixed cases:** genuine moves (Jefferys, Birmingham to Oxford) sit alongside noise (Mark Hallett filed
  under NINR on 1 work vs 71 at NINDS; Klaus-Armin Nave under MPI Psychiatry on 1 vs 40 at MPI
  Experimental Medicine; David Bredt under Rapt Therapeutics on 1 vs 24).

### 6. Legitimate but unusual (must survive any rule)

- NIH intramural institutes (NIMH, NINDS, NIDA, NCI, NIDCD).
- National academies' institutes: Polish, Czech, Hungarian, Slovak, Bulgarian.
- IRCCS and hospital foundations (Fondazione Santa Lucia, Carlo Besta, Mondino, Don Gnocchi), NHS
  Foundation Trusts.
- Champalimaud Foundation, FORTH, University of Veterinary Medicine Hannover, Foundation.
- Companies: Cochlear, MED-EL, Oticon, Novo Nordisk, pharma.
- Bernstein Centers, Spinoza Centre, Swiss Epilepsy Center, NMI Reutlingen.
- Royal Academy of Music Aarhus/Aalborg (Peter Vuust, 70 of 89 works; genuinely there).
- NY State OPWDD (Institute for Basic Research), Office of Chief Medical Examiner, EPA and USDA research
  labs, Carnegie Department of Embryology.
- **Name-pattern false positives:** "London South Bank University" matches "bank", and every Spanish
  "Investigación" institute matches "invest".

### 7. Co-author affiliations (non-last authorships, 2024)

- 30,492 occurrences, 20,821 distinct (PI, institution) pairs; 4,793 on ≥ 2 works within 2024.
- **Junk rules touch few pairs.** Only about 195 hit the graph-institution rules above (curated 94,
  funder 44, mismatch 32, ghosts 19, publisher 6).
- **Blob-sharing is the bigger quality issue** (the Sadra Sadeh / Crick case). 10% of occurrences come from
  one raw affiliation blob shared by ≥ 3 co-authors and resolved to ≥ 3 institutions, and 5% from a single
  raw string resolved to ≥ 3 institutions. Of the ≥ 2-work pairs, 223 rest entirely on shared blobs.
- **Umbrellas dominate the outside-graph list:** Johns Hopkins Medicine (198 PIs), AP-HP (138), CEA (72),
  Chinese Academy of Sciences (62), VA / VHA, Mass General Brigham, Sorbonne Paris Cité. Only "Canada
  Research Chairs" is funder-dominant in the top 300.
- 45% of outside-graph pairs point at out-of-region institutions (Monash, Peking, Queensland). Most are
  genuine collaborations or visiting posts, not junk. Label them as such and don't drop them.

## Recommended cleaning approach

Apply the rules in this order. Everything except R6 lives in one curated file plus a small classifier,
mirroring `umbrellas.json`.

| # | Rule | Action | Expected impact (euna graph) |
|---|---|---|---|
| R1 | **Curated remap list** `pipeline/junk_institutions.json`: `{id: {action: "remap", to: id} \| {action: "drop"} \| {action: "demote"}, note, verified}` | Remap mis-resolutions (Harvard University Press → Harvard; UTSW ghosts → UTSW; Lincoln's Inn → CRUK; Abbott Fund → Abbott; META Health → Meta; Psychiatry Research Trust → KCL). Drop generic-string entities. | 36 seed entries: **367 primary PIs (128 active)**, 229 re-homed, 138 orphaned (review before dropping). Remaps turn most orphans into correct homes. |
| R2 | **Funder-as-affiliation**: nonprofit/other with funder works ≥ 5× institution works, plus a curated government-funder list | Demote: never primary, and excluded from co-author affiliations | 15 institutions: 61 primary PIs (42 re-homed, 19 orphaned), cleans 892 secondaries |
| R3 | **Publisher/society-as-affiliation**: publisher works ≥ 5× institution works, plus curated societies | Drop from primary and co-author affiliations | 7 + about 6 curated: 19 primary PIs, 256 secondaries |
| R4 | **Ghost entities**: dead id or `works_count == 0` | Remap to the sibling sharing the PI's other affiliation (same city), else drop | 3 institutions, 45 primary PIs (all re-homeable, 32 active) |
| R5 | **Region leak**, authorship level (preferred): ignore an authorship → institution link when the raw strings name only out-of-region places. Institution level (fallback, no raw strings): curate ≥ 80% mismatch; queue 50–80% for review | Drop the link; PIs left with no in-region evidence leave the region build | ≥ 80%: 25 institutions, 135 primary PIs, **89 leave the graph** (correct, they're out of region). 50–80% after review: up to 167 more |
| R6 | **Primary support floor**: re-rank current affiliations by works in the last 3 active years; require ≥ 2 works, or ≥ 25% of recent works, before a current affiliation beats a stronger one | Re-pick primary | Up to 437 active PIs re-examined. Expect a split between noise (Hallett, Nave) and genuine moves (Jefferys). Audit 30 by hand first |
| R7 | **Name-pattern review queue**: Press, Society, Inn, Council, Ministry, Foundation, Trust, Association, Academy of | Report only, never auto-act | Flags about 290 institutions; mostly legitimate |

## Where it plugs in

- **`pipeline/collect_neuro.py`**
  - `aggregate()`: apply R1 remap/drop and R5 per authorship institution before tallying `a["insts"]`. The
    graph build is region-filtered, so R5 must run before the `cc in allow` check.
  - `_rank_inst()`: R2 demotion (like umbrellas) and R6 recency-window support.
  - `build_graph()`: R4 remaps, then drop PIs with no surviving in-region institution (already the orphan
    path).
- **`pipeline/fetch_institutions.py`**: switch to the wide select (roles, `works_count`, dead-id tracking);
  `institutions_full.jsonl.gz` already has it. Emit a derived `data/cache/institution_flags.json` holding
  role ratios, mismatch share and rule hits for collect and enrich to read.
- **`pipeline/enrich_text.py tag`** (co-author affiliations):
  - apply `umbrellas.json`, R1, R2, R3 and R4 to co-author institutions;
  - mark or skip links that come only from a shared multi-institution blob (≥ 3 co-authors, ≥ 3
    institutions);
  - keep the ≥ 2 works rule across the whole window;
  - keep out-of-region institutions, but label them.
- **Data gap for R5 at authorship level:** the reduced 1996–2026 slices do not store
  `raw_affiliation_strings`, while the `.full` 2019–2026 slices do. Options:
  - (a) authorship-level R5 for 2019–26 only, institution-level curated R5 for older years;
  - (b) add `raw_affiliation_strings` to `_extract` and re-crawl 1996–2018. About 9,000 requests, roughly
    one day on the free key.

  Recommend (a) now, (b) at the next refresh.

## Risks

- **Over-pruning real employers.** Name rules would remove the academies, NIH institutes, IRCCS and NHS
  Trusts; hence roles plus curation only. Keep the section 6 list as an explicit allowlist test.
- **Remaps can merge distinct places**, such as UTHealth Houston vs San Antonio. Only remap to the target
  the PI's own other affiliation names; otherwise drop.
- **R5 string heuristics:** place names inside institution names ("Beth Israel", "Hebrew", "King's") and
  expatriates writing a home-country string. Mitigations: ignore tokens found in the institution's own
  name or alternatives, and require all raw strings on the authorship to be out-of-region.
- **R6 can undo a genuine move** until the new place accumulates papers. Use a window, not lifetime counts.
- **Orphans** (PIs losing their only institution): review before deleting. Many are correctly out of
  region, but some are real UK or EU PIs with bad strings.

## Validation

1. **Allowlist test:** assert every section 6 institution keeps its primary PIs, e.g. NIMH ≥ 150,
   Fondazione Santa Lucia ≥ 80, Polish Academy of Sciences ≥ 60.
2. **Sanity lists:** `python3 pipeline/inspect_graph.py --inst "Crick"` (plus UCL, Oxford, Harvard,
   Columbia). Expect Harvard to gain Alvarez, Cushman and Caramazza; Columbia to gain Kellendonk and
   Devanand; Crick or its CRUK lineage to gain Julian Lewis and Sally Leevers.
3. **Leakage check:** after R5, the rerun mismatch detector should find no institution ≥ 80%. Spot-check
   20 dropped orphans by raw strings.
4. **Before/after diff:** the umbrella regression (`--top-institutions`), per-country PI counts
   (`--by-country`; expect ME, PT, LV and EE counts to fall), and Sadra Sadeh's co-author affiliations
   (should keep the Crick only if it rests on ≥ 2 non-blob works).
5. **Re-run layout** only after the institution set changes, then `fetch_institutions.py --merge`.

## Open questions

- Should PIs orphaned by R5 be dropped from the euna build or kept with a "region uncertain" flag?
- Accept a partial crawl (option b) to get authorship-level leak detection for 1996–2018?
