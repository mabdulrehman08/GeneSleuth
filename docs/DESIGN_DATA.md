# GeneSleuth data design (Agent A)

This is the data-side design document that `Design.md` links to. It describes how a benchmark or demo case is
made from public data, how the lookup tools work, and where every file lives. Licenses and attributions are in
[DATA_SOURCES.md](DATA_SOURCES.md); the benchmark protocol and results are in [BENCHMARK.md](BENCHMARK.md).
Status: v1 written from the module headers and status files at 13:50 ET; sections marked (pending) are filled in as the
other slices land their parts.

## 1. Idea in one paragraph
A case is a real 1000 Genomes genome (NA12878) with one real ClinVar pathogenic variant planted in it, plus a
synthetic referral letter written from the disease's HPO annotations. The agent receives the filtered "suspects" (the
sample's rare variants in 58 epilepsy genes plus the planted variant) and the letter, never the truth. Nothing in the
`Case` (field set, consequence vocabulary, ordering) reveals which suspect is planted, and per-variant ClinVar lookup is
switched off so the answer cannot be read back from ClinVar.

## 2. Data flow

```
PanelApp 402 gene list --> MANE v1.5 summary+GTF --> panel_regions.tsv, mane_features.tsv.gz      (slice A1)
1000G NYGC 30x (NA12878) --bcftools--> variants in panel regions --gnomAD AF filter--> suspects     (slice A1)
ClinVar VCF --> clinvar_panel.tsv.gz (all records in the panel regions)                              (slice A2)
HPO release --> hpo_terms / hpo_gene / hpo_disease / hpo_gene_disease tables                         (slice A2)
clinvar_panel + HPO --> candidates, splits (dev/test/demo), true phenotypes, letters (Hydrogen)      (slice A3)
build_case(option) = suspects + planted ClinVar variant + letter ; holdout_for(truth)                (slice A3)
lookups/api.py: region_context, population_frequency, clinvar_lookup(off), gene_phenotypes,
                phenotype_match, hpo_search                                                          (slice A2)
bench/: arms atlas_only, alphagenome_only, gemini_only, full, fixed_recipe -> metrics, report         (slice A4)
```

## 3. Where files live (read order: `ROOT/assets/` first, then `DATA_DIR/work`)

`assets/` is committed (gzipped tables, under 50 MB in total, never `.vcf.gz` or `.tbi`) so the other computer
runs without our `DATA_DIR`. `DATA_DIR` (gitignored, `GENESLEUTH_DATA_DIR`) holds raw downloads (`raw/`), derived
tables (`work/`) and API caches (`cache/`). `scripts/data_setup.py` (A3) checks `assets/` and rebuilds anything
missing by calling each owner's idempotent `scripts/data_*.py main()`.

| File | Written by | Format |
|---|---|---|
| `panel_regions.tsv` | A1 `scripts/data_panel.py` | `gene chrom start end strand tss ensembl_gene`, chr-prefixed GRCh38, 1-based inclusive, gene span +/- 10 kb |
| `mane_features.tsv.gz` | A1 | `gene transcript chrom start end strand feature exon_number` (exon, CDS, UTR, start/stop codon) |
| `suspects_<sample>.json(.gz)` | A1 | `{"sample_id", "funnel", "suspects": [Variant]}` (pending) |
| `hpo_terms.json(.gz)` | A2 `scripts/data_hpo.py` | `{hpo_id: {label, synonyms, parents}}` (19,894 terms) |
| `hpo_gene.tsv(.gz)` | A2 | `gene hpo_id` (273,933 unique pairs, 5,277 genes) |
| `hpo_gene_disease.tsv(.gz)` | A2 | `gene disease_id disease_name` |
| `hpo_disease.tsv(.gz)` | A2 | `disease_id disease_name hpo_id frequency` (aspect P, NOT rows dropped) |
| `hpo_alt_ids.json(.gz)` | A2 | alternative HPO id -> primary id |
| `clinvar_panel.tsv.gz` | A2 `scripts/data_clinvar_table.py` | `variant_id variation_id allele_id chrom pos ref alt clnsig review_status stars condition_names condition_dbs gene mc` (115,586 records) |
| `clinvar_candidates.json(.gz)`, `splits.json`, truth, `letters/*.pdf` | A3 | candidate pool, dev/test/demo split, true phenotypes, referral letters (pending) |
| `bench/results/<split>/<mode>/<case>.json` | A4 | `{result, truth, meta}` |

## 4. Case construction and leakage controls
- Background: one real sample (NA12878), only its non-reference variants in the 58 panel regions are kept. The rarity
  filter uses gnomAD v4.1 AF (missing counts as rare); the funnel counts reported are the measured ones (pending: A1 numbers).
- Planted variant: a ClinVar Pathogenic / Likely pathogenic SNV (1+ star, no conflicting classifications) in a panel
  gene, injected as heterozygous; the same field set and VEP/MANE consequence vocabulary as every other suspect.
- Letter: 5-8 HPO terms sampled by frequency from phenotype.hpoa (aspect P) for the linked disease, about 30% replaced
  by a parent term, 1-2 decoys; Gemini 4 Hydrogen writes the letter, which is regex-checked to contain no gene symbol,
  HGVS notation or condition name; part of the test letters are rendered as noisy scans (pending: A3 details).
- Holdout: `holdout_for(truth)` returns the planted variant id and its ClinVar ids. `clinvar_lookup` is OFF for every
  benchmark and demo case (returns `{"disabled": true, "note": "ClinVar lookup off to prevent leakage"}`); the
  holdout logic (hide the id, the ClinVar ids and any record at the same chrom+pos) stays behind `enabled=True` as a
  second guard, and the fixed recipe may only use the gene-level feature "gene has a P/LP record" computed with the
  holdout excluded (`lookups.clinvar.gene_has_plp_record`).
- Benchmark protocol, arms, splits, named cases and leakage controls: see BENCHMARK.md.

## 5. Lookup tools (`genesleuth/lookups/`)
Public interface `lookups/api.py` (signatures fixed with Agent B): every function returns a JSON-serialisable dict
(`hpo_search` returns a list), never raises (`{"error": ...}` on failure; `[{"error": ...}]` for `hpo_search`), is cached
on disk under `DATA_DIR/cache/lookups/`, and is routed to `lookups/fakes.py` when `FAKE_MODE=1` (development only).

| Tool | Implementation | Notes |
|---|---|---|
| `region_context(variant_id)` | `region.py`: MANE Select transcript geometry (exons, CDS, UTR) of the 58 genes; takes gene/region/consequence/distance_to_tss from A1's annotated suspects when the variant is one | classes coding, utr5, utr3, splice (intronic <= 8 bp from an exon edge), intron, promoter (<= 2 kb upstream), intergenic; also exon/intron number, strand, nearby panel genes |
| `population_frequency(variant_id)` | `popfreq.py`: gnomAD v4.1 GraphQL (`gnomad_r4`), genomes + exomes combined; falls back to the AF stored on the suspect, then "unavailable" | measured about 10 requests/min before HTTP 429, so calls are spaced 6.5 s apart and every answer (also "not observed") is cached |
| `clinvar_lookup(variant_id, holdout, enabled=False)` | `clinvar.py`: local panel table with holdout guards | disabled by default, see section 4 |
| `gene_phenotypes(gene)` | `phenotypes.py`: genes_to_phenotype terms + disease names from phenotype.hpoa | diseases and HPO terms with labels |
| `phenotype_match(gene, hpo_ids)` | `phenotypes.py`: each patient term and the gene's terms are expanded to themselves plus ancestors up to 2 levels; score = fraction of patient terms whose expanded set meets the gene's | returns the closest matched pair per term, unmatched terms, counts |
| `hpo_search(text, k)` | `phenotypes.py`: exact label, exact synonym, then token-overlap ranking | `matched_on` is label, synonym, token_overlap or synonym_overlap |

Known limits: `region_context` follows MANE Select only, so variants that ClinVar annotates on other isoforms or in
overlapping non-panel genes can get a different class; `phenotype_match` with 2 ancestor levels is generous for broad
terms (a seizure term matches most neurological genes), which is why the matched pairs and distances are returned.

## 6. Reproduce
```
python scripts/data_setup.py        # A3: checks assets/, rebuilds missing parts, smoke-tests build_case
python scripts/data_hpo.py          # HPO release + tables (+ assets/*.gz)
python scripts/data_clinvar_table.py  # ClinVar panel table (+ assets/clinvar_panel.tsv.gz)
FAKE_MODE=1 python -m pytest tests/test_lookups.py   # fakes; without FAKE_MODE the real tables are used
```

## 7. Honest limits of the data design
One background sample, heterozygous injection only, synthetic letters, small test set; the gnomAD API is rate limited
(frequencies for suspects are streamed in bulk by A1 rather than queried one by one); AlphaGenome output is for
non-commercial research use (DATA_SOURCES.md, item 8). (pending: final numbers from A1, A3 and A4.)
