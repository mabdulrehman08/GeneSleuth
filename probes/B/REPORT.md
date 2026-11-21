# Agent core API probes

November 21, 2026. Both SDKs are installed. The full probe from this checkout encountered Gemini connection errors and an AlphaGenome channel timeout. A separate live preflight from the network-enabled terminal verified Decision 1, Carbon referral reading, and AlphaGenome scoring with the configured brain and blood conditions.

| Surface | Documented interface | Local run |
| --- | --- | --- |
| Gemini 4 Carbon, Neon and Hydrogen | Stable v1 Interactions. Structured responses use `response_format` with a JSON Schema. The reader can send a PDF inline as a document block, including a scan. Neon tool calls are `function_call` steps with an id, name and arguments. Answer every call in the turn with a native `function_result` and the previous interaction id. | SDK loaded. Calls failed with connection errors. |
| Gemini Decision 1 | v1beta `decisions.create` accepts up to 1,000 questions per request. It can mix `noul`, `choice` and `score` questions and accepts inline image input. Each answer includes confidence. | SDK loaded. Calls failed with connection errors. |
| AlphaGenome 2 | `alphagenome.models.v2.dna_client`. One condition per request. `supported_conditions` returns a table keyed by `condition` with a `biosample_name` and per-output imputation modes. The scoring response has `raw_score` only. Use the official recommended RNA-seq and three splicing scorers. Indels are supported. For left alignment use the documented `genome.normalize_variant` with reference sequence. | SDK loaded. Channel readiness timed out. Condition ids and latencies are unverified. |
| AlphaGenome Atlas (AG1) | `query_variants` returns AnnData by scorer and accepts up to ten workers in the documented example. Confirm available scorer names with `scorer_metadata` and check the AVI response layout before extracting attributions. | SDK loaded. Atlas request depends on a reachable AlphaGenome channel. |
| Managed Agents | The version-pinned Antigravity agent supports a remote sandbox and streaming. The official Antigravity guide documents client-side function round trips and an object-valued function result on continuation. This run has not established a successful custom-function round trip, environment reuse, the thinking-level parameter or a 15-call latency/cost measurement. | Blocked before client creation. Default to the local Neon runtime at the decision gate unless the round trip is demonstrated. |

AlphaGenome's public splicing tutorial divides only the junction component by five. The team prompt writes parentheses around all three components. The team brief repeats the parenthesized formula. GeneSleuth implements the team's formula so the benchmark uses a consistent definition. Maintain raw signed values separately from any normalized ranking score.

Run the probe from the repo root after installing the packages and saving the keys to the ignored `.env`.

```bash
PYTHONPATH=. .venv/bin/python probes/B/api_probe.py
```

The emitted JSON records success or failure by probe, elapsed time for attempted calls and selected fields from successful responses. The script omits SDK exception bodies and never prints credentials.

## Official references

- [Gemini release notes](https://aistudio.google.com/docs/changelog)
- [Gemini Interactions](https://aistudio.google.com/docs/interactions-overview)
- [Gemini function calling](https://aistudio.google.com/docs/function-calling)
- [Gemini document processing](https://aistudio.google.com/docs/document-processing)
- [Gemini Decisions API](https://aistudio.google.com/docs/decisions-api)
- [Managed Agents quickstart](https://aistudio.google.com/docs/managed-agents-quickstart)
- [AlphaGenome 2 API](https://www.alphagenomedocs.com/api/models_v2.html)
- [AlphaGenome splicing workflow](https://www.alphagenomedocs.com/colabs/v2/splicing_variant.html)
- [AlphaGenome Atlas](https://www.alphagenomedocs.com/api/atlas.html)

## Live preflight and end-to-end checkpoint

The live preflight built a real case and referral PDF in 0.4 seconds, checked Decision 1 in 1.3 seconds, checked the configured AlphaGenome brain and blood conditions and a background score in 3.4 seconds, and read the referral with Carbon in 14.6 seconds. These timings cover the preflight operations.

`scripts/data_setup.py --check-only` passed with real Side A data and no missing letter PDFs across the checked splits. The live script built a case containing 282 candidates in 0.02 seconds. The first Carbon interaction returned an SDK connection error. The attempt produced no rank, AlphaGenome calls or checker results.

The six deterministic checker tests pass independently. An offline test with provider doubles exercised the full submission and revision loop. The installed AlphaGenome visualization components also rendered a two-condition fixture to a 1600 × 900 PNG.

Triage uses the public population-frequency lookup for every suspect. An offline regression check verified one lookup per suspect and confirmed that both model inputs omit frequency provenance.
