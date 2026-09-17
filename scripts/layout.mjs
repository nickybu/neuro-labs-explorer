// Offline ForceAtlas2 layout: bakes x/y into each node of a dataset so the
// browser never runs physics on load. Run after collect_neuro.py:
//
//   node scripts/layout.mjs                        # default datasets
//   node scripts/layout.mjs data/graph_neuro.json  # a specific file
//   node scripts/layout.mjs --iterations 250 f.json
//
// For very large graphs give Node more headroom:
//   node --max-old-space-size=8192 scripts/layout.mjs data/graph_neuro.json
//
// Positions are written back atomically (temp file + rename) so an interrupted
// run cannot destroy the dataset it is reading. Re-runnable and deterministic.
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

const argv = process.argv.slice(2);
let iterOverride = null;
const files = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === "--iterations" || argv[i] === "-i") iterOverride = +argv[++i];
  else files.push(argv[i]);
}
if (files.length === 0) {
  for (const f of ["data/graph_neuro.json", "data/graph.json", "data/sample.json"]) {
    if (fs.existsSync(f)) files.push(f);
  }
}

// Deterministic seed position so runs are reproducible (FA2 needs initial x/y).
function seed(id, i, n) {
  let h = 2166136261;
  for (let k = 0; k < id.length; k++) { h ^= id.charCodeAt(k); h = Math.imul(h, 16777619); }
  const a = ((h >>> 0) % 10000) / 10000 * Math.PI * 2;
  const r = 100 + ((i / n) * 900);
  return { x: Math.cos(a) * r, y: Math.sin(a) * r };
}

function layoutFile(file) {
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  const g = new Graph({ type: "undirected", multi: true });

  data.nodes.forEach((node, i) => {
    const p = seed(node.id, i, data.nodes.length);
    // Heavier "mass" for institutions so they anchor the PIs around them.
    const size = node.type === "institution" ? 12 : node.type === "funder" ? 8 : 6;
    g.addNode(node.id, { x: p.x, y: p.y, size });
  });
  for (const l of data.links) {
    if (!g.hasNode(l.source) || !g.hasNode(l.target) || l.source === l.target) continue;
    // Affiliation is what should pull a PI toward their institution. Funding
    // is a real relationship but a poor layout force - every PI in the country
    // shares a handful of funders, which would collapse the graph into blobs.
    const weight = l.rel === "affiliated_with" ? (l.current ? 1 : 0.3)
                 : l.rel === "funded_by" ? 0
                 : 1;
    if (weight > 0) g.addEdge(l.source, l.target, { weight });
  }

  // Good defaults scaled to graph size (enables Barnes-Hut for big graphs).
  const settings = forceAtlas2.inferSettings(g);
  // inferSettings returns gravity 0.05 + strongGravityMode. Overriding gravity
  // to 1.2 gives a pleasingly tight picture up to ~25k nodes, but at 100k+ the
  // attraction overwhelms repulsion and the whole graph collapses into a solid
  // disc. Past that size, back off gravity and push repulsion up instead.
  if (g.order > 40000) {
    settings.gravity = 0.05;
    settings.strongGravityMode = false;
    settings.scalingRatio = 60;
  } else {
    settings.gravity = 1.2;
    settings.scalingRatio = 12;
  }
  settings.slowDown = 1 + Math.log(g.order);
  const iterations = iterOverride ?? (g.order > 4000 ? 500 : 300);

  const t0 = Date.now();
  forceAtlas2.assign(g, { iterations, settings });
  const secs = ((Date.now() - t0) / 1000).toFixed(1);

  // Write positions back onto the nodes.
  const pos = new Map();
  g.forEachNode((id, attr) => { pos.set(id, attr); });
  for (const node of data.nodes) {
    const p = pos.get(node.id);
    if (!p) continue;
    node.x = Math.round(p.x * 100) / 100;
    node.y = Math.round(p.y * 100) / 100;
  }
  data.meta.layout = { algo: "forceatlas2", iterations, nodes: g.order };

  // Atomic: never leave a half-written dataset behind on crash or Ctrl-C.
  const json = JSON.stringify(data);
  const tmp = file + ".tmp";
  fs.writeFileSync(tmp, json);
  fs.renameSync(tmp, file);
  // Refresh the pre-compressed sibling serve.py hands to the browser.
  const gz = file + ".gz";
  if (fs.existsSync(gz)) {
    fs.writeFileSync(gz + ".tmp", zlib.gzipSync(json, { level: 6 }));
    fs.renameSync(gz + ".tmp", gz);
  }
  const mb = (fs.statSync(file).size / 1e6).toFixed(1);
  console.log(`${path.basename(file)}: ${g.order} nodes / ${g.size} edges laid out in ${secs}s (${iterations} iters) -> ${mb} MB`);
}

for (const f of files) layoutFile(f);
