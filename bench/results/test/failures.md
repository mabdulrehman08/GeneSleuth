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
| error | 9 |

## 1ebf4e969dab180e: POLG chr15-89317539-G-C (splice)

- condition: Sensory ataxic neuropathy, dysarthria, and ophthalmoparesis
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean

## 2c822300822a142f: ALDH7A1 chr5-126568254-C-T (splice)

- condition: Epilepsy, pyridoxine-dependent
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean

## 641ef5ede9fac37f: TSC1 chr9-132912459-T-A (splice)

- condition: Tuberous sclerosis-1
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean

## 6a85ec2973fd5151: SCN1A chr2-166056406-C-G (splice)

- condition: Generalized epilepsy with febrile seizures plus, type 2
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean

## 945f8d0795a4f817: SCN1A chr2-166037876-C-T (coding)

- condition: Generalized epilepsy with febrile seizures plus, type 2
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean

## 97e7ac7c9f686dc7: DEPDC5 chr22-31754981-T-C (splice)

- condition: Familial focal epilepsy with variable foci
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean

## bf4c21599e9b2961: CACNA1A chr19-13228797-T-C (intron)

- condition: Epileptic encephalopathy, early infantile, 42
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
- letter: clean

## d8c693f1a18c9dcb: SLC6A1 chr3-11025543-T-C (coding)

- condition: Myoclonic-atonic epilepsy
- hidden variant rank: not in ranked list
- category: **error**
- agent looked at the hidden variant: no
- tissues used in the run: none
- evidence: `{"error": "The investigator did not return a fact-checked shortlist within its budget"}`
- agent top 3: none
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
