# GeneSleuth

An AI detective that helps geneticists find the hidden cause of unsolved genetic disease.

A child with epileptic encephalopathy had two rounds of blood RNA sequencing with ambiguous results. A deep intronic DNM1 variant affected an exon used in brain-specific transcripts. AlphaGenome predicted an effect in glutamatergic neurons and little corresponding signal in venous blood. Splice predictors can flag a variant. The tissue comparison helps explain why the blood tests were inconclusive. This published case motivates GeneSleuth and is excluded from the evidence for generalization. [AlphaGenome Atlas paper, Fig. 3](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-atlas-a-predictive-map-of-every-possible-dna-letter-change-in-the-human-genome/alphagenome-atlas.pdf)

## The problem

Many families remain without a diagnosis after genetic testing. Protein-coding sequence accounts for roughly 2% of the genome, and the remaining sequence includes variants that can alter splicing and regulation. Finding a relevant variant takes more than looking for the largest predicted change. The candidate has to fit the patient's symptoms, the gene, and the tissue where the effect matters. [Genome Sequencing for Diagnosing Rare Diseases](https://doi.org/10.1056/NEJMoa2314761) · [AlphaGenome overview](https://deepmind.google/blog/alphagenome-ai-for-better-understanding-the-genome/)

## Built today at the Gemini 4 NYC Hackathon (Nov 21, 2026)

The Nov 19 research briefs were written before the event. Project code was written during the event. The project has three parts.

- Data preparation, public variant case construction and benchmark scoring.
- Referral extraction, candidate triage, tissue routing, adaptive tool calls and claim verification.
- A live browser investigation with PDF review, an evidence timeline, a tissue comparison, reveal, and Markdown export. See the [design](Design.md) for boundaries and [B2 status](STATUS_B2.md) for current verification.

## How it works

```mermaid
flowchart TD
    PDF["Referral PDF"] --> Carbon["Carbon phenotypes and plan"]
    Genome["Background genome"] --> Filter["Panel and rarity filters"]
    Carbon --> Triage["Decision 1 triage and routing"]
    Filter --> Triage
    Triage --> Neon["Neon investigation"]
    Neon --> AG["AlphaGenome by tissue"]
    AG --> Hydrogen["Hydrogen summaries"]
    Hydrogen --> Neon
    Neon --> Code["Citation and number checks"]
    Code --> Gate["Decision 1 claim checks"]
    Gate -->|Revise| Neon
    Gate -->|Supported| Review["Ranked evidence and reviewer decisions"]
```

| Component | Job |
| --- | --- |
| Decision 1 | Batches triage and tissue routing, then checks claims against their cited evidence. |
| Gemini 4 Neon | Investigates, chooses variant–tissue pairs, ranks candidates, and revises rejected claims. |
| Gemini 4 Carbon | Reads the referral PDF, extracts HPO phenotypes, and writes a hypothesis plan. |
| Gemini 4 Hydrogen | Summarizes AlphaGenome outputs in parallel worker calls. |
| Gemini Managed Agents | Provides the hosted sandbox when enabled and verified. The demo runtime comes from the active investigation trace. |
| AlphaGenome | Atlas (AG1) supplies precomputed AVI scores. Live calls supply tissue-specific effects and reference-versus-alternate tracks. |

## Isn't this just one AI reading AlphaGenome's output?

AlphaGenome scores a supplied variant–tissue pair. GeneSleuth chooses which pairs to test across the candidate list under a call budget. Tissue choice changes what the model can see. The ranking also uses phenotype fit, frequency, and variant context. A claim checker verifies the resulting statements against cited tool calls and exposes rejections for review. The benchmark tests each addition against simpler approaches.

## Evidence

The benchmark design places public ClinVar variants into a public 1000 Genomes background and describes the phenotype in a synthetic referral. The case builder keeps a separate answer key and disables ClinVar lookup during investigation. The five arms use the same candidate list. The report presents hit@1, hit@5, and hit@10 with 95% Wilson intervals, coding and non-coding subgroups, and failures by category. [Benchmark methodology and results](docs/BENCHMARK.md)

| Arm | Evidence used to rank |
| --- | --- |
| AlphaGenome Atlas (AG1) | Precomputed AVI score |
| AlphaGenome 2 | Live score in one fixed brain condition |
| Gemini-only | Referral phenotypes and suspect list |
| Fixed recipe | Fixed weights for phenotype fit, variant-effect score, consequence severity, and held-out gene-level ClinVar evidence |
| Full GeneSleuth | Decision 1 routing, adaptive Neon investigation, and checked evidence |

Measured test-set results and the chart are pending integration. The published DNM1 story is excluded from proof because it may be familiar to the model. MFSD8 c.999-556C>G is a recent published holdout candidate. Its eligibility depends on the confirmed coordinate and cutoff checks. The PLA2G6 c.2034+355G>A preprint illustrates a filter failure mode. The allele can be relatively common in one ancestry group and was implicated alongside a second allele, so a strict rarity filter can discard it. [MFSD8 report](https://doi.org/10.3389/fgene.2026.1980180) · [PLA2G6 preprint](https://doi.org/10.64898/2026.06.10.26355004)

## Run the demo

From the project root, with the data and investigator modules present:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
```

Set `GEMINI_API_KEY`, `ALPHA_GENOME_API_KEY`, and an absolute shared `GENESLEUTH_DATA_DIR` in `.env`. Set the tissue IDs to the values confirmed in the [probe report](probes/B/REPORT.md). Then run:

```sh
python scripts/data_setup.py --check-only
python -m scripts.demo_prewarm
python -m scripts.demo_check
python -m genesleuth.server.app
```

Visit [GeneSleuth locally](http://127.0.0.1:8000). Pick a case or use Random, open the referral, and click Investigate. After the shortlist arrives, inspect the citations, reveal the hidden variant, or review and export the evidence. Prewarm uses the shared background bundle and excludes all potential spike-in positions. If assets are missing, run the data setup script without `--check-only` to build them.

## Data sources and terms

| Source | Use and terms |
| --- | --- |
| 1000 Genomes / IGSR | Public NA12878 background from the NYGC high-coverage phased data. Reuse follows the IGSR statements and EMBL-EBI terms. [IGSR data and attribution](https://www.internationalgenome.org/data/) · [Byrska-Bishop et al.](https://doi.org/10.1016/j.cell.2022.08.004) |
| ClinVar | Public variant labels and truth for case construction. See NCBI's public-domain policy and submitter terms. [ClinVar use and attribution](https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/) · [Landrum et al.](https://doi.org/10.1093/nar/gkx1153) |
| gnomAD v4.1 | Primary population-frequency data are CC0 1.0. This tool includes data from the gnomAD v4.1 release. [gnomAD](https://gnomad.broadinstitute.org/) |
| Human Phenotype Ontology | Phenotype annotations and labels use release v2026-09-01 under the HPO license. [HPO](https://hpo.jax.org) · [HPO license](https://human-phenotype-ontology.github.io/license.html) |
| PanelApp and MANE | The epilepsy genes come from Genomics England PanelApp panel 402. Transcript annotations use MANE v1.5 and Ensembl. Source terms and citations are listed in the [data inventory](docs/DATA_SOURCES.md). |
| AlphaGenome and AlphaGenome Atlas | API outputs and Atlas scores are licensed for non-commercial research use and may not be used for clinical decisions. [AlphaGenome usage terms](https://google-deepmind-alphagenome.readthedocs-hosted.com/faqs.html#what-terms-of-use-apply-and-is-commercial-access-available) |

These data were generated at the New York Genome Center with funds provided by NHGRI Grant 3UM1HG008901-03S1. The data inventory lists the collection and version citations.

## Limitations

A candidate must survive the panel and frequency filters to be ranked. A synthetic referral can be cleaner than a real referral, and a planted single variant does not capture every inheritance pattern. Tissue models predict molecular effects with uneven tissue coverage. Claim verification tests consistency with the available evidence. Model outages, quota, and latency can limit how many candidates are scored.

## Team

Haider Gilani and Muhammad Abdulrehman.
