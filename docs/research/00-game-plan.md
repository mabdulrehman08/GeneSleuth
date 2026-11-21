# GeneSleuth: game plan (merged from prep briefs 01–04)

Event: **Sat Nov 21, 2026**, hacking 10:30–17:00. Verdict: **GO, with caveats.**

## Architecture (as validated by the research)

1. **Data funnel (deterministic code)**
   - Stream one 1000 Genomes GRCh38 sample, regions only, from the 58-gene epilepsy panel (±10 kb, about 9 Mb).
   - Plant a ClinVar variant.
   - Filter by gnomAD v4.1 allele frequency.
   - Score phenotype match with HPO.
   - Expected size: about 12–16k variants in the regions, falling to about 50–250 rare ones. *Measure the real numbers; don't quote "4M → 400" until measured.*
2. **Pre-rank with the AlphaGenome Atlas.** Use the AVI score and Atlas scores, which are cheap and allow higher query rates. The Atlas is built on AlphaGenome 1 and holds scores only.
3. **Gemini investigator in Managed Agents.**
   - Save an agent with one SKILL file per tool: AlphaGenome, gnomAD, HPO, ClinVar.
   - Each case gets a fresh sandbox, and the agent writes its own analysis code.
   - Carbon/Argon plans and ranks; Hydrogen does routine lookups.
   - Live AlphaGenome 2 calls go to only the top 10–30 candidates. Each call covers one tissue, and choosing the tissue is the agent's job.
4. **Evidence checker.** Our own code runs as a client-side `submit_report` function and rejects any claim that doesn't cite a tool-result ID. A pre-tool hook is a nice extra, but hooks fail open and don't fire on custom functions, so they can't be the only check.
5. **Visual.** `alphagenome.visualization`: the REF vs ALT RNA-seq overlay plus a Sashimi splice-junction plot, in the brain condition.

## Demo story
- **Anchor case:** DNM1 c.1335+1605G>A (chr9:128225994 G>A; *confirm the build with VariantValidator*).
  - It's a deep-intronic, brain-only exon 10a splice change.
  - Blood RNA tests missed it. **"The test looked in the wrong tissue; the model looked in the right one."**
  - It's likely memorized, so use it as the story, not as proof.
- **Unseen holdout:** MFSD8 c.999-556C>G (Oct 20 2026). The genomic coordinate needs deriving.
- **Honest-failure example:** PLA2G6 c.2034+355G>A. It's common enough that the frequency filter can drop it.
- **Live trick:** a judge picks from 169 deep non-coding ClinVar variants in the panel genes, and we plant it and find it.

## Benchmark
- **Pool:** about 1,390 splice/non-coding pathogenic/likely-pathogenic single-letter variants at ≥1 star in the 58 genes; the 169 deep non-coding ones are the showcase pool.
- **Arms:**
  - (a) Atlas/AlphaGenome score only
  - (b) Gemini, no tools
  - (c) full agent, with ClinVar lookup **off** for benchmark cases
  - optional (d) SpliceAI
- **Size:**
  - About 60 cases if run over several days: 40 spike-ins, 15 negative controls and 5 real cases.
  - On Saturday, Tier-1 billing (about $10 per 10 min, $0.70–3.25 per run) allows only **20–30 cases**. Report the 95% confidence intervals honestly.
- **Leakage controls:**
  - Compare ClinVar IDs from before vs after the cutoff (diff the monthly snapshots; there's no "date added" field).
  - Shuffle the coordinate within the same gene.
  - Ask the model to cite a publication; a correct citation means memorization.
- **Reference targets:**
  - Gemini alone will likely be weak (best LLM without tools: top-10 about 37%).
  - **The real bar is Atlas AVI**: top-50 29.5% → 74.3% after a frequency filter, on 112 GREGoR cases.
- **Pre-registered failure modes:**
  1. Wrong tissue
  2. Variant types we can't score (structural variants, repeat expansions, indels, mosaicism)
  3. Missed second hit in recessive disease

## Do now (blocking)
- [ ] Get an AlphaGenome API key at alphagenome.google/api. It's non-commercial, research-only and not for clinical use, so pitch it as **research triage**.
- [ ] Link billing on a dedicated AI Studio project; Argon/Carbon aren't on the free tier.
- [ ] Install bcftools and tabix (WSL2: `apt install bcftools tabix`). The Windows machine has neither.
- [ ] Look up Gemini 4's knowledge cutoff, which sets the leakage split.

## Throwaway checks before Saturday (practice only)
- Time 10 AlphaGenome 2 scoring calls and find where `RESOURCE_EXHAUSTED` starts.
- List the brain conditions and which have measured vs imputed data.
- Time an Atlas query for about 400 variants.
- Reproduce the DNM1 prediction and plot.
- Measure the cost and time of one roughly 15-tool-call Managed Agents run.
- Check NA12878 is in the 3,202-sample panel.

## Open risks
- AlphaGenome rate limits aren't published, so cache everything and keep a replay ready (and say so if it's used).
- The Gemini 4 knowledge cutoff is unknown.
- It's unconfirmed whether the agent config can set the thinking level.
- There are reports of Carbon streams coming back from a different model; log `modelVersion`.
- AlphaGenome's terms may restrict commercial use and prize use, so read them.
