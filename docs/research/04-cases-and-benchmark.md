# 04 — Demo cases and benchmark protocol (research only, no project code)

Researched 2026-11-19. Every variant below was copied from the source text. Anything I could not confirm is marked **UNVERIFIED**. GeneSleuth is a research tool for geneticists. It is not medical advice.

---

## Best demo case: DNM1 deep-intronic variant (AlphaGenome Atlas / GREGoR, Broad)

**Pick #1: DNM1 NM_004408.4:c.1335+1605G>A, chr9:128225994:G>A, de novo, heterozygous, epileptic encephalopathy.**

Why this one:
- **It is the case from the DeepMind materials.** The AlphaGenome Atlas blog (Sep 8 2026) credits Laura Covill and Anne O'Donnell-Luria (Broad) and GREGoR with finding a DNM1 variant that "created an incorrect splice site… abnormal extension of the resulting protein". https://deepmind.google/blog/alphagenome-atlas-a-predictive-map-of-every-possible-dna-letter-change-in-the-human-genome/
- **Exact variant published.** Atlas preprint (medRxiv, posted 2026-09-20): "the top ranked variant by AVI was a heterozygous noncoding VUS in intron 10 of DNM1 (chr9:128225994:G>A, HGVS: NM_004408.4:c.1335+1605G>A)… creates a brain-specific cryptic splice acceptor site resulting in a 13 amino acid (aa) in-frame extension of exon 10a". https://www.medrxiv.org/content/10.64898/2026.09.16.26363192v1.full
- **The story explains itself to non-biologists.** Exon 10a appears only in brain transcripts. The paper says: "Predictions in the 'venous blood' biosample showed negligible expression of exon 10a, explaining why previous RNA-seq from blood draws were inconclusive." So the family had two rounds of blood RNA-seq that came back ambiguous, because the defect only shows up in neurons. AlphaGenome's predictions for the "glutamatergic neuron" biosample point straight at it, and 69% of its AVI PHRED score of 24.7 is attributed to splicing. Pitch line: *"the test looked in the wrong tissue; the model looked in the right one."*
- **It was validated.** Minigene reporter screens across several cell lines, plus two other known nearby intronic DNM1 variants (15-aa and 2-aa extensions) that the model also reproduces. Those make good extra test cases.

Caveats to state honestly:
- **The same variant was published earlier**, in Nguyen et al., *Neurology* 106:e214645 (published online 2026-02-13), participant R02: "a male infant who presented with an unclassified DEE with generalized and focal seizures, hypotonia, and global developmental delay… de novo heterozygous noncoding VUS in intron 10 of DNM1 (NM_004408.4:c.1335+1605G>A)". In the brain transcript this is NM_001288739.2:c.1197-41G>A. Seizure onset was at 115 days. It was reclassified to likely pathogenic after fibroblast cDNA work. https://pmc.ncbi.nlm.nih.gov/articles/PMC12938226/ . I could not tell whether R02 and the GREGoR proband RGP_2167 are the same child (**UNVERIFIED**). A YouTube short calls the patient "her", which conflicts with R02 being male, so don't use that detail on stage.
- **Leakage risk.** It appeared Feb 2026 and again in the high-profile Atlas release, so Gemini 4 may have memorized it. Treat DNM1 as the *narrative* case, not proof. Use the MFSD8 case below as the unrehearsed holdout.
- **SpliceAI also flagged it** (Nguyen: higher SpliceAI score than the canonical site). Don't claim only AlphaGenome could find it. The defensible claim is that AlphaGenome adds the tissue specificity that explains why blood RNA-seq missed it.
- **Years to diagnosis are not stated** in either paper (**UNVERIFIED**). Nguyen gives a median of 468 days from clinical genome report to reanalysis across the cohort. Say "remained unsolved after clinical genome sequencing and two RNA-seq attempts" and nothing more.
- Reference build: the preprint's verbatim text gives chr9:128225994 with no build. It is presumably GRCh38, since AlphaGenome uses hg38. Confirm with VariantValidator before demo day.

---

## Case table

| # | Case | Date | Gene / variant (as published) | Phenotype → HPO (verify IDs in the HPO browser) | Time to diagnosis | OK to reference? |
|---|---|---|---|---|---|---|
| 1 | **DNM1 DEE**, GREGoR/Broad RGP_2167 (Atlas preprint) and Nguyen et al. *Neurology* R02 | Atlas: 2026-09-20 preprint. Nguyen: 2026-02-13 | DNM1 NM_004408.4:c.1335+1605G>A, chr9:128225994:G>A (build not stated, likely GRCh38), het, de novo | Epileptic encephalopathy HP:0200134; Global developmental delay HP:0001263; Hypotonia HP:0001252; Focal-onset seizure HP:0007359; Generalized-onset seizure HP:0002197 | Not stated. Unsolved after clinical rGS plus 2× blood RNA-seq | Yes: published, de-identified, IRB stated |
| 2 | **PLA2G6 neurodegeneration (PLAN)**, two siblings, Colombia/UCSB, **solved by AlphaGenome** | 2026-06-18 (medRxiv) | Compound het: NM_003560.4:c.2132C>G p.(Pro711Arg) (maternal) + **NM_003560.4:c.2034+355G>A, chr22:38115172:C>T, rs147795054** (paternal, deep intronic, 160-bp cryptic exon) | Parkinsonism HP:0001300; Visual hallucinations HP:0002367; Disinhibition HP:0000734; Abnormality of the autonomic nervous system HP:0002270 | **"nearly two decades after the proband's symptom onset"**. Exome, genome, MLPA and long-read all failed. One sibling had died 3 years earlier | Yes (preprint, CC BY 4.0). These are **adults**, so it is not the pediatric centerpiece |
| 3 | **MFSD8 / CLN7 Batten disease**, girl, Moscow | **2026-10-20** (*Front. Genet.* 17:1980180) | MFSD8 NM_001371596.2:c.999-556C>G, homozygous, 98-nt pseudoexon (pseudoexon chr4:127,922,520–127,922,617; the variant's genomic coordinate is not given, so derive it with VariantValidator) | Developmental regression HP:0002376; Atonic seizure HP:0010819; Myoclonic seizure HP:0032794; Cerebellar ataxia HP:0001251; Intention tremor HP:0002080; Cerebellar atrophy HP:0001272; Cerebral atrophy HP:0002059 | Symptoms from about 4 y, seizures at 4 y 10 mo, still progressing at 8 y 2 mo. WES and metabolic/enzyme tests were unremarkable before trio WGS. Exact time to diagnosis not stated | Yes: published, de-identified. **Best leakage-safe holdout** (published after any plausible Gemini 4 cutoff) |
| 4 (extra test cases) | Other DNM1 exon-10a variants: NM_001288739.2:c.1197-8G>A (recurrent, in DEE) and the 15-aa / 2-aa extension variants in Atlas fig. S9B | 2023 onward | See Atlas refs 38–39 and Nguyen refs 25–26 | DEE | n/a | Yes. Likely memorized, so use as positive controls only |

Sources: #2 https://www.medrxiv.org/content/10.64898/2026.06.10.26355004v1.full. In that study AlphaGenome scored 91 shared non-coding variants within 1 Mb of PLA2G6. The causal one "was a clear outlier… the only variant with scores above 2, with a maximum score of 8.26". SpliceAI acceptor gain was 0.95 but "tissue-agnostic". #3 https://pmc.ncbi.nlm.nih.gov/articles/PMC13727524/ (SpliceAI acceptor 0.73 / donor 0.67, 84% aberrant transcript in fibroblasts).

**Warning about the PLA2G6 case:** the causal allele has an rsID, and the authors note that being homozygous for it "unlikely necessarily results in disease". An aggressive allele-frequency filter could remove it. That makes it a good "where it fails" example.

---

## Benchmark design notes

### How the field evaluates variant prioritization
- **Metric:** top-1 / top-3 / top-5 / top-10 recall of the causal variant (or gene) among all candidates in the patient, plus the median rank. Atlas uses cumulative recall at top-K: on 112 P/LP variants from GREGoR solved cases ranked against each patient's own background variants, **AVI 29.5% vs CADD v1.7 12.5% at top 50**. After a gnomAD AF < 0.001 filter (105 variants), that rises to **74.3% vs 61%**. (Atlas preprint, above.)
- **Spike-in protocol:** Genomiser seeded 453 curated non-coding Mendelian variants into 1,092 genomes from 1000 Genomes, giving 10,419 simulated genomes with HPO profiles taken from the disease annotation. It ranked the causal variant **#1 in 77%** with full phenotypes and **68%** with clinically realistic phenotypes. Phen-Gen managed 19% / 14%. https://pubmed.ncbi.nlm.nih.gov/27569544 ; https://www.genomeweb.com/informatics/new-computational-tool-improves-id-non-coding-pathogenic-variants-mendelian-disorders . JAX notes that 77% "won't happen in the real world", because every simulated genome had a non-coding answer.
- **Phenotype-only baselines:** LIRICAL put the correct diagnosis in the top 3 in 92.9% of 384 case reports. https://pubmed.ncbi.nlm.nih.gov/32755546/ . Exomiser on 4,877 diagnosed 100kGP cases: 82.6% / 91.3% / 93.6% at top-1 / 3 / 10. LLMs without tools: the best (o1-preview) reached 36.8% top-10 on 5,213 cases, short of traditional tools. https://pmc.ncbi.nlm.nih.gov/articles/PMC11302616/
- **LLM-on-top-of-ranker:** aiDIVA uses GPT-4o to re-rank the top 10. It reached 97.4% top-3 on cases with ClinVar/HGMD evidence and 93.3% on a post-training cohort whose variants were absent from ClinVar/HGMD. Without any ClinVar/HGMD features it got 83.9%. Re-asking the identical prompt changed answers in 27% of failing cases. https://www.nature.com/articles/s41525-026-00611-x

### Known pitfalls
1. **Memorization and leakage.** Published cases, including both 2026 DNM1 papers, may be in Gemini's training data. Its "reasoning" may just be recall.
2. **Circularity.** Benchmarks often label with ClinVar P/LP and then let the tool use ClinVar features. Atlas's GREGoR labels are ClinVar submissions, so don't let the agent query ClinVar on benchmark cases. aiDIVA's drop from 93.3% to 83.9% without ClinVar shows how big this effect is.
3. **Phenotype noise.** Simulated HPO sets are cleaner than real ones (Genomiser fell from 77% to 68% with realistic phenotypes). Add imprecision: drop terms, replace terms with their parents, add 1–2 random terms.
4. **Tool misconfiguration.** The AI-MARRVEL paper reported DDD top-1 of about 15% for Exomiser and 30% for LIRICAL. Smedley et al. rebutted that the same versions get 62% and 47% when configured correctly. https://zenodo.org/records/12754888/files/NEJM-AI-Response.pdf (summary: https://pmc.ncbi.nlm.nih.gov/articles/PMC11221788/). Report your baseline settings openly, or judges won't trust your numbers.
5. **Spike-in realism.** Spiked variants are perfectly called. Real data has calling errors, indels and phasing problems. The Atlas excluded SNV-only models from its indel-inclusive comparison.

### Recommended protocol (about 60 cases, doable in 6.5 h)
**Case set (n ≈ 60):**
- 40 spike-in cases: ClinVar P/LP **non-coding or splice** SNVs (intronic more than 50 bp from the exon, UTR, promoter) in OMIM disease genes. Prefer ClinVar submissions dated after a chosen cutoff, such as 2026-06. Spike each into the same 1000 Genomes sample (for example NA12878, GRCh38).
- To keep run time manageable, restrict candidates to rare variants (AF < 0.001) within ±50 kb of the 500 genes nearest the HPO match. State this restriction openly.
- HPO terms: take 5 terms per case from the disease's HPO annotations, then add noise (drop 1, replace 1 with its parent, add 1 decoy).
- 15 spike-in **negative controls**: a benign ClinVar non-coding variant with the same HPO profile. The right answer is "no confident candidate".
- 5 real published cases from the table above (DNM1, PLA2G6, MFSD8, plus the two DNM1 extension variants).

**Arms (same candidate list for every arm):**
- (a) **AlphaGenome-only:** rank by AlphaGenome / AVI score. No phenotype, no LLM.
- (b) **Gemini without tools:** give it the HPO terms and the candidate list (variant strings only) and ask for a top-10 ranking.
- (c) **Full agent:** Gemini + AlphaGenome tissue-specific scoring + an HPO-to-gene step. ClinVar lookup must be **disabled on benchmark cases**.
- Optional: (d) SpliceAI-only, because two of the three real cases were also found by SpliceAI.

**Leakage control:**
- Compare spike-in cases with variants published **before** the model cutoff against those published **after** it.
- **Coordinate-shuffle control:** move the true variant to a matched but uninformative intronic position in the same gene. If arm (b) still ranks the gene first, it is recalling the gene from the phenotype, not reading the variant.
- Ask arm (b) to name the publication for each variant. A correct citation means memorization.

**Report:** top-1 / 5 / 10 recall with 95% binomial CIs (with n = 40, the CI is about ±15%, so say that), the negative-control false-confident rate, and the run-to-run variance from 3 repeats of arm (c). Pre-register this file before running.

### Pre-registered "where it fails" categories (most likely 3)
1. **Tissue mismatch / wrong biosample.** Effects that appear only in brain or some other tissue are missed if the agent scores the wrong tissue. DNM1 is the example: it is negligible in blood.
2. **Non-SNV or complex alleles.** Structural variants, repeat expansions, mosaicism and indels are missed. 5 of the 10 Nguyen reanalysis findings were CNV/SV/STR/mosaic types.
3. **Recessive second hits and common-ish alleles.** One allele is found, but the second (deep-intronic, with an rsID and nonzero AF) is filtered out or under-ranked. PLA2G6 is the example. A related failure: the gene is right because of phenotype recall, but the variant is wrong.
