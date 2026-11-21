# B2 demo and docs

Updated 2026-11-21 13:20:31 EST

## Done

- Initialized the local checkout of the new repository and committed the byte-identical shared contract.
- Created an ignored, untracked `.env` and a Python 3.12 virtual environment. The shell had neither API key set.
- Verified the DNM1 narrative and AlphaGenome use terms against primary sources.

## In progress

- README, design, pitch, video script, and submission checklist drafted. Benchmark and real-runtime sections are pending the other agents' results.
- Waiting for the five team research briefs before writing server and frontend code.

## Blocked

- Shell DNS cannot resolve GitHub, PyPI, or npm. Both push attempts, the dependency install, the Gemini docs MCP install, and the Gemini skill install failed. GitHub's API reported an empty repository at the 1:20 p.m. checkpoint.
- The sandbox denied creation of `~/genesleuth-data`. This checkout temporarily uses `/tmp/genesleuth-data`.

## NEEDS FROM B1

- `probes/B/REPORT.md` with confirmed integration shape and selected tissue conditions.
- The `look_again` signature, how it identifies the existing session, and its result and event shape.
- Structured trace fields for Decision 1 triage and checker counts, rejected claims and revisions, model fallbacks, elapsed budgets, and run cost.
- A stable B1 entry point for the Decisions API smoke check.
- From Side A, the background-only suspect source and the demo asset setup command.

## HUMAN TO DO

- Populate the two empty API key entries directly in `.env`.
- If the terminal can reach the network, push the contract using `git push -u origin main` and install `requirements.txt` in the local virtual environment.
- Create `~/genesleuth-data` and set the same absolute `GENESLEUTH_DATA_DIR` in both agents' checkouts when the shared location is available.
- Run `npx add-mcp "https://gemini-api-docs-mcp.dev"` and `npx skills add google-gemini/gemini-skills --skill gemini-api-dev` from a network-enabled terminal. Restart the coding session if required.
- Place all five research briefs under `docs/research/` in this local checkout, or attach them in chat. Side A owns those files.
