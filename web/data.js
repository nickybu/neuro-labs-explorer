// Shared dataset loader + constants for both pages.
//
// The lab tier no longer exists as its own node type - it was 1:1 with each PI
// and carried only "{Surname} Group", so it is now a `labLabel` field. Nodes
// are institution / pi / funder.
const NODE_COLORS = {
  institution: "#4c8dff",
  pi: "#f0883e",
  funder: "#a371f7",
};

// Status drives the default view: a PI who still last-authors recently is
// running a lab; the others are kept but hidden unless asked for.
const STATUS_COLORS = {
  active: "#f0883e",
  winding_down: "#b9873f",
  inactive: "#6e7681",
};
const STATUS_LABELS = {
  active: "Active",
  winding_down: "Winding down",
  inactive: "Inactive / retired",
};

const CAREER_COLOR = "#db61a2";
const FUNDING_COLOR = "#6f42c1";

// Newest dataset first. serve.py transparently swaps in a pre-compressed .gz
// sibling, so these stay plain .json paths.
const DATASET_PATHS = [
  "../data/graph_neuro.json",
  "../data/graph.json",
  "../data/sample.json",
];

async function loadData() {
  const tried = [];
  for (const path of DATASET_PATHS) {
    try {
      const res = await fetch(path);
      if (!res.ok) { tried.push(`${path} (${res.status})`); continue; }
      const data = await res.json();
      data._source = path.split("/").pop();
      return data;
    } catch (e) {
      // A parse/OOM failure here must not look like "file absent" - surface it
      // rather than silently falling through to the tiny sample dataset.
      tried.push(`${path} (${e.message})`);
    }
  }
  throw new Error(
    "No dataset could be loaded.\nTried:\n  " + tried.join("\n  ") +
    "\n\nRun: python3 pipeline/collect_neuro.py --region euna"
  );
}

// Index helpers reused across pages.
function indexGraph(data) {
  const byId = new Map();
  for (const n of data.nodes) byId.set(n.id, n);
  return { byId };
}

function fmtInt(n) {
  return (n || 0).toLocaleString();
}

// "1998-2026" / "2026" / "" - PI career span for the detail panel and cards.
function yearSpan(n) {
  if (!n.firstYear && !n.lastYear) return "";
  if (n.firstYear === n.lastYear) return String(n.firstYear);
  return `${n.firstYear ?? "?"}-${n.lastYear ?? "?"}`;
}

function escapeHTML(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// ---------------------------------------------------------------------------
// Enrichment files (both optional - the graph must still work without them).
// tags_neuro.json : per-PI method / model-system tag counts (pipeline/enrich_text.py tag)
// works_neuro.json: per-PI [year, title, [tagIds]] list for the same window
// ---------------------------------------------------------------------------
const TAGS_PATH = "../data/tags_neuro.json";
const WORKS_PATH = "../data/works_neuro.json";

async function loadOptionalJSON(path) {
  try {
    const res = await fetch(path);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.warn(`optional dataset ${path} not loaded: ${e.message}`);
    return null;
  }
}
const loadTags = () => loadOptionalJSON(TAGS_PATH);
const loadWorks = () => loadOptionalJSON(WORKS_PATH);

// Fallback only: institution nodes carry a full `country` name once
// fetch_institutions.py has merged geo; this covers nodes without a record.
const COUNTRY_NAMES = {
  AL: "Albania", AD: "Andorra", AT: "Austria", BY: "Belarus", BE: "Belgium",
  BA: "Bosnia and Herzegovina", BG: "Bulgaria", HR: "Croatia", CY: "Cyprus",
  CZ: "Czechia", DK: "Denmark", EE: "Estonia", FI: "Finland", FR: "France",
  DE: "Germany", GR: "Greece", HU: "Hungary", IS: "Iceland", IE: "Ireland",
  IT: "Italy", LV: "Latvia", LI: "Liechtenstein", LT: "Lithuania", LU: "Luxembourg",
  MT: "Malta", MD: "Moldova", MC: "Monaco", ME: "Montenegro", NL: "Netherlands",
  MK: "North Macedonia", NO: "Norway", PL: "Poland", PT: "Portugal", RO: "Romania",
  RS: "Serbia", SK: "Slovakia", SI: "Slovenia", ES: "Spain", SE: "Sweden",
  CH: "Switzerland", UA: "Ukraine", GB: "United Kingdom", XK: "Kosovo",
  SM: "San Marino", VA: "Vatican City", US: "United States", CA: "Canada", MX: "Mexico",
};
function countryName(cc) {
  return COUNTRY_NAMES[cc] || cc || "";
}

// "Oxford, United Kingdom" / "United Kingdom" / "" for an institution node.
function placeOf(inst) {
  if (!inst) return "";
  const country = inst.country || countryName(inst.cc);
  return inst.city ? `${inst.city}, ${country}` : country;
}

// Ranked "Patch clamp ×5" chips from a tags record {m:{id:n}, o:{id:n}}.
// `tagLabel` is a Map(id -> label); `highlight` is a Set of ids to emphasise.
function tagChipsHTML(rec, tagLabel, max, highlight) {
  if (!rec) return "";
  const all = [];
  for (const g of ["o", "m"]) {
    for (const [id, n] of Object.entries(rec[g] || {})) all.push([id, n, g]);
  }
  all.sort((a, b) => (highlight?.has(b[0]) - highlight?.has(a[0])) || b[1] - a[1]);
  return all.slice(0, max || 6).map(([id, n, g]) =>
    `<span class="tag ${g === "o" ? "tag-org" : "tag-meth"}${highlight?.has(id) ? " tag-hit" : ""}">` +
    `${escapeHTML(tagLabel.get(id) || id)} <span class="n">×${n}</span></span>`).join("");
}
