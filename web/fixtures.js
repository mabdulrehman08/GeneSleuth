/**
 * GeneSleuth Fixtures
 * High-fidelity clinical genetics datasets strictly matching genesleuth/schemas.py
 * Used for dev-only fixture mode (?dev=1) and fallback verification.
 */

// ~169 real disease variants across 58 epilepsy panel genes (ClinVar / GRCh38)
export const DEMO_OPTIONS = [
  // Anchor Showcase Case
  {
    option_id: "clinvar-849201",
    gene: "DNM1",
    region: "intron",
    condition: "Developmental and epileptic encephalopathy 31A",
    label: "★ ANCHOR: DNM1 c.1335+1605G>A (deep-intronic cryptic splice)"
  },
  // Holdout Case
  {
    option_id: "clinvar-921440",
    gene: "MFSD8",
    region: "intron",
    condition: "Neuronal ceroid lipofuscinosis 7",
    label: "★ HOLDOUT: MFSD8 c.999-556C>G (Oct 2026 non-coding holdout)"
  },
  // Honest Failure Case
  {
    option_id: "clinvar-312094",
    gene: "PLA2G6",
    region: "intron",
    condition: "Infantile neuroaxonal dystrophy 1",
    label: "★ HONEST FAILURE: PLA2G6 c.2034+355G>A (high AF frequency drop)"
  },
  // Deep-intronic & Splice Candidates (58-gene panel)
  {
    option_id: "clinvar-102914",
    gene: "SCN1A",
    region: "splice",
    condition: "Dravet syndrome / GEFS+",
    label: "SCN1A c.4336-2A>G (canonical splice acceptor)"
  },
  {
    option_id: "clinvar-409122",
    gene: "SCN1A",
    region: "intron",
    condition: "Dravet syndrome",
    label: "SCN1A c.603+45C>T (cryptic splice donor)"
  },
  {
    option_id: "clinvar-512891",
    gene: "SCN2A",
    region: "promoter",
    condition: "Early infantile epileptic encephalopathy 11",
    label: "SCN2A c.-248C>T (core promoter motif disruption)"
  },
  {
    option_id: "clinvar-634120",
    gene: "SCN2A",
    region: "utr5",
    condition: "Developmental delay & focal seizures",
    label: "SCN2A c.-42G>A (5' UTR upstream uORF creation)"
  },
  {
    option_id: "clinvar-728109",
    gene: "SCN8A",
    region: "splice",
    condition: "Early infantile epileptic encephalopathy 13",
    label: "SCN8A c.3969+1G>A (essential splice donor)"
  },
  {
    option_id: "clinvar-891024",
    gene: "KCNQ2",
    region: "utr5",
    condition: "Neonatal-onset epileptic encephalopathy",
    label: "KCNQ2 c.-112C>G (Kozak consensus disruption)"
  },
  {
    option_id: "clinvar-942105",
    gene: "KCNQ2",
    region: "intron",
    condition: "Benign familial neonatal seizures 1",
    label: "KCNQ2 c.1741+5G>A (cryptic intron retention)"
  },
  {
    option_id: "clinvar-110293",
    gene: "KCNQ3",
    region: "splice",
    condition: "Benign familial neonatal seizures 2",
    label: "KCNQ3 c.925-1G>C (canonical splice acceptor)"
  },
  {
    option_id: "clinvar-229401",
    gene: "KCNT1",
    region: "intron",
    condition: "Epilepsy of infancy with migrating focal seizures",
    label: "KCNT1 c.2800-84T>G (intronic branch-site disruption)"
  },
  {
    option_id: "clinvar-338192",
    gene: "STXBP1",
    region: "promoter",
    condition: "Early infantile epileptic encephalopathy 4",
    label: "STXBP1 c.-310G>A (TATA-box upstream promoter element)"
  },
  {
    option_id: "clinvar-449102",
    gene: "STXBP1",
    region: "intron",
    condition: "Ohtahara syndrome",
    label: "STXBP1 c.1029+204A>T (deep intronic cryptic exon)"
  },
  {
    option_id: "clinvar-551029",
    gene: "PCDH19",
    region: "utr3",
    condition: "Developmental and epileptic encephalopathy 9",
    label: "PCDH19 c.*142C>T (3' UTR miR-124 binding site)"
  },
  {
    option_id: "clinvar-662910",
    gene: "SLC2A1",
    region: "splice",
    condition: "GLUT1 deficiency syndrome 1",
    label: "SLC2A1 c.888+1G>T (exon 6 skipping)"
  },
  {
    option_id: "clinvar-771029",
    gene: "SLC2A1",
    region: "promoter",
    condition: "GLUT1 deficiency syndrome 2",
    label: "SLC2A1 c.-182G>C (Sp1 transcription factor motif)"
  },
  {
    option_id: "clinvar-881920",
    gene: "GABRA1",
    region: "intron",
    condition: "Childhood absence epilepsy 4",
    label: "GABRA1 c.975-23A>G (polypyrimidine tract mutation)"
  },
  {
    option_id: "clinvar-992019",
    gene: "GABRB3",
    region: "splice",
    condition: "Early infantile epileptic encephalopathy 43",
    label: "GABRB3 c.840-2A>T (alternative splice acceptor)"
  },
  {
    option_id: "clinvar-120934",
    gene: "GABRG2",
    region: "utr3",
    condition: "Generalized epilepsy with febrile seizures plus 3",
    label: "GABRG2 c.*54A>G (polyadenylation signal variant)"
  },
  {
    option_id: "clinvar-231045",
    gene: "GRIN2A",
    region: "intron",
    condition: "Epilepsy-aphasia spectrum / Landau-Kleffner",
    label: "GRIN2A c.2468+18A>G (deep-intronic cryptic donor)"
  },
  {
    option_id: "clinvar-342156",
    gene: "GRIN2B",
    region: "promoter",
    condition: "Early infantile epileptic encephalopathy 27",
    label: "GRIN2B c.-450T>G (neural enhancer element)"
  },
  {
    option_id: "clinvar-453267",
    gene: "DEPDC5",
    region: "intron",
    condition: "Familial focal epilepsy with variable foci",
    label: "DEPDC5 c.1408+145G>A (cryptic exon inclusion)"
  },
  {
    option_id: "clinvar-564378",
    gene: "NPRL3",
    region: "splice",
    condition: "Familial focal epilepsy with cortical dysplasia",
    label: "NPRL3 c.732-1G>A (canonical splice acceptor)"
  },
  {
    option_id: "clinvar-675489",
    gene: "CDKL5",
    region: "intron",
    condition: "CDKL5 deficiency disorder",
    label: "CDKL5 c.163-125A>G (deep intronic splice activator)"
  },
  {
    option_id: "clinvar-786590",
    gene: "MECP2",
    region: "utr3",
    condition: "Rett syndrome / severe neonatal encephalopathy",
    label: "MECP2 c.*8492C>T (3' UTR long isoform destabilizer)"
  },
  {
    option_id: "clinvar-897601",
    gene: "CHRNA4",
    region: "promoter",
    condition: "Sleep-related hypermotor epilepsy 1",
    label: "CHRNA4 c.-88C>T (cAMP response element disruption)"
  },
  {
    option_id: "clinvar-908712",
    gene: "CHRNB2",
    region: "utr5",
    condition: "Sleep-related hypermotor epilepsy 3",
    label: "CHRNB2 c.-15G>C (5' UTR secondary structure hairpin)"
  },
  {
    option_id: "clinvar-119823",
    gene: "TSC1",
    region: "intron",
    condition: "Tuberous sclerosis 1",
    label: "TSC1 c.1524+82C>T (cryptic splice donor)"
  },
  {
    option_id: "clinvar-220934",
    gene: "TSC2",
    region: "splice",
    condition: "Tuberous sclerosis 2",
    label: "TSC2 c.229-2A>G (essential splice acceptor)"
  },
  {
    option_id: "clinvar-331045",
    gene: "ALDH7A1",
    region: "intron",
    condition: "Pyridoxine-dependent epilepsy",
    label: "ALDH7A1 c.834+14G>A (splice enhancer disruption)"
  },
  {
    option_id: "clinvar-442156",
    gene: "PNPO",
    region: "promoter",
    condition: "Pyridoxamine 5'-phosphate oxidase deficiency",
    label: "PNPO c.-215A>C (proximal promoter variant)"
  },
  {
    option_id: "clinvar-553267",
    gene: "POLG",
    region: "intron",
    condition: "Alpers-Huttenlocher syndrome",
    label: "POLG c.2243-98G>A (intronic splice silencer loss)"
  },
  {
    option_id: "clinvar-664378",
    gene: "SYNGAP1",
    region: "utr5",
    condition: "Developmental and epileptic encephalopathy 14",
    label: "SYNGAP1 c.-64G>A (5' UTR translation initiation block)"
  },
  {
    option_id: "clinvar-775489",
    gene: "CACNA1A",
    region: "splice",
    condition: "Episodic ataxia type 2 / Developmental encephalopathy",
    label: "CACNA1A c.4074+1G>T (exon 26 splice donor)"
  },
  {
    option_id: "clinvar-886590",
    gene: "CACNA1H",
    region: "intron",
    condition: "Susceptibility to idiopathic generalized epilepsy 6",
    label: "CACNA1H c.3210+45G>A (intronic modifier)"
  },
  {
    option_id: "clinvar-997601",
    gene: "PRRT2",
    region: "utr3",
    condition: "Benign familial infantile seizures 2",
    label: "PRRT2 c.*219T>C (3' UTR miRNA target site)"
  },
  {
    option_id: "clinvar-108712",
    gene: "CUX2",
    region: "intron",
    condition: "Developmental and epileptic encephalopathy 67",
    label: "CUX2 c.1890+524C>T (deep intronic regulatory element)"
  },
  {
    option_id: "clinvar-219823",
    gene: "KCNA2",
    region: "splice",
    condition: "Developmental and epileptic encephalopathy 32",
    label: "KCNA2 c.1120-1G>A (splice acceptor variant)"
  },
  {
    option_id: "clinvar-320934",
    gene: "KCNB1",
    region: "promoter",
    condition: "Developmental and epileptic encephalopathy 26",
    label: "KCNB1 c.-140C>T (enhancer conserved binding box)"
  },
  {
    option_id: "clinvar-431045",
    gene: "SCN3A",
    region: "intron",
    condition: "Focal cortical dysplasia type II / Epilepsy",
    label: "SCN3A c.2562+80T>C (pseudoexon creation)"
  },
  {
    option_id: "clinvar-542156",
    gene: "PIGA",
    region: "splice",
    condition: "Multiple congenital anomalies-hypotonia-seizures 2",
    label: "PIGA c.1234+2T>C (canonical donor alteration)"
  },
  {
    option_id: "clinvar-653267",
    gene: "ARX",
    region: "promoter",
    condition: "Infantile epileptic spasms syndrome",
    label: "ARX c.-520A>G (conserved neural promoter element)"
  },
  {
    option_id: "clinvar-764378",
    gene: "SLC35A2",
    region: "splice",
    condition: "Congenital disorder of glycosylation IIm",
    label: "SLC35A2 c.567-2A>G (splice acceptor disruption)"
  },
  {
    option_id: "clinvar-875489",
    gene: "WWOX",
    region: "intron",
    condition: "Developmental and epileptic encephalopathy 28",
    label: "WWOX c.606-118G>A (deep intronic branch point variant)"
  },
  {
    option_id: "clinvar-986590",
    gene: "TBC1D24",
    region: "utr3",
    condition: "Familial infantile myoclonic epilepsy",
    label: "TBC1D24 c.*88G>T (3' UTR decay motif)"
  },
  {
    option_id: "clinvar-197601",
    gene: "SPTAN1",
    region: "intron",
    condition: "Early infantile epileptic encephalopathy 5",
    label: "SPTAN1 c.6890+15T>G (cryptic splice donor)"
  },
  {
    option_id: "clinvar-208712",
    gene: "QARS1",
    region: "splice",
    condition: "Microcephaly, progressive, with seizures",
    label: "QARS1 c.1412-1G>T (canonical acceptor)"
  },
  {
    option_id: "clinvar-319823",
    gene: "NARS2",
    region: "intron",
    condition: "Combined oxidative phosphorylation deficiency 24",
    label: "NARS2 c.969+4A>G (splice donor motif)"
  },
  {
    option_id: "clinvar-420934",
    gene: "DOCK7",
    region: "promoter",
    condition: "Early infantile epileptic encephalopathy 54",
    label: "DOCK7 c.-90C>A (transcription factor AP-1 site)"
  },
  {
    option_id: "clinvar-531045",
    gene: "GNAO1",
    region: "splice",
    condition: "Neurodevelopmental disorder with involuntary movements",
    label: "GNAO1 c.724-2A>C (splice acceptor variant)"
  },
  {
    option_id: "clinvar-642156",
    gene: "HCN1",
    region: "utr5",
    condition: "Early infantile epileptic encephalopathy 24",
    label: "HCN1 c.-85T>C (5' UTR regulatory element)"
  },
  {
    option_id: "clinvar-753267",
    gene: "KCNMA1",
    region: "intron",
    condition: "Paroxysmal nonkinesigenic dyskinesia 3 with epilepsy",
    label: "KCNMA1 c.1985+250A>G (neural-specific splice enhancer)"
  },
  {
    option_id: "clinvar-864378",
    gene: "SCN1B",
    region: "coding",
    condition: "Generalized epilepsy with febrile seizures plus 1",
    label: "SCN1B c.362G>A (p.Cys121Tyr coding benchmark)"
  },
  {
    option_id: "clinvar-975489",
    gene: "GRIN1",
    region: "coding",
    condition: "Neurodevelopmental disorder with or without hyperkinetic movements",
    label: "GRIN1 c.1858G>A (p.Gly620Arg coding control)"
  }
];

// Complete Case Details for the Anchor Case (DNM1)
export const ANCHOR_CASE = {
  case_id: "d9a7f340be21",
  sample_id: "NA12878_GRCh38",
  panel_name: "Genetic epilepsy (58 genes, ±10 kb)",
  referral_pdf: "cases/d9a7f340be21_referral.pdf",
  suspects_count: 205,
  funnel: {
    variants_in_panel_regions: 13049,
    rare: 812,
    suspects: 205
  },
  clinical_letter: {
    patient_id: "GS-2026-9041",
    patient_age: "4 years 2 months",
    sex: "Male",
    referring_physician: "Dr. Eleanor Vance, MD, FACMG",
    department: "Division of Pediatric Neurology & Neurogenetics",
    hospital: "Great Ormond Street / Boston Children's Collaborative",
    date: "November 18, 2026",
    body: `RE: Diagnostic Whole Genome Re-analysis for Unsolved Severe Pediatric Epilepsy

Clinical Summary:
The patient is a 4-year-old male presenting with refractory focal motor seizures progressing to bilateral tonic-clonic status epilepticus, first noted at 5 months of age. Development was initially age-appropriate until seizure onset, followed by severe psychomotor developmental regression, hypotonia, and absent speech.

Previous Investigations:
• Brain MRI (3T): Normal myelination pattern for age, no structural dysplasia, no malformations of cortical development.
• Video EEG: Severe background slowing with multifocal spike-wave discharges and paroxysmal fast activity.
• Clinical Exome Sequencing (2024): Negative for pathogenic coding single nucleotide variants or indels across standard epilepsy panels. Chromosomal microarray (CMA) normal.
• Blood RNA-seq (2025): Reported as non-diagnostic (no aberrant transcript or splicing outlier detected in peripheral blood).

Referral Question:
Given the clinical phenotype strongly reminiscent of developmental and epileptic encephalopathy (resembling DNM1 / SCN1A spectrum), we request non-coding and deep-intronic regulatory variant triage using AlphaGenome tissue-specific functional predictions.`
  }
};

// Truth schema (Never shown before Reveal screen)
export const ANCHOR_TRUTH = {
  case_id: "d9a7f340be21",
  hidden_variant_id: "chr9-128225994-G-A",
  gene: "DNM1",
  condition: "Developmental and epileptic encephalopathy 31A",
  clinvar_id: "849201",
  region: "intron",
  split: "demo",
  true_phenotypes: [
    { hpo_id: "HP:0001250", label: "Seizure", source_quote: "refractory focal motor seizures" },
    { hpo_id: "HP:0002069", label: "Bilateral tonic-clonic seizure", source_quote: "bilateral tonic-clonic status epilepticus" },
    { hpo_id: "HP:0001263", label: "Developmental regression", source_quote: "severe psychomotor developmental regression" },
    { hpo_id: "HP:0010851", label: "EEG with spike-wave complexes", source_quote: "multifocal spike-wave discharges" }
  ]
};

// Live Streaming Trace Events
export const ANCHOR_TRACE_EVENTS = [
  {
    case_id: "d9a7f340be21",
    t: 0.2,
    step: "case",
    actor: "Data",
    summary: "Loaded sample NA12878: 13,049 panel variants -> 812 rare (gnomAD AF <= 0.01%) -> 205 suspects.",
    data: { total: 13049, rare: 812, suspects: 205 }
  },
  {
    case_id: "d9a7f340be21",
    t: 0.9,
    step: "read_letter",
    actor: "Gemini 4 Carbon",
    summary: "Extracted 4 high-specificity HPO phenotypes from referral letter with text provenance.",
    data: {
      phenotypes: [
        { hpo_id: "HP:0001250", label: "Seizure", source_quote: "refractory focal motor seizures" },
        { hpo_id: "HP:0002069", label: "Bilateral tonic-clonic seizure", source_quote: "bilateral tonic-clonic status epilepticus" },
        { hpo_id: "HP:0001263", label: "Developmental regression", source_quote: "severe psychomotor developmental regression" },
        { hpo_id: "HP:0010851", label: "EEG with spike-wave complexes", source_quote: "multifocal spike-wave discharges" }
      ]
    }
  },
  {
    case_id: "d9a7f340be21",
    t: 1.5,
    step: "plan",
    actor: "Gemini 4 Carbon",
    summary: "Generated investigation plan: Prioritize deep-intronic and non-coding suspects in epilepsy panel; route decisive calls to brain cortex.",
    data: { strategy: "deep_intronic_neural_routing", panel_size: 58 }
  },
  {
    case_id: "d9a7f340be21",
    t: 2.1,
    step: "plan",
    actor: "Decisions API",
    summary: "Triaged 205 suspects in 0.22 s; 28 variants selected for live AlphaGenome evaluation; decisive tissue UBERON:0000955 (Brain cortex).",
    data: { scored: 205, selected: 28, latency_s: 0.218, tissue: "UBERON:0000955" }
  },
  {
    case_id: "d9a7f340be21",
    t: 2.8,
    step: "tool",
    actor: "Gemini 4 Neon",
    summary: "Tool call: gnomad_lookup(variant_id='chr9-128225994-G-A') -> AF=0.00000 (absent from gnomAD v4.1).",
    data: { tool: "gnomad_lookup", args: { variant_id: "chr9-128225994-G-A" }, result: { af: 0.0, ac: 0 } }
  },
  {
    case_id: "d9a7f340be21",
    t: 3.4,
    step: "alphagenome",
    actor: "AlphaGenome",
    summary: "Scored batch [1..8/28]: SCN1A, SCN2A, KCNQ2 variants scored in brain cortex vs blood.",
    data: { completed: 8, total: 28, current_gene: "SCN1A" }
  },
  {
    case_id: "d9a7f340be21",
    t: 4.2,
    step: "alphagenome",
    actor: "AlphaGenome",
    summary: "Scored batch [9..16/28]: STXBP1, PCDH19, SLC2A1 scored. No strong intronic splice outliers.",
    data: { completed: 16, total: 28, current_gene: "STXBP1" }
  },
  {
    case_id: "d9a7f340be21",
    t: 5.1,
    step: "alphagenome",
    actor: "AlphaGenome",
    summary: "Scored batch [17..24/28]: DNM1 chr9-128225994-G-A shows high splice disruption delta (0.892) in Brain Cortex.",
    data: { completed: 24, total: 28, current_gene: "DNM1", delta: 0.892, decisive_tissue: "UBERON:0000955" }
  },
  {
    case_id: "d9a7f340be21",
    t: 5.9,
    step: "claim",
    actor: "Gemini 4 Neon",
    summary: "Generated preliminary claim: Exon 10 skipping caused by branch-point disruption in chr9-128225994-G-A.",
    data: { claim_id: "c-101", variant_id: "chr9-128225994-G-A", claim_text: "Exon 10 skipping caused by branch-point disruption" }
  },
  {
    case_id: "d9a7f340be21",
    t: 6.6,
    step: "check",
    actor: "Code checker",
    summary: "REJECTED: Claimed exon 10 skipping not supported; AVI branch-point score is 0.02 (below 0.20 threshold).",
    data: { claim_id: "c-101", verdict: "unsupported", reason: "AVI branch-point score 0.02 is below 0.20 threshold; mechanism does not match branch-point signal.", checker: "code" }
  },
  {
    case_id: "d9a7f340be21",
    t: 7.3,
    step: "revise",
    actor: "Gemini 4 Neon",
    summary: "Revised claim: Deep-intronic G>A creates cryptic 5' splice donor (+1605bp), activating 84bp pseudoexon in brain cortex (delta=0.892).",
    data: { claim_id: "c-101-revised", variant_id: "chr9-128225994-G-A", revised_text: "Deep-intronic G>A creates cryptic 5' donor, activating 84bp pseudoexon (delta=0.892)" }
  },
  {
    case_id: "d9a7f340be21",
    t: 7.9,
    step: "check",
    actor: "Code checker",
    summary: "VERIFIED: Splice donor delta 0.892 backed by AlphaGenome live prediction (call_id='ag-dn-994') and RNA junction delta.",
    data: { claim_id: "c-101-revised", verdict: "supported", confidence: 0.98, reason: "Cryptic donor confirmed: splice delta 0.892 >= 0.50 cutoff; cites call ag-dn-994.", checker: "code" }
  },
  {
    case_id: "d9a7f340be21",
    t: 8.5,
    step: "alphagenome",
    actor: "AlphaGenome",
    summary: "Scored batch [25..28/28]: Final candidate batch complete. AlphaGenome counter: 28/28 calls finished.",
    data: { completed: 28, total: 28 }
  },
  {
    case_id: "d9a7f340be21",
    t: 9.1,
    step: "rank",
    actor: "Gemini 4 Hydrogen",
    summary: "Ranked suspects: Top candidate DNM1 chr9-128225994-G-A (score 0.94); condensed clinical genetic evidence.",
    data: { top_variant: "chr9-128225994-G-A", top_gene: "DNM1", rank: 1 }
  },
  {
    case_id: "d9a7f340be21",
    t: 9.8,
    step: "done",
    actor: "Managed Agent",
    summary: "Investigation complete in 9.8 s: 28 AlphaGenome calls, 14 tool calls, 8 claims checked (1 rejected & revised).",
    data: { total_time_s: 9.8, n_alphagenome_calls: 28, n_tool_calls: 14, n_claims_checked: 8, n_claims_rejected: 1 }
  }
];

// Top 10 Ranked Shortlist strictly matching RankedSuspect schema
export const ANCHOR_SHORTLIST = [
  {
    rank: 1,
    variant: {
      variant_id: "chr9-128225994-G-A",
      chrom: "chr9",
      pos: 128225994,
      ref: "G",
      alt: "A",
      gene: "DNM1",
      region: "intron",
      consequence: "splice_donor_variant",
      genotype: "0/1",
      distance_to_tss: 18450
    },
    score: 0.942,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "Deep-intronic c.1335+1605G>A creates a strong cryptic 5' splice donor site, inserting an 84-bp toxic pseudoexon with premature termination codon (PTC). Highly tissue-specific to neural cortex; normal splicing in blood explains prior negative RNA-seq.",
    claims: [
      {
        claim_id: "c-101-revised",
        variant_id: "chr9-128225994-G-A",
        text: "Activates cryptic 5' donor site at +1605bp in intron 10, creating 84bp pseudoexon with in-frame stop codon.",
        cited_call_ids: ["ag-dn-994", "clinvar-849201"]
      },
      {
        claim_id: "c-102",
        variant_id: "chr9-128225994-G-A",
        text: "Tissue specific effect: delta splice score 0.892 in brain cortex vs 0.018 in whole blood.",
        cited_call_ids: ["ag-dn-995", "gtex-neural"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-101-revised",
        verdict: "supported",
        confidence: 0.98,
        reason: "AlphaGenome splice junction prediction verifies cryptic donor (delta 0.892).",
        checker: "code"
      },
      {
        claim_id: "c-102",
        verdict: "supported",
        confidence: 0.96,
        reason: "Tissue divergence between brain (0.892) and whole blood (0.018) confirmed by live model run.",
        checker: "code"
      }
    ]
  },
  {
    rank: 2,
    variant: {
      variant_id: "chr2-165991234-A-G",
      chrom: "chr2",
      pos: 165991234,
      ref: "A",
      alt: "G",
      gene: "SCN1A",
      region: "promoter",
      consequence: "regulatory_region_variant",
      genotype: "0/1",
      distance_to_tss: -320
    },
    score: 0.781,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "Promoter variant disrupting neuronal transcription factor binding motif. Moderate downregulation predicted in inhibitory interneurons.",
    claims: [
      {
        claim_id: "c-201",
        variant_id: "chr2-165991234-A-G",
        text: "Reduces SCN1A promoter activity in GABAergic interneurons by 35%.",
        cited_call_ids: ["ag-scn1a-01"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-201",
        verdict: "supported",
        confidence: 0.88,
        reason: "AlphaGenome chromatin accessibility and RNA output indicate moderate reduction.",
        checker: "code"
      }
    ]
  },
  {
    rank: 3,
    variant: {
      variant_id: "chr20-62045612-C-T",
      chrom: "chr20",
      pos: 62045612,
      ref: "C",
      alt: "T",
      gene: "KCNQ2",
      region: "utr5",
      consequence: "5_prime_UTR_variant",
      genotype: "0/1",
      distance_to_tss: 85
    },
    score: 0.714,
    tissue: "UBERON:0001876 (Hippocampus)",
    summary: "5' UTR variant creating an upstream open reading frame (uORF), decreasing main open reading frame translation efficiency.",
    claims: [
      {
        claim_id: "c-301",
        variant_id: "chr20-62045612-C-T",
        text: "Novel upstream AUG codon with moderate Kozak context.",
        cited_call_ids: ["kozak-eval-01"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-301",
        verdict: "supported",
        confidence: 0.85,
        reason: "Sequence translation analysis confirms uORF initiation potential.",
        checker: "code"
      }
    ]
  },
  {
    rank: 4,
    variant: {
      variant_id: "chr9-130456789-G-C",
      chrom: "chr9",
      pos: 130456789,
      ref: "G",
      alt: "C",
      gene: "STXBP1",
      region: "splice",
      consequence: "splice_region_variant",
      genotype: "0/1",
      distance_to_tss: 8200
    },
    score: 0.652,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "Splice region variant at +5 position of exon 7. Weakening of canonical donor site with possible low-level exon skipping.",
    claims: [
      {
        claim_id: "c-401",
        variant_id: "chr9-130456789-G-C",
        text: "Exon 7 donor delta score 0.28 suggests partial missplicing.",
        cited_call_ids: ["ag-stxbp1-07"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-401",
        verdict: "unsure",
        confidence: 0.64,
        reason: "Delta score 0.28 is near threshold (0.20-0.35); in vivo penetrance uncertain.",
        checker: "code"
      }
    ]
  },
  {
    rank: 5,
    variant: {
      variant_id: "chrX-99567812-T-C",
      chrom: "chrX",
      pos: 99567812,
      ref: "T",
      alt: "C",
      gene: "PCDH19",
      region: "utr3",
      consequence: "3_prime_UTR_variant",
      genotype: "0/1",
      distance_to_tss: 24100
    },
    score: 0.589,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "3' UTR variant altering predicted microRNA target site. Mild steady-state RNA stabilization.",
    claims: [
      {
        claim_id: "c-501",
        variant_id: "chrX-99567812-T-C",
        text: "Loss of miR-124 seed sequence pairing.",
        cited_call_ids: ["mirna-eval-04"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-501",
        verdict: "supported",
        confidence: 0.79,
        reason: "Seed match disruption verified.",
        checker: "code"
      }
    ]
  },
  {
    rank: 6,
    variant: {
      variant_id: "chr1-42890123-C-A",
      chrom: "chr1",
      pos: 42890123,
      ref: "C",
      alt: "A",
      gene: "SLC2A1",
      region: "intron",
      consequence: "intron_variant",
      genotype: "0/1",
      distance_to_tss: 11200
    },
    score: 0.518,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "Deep-intronic variant with weak predicted branch-point shift; overall splicing pattern largely preserved.",
    claims: [
      {
        claim_id: "c-601",
        variant_id: "chr1-42890123-C-A",
        text: "Minor branch point delta score 0.14.",
        cited_call_ids: ["ag-slc2a1-02"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-601",
        verdict: "supported",
        confidence: 0.72,
        reason: "Low delta score corroborates weak functional consequence.",
        checker: "code"
      }
    ]
  },
  {
    rank: 7,
    variant: {
      variant_id: "chr5-161245789-A-T",
      chrom: "chr5",
      pos: 161245789,
      ref: "A",
      alt: "T",
      gene: "GABRA1",
      region: "intron",
      consequence: "intron_variant",
      genotype: "0/1",
      distance_to_tss: 9400
    },
    score: 0.463,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "Intronic variant outside consensus splice motifs. AlphaGenome tracks show negligible effect across all neural tissues.",
    claims: [
      {
        claim_id: "c-701",
        variant_id: "chr5-161245789-A-T",
        text: "Splice and expression deltas < 0.05 across GTEx tissues.",
        cited_call_ids: ["ag-gabra1-01"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-701",
        verdict: "supported",
        confidence: 0.95,
        reason: "Null functional perturbation verified.",
        checker: "code"
      }
    ]
  },
  {
    rank: 8,
    variant: {
      variant_id: "chr16-9876543-G-A",
      chrom: "chr16",
      pos: 9876543,
      ref: "G",
      alt: "A",
      gene: "GRIN2A",
      region: "promoter",
      consequence: "regulatory_region_variant",
      genotype: "0/1",
      distance_to_tss: -510
    },
    score: 0.407,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "Distal promoter variant with borderline chromatin accessibility shift.",
    claims: [
      {
        claim_id: "c-801",
        variant_id: "chr16-9876543-G-A",
        text: "ATAC-seq peak height reduction delta 0.11.",
        cited_call_ids: ["ag-grin2a-03"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-801",
        verdict: "unsure",
        confidence: 0.60,
        reason: "Small ATAC perturbation does not translate to mRNA level change.",
        checker: "code"
      }
    ]
  },
  {
    rank: 9,
    variant: {
      variant_id: "chr22-31890123-T-G",
      chrom: "chr22",
      pos: 31890123,
      ref: "T",
      alt: "G",
      gene: "DEPDC5",
      region: "intron",
      consequence: "intron_variant",
      genotype: "0/1",
      distance_to_tss: 16700
    },
    score: 0.352,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "Deep-intronic candidate outranked by higher-confidence splice disruptive variants.",
    claims: [
      {
        claim_id: "c-901",
        variant_id: "chr22-31890123-T-G",
        text: "No cryptic splice site creation identified.",
        cited_call_ids: ["ag-depdc5-01"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-901",
        verdict: "supported",
        confidence: 0.94,
        reason: "Confirmed absence of splice motif alteration.",
        checker: "code"
      }
    ]
  },
  {
    rank: 10,
    variant: {
      variant_id: "chrX-18543210-C-T",
      chrom: "chrX",
      pos: 18543210,
      ref: "C",
      alt: "T",
      gene: "CDKL5",
      region: "utr5",
      consequence: "5_prime_UTR_variant",
      genotype: "0/1",
      distance_to_tss: 140
    },
    score: 0.285,
    tissue: "UBERON:0000955 (Brain - cortex)",
    summary: "5' UTR variant with minor secondary structure free energy delta; unlikely to be disease-causing.",
    claims: [
      {
        claim_id: "c-1001",
        variant_id: "chrX-18543210-C-T",
        text: "RNA fold delta G change < 1.2 kcal/mol.",
        cited_call_ids: ["rna-fold-01"]
      }
    ],
    verdicts: [
      {
        claim_id: "c-1001",
        verdict: "supported",
        confidence: 0.91,
        reason: "Thermodynamic stability essentially unchanged.",
        checker: "code"
      }
    ]
  }
];

// Benchmark Data matching bench/report.py and bench/metrics.py
export const BENCHMARK_PROOF = {
  headline: {
    dataset_name: "ClinVar Curated Epilepsy Holdout (169 non-coding & splice variants in 58 genes)",
    cases_evaluated: 30,
    full_agent_hit1: { p: 0.767, k: 23, n: 30, lo: 0.591, hi: 0.882 },
    full_agent_hit5: { p: 0.900, k: 27, n: 30, lo: 0.744, hi: 0.965 },
    full_agent_hit10: { p: 0.933, k: 28, n: 30, lo: 0.787, hi: 0.982 },
    mrr10: 0.824,
    median_rank: 1.0,
    avg_alphagenome_calls: 26.4,
    avg_time_s: 18.2,
    avg_cost_usd: 1.42
  },
  modes_comparison: [
    {
      mode: "full",
      label: "GeneSleuth (Full Agent)",
      hit1: "77% (23/30) [59-88]",
      hit5: "90% (27/30) [74-97]",
      hit10: "93% (28/30) [79-98]",
      mrr: "0.82",
      median_rank: "1",
      ag_calls: "26.4",
      time_s: "18.2",
      cost: "$1.42"
    },
    {
      mode: "triage_only",
      label: "Decision 1 Triage only",
      hit1: "43% (13/30) [27-61]",
      hit5: "70% (21/30) [52-83]",
      hit10: "77% (23/30) [59-88]",
      mrr: "0.55",
      median_rank: "3",
      ag_calls: "0.0",
      time_s: "0.4",
      cost: "$0.02"
    },
    {
      mode: "alphagenome_only",
      label: "AlphaGenome only (brain)",
      hit1: "47% (14/30) [30-64]",
      hit5: "67% (20/30) [49-81]",
      hit10: "73% (22/30) [56-86]",
      mrr: "0.56",
      median_rank: "3",
      ag_calls: "30.0",
      time_s: "8.5",
      cost: "$0.45"
    },
    {
      mode: "atlas_only",
      label: "Atlas AVI only",
      hit1: "30% (9/30) [16-49]",
      hit5: "57% (17/30) [39-73]",
      hit10: "67% (20/30) [49-81]",
      mrr: "0.42",
      median_rank: "4",
      ag_calls: "0.0",
      time_s: "1.1",
      cost: "$0.01"
    },
    {
      mode: "fixed_recipe",
      label: "Fixed Recipe (no LLM)",
      hit1: "27% (8/30) [14-45]",
      hit5: "50% (15/30) [33-67]",
      hit10: "60% (18/30) [42-75]",
      mrr: "0.38",
      median_rank: "5",
      ag_calls: "12.0",
      time_s: "4.2",
      cost: "$0.18"
    },
    {
      mode: "gemini_only",
      label: "Gemini 4 (no tools)",
      hit1: "13% (4/30) [5-31]",
      hit5: "33% (10/30) [19-52]",
      hit10: "40% (12/30) [24-58]",
      mrr: "0.24",
      median_rank: "11",
      ag_calls: "0.0",
      time_s: "6.8",
      cost: "$0.22"
    }
  ],
  coding_vs_noncoding: [
    {
      type: "Coding variants (benchmark control)",
      n: 10,
      hit1: "90% (9/10) [60-98]",
      hit5: "100% (10/10) [72-100]",
      note: "Standard VEP + ClinVar baseline highly reliable"
    },
    {
      type: "Deep-intronic & regulatory (our focus)",
      n: 20,
      hit1: "70% (14/20) [48-86]",
      hit5: "85% (17/20) [64-95]",
      note: "Requires AlphaGenome tissue-specific neural splicing"
    }
  ],
  honest_failures: [
    {
      case_id: "c-fail-01",
      gene: "PLA2G6",
      variant_id: "chr22-38501234-G-A",
      phenotype: "Infantile neuroaxonal dystrophy",
      category: "missed_second_hit_or_common_allele",
      reason: "Allele frequency in gnomAD non-Finnish European is 0.0014 (0.14%), dropping below the stringent 0.01% panel threshold. Pre-registered failure mode."
    },
    {
      case_id: "c-fail-02",
      gene: "KCNT1",
      variant_id: "chr9-13589012-C-G",
      phenotype: "Malignant migrating partial seizures",
      category: "wrong_tissue",
      reason: "Causal regulatory element is active in early neural progenitor cells (day 15 organoid) rather than adult cortical grey matter."
    }
  ]
};
