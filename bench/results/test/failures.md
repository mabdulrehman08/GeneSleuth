# Failures of the full agent

Every full-mode case whose hidden variant did not reach the top 10, with one pre-registered category (rules in `bench/report.py:classify_failure`). Categories are assigned by code from the saved tool calls, not by reading the outcome and choosing a story.

| category | count |
|---|---|
| never_inspected | 0 |
| wrong_tissue | 0 |
| weak_alphagenome_effect | 0 |
| phenotype_mismatch | 0 |
| outranked_by_coding | 0 |
| checker_rejected_true_claim | 0 |
| unscorable_variant_type | 0 |
| missed_second_hit_or_common_allele | 0 |
| error | 1 |
| unclassified | 1 |

## bf4c21599e9b2961: CACNA1A chr19-13228797-T-C (intron)

- condition: Epileptic encephalopathy, early infantile, 42
- hidden variant rank: not in ranked list
- category: **unclassified**
- agent looked at the hidden variant: yes (2 tool calls)
- tissues used in the run: UBERON:0000955
- evidence: `{"n_calls_on_hidden": 2, "tissues": []}`
- agent top 3: CDKL5 chrX-18518389-T-TC (intron); STXBP1 chr9-127623001-C-T (intron); GNAO1 chr16-56195414-T-G (intron)
- letter: clean

## ddc4a709da29b72a: POLG chr15-89326739-C-T (splice)

- condition: Mitochondrial DNA depletion syndrome 4A (Alpers type)
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean
