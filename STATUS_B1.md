# Agent B1 status

Updated 2026-11-21 14:49:37 EST.

## Done

- Verified all 16 B1 runtime, checker and end-to-end script files on GitHub main against their local Git blob ids.
- Implemented Carbon referral extraction and planning, AlphaGenome 2 and Atlas clients, Decision 1 triage and routing, the Neon investigation loop, Hydrogen score summaries, claim verification, the three baseline modes and same-session reviewer follow-up.
- Six checker tests pass in the integrated checkout. Offline provider doubles exercised claim rejection, revision and same-session continuation. The installed AlphaGenome plotting components rendered two fixture conditions at 1600 × 900.
- Side A's real-data check passed in this checkout. It found 85 available demo options and no missing letter PDFs across the checked splits.
- The real end-to-end check built a case with 282 candidates in 0.02 s before Carbon returned APIConnectionError. A later preflight in the network-enabled terminal passed Decision 1, Carbon, and the AlphaGenome brain and blood checks.
- Triage now calls the public population-frequency lookup for every suspect. The candidate rows sent to Decision 1 and Neon omit frequency provenance. A focused regression check and all six checker tests passed.
- Both credentials are present in the ignored, untracked .env. The two local checkouts use /tmp/genesleuth-data. The home-directory data path was unavailable in the shell sandbox.

## In progress

- The triage change, probe report, status and design are on the local b1-integration branch, based on the integrated main snapshot.
- Managed Agents is opt-in. The client-side round trip and the latency and cost targets still need a live confirmation.

## Blocked

- Gemini and AlphaGenome probes in this workspace encountered network failures. GitHub CLI access fails DNS resolution here.
- A live end-to-end ranking remains unverified.

## HUMAN TO DO

- From a network-enabled terminal in the integrated checkout, run `FAKE_MODE=0 PYTHONPATH=. .venv/bin/python probes/B/api_probe.py` and then `FAKE_MODE=0 .venv/bin/python scripts/e2e_one_case.py`.
- If the browser or authenticated Git connection is available, publish this branch's documentation commit to main after checking it against latest main.

## NEEDS FROM B2

- Keep the complete previous InvestigationResult in the same process for look_again. The client checks that the result matches the latest completed session before resuming it.
- Check real data readiness before building a live case. The Side A public case builder can use development fixtures when required assets are missing.
- Total cost is in timings['cost_usd'] when provider usage is available. The Decisions smoke-check entry point is genesleuth.gemini_clients.decide(input_data, questions).
