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
| error | 4 |

## 0a7d9e2962b9d5e3: CHD2 chr15-92955513-G-A (splice)

- condition: Develomental and epileptic encephalopathy 94
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: scanned

## acd918b94301822f: TSC2 chr16-2056072-G-A (intron)

- condition: Tuberous sclerosis-2
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: scanned

## c72bc2c5ca63f42b: KCNQ2 chr20-63428365-A-C (splice)

- condition: Seizures, benign familial neonatal, 1
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: scanned

## f6ce33e90a7522d3: SCN1A chr2-166056512-T-G (intron)

- condition: Epileptic encephalopathy, early infantile, 6 (Dravet syndrome)
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: scanned
