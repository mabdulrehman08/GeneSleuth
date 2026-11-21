# B2 demo and docs

Updated 2026-11-21 13:44:37 EST

## Done

- Read the five pre-event research briefs and B1's probe report.
- Built the FastAPI demo routes, judge's picker, referral preview, event timeline, claim evidence, review, reveal, plots, and held-out benchmark page.
- Added live demo preflight and background-only cache warming scripts.
- Exercised case creation, PDF delivery, event replay, rejection and revision, review, same-session follow-up, evidence download, reveal, and PNG delivery against Side A and B1 development fixtures.
- Confirmed the live server and preflight reject fake mode. The live server also rejects automatic data fixture fallback.
- Drafted the README, design, pitch, video script, and submission checklist. Benchmark results are pending.

## In progress

- Verify real-case timings against the released data and run the timed browser rehearsal. B1's current trace formats for triage, claims, budgets, cost, and fallback match the demo view.

## Blocked

- The B2 shell cannot resolve GitHub. GitHub's connected write attempt rejected tree creation with HTTP 403. Remote main now has Side A's work. The B1 environment has both key settings and the provider SDKs installed.
- Side A has pushed panel, ClinVar, and HPO assets. The remaining case and background inputs, setup script, and held-out test results are pending.
- The B2 sandbox denied local port binding, and offline Chromium launch aborted. FastAPI and static frontend checks passed. Browser rehearsal requires a terminal with localhost access.

## NEEDS FROM B1

- Confirm the provider smoke run, observed brain and blood conditions, and live decisions telemetry. The server uses the existing `look_again(case, holdout, previous, request, on_event, profile)` interface.
- Ensure the demo profile requests submission by 120 seconds. The server applies a 180-second overall timeout and surfaces the failure.

## HUMAN TO DO

- Coordinate Side A's `assets/` and `scripts/data_setup.py` delivery, then run the build and rehearsal in the integrated checkout.
- Run the live demo with B1's existing ignored `.env` or fill the B2 checkout's ignored `.env` if launching from B2. Use one shared absolute data directory. B2 currently uses `/tmp/genesleuth-data`.
- From the B2 checkout and a network-enabled terminal, run `git fetch origin`, then `git rebase --onto origin/main 1b1c6cd main` to replay B2 changes onto Side A's shared contract. Verify `.env` is ignored and untracked, then run `git push -u origin main`.
- Record and submit manually using `SUBMISSION_CHECKLIST.md`.
