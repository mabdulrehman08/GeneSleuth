# 01 — AlphaGenome API: GO / NO-GO for GeneSleuth

_Researched 2026-11-19. Docs version observed: `alphagenome` v2.0.0 (released 2026-11-11)._

## Verdict: GO-WITH-CAVEATS

The API fits a 6.5-hour build. The key is free and self-serve for non-commercial use, and the package is `pip install alphagenome` with no GPU needed. `predict_variant` returns REF and ALT tracks, and the built-in `plot_components` (`OverlaidTracks`, `Sashimi`) draws the "gene breaking" visual in about 15 lines. The Atlas gives precomputed scores with batched lookups. There are three caveats:
1. **No published rate limits or latency.** Quotas "vary with demand", live predictions are batch size 1, one variant per request, and they suit "small-scale analyses".
2. **AlphaGenome 2 (AG2) scores one condition (tissue/cell type) per call.** 400 candidates × N tissues means 400·N calls, so the agent has to pick tissues. That suits the pitch.
3. **The Atlas is built on AlphaGenome 1 (AG1), not AG2.** It is a fast fallback, not an AG2 showcase.

Plan: pre-filter with the Atlas or AVI, use live AG2 calls for only about 10–30 top candidates, and cache everything.

## 1. Access and terms
- Self-serve API key creation at https://alphagenome.google/api ("create an API key below"). Free for non-commercial use. I found no documented approval queue, but check it hands-on.
- One key covers both the model and the Atlas: "Model predictions and Atlas queries both need a free AlphaGenome API key" (https://www.alphagenomedocs.com/installation.html).
- Terms: outputs and Atlas scores are **non-commercial research only**. They must not be used to train ML models or for clinical decision-making (https://www.alphagenomedocs.com/faqs.html, https://github.com/google-deepmind/alphagenome). Commercial use goes through Google Cloud Model Garden.
- **Pitch implication:** frame GeneSleuth as a research triage tool, not a diagnostic. Whether hackathon prize use counts as "non-commercial" is **unverified**. Skim https://alphagenome.google/terms.
- Env var: `ALPHA_GENOME_API_KEY`. `colab_utils.get_api_key()` reads it (installation page).

## 2. Package and core calls
- `pip install alphagenome`. Python ≥3.11, supports 3.14. Works on Linux, macOS and Windows (GitHub README, installation page).
- AG2: `from alphagenome.models.v2 import dna_client`. AG1: `from alphagenome.models.v1 import dna_client` (https://www.alphagenomedocs.com/user_guides/ag1_vs_ag2.html).
- `dna_model = dna_client.create(API_KEY)`.
- `genome.Variant(chromosome, position, reference_bases, alternate_bases)` uses a **1-based** position, which matches VCF. `genome.Interval` is 0-based half-open (FAQ).
- `interval = variant.reference_interval.resize(dna_client.SEQUENCE_LENGTH_1MB)`
- **REF vs ALT tracks:** `dna_model.predict_variant(interval=, variant=, requested_outputs=[dna_client.OutputType.RNA_SEQ], condition=)`. Then use `output.reference` / `output.alternate`, and `.filter_to_observed()`, `.filter_to_negative_strand()` (https://www.alphagenomedocs.com/getting_started.html).
- **Scoring:** `dna_model.score_variant(interval=, variant=, variant_scorers=[variant_scorers.RECOMMENDED_VARIANT_SCORERS['RNA_SEQ']], condition=)`, then `variant_scorers.tidy_scores([scores])` to get a DataFrame (getting started).
- **Batch:** `score_variants(intervals, variants, conditions=..., variant_scorers=..., max_workers=5)` and `predict_variants(...)`. These parallelise client-side (https://www.alphagenomedocs.com/api/generated/alphagenome.models.v2.dna_client.DnaClient.score_variants.html).
- Also available: `score_interval`, `score_ism_variants`, `predict_interval`, `predict_sequence` (https://www.alphagenomedocs.com/api/models_v2.html).
- AG2 returns `raw_score` only. There is **no `quantile_score`**, which AG1 has (ag1_vs_ag2 page). Cross-gene ranking needs our own normalisation, or AG1 quantiles.
- Indels are supported. Use `genome.normalize_variant()` to left-align them (FAQ).
- Splicing score recipe from the docs: (max|SPLICE_SITES| + max|SPLICE_SITE_USAGE| + max|SPLICE_JUNCTIONS|) / 5 (https://www.alphagenomedocs.com/colabs/v2/splicing_variant.html).

## 3. Modalities and tissues
- AG2 has 15 `OutputType`s (https://www.alphagenomedocs.com/exploring_model_metadata.html):
  - Expression and accessibility: RNA_SEQ (1 bp), CAGE, SC_GENE_EXPRESSION, SC_GENE_EXPRESSION_DENOISED, DNASE, ATAC, SC_ATAC.
  - Histone, TF and methylation: CHIP_HISTONE (128 bp), CHIP_TF (128 bp), METHYLATION.
  - Splicing: SPLICE_SITES, SPLICE_SITE_USAGE, SPLICE_JUNCTIONS (all 1 bp).
  - Other: CONTACT_MAPS (2048 bp), CELL_EMBEDDINGS.
- PROCAP was removed in AG2 (ag1_vs_ag2 page).
- Conditions are ontology CURIEs or composites like `UBERON:0000178_CL:0001054`. List them with `dna_model.supported_conditions()`. The "Choosing a condition" tutorial output shows **2,799** human conditions, including `CL:0000047` neural stem cell and `CL:0000100` motor neuron (https://www.alphagenomedocs.com/colabs/v2/choosing_a_condition.html). The 2,799 figure came from a page extraction, so re-confirm it.
- The AG2 blog mentions brain astrocytes as an enhancer-gene use case (https://deepmind.google/blog/alphagenome-2-deciphering-how-cells-read-dna-to-better-understand-disease/).
- **Unverified:** exact brain/cortex UBERON CURIEs in AG2, and which of them have *observed* (not imputed) RNA-seq and splicing tracks. Each track carries an `imputation_mode` of `observed`, `imputed_supported` or `imputed_exploratory` (FAQ). Prefer `observed` for the demo.
- AG1 metadata uses `UBERON:0002245` for GTEx "Brain – Cerebellar hemisphere" (exploring_model_metadata page).

## 4. Limits, build, latency, quotas
- Genome build: **hg38** (GRCh38.p13). mm10 is also supported. LiftOver hg19 VCFs (FAQ).
- Input lengths: 16,384, 131,072, 524,288 and 1,048,576 bp. 1 MB is recommended (FAQ).
- Quotas: "Query rates vary with demand: pre-computed Atlas lookups support higher query rates than live model predictions, which suit small-scale analyses rather than large, genome-wide analyses" (GitHub README).
- A community forum staff answer says quotas "are regularly changed", throttling shows up as `RESOURCE_EXHAUSTED`, the client retries with exponential backoff, and each request is up to 1 MB with batch size 1, one variant per request (https://www.alphagenomecommunity.com/t/what-are-the-alphagenome-api-limits/673).
- **No published numbers for latency per call or requests per minute.** Measure them yourselves.
- Expression conditioning is capped at 256 cells per call (models_v2 API page).

## 5. AlphaGenome Atlas
- Contents: precomputed effects for about **9 billion SNVs** (every possible single-letter change) (https://deepmind.google/blog/alphagenome-atlas-a-predictive-map-of-every-possible-dna-letter-change-in-the-human-genome/):
  - thousands of molecular-effect predictions per variant;
  - the **AVI score**, which combines AlphaGenome and AlphaMissense into one number;
  - SHAP-style feature attributions, e.g. "splicing";
  - more than 2,500 motifs.
- The whole dataset is about 1 PB.
- Demo-relevant precedent: AVI prioritised an overlooked **DNM1** splice-creating variant in epileptic encephalopathy (GREGoR and Broad). That fits the gene panel exactly (same blog).
- Access:
  - Web: https://alphagenome.google/atlas
  - Python: `from alphagenome.atlas import atlas`, then `atlas.create(api_key)` returns an `AtlasClient` with `query_variant`, `query_variants(variants, requested_scorers=, ontology_terms=, gene_ids=, gene_names=, max_workers=10)`, `query_interval(interval, requested_scorers=)` and `scorer_metadata()`. These return `{scorer: AnnData}` (https://www.alphagenomedocs.com/api/generated/alphagenome.atlas.atlas.AtlasClient.html, …query_variants.html).
  - Bulk downloads in Tabix format (https://deepmind.google.com/science/alphagenome/downloads):
    - AVI SNV scores: 88.5 GB, permissive commercial and non-commercial use.
    - AG1 merged splicing scores: 20.6 GB.
    - AVI feature importances: 283.9 GB.
    - AG2 predictions plus enhancer-gene links: 3.2 GB. These cover trait-associated variants per the AG2 blog, not all SNVs.
  - I found no BigQuery offering.
- **Important:** the downloadable Atlas and AVI files are labelled **AlphaGenome 1**. The Verge reports that AG2's compute demands made a genome-wide AG2 Atlas impractical (https://www.theverge.com/ai-artificial-intelligence/1031524/google-deepmind-alphagenome-2-genetic-ai-model).
- **Can it replace live calls?** For *scores*, yes: use `query_interval` over 50 gene regions, or Tabix-slice the AVI file. It has SNVs only, no indels. For *tracks* (the REF vs ALT visual), no: the Atlas stores scores, not tracks. The demo still needs live `predict_variant` calls, or tracks precomputed and cached on the day.

## 6. AlphaGenome 2 vs 1
- AG2 is **conditional**: one condition per call instead of all tissues at once. It supports `cell_conditioning=` from your own scRNA-seq (up to 256 cells) and cross-modality imputation. It was trained on more than 107M cell profiles (AG2 blog, ag1_vs_ag2 page).
- New outputs: SC_GENE_EXPRESSION(_DENOISED), SC_ATAC, METHYLATION, CELL_EMBEDDINGS.
- SPLICE_SITES is now condition-specific with 5 channels. CONTACT_MAPS values are not comparable to AG1.
- Metadata moved from `output_metadata()` to `supported_conditions()` plus `observed_metadata()`, with a `biosample_curie` column.
- AG1 remains available via `models.v1` and is the only way to "score across all tissues at once" (ag1_vs_ag2 page). For a quick all-tissue triage, AG1 needs fewer calls.

## 7. Plotting
- `from alphagenome.visualization import plot_components`.
- `plot_components.plot([...], interval=, annotations=[plot_components.VariantAnnotation([variant])])`.
- Track components: `OverlaidTracks(tdata={'REF':…, 'ALT':…}, colors=…)`, `Sashimi` (splice junction arcs), `TranscriptAnnotation`, `OverlaidGeneExpression`.
- Uses matplotlib (getting_started, splicing_variant tutorial, https://www.alphagenomedocs.com/colabs/v2/plotting_predictions.html).
- An exon-skipping Sashimi plot plus a REF/ALT RNA-seq overlay is the cheapest "wow".

## Things to test hands-on before Saturday (throwaway code only)
1. Create a key with a non-personal project and confirm it works instantly: run `len(dna_model.supported_conditions())`.
2. Time 10 sequential `score_variant` calls at 1 MB with the RNA_SEQ scorer in one brain condition. Then time `score_variants(..., max_workers=5)` and 10 to find where `RESOURCE_EXHAUSTED` starts.
3. Time one `predict_variant` with RNA_SEQ + SPLICE_JUNCTIONS + SPLICE_SITE_USAGE, and record the payload size and memory.
4. Filter `supported_conditions()` for brain, cortex, neuron and astrocyte terms. Note which have `observed` RNA_SEQ and splicing.
5. Time `AtlasClient.query_variants` for 400 SNVs. Also time `query_interval` over one gene, e.g. SCN1A. List `scorer_metadata()` names and find the AVI scorer name.
6. Reproduce the DNM1 splice variant from the Atlas paper as the demo anchor. Get the coordinates from the medRxiv preprint (doi:10.64898/2026.09.16.26363192).
7. Render the `Sashimi` + `OverlaidTracks` REF/ALT plot and export it as PNG for the UI.
8. Compare AG1 `quantile_score` against AG2 `raw_score` ranking on 20 known ClinVar-pathogenic epilepsy variants.
9. Decide the cache strategy: pickle or `np.savez_compressed` outputs keyed by (variant, condition, outputs), so the live demo replays even if quota throttles.
10. Read https://alphagenome.google/terms for any hackathon or prize wording.
