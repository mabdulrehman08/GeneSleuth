# GeneSleuth design

This document specifies the planned live demo and reviewer workflow. See the [agent design](docs/DESIGN_AGENT.md), [data design](docs/DESIGN_DATA.md), and [benchmark](docs/BENCHMARK.md) for their respective components.

## Case lifecycle

The interface is plain HTML, JavaScript and CSS. FastAPI serves the pages and maintains a single-process case store. A case moves from build to investigation, reviewer decisions, and reveal. The case builder returns a public case and a separate answer key. The API keeps the answer key server-side until Reveal and passes the configured holdout to the investigator.

| Route | Responsibility |
| --- | --- |
| `GET /`, `GET /api/options` | Serve the demo and return the judge's picker options. |
| `POST /api/cases` | Build a case from the selected option or a random one. Return the opaque case ID, funnel, suspect count and letter URL. |
| `GET /api/cases/{id}/letter` | Serve the case referral PDF inline. |
| `POST /api/cases/{id}/investigate` | Schedule the demo-profile investigation in the background. |
| `GET /api/cases/{id}/events` | Replay and stream trace events, then send the terminal result. |
| `POST /api/cases/{id}/review` | Record Accept or Reject for a current shortlist entry. |
| `POST /api/cases/{id}/look-again` | Pass the extension request to the investigator's existing session and stream the follow-up. |
| `GET /api/cases/{id}/report` | Download accepted candidates and supported evidence with citations, plus review decisions. |
| `POST /api/cases/{id}/reveal` | Disclose the answer key and shortlist rank after completion, and request the hidden candidate's plot if needed. |
| `GET /api/plots/{file}` | Serve a registered PNG artifact. |
| `GET /benchmark` | Show the held-out test chart and report when published. |

## Live view and evaluation

The picker searches by gene, region and condition and supports random selection. It displays the referral alongside the funnel. The timeline uses model and tool events with elapsed times, call counts, checker verdicts and runtime fallbacks. Cost comes from run-level investigator telemetry when provided. Candidate details connect checked claims to their evidence. The plot compares reference and alternate tracks in brain and blood. A shortlist miss remains visible after reveal.

Build and investigation have separate elapsed timers. The demo targets 15 seconds to build and 100 seconds to investigate. The investigator owns model deadlines, budget enforcement, retries and fallback. The server owns stream completion, replay, and visible failure states. A delayed plot cannot delay revealing the rank.

## Review and storage

Accept and Reject are reviewer decisions, keyed by variant ID. Follow-up requests keep the same investigator session and use its existing evidence. Review history is written to `GENESLEUTH_DATA_DIR/reviews/<case_id>.json`. The Markdown export includes current accepted entries and only claims marked supported, with the cited call IDs and review decisions.

The case session, plot handles and live trace are scoped to the demo server process. The review log and provider caches live on disk. The server requires `--dev` for fake mode. The demo check requires live mode and delegates provider calls to the shared clients or investigator.

## Dependencies and integration

Side A supplies `list_demo_options`, `build_case`, `holdout_for` and the data bundle. B1 supplies `investigate`, `look_again`, `plot_variant` and `list_tissues`. The prewarm script delegates scoring to B1 and needs a confirmed background-only source from Side A. See [B2 status](STATUS_B2.md) for open contracts and verified behavior.
