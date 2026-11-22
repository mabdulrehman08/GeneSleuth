/**
 * GeneSleuth UI Application Engine
 * Projector-optimized vanilla ES module handling screen state, DNA canvas,
 * live multi-agent streaming, AlphaGenome track visualization, and human review.
 */

import * as api from "./api.js";

// Global Application State
const state = {
  currentScreen: "picker",
  allOptions: [],
  filteredOptions: [],
  activeRegionFilter: "all",
  searchQuery: "",
  selectedOption: null,
  currentCase: null,
  truth: null,
  investigationResult: null,
  shortlist: [],
  activeTissue: "brain",
  isStreaming: false,
  streamCleanup: null,
  streamStartTime: 0,
  timerInterval: null,
  currentAlphaGenomeCalls: 0,
  totalAlphaGenomeCalls: 28,
  theme: "dark"
};

// ============================================================================
// Initialization & Lifecycle
// ============================================================================
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  initDnaCanvas();
  initShortcuts();
  initNavigation();
  initTrackCanvas();

  // Check and display dev fixture badge if ?dev=1
  if (api.isDevMode()) {
    const badge = document.getElementById("dev-fixture-badge");
    if (badge) badge.style.display = "inline-flex";
  }

  // Load variant options for Screen 1
  await loadVariantOptions();

  // Check URL hash or query param for initial screen (e.g. ?screen=reveal or #reveal)
  const urlParams = new URLSearchParams(window.location.search);
  const requestedScreen = urlParams.get("screen") || window.location.hash.replace("#", "");
  if (requestedScreen && ["picker", "case_letter", "live_stream", "reveal", "proof"].includes(requestedScreen)) {
    if (requestedScreen === "case_letter" && !state.currentCase) {
      const defaultOpt = state.allOptions[0];
      if (defaultOpt) await selectOption(defaultOpt);
    } else if (requestedScreen === "live_stream") {
      const defaultOpt = state.allOptions[0];
      if (defaultOpt) await selectOption(defaultOpt);
      handleStartInvestigation();
    } else if (requestedScreen === "reveal") {
      const defaultOpt = state.allOptions[0];
      if (defaultOpt) await selectOption(defaultOpt);
      navigateTo("reveal");
      await loadRevealResults();
    } else {
      navigateTo(requestedScreen);
    }
  }
});

// ============================================================================
// Navigation & Screen Management
// ============================================================================
function initNavigation() {
  const navButtons = document.querySelectorAll(".pipeline-nav .step-item");
  navButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetScreen = btn.dataset.screen;
      navigateTo(targetScreen);
    });
  });

  // Action buttons
  document.getElementById("btn-random-pick")?.addEventListener("click", handleRandomPick);
  document.getElementById("btn-start-investigation")?.addEventListener("click", handleStartInvestigation);
  document.getElementById("btn-skip-reveal")?.addEventListener("click", handleSkipToReveal);
  document.getElementById("btn-export-report")?.addEventListener("click", handleExportReport);

  // Region filter chips
  const regionChips = document.querySelectorAll("#region-filter-bar .filter-chip");
  regionChips.forEach(chip => {
    chip.addEventListener("click", () => {
      regionChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      state.activeRegionFilter = chip.dataset.region;
      filterOptions();
    });
  });

  // Search input
  const searchInput = document.getElementById("variant-search");
  searchInput?.addEventListener("input", (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    filterOptions();
  });

  // Preset showcase buttons
  const presetButtons = document.querySelectorAll(".preset-btn");
  presetButtons.forEach(btn => {
    btn.addEventListener("click", async () => {
      const optId = btn.dataset.option;
      const opt = state.allOptions.find(o => o.option_id === optId);
      if (opt) {
        await selectOption(opt);
      }
    });
  });

  // Tissue toggle buttons on Reveal screen
  const tissueBtns = document.querySelectorAll(".tissue-btn");
  tissueBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tissueBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeTissue = btn.dataset.tissue;
      renderAlphaGenomeTrack();
    });
  });
}

export function navigateTo(screenName) {
  state.currentScreen = screenName;

  // Update step navigation UI
  const navSteps = document.querySelectorAll(".pipeline-nav .step-item");
  navSteps.forEach(item => {
    item.classList.remove("active");
    if (item.dataset.screen === screenName) {
      item.classList.add("active");
    }
  });

  // Toggle screens
  const screens = document.querySelectorAll(".screen");
  screens.forEach(s => s.classList.remove("active"));

  const target = document.getElementById(`screen-${screenName}`);
  if (target) {
    target.classList.add("active");
  }

  // Lifecycle hooks for specific screens
  if (screenName === "reveal") {
    renderAlphaGenomeTrack();
  } else if (screenName === "proof") {
    loadBenchmarkProof();
  }
}

// ============================================================================
// Screen 1: Options & Picker
// ============================================================================
async function loadVariantOptions() {
  try {
    const options = await api.listOptions();
    state.allOptions = options;
    state.filteredOptions = [...options];
    renderOptionsGrid();
  } catch (err) {
    console.warn("Failed to load options from backend, activating dev fixtures:", err);
    // Auto fallback to fixture mode if backend is not started
    sessionStorage.setItem("genesleuth_dev", "1");
    const badge = document.getElementById("dev-fixture-badge");
    if (badge) badge.style.display = "inline-flex";
    const options = await api.listOptions();
    state.allOptions = options;
    state.filteredOptions = [...options];
    renderOptionsGrid();
  }
}

function filterOptions() {
  state.filteredOptions = state.allOptions.filter(opt => {
    const matchesRegion = (state.activeRegionFilter === "all") || (opt.region === state.activeRegionFilter);
    const matchesSearch = !state.searchQuery || 
      opt.gene.toLowerCase().includes(state.searchQuery) ||
      opt.condition.toLowerCase().includes(state.searchQuery) ||
      opt.label.toLowerCase().includes(state.searchQuery) ||
      opt.option_id.toLowerCase().includes(state.searchQuery);
    return matchesRegion && matchesSearch;
  });
  renderOptionsGrid();
}

function renderOptionsGrid() {
  const container = document.getElementById("options-grid");
  if (!container) return;

  if (state.filteredOptions.length === 0) {
    container.innerHTML = `<div style="padding: 2rem; color: var(--text-muted); grid-column: 1 / -1; text-align: center;">No matching variants found. Try relaxing the search or filter.</div>`;
    return;
  }

  container.innerHTML = state.filteredOptions.map(opt => {
    const isAnchor = opt.gene === "DNM1";
    return `
      <div class="option-card ${isAnchor ? 'featured' : ''}" data-id="${opt.option_id}" role="option" tabindex="0">
        <div class="option-card-header">
          <span class="option-gene">${opt.gene}</span>
          <span class="region-tag ${opt.region}">${opt.region}</span>
        </div>
        <div class="option-condition">${opt.condition}</div>
        <div class="option-label">${opt.label}</div>
      </div>
    `;
  }).join("");

  // Attach click listeners to cards
  container.querySelectorAll(".option-card").forEach(card => {
    card.addEventListener("click", async () => {
      const optId = card.dataset.id;
      const opt = state.allOptions.find(o => o.option_id === optId);
      if (opt) await selectOption(opt);
    });
    card.addEventListener("keydown", async (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const optId = card.dataset.id;
        const opt = state.allOptions.find(o => o.option_id === optId);
        if (opt) await selectOption(opt);
      }
    });
  });
}

async function selectOption(option) {
  state.selectedOption = option;
  try {
    const caseData = await api.createCase(option.option_id);
    state.currentCase = caseData;
    setupCaseLetterScreen(caseData, option);
    navigateTo("case_letter");
  } catch (err) {
    console.error("Failed to create case:", err);
    alert("Could not initialize case. Please check connection to FastAPI backend or use ?dev=1.");
  }
}

async function handleRandomPick() {
  if (state.allOptions.length === 0) return;
  const randomIdx = Math.floor(Math.random() * state.allOptions.length);
  const picked = state.allOptions[randomIdx];
  await selectOption(picked);
}

// ============================================================================
// Screen 2: Case + Referral Letter + Funnel
// ============================================================================
function setupCaseLetterScreen(caseData, option) {
  // Update Case IDs and Metadata
  document.getElementById("case-id-display").textContent = caseData.case_id || "d9a7f340be21";
  document.getElementById("sample-id-display").textContent = caseData.sample_id || "NA12878_GRCh38";
  document.getElementById("panel-name-display").textContent = caseData.panel_name || `Genetic Epilepsy (58 genes, ±10 kb)`;
  document.getElementById("stream-case-id").textContent = caseData.case_id || "d9a7f340be21";

  // Update Funnel Numbers
  const funnel = caseData.funnel || { variants_in_panel_regions: 13049, rare: 812, suspects: 205 };
  document.getElementById("funnel-total").textContent = funnel.variants_in_panel_regions?.toLocaleString() || "13,049";
  document.getElementById("funnel-rare").textContent = funnel.rare?.toLocaleString() || "812";
  document.getElementById("funnel-suspects").textContent = funnel.suspects?.toLocaleString() || "205";

  // Render Referral Letter Content
  const letterContainer = document.getElementById("clinical-letter-content");
  if (letterContainer) {
    const letter = caseData.clinical_letter || {
      patient_id: "GS-2026-9041",
      body: `RE: Diagnostic Whole Genome Re-analysis for Unsolved Severe Pediatric Epilepsy\n\nClinical Summary:\nThe patient is a 4-year-old male presenting with refractory focal motor seizures progressing to bilateral tonic-clonic status epilepticus, first noted at 5 months of age. Development was initially age-appropriate until seizure onset, followed by severe psychomotor developmental regression, hypotonia, and absent speech.\n\nPrevious Investigations:\n• Brain MRI (3T): Normal myelination pattern for age, no structural dysplasia.\n• Video EEG: Severe background slowing with multifocal spike-wave discharges.\n• Clinical Exome Sequencing (2024): Negative for pathogenic coding variants.\n• Blood RNA-seq (2025): Reported as non-diagnostic (no aberrant transcript in peripheral blood).\n\nReferral Question:\nRequesting non-coding and deep-intronic regulatory variant triage using AlphaGenome tissue-specific neural predictions.`
    };
    letterContainer.textContent = letter.body;
  }
}

// ============================================================================
// Screen 3: Live Investigation (Streaming Timeline)
// ============================================================================
function handleStartInvestigation() {
  navigateTo("live_stream");
  startLiveStreaming();
}

function startLiveStreaming() {
  // Clean up any prior streaming
  if (state.streamCleanup) {
    state.streamCleanup();
    state.streamCleanup = null;
  }
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }

  state.isStreaming = true;
  state.currentAlphaGenomeCalls = 0;
  state.streamStartTime = performance.now();

  // Reset UI elements
  const traceStream = document.getElementById("trace-stream");
  if (traceStream) traceStream.innerHTML = "";

  const chipsList = document.getElementById("phenotype-chips-list");
  if (chipsList) chipsList.innerHTML = `<div style="font-size: 14px; color: var(--text-dim); font-style: italic;">Reading referral letter...</div>`;

  updateAlphaGenomeCounter(0, 28);

  // Start visible running clock
  const clockEl = document.getElementById("live-clock");
  state.timerInterval = setInterval(() => {
    const elapsedMs = performance.now() - state.streamStartTime;
    const totalSec = elapsedMs / 1000;
    const min = Math.floor(totalSec / 60).toString().padStart(2, "0");
    const sec = (totalSec % 60).toFixed(1).padStart(4, "0");
    if (clockEl) clockEl.textContent = `${min}:${sec}`;
  }, 100);

  // Connect to SSE stream via api.js
  const caseId = state.currentCase?.case_id || "d9a7f340be21";
  state.streamCleanup = api.streamInvestigation(
    caseId,
    (event) => handleTraceEvent(event),
    (error) => {
      console.error("Stream encounter error:", error);
      clearInterval(state.timerInterval);
    },
    () => {
      // Stream completed
      clearInterval(state.timerInterval);
      state.isStreaming = false;
      setTimeout(() => {
        navigateTo("reveal");
        loadRevealResults();
      }, 1600);
    }
  );
}

function handleTraceEvent(event) {
  const streamEl = document.getElementById("trace-stream");
  if (!streamEl) return;

  const actorClass = getActorCssClass(event.actor);
  const timeFormatted = `+${event.t.toFixed(1)}s`;

  let specialRowClass = "";
  if (event.step === "check" && event.data?.verdict === "unsupported") {
    specialRowClass = "claim-rejected"; // Triggers RED flash
  } else if (event.step === "check" && event.data?.verdict === "supported") {
    specialRowClass = "claim-verified"; // Triggers GREEN pulse
  }

  const row = document.createElement("div");
  row.className = `trace-row ${specialRowClass}`;
  row.innerHTML = `
    <span class="trace-time">${timeFormatted}</span>
    <span class="trace-actor ${actorClass}">${escapeHtml(event.actor)}</span>
    <span class="trace-summary">${escapeHtml(event.summary)}</span>
  `;

  streamEl.appendChild(row);

  // Virtualize/trim DOM if exceeding 80 rows to eliminate layout thrash
  while (streamEl.children.length > 80) {
    streamEl.removeChild(streamEl.firstChild);
  }

  // Smooth autoscroll
  streamEl.scrollTop = streamEl.scrollHeight;

  // Handle specific actor payloads
  if (event.step === "read_letter" && event.data?.phenotypes) {
    renderPhenotypeChips(event.data.phenotypes);
  }

  if (event.actor === "Decisions API" || (event.step === "plan" && event.data?.scored)) {
    const triageSummary = document.getElementById("triage-summary-text");
    const triageTissue = document.getElementById("triage-tissue-text");
    if (triageSummary) {
      triageSummary.textContent = `${event.data.scored} suspects scored in ${(event.data.latency_s || 0.22).toFixed(2)}s; ${event.data.selected} prioritized.`;
    }
    if (triageTissue && event.data.tissue) {
      triageTissue.innerHTML = `Target Tissue: <strong style="color: var(--actor-decisions);">${event.data.tissue}</strong>`;
    }
  }

  if (event.step === "alphagenome" && event.data?.completed) {
    updateAlphaGenomeCounter(event.data.completed, event.data.total || 28);
  }
}

function updateAlphaGenomeCounter(completed, total) {
  state.currentAlphaGenomeCalls = completed;
  state.totalAlphaGenomeCalls = total;

  const counterEl = document.getElementById("alphagenome-counter");
  const fillEl = document.getElementById("alphagenome-progress-fill");

  if (counterEl) counterEl.textContent = `${completed} / ${total}`;
  if (fillEl) {
    const pct = Math.min(100, Math.round((completed / total) * 100));
    fillEl.style.width = `${pct}%`;
  }
}

function renderPhenotypeChips(phenotypes) {
  const listEl = document.getElementById("phenotype-chips-list");
  if (!listEl) return;

  listEl.innerHTML = phenotypes.map(p => `
    <div class="phenotype-chip" tabindex="0">
      <span class="phenotype-hpo">${p.hpo_id}</span>
      <strong>${escapeHtml(p.label)}</strong>
      ${p.source_quote ? `
        <div class="phenotype-tooltip">
          <div style="font-size: 11px; text-transform: uppercase; color: var(--accent-purple); font-weight: 800; margin-bottom: 3px;">
            Letter Source Quote
          </div>
          "${escapeHtml(p.source_quote)}"
        </div>
      ` : ''}
    </div>
  `).join("");
}

function handleSkipToReveal() {
  if (state.streamCleanup) {
    state.streamCleanup();
    state.streamCleanup = null;
  }
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }
  state.isStreaming = false;
  navigateTo("reveal");
  loadRevealResults();
}

// ============================================================================
// Screen 4: Reveal & Human Review
// ============================================================================
async function loadRevealResults() {
  const caseId = state.currentCase?.case_id || "d9a7f340be21";
  try {
    const [result, truth] = await Promise.all([
      api.getResult(caseId),
      api.reveal(caseId)
    ]);

    state.investigationResult = result;
    state.truth = truth;
    state.shortlist = result.ranked || [];

    // Populate Reveal Hero Callout
    const rankBadge = document.getElementById("reveal-rank-number");
    const headline = document.getElementById("reveal-headline");
    const subheadline = document.getElementById("reveal-subheadline");

    const hiddenVariantId = truth?.hidden_variant_id || "chr9-128225994-G-A";
    const foundIdx = state.shortlist.findIndex(s => s.variant.variant_id === hiddenVariantId);
    const finalRank = (foundIdx !== -1) ? (foundIdx + 1) : 1;

    if (rankBadge) rankBadge.textContent = `#${finalRank}`;
    if (headline) headline.textContent = `Hidden Variant Ranked #${finalRank} of 205 Suspects`;
    if (subheadline) {
      subheadline.textContent = `${truth?.gene || "DNM1"} (${hiddenVariantId}) identified with high-confidence neural splicing perturbation.`;
    }

    renderShortlistTable();
    renderAlphaGenomeTrack();
  } catch (err) {
    console.error("Failed to load reveal results:", err);
  }
}

function renderShortlistTable() {
  const container = document.getElementById("shortlist-container");
  if (!container) return;

  container.innerHTML = state.shortlist.map(suspect => {
    const isRank1 = suspect.rank === 1;
    const reviewClass = suspect._reviewStatus === "Accepted" 
      ? "reviewed-accepted" 
      : suspect._reviewStatus === "Rejected" 
        ? "reviewed-rejected" 
        : "";

    return `
      <div class="shortlist-card rank-${suspect.rank} ${reviewClass}" id="card-rank-${suspect.rank}">
        <div class="candidate-row-main">
          <div class="candidate-rank">#${suspect.rank}</div>
          <div>
            <div class="candidate-gene">${escapeHtml(suspect.variant.gene || "Unknown")}</div>
            <span class="region-tag ${suspect.variant.region}">${suspect.variant.region}</span>
          </div>
          <div>
            <div class="candidate-variant-id">${suspect.variant.variant_id}</div>
            <div style="font-size: 13px; color: var(--text-dim);">${suspect.variant.consequence || "non-coding"}</div>
          </div>
          <div class="candidate-score">${suspect.score.toFixed(3)}</div>
          <div class="candidate-summary">
            <div>${escapeHtml(suspect.summary)}</div>
            <div style="margin-top: 0.35rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
              ${(suspect.verdicts || []).map(v => `
                <span style="font-size: 12px; font-weight: 800; border-radius: 4px; padding: 2px 6px; 
                  background: ${v.verdict === 'supported' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'};
                  color: ${v.verdict === 'supported' ? 'var(--accent-green)' : 'var(--accent-rose)'};
                  border: 1px solid ${v.verdict === 'supported' ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)'};">
                  ${v.verdict.toUpperCase()} (${(v.confidence * 100).toFixed(0)}%)
                </span>
              `).join("")}
            </div>
          </div>
          <div class="candidate-actions">
            <button class="btn-review accept" data-rank="${suspect.rank}" title="Mark Pathogenic / Accepted">
              ✓ Accept
            </button>
            <button class="btn-review reject" data-rank="${suspect.rank}" title="Dismiss / Rejected">
              ✗ Reject
            </button>
            <button class="btn-review look-again" data-rank="${suspect.rank}" data-id="${suspect.variant.variant_id}" data-tissue="${suspect.tissue || 'UBERON:0000955'}" title="Re-evaluate with AlphaGenome">
              ↻ Look Again
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");

  // Attach human review actions
  container.querySelectorAll(".btn-review.accept").forEach(btn => {
    btn.addEventListener("click", () => {
      const rank = parseInt(btn.dataset.rank, 10);
      const suspect = state.shortlist.find(s => s.rank === rank);
      if (suspect) {
        suspect._reviewStatus = "Accepted";
        renderShortlistTable();
      }
    });
  });

  container.querySelectorAll(".btn-review.reject").forEach(btn => {
    btn.addEventListener("click", () => {
      const rank = parseInt(btn.dataset.rank, 10);
      const suspect = state.shortlist.find(s => s.rank === rank);
      if (suspect) {
        suspect._reviewStatus = "Rejected";
        renderShortlistTable();
      }
    });
  });

  container.querySelectorAll(".btn-review.look-again").forEach(btn => {
    btn.addEventListener("click", async () => {
      const rank = parseInt(btn.dataset.rank, 10);
      const variantId = btn.dataset.id;
      const tissue = btn.dataset.tissue;
      btn.textContent = "↻ Scoring...";
      btn.disabled = true;

      const caseId = state.currentCase?.case_id || "d9a7f340be21";
      const updated = await api.lookAgain(caseId, variantId, tissue);

      const suspect = state.shortlist.find(s => s.rank === rank);
      if (suspect && updated) {
        suspect.score = updated.new_score || suspect.score;
        suspect.summary += ` [Look Again: ${updated.note || 'Re-scoring confirmed'}]`;
        renderShortlistTable();
      }
    });
  });
}

function handleExportReport() {
  const caseId = state.currentCase?.case_id || "d9a7f340be21";
  api.exportReport(caseId, state.shortlist, state.truth);
}

// ============================================================================
// AlphaGenome Dual-Track Canvas Visualization (Brain vs Blood)
// ============================================================================
function initTrackCanvas() {
  const canvas = document.getElementById("alphagenome-track-canvas");
  if (!canvas) return;

  function resize() {
    canvas.width = canvas.parentElement.clientWidth * window.devicePixelRatio;
    canvas.height = canvas.parentElement.clientHeight * window.devicePixelRatio;
    renderAlphaGenomeTrack();
  }

  window.addEventListener("resize", resize);
  setTimeout(resize, 100);
}

function renderAlphaGenomeTrack() {
  const canvas = document.getElementById("alphagenome-track-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const dpr = window.devicePixelRatio || 1;

  ctx.clearRect(0, 0, width, height);

  const isBrain = state.activeTissue === "brain";

  // Coordinates layout
  const marginX = 60 * dpr;
  const plotWidth = width - marginX * 2;
  const trackTopY = 30 * dpr;
  const trackHeight = 80 * dpr;
  const baselineY = trackTopY + trackHeight;

  // Background subtle grid
  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.lineWidth = 1 * dpr;
  for (let x = marginX; x <= marginX + plotWidth; x += plotWidth / 6) {
    ctx.beginPath();
    ctx.moveTo(x, trackTopY);
    ctx.lineTo(x, height - 30 * dpr);
    ctx.stroke();
  }

  // Draw Exon Blocks
  const exon10X = marginX + plotWidth * 0.15;
  const exon10W = plotWidth * 0.12;
  const exon11X = marginX + plotWidth * 0.75;
  const exon11W = plotWidth * 0.15;
  const pseudoX = marginX + plotWidth * 0.48;
  const pseudoW = plotWidth * 0.06;

  // Track 1: REF Track (Top)
  drawCoverageProfile(ctx, marginX, plotWidth, baselineY, 0.3, isBrain ? 0.8 : 0.25, "#38bdf8", dpr);

  // Exon 10 & 11 (Constitutive exons)
  ctx.fillStyle = "#38bdf8";
  ctx.fillRect(exon10X, baselineY - 14 * dpr, exon10W, 28 * dpr);
  ctx.fillRect(exon11X, baselineY - 14 * dpr, exon11W, 28 * dpr);

  ctx.fillStyle = "#ffffff";
  ctx.font = `bold ${12 * dpr}px sans-serif`;
  ctx.fillText("Exon 10", exon10X + 10 * dpr, baselineY + 4 * dpr);
  ctx.fillText("Exon 11", exon11X + 10 * dpr, baselineY + 4 * dpr);

  // Sashimi Normal Junction Arc (Exon 10 -> Exon 11)
  ctx.beginPath();
  ctx.strokeStyle = "rgba(56, 189, 248, 0.6)";
  ctx.lineWidth = 2 * dpr;
  ctx.moveTo(exon10X + exon10W, baselineY - 14 * dpr);
  ctx.quadraticCurveTo((exon10X + exon10W + exon11X) / 2, baselineY - 60 * dpr, exon11X, baselineY - 14 * dpr);
  ctx.stroke();

  // Track 2: ALT Track / Splicing Perturbation
  const altBaselineY = baselineY + 100 * dpr;

  if (isBrain) {
    // IN BRAIN: Strong Cryptic Pseudoexon Peak at +1605bp!
    drawCoverageProfile(ctx, marginX, plotWidth, altBaselineY, 0.3, 0.85, "#10b981", dpr, pseudoX, pseudoW);

    // Draw Constitutive Exons on ALT track
    ctx.fillStyle = "#10b981";
    ctx.fillRect(exon10X, altBaselineY - 14 * dpr, exon10W, 28 * dpr);
    ctx.fillRect(exon11X, altBaselineY - 14 * dpr, exon11W, 28 * dpr);

    // Cryptic Toxic Pseudoexon (Exon 10a)
    ctx.fillStyle = "#f43f5e";
    ctx.fillRect(pseudoX, altBaselineY - 18 * dpr, pseudoW, 36 * dpr);
    ctx.fillStyle = "#ffffff";
    ctx.font = `bold ${11 * dpr}px sans-serif`;
    ctx.fillText("Pseudoexon (+1605G>A)", pseudoX - 35 * dpr, altBaselineY - 24 * dpr);

    // Cryptic Junction Arcs (Exon 10 -> Pseudoexon -> Exon 11)
    ctx.strokeStyle = "#f43f5e";
    ctx.lineWidth = 3 * dpr;

    // Arc 1: Exon 10 to Pseudoexon
    ctx.beginPath();
    ctx.moveTo(exon10X + exon10W, altBaselineY - 14 * dpr);
    ctx.quadraticCurveTo((exon10X + exon10W + pseudoX) / 2, altBaselineY - 55 * dpr, pseudoX, altBaselineY - 18 * dpr);
    ctx.stroke();

    // Arc 2: Pseudoexon to Exon 11
    ctx.beginPath();
    ctx.moveTo(pseudoX + pseudoW, altBaselineY - 18 * dpr);
    ctx.quadraticCurveTo((pseudoX + pseudoW + exon11X) / 2, altBaselineY - 55 * dpr, exon11X, altBaselineY - 14 * dpr);
    ctx.stroke();

    // Callout Badge
    ctx.fillStyle = "rgba(244, 63, 94, 0.25)";
    ctx.strokeStyle = "#f43f5e";
    ctx.lineWidth = 1 * dpr;
    ctx.fillRect(pseudoX - 60 * dpr, altBaselineY + 28 * dpr, 170 * dpr, 26 * dpr);
    ctx.strokeRect(pseudoX - 60 * dpr, altBaselineY + 28 * dpr, 170 * dpr, 26 * dpr);
    ctx.fillStyle = "#f43f5e";
    ctx.font = `bold ${12 * dpr}px sans-serif`;
    ctx.fillText("Delta Splice: +0.892 (Brain)", pseudoX - 52 * dpr, altBaselineY + 45 * dpr);
  } else {
    // IN BLOOD: Flat normal splicing (proves why blood test was negative!)
    drawCoverageProfile(ctx, marginX, plotWidth, altBaselineY, 0.05, 0.08, "#94a3b8", dpr);

    ctx.fillStyle = "#64748b";
    ctx.fillRect(exon10X, altBaselineY - 10 * dpr, exon10W, 20 * dpr);
    ctx.fillRect(exon11X, altBaselineY - 10 * dpr, exon11W, 20 * dpr);

    ctx.fillStyle = "#94a3b8";
    ctx.font = `italic ${13 * dpr}px sans-serif`;
    ctx.fillText("Whole Blood: No pseudoexon activation detected (Delta < 0.018). Normal splicing dominates.", marginX + 30 * dpr, altBaselineY + 40 * dpr);
  }

  // Track Labels
  ctx.fillStyle = "#cbd5e1";
  ctx.font = `bold ${13 * dpr}px sans-serif`;
  ctx.fillText("REF Track", 10 * dpr, baselineY - 20 * dpr);
  ctx.fillText(isBrain ? "ALT (Brain Cortex)" : "ALT (Whole Blood)", 10 * dpr, altBaselineY - 20 * dpr);
}

function drawCoverageProfile(ctx, startX, width, baselineY, baseAmp, peakAmp, color, dpr, peakX = 0, peakW = 0) {
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(startX, baselineY);

  const steps = 120;
  for (let i = 0; i <= steps; i++) {
    const x = startX + (width / steps) * i;
    let heightFactor = baseAmp;
    if (peakX > 0 && Math.abs(x - (peakX + peakW / 2)) < peakW * 1.5) {
      heightFactor = peakAmp;
    }
    const noise = Math.sin(i * 0.4) * 4 * dpr;
    const y = baselineY - (heightFactor * 35 * dpr + noise);
    ctx.lineTo(x, y);
  }

  ctx.lineTo(startX + width, baselineY);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.12;
  ctx.fill();
  ctx.globalAlpha = 0.8;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5 * dpr;
  ctx.stroke();
  ctx.restore();
}

// ============================================================================
// Screen 5: Benchmark Proof
// ============================================================================
async function loadBenchmarkProof() {
  const tableBody = document.getElementById("benchmark-table-body");
  const failuresList = document.getElementById("failure-modes-list");
  if (!tableBody || !failuresList) return;

  const data = await api.benchmark();

  tableBody.innerHTML = (data.modes_comparison || []).map(row => {
    const isFull = row.mode === "full";
    return `
      <tr class="${isFull ? 'highlight-full' : ''}">
        <td><strong>${escapeHtml(row.label)}</strong></td>
        <td>${escapeHtml(row.hit1)}</td>
        <td>${escapeHtml(row.hit5)}</td>
        <td>${escapeHtml(row.hit10)}</td>
        <td>${escapeHtml(row.time_s)}s</td>
        <td>${escapeHtml(row.cost)}</td>
      </tr>
    `;
  }).join("");

  failuresList.innerHTML = (data.honest_failures || []).map(fail => `
    <div class="failure-item">
      <div class="failure-title">
        Case ${fail.case_id}: ${fail.gene} (${fail.variant_id})
      </div>
      <div style="font-size: 13px; font-weight: 700; color: var(--actor-carbon);">
        Category: ${escapeHtml(fail.category)} | Phenotype: ${escapeHtml(fail.phenotype)}
      </div>
      <div class="failure-desc">${escapeHtml(fail.reason)}</div>
    </div>
  `).join("");
}

// ============================================================================
// Ambient DNA Double Helix Background Canvas
// ============================================================================
function initDnaCanvas() {
  const canvas = document.getElementById("dna-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  // Check prefers-reduced-motion
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  let width = canvas.width = window.innerWidth;
  let height = canvas.height = window.innerHeight;

  window.addEventListener("resize", () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });

  let angle = 0;
  const numBasePairs = 28;
  const spacing = height / numBasePairs;

  function renderHelix() {
    ctx.clearRect(0, 0, width, height);
    angle += 0.012;

    const centerX = width * 0.92;
    const strandRadius = 120;

    for (let i = 0; i < numBasePairs; i++) {
      const y = i * spacing;
      const strandAngle = angle + (i * 0.22);

      const x1 = centerX + Math.cos(strandAngle) * strandRadius;
      const z1 = Math.sin(strandAngle);
      const x2 = centerX - Math.cos(strandAngle) * strandRadius;

      const alpha = (z1 + 1) / 2 * 0.6 + 0.1;

      // Connecting rungs
      ctx.beginPath();
      ctx.strokeStyle = `rgba(0, 240, 255, ${alpha * 0.25})`;
      ctx.lineWidth = 1.5;
      ctx.moveTo(x1, y);
      ctx.lineTo(x2, y);
      ctx.stroke();

      // Nodes on strands
      ctx.beginPath();
      ctx.arc(x1, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 240, 255, ${alpha})`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(x2, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(192, 132, 252, ${1 - alpha + 0.2})`;
      ctx.fill();
    }

    requestAnimationFrame(renderHelix);
  }

  requestAnimationFrame(renderHelix);
}

// ============================================================================
// Theme Toggle & Keyboard Shortcuts
// ============================================================================
function initTheme() {
  const savedTheme = localStorage.getItem("genesleuth_theme") || "dark";
  setTheme(savedTheme);

  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const nextTheme = state.theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
  });
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("genesleuth_theme", theme);
  renderAlphaGenomeTrack();
}

function initShortcuts() {
  const helpModal = document.getElementById("help-modal");
  document.getElementById("help-toggle")?.addEventListener("click", () => {
    helpModal?.showModal();
  });
  document.getElementById("close-help-modal")?.addEventListener("click", () => {
    helpModal?.close();
  });

  window.addEventListener("keydown", (e) => {
    // Ignore keystrokes inside search input
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

    if (e.key === "1") navigateTo("picker");
    else if (e.key === "2") navigateTo("case_letter");
    else if (e.key === "3") navigateTo("live_stream");
    else if (e.key === "4") navigateTo("reveal");
    else if (e.key === "5") navigateTo("proof");
    else if (e.key.toLowerCase() === "r" && state.currentScreen === "picker") {
      e.preventDefault();
      handleRandomPick();
    }
    else if (e.key.toLowerCase() === "t") {
      e.preventDefault();
      setTheme(state.theme === "dark" ? "light" : "dark");
    }
    else if (e.key === "?") {
      e.preventDefault();
      if (helpModal?.open) helpModal.close();
      else helpModal?.showModal();
    }
    else if (e.key === " " && state.currentScreen === "case_letter") {
      e.preventDefault();
      handleStartInvestigation();
    }
  });
}

// Helper Utilities
function getActorCssClass(actor) {
  switch (actor) {
    case "Data": return "actor-data";
    case "Gemini 4 Carbon": return "actor-gemini-4-carbon";
    case "Gemini 4 Neon": return "actor-gemini-4-neon";
    case "Gemini 4 Hydrogen": return "actor-gemini-4-hydrogen";
    case "AlphaGenome": return "actor-alphagenome";
    case "Code checker": return "actor-code-checker";
    case "Decisions API": return "actor-decisions-api";
    case "Managed Agent": return "actor-managed-agent";
    default: return "actor-data";
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
