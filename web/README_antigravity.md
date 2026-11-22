# GeneSleuth Web UI

High-contrast, projector-first diagnostic interface for **GeneSleuth** (AI-Powered Non-Coding Variant Triage using Gemini 4 + AlphaGenome).

Designed for live hackathon demonstration to judges on a 16:9 projector, legible from 20+ feet away with 18px+ body typography, 44px+ metrics, distinct actor color-coding, and real-time streaming evidence verification.

---

## Architecture & Zero-Build Runtime

- **Strictly Plain Vanilla**: Native HTML5, ES Modules JS, modern CSS3 variables and grid.
- **Zero build step, zero npm runtime dependencies**.
- **Resilient & Offline-Capable**: No external CDN blocking risks; fully self-contained.
- **Data Contract Compliant**: Strictly follows schemas defined in `genesleuth/schemas.py` (`DemoOption`, `Case`, `CaseTruth`, `TraceEvent`, `InvestigationResult`, `RankedSuspect`, `Claim`, `CheckVerdict`).

---

## 5 Pipeline Screens

1. **PICKER**: Browse ~169 real disease variants across the 58-gene epilepsy panel, filter by region (`intron`, `splice`, `promoter`, `utr5`, `utr3`, `coding`), live search, or trigger an unbiased **RANDOM PICK** (`R`). Highlighted showcase presets include:
   - **Anchor**: `DNM1 c.1335+1605G>A` (Deep-intronic cryptic splice in brain; missed in blood RNA tests).
   - **Holdout**: `MFSD8 c.999-556C>G` (Unseen post-cutoff non-coding holdout).
   - **Honest Failure**: `PLA2G6 c.2034+355G>A` (High AF frequency filter drop demonstration).
2. **CASE + LETTER**: Displays the clinical referral letter alongside an animated **Deterministic Filter Funnel** (`13,049` panel variants -> `812` rare -> `205` candidate suspects).
3. **LIVE INVESTIGATION**: Multi-agent timeline streaming live `TraceEvent`s with running clock:
   - **Gemini 4 Carbon**: HPO phenotype extraction with source text provenance on hover.
   - **Decisions API (Decision 1)**: Sub-second triage (`205 suspects scored in 0.22s, 28 prioritized`) and tissue routing.
   - **AlphaGenome**: Real-time counter of live deep neural model calls (0 to 28).
   - **Code Checker Verification**: Claims that fail check flash **RED** with checker rationale; revised claims pulse **GREEN** with verification confidence.
4. **REVEAL & REVIEW**: High-impact reveal of candidate ranking (`#1 of 205`), AlphaGenome dual-track visualization (**Brain Cortex** pseudoexon activation vs **Whole Blood** normal control), verified claims breakdown, human review controls (`Accept`, `Reject`, `Look Again`), and Markdown evidence report export.
5. **BENCHMARK PROOF**: Comparative hit rate matrix across 5 baselines with 95% Wilson binomial confidence intervals, and pre-registered honest failure modes accounting.

---

## Running the Web UI

### Option 1: Served by FastAPI (Agent B Backend)

Agent B mounts `web/` as static files:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()
# ... Agent B's API routes (/api/options, /api/cases, etc.) ...
app.mount("/", StaticFiles(directory="web", html=True), name="web")
```

Run FastAPI server:
```bash
uvicorn genesleuth.server:app --host 0.0.0.0 --port 8000 --reload
```
Navigate to: `http://localhost:8000`

### Option 2: Dev-Only Fixture Mode (`?dev=1`)

To test or demo the full end-to-end interface without requiring the FastAPI backend or external API keys:

```bash
# Using Python's built-in static HTTP server
python -m http.server 8080 --directory web
```

Open: **`http://localhost:8080/?dev=1`**

When `?dev=1` is present:
- Clearly displays the **`● FIXTURE DATA`** badge in the navigation bar.
- Simulates complete multi-agent streaming, authentic HPO extraction, Decision 1 triage, AlphaGenome counters, red/green claim verification, dual-track Brain vs Blood Sashimi plots, and human review actions.

---

## Keyboard Shortcuts

| Key | Action |
|:---:|:---|
| `1` - `5` | Switch directly between the 5 pipeline screens |
| `R` | Pick a random variant (Picker screen) |
| `Space` | Primary screen action (Start Investigation, Reveal) |
| `T` | Toggle Dark / Light theme |
| `?` | Show / hide keyboard shortcuts dialog |

---

## Network Isolation

All backend API requests are isolated exclusively in **`web/api.js`**:
- `listOptions()`
- `createCase(optionId)`
- `getCase(caseId)`
- `streamInvestigation(caseId, onEvent, onError, onComplete)`
- `getResult(caseId)`
- `reveal(caseId)`
- `lookAgain(caseId, variantId, tissue)`
- `exportReport(caseId, shortlist, truth)`
- `benchmark()`
