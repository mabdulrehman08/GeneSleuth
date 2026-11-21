# Data sources, licenses and attribution

Every external source used by GeneSleuth, with URL, version read on Nov 21 2026, license or terms as published by
the source, and the attribution it asks for. License text was read from each source's own pages, repository or PDF
on Nov 21 2026 (items marked UNVERIFIED could not be read as rendered pages; the reason is given). All code in this
repository was written during the event; only public data and public APIs are used.

Suggested README acknowledgement block (copy as is):

> This product uses the Human Phenotype Ontology (release v2026-09-01; https://hpo.jax.org). It includes data from
> the 1000 Genomes Project / IGSR high-coverage NYGC callset, ClinVar, MANE (NCBI and EMBL-EBI), Ensembl and gnomAD
> v4.1, and gene panel content from Genomics England PanelApp. Variant effect predictions come from Google
> DeepMind's AlphaGenome.

## Summary table

| Source | What we use it for | License / terms | Required attribution |
|---|---|---|---|
| 1000 Genomes / IGSR NYGC 30x (3,202 samples) | background genome (NA12878), AF fallback | open data, no formal license; EMBL-EBI Terms of Use + IGSR reuse statements | NYGC/NHGRI acknowledgement sentence + Byrska-Bishop et al. 2022 |
| gnomAD v4.1 | allele-frequency filter and `population_frequency` | CC0 1.0 (primary data) | requested, not required: Chen et al. 2024, "This tool includes data from the gnomAD v4.1 release"; do not use "gnomAD" in a tool name |
| ClinVar | planted variants, truth labels, local panel table | NCBI public domain, no NCBI restrictions (submitter content may carry its own copyright) | attribute ClinVar as data source; Landrum et al. 2018 |
| HPO (hp.obo, hp.json, genes_to_phenotype.txt, phenotype.hpoa) | phenotype terms, gene-phenotype match, synthetic letters | custom HPO license (free use with conditions) | cite HPO, show version/date, do not alter content, show acknowledgement statement |
| MANE v1.5 (summary + Ensembl GTF) | gene coordinates, exon/UTR structure | none stated on the MANE pages; falls under NCBI public-domain policy and EMBL-EBI/Ensembl open terms (inferred) | Morales et al. 2022 |
| Ensembl (REST, VEP) | VEP consequence fallback, gene IDs | no restrictions on data; code Apache 2.0; third-party constraints may apply | Ensembl release + Dyer et al. (Ensembl 2025); McLaren et al. 2016 (VEP) |
| Genomics England PanelApp (panel 402) | source of the 58-gene epilepsy list | custom Terms of Use (December 2019) | acknowledge Genomics England as author; Martin et al. 2019; name and version of the panel |
| AlphaGenome (Google DeepMind) | variant effect scores, plots | Google AlphaGenome terms: non-commercial research use | Avsec et al. 2026 (+ Atlas preprint) |
| Gemini API (Gemini 4 Carbon, Neon, Hydrogen, Decision 1) | reader, investigator, triage, checker, letters | Google APIs Terms + Gemini API Additional Terms (eff. 2026-03-23) | none required |
| myvariant.info | optional AF fallback only (not used in the current build) | custom TSRI Terms of Use; underlying data keep their own licenses | keep copyright notices |

## 1. 1000 Genomes / IGSR, NYGC 30x high-coverage (GRCh38)
- URLs: https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/ ;
  reuse statements: https://www.internationalgenome.org/IGSR_disclaimer and the 30x data reuse README in the same collection.
- Version: 3,202 samples (2,504 unrelated released 2019, 698 related released 2020); phased SNV/INDEL/SV panel 2022-04-22.
- Terms (verbatim): "Data from the 1000 Genomes Project is now available without embargo, following the final
  publication from the project. Use of the data should be cited in the usual way." Reuse README: "All cell lines were
  obtained from the Coriell Institute for Medical Research and were consented for full public release of genomic data."
  IGSR also notes that restrictions on pieces of data "vary".
- Attribution: "These data were generated at the New York Genome Center with funds provided by NHGRI Grant
  3UM1HG008901-03S1." (the 3,202-sample extension also lists 3UM1HG008901-04S2). Cite Byrska-Bishop et al.,
  *High-coverage whole-genome sequencing of the expanded 1000 Genomes Project cohort including 602 trios*, Cell
  185(18):3426-3440 (2022), doi:10.1016/j.cell.2022.08.004.
- Bundled derivative: a one-sample (NA12878) subset of variants in the panel regions (slice A1's suspects table).

## 2. gnomAD v4.1
- URLs: https://gnomad.broadinstitute.org/ (GraphQL API https://gnomad.broadinstitute.org/api, dataset `gnomad_r4`);
  VCFs https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/genomes/.
- Version: v4.1 released 04/19/2024 (807,162 individuals); v4.1.1 constraint update announced 2026-03-30.
- Terms (verbatim, from the site's own policy source): "The primary data from the gnomAD exomes and genomes are
  available free of restrictions under the Creative Commons Zero Public Domain Dedication. This means that you can
  use it for any purpose without legally having to give attribution. However, we request that you actively
  acknowledge and give attribution to the gnomAD project, and link back to the relevant page, wherever possible."
  Annotations such as SpliceAI are CC BY-NC 4.0 (we do not use them). Users agree not to attempt to reidentify
  participants. Developers are asked to state "This tool includes data from the gnomAD v4.1 release." and not to put
  "gnomAD" in the tool's name or use its logo.
- Citation: Chen S, et al. *A genomic mutational constraint map using variation in 76,156 human genomes*, Nature
  625:92-100 (2024), doi:10.1038/s41586-023-06045-0.
- Measured API behaviour: about 2 s per request; HTTP 429 after roughly 4-10 requests in a short burst (about 10 per
  minute), so `population_frequency` spaces calls and caches every answer.
- Not read as a rendered page (JavaScript app); text taken from the site's source repository
  (broadinstitute/gnomad-browser, `browser/about/policies/`), which may be newer than the deployed site.
- Bundled derivative: allele frequencies (AF/AN) for the sample's panel-region variants (slice A1's suspects table).

## 3. ClinVar
- URL: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz (we used the weekly `clinvar_20261115` VCF).
- Terms: "If you distribute or copy data from ClinVar, we ask that you provide attribution to ClinVar as a data source
  in publications and websites. You can cite one of the ClinVar publications (e.g. PMID: 29165669)." NCBI policy:
  information created by or for the US government is public domain, and "NCBI itself places no restrictions on the use
  or distribution of the data"; submitted third-party content may be protected by copyright.
- Citation: Landrum MJ, et al. *ClinVar: improving access to variant interpretations and supporting evidence*, Nucleic
  Acids Res 46(D1):D1062-D1067 (2018), doi:10.1093/nar/gkx1153.
- UNVERIFIED detail: the ClinVar usage page is behind a CAPTCHA; the quote is from an archived copy.
- Bundled derivative: `assets/clinvar_panel.tsv.gz`, all 115,586 ClinVar records inside the 58 panel regions
  (columns in `scripts/data_clinvar_table.py`), reduced to the fields CLNSIG, CLNREVSTAT, CLNDN, CLNDISDB, MC,
  GENEINFO, ALLELEID and the variation id. Candidate lists (slice A3) are derived from it.

## 4. Human Phenotype Ontology
- URLs: https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/{hp.obo,hp.json,genes_to_phenotype.txt,phenotype.hpoa};
  license page https://human-phenotype-ontology.github.io/license.html (the hp.obo header points to
  https://hpo.jax.org/app/license, a JavaScript app that could not be rendered).
- Version: release v2026-09-01 (published 2026-09-03); phenotype.hpoa `#version: 2026-09-02`.
- Terms (verbatim): "The HPO vocabularies, annotation files, tools and documentation are freely available." Conditions:
  "That the Human Phenotype Ontology Consortium is acknowledged and cited properly. That any HPO Consortium file(s)
  displayed publicly include the date(s) and/or version number(s) of the relevant HPO file(s). That neither the
  content of the HPO file(s) nor the logical relationships embedded within the HPO file(s) be altered in any way."
  Services and products "have to display a short acknowledgement statement, that makes clear that the
  service/product is using HPO." Statement: "This service/product is using the Human Phenotype Ontology (version
  information). Find out more at http://www.human-phenotype-ontology.org."
- Citation: Gargano MA, et al. *The Human Phenotype Ontology in 2024: phenotypes around the world*, Nucleic Acids Res
  52(D1):D1333-D1346 (2024), doi:10.1093/nar/gkad1005.
- UNVERIFIED: phenotype.hpoa includes OMIM- and Orphanet-derived disease annotations whose upstream terms (OMIM,
  Orphadata) were not read.
- Bundled derivatives (reformatted, content and relationships unchanged): `assets/hpo_terms.json.gz` (id, label,
  synonyms, parents from hp.obo), `assets/hpo_gene.tsv.gz` (gene, hpo_id from genes_to_phenotype.txt),
  `assets/hpo_gene_disease.tsv.gz`, `assets/hpo_disease.tsv.gz` (disease_id, name, hpo_id, frequency from
  phenotype.hpoa, aspect P, NOT rows dropped), `assets/hpo_alt_ids.json.gz` (alternative id map). HPO release
  v2026-09-01 / hpoa 2026-09-02 applies to all of them.

## 5. MANE (Matched Annotation from NCBI and EMBL-EBI)
- URLs: https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/ (`MANE.GRCh38.v1.5.summary.txt.gz`,
  `MANE.GRCh38.v1.5.ensembl_genomic.gtf.gz`).
- Version: MANE v1.5 (files dated 2025-12-04).
- Terms: the MANE pages state no license sentence and link to NCBI web policies (public domain, see ClinVar above);
  the Ensembl-side annotation falls under Ensembl terms (item 6). The license is therefore inferred, not quoted.
- Citation: Morales J, et al. *A joint NCBI and EMBL-EBI transcript set for clinical genomics and research*, Nature
  604(7905):310-315 (2022), doi:10.1038/s41586-022-04558-8.
- Bundled derivatives: `assets/panel_regions.tsv` (gene spans +/- 10 kb) and `assets/mane_features.tsv.gz`
  (exon/CDS/UTR/codon features of the 58 MANE Select transcripts).

## 6. Ensembl (REST API and VEP)
- URLs: https://rest.ensembl.org/ ; legal: https://www.ensembl.org/info/about/legal/disclaimer.html and
  https://www.ensembl.org/info/about/legal/code_licence.html.
- Version: Ensembl release 116 (June 2026).
- Terms (verbatim): "Ensembl imposes no restrictions on access to, or use of, the data provided and the software used
  to analyse and present it. Ensembl data generated by members of the project are available without restriction.
  Ensembl code written by members of the project is provided under the Apache 2.0 licence." Some included data and
  software "may be subject to third-party constraints".
- Citation: Dyer SC, et al. *Ensembl 2025*, Nucleic Acids Res 53(D1):D948-D957 (2025), doi:10.1093/nar/gkae1071, plus the
  release number; for VEP: McLaren W, et al. *The Ensembl Variant Effect Predictor*, Genome Biology 17:122 (2016),
  doi:10.1186/s13059-016-0974-4.
- UNVERIFIED: the REST rate limit (about 15 requests/s) comes from a 2014 wiki page; honour `X-RateLimit` headers and
  `Retry-After`.

## 7. Genomics England PanelApp
- URL: https://panelapp.genomicsengland.co.uk/api/v1/panels/402/ (panel 402, "Early onset or syndromic epilepsy",
  v9.100 on 2026-11-11). We take only the gene list (58 green genes chosen from it; see `docs/research/03-data.md`).
- Terms (PanelApp Terms of Use, December 2019, verbatim): 1.1 "You agree not to use PanelApp for any commercial
  purposes (including any commercial research), or for diagnostic use, medical decision-making or providing a
  healthcare service (whether or not carried out on a commercial basis), unless you have entered into a separate
  agreement with GEL for such use of PanelApp." 1.4 "Our status (and that of any identified contributors) as the
  authors of PanelApp and any content on it must always be acknowledged." OMIM- and Orphanet-derived content carries
  additional terms (sections 6 and 7).
- Citation: Martin AR, et al. *PanelApp crowdsources expert knowledge to establish consensus diagnostic gene panels*,
  Nat Genet (2019), doi:10.1038/s41588-019-0528-2; give the panel name and version.

## 8. AlphaGenome (Google DeepMind): usage terms
- URLs: https://github.com/google-deepmind/alphagenome ; model terms
  https://storage.googleapis.com/alphagenome/terms/AlphaGenome-Model-Terms-of-Use.pdf (last modified Dec 10, 2025).
- Version: GitHub release v2.0.0 (2026-11-11).
- **Usage terms (this is the single place the project states them):** AlphaGenome API output is for **non-commercial
  research use only**. Repository README: "AlphaGenome API is subject to the AlphaGenome Terms of Service. Other than
  as expressly provided in the AlphaGenome Terms of Service ..., outputs generated by AlphaGenome and other information
  provided in AlphaGenome Atlas are for non-commercial use only and should not be used for the training of other
  machine learning models." "The API is offered free of charge for non-commercial use." The model-parameters terms
  limit use to, or on behalf of, non-commercial organizations (universities, non-profits, research institutes,
  educational, journalism and government bodies) and forbid training other models on outputs. Published outputs need
  clear notice of any modifications.
- Citation: Avsec Z, et al. *Advancing regulatory variant effect prediction with AlphaGenome*, Nature 649:1206-1218
  (2026), doi:10.1038/s41586-025-10014-0. For Atlas scores also cite the AlphaGenome Atlas preprint listed in the
  repository README (doi:10.64898/2026.09.16.26363192, not independently verified).
- UNVERIFIED: the API Terms of Service and Output Terms pages are JavaScript apps and could not be read; the quoted
  text is from the README and the model-terms PDF. Code in the repo is Apache 2.0, docs CC BY 4.0.

## 9. Gemini API (Gemini 4 Carbon, Neon, Hydrogen and Gemini Decision 1)
- URL: https://aistudio.google.com/docs/terms (Gemini API Additional Terms of Service, effective March 23, 2026) and
  the Google APIs Terms of Service.
- Terms: contractual terms, not an open license. Paid Services: "Google doesn't use your prompts ... or responses to
  improve our products"; prompts and responses are logged for a limited time "solely for detecting and preventing
  violations of the Prohibited Use Policy". Unpaid Services: content may be used to improve Google products and
  human reviewers may read it. A key counts as a Paid Service only through a Cloud project with active billing. We use
  the hackathon's temporary paid-tier project. Models: gemini-4-carbon, gemini-4-neon, gemini-4-hydrogen,
  gemini-decision-1.
- Attribution: none required. Gemini 4 model-specific terms were not read (UNVERIFIED).

## 10. myvariant.info (fallback only, currently unused)
- URL: https://myvariant.info/terms/ (terms last updated Jun 14 2023): TSRI authorizes access and use under its
  conditions, and copies must keep copyright notices; data are provided "AS-IS". Underlying databases keep their own
  licenses.

## Bundled tables in `assets/` and their sources

| File | Owner slice | Derived from | License basis |
|---|---|---|---|
| `hpo_terms.json.gz`, `hpo_gene.tsv.gz`, `hpo_gene_disease.tsv.gz`, `hpo_disease.tsv.gz`, `hpo_alt_ids.json.gz` | A2 | HPO v2026-09-01 (items above) | HPO license (4) |
| `clinvar_panel.tsv.gz` | A2 | ClinVar weekly VCF 2026-11-15 | NCBI public domain (3) |
| `panel_regions.tsv`, `mane_features.tsv.gz` | A1 | MANE v1.5 summary + Ensembl GTF, PanelApp gene list | MANE/NCBI/Ensembl (5, 6), PanelApp (7) |
| `suspects_<sample>.json.gz` | A1 | 1000 Genomes NYGC 30x (NA12878), gnomAD v4.1 AF, MANE-based annotation | (1), (2) |
| `clinvar_candidates.json.gz`, `splits.json`, truth files | A3 | ClinVar (3), HPO annotations (4) | (3), (4) |
| `letters/*.pdf` | A3 | synthetic referral letters written by Gemini 4 Hydrogen from HPO terms; no real patients | Gemini terms (9) |

Slices A1, A3 and A4 send additions to this table through their `docs/status_a/*.md` files; A2 merges them here.
