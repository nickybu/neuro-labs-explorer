"""Configuration for the OpenAlex-based UK research-lab collection pipeline.

All relevance rules live here so the definition of "relevant lab" is explicit,
auditable, and easy to tune. Nothing here fabricates data — it only decides
which real OpenAlex records to keep.
"""

# Polite-pool contact (OpenAlex asks for an email; gives faster, more reliable service).
MAILTO = "you@example.com"

API_ROOT = "https://api.openalex.org"

# ---------------------------------------------------------------------------
# Relevance model
# ---------------------------------------------------------------------------
# OpenAlex organises every "topic" under a subfield -> field -> domain hierarchy.
# We keep a PI (author) if ANY of their topics satisfies the relevance test below.
#
# Two-part test:
#   1. Topic/subfield display name matches a keyword (captures the user's intent
#      precisely: brains, cognition, evolution, ML/AI, computation, networks).
#   2. OR the topic's field is one of the "always relevant" fields.

# Field IDs (from /fields). Neuroscience + Psychology are relevant wholesale.
ALWAYS_RELEVANT_FIELDS = {
    "28",  # Neuroscience
    "32",  # Psychology
}

# For these broader fields we require a keyword match (avoids pulling in e.g.
# civil engineers, pure algebraists, agronomists who aren't in scope).
KEYWORD_GATED_FIELDS = {
    "17",  # Computer Science  -> AI/ML/computation only
    "11",  # Agricultural and Biological Sciences -> evolution/ecology only
    "26",  # Mathematics -> computational/network only
    "22",  # Engineering -> network/neural engineering only
    "18",  # Decision Sciences
    "13",  # Biochemistry, Genetics and Molecular Biology -> neuro/evo-devo only
}

# Case-insensitive substrings tested against topic + subfield display names.
RELEVANCE_KEYWORDS = [
    "neuro", "brain", "cortex", "cortical", "synap", "neural", "spiking",
    "connectom", "neuroimag", "eeg", "meg", "fmri", "electrophysiolog",
    "cogniti", "perception", "attention", "memory", "language processing",
    "psycholog", "behaviou", "behavior", "mental",
    "artificial intelligence", "machine learning", "deep learning",
    "reinforcement learning", "neural network", "computer vision",
    "natural language", "computation", "computational",
    "evolution", "phylogen", "population genetics", "ecolog", "genome evolution",
    "network", "graph", "complex systems", "dynamical system",
    "bioinformatic", "systems biology", "developmental biolog",
]

# Human-readable research "areas" used for filtering in the UI. Each area maps to
# keyword tests applied to a PI's topics/subfields. A PI can belong to several.
AREA_RULES = {
    "Neuroscience": ["neuro", "brain", "cortex", "cortical", "synap", "neural circuit",
                     "connectom", "neuroimag", "electrophysiolog", "spiking"],
    "Cognitive Science": ["cogniti", "perception", "attention", "memory",
                          "language processing", "decision", "consciousness"],
    "Psychology": ["psycholog", "behaviou", "behavior", "mental health", "emotion"],
    "AI / Machine Learning": ["artificial intelligence", "machine learning",
                              "deep learning", "reinforcement learning",
                              "neural network", "computer vision", "natural language"],
    "Computation": ["computation", "computational", "algorithm",
                    "dynamical system", "complex systems", "statistical model"],
    "Evolutionary Biology": ["evolution", "phylogen", "population genetics",
                             "ecolog", "genome evolution", "adaptation", "speciation"],
    "Networks & Connectomics": ["brain connectivity", "functional connectivity",
                                "connectom", "graph theory", "neural network",
                                "signal processing", "genomic network"],
}

# ---------------------------------------------------------------------------
# How strictly a PI must be "about" a relevant area. We only keep an author if
# their leading research (not a single stray secondary topic) is in scope.
# ---------------------------------------------------------------------------
# Number of the author's top topics to consider.
TOPIC_WINDOW = 5
# Keep the author if the single primary topic is relevant, OR at least this many
# of the top-window topics are relevant.
MIN_RELEVANT_TOPICS = 2

# ---------------------------------------------------------------------------
# Selection thresholds (tune for depth vs. legibility)
# ---------------------------------------------------------------------------
# Ignore obviously-broken merged author profiles and one-off authors.
AUTHOR_MIN_WORKS = 25
AUTHOR_MAX_WORKS = 3000
AUTHOR_MIN_CITATIONS = 200

# Per institution: how many top-cited candidate authors to fetch and screen.
CANDIDATES_PER_INSTITUTION = 120
# Per institution: cap on relevant PIs kept (keeps the graph legible).
MAX_PIS_PER_INSTITUTION = 25

# Only keep institutions with at least this much total output (drops tiny orgs).
INSTITUTION_MIN_WORKS = 2000

# Institution types to include (education = universities, facility = institutes).
INSTITUTION_TYPES = ["education", "facility"]
