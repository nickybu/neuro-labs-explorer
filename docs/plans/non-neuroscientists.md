# Plan: flag PIs who are not really neuroscientists

Status: investigation done, nothing implemented. Written 2026-09-17.

## Why this exists

A PI enters the graph by last-authoring at least two works whose OpenAlex *primary topic* is in the Neuroscience field. That bar is low, and OpenAlex's topic classifier is noisy. So the graph contains people whose labs are plainly elsewhere: a malaria immunologist with one cerebral-malaria paper, a soft-robotics group, a horticulture lab whose purslane papers were filed under neuroscience. They crowd results and undermine trust, most visibly at the Crick, where the user will recognise every name.

## Headline

- **About 15% of active PIs (6,484 of 43,544) look off-field** under the recommended rule, and 24% of winding-down PIs (5,805 of 24,489). In the UK it is 498 of 3,676 active PIs.
- **Hide them by default, never delete.** Add a flag, a "include off-field PIs" toggle, and a one-line explanation in the detail panel.
- **The rule is imperfect in a known direction.** On a hand-judged random sample it hides 26 of 40 irrelevant PIs, 8 of 31 marginal ones, and 0 of 14 core neuroscientists. About a third of irrelevant PIs stay visible. That is the price of not hiding people like Linnarsson, Longtin or Briscoe.
- **No new crawl is needed for active and winding-down PIs.** Their author records are already cached. Inactive PIs need about 390 more requests.

## Evidence

### Signal: each author's OpenAlex topics

OpenAlex returns each author's **top five topics** with work counts, each tagged with topic, subfield and field. These counts cover **every authorship position**, not just last-authored papers, so they describe a person's whole output, which is what we want for "is this a neuroscience lab".

Fetched raw for all 68,034 active and winding-down PIs into `data/cache/authors.jsonl.gz` (80 MB, 681 requests).

### Field-level share is not enough

OpenAlex files many nervous-system topics outside the Neuroscience field. Share by field alone scores Bart De Strooper (Alzheimer's) and Rickie Patani (ALS) at 12–15%.

| Definition of "neuro" topic | Active PIs under 10% | Under 25% |
|---|---|---|
| Field 28 Neuroscience only | 10,184 (23.4%) | 17,287 (39.7%) |
| + Psychology (32), Neurology (2728), Psychiatry (2738) | 6,797 (15.6%) | 11,498 (26.4%) |
| **+ 29 curated nervous-system topics filed elsewhere** | **5,844 (13.4%)** | **9,667 (22.2%)** |

The curated topics include Alzheimer's (in Medicine / Physiology), neurodevelopmental genetics, retinal development, pain, glioma, TBI, stroke, MS and spinal cord injury. The full list is in Appendix A.

### Hand audit

Seeded random samples of active PIs per share band, each judged from their top topics and their own neuro-tagged titles. **Irrelevant** means a neuroscientist browsing labs would not want them. **Marginal** means adjacent or clinical work some users would want. **Core** means a neuroscience lab.

| Curated share band | Pool | Sampled | Irrelevant | Marginal | Core |
|---|---|---|---|---|---|
| under 10% | 5,844 | 30 | 22 | 8 | 0 |
| 10–25% | 3,823 | 25 | 11 | 11 | 3 |
| 25–50% | 6,009 | 20 | 7 | 8 | 5 |
| 50–75% | 8,490 | 10 | 0 | 4 | 6 |

Representative verdicts:

- **Under 10%, irrelevant:** Fumiya Iida (soft robotics, 10 "neuro" last-authored papers), Nikolaos Tzortzakis (horticulture), Jérémie Sellam (rheumatology, one vagus-nerve trial), Stephen Fletcher (organic chemistry).
- **Under 10%, marginal:** Rory Fisher (RGS6 signalling in dopamine neurons), Gunnar Cedersund (neurovascular fMRI models), Auguste Genovesio (image analysis for Drosophila brain imaging).
- **10–25%, core:** Massimo Vergassola (olfactory navigation theory), Daniel Bertrand (nicotinic receptors), Pier Stanislao Paolucci (spiking-network models).
- **10–25%, irrelevant:** Michael Reiss (science education), Franklin Miller (bioethics), Fausto Salaffi (rheumatology).
- **25–50%, core:** Sten Linnarsson (brain cell atlases, 29%), André Longtin (computational neuroscience, 39%), Richard Gronostajski (neural stem cells).
- **25–50%, irrelevant:** Carol Ward (paleoanthropology), Shannon MacDonald (radiation oncology), Francesco Scaglione (antibiotics, kept in by a circadian topic).

**Crick** (49 PIs with author records, judged individually):

- Irrelevant: Jean Langhorne (malaria), Karen Vousden (cancer), Justin Molloy (myosin), Elke Ober (pancreas), Nicolas Tapon (Hippo signalling), Jean-Paul Vincent (Wnt), Shahid Khan (bacterial motors), Andrew Oates (segmentation clock).
- Marginal: Robin Lovell-Badge (sex determination; Sox3 pituitary papers), Verónica Moncho-Amor (SOX2 neural stem cells), Mariya Moosajee (retinal genetics), Ralf Adams (angiogenesis and axon guidance), Annalisa Pastore (neurodegenerative protein structure), John O'Neill (cellular circadian clocks).
- Core despite low share: James Briscoe (neural tube patterning, 12%), Madeline Lancaster (brain organoids, 17%), Corinne Houart (forebrain patterning, 18%), Vassilis Pachnis (enteric nervous system).

### Is the top-five proxy good enough?

For the 134 judged PIs I fetched their **full** topic distribution (one group-by request each).

- The top-five share and full share agree on average (median difference +0.01). They differ by more than 15 points for 23 of 134.
- The best full-distribution rule found (full share under 20% and fewer than 20 works on neuro topics) hides 28 of 40 irrelevant and 0 of 14 core. The recommended top-five rule hides 26 of 40 and 0 of 14.
- Full distributions for everyone would cost about 107,000 requests, roughly 11 days of free budget. **Not worth it** for two more correct hides per 40.

### Candidate rules on the judged set

Hidden counts are unweighted on the random sample. "Est. active hidden" is over all 43,544 active PIs.

| Rule | Est. active hidden | Irrelevant hidden | Marginal hidden | Core hidden | Crick core hidden |
|---|---|---|---|---|---|
| share < 10% | 5,844 | 22/40 | 8/31 | 0/14 | none |
| share < 25% | 9,667 | 33/40 | 19/31 | 3/14 | Briscoe, Lancaster, Houart |
| share < 25% and largest neuro topic < 10 | 6,738 | 27/40 | 10/31 | 0/14 | none |
| **share < 25% and largest neuro topic < 10 and neuro method tags < 3** | **6,484** | **26/40** | **8/31** | **0/14** | **none** |
| share < 50% and largest neuro topic < 20 | 10,246 | 33/40 | 18/31 | 1/14 | Houart, Andrés |

Caveat: 14 core PIs is a small sample. Zero core hidden is encouraging, not proof.

## Recommended rule

A PI is **off-field** when all three hold:

1. **Curated neuro share under 25%.** Share = work counts in the author's top-five topics that are in field 28 or 32, subfield 2728 or 2738, or the Appendix A list, divided by the top-five total.
2. **Largest neuro topic under 10 works.** Neuro here means field 28, subfield 2728 or Appendix A, deliberately excluding Psychology. This keeps developmental neurobiologists whose share is low but who have a real neuro topic: Briscoe has 37 works in "Neurogenesis", Lancaster 20.
3. **Fewer than 3 neuroscience-specific method tags** from `data/tags_neuro.json`. This rescues people whose OpenAlex profile is merged with a namesake. Ilya Bezprozvanny (UTSW, calcium and Alzheimer's) has a profile dominated by Social Sciences, and P. Mermelstein's by speech engineering, yet their own last-authored papers carry six specific neuro method tags each.

Specific method tags are the categories Electrophysiology, Optical imaging & sensors, Human neuroimaging, and Stimulation & neurotechnology. The set also includes em_connectomics, tissue_clearing, psychophysics, eye_tracking, rodent_behaviour, vr_headfixed, sleep_recording, neuropsych_tests, cognitive_models, neuromorphic, pose_tracking, viral_tracing and in_utero. It excludes mri and pet, which clinicians use for everything, and all organism tags, since immunologists use mice too.

Why these thresholds:

- **25% share** is where the audit turns. Below it most PIs are irrelevant or marginal, and the core ones there are rescued by conditions 2 and 3.
- **10 works on the largest neuro topic** keeps every judged core PI with margin: the lowest among core PIs under 25% share is Corinne Houart at 18, then Madeline Lancaster at 20. Every off-field Crick PI named above has 0.
- **3 method tags** is where tags stop being incidental. With a threshold of 1, a single clinical paper would rescue people like Jérémie Sellam (rheumatology, one vagus-nerve trial). The rescue still keeps some engineers who are arguably irrelevant, such as Carmen Mezura-Godoy (BCI usability reviews, 4 tags).

## Implementation plan

1. **Fetch inactive PIs' author records.** Extend the existing fetch into a resumable `pipeline/fetch_authors.py` that appends raw records to `data/cache/authors.jsonl.gz` and skips cached ids. About 390 requests.
2. **Compute relevance in `pipeline/enrich_text.py tag`**, which already loads the PI set and writes the per-PI tag counts that condition 3 needs. Add `pipeline/relevance.py` holding the Appendix A topic ids, the specific-method set and one function that returns `{share, neuroTopicMax, specificTags, offField, dominantField, dominantShare}`. Write it to `tags_neuro.json` under `pis[id].rel`. The graph file stays untouched, so no re-layout, consistent with how tags are already handled.
3. **Record the rule in `tags_neuro.json` meta**: thresholds, topic list version and counts hidden per status. Changing a threshold is then a re-run of `tag`, not a code search.
4. **Graph page (`web/index.html`).** Add `q.includeOffField` (default false) to the query state, skip off-field PIs in the `runQuery` filter unless it is set or the PI is pinned, and add an "Include off-field PIs (n)" checkbox under Lab status. Show the count of hidden matches next to the result count so the filter is never silent.
5. **Detail panel.** For any PI with `rel`, show one line such as "Mostly publishes in Medicine (71% of top topics)". Off-field PIs get a small "off-field" tag. This makes the judgement inspectable rather than hidden.
6. **Search page (`web/search.html`).** Apply the same default and toggle.
7. **Inspector.** `pipeline/inspect_graph.py --pi` prints the relevance fields, so a disputed case can be checked in one command.

## Edge cases

- **Merged author profiles** inflate or deflate share. François Guillemot's top topic is "Vietnamese History" (share 28%, kept by his neurogenesis topic). Condition 3 rescues some cases. A per-PI override list, `pipeline/relevance_overrides.json` in the style of `umbrellas.json`, handles the rest by hand.
- **Psychology counts toward share** (condition 1) but not toward the largest-topic test (condition 2). That keeps paleoanthropologists and bioethicists from being rescued by a psychology topic. If psychology becomes its own scope later, revisit this.
- **Clinicians** such as neurosurgeons, psychiatrists and neuro-oncologists mostly fall in the marginal band and stay visible. Hiding them is a user decision, not something this rule should decide silently.
- **Topics lag and change.** OpenAlex recomputes them. Store the fetch date in meta and refetch on a data refresh.
- **Pinned and deep-linked PIs** are always shown, so a link to an off-field PI never lands on an empty page.
- **The rule uses tag counts from 2019–2026.** A PI with no recent last-authored work has no tags, so condition 3 cannot rescue them. That only affects inactive PIs, which are hidden by default anyway.

## Validation

- **Regression set.** Appendix B lists 134 hand-judged PIs with their verdicts. After any change to the rule or topic list, recompute and check that no core PI flips to hide and that hides of irrelevant PIs do not drop.
- **Crick spot-check** by the user, who knows these labs. Appendix B marks Crick-associated PIs.
- **Counts sanity.** Off-field share should stay roughly flat across countries: currently 12.5–17.3% of active PIs in the eight largest.
- **Default views.** Re-run the saved graph queries (UK + two-photon + mouse, Crick + London) and confirm no expected lab disappears.

## Open decisions for the user

1. Hide off-field PIs by default, or only badge them?
2. Should clinicians (neurosurgery, psychiatry, neuro-oncology) stay visible?
3. Is psychology in scope for share? Today it is, since cognitive science is on the roadmap.

## Cost of this investigation

822 OpenAlex requests: 681 author records, 134 full topic distributions, 2 topic metadata, 5 probes.

Raw data written, all under `data/cache/` (gitignored):

- `authors.jsonl.gz`: author records for all active and winding-down PIs.
- `author_fields.jsonl.gz`: full topic distributions for the 134 judged PIs.
- `topics.jsonl.gz`: metadata for 112 topics outside the top-five lists.

## Appendix A: nervous-system topics OpenAlex files outside neuroscience

| Topic id | Topic | OpenAlex field / subfield |
|---|---|---|
| T10086 | Alzheimer's disease research and treatments | Medicine / Physiology |
| T11304 | Advanced Neuroimaging Techniques and Applications | Medicine / Radiology, Nuclear Medicine and Imaging |
| T11772 | Genetics and Neurodevelopmental Disorders | Biochemistry, Genetics and Molecular Biology / Genetics |
| T10691 | Retinal Development and Disorders | Biochemistry, Genetics and Molecular Biology / Molecular Biology |
| T10196 | Pain Mechanisms and Treatments | Medicine / Physiology |
| T10510 | Stroke Rehabilitation and Recovery | Medicine / Rehabilitation |
| T10129 | Glioma Diagnosis and Treatment | Medicine / Genetics |
| T10416 | Traumatic Brain Injury Research | Medicine / Epidemiology |
| T10227 | Acute Ischemic Stroke Management | Medicine / Epidemiology |
| T11071 | Treatment of Major Depression | Medicine / Pharmacology |
| T10137 | Multiple Sclerosis Research Studies | Medicine / Pathology and Forensic Medicine |
| T11184 | Neonatal and fetal brain pathology | Medicine / Pediatrics, Perinatology and Child Health |
| T10816 | Cerebrovascular and Carotid Artery Diseases | Medicine / Pulmonary and Respiratory Medicine |
| T10925 | Spinal Cord Injury Research | Medicine / Pathology and Forensic Medicine |
| T12400 | Neurogenetic and Muscular Disorders Research | Medicine / Genetics |
| T12552 | Fetal and Pediatric Neurological Disorders | Medicine / Pediatrics, Perinatology and Child Health |
| T10867 | Intensive Care Unit Cognitive Disorders | Medicine / Critical Care and Intensive Care Medicine |
| T12023 | Cholinesterase and Neurodegenerative Diseases | Medicine / Pharmacology |
| T12459 | Nerve Injury and Rehabilitation | Medicine / Surgery |
| T10576 | Opioid Use Disorder Treatment | Medicine / Public Health, Environmental and Occupational Health |
| T10954 | Peripheral Nerve Disorders | Medicine / Radiology, Nuclear Medicine and Imaging |
| T11335 | Prion Diseases and Protein Misfolding | Biochemistry, Genetics and Molecular Biology / Molecular Biology |
| T12193 | Trigeminal Neuralgia and Treatments | Medicine / Pathology and Forensic Medicine |
| T13077 | Cancer-related cognitive impairment studies | Medicine / Pulmonary and Respiratory Medicine |
| T12476 | Intraoperative Neuromonitoring and Anesthetic Effects | Medicine / Surgery |
| T13966 | Neurological and metabolic disorders | Medicine / Endocrinology, Diabetes and Metabolism |
| T12237 | Congenital gastrointestinal and neural anomalies | Medicine / Surgery |
| T11904 | Spatial Cognition and Navigation | Engineering / Automotive Engineering |
| T11345 | Cognitive and developmental aspects of mathematical skills | Mathematics / Statistics and Probability |

## Appendix B: hand-judged regression set

Crick-associated PIs first, then the random samples, each ordered by verdict and share. "Curated share" is the top-five share defined above, "largest neuro topic" the work count on the biggest field-28 / Neurology / Appendix A topic, and "rule" the recommended rule's outcome.

| PI | Institution | Status | Curated share | Largest neuro topic | Neuro method tags | Verdict | Rule |
|---|---|---|---|---|---|---|---|
| Karen H. Vousden (Crick) | Cancer Research UK | winding_down | 0% | 0 | 0 | irrelevant | hide |
| Jean Langhorne (Crick) | The Francis Crick Institute | winding_down | 0% | 0 | 0 | irrelevant | hide |
| Elke A. Ober (Crick) | University of Copenhagen | winding_down | 0% | 0 | 0 | irrelevant | hide |
| Justin E. Molloy (Crick) | The Francis Crick Institute | winding_down | 0% | 0 | 0 | irrelevant | hide |
| Nicolas Tapon (Crick) | The Francis Crick Institute | active | 0% | 0 | 0 | irrelevant | hide |
| Andrew C. Oates (Crick) | University College London | active | 7% | 12 | 0 | irrelevant | keep |
| Jean‐Paul Vincent (Crick) | The Francis Crick Institute | active | 12% | 17 | 0 | irrelevant | keep |
| Shahid Khan (Crick) | Albert Einstein College of Medicine | winding_down | 23% | 20 | 0 | irrelevant | keep |
| Robin Lovell‐Badge (Crick) | The Francis Crick Institute | active | 0% | 0 | 0 | marginal | hide |
| Verónica Moncho-Amor (Crick) | The Francis Crick Institute | active | 17% | 5 | 0 | marginal | hide |
| Ralf H. Adams (Crick) | Max Planck Institute for Molecular Biomedi | active | 23% | 55 | 0 | marginal | keep |
| Ander Matheu (Crick) | Ikerbasque | active | 27% | 32 | 0 | marginal | keep |
| Annalisa Pastore (Crick) | King's College London | active | 28% | 110 | 0 | marginal | keep |
| Alex P. Gould (Crick) | Medical Research Council | winding_down | 31% | 30 | 0 | marginal | keep |
| David G. Wilkinson (Crick) | The Francis Crick Institute | winding_down | 33% | 83 | 0 | marginal | keep |
| Mariya Moosajee (Crick) | University College London | active | 44% | 109 | 0 | marginal | keep |
| John S. O’Neill (Crick) | MRC Laboratory of Molecular Biology | active | 60% | 85 | 0 | marginal | keep |
| James Briscoe (Crick) | The Francis Crick Institute | active | 12% | 37 | 0 | core | keep |
| Madeline A. Lancaster (Crick) | MRC Laboratory of Molecular Biology | active | 17% | 20 | 0 | core | keep |
| Corinne Houart (Crick) | King's College London | active | 18% | 18 | 0 | core | keep |
| François Guillemot (Crick) | Institut de génétique et de biologie moléc | winding_down | 28% | 143 | 2 | core | keep |
| Marta Andrés (Crick) | University College London | active | 36% | 17 | 0 | core | keep |
| Joerg T. Albert (Crick) | University College London | active | 49% | 30 | 0 | core | keep |
| David Ogden (Crick) | Université Paris Cité | winding_down | 52% | 30 | 3 | core | keep |
| Noelia Urbán (Crick) | Institute of Molecular Biotechnology | active | 53% | 21 | 1 | core | keep |
| Irene Miguel‐Aliaga (Crick) | Imperial College London | active | 54% | 37 | 0 | core | keep |
| Iris Salecker (Crick) | École Normale Supérieure - PSL | active | 55% | 30 | 0 | core | keep |
| Vassilis Pachnis (Crick) | The Francis Crick Institute | winding_down | 57% | 70 | 2 | core | keep |
| Tobias Ackels (Crick) | University of Bonn | active | 59% | 27 | 2 | core | keep |
| Akhilesh B. Reddy (Crick) | Translational Therapeutics (United States) | active | 59% | 72 | 3 | core | keep |
| Lucia L. Prieto-Godino (Crick) | The Francis Crick Institute | active | 59% | 29 | 1 | core | keep |
| Andrea Serio (Crick) | King's College London | active | 61% | 11 | 1 | core | keep |
| Rickie Patani (Crick) | University College London | active | 69% | 64 | 0 | core | keep |
| Andreas T. Schaefer (Crick) | The Francis Crick Institute | active | 73% | 60 | 4 | core | keep |
| Johannes Kohl (Crick) | The Francis Crick Institute | active | 73% | 10 | 0 | core | keep |
| Benedikt Berninger (Crick) | Johannes Gutenberg University Mainz | active | 74% | 93 | 2 | core | keep |
| Izumi Fukunaga (Crick) | The Francis Crick Institute | winding_down | 76% | 32 | 9 | core | keep |
| Mihály Köllő (Crick) | The Francis Crick Institute | active | 81% | 14 | 1 | core | keep |
| Bart De Strooper (Crick) | University College London | active | 82% | 370 | 3 | core | keep |
| Ede Rancz (Crick) | The Francis Crick Institute | active | 91% | 16 | 4 | core | keep |
| Troy W. Margrie (Crick) | University College London | active | 100% | 59 | 5 | core | keep |
| Denis Burdakov (Crick) | ETH Zurich | active | 100% | 129 | 7 | core | keep |
| Katharina Schmack (Crick) | The Francis Crick Institute | active | 100% | 14 | 0 | core | keep |
| Julia J. Harris (Crick) | University College London | active | 100% | 11 | 3 | core | keep |
| Petr Znamenskiy (Crick) | The Francis Crick Institute | active | 100% | 15 | 4 | core | keep |
| Mahesh Karnani (Crick) | University of Edinburgh | active | 100% | 18 | 3 | core | keep |
| Timothy V. P. Bliss (Crick) | The Francis Crick Institute | active | 100% | 9 | 0 | core | keep |
| Athena Akrami (Crick) | University College London | active | 100% | 37 | 3 | core | keep |
| M. Florencia Iacaruso (Crick) | The Francis Crick Institute | active | 100% | 15 | 2 | core | keep |
| Fumiya Iida | University of Cambridge | active | 0% | 0 | 0 | irrelevant | hide |
| Till Ittermann | Universitätsmedizin Greifswald | active | 0% | 0 | 0 | irrelevant | hide |
| Hannah S. Stuart | University of California, Berkeley | active | 0% | 0 | 0 | irrelevant | hide |
| Livia Perfetto | Human Technopole | active | 0% | 0 | 0 | irrelevant | hide |
| Sean M. Ronnekleiv‐Kelly | University of Wisconsin–Madison | active | 0% | 0 | 0 | irrelevant | hide |
| Di Wei | University of Cambridge | active | 0% | 0 | 0 | irrelevant | hide |
| Chong H. Ahn | University of Cincinnati | active | 0% | 0 | 0 | irrelevant | hide |
| Nikolaos Tzortzakis | Cyprus University of Technology | active | 0% | 0 | 0 | irrelevant | hide |
| Lynn B. Jorde | University of Utah | active | 0% | 0 | 0 | irrelevant | hide |
| Franziska Mathis-Ullrich | Friedrich-Alexander-Universität Erlangen-N | active | 0% | 0 | 0 | irrelevant | hide |
| Sudhiranjan Gupta | Central Texas Veterans Health Care System | active | 0% | 0 | 0 | irrelevant | hide |
| Stephen P. Fletcher | Mansfield University | active | 0% | 0 | 0 | irrelevant | hide |
| Katherine S. O’Neal | University of Oklahoma Health Sciences Cen | active | 0% | 0 | 0 | irrelevant | hide |
| Qian Chen | Brown University | active | 0% | 0 | 0 | irrelevant | hide |
| Ralf Peeters | Maastricht University | active | 0% | 0 | 0 | irrelevant | hide |
| José I. Recio-Rodríguez | Universidad de Salamanca | active | 0% | 0 | 2 | irrelevant | hide |
| Jérémie Sellam | Sorbonne Université | active | 0% | 0 | 1 | irrelevant | hide |
| Kay Poulton | Manchester Academic Health Science Centre | active | 0% | 0 | 0 | irrelevant | hide |
| Maria Gorlatova | Duke University | active | 0% | 0 | 2 | irrelevant | hide |
| Alfred Marc Iloreta | Icahn School of Medicine at Mount Sinai | active | 0% | 0 | 0 | irrelevant | hide |
| Roland Bingisser | University Hospital of Basel | active | 0% | 0 | 0 | irrelevant | hide |
| Peter W. Nathanielsz | University of Wyoming | active | 10% | 0 | 0 | irrelevant | hide |
| Laura H. Blumenschein | Purdue University West Lafayette | active | 12% | 12 | 1 | irrelevant | keep |
| Shirley Luckhart | University of Idaho | active | 12% | 29 | 0 | irrelevant | keep |
| Chengcheng Jia | Toronto Metropolitan University | active | 13% | 6 | 2 | irrelevant | hide |
| Michael Reiß | University College London | active | 14% | 0 | 0 | irrelevant | hide |
| David Rodríguez‐Arias | Universidad de Granada | active | 14% | 0 | 0 | irrelevant | hide |
| Arne Hansen | University of Bremen | active | 15% | 30 | 1 | irrelevant | keep |
| Franklin G. Miller | Cornell University | active | 16% | 73 | 1 | irrelevant | keep |
| Carmen Mezura-Godoy | Universidad Veracruzana | active | 16% | 8 | 4 | irrelevant | keep |
| Luc J. Martin | Université de Moncton | active | 17% | 13 | 0 | irrelevant | keep |
| Eniko T. Enikov | University of Arizona | active | 18% | 15 | 0 | irrelevant | keep |
| Fausto Salaffi | Marche Polytechnic University | active | 18% | 0 | 1 | irrelevant | hide |
| Carol V. Ward | University of Missouri | active | 30% | 0 | 0 | irrelevant | keep |
| Shannon M. MacDonald | Massachusetts General Hospital | active | 30% | 121 | 0 | irrelevant | keep |
| Francesco Scaglione | Azienda Socio Sanitaria Territoriale Laria | active | 32% | 47 | 0 | irrelevant | keep |
| Mohammadali M. Shoja | Nova Southeastern University | active | 33% | 43 | 0 | irrelevant | keep |
| Tobias Röddiger | Karlsruhe Institute of Technology | active | 36% | 25 | 3 | irrelevant | keep |
| Edward Meinert | Imperial College London | active | 41% | 15 | 1 | irrelevant | keep |
| Debra A. Harley | University of Kentucky | active | 43% | 0 | 0 | irrelevant | keep |
| Huazhong Shu | Université de Rennes | active | 0% | 0 | 3 | marginal | keep |
| Gunnar Cedersund | Linköping University | active | 0% | 0 | 3 | marginal | keep |
| I. Kovács | Northwestern University | active | 0% | 0 | 0 | marginal | hide |
| Marco Segatto | University of Molise | active | 0% | 0 | 0 | marginal | hide |
| Shelley L. Berger | University of Pennsylvania | active | 0% | 0 | 1 | marginal | hide |
| Daniel J. Kosman | University at Buffalo, State University of | active | 0% | 0 | 0 | marginal | hide |
| Auguste Genovesio | Institut de Biologie de l'École Normale Su | active | 0% | 0 | 0 | marginal | hide |
| Rory A. Fisher | University of Iowa | active | 10% | 12 | 0 | marginal | keep |
| Cinzia Rinaldo | Institute of Molecular Biology and Patholo | active | 12% | 8 | 0 | marginal | hide |
| Donald G. Welsh | Western University | active | 13% | 28 | 3 | marginal | keep |
| László Hunyady | Semmelweis University | active | 13% | 34 | 0 | marginal | keep |
| Matt S. Stock | University of Central Florida | active | 14% | 38 | 2 | marginal | keep |
| Alyssa E. Johnson | Louisiana State University | active | 15% | 8 | 0 | marginal | hide |
| Jiřı́ Novotný | Charles University | active | 20% | 31 | 0 | marginal | keep |
| Laura Maria Comella | University of Freiburg | active | 20% | 7 | 1 | marginal | hide |
| Anne Eichmann | Collège de France | active | 21% | 61 | 0 | marginal | keep |
| Mijke P. Lambregtse‐van den Berg | Erasmus MC | active | 23% | 10 | 0 | marginal | keep |
| Nina C. Weber | University of Amsterdam | active | 24% | 45 | 0 | marginal | keep |
| Christian Matula | Medical University of Vienna | active | 24% | 10 | 0 | marginal | keep |
| Stefano Strano | Sapienza University of Rome | active | 28% | 8 | 0 | marginal | keep |
| Roman V. Kondratov | Cleveland State University | active | 40% | 49 | 0 | marginal | keep |
| Fabio Cofano | University of Turin | active | 41% | 4 | 0 | marginal | keep |
| Giorgia Girotto | University of Trieste | active | 43% | 55 | 0 | marginal | keep |
| Marco Fiore | Institute of Cell Biology and Neurobiology | active | 45% | 58 | 0 | marginal | keep |
| Manuel Pontes | Rowan University | active | 47% | 0 | 0 | marginal | keep |
| Cristina Rodriguez‐Fontenla | Universidade de Santiago de Compostela | active | 47% | 13 | 0 | marginal | keep |
| Robert A. Barton | Durham University | active | 49% | 0 | 0 | marginal | keep |
| Melissa Tovin | Nova Southeastern University | active | 54% | 11 | 0 | marginal | keep |
| Khalid H. Abed | Jackson State University | active | 57% | 11 | 2 | marginal | keep |
| Simon J. Williams | University of Warwick | active | 68% | 20 | 0 | marginal | keep |
| Andrei Corneliu Holman | Alexandru Ioan Cuza University | active | 71% | 22 | 0 | marginal | keep |
| Massimo Vergassola | University of California San Diego | active | 18% | 24 | 0 | core | keep |
| Pier Stanislao Paolucci | Istituto Nazionale di Fisica Nucleare | active | 19% | 48 | 4 | core | keep |
| Daniel Bertrand | University of Geneva | active | 21% | 82 | 0 | core | keep |
| Sten Linnarsson | Karolinska Institutet | active | 29% | 32 | 0 | core | keep |
| Federico Dajas‐Bailador | University of Nottingham | active | 35% | 6 | 0 | core | keep |
| André Longtin | University of Ottawa | active | 39% | 201 | 3 | core | keep |
| Richard M. Gronostajski | University at Buffalo, State University of | active | 44% | 38 | 0 | core | keep |
| Jie Lu | Imaging, Brain, and Neuropsychiatry | active | 47% | 108 | 7 | core | keep |
| Derek Daniels | University at Buffalo, State University of | active | 55% | 48 | 0 | core | keep |
| Jeannette Hübener‐Schmid | University of Tübingen | active | 59% | 57 | 0 | core | keep |
| Jeffrey L. Goldberg | Stanford University | active | 66% | 89 | 2 | core | keep |
| Daniele Bertoglio | University of Antwerp | active | 69% | 37 | 0 | core | keep |
| Laurence Mouchnino | Laboratoire de Neurosciences Cognitives | active | 73% | 9 | 1 | core | keep |
| T Hummel | University Hospital Carl Gustav Carus | active | 73% | 5 | 0 | core | keep |
