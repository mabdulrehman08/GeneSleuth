# GeneSleuth live pitch

## 0:00–0:20 · The wrong tissue

“A child with severe epilepsy went through genome sequencing and two rounds of blood RNA testing without a clear explanation. The clue was a deep intronic change in DNM1, near a brain-specific exon. The blood tests looked in a tissue where that exon barely showed up. A model let researchers look in a different tissue.” [Source, Fig. 3](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-atlas-a-predictive-map-of-every-possible-dna-letter-change-in-the-human-genome/alphagenome-atlas.pdf)

## 0:20–0:45 · Make it a case

“Pick any variant, or hit Random. GeneSleuth places a public disease-associated variant in a real 1000 Genomes background. The investigator gets a synthetic referral letter and the filtered variant list.”

Click Investigate as soon as the case loads. Point to the PDF and the actual funnel counts. Explain that the referral describes symptoms and the answer stays on the server until Reveal.

## 0:45–2:05 · Watch the investigation

“Carbon reads the referral as a PDF and turns symptoms into structured phenotypes and an investigation plan. Decision 1 screens the candidate list in one batch and suggests a tissue. Neon decides which variants and tissues to spend live AlphaGenome calls on. Hydrogen condenses the raw outputs in parallel.”

Show a real tool call and its effect on the call counter. Open an actual checker rejection if one appears and read the reason. If all claims pass, open a supported claim and point to its cited tool result. Describe Managed Agents as the hosted sandbox only if the active run used it.

“AlphaGenome predicts an effect for a variant and tissue we select. GeneSleuth makes those selections under a budget and combines them with phenotype fit and population frequency. A second Decision 1 pass checks each claim against its cited evidence.”

## 2:05–2:35 · Reveal and review

Use Reveal and read the actual rank, including a miss if the variant fell outside the shortlist. If the plot is ready, point out the reference and alternate tracks, then describe the difference actually shown in brain and blood.

Open one candidate’s evidence. Show Accept or Reject and the Look again control. Explain that a reviewer can ask a tissue-specific question in the same investigation and export accepted evidence with citations.

## 2:35–3:00 · What the benchmark says

Open the benchmark. State the test-set size and one observed difference against AlphaGenome Atlas (AG1), with uncertainty. If results are pending, say so. Present DNM1 as the motivating story and MFSD8 as a recent published holdout candidate. The PLA2G6 example illustrates how a rarity filter can discard a variant implicated in a compound-heterozygous case. [MFSD8 report](https://doi.org/10.3389/fgene.2026.1980180) · [PLA2G6 preprint](https://doi.org/10.64898/2026.06.10.26355004)

## Q&A

| Question | Answer |
| --- | --- |
| Isn't this just AlphaGenome? | Atlas AVI is a strong baseline. The full system can weigh phenotype and frequency, choose a smaller set of variant–tissue pairs to score live, and show which evidence supports each claim. The benchmark measures whether that adds value. |
| Could Gemini memorize ClinVar? | The lookup is disabled and the answer key is held server-side. Prior knowledge can still enter through pretrained models. Report only the cutoff split, publication check, and coordinate-shuffle controls the benchmark actually ran. |
| Why should a geneticist trust it? | The shortlist exposes tool-call citations and checker verdicts. Reviewers can inspect those predictions and the case context, change their decisions, and request another test. |
| What if the cause is outside the panel? | It cannot rank a variant that never reached the candidate list. Panel and frequency filter misses belong in the evaluation. |
