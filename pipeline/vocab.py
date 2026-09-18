"""Controlled vocabulary for tagging works with research methods and model systems.

Each tag is matched two ways, either of which counts as a hit:

* ``re``   - regex alternatives applied to the lowercased, normalised
             title + abstract. Joined into ONE pattern per tag, fenced with
             ``(?<![a-z0-9])`` / ``(?![a-z0-9])`` rather than ``\\b`` because
             several alternatives end in punctuation (``ca2+``, ``c. elegans``).
* ``mesh`` - exact MeSH descriptor names (PubMed-indexed works only, so this
             is additive: preprints never carry MeSH). A descriptor belongs to
             at most one tag.

Every tag has a category, which the UI uses to group chips.

Tune by running ``python3 pipeline/enrich_text.py audit --tag ID`` after a
``tag`` run, editing here, bumping ``VOCAB_VERSION`` and re-running ``tag``
(minutes, no API calls - the raw text is cached). Tag ids are stable: they are
stored in shared URLs, so rename labels freely but never ids.

Audit history (why some patterns look fussy):
* bare "cat"/"bat" were mostly abbreviations (Comprehensive Aphasia Test,
  brown adipose tissue); bare "pet" matched pet ownership;
* bare "connectome" was mostly fMRI/DTI prose, so the EM tag needs EM terms;
* "clarity" is common English, so the tissue-clearing tag needs context;
* antibody reagents ("rabbit anti-GFAP", "mouse monoclonal") tagged human tissue
  studies as rabbit/mouse work, hence ``_NOT_REAGENT`` on species names;
* bare "canine" matched MDCK (Madin-Darby canine kidney) cell-biology papers;
* bare "cerebrospinal fluid" matched hydrocephalus / CSF physiology, not biomarkers;
* the Prospective/Retrospective Studies MeSH headings sit on most clinical papers.
"""
from __future__ import annotations

import re

# Species names used as antibody hosts are reagents, not model systems.
_NOT_REAGENT = r"(?! (?:anti\b|anti-|monoclonal|polyclonal|igg|igm|antibod|antiserum|serum albumin))"

VOCAB_VERSION = "2026-09-17.3"

# Category order drives the UI grouping.
ORGANISM_CATEGORIES = ["Humans", "Rodents", "Primates", "Other mammals", "Birds",
                       "Fish, amphibians & reptiles", "Invertebrates"]
METHOD_CATEGORIES = ["Electrophysiology", "Optical imaging & sensors", "Human neuroimaging",
                     "Stimulation & neurotechnology", "Molecular & genetic",
                     "Anatomy & microscopy", "Behaviour & cognition", "Computational & data",
                     "Clinical & population"]

# id -> (label, category, [regex alternatives], [MeSH descriptor names])
ORGANISMS: dict[str, tuple[str, str, list[str], list[str]]] = {
    # --- Humans ------------------------------------------------------------
    "human":            ("Human (any)", "Humans",
                         [r"humans?", r"patients?", r"participants?",
                          r"healthy (?:adults?|volunteers?|controls?|subjects?)"],
                         ["Humans"]),
    "human_patients":   ("Human patients / clinical", "Humans",
                         [r"patients?", r"outpatients?", r"inpatients?",
                          r"clinical (?:cohorts?|samples?|populations?)"],
                         []),
    "human_tissue":     ("Human tissue (post-mortem / resected)", "Humans",
                         [r"post-?mortem", r"autops(?:y|ies)", r"brain banks?",
                          r"(?:human|donor) brain (?:tissue|samples?|specimens?)", r"surgically resected",
                          r"resected (?:human )?(?:cortical |brain |neocortical )?tissue"],
                         ["Autopsy", "Tissue Banks"]),
    # --- Rodents -----------------------------------------------------------
    "mouse":            ("Mouse", "Rodents", [r"mice", r"mouse" + _NOT_REAGENT, r"murine", r"mus musculus"],
                         ["Mice", "Mice, Inbred C57BL", "Mice, Transgenic", "Mice, Knockout",
                          "Mice, Inbred BALB C", "Mice, Inbred Strains"]),
    "rat":              ("Rat", "Rodents", [r"rats?" + _NOT_REAGENT, r"rattus"],
                         ["Rats", "Rats, Sprague-Dawley", "Rats, Wistar", "Rats, Long-Evans"]),
    "guinea_pig":       ("Guinea pig", "Rodents", [r"guinea[- ]pigs?" + _NOT_REAGENT, r"cavia porcellus"],
                         ["Guinea Pigs"]),
    "gerbil":           ("Gerbil", "Rodents", [r"gerbils?", r"meriones"], ["Gerbillinae"]),
    "hamster":          ("Hamster", "Rodents", [r"hamsters?", r"mesocricetus"],
                         ["Cricetinae", "Mesocricetus"]),
    "vole":             ("Vole", "Rodents", [r"voles?", r"microtus"], ["Arvicolinae"]),
    "naked_mole_rat":   ("Naked mole-rat", "Rodents",
                         [r"naked mole-?rats?", r"heterocephalus"], ["Mole Rats"]),
    # --- Primates ----------------------------------------------------------
    "macaque":          ("Macaque / NHP", "Primates",
                         [r"macaques?", r"macaca", r"rhesus", r"monkeys?", r"non-?human primates?"],
                         ["Macaca mulatta", "Macaca fascicularis", "Macaca", "Primates"]),
    "marmoset":         ("Marmoset", "Primates", [r"marmosets?", r"callithrix"], ["Callithrix"]),
    # --- Other mammals -----------------------------------------------------
    "ferret":           ("Ferret", "Other mammals", [r"ferrets?"], ["Ferrets"]),
    "cat":              ("Cat", "Other mammals",
                         [r"felis catus", r"domestic cats?", r"feline",
                          r"(?:adult|anesthetized|anaesthetized|awake) cats"],
                         ["Cats"]),
    "pig":              ("Pig / minipig", "Other mammals",
                         [r"(?<!guinea )(?<!guinea-)pigs?", r"minipigs?", r"porcine", r"sus scrofa"],
                         ["Swine", "Swine, Miniature"]),
    "bat":              ("Bat", "Other mammals",
                         [r"(?:fruit|vampire|egyptian|big brown|little brown) bats?",
                          r"bat (?:echolocation|navigation|flight|species|hippocamp\w+)",
                          r"chiroptera", r"echolocat\w+", r"rousettus", r"eptesicus", r"myotis"],
                         ["Chiroptera"]),
    "rabbit":           ("Rabbit", "Other mammals", [r"rabbits?" + _NOT_REAGENT, r"oryctolagus"], ["Rabbits"]),
    "dog":              ("Dog", "Other mammals", [r"dogs?", r"canine (?:model|cognition|brain|patients?|epilepsy|olfaction)", r"canis familiaris"],
                         ["Dogs"]),
    "sheep":            ("Sheep", "Other mammals", [r"sheep" + _NOT_REAGENT, r"ovine"], ["Sheep"]),
    "tree_shrew":       ("Tree shrew", "Other mammals", [r"tree shrews?", r"tupaia"],
                         ["Tupaiidae"]),
    # --- Birds -------------------------------------------------------------
    "songbird":         ("Songbird", "Birds",
                         [r"songbirds?", r"zebra finch(?:es)?", r"taeniopygia",
                          r"bengalese finch(?:es)?"],
                         ["Finches", "Songbirds"]),
    "chick":            ("Chick / chicken", "Birds",
                         [r"chicks?", r"chickens?" + _NOT_REAGENT, r"chick embryos?", r"gallus"],
                         ["Chickens", "Chick Embryo"]),
    "owl":              ("Owl", "Birds", [r"owls?", r"tyto alba"], ["Strigiformes"]),
    "pigeon_corvid":    ("Pigeon / corvid", "Birds",
                         [r"pigeons?", r"columba livia", r"crows?", r"ravens?", r"corvids?"],
                         ["Columbidae", "Crows"]),
    # --- Fish, amphibians & reptiles ---------------------------------------
    "zebrafish":        ("Zebrafish", "Fish, amphibians & reptiles",
                         [r"zebrafish", r"danio rerio"], ["Zebrafish"]),
    "other_fish":       ("Other fish (goldfish, medaka, electric fish)", "Fish, amphibians & reptiles",
                         [r"goldfish", r"medaka", r"killifish", r"cichlids?", r"electric fish",
                          r"mormyrid\w*", r"gymnotiform\w*", r"apteronotus", r"eigenmannia",
                          r"teleosts?"],
                         ["Goldfish", "Oryzias", "Cichlids", "Electric Fish"]),
    "xenopus":          ("Xenopus / frog", "Fish, amphibians & reptiles",
                         [r"xenopus", r"tadpoles?", r"frogs?", r"bullfrogs?"],
                         ["Xenopus", "Xenopus laevis", "Anura", "Ranidae"]),
    "axolotl":          ("Axolotl / salamander", "Fish, amphibians & reptiles",
                         [r"axolotls?", r"salamanders?", r"newts?", r"ambystoma"],
                         ["Ambystoma", "Urodela"]),
    "lamprey":          ("Lamprey", "Fish, amphibians & reptiles", [r"lampreys?", r"petromyzon"],
                         ["Lampreys"]),
    "reptile":          ("Reptile (turtle, lizard)", "Fish, amphibians & reptiles",
                         [r"turtles?", r"lizards?", r"geckos?", r"reptiles?", r"pogona"],
                         ["Turtles", "Lizards", "Reptiles"]),
    # --- Invertebrates -----------------------------------------------------
    "drosophila":       ("Drosophila", "Invertebrates",
                         [r"drosophila", r"fruit ?fl(?:y|ies)", r"melanogaster"],
                         ["Drosophila", "Drosophila melanogaster"]),
    "c_elegans":        ("C. elegans", "Invertebrates", [r"c\. ?elegans", r"caenorhabditis"],
                         ["Caenorhabditis elegans"]),
    "honeybee":         ("Honeybee / bumblebee", "Invertebrates",
                         [r"honey ?bees?", r"apis mellifera", r"bumble ?bees?"], ["Bees"]),
    "other_insects":    ("Other insects (locust, moth, ant, mosquito)", "Invertebrates",
                         [r"locusts?", r"crickets?", r"cockroach(?:es)?", r"moths?", r"manduca",
                          r"mosquito(?:es)?", r"aedes", r"anopheles", r"butterfl(?:y|ies)",
                          r"ants", r"camponotus", r"harpegnathos", r"stick insects?"],
                         ["Grasshoppers", "Gryllidae", "Cockroaches", "Moths", "Manduca",
                          "Culicidae", "Ants", "Butterflies"]),
    "aplysia":          ("Aplysia", "Invertebrates", [r"aplysia"], ["Aplysia"]),
    "cephalopod":       ("Cephalopod", "Invertebrates",
                         [r"octopus", r"cuttlefish", r"squid", r"cephalopods?"],
                         ["Cephalopoda", "Octopodiformes", "Decapodiformes"]),
    "crustacean":       ("Crustacean (crab, lobster)", "Invertebrates",
                         [r"crabs?", r"lobsters?", r"crayfish", r"stomatogastric",
                          r"cancer borealis"],
                         ["Brachyura", "Nephropidae", "Astacoidea"]),
    "leech":            ("Leech", "Invertebrates", [r"leech(?:es)?", r"hirudo"], ["Leeches"]),
    "planarian":        ("Planarian", "Invertebrates", [r"planarians?", r"schmidtea"],
                         ["Planarians"]),
    "cnidarian":        ("Hydra / cnidarian", "Invertebrates",
                         [r"hydra", r"nematostella", r"jellyfish", r"cnidarians?"],
                         ["Hydra", "Sea Anemones", "Cnidaria"]),
}

METHODS: dict[str, tuple[str, str, list[str], list[str]]] = {
    # --- Electrophysiology -------------------------------------------------
    "patch_clamp":      ("Patch clamp", "Electrophysiology",
                         [r"patch[- ]clamp", r"whole[- ]cell (?:recording|patch)s?",
                          r"voltage[- ]clamp", r"current[- ]clamp"],
                         ["Patch-Clamp Techniques"]),
    "slice_ephys":      ("Brain slice preparations", "Electrophysiology",
                         [r"acute (?:brain |hippocampal |cortical |cerebellar |spinal cord )?slices?",
                          r"brain slices?", r"(?:hippocampal|cortical|cerebellar|striatal|brainstem) slices?",
                          r"organotypic (?:slice )?cultures?", r"ex vivo slices?"],
                         []),
    "extracellular":    ("Extracellular ephys", "Electrophysiology",
                         [r"extracellular recordings?", r"single[- ]units?", r"multi[- ]unit",
                          r"tetrodes?", r"spike sorting", r"local field potentials?", r"lfps?"],
                         []),
    "neuropixels":      ("Neuropixels", "Electrophysiology", [r"neuropixels?"], []),
    "mea":              ("Multi-electrode arrays (MEA)", "Electrophysiology",
                         [r"multi-?electrode arrays?", r"microelectrode arrays?", r"utah arrays?"],
                         []),
    "ecog":             ("Intracranial EEG / ECoG / human single units", "Electrophysiology",
                         [r"ecog", r"electrocorticogra\w+", r"intracranial (?:eeg|recordings?)",
                          r"stereo-?eeg", r"seeg", r"depth electrodes?", r"microwires?",
                          r"single[- ]neurons? (?:recordings? )?in (?:humans?|patients)",
                          r"human single[- ]neurons?"],
                         ["Electrocorticography"]),
    "emg":              ("EMG / MEPs / nerve conduction", "Electrophysiology",
                         [r"electromyogra\w+", r"emg", r"motor evoked potentials?", r"meps?",
                          r"microneurography", r"nerve conduction"],
                         ["Electromyography", "Evoked Potentials, Motor", "Neural Conduction"]),
    # --- Optical imaging & sensors -----------------------------------------
    "two_photon":       ("Two-photon imaging", "Optical imaging & sensors",
                         [r"two[- ]photon", r"2[- ]photon", r"multi-?photon"],
                         ["Microscopy, Fluorescence, Multiphoton"]),
    "calcium_imaging":  ("Calcium imaging", "Optical imaging & sensors",
                         [r"calcium imaging", r"gcamp\d*[a-z]?", r"ca2\+ imaging",
                          r"calcium indicators?", r"miniscopes?"],
                         []),
    "voltage_imaging":  ("Voltage imaging", "Optical imaging & sensors",
                         [r"voltage imaging", r"genetically encoded voltage indicators?", r"gevis?",
                          r"voltage-sensitive dyes?", r"voltage[- ]sensitive dye imaging"],
                         []),
    "widefield":        ("Widefield / mesoscale imaging", "Optical imaging & sensors",
                         [r"wide-?field (?:calcium |optical |fluorescence )?imaging",
                          r"meso(?:scale|scopic) (?:calcium )?imaging",
                          r"intrinsic signal (?:optical )?imaging",
                          r"optical imaging of intrinsic signals?"],
                         []),
    "fiber_photometry": ("Fiber photometry", "Optical imaging & sensors",
                         [r"fibe?r[- ]photometry"], []),
    "nt_sensors":       ("Neurotransmitter sensors (GRAB, dLight)", "Optical imaging & sensors",
                         [r"grab[- ]?(?:da|ne|ach|5-?ht|ecb|ado|oxt|gaba)\w*", r"dlight\d*",
                          r"iglusnfr\w*", r"igaba-?snfr\w*",
                          r"genetically encoded (?:neurotransmitter|neuromodulator|dopamine|"
                          r"serotonin|acetylcholine|norepinephrine) (?:sensors?|indicators?)"],
                         []),
    # --- Human neuroimaging ------------------------------------------------
    "fmri":             ("fMRI", "Human neuroimaging",
                         [r"fmri", r"functional (?:magnetic resonance|mri)",
                          r"bold (?:signal|response|fmri|contrast)", r"resting[- ]state"],
                         []),
    "mri":              ("Structural / diffusion MRI", "Human neuroimaging",
                         [r"mri", r"magnetic resonance imaging", r"diffusion tensor", r"dti",
                          r"tractography", r"voxel[- ]based morphometry"],
                         ["Magnetic Resonance Imaging", "Diffusion Tensor Imaging",
                          "Diffusion Magnetic Resonance Imaging"]),
    "mrs":              ("MR spectroscopy", "Human neuroimaging",
                         [r"magnetic resonance spectroscop\w*", r"(?:1h-?)?mrs", r"mrsi"],
                         ["Magnetic Resonance Spectroscopy", "Proton Magnetic Resonance Spectroscopy"]),
    "eeg":              ("EEG / ERP", "Human neuroimaging",
                         [r"eeg", r"electroencephalogra(?:phy|m|phic)",
                          r"event[- ]related potentials?", r"erps?"],
                         ["Electroencephalography", "Evoked Potentials"]),
    "meg":              ("MEG", "Human neuroimaging", [r"meg", r"magnetoencephalogra(?:phy|m|phic)"],
                         ["Magnetoencephalography"]),
    "fnirs":            ("fNIRS", "Human neuroimaging",
                         [r"fnirs", r"functional near-?infrared spectroscopy",
                          r"near-?infrared spectroscopy", r"nirs"],
                         ["Spectroscopy, Near-Infrared"]),
    "pet":              ("PET", "Human neuroimaging",
                         [r"positron emission",
                          r"pet (?:imaging|scans?|tracers?|ligands?|stud(?:y|ies)|data|measures?)",
                          r"(?:amyloid|tau|fdg|tspo|synaptic|dopamine|brain) pet",
                          r"pet[-/ ]?(?:mri?|ct)"],
                         ["Positron-Emission Tomography",
                          "Positron Emission Tomography Computed Tomography"]),
    "lesion_mapping":   ("Lesion-symptom mapping", "Human neuroimaging",
                         [r"lesion-?symptom mapping", r"voxel-?based lesion", r"lesion network mapping",
                          r"lesion-?deficit (?:mapping|analysis)"],
                         []),
    # --- Stimulation & neurotechnology ---------------------------------------
    "optogenetics":     ("Optogenetics", "Stimulation & neurotechnology",
                         [r"optogenetic(?:s|ally)?", r"channelrhodopsin", r"chr2",
                          r"halorhodopsin", r"archt?"],
                         ["Optogenetics"]),
    "chemogenetics":    ("Chemogenetics (DREADDs)", "Stimulation & neurotechnology",
                         [r"chemogenetic(?:s|ally)?", r"dreadds?", r"clozapine[- ]n[- ]oxide", r"cno"],
                         []),
    "tms_tdcs":         ("TMS / tDCS", "Stimulation & neurotechnology",
                         [r"tms", r"transcranial magnetic", r"tdcs", r"tacs",
                          r"transcranial (?:direct|alternating|electrical) current"],
                         ["Transcranial Magnetic Stimulation",
                          "Transcranial Direct Current Stimulation"]),
    "dbs":              ("Deep brain stimulation", "Stimulation & neurotechnology",
                         [r"deep brain stimulation", r"dbs"], ["Deep Brain Stimulation"]),
    "ultrasound":       ("Focused / functional ultrasound", "Stimulation & neurotechnology",
                         [r"focused ultrasound", r"transcranial ultrasound", r"ultrasound neuromodulation",
                          r"functional ultrasound(?: imaging)?", r"fusi", r"tfus", r"lifu",
                          r"low-intensity (?:focused )?ultrasound"],
                         []),
    "nerve_stim":       ("Vagus / spinal / peripheral nerve stimulation", "Stimulation & neurotechnology",
                         [r"vagus nerve stimulation", r"vns", r"tavns", r"spinal cord stimulation",
                          r"peripheral nerve stimulation", r"sacral (?:nerve )?(?:neuro)?modulation"],
                         ["Vagus Nerve Stimulation", "Spinal Cord Stimulation",
                          "Transcutaneous Electric Nerve Stimulation"]),
    "microstim":        ("Intracortical microstimulation", "Stimulation & neurotechnology",
                         [r"microstimulation", r"icms", r"intracortical (?:electrical )?stimulation"],
                         []),
    "inactivation":     ("Lesions / pharmacological inactivation", "Stimulation & neurotechnology",
                         [r"muscimol", r"excitotoxic lesions?", r"ibotenic acid",
                          r"pharmacological (?:inactivation|silencing)", r"reversible inactivation",
                          r"cooling inactivation", r"lesion stud(?:y|ies)"],
                         []),
    "bci":              ("Brain-computer interface", "Stimulation & neurotechnology",
                         [r"brain[- ](?:computer|machine) interfaces?", r"bcis?", r"neuroprosthe\w+"],
                         ["Brain-Computer Interfaces"]),
    # --- Molecular & genetic -----------------------------------------------
    "genetic_models":   ("Genetic models (Cre, knockouts, GAL4)", "Molecular & genetic",
                         [r"cre[- ](?:driver|lines?|recombinase|dependent|mice|mouse)", r"floxed",
                          r"conditional (?:knockout|deletion)", r"knock-?in (?:mice|mouse|lines?)",
                          r"knockout (?:mice|mouse|rats?|lines?)",
                          r"transgenic (?:mice|mouse|lines?|rats?|zebrafish|flies)",
                          r"gal4", r"split-gal4"],
                         []),
    "in_utero":         ("In utero electroporation", "Molecular & genetic",
                         [r"in utero electroporation", r"iue"], []),
    "viral_tracing":    ("Viral vectors (AAV) / tracing", "Molecular & genetic",
                         [r"rabies", r"monosynaptic tracing",
                          r"(?:anterograde|retrograde|viral) tracing", r"aav",
                          r"adeno-associated"],
                         ["Neuroanatomical Tract-Tracing Techniques"]),
    "crispr":           ("CRISPR / gene editing", "Molecular & genetic",
                         [r"crispr", r"cas9", r"gene editing", r"genome editing"],
                         ["CRISPR-Cas Systems", "Gene Editing"]),
    "knockdown":        ("Knockdown / gene therapy (ASO, RNAi)", "Molecular & genetic",
                         [r"antisense oligonucleotides?", r"asos?", r"sirna", r"shrna",
                          r"rna interference", r"rnai", r"gene therapy", r"gene replacement"],
                         ["Oligonucleotides, Antisense", "RNA Interference", "Genetic Therapy",
                          "RNA, Small Interfering"]),
    "scrnaseq":         ("Single-cell / spatial transcriptomics", "Molecular & genetic",
                         [r"single[- ]cell rna", r"sc-?rna-?seq", r"sn-?rna-?seq",
                          r"single[- ]nucleus rna", r"single[- ]cell transcriptom\w+",
                          r"spatial transcriptom\w+", r"patch-?seq", r"merfish"],
                         ["Single-Cell Gene Expression Analysis", "Single-Cell Analysis"]),
    "bulk_omics":       ("Transcriptomics / epigenomics", "Molecular & genetic",
                         [r"rna-?seq(?:uencing)?", r"transcriptom(?:e|es|ic|ics)", r"atac-?seq",
                          r"chip-?seq", r"dna methylation", r"epigenom\w*",
                          r"histone (?:modifications?|acetylation|methylation)",
                          r"chromatin accessibility"],
                         ["RNA-Seq", "Transcriptome", "DNA Methylation", "Epigenomics",
                          "Chromatin Immunoprecipitation Sequencing", "Gene Expression Profiling"]),
    "omics":            ("Proteomics / metabolomics", "Molecular & genetic",
                         [r"proteomics?", r"mass spectrometry", r"metabolomics?", r"lipidomics?"],
                         ["Proteomics", "Mass Spectrometry", "Metabolomics"]),
    "ipsc_organoid":    ("iPSC / organoids", "Molecular & genetic",
                         [r"ipscs?", r"induced pluripotent", r"organoids?", r"assembloids?"],
                         ["Induced Pluripotent Stem Cells", "Organoids"]),
    "cell_culture":     ("Primary neural cultures", "Molecular & genetic",
                         [r"primary (?:neuronal|hippocampal|cortical|glial|astrocyte|microglial?) cultures?",
                          r"cultured (?:neurons|astrocytes|microglia)", r"neuronal cultures?",
                          r"(?:neurons|astrocytes|microglia) in culture"],
                         ["Primary Cell Culture"]),
    "microdialysis":    ("Microdialysis / voltammetry", "Molecular & genetic",
                         [r"microdialysis", r"fast[- ]scan cyclic voltammetry", r"fscv"],
                         ["Microdialysis"]),
    "gwas":             ("GWAS / sequencing genetics", "Molecular & genetic",
                         [r"genome[- ]wide association", r"gwas", r"polygenic",
                          r"whole[- ]exome", r"whole[- ]genome sequencing", r"exome sequencing"],
                         ["Genome-Wide Association Study", "Exome Sequencing",
                          "Whole Genome Sequencing"]),
    "mendelian_rand":   ("Mendelian randomization", "Molecular & genetic",
                         [r"mendelian randomi[sz]ation"], ["Mendelian Randomization Analysis"]),
    # --- Anatomy & microscopy ----------------------------------------------
    "immunostaining":   ("Immunostaining / in situ hybridization", "Anatomy & microscopy",
                         [r"immunohistochem\w+", r"immunofluorescen\w+", r"in situ hybridi[sz]ation",
                          r"rnascope", r"smfish"],
                         ["Immunohistochemistry", "In Situ Hybridization"]),
    "tissue_clearing":  ("Tissue clearing / light-sheet", "Anatomy & microscopy",
                         [r"light[- ]sheet", r"tissue clearing", r"idisco\+?", r"ubisco",
                          r"clarity[- ](?:based|cleared|clearing|method|protocol|technique)",
                          r"passive clarity", r"whole-brain (?:clearing|imaging)"],
                         []),
    "em_connectomics":  ("Electron microscopy / EM connectomics", "Anatomy & microscopy",
                         [r"(?<!cryo-)(?<!cryo )electron microscop(?:y|ic)", r"serial[- ]section",
                          r"volume (?:em|electron)", r"fib-?sem", r"ssem",
                          r"em connectom\w+", r"connectomic reconstructions?",
                          r"dense reconstructions?", r"synaptic[- ]resolution"],
                         ["Microscopy, Electron"]),
    "super_res":        ("Super-resolution / expansion microscopy", "Anatomy & microscopy",
                         [r"super-?resolution", r"sted (?:microscopy|nanoscopy)",
                          r"d?storm (?:imaging|microscopy)", r"palm (?:imaging|microscopy)",
                          r"single-?molecule (?:localization|imaging|tracking)",
                          r"expansion microscopy", r"minflux", r"nanoscopy"],
                         []),
    "structural_bio":   ("Structural biology (cryo-EM, crystallography, MD)", "Anatomy & microscopy",
                         [r"cryo-?em", r"cryo-?electron (?:microscopy|tomography)",
                          r"crystal structures?", r"x-ray crystallograph\w*",
                          r"molecular dynamics simulations?", r"alphafold\d*"],
                         ["Cryoelectron Microscopy", "Crystallography, X-Ray",
                          "Molecular Dynamics Simulation"]),
    "morphology":       ("Neuronal morphology / reconstruction", "Anatomy & microscopy",
                         [r"neuronal morphology", r"dendritic (?:morphology|arbori[sz]ation|arbors?|spines?)",
                          r"spine density", r"golgi(?:-cox)? stain\w*", r"sholl analysis",
                          r"(?:single-)?neuron reconstructions?", r"biocytin",
                          r"morphological reconstructions?"],
                         ["Dendritic Spines"]),
    # --- Behaviour & cognition ---------------------------------------------
    "psychophysics":    ("Psychophysics", "Behaviour & cognition",
                         [r"psychophysic(?:s|al|ally)", r"two[- ]alternative forced[- ]choice",
                          r"2afc", r"detection thresholds?", r"discrimination tasks?",
                          r"staircase procedure"],
                         ["Psychophysics"]),
    "eye_tracking":     ("Eye tracking / pupillometry", "Behaviour & cognition",
                         [r"eye[- ]track(?:ing|er)", r"saccad(?:e|es|ic)", r"gaze",
                          r"pupillometry", r"pupil (?:size|diameter|dilation)"],
                         ["Eye-Tracking Technology", "Saccades", "Pupil"]),
    "pose_tracking":    ("Pose tracking (DeepLabCut etc.)", "Behaviour & cognition",
                         [r"deeplabcut", r"pose estimation", r"markerless", r"sleap",
                          r"video tracking"],
                         []),
    "rodent_behaviour": ("Rodent behavioural assays", "Behaviour & cognition",
                         [r"water maze", r"fear conditioning", r"open[- ]field (?:test|arena)",
                          r"elevated plus[- ]maze", r"novel object recognition", r"barnes maze",
                          r"[ty]-maze", r"radial arm maze", r"forced swim(?:ming)? test",
                          r"tail suspension", r"sucrose preference", r"rotarod",
                          r"prepulse inhibition", r"three-chamber", r"marble burying",
                          r"operant (?:conditioning|tasks?|chambers?|responding)",
                          r"self-administration", r"conditioned place preference"],
                         ["Maze Learning", "Conditioning, Operant", "Rotarod Performance Test",
                          "Open Field Test", "Elevated Plus Maze Test", "Self Administration"]),
    "vr_headfixed":     ("Virtual reality / head-fixed behaviour", "Behaviour & cognition",
                         [r"virtual reality", r"vr", r"head-?fixed",
                          r"virtual (?:corridors?|environments?|navigation|tracks?)"],
                         ["Virtual Reality"]),
    "sleep_recording":  ("Sleep recording (PSG, actigraphy)", "Behaviour & cognition",
                         [r"polysomnogra\w+", r"sleep recordings?", r"actigraph\w*", r"sleep eeg",
                          r"sleep spindles?", r"slow-wave activity"],
                         ["Polysomnography", "Actigraphy"]),
    "neuropsych_tests": ("Neuropsychological testing", "Behaviour & cognition",
                         [r"neuropsychological (?:tests?|testing|assessments?|battery|evaluations?)",
                          r"montreal cognitive assessment", r"moca", r"mini-mental", r"mmse",
                          r"cantab"],
                         ["Neuropsychological Tests", "Mental Status and Dementia Tests"]),
    # --- Computational & data ----------------------------------------------
    "comp_modelling":   ("Computational modelling", "Computational & data",
                         [r"computational model(?:s|ling|ing)?", r"biophysical model\w*",
                          r"spiking (?:neural )?networks?", r"bayesian (?:model\w*|inference)",
                          r"dynamical systems?", r"mean[- ]field", r"normative model\w*"],
                         ["Models, Neurological", "Computer Simulation"]),
    "cognitive_models": ("Cognitive / RL models (RL, DDM, active inference)", "Computational & data",
                         [r"reinforcement learning", r"drift[- ]diffusion", r"computational psychiatry",
                          r"active inference", r"predictive coding", r"free[- ]energy principle",
                          r"hierarchical gaussian filter", r"bayesian observer"],
                         []),
    "deep_learning":    ("Machine / deep learning", "Computational & data",
                         [r"deep learning", r"deep neural networks?",
                          r"convolutional neural networks?", r"cnns?",
                          r"recurrent neural networks?", r"rnns?", r"machine learning",
                          r"artificial intelligence", r"large language models?", r"llms?"],
                         ["Deep Learning", "Machine Learning", "Neural Networks, Computer"]),
    "network_analysis": ("Network / graph-theory analysis", "Computational & data",
                         [r"graph theor(?:y|etical)", r"network neuroscience", r"small-?world",
                          r"rich-?club", r"network (?:topology|hubs?|efficiency|controllability)"],
                         []),
    "neuromorphic":     ("Neuromorphic / neurorobotics", "Computational & data",
                         [r"neuromorphic", r"memristor\w*", r"neurorobotic\w*",
                          r"brain-inspired (?:computing|hardware|chips?)"],
                         []),
    "software_data":    ("Software, tools & open data", "Computational & data",
                         [r"open[- ]source (?:software|toolbox|toolkit|pipeline|package|platform|tools?)",
                          r"(?:python|matlab|analysis) (?:package|library|toolbox)",
                          r"software (?:package|tool|toolkit|platform)", r"open datasets?",
                          r"neurodata without borders", r"brain imaging data structure"],
                         ["Software"]),
    # --- Clinical & population ---------------------------------------------
    "clinical_trial":   ("Clinical trials", "Clinical & population",
                         [r"randomi[sz]ed(?: (?:controlled|clinical|placebo-controlled|double-blind))? trials?",
                          r"rcts?", r"placebo[- ]controlled", r"double[- ]blind", r"open-label",
                          r"phase (?:i|ii|iii|1|2|3|1b|2a|2b) (?:clinical )?trials?"],
                         ["Randomized Controlled Trials as Topic", "Double-Blind Method",
                          "Placebos", "Clinical Trials as Topic"]),
    "cohort_epi":       ("Cohorts / epidemiology / biobanks", "Clinical & population",
                         [r"cohort stud(?:y|ies)", r"prospective cohort", r"longitudinal cohort",
                          r"birth cohort", r"population-based (?:cohort|stud(?:y|ies)|samples?|registr\w*)",
                          r"uk biobank", r"biobanks?", r"registry-based", r"(?:national|patient) registr(?:y|ies)",
                          r"epidemiolog\w*", r"nationwide (?:cohort|stud(?:y|ies)|registr\w*|population)"],
                         ["Cohort Studies", "Epidemiologic Studies", "Registries", "Biological Specimen Banks"]),
    "meta_analysis":    ("Meta-analysis / systematic review", "Clinical & population",
                         [r"meta-?analys[ie]s", r"meta-?analytic", r"systematic reviews?",
                          r"umbrella reviews?", r"scoping reviews?"],
                         []),
    "questionnaires":   ("Questionnaires / psychometrics", "Clinical & population",
                         [r"questionnaires?", r"self-?report(?:s|ed)?", r"psychometric\w*",
                          r"surveys?", r"rating scales?"],
                         ["Surveys and Questionnaires", "Psychometrics", "Self Report"]),
    "fluid_biomarkers": ("Fluid biomarkers (CSF / blood)", "Clinical & population",
                         [r"(?:csf|cerebrospinal fluid) (?:biomarkers?|levels?|concentrations?|samples?|analys[ie]s|proteom\w*|"
                          r"p-?tau\w*|amyloid|neurofilament\w*|nfl|markers?)", r"blood[- ]based biomarkers?",
                          r"(?:plasma|serum) (?:biomarkers?|p-?tau\w*|nfl|neurofilament\w*)",
                          r"neurofilament light", r"p-?tau ?(?:181|217|231)", r"simoa"],
                         ["Neurofilament Proteins"]),
    "digital_health":   ("Wearables / smartphone / EMA", "Clinical & population",
                         [r"wearables?", r"smartphones?", r"digital phenotyping",
                          r"ecological momentary assessments?", r"mhealth", r"mobile health",
                          r"accelerometer\w*"],
                         ["Wearable Electronic Devices", "Smartphone", "Ecological Momentary Assessment"]),
}

GROUPS = {"organisms": ORGANISMS, "methods": METHODS}
CATEGORY_ORDER = {"organisms": ORGANISM_CATEGORIES, "methods": METHOD_CATEGORIES}

_DASHES = re.compile("[‐‑‒–—−]")
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, unify dashes and collapse whitespace so patterns stay simple."""
    return _WS.sub(" ", _DASHES.sub("-", (text or "").lower())).strip()


def compile_vocab() -> list[tuple[str, str, str, re.Pattern | None, frozenset[str]]]:
    """[(group, id, label, compiled_regex_or_None, mesh_names)] in declaration order."""
    out = []
    for group, table in GROUPS.items():
        for tid, (label, _cat, pats, mesh) in table.items():
            rx = None
            if pats:
                rx = re.compile(r"(?<![a-z0-9])(?:" + "|".join(pats) + r")(?![a-z0-9])")
            out.append((group, tid, label, rx, frozenset(mesh)))
    return out


def labels() -> dict[str, dict[str, str]]:
    """{group: {id: label}} for the UI."""
    return {g: {tid: v[0] for tid, v in t.items()} for g, t in GROUPS.items()}


def categories() -> dict[str, dict[str, str]]:
    """{group: {id: category}} for the UI."""
    return {g: {tid: v[1] for tid, v in t.items()} for g, t in GROUPS.items()}


def _self_check() -> list[str]:
    problems = []
    seen_mesh: dict[str, str] = {}
    for g, table in GROUPS.items():
        for tid, (label, cat, pats, mesh) in table.items():
            if cat not in CATEGORY_ORDER[g]:
                problems.append(f"{g}/{tid}: unknown category {cat!r}")
            for m in mesh:
                if m in seen_mesh:
                    problems.append(f"MeSH {m!r} claimed by {seen_mesh[m]} and {tid}")
                seen_mesh[m] = tid
    return problems


if __name__ == "__main__":
    v = compile_vocab()
    print(f"{len(v)} tags ({len(ORGANISMS)} organisms, {len(METHODS)} methods); "
          f"problems: {_self_check() or 'none'}")
    rx = {tid: r for _, tid, _, r, _ in v}
    probes = [
        ("pig", "guinea pig cochlea", False), ("guinea_pig", "guinea pig cochlea", True),
        ("pig", "porcine model", True), ("em_connectomics", "cryo-electron microscopy structure", False),
        ("structural_bio", "cryo-electron microscopy structure", True),
        ("tissue_clearing", "for clarity, we", False), ("tissue_clearing", "clarity-based clearing", True),
        ("ants", "participants performed", None), ("other_insects", "participants performed", False),
        ("other_insects", "desert ants navigate", True), ("human_tissue", "post-mortem brain tissue", True),
        ("nt_sensors", "we grab objects", False), ("nt_sensors", "grab-da2m sensor", True),
        ("rabbit", "rabbit anti-gfap antibody", False), ("rabbit", "rabbits were trained", True),
        ("mouse", "mouse monoclonal antibody against", False), ("mouse", "in the mouse cortex", True),
        ("chick", "chicken anti-gfp", False), ("dog", "madin-darby canine kidney cells", False),
        ("fluid_biomarkers", "cerebrospinal fluid dynamics in hydrocephalus", False),
        ("fluid_biomarkers", "csf p-tau181 levels", True),
        ("rodent_behaviour", "morris water maze", True), ("fluid_biomarkers", "csf1r inhibition", False),
    ]
    bad = 0
    for tid, text, want in probes:
        if want is None or tid not in rx:
            continue
        got = bool(rx[tid].search(normalise(text)))
        if got != want:
            bad += 1
            print(f"  PROBE FAIL {tid}: {text!r} -> {got}, expected {want}")
    print(f"probes: {len(probes) - bad}/{len(probes)} ok" if not bad else f"probes: {bad} failed")
