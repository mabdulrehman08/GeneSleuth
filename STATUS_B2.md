# B2 demo and docs

Updated 2026-11-21 14:51:45 EST

## Done

- The live Terminal preflight passed Decision 1, AlphaGenome and Carbon. The updated bundle has 85 demo choices and all expected PDFs.
- Blocked lookup leakage before the benchmark. Case construction precomputes frequency buckets for every suspect, region annotations come from one local path, and Decision 1 and Neon receive no frequency provenance. The five-case regression and 22 related tests passed.
- Read the five pre-event research briefs and B1's probe report.
- Built the FastAPI demo routes, judge's picker, referral preview, event timeline, claim evidence, review, reveal, plots, and held-out benchmark page.
- Added live demo preflight and background-only cache warming scripts.
- Exercised case creation, PDF delivery, event replay, rejection and revision, review, same-session follow-up, evidence download, reveal, and PNG delivery against Side A and B1 development fixtures.
- Confirmed the live server and preflight reject fake mode. The live server also rejects automatic data fixture fallback.
- Pushed the demo and documentation to GitHub main.
- Side A's bundle passed the real-data setup check. Tested the real picker, two selected cases, and one random case through FastAPI. Each build finished under 0.6 seconds with 282 suspects and a PDF. The picker currently has 23 available demo options.
- Prewarming now reads the real background bundle and excludes potential spike-in positions. The cache plan validated 281 variants without making provider calls.
- The demo server only accepts prepared demo options, so a manually entered benchmark ID cannot access DEV or TEST cases.
- Updated the README from Side A's benchmark protocol and data inventory. Test results are pending.

## In progress

- Run the timed browser rehearsal with the integrated B1 investigator. The trace formats for triage, claims, budgets, cost, and fallback match the demo view.

## Blocked

- Run DEV and TEST only after the leakage fix is confirmed on GitHub main. Held-out results are pending.
- The B2 shell cannot resolve GitHub. The previous collaborator Terminal push worked. The connected GitHub app rejected the follow-up with HTTP 403, and Chrome's upload form did not accept the staged folders from Finder.
- B1's investigator and real-case check are on GitHub main. The integrated preflight passed key presence and real PDF setup. Decisions and Carbon returned SDK APIConnectionError, and AlphaGenome condition metadata timed out from this workspace.
- The B2 sandbox denied local port binding, and offline Chromium launch aborted. FastAPI and static frontend checks passed. Browser rehearsal requires a terminal with localhost access.

## NEEDS FROM B1

- Confirm the provider smoke run, observed brain and blood conditions, and live decisions telemetry. The server uses the existing `look_again(case, holdout, previous, request, on_event, profile)` interface.
- Ensure the demo profile requests submission by 120 seconds. The server applies a 180-second overall timeout and surfaces the failure.

## HUMAN TO DO

- Run `python -m scripts.demo_check` from a network-enabled terminal in the integrated checkout. Rehearse three real cases if the live checks pass.
- Run the live demo with B1's existing ignored `.env` or fill the B2 checkout's ignored `.env` if launching from B2. Use one shared absolute data directory. B2 currently uses `/tmp/genesleuth-data`.
- If shell DNS remains blocked, push the B2 integration follow-up from the B2 checkout in the network-enabled Terminal. The B2 branch already tracks origin/main.
- Record and submit manually using `SUBMISSION_CHECKLIST.md`.
