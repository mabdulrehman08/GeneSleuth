const byId = (id) => document.getElementById(id);
const count = new Intl.NumberFormat();
const actors = [
  ["carbon", "carbon"], ["neon", "neon"], ["hydrogen", "hydrogen"],
  ["alphagenome", "alphagenome"], ["decision", "decisions"],
  ["managed", "managed"], ["data", "data"],
];
const state = {
  options: [], session: null, version: 0, source: null, timer: null,
  review: {}, dropped: new Map(), tissues: new Map(),
};

function node(tag, content, className) {
  const element = document.createElement(tag);
  if (content !== undefined) element.textContent = content;
  if (className) element.className = className;
  return element;
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  if (response.ok) return response.json();
  const error = await response.json().catch(() => ({}));
  throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${response.status}).`);
}

function casePath(suffix) {
  return `/api/cases/${encodeURIComponent(state.session.case_id)}/${suffix}`;
}

function notify(message = "", error = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.classList.toggle("error", error);
  notice.hidden = !message;
}

function focusSection(id) {
  byId(id).focus({ preventScroll: true });
  byId(id).scrollIntoView({ block: "start" });
}

function displayOptions() {
  const words = byId("search").value.toLowerCase().trim().split(/\s+/);
  const matches = state.options.filter((option) => {
    const text = [option.gene, option.region, option.condition, option.label].join(" ").toLowerCase();
    return words.every((word) => text.includes(word));
  });
  byId("option-count").textContent = `${count.format(matches.length)} cases`;
  const rows = matches.map((option) => {
    const row = node("button", undefined, "option");
    row.type = "button";
    row.append(node("strong", option.gene), node("span", option.region, "region muted"),
      node("span", option.condition || option.label), node("span", "→", "pick-arrow"));
    row.lastChild.setAttribute("aria-hidden", "true");
    row.addEventListener("click", () => build(option.option_id));
    return row;
  });
  byId("options").replaceChildren(...rows);
}

async function loadOptions() {
  try {
    state.options = await api("/api/options");
    displayOptions();
  } catch (error) {
    byId("option-count").textContent = "Picker unavailable";
    notify(error.message, true);
  }
}

function displayFunnel(session) {
  const funnel = session.funnel;
  const stages = [
    ["Variants in panel regions", funnel.variants_in_panel_regions],
    ["Rare variants", funnel.rare ?? funnel["rare_af_lt_0.001"] ?? funnel["rare_af_lt_0.01"]],
    ["Suspects for investigation", session.n_suspects],
  ].filter(([, value]) => Number.isFinite(value));
  const largest = Math.max(1, ...stages.map(([, value]) => value));
  byId("funnel").replaceChildren(...stages.map(([name, value]) => {
    const item = node("li");
    item.style.setProperty("--width", `${Math.max(3, value / largest * 100)}%`);
    item.append(node("strong", count.format(value)), node("span", name));
    return item;
  }));
}

async function build(optionId) {
  if (byId("random").disabled) return;
  const version = ++state.version;
  byId("random").disabled = true;
  byId("picker").setAttribute("aria-busy", "true");
  notify("Preparing the background genome and referral…");
  try {
    const session = await api("/api/cases", { option_id: optionId });
    if (version !== state.version) return;
    state.session = session;
    displayFunnel(session);
    byId("build-time").textContent = `Built in ${session.build_seconds.toFixed(1)} s`;
    byId("letter").src = session.letter_url;
    byId("letter-link").href = session.letter_url;
    byId("case").hidden = false;
    byId("picker").hidden = true;
    notify();
    focusSection("case-title");
  } catch (error) {
    if (version === state.version) notify(error.message, true);
  } finally {
    if (version === state.version) {
      byId("random").disabled = false;
      byId("picker").removeAttribute("aria-busy");
    }
  }
}

function stopStream() {
  state.source?.close();
  clearInterval(state.timer);
  state.source = null;
  state.timer = null;
}

function beginRun(run, followup) {
  stopStream();
  const version = state.version;
  const started = performance.now();
  const timeline = byId("timeline");
  const checked = new Map();
  let ag = 0;
  let calls = 0;
  let budget = state.session.alphagenome_budget;
  let revision = false;
  const rejectedRows = new Map();
  const showElapsed = () => { byId("elapsed").textContent = `${((performance.now() - started) / 1000).toFixed(1)} s`; };
  const showCalls = () => {
    byId("ag-count").textContent = `${ag} / ${budget}`;
    byId("tool-count").textContent = count.format(calls);
  };
  showElapsed();
  showCalls();
  state.timer = setInterval(showElapsed, 250);
  timeline.replaceChildren();
  for (const id of ["check-count", "reject-count", "triage-count", "cost"]) {
    byId(id).textContent = id === "triage-count" ? "—" : id === "cost" ? "" : "0";
  }
  byId("investigation").hidden = false;
  byId("connection").textContent = followup ? "Continuing the existing investigation…" : "Connecting to the investigation…";
  state.followup = followup;
  byId("results").inert = followup;
  focusSection("timeline-title");
  const source = new EventSource(casePath(`events?run=${run}`));
  state.source = source;
  source.onopen = () => { byId("connection").textContent = "Live"; };
  source.onerror = () => { byId("connection").textContent = "Connection interrupted. Reconnecting…"; };
  source.addEventListener("trace", (message) => {
    const event = JSON.parse(message.data);
    const data = event.data || {};
    const actor = event.actor.toLowerCase();
    const rejected = event.step === "check" && ["unsupported", "unsure"].includes(data.verdict);
    const revised = event.step === "check" && data.verdict === "supported" && revision;
    const before = timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 56;
    if (event.step === "revise") revision = true;
    const label = actors.find(([key]) => actor.includes(key))?.[1];
    const failed = rejected || event.step === "error";
    const emphasis = failed ? "rejected" : revised ? "revised" : data.fallback_to ? "fallback" : "";
    const row = node("li", undefined, emphasis);
    const detail = event.step === "check" && data.text ? data.text : event.summary;
    const summary = node("div", detail);
    const reason = data.reason || data.error;
    if (typeof reason === "string" && reason !== detail) summary.append(node("span", reason, "reason"));
    row.append(node("time", `+${Number(event.t).toFixed(1)}s`), node("span", event.actor, `actor ${label || ""}`), summary);
    if (revised && rejectedRows.has(data.variant_id)) {
      rejectedRows.get(data.variant_id).after(row);
      rejectedRows.delete(data.variant_id);
    } else {
      timeline.append(row);
    }
    if (rejected && data.variant_id) {
      rejectedRows.set(data.variant_id, row);
      if (!state.dropped.has(data.variant_id)) state.dropped.set(data.variant_id, new Map());
      state.dropped.get(data.variant_id).set(data.claim_id, data);
    }
    if (before) timeline.scrollTop = timeline.scrollHeight;
    if (Number.isFinite(data.alphagenome_budget)) budget = data.alphagenome_budget;
    if (Number.isFinite(data.n_alphagenome_calls)) ag = data.n_alphagenome_calls;
    else if (event.step === "alphagenome" && data.call_id) ag += 1;
    if (Number.isFinite(data.n_tool_calls)) calls = data.n_tool_calls;
    else if (["tool", "alphagenome"].includes(event.step) && data.call_id) calls += 1;
    showCalls();
    if (actor.includes("decision") && event.step === "plan" && Number.isFinite(data.n_suspects)) {
      byId("triage-count").textContent = count.format(data.n_suspects);
    }
    if (Number.isFinite(data.n_claims_checked)) byId("check-count").textContent = count.format(data.n_claims_checked);
    if (Number.isFinite(data.n_claims_rejected)) byId("reject-count").textContent = count.format(data.n_claims_rejected);
    if (event.step === "check" && data.claim_id && data.verdict) {
      checked.set(`${data.claim_id}/${revision}/${event.t}`, data.verdict);
      if (!Number.isFinite(data.n_claims_checked)) byId("check-count").textContent = count.format(checked.size);
      if (!Number.isFinite(data.n_claims_rejected)) byId("reject-count").textContent = count.format([...checked.values()].filter((value) => value !== "supported").length);
    }
    if (Number.isFinite(data.cost_usd)) displayCost(data.cost_usd);
  });
  source.addEventListener("done", (message) => {
    if (version !== state.version) return;
    const result = JSON.parse(message.data);
    stopStream();
    state.followup = false;
    byId("results").inert = false;
    byId("connection").textContent = "Investigation complete";
    ag = result.n_alphagenome_calls;
    calls = result.n_tool_calls;
    showCalls();
    byId("check-count").textContent = count.format(result.n_claims_checked);
    byId("reject-count").textContent = count.format(result.n_claims_rejected);
    byId("elapsed").textContent = `${result.investigation_seconds.toFixed(1)} s`;
    displayCost(result.cost_usd);
    showResults(result);
  });
  source.addEventListener("failed", (message) => {
    if (version !== state.version) return;
    stopStream();
    state.followup = false;
    byId("results").inert = false;
    byId("connection").textContent = "Investigation interrupted";
    byId("investigate").disabled = followup;
    notify(JSON.parse(message.data).message, true);
  });
}

function displayCost(cost) {
  byId("cost").textContent = Number.isFinite(cost) ? `Estimated Gemini cost $${cost.toFixed(4)}` : "Gemini cost unavailable";
}

async function investigate() {
  const version = state.version;
  byId("investigate").disabled = true;
  notify();
  try {
    const { run } = await api(casePath("investigate"), {});
    if (version === state.version) beginRun(run, false);
  } catch (error) {
    if (version === state.version) {
      byId("investigate").disabled = false;
      notify(error.message, true);
    }
  }
}

function evidence(item, ledger) {
  const block = node("div", undefined, "evidence-details");
  const variant = item.variant;
  const verdicts = new Map(item.verdicts.map((check) => [check.claim_id, check]));
  const claims = node("ul", undefined, "claims");
  const shown = new Set();
  const supportedText = new Set(item.claims.filter((claim) =>
    verdicts.get(claim.claim_id)?.verdict === "supported").map((claim) => claim.text));
  if (item.summary) block.append(node("p", item.summary));
  for (const claim of item.claims) {
    const verdict = verdicts.get(claim.claim_id);
    const supported = verdict?.verdict === "supported";
    const line = node("li", undefined, supported ? "supported" : "dropped");
    line.append(node(supported ? "span" : "s", `${supported ? "✓ " : ""}${claim.text}`));
    if (claim.cited_call_ids.length) {
      const refs = node("details");
      refs.append(node("summary", `Evidence ${claim.cited_call_ids.join(", ")}`));
      for (const id of claim.cited_call_ids) {
        const call = ledger.get(id);
        if (call) refs.append(node("p", `${id} · ${call.tool} · ${call.result_summary}`));
      }
      line.append(refs);
    }
    if (!supported) line.append(node("div", verdict?.reason || "No supporting verdict.", "muted"));
    claims.append(line);
    shown.add(claim.claim_id);
  }
  for (const [id, dropped] of state.dropped.get(variant.variant_id) || []) {
    if (shown.has(id) || supportedText.has(dropped.text)) continue;
    const line = node("li", undefined, "dropped");
    line.append(node("s", dropped.text || "Claim rejected"), node("div", dropped.reason || "", "muted"));
    claims.append(line);
  }
  block.append(claims);
  const controls = node("div", undefined, "actions");
  const status = node("span", "", "muted");
  status.setAttribute("role", "status");
  for (const [action, label] of [["accept", "Accept"], ["reject", "Reject"]]) {
    const button = node("button", label, "button quiet");
    button.type = "button";
    button.addEventListener("click", async () => {
      const version = state.version;
      try {
        const result = await api(casePath("review"), { variant_id: variant.variant_id, action });
        if (version === state.version) {
          state.review = result.review;
          status.textContent = action === "accept" ? "Accepted" : "Rejected";
          controls.querySelectorAll("[aria-pressed]").forEach((entry) => entry.setAttribute("aria-pressed", String(entry === button)));
        }
      } catch (error) {
        if (version === state.version) status.textContent = error.message;
      }
    });
    button.setAttribute("aria-pressed", String(state.review[variant.variant_id] === action));
    controls.append(button);
  }
  const current = state.review[variant.variant_id];
  status.textContent = current === "accept" ? "Accepted" : current === "reject" ? "Rejected" : "";
  const again = node("button", "Look again", "button quiet");
  again.type = "button";
  again.addEventListener("click", () => openReview(variant));
  controls.append(again, status);
  block.append(controls);
  return block;
}

function showResults(result) {
  state.review = result.review;
  const ledger = new Map(result.tool_calls.map((call) => [call.call_id, call]));
  const tissueNames = new Map();
  for (const call of result.tool_calls) {
    if (call.result?.tissue && call.result?.tissue_name) {
      tissueNames.set(call.result.tissue, call.result.tissue_name);
    }
  }
  byId("result-time").textContent = `Case ${result.build_seconds.toFixed(1)} s · Investigation ${result.investigation_seconds.toFixed(1)} s`;
  byId("phenotypes").replaceChildren(...result.phenotypes.map((phenotype) => {
    const chip = node("span", phenotype.label, "phenotype");
    chip.title = [phenotype.hpo_id, phenotype.source_quote].filter(Boolean).join(" · ");
    return chip;
  }));
  const rows = [];
  for (const item of result.ranked) {
    const variant = item.variant;
    const row = node("tr");
    row.dataset.variant = variant.variant_id;
    const gene = node("td");
    gene.append(node("strong", variant.gene || "—"), node("small", variant.variant_id, "variant-id"));
    row.append(node("td", String(item.rank)), gene, node("td", variant.region),
      node("td", (variant.consequence || "—").replaceAll("_", " ")),
      node("td", Number.isFinite(item.score) ? item.score.toFixed(3) : "—"),
      node("td", tissueNames.get(item.tissue) || item.tissue || "—"));
    const button = node("button", "Details +", "evidence-button");
    button.type = "button";
    const detailsRow = node("tr", undefined, "evidence-row");
    detailsRow.id = `evidence-${item.rank}`;
    detailsRow.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", detailsRow.id);
    button.setAttribute("aria-label", `Evidence for ${variant.gene || variant.variant_id}, rank ${item.rank}`);
    const details = node("td");
    details.colSpan = 7;
    details.append(evidence(item, ledger));
    detailsRow.append(details);
    button.addEventListener("click", () => {
      detailsRow.hidden = !detailsRow.hidden;
      button.setAttribute("aria-expanded", String(!detailsRow.hidden));
      button.textContent = detailsRow.hidden ? "Details +" : "Details −";
    });
    const cell = node("td");
    cell.append(button);
    row.append(cell);
    rows.push(row, detailsRow);
  }
  byId("ranking").replaceChildren(...rows);
  byId("download").href = casePath("report");
  byId("results").hidden = false;
  byId("top-plot").hidden = !result.ranked.length;
  if (result.ranked.length) showPlot("top", byId("top-plot"), "Top candidate · Brain and blood");
  highlight();
  focusSection("ranking-title");
}

function highlight() {
  for (const row of byId("ranking").querySelectorAll("[data-variant]")) {
    row.classList.toggle("row-highlight", row.dataset.variant === state.revealedVariant);
  }
}

async function showPlot(target, container, title, first) {
  const version = state.version;
  const token = Symbol();
  container.plotRequest = token;
  container.replaceChildren(node("h3", title), node("p", "Generating AlphaGenome tracks…", "muted"));
  try {
    let plot = first || await api(casePath(`plot?target=${target}`));
    for (let attempt = 0; attempt < 46 && plot.status === "pending"; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      if (version !== state.version || container.plotRequest !== token) return;
      plot = await api(casePath(`plot?target=${target}`));
    }
    if (version !== state.version || container.plotRequest !== token) return;
    if (plot.status === "ready") {
      const image = node("img");
      image.src = plot.url;
      image.alt = "AlphaGenome predicted reference and alternate allele tracks in brain and blood.";
      const link = node("a");
      link.href = plot.url;
      link.target = "_blank";
      link.rel = "noopener";
      link.append(image);
      container.lastElementChild.replaceWith(link);
    } else {
      container.lastElementChild.textContent = plot.message || "AlphaGenome tracks are still pending.";
    }
  } catch (error) {
    if (version === state.version && container.plotRequest === token) {
      container.lastElementChild.textContent = error.message;
    }
  }
}

async function reveal() {
  const version = state.version;
  byId("reveal-button").disabled = true;
  try {
    const result = await api(casePath("reveal"), {});
    if (version !== state.version) return;
    const { truth, rank, n_suspects: suspects } = result;
    state.revealedVariant = truth.hidden_variant_id;
    byId("reveal-title").textContent = rank ? `Hidden variant ranked #${rank} of ${suspects} suspects` :
      result.passed_filter ? `Hidden variant was outside the top 10 of ${suspects} suspects` : "Hidden variant did not pass the filter";
    byId("reveal-detail").textContent = `${truth.gene} · ${truth.condition} · ${truth.hidden_variant_id}`;
    byId("reveal").hidden = false;
    highlight();
    focusSection("reveal-title");
    showPlot("hidden", byId("hidden-plot"), "Hidden variant · Brain and blood", result.plot);
  } catch (error) {
    if (version === state.version) {
      notify(error.message, true);
      byId("reveal-button").disabled = false;
    }
  }
}

let tissueTimer;
let tissueQuery = 0;
function searchTissues() {
  const request = ++tissueQuery;
  const query = byId("tissue").value.trim();
  clearTimeout(tissueTimer);
  tissueTimer = setTimeout(async () => {
    try {
      const tissues = await api(`/api/tissues?query=${encodeURIComponent(query)}`);
      if (request !== tissueQuery || !byId("look-dialog").open) return;
      state.tissues = new Map(tissues.slice(0, 50).map(({ ontology_id, name }) => [name, ontology_id]));
      byId("tissue-options").replaceChildren(...Array.from(state.tissues, ([name, id]) => {
        const option = node("option");
        option.value = name;
        option.label = id;
        return option;
      }));
    } catch {
      if (request === tissueQuery && byId("look-dialog").open) {
        byId("look-message").textContent = "Tissue suggestions unavailable. Enter a condition or a question.";
      }
    }
  }, 240);
}

function openReview(variant) {
  state.reviewVariant = variant.variant_id;
  byId("look-variant").textContent = `${variant.gene || "Variant"} · ${variant.variant_id}`;
  byId("tissue").value = "";
  byId("question").value = "";
  byId("look-message").textContent = "";
  byId("look-dialog").showModal();
  searchTissues();
}

async function followup(event) {
  event.preventDefault();
  const version = state.version;
  const tissue = byId("tissue").value.trim();
  const question = byId("question").value.trim();
  byId("look-submit").disabled = true;
  try {
    const { run } = await api(casePath("look-again"), {
      variant_id: state.reviewVariant, tissue: state.tissues.get(tissue) || tissue || null,
      question: question || null,
    });
    if (version !== state.version) return;
    byId("look-dialog").close();
    notify();
    beginRun(run, true);
  } catch (error) {
    if (version === state.version) byId("look-message").textContent = error.message;
  } finally {
    byId("look-submit").disabled = false;
  }
}

function reset() {
  ++state.version;
  stopStream();
  state.session = null;
  state.review = {};
  state.dropped.clear();
  state.revealedVariant = null;
  state.followup = false;
  for (const id of ["case", "investigation", "results", "reveal"]) byId(id).hidden = true;
  for (const id of ["random", "investigate", "reveal-button"]) byId(id).disabled = false;
  byId("picker").hidden = false;
  byId("picker").removeAttribute("aria-busy");
  byId("results").inert = false;
  byId("letter").removeAttribute("src");
  byId("look-dialog").close();
  notify();
  focusSection("picker-title");
}

byId("search").addEventListener("input", displayOptions);
byId("random").addEventListener("click", () => build(null));
byId("investigate").addEventListener("click", investigate);
byId("reveal-button").addEventListener("click", reveal);
byId("reset").addEventListener("click", reset);
byId("tissue").addEventListener("input", searchTissues);
byId("look-form").addEventListener("submit", followup);
byId("look-cancel").addEventListener("click", () => byId("look-dialog").close());
document.addEventListener("keydown", (event) => {
  if (event.key.toLowerCase() === "r" && !event.metaKey && !event.ctrlKey && !event.altKey &&
      !byId("look-dialog").open && !event.target.closest("input, textarea, [contenteditable]")) reset();
});
loadOptions();
