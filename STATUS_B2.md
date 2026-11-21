# B2 demo and docs

Updated 2026-11-21 13:57:35 EST

## Done

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

- The B2 shell cannot resolve GitHub. The collaborator's Terminal push worked. The connected GitHub app rejected the write with HTTP 403.
- B1's investigator is implemented locally and awaiting integration on GitHub main. Its local Gemini probes failed to connect, and AlphaGenome timed out. Both keys are configured in B1's ignored environment.
- Side A's setup found 66 missing PDFs across DEV, TEST and DEMO in the current snapshot. Prepared demo options load normally. The held-out report and chart remain pending.
- The B2 sandbox denied local port binding, and offline Chromium launch aborted. FastAPI and static frontend checks passed. Browser rehearsal requires a terminal with localhost access.

## NEEDS FROM B1

- Confirm the provider smoke run, observed brain and blood conditions, and live decisions telemetry. The server uses the existing `look_again(case, holdout, previous, request, on_event, profile)` interface.
- Ensure the demo profile requests submission by 120 seconds. The server applies a 180-second overall timeout and surfaces the failure.

## HUMAN TO DO

- After B1 is on main, run `python scripts/data_setup.py --check-only` and `python -m scripts.demo_check` from a network-enabled terminal in the integrated checkout. Rehearse three real cases if the live checks pass.
- Run the live demo with B1's existing ignored `.env` or fill the B2 checkout's ignored `.env` if launching from B2. Use one shared absolute data directory. B2 currently uses `/tmp/genesleuth-data`.
- If shell DNS remains blocked, push the B2 integration follow-up from the B2 checkout in the network-enabled Terminal. The B2 branch already tracks origin/main.
- Record and submit manually using `SUBMISSION_CHECKLIST.md`.
