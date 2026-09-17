"""Controlled vocabulary for tagging works with research methods and model systems.

Each tag is matched two ways, either of which counts as a hit:

* ``re``   - regex alternatives applied to the lowercased, normalised
             title + abstract. Joined into ONE pattern per tag, fenced with
             ``(?<![a-z0-9])`` / ``(?![a-z0-9])`` rather than ``\\b`` because
             several alternatives end in punctuation (``ca2+``, ``c. elegans``).
* ``mesh`` - exact MeSH descriptor names (PubMed-indexed works only, so this
             is additive: preprints never carry MeSH).

Tune by running ``python3 pipeline/enrich_text.py audit`` after a ``tag`` run,
editing here, bumping ``VOCAB_VERSION`` and re-running ``tag`` (minutes, no
API calls - the raw text is cached).

Known-ambiguous short tokens to watch in audits: pet, meg, cno, aav, gaze,
bats, cats, dbs, tms, erps.
"""
from __future__ import annotations

import re

VOCAB_VERSION = "2026-09-17.1"

# id -> (label, [regex alternatives], [MeSH descriptor names])
ORGANISMS: dict[str, tuple[str, list[str], list[str]]] = {
    "mouse":      ("Mouse", [r"mice", r"mouse", r"murine", r"mus musculus"],
                   ["Mice", "Mice, Inbred C57BL", "Mice, Transgenic", "Mice, Knockout",
                    "Mice, Inbred BALB C", "Mice, Inbred Strains"]),
    "rat":        ("Rat", [r"rats?", r"rattus"],
                   ["Rats", "Rats, Sprague-Dawley", "Rats, Wistar", "Rats, Long-Evans"]),
    "human":      ("Human", [r"humans?", r"patients?", r"participants?",
                             r"healthy (?:adults?|volunteers?|controls?|subjects?)"],
                   ["Humans"]),
    "macaque":    ("Macaque / NHP", [r"macaques?", r"macaca", r"rhesus", r"monkeys?",
                                     r"non-?human primates?"],
                   ["Macaca mulatta", "Macaca fascicularis", "Macaca", "Primates"]),
    "marmoset":   ("Marmoset", [r"marmosets?", r"callithrix"], ["Callithrix"]),
    "drosophila": ("Drosophila", [r"drosophila", r"fruit ?fl(?:y|ies)", r"melanogaster"],
                   ["Drosophila", "Drosophila melanogaster"]),
    "zebrafish":  ("Zebrafish", [r"zebrafish", r"danio rerio"], ["Zebrafish"]),
    "c_elegans":  ("C. elegans", [r"c\. ?elegans", r"caenorhabditis"],
                   ["Caenorhabditis elegans"]),
    "songbird":   ("Songbird", [r"songbirds?", r"zebra finch(?:es)?", r"taeniopygia",
                                r"bengalese finch(?:es)?"],
                   ["Finches", "Songbirds"]),
    "xenopus":    ("Xenopus", [r"xenopus", r"tadpoles?"], ["Xenopus", "Xenopus laevis"]),
    "ferret":     ("Ferret", [r"ferrets?"], ["Ferrets"]),
    "aplysia":    ("Aplysia", [r"aplysia"], ["Aplysia"]),
    "honeybee":   ("Honeybee / bumblebee", [r"honey ?bees?", r"apis mellifera",
                                            r"bumble ?bees?"],
                   ["Bees"]),
    # Bare "cat"/"bat" are abbreviations far more often than animals (CAT =
    # Comprehensive Aphasia Test, BAT = brown adipose tissue) - audited 2026-09.
    "cat":        ("Cat", [r"felis catus", r"domestic cats?", r"feline",
                           r"(?:adult|anesthetized|anaesthetized|awake) cats"],
                   ["Cats"]),
    "pig":        ("Pig / minipig", [r"pigs?", r"minipigs?", r"porcine", r"sus scrofa"],
                   ["Swine", "Swine, Miniature"]),
    "bat":        ("Bat", [r"(?:fruit|vampire|egyptian|big brown|little brown) bats?",
                           r"bat (?:echolocation|navigation|flight|species|hippocamp\w+)",
                           r"chiroptera", r"echolocat\w+", r"rousettus", r"eptesicus", r"myotis"],
                   ["Chiroptera"]),
    "cephalopod": ("Cephalopod", [r"octopus", r"cuttlefish", r"squid", r"cephalopods?"],
                   ["Cephalopoda", "Octopodiformes", "Decapodiformes"]),
}

METHODS: dict[str, tuple[str, list[str], list[str]]] = {
    "patch_clamp":      ("Patch clamp",
                         [r"patch[- ]clamp", r"whole[- ]cell (?:recording|patch)s?",
                          r"voltage[- ]clamp", r"current[- ]clamp"],
                         ["Patch-Clamp Techniques"]),
    "extracellular":    ("Extracellular ephys",
                         [r"extracellular recordings?", r"single[- ]units?", r"multi[- ]unit",
                          r"tetrodes?", r"spike sorting", r"local field potentials?", r"lfps?"],
                         []),
    "neuropixels":      ("Neuropixels", [r"neuropixels?"], []),
    "two_photon":       ("Two-photon imaging",
                         [r"two[- ]photon", r"2[- ]photon", r"multi-?photon"],
                         ["Microscopy, Fluorescence, Multiphoton"]),
    "calcium_imaging":  ("Calcium imaging",
                         [r"calcium imaging", r"gcamp\d*[a-z]?", r"ca2\+ imaging",
                          r"calcium indicators?", r"miniscopes?"],
                         []),
    "optogenetics":     ("Optogenetics",
                         [r"optogenetic(?:s|ally)?", r"channelrhodopsin", r"chr2",
                          r"halorhodopsin", r"archt?"],
                         ["Optogenetics"]),
    "chemogenetics":    ("Chemogenetics (DREADDs)",
                         [r"chemogenetic(?:s|ally)?", r"dreadds?", r"clozapine[- ]n[- ]oxide",
                          r"cno"],
                         []),
    "fiber_photometry": ("Fiber photometry", [r"fibe?r[- ]photometry"], []),
    "fmri":             ("fMRI",
                         [r"fmri", r"functional (?:magnetic resonance|mri)",
                          r"bold (?:signal|response|fmri|contrast)", r"resting[- ]state"],
                         []),
    "mri":              ("Structural / diffusion MRI",
                         [r"mri", r"magnetic resonance imaging", r"diffusion tensor", r"dti",
                          r"tractography", r"voxel[- ]based morphometry"],
                         ["Magnetic Resonance Imaging", "Diffusion Tensor Imaging",
                          "Diffusion Magnetic Resonance Imaging"]),
    "eeg":              ("EEG / ERP",
                         [r"eeg", r"electroencephalogra(?:phy|m|phic)",
                          r"event[- ]related potentials?", r"erps?"],
                         ["Electroencephalography", "Evoked Potentials"]),
    "meg":              ("MEG", [r"meg", r"magnetoencephalogra(?:phy|m|phic)"],
                         ["Magnetoencephalography"]),
    "ecog":             ("Intracranial EEG / ECoG",
                         [r"ecog", r"electrocorticogra\w+", r"intracranial (?:eeg|recordings?)",
                          r"stereo-?eeg", r"seeg", r"depth electrodes?"],
                         ["Electrocorticography"]),
    "tms_tdcs":         ("TMS / tDCS",
                         [r"tms", r"transcranial magnetic", r"tdcs", r"tacs",
                          r"transcranial (?:direct|alternating|electrical) current"],
                         ["Transcranial Magnetic Stimulation",
                          "Transcranial Direct Current Stimulation"]),
    "dbs":              ("Deep brain stimulation", [r"deep brain stimulation", r"dbs"],
                         ["Deep Brain Stimulation"]),
    "pet":              ("PET",
                         [r"positron emission",
                          r"pet (?:imaging|scans?|tracers?|ligands?|stud(?:y|ies)|data|measures?)",
                          r"(?:amyloid|tau|fdg|tspo|synaptic|dopamine|brain) pet", r"pet[-/ ]?(?:mri?|ct)"],
                         ["Positron-Emission Tomography",
                          "Positron Emission Tomography Computed Tomography"]),
    # Bare "connectome" is mostly fMRI/DTI prose - keep this tag to genuine EM.
    "em_connectomics":  ("Electron microscopy / EM connectomics",
                         [r"electron microscop(?:y|ic)", r"serial[- ]section",
                          r"volume (?:em|electron)", r"fib-?sem", r"ssem", r"expansion microscopy",
                          r"em connectom\w+", r"connectomic reconstructions?",
                          r"dense reconstructions?", r"synaptic[- ]resolution"],
                         ["Microscopy, Electron"]),
    "scrnaseq":         ("Single-cell / spatial transcriptomics",
                         [r"single[- ]cell rna", r"sc-?rna-?seq", r"sn-?rna-?seq",
                          r"single[- ]nucleus rna", r"single[- ]cell transcriptom\w+",
                          r"spatial transcriptom\w+", r"patch-?seq", r"merfish"],
                         ["Single-Cell Gene Expression Analysis", "Single-Cell Analysis"]),
    "crispr":           ("CRISPR / gene editing",
                         [r"crispr", r"cas9", r"gene editing", r"genome editing"],
                         ["CRISPR-Cas Systems", "Gene Editing"]),
    "ipsc_organoid":    ("iPSC / organoids",
                         [r"ipscs?", r"induced pluripotent", r"organoids?", r"assembloids?"],
                         ["Induced Pluripotent Stem Cells", "Organoids"]),
    "viral_tracing":    ("Viral vectors (AAV) / tracing",
                         [r"rabies", r"monosynaptic tracing",
                          r"(?:anterograde|retrograde|viral) tracing", r"aav",
                          r"adeno-associated"],
                         ["Neuroanatomical Tract-Tracing Techniques"]),
    "comp_modelling":   ("Computational modelling",
                         [r"computational model(?:s|ling|ing)?", r"biophysical model\w*",
                          r"spiking (?:neural )?networks?", r"bayesian (?:model\w*|inference)",
                          r"dynamical systems?", r"mean[- ]field", r"normative model\w*"],
                         ["Models, Neurological", "Computer Simulation"]),
    "deep_learning":    ("Machine / deep learning",
                         [r"deep learning", r"deep neural networks?",
                          r"convolutional neural networks?", r"cnns?",
                          r"recurrent neural networks?", r"rnns?", r"machine learning",
                          r"artificial intelligence", r"large language models?", r"llms?"],
                         ["Deep Learning", "Machine Learning", "Neural Networks, Computer"]),
    "psychophysics":    ("Psychophysics",
                         [r"psychophysic(?:s|al|ally)", r"two[- ]alternative forced[- ]choice",
                          r"2afc", r"detection thresholds?", r"discrimination tasks?",
                          r"staircase procedure"],
                         ["Psychophysics"]),
    "eye_tracking":     ("Eye tracking / pupillometry",
                         [r"eye[- ]track(?:ing|er)", r"saccad(?:e|es|ic)", r"gaze",
                          r"pupillometry", r"pupil (?:size|diameter|dilation)"],
                         ["Eye-Tracking Technology", "Saccades", "Pupil"]),
    "pose_tracking":    ("Pose tracking (DeepLabCut etc.)",
                         [r"deeplabcut", r"pose estimation", r"markerless", r"sleap",
                          r"video tracking"],
                         []),
    "bci":              ("Brain-computer interface",
                         [r"brain[- ](?:computer|machine) interfaces?", r"bcis?",
                          r"neuroprosthe\w+"],
                         ["Brain-Computer Interfaces"]),
    "immunostaining":   ("Immunostaining / light-sheet",
                         [r"immunohistochem\w+", r"immunofluorescen\w+",
                          r"in situ hybridi[sz]ation", r"light[- ]sheet", r"tissue clearing"],
                         ["Immunohistochemistry", "In Situ Hybridization"]),
    "omics":            ("Proteomics / metabolomics",
                         [r"proteomics?", r"mass spectrometry", r"metabolomics?", r"lipidomics?"],
                         ["Proteomics", "Mass Spectrometry", "Metabolomics"]),
    "microdialysis":    ("Microdialysis / voltammetry",
                         [r"microdialysis", r"fast[- ]scan cyclic voltammetry", r"fscv"],
                         ["Microdialysis"]),
    "gwas":             ("GWAS / sequencing genetics",
                         [r"genome[- ]wide association", r"gwas", r"polygenic",
                          r"whole[- ]exome", r"whole[- ]genome sequencing", r"exome sequencing"],
                         ["Genome-Wide Association Study", "Exome Sequencing",
                          "Whole Genome Sequencing"]),
}

GROUPS = {"organisms": ORGANISMS, "methods": METHODS}

_DASHES = re.compile("[‐‑‒–—−]")
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, unify dashes and collapse whitespace so patterns stay simple."""
    return _WS.sub(" ", _DASHES.sub("-", (text or "").lower())).strip()


def compile_vocab() -> list[tuple[str, str, str, re.Pattern | None, frozenset[str]]]:
    """[(group, id, label, compiled_regex_or_None, mesh_names)] in declaration order."""
    out = []
    for group, table in GROUPS.items():
        for tid, (label, pats, mesh) in table.items():
            rx = None
            if pats:
                rx = re.compile(r"(?<![a-z0-9])(?:" + "|".join(pats) + r")(?![a-z0-9])")
            out.append((group, tid, label, rx, frozenset(mesh)))
    return out


def labels() -> dict[str, dict[str, str]]:
    """{group: {id: label}} for the UI."""
    return {g: {tid: v[0] for tid, v in t.items()} for g, t in GROUPS.items()}


if __name__ == "__main__":
    from collections import Counter
    v = compile_vocab()
    dup = [m for m, n in Counter(m for *_, ms in v for m in ms).items() if n > 1]
    print(f"{len(v)} tags ({len(ORGANISMS)} organisms, {len(METHODS)} methods); "
          f"duplicate MeSH names: {dup or 'none'}")
    sample = normalise("Two-Photon Ca2+ imaging in C. elegans and Drosophila — a GCaMP6f study")
    print([tid for _, tid, _, rx, _ in v if rx and rx.search(sample)])
