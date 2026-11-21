# Agent B1 status

Updated 2026-11-21 14:26:28 EST.

## Done

- Verified all 16 B1 runtime, checker and end-to-end script files on GitHub main against their local Git blob ids.
- Implemented Carbon referral extraction and planning, AlphaGenome 2 and Atlas clients, Decision 1 triage and routing, the Neon investigation loop, Hydrogen score summaries, claim verification, the three baseline modes and same-session reviewer follow-up.
- Six checker tests pass in the integrated checkout. Offline provider doubles exercised claim rejection, revision and same-session continuation. The installed AlphaGenome plotting components rendered two fixture conditions at 1600 × 900.
- Side A's real-data check passed in this checkout. It found 85 available demo options and no missing letter PDFs across the checked splits.
- The real end-to-end check built a case with 282 candidates in 0.02 s before Carbon returned APIConnectionError. No ranking, AlphaGenome requests or checker results were produced for that run.
- Both credentials are present in the ignored, untracked .env. The two local checkouts use /tmp/genesleuth-data. The home-directory data path was unavailable in the shell sandbox.

## In progress

- The probe report and this status are in the local b1-integration branch, which is based on the integrated main snapshot.
- Managed Agents is opt-in. The client-side round trip and the latency and cost targets still need a live confirmation.

## Blocked

- Gemini calls fail with SDK connection errors in this workspace. The AlphaGenome channel readiness probe times out. GitHub CLI access fails DNS resolution.
- A real hidden-variant rank, measured provider latency and a live end-to-end result remain unverified.

## HUMAN TO DO

- From a network-enabled terminal in the integrated checkout, run `FAKE_MODE=0 PYTHONPATH=. .venv/bin/python probes/B/api_probe.py` and then `FAKE_MODE=0 .venv/bin/python scripts/e2e_one_case.py`.
- If the browser or authenticated Git connection is available, publish this branch's documentation commit to main after checking it against latest main.

## NEEDS FROM B2

- Keep the complete previous InvestigationResult in the same process for look_again. The client checks that the result matches the latest completed session before resuming it.
- Check real data readiness before building a live case. The Side A public case builder can use development fixtures when required assets are missing.
- Total cost is in timings['cost_usd'] when provider usage is available. The Decisions smoke-check entry point is genesleuth.gemini_clients.decide(input_data, questions).
