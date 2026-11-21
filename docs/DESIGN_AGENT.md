# GeneSleuth agent core

Implementation contract for the agent and demo integration. Live provider behavior is tracked in [the API probe report](../probes/B/REPORT.md).

## Public entry points

- `investigate(case, holdout, mode="full", on_event=None, profile="bench")` is asynchronous and returns the shared `InvestigationResult`. A caller supplies a synchronous event callback. The case carries candidate variants and a referral PDF.
- `look_again(case, holdout, previous, request, on_event=None, profile="demo")` is asynchronous. It resumes the server-side Gemini interaction used by the previous result and rechecks any submitted claims. The API checks the case id and last completed result, then uses the retained interaction id and evidence ledger. Session state lives in memory in one application process. The caller should keep the previous result when continuation fails.
- `read_referral(pdf_path)` is synchronous and returns shared `Phenotype` objects. The full pipeline also uses a patient phenotype and hypothesis plan read in the same Carbon call.
- `score_variant(variant, tissue_ontology_id)`, `atlas_scores(variants)`, `list_tissues(query=None)` and `plot_variant(variant, tissue_ids, out_path)` are synchronous. Async callers run these in a worker thread.

## Evidence flow

The reviewer’s PDF stays separate from the holdout and case truth. Carbon reads the document and returns quotes, candidate HPO labels and hypotheses. Local HPO lookup selects labels and ids. The pipeline supplies the agent with candidate context and the normalized phenotypes. The case truth stays in the caller.

Atlas AVI, cached population frequency and the annotations give Decision 1 the evidence to triage and route the case. A live population lookup is reserved for an investigator tool call when there is no cached evidence. Confidence travels with each probability so Neon can take a second look at uncertain scores. AlphaGenome 2 supplies one tissue-specific result per requested variant and condition. A Hydrogen summary accompanies the structured result. The original data remains the authority for numeric checks.

Neon writes a shortlist through `submit_report`. Code checks that cited evidence exists, matches the variant and supports its quantities and tissue labels. Decision 1 then evaluates all remaining claims together. Rejected and uncertain claims can be revised twice. Claims that still lack support are dropped. The investigator can only complete through this gate. The retained tool ledger and verdicts let the UI show what happened.

## Baselines

All modes extract phenotypes through the same reader. Atlas-only ranks by AVI. AlphaGenome-only scores all candidates in the fixed brain condition and sorts by effect magnitude. Gemini-only ranks the full suspect list from the case data in one Neon call with no tools. The shared result schema enumerates those modes and the full investigation.

## Trace contract for the demo

| Event step | Data |
| --- | --- |
| `read_letter` | `phenotypes` |
| `plan` for Carbon | `likely_genes`, `mechanisms`, `tissues_to_test` |
| `plan` for Decision 1 | `n_suspects`, `elapsed_s`, `routed_tissue`, `route_confidence` |
| `tool`, `alphagenome` | `call_id`, `tool`, `args`, `artifact_path`, `n_tool_calls`, `n_alphagenome_calls`, `alphagenome_budget` |
| `check` per claim | `claim_id`, `variant_id`, `text`, `verdict`, `confidence`, `reason` |
| `check` for the batch | `n_checked`, `n_supported`, `n_rejected`, `elapsed_s` |
| `revise` | `round`, `n_rejected` |
| `done` | Shared result and total provider cost where available |

The application can preserve reviewed results and export them through its own review log. Retry and model fallback events identify the failed model and the next one.

## Runtime and failure handling

The local Neon loop is the default. Managed Agents is opt-in with `USE_MANAGED_AGENT=1` after a live custom-function round trip succeeds. Both runtimes use the same client-side report gate. Decision 1 errors fail the investigation. Gemini overload responses are retried with a bounded backoff and eligible model roles fall back with a trace event. Development mode is deterministic and has no network dependency.

The AlphaGenome score stores raw signed values plus an effect measure scaled across outputs. Atlas coverage can be partial because it covers single-nucleotide variants. The AlphaGenome-only baseline uses one fixed condition and reports the normalized effect. A successful score or plot is cached by variant, condition and output selection.

The provider usage log is stored under the configured cache directory. It includes the call configuration and response with keys and inline media bytes stripped. Session ids and filesystem paths stay out of the browser result.

The end-to-end check runs with `FAKE_MODE=0` and checks that the Side A case builder is ready with real data. The local integration built a real case. The investigation stopped at the first Gemini network request.
