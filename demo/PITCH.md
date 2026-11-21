# GeneSleuth live pitch (3 minutes + 2 minutes of Q&A)

The live run now takes about 2 to 2.7 minutes. So the judge picks, you press Investigate immediately, and you narrate the run as it streams. Do not wait for the run before you start talking. Have a recorded run ready in case the venue connection fails, and label it "recorded run".

## 0:00–0:20 · The wrong tissue

“A child with severe epilepsy had genome sequencing and two rounds of blood RNA testing and still had no answer. The clue was a deep intronic change in DNM1 near a brain-specific exon. The blood tests looked in a tissue where that exon barely shows up. A model let researchers look in the right one.” [Source, Fig. 3](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphagenome-atlas-a-predictive-map-of-every-possible-dna-letter-change-in-the-human-genome/alphagenome-atlas.pdf)

Say clearly: DNM1 is the story, not our proof.

## 0:20–0:40 · The judge picks, and we start

“Pick any variant, or press Random. We plant that real disease variant into a real genome, and the investigator gets a referral letter, sometimes a scan, plus a list of about 280 rare variants. The answer stays on the server.”

Press **Investigate** the moment the case loads. Point to the letter and to the real funnel counts (about 12,900 variants in the epilepsy genes, 282 suspects).

## 0:40–2:30 · Watch the investigation (narrate while it runs)

“Carbon reads the letter and turns it into phenotypes and a plan. Decision 1 triages all 282 suspects in about two seconds. Neon chooses which variants and which tissues deserve a live AlphaGenome call. Hydrogen condenses each raw AlphaGenome output. Every claim must cite a real tool result, and a second Decision 1 pass checks the claims against that evidence.”

Point to the AlphaGenome-calls counter and to one real tool call. Open a real checker rejection if one appears and read the reason; if none appears, open a supported claim and its cited result. Do not mention Managed Agents: the submitted run uses the local Neon loop.

“AlphaGenome scores one variant in one tissue per call. Choosing which of 282 variants to check, and where, is the hard part.”

## 2:30–2:50 · Reveal and review

Press **Reveal** and read the actual rank, including a miss if the variant fell outside the top 10. Point to the reference and alternate tracks in brain and in blood. Show Accept, Reject and “Look again”: the geneticist stays in control and can send the agent back to a specific tissue.

## 2:50–3:00 · The honest proof

“On a held-out test of twenty cases, our agent matched the best simple baselines, AlphaGenome alone and a fixed recipe, but did not beat them. With a longer time budget it ranked the hidden variant in the top five in 85% of cases. Before a late fix, nine of twenty runs did not finish at demo speed; after it, four live runs all finished. What GeneSleuth adds is a checked evidence trail for every claim. The full numbers and failures are in the repo.”

## Q&A

| Question | Answer |
| --- | --- |
| Isn't this just AlphaGenome? | On our spike-in test AlphaGenome alone is a strong baseline (80% in the top five, against 85% for the full agent), and we say so. GeneSleuth adds phenotype from the letter, a call budget, tissue choice and a checker that rejects unsupported claims. We have not shown it ranks better. |
| Does it beat the baselines? | No. It matches them. First run: 55% in the top five, because nine of twenty runs hit the demo time limit. After we reran only those nine with a longer budget (5 to 6 minutes each, not demo speed): 85% in the top five and 90% in the top ten, the same as the fixed recipe and about the same as Gemini with no tools. The test is also easy: the planted variants are mostly splice or non-coding and the background has almost none. Twenty cases is small and the intervals overlap. |
| Could Gemini have memorized ClinVar? | ClinVar lookup is off during every run and the answer key stays server-side. Pretrained knowledge can still leak in, which is why DNM1 is never in the test set. Gemini with no tools reached 85%, so we think the letter plus a 58-gene panel nearly identifies the gene. |
| Why should a geneticist trust it? | Every claim cites a tool result and passes a checker. The reviewer accepts or rejects each candidate, can send the agent back to a tissue, and exports the evidence. |
| What if the cause isn't in the panel? | It cannot rank a variant that never reached the candidate list. Two named cases we wanted to test (MFSD8, PLA2G6) are outside our 58 genes, so they are untested. |
| What did you build today? | All code and data files in the repo, built on Nov 21. The research briefs are planning documents from Nov 19. |
