> **Stand-ins used:** atlas_no_scores(Atlas returned no AVI for any suspect: AlphaGenome Atlas metadata did not expose an AVI scorer; effect term = 0). Numbers for the affected arms are not final.

# Benchmark report: test

20 cases; 20 case(s) have results in every mode. Hit rates show `% (hits/n) [95% Wilson interval]`. With n this small the intervals are wide; read the interval, not the point estimate. Errored runs count as misses.

![chart](chart.png)

## Headline

| Mode | n | hit@1 | hit@5 | hit@10 | MRR@10 | median rank | filter recall |
|---|---|---|---|---|---|---|---|
| Gemini 4, no tools | 20 | 85% (17/20) [64-95] | 85% (17/20) [64-95] | 85% (17/20) [64-95] | 0.85 | 1 | 100% (20/20) [84-100] |
| Atlas AVI only | 20 | 0% (0/20) [0-16] | 0% (0/20) [0-16] | 0% (0/20) [0-16] | 0.00 | 11+ | 100% (20/20) [84-100] |
| AlphaGenome only (brain) | 20 | 80% (16/20) [58-92] | 80% (16/20) [58-92] | 85% (17/20) [64-95] | 0.81 | 1 | 100% (20/20) [84-100] |
| Fixed recipe (no LLM) | 20 | 55% (11/20) [34-74] | 80% (16/20) [58-92] | 90% (18/20) [70-97] | 0.66 | 1 | 100% (20/20) [84-100] |
| GeneSleuth (full agent), as first run (demo budget, 9 timeouts counted as misses) | 20 | 50% (10/20) [30-70] | 55% (11/20) [34-74] | 55% (11/20) [34-74] | 0.51 | 3 | 100% (20/20) [84-100] |
| GeneSleuth (full agent), after rerunning 9 of the 9 timed-out cases with the longer budget | 20 | 75% (15/20) [53-89] | 85% (17/20) [64-95] | 90% (18/20) [70-97] | 0.78 | 1 | 100% (20/20) [84-100] |

Rank 11+ or missing counts as a miss. MRR is MRR@10. Median rank treats a miss as 11 (`+` = at least that).

Both full-agent rows are shown on purpose: the first row is the pre-registered first run; the second differs only in that the timed-out cases were repeated (see 'What was rerun, and why').

### Among runs that finished (not the headline)

Errored runs count as misses in the headline above. This table drops them, to show how an arm does when it returns an answer. It is biased toward easier or faster cases, so do not quote it instead of the headline.

| Mode | runs finished / total | hit@1 | hit@5 | hit@10 |
|---|---|---|---|---|
| Gemini 4, no tools | 17 / 20 | 100% (17/17) [82-100] | 100% (17/17) [82-100] | 100% (17/17) [82-100] |
| Atlas AVI only | 0 / 20 | n/a | n/a | n/a |
| AlphaGenome only (brain) | 20 / 20 | 80% (16/20) [58-92] | 80% (16/20) [58-92] | 85% (17/20) [64-95] |
| Fixed recipe (no LLM) | 20 / 20 | 55% (11/20) [34-74] | 80% (16/20) [58-92] | 90% (18/20) [70-97] |
| GeneSleuth (full agent), as first run (demo budget, 9 timeouts counted as misses) | 11 / 20 | 91% (10/11) [62-98] | 100% (11/11) [74-100] | 100% (11/11) [74-100] |
| GeneSleuth (full agent), after rerunning 9 of the 9 timed-out cases with the longer budget | 19 / 20 | 79% (15/19) [57-91] | 89% (17/19) [69-97] | 95% (18/19) [75-99] |

## What was rerun, and why

In the first TEST run, 9 of 20 full-agent runs ended with an error: `The investigator did not return a fact-checked shortlist within its budget`. That is the demo-profile deadline being reached before the agent submitted (four cases and their arms ran at the same time, so those runs were also slower than they would be alone). Following the pre-registered rule (crashes may be rerun, failed cases only, and noted), 9 of those 9 cases were rerun for the full arm, with the longer `bench` profile limits (360 s deadline). No other arm and no other case was rerun, nothing was tuned on TEST, and the first-run results are kept unchanged in `full_first_run/` and shown in their own row.

| case | gene | region | letter | first run | rerun | rerun time (s) |
|---|---|---|---|---|---|---|
| 1ebf4e969dab180e | POLG | splice | clean | error (deadline) | rank 1 | 375 |
| 2c822300822a142f | ALDH7A1 | splice | clean | error (deadline) | rank 1 | 358 |
| 641ef5ede9fac37f | TSC1 | splice | clean | error (deadline) | rank 1 | 292 |
| 6a85ec2973fd5151 | SCN1A | splice | clean | error (deadline) | rank 1 | 350 |
| 945f8d0795a4f817 | SCN1A | coding | clean | error (deadline) | rank 3 | 341 |
| 97e7ac7c9f686dc7 | DEPDC5 | splice | clean | error (deadline) | rank 1 | 350 |
| bf4c21599e9b2961 | CACNA1A | intron | clean | error (deadline) | not in top 10 | 291 |
| d8c693f1a18c9dcb | SLC6A1 | coding | clean | error (deadline) | rank 8 | 356 |
| ddc4a709da29b72a | POLG | splice | clean | error (deadline) | error: The investigator did not return a fact-checked shortlist wit | 384 |

## Resources

| Mode | median AlphaGenome calls | median tool calls | median time (s) | claims checked / rejected | errors | median cost / case (USD) |
|---|---|---|---|---|---|---|
| Gemini 4, no tools | 0 | 0 | 49.0 | 0 / 0 | 3 | 0.13 |
| Atlas AVI only | n/a | n/a | 3.9 | 0 / 0 | 20 | n/a |
| AlphaGenome only (brain) | 282 | 0 | 6.3 | 0 / 0 | 0 | n/a |
| Fixed recipe (no LLM) | 0 | 2 | 0.9 | 0 / 0 | 0 | n/a |
| GeneSleuth (full agent), as first run (demo budget, 9 timeouts counted as misses) | 3 | 45 | 150.5 | 316 / 82 | 9 | 0.36 |
| GeneSleuth (full agent), after rerunning 9 of the 9 timed-out cases with the longer budget | 9 | 45 | 179.8 | 791 / 169 | 1 | 0.55 |

Median AlphaGenome and tool calls are over runs that finished (an errored run has no trace). Median time includes errored runs. Cost is the agent's own per-run accounting when present, else read from `calls.jsonl` (Gemini calls only; AlphaGenome calls are not billed per call here). `~` = attributed by time window, so approximate.

## Breakdowns (hit@5)

#### Region type (coding vs non-coding)

| Mode | coding hit@5 | non-coding hit@5 |
|---|---|---|
| Gemini 4, no tools | 100% (3/3) [44-100] | 82% (14/17) [59-94] |
| Atlas AVI only | 0% (0/3) [0-56] | 0% (0/17) [0-18] |
| AlphaGenome only (brain) | 0% (0/3) [0-56] | 94% (16/17) [73-99] |
| Fixed recipe (no LLM) | 67% (2/3) [21-94] | 82% (14/17) [59-94] |
| GeneSleuth (full agent), as first run (demo budget, 9 timeouts counted as misses) | 33% (1/3) [6-79] | 59% (10/17) [36-78] |
| GeneSleuth (full agent), after rerunning 9 of the 9 timed-out cases with the longer budget | 67% (2/3) [21-94] | 88% (15/17) [66-97] |

#### Letter type (clean vs scanned)

| Mode | clean hit@5 | scanned hit@5 |
|---|---|---|
| Gemini 4, no tools | 83% (10/12) [55-95] | 88% (7/8) [53-98] |
| Atlas AVI only | 0% (0/12) [0-24] | 0% (0/8) [0-32] |
| AlphaGenome only (brain) | 83% (10/12) [55-95] | 75% (6/8) [41-93] |
| Fixed recipe (no LLM) | 83% (10/12) [55-95] | 75% (6/8) [41-93] |
| GeneSleuth (full agent), as first run (demo budget, 9 timeouts counted as misses) | 25% (3/12) [9-53] | 100% (8/8) [68-100] |
| GeneSleuth (full agent), after rerunning 9 of the 9 timed-out cases with the longer budget | 75% (9/12) [47-91] | 100% (8/8) [68-100] |

## Full-agent failure categories

| category | count |
|---|---|
| unclassified | 1 |
| error | 1 |

Details in `failures.md`.

## Leakage controls

_No leakage-control results yet._

## Named cases (not pooled)

_No named-case runs yet (DNM1, MFSD8, PLA2G6 are reported separately and never pooled into TEST)._
