# B2 demo and docs

Updated 2026-11-21 13:40:33 EST

## Done

- Read the five pre-event research briefs and B1's probe report.
- Built the FastAPI demo routes, judge's picker, referral preview, event timeline, claim evidence, review, reveal, plots, and held-out benchmark page.
- Added live demo preflight and background-only cache warming scripts.
- Exercised case creation, PDF delivery, event replay, rejection and revision, review, same-session follow-up, evidence download, reveal, and PNG delivery against Side A and B1 development fixtures.
- Confirmed the live server and preflight reject fake mode. The live server also rejects automatic data fixture fallback.
- Drafted the README, design, pitch, video script, and submission checklist. Benchmark results are pending.

## In progress

- Browser rehearsal at desktop and phone widths.
- Verify real-case timings and instrument fields against the released A and B1 packages.

## Blocked

- The B2 shell cannot resolve GitHub. Remote main now exists with Side A's work. The B1 environment has both key settings and the provider SDKs installed.
- Side A's real data bundle and held-out test artifacts are still pending. The B2 sandbox also blocks binding a local HTTP port, so the real local-browser rehearsal must run in a terminal with localhost access.

## NEEDS FROM B1

- Confirm the provider smoke run, observed brain and blood conditions, and live decisions telemetry. The server uses the existing `look_again(case, holdout, previous, request, on_event, profile)` interface.
- Ensure the demo profile requests submission by 120 seconds. The server applies a 180-second overall timeout and surfaces the failure.

## HUMAN TO DO

- Coordinate Side A's `assets/` and `scripts/data_setup.py` delivery, then run the build and rehearsal in the integrated checkout.
- Run the live demo with B1's existing ignored `.env` or fill the B2 checkout's ignored `.env` if launching from B2. Use one shared absolute data directory. B2 currently uses `/tmp/genesleuth-data`.
- If the shell push continues to fail, push the B2 changes from a network-enabled terminal after bringing the Side A and B1 commits together. Do not force-push.
- Record and submit manually using `SUBMISSION_CHECKLIST.md`.
