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
    row.append(node("strong", option.gene), node("span", option.condition || option.label, "condition"),
      node("span", option.region, "region"));
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
    const bar = node("div", undefined, "bar");
    bar.style.setProperty("--width", `${Math.max(2, Math.sqrt(value / largest) * 100)}%`);
    item.append(node("strong", count.format(value)), node("span", name), bar);
    return item;
  }));
}

function openSession(session) {
  state.session = session;
  displayFunnel(session);
  byId("build-time").textContent = `Built in ${session.build_seconds.toFixed(1)} s`;
  byId("letter").src = session.letter_url;
  byId("letter-link").href = session.letter_url;
  byId("case-note").textContent = !session.uploaded
    ? "The planted variant is one of the suspects below. Nothing here says which."
    : session.mode === "fallback"
      ? "This is a prepared demo genome, not your upload. Nothing is revealed for it."
      : "Your uploaded genome, filtered to rare variants in the 58 epilepsy panel genes. There is no hidden answer.";
  byId("reveal-button").hidden = Boolean(session.uploaded);
  byId("case").hidden = false;
  byId("picker").hidden = true;
}

async function uploadCase(event) {
  event.preventDefault();
  const vcf = byId("vcf-file").files[0];
  const pdf = byId("pdf-file").files[0];
  if (!vcf || !pdf || byId("upload-submit").disabled) return;
  const version = ++state.version;
  byId("upload-submit").disabled = true;
  byId("random").disabled = true;
  byId("picker").setAttribute("aria-busy", "true");
  notify("Reading your variant file and filtering to rare panel variants. This can take up to a minute…");
  try {
    const form = new FormData();
    form.append("vcf", vcf);
    form.append("referral_pdf", pdf);
    const response = await fetch("/api/cases/upload", { method: "POST", body: form });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === "string" ? error.detail : `Upload failed (${response.status}).`);
    }
    const session = await response.json();
    if (version !== state.version) return;
    openSession(session);
    if (session.mode === "fallback") {
      notify(`Using a prepared demo genome because: ${session.reason || "the upload could not be processed"}`, true);
    } else {
      notify();
    }
    focusSection("case-title");
  } catch (error) {
    if (version === state.version) notify(error.message, true);
  } finally {
    if (version === state.version) {
      byId("upload-submit").disabled = false;
      byId("random").disabled = false;
      byId("picker").removeAttribute("aria-busy");
    }
  }
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
    openSession(session);
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
    const row = node("li", undefined, [emphasis, label || ""].join(" ").trim());
    const detail = event.step === "check" && data.text ? data.text : event.summary;
    const summary = node("div", detail);
    const reason = data.reason || data.error;
    if (typeof reason === "string" && reason !== detail) summary.append(node("span", reason, "reason"));
    row.append(node("time", `${Number(event.t).toFixed(1)} s`), node("span", event.actor, `actor ${label || ""}`), summary);
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
    byId("investigate").hidden = followup;
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
    if (version === state.version) {
      byId("investigate").hidden = true;
      beginRun(run, false);
    }
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
    line.append(node(supported ? "span" : "s", claim.text));
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
  byId("result-time").textContent = `Case built in ${result.build_seconds.toFixed(1)} s, investigated in ${result.investigation_seconds.toFixed(1)} s`;
  byId("phenotypes").replaceChildren(...result.phenotypes.map((phenotype) => {
    const chip = node("span", phenotype.label, "phenotype");
    chip.title = [phenotype.hpo_id, phenotype.source_quote].filter(Boolean).join(" · ");
    return chip;
  }));
  const rows = [];
  const topScore = Math.max(0, ...result.ranked.map((item) => Number.isFinite(item.score) ? item.score : 0));
  for (const item of result.ranked) {
    const variant = item.variant;
    const tissueName = tissueNames.get(item.tissue) || item.tissue || "";
    const row = node("tr", undefined, `${item.rank === 1 ? "top " : ""}${tissueKind(tissueName)}`);
    row.dataset.variant = variant.variant_id;
    const gene = node("td");
    gene.append(node("span", variant.gene || "—", "gene"), node("small", variant.variant_id, "variant-id"));
    const score = node("td");
    const scoreWrap = node("div", undefined, "score");
    const bar = node("div", undefined, "bar");
    if (Number.isFinite(item.score) && topScore > 0) bar.style.setProperty("--pct", `${Math.max(2, item.score / topScore * 100)}%`);
    scoreWrap.append(node("span", Number.isFinite(item.score) ? item.score.toFixed(3) : "—"), bar);
    score.append(scoreWrap);
    const tissue = node("td");
    tissue.append(node("span", tissueName || "—", tissueName ? "tissue" : ""));
    row.append(node("td", String(item.rank), "rank"), gene, node("td", variant.region),
      node("td", (variant.consequence || "—").replaceAll("_", " "), "consequence"), score, tissue);
    const button = node("button", undefined, "evidence-button");
    button.append(node("span", "Evidence"));
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
  if (result.ranked.length) {
    showLocus("top", byId("top-locus"), "The top candidate");
    showPlot("top", byId("top-plot"), "Top candidate in brain and blood");
  }
  highlight();
  focusSection("ranking-title");
}

function tissueKind(name) {
  const text = String(name).toLowerCase();
  if (/brain|cortex|cereb|hippocamp|neuron|neural|glia|caudate|putamen|amygdala|hypothalam|spinal/.test(text)) return "brain";
  if (/blood|leukocyte|lymph|monocyte|neutrophil|erythro|plasma|t cell|b cell/.test(text)) return "blood";
  return text ? "other" : "";
}

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, text) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  if (text !== undefined) element.textContent = text;
  return element;
}

function drawLocus(container, locus, title) {
  const W = 960, H = 196, left = 64, right = 24;
  const span = Math.max(1, locus.end - locus.start);
  const x = (pos) => left + (pos - locus.start) / span * (W - left - right);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  root.append(svg("title", {}, `${locus.gene} locus with the candidate variant and predicted effect in brain and blood.`));
  const tracks = [["brain", "Brain", locus.tracks.brain], ["blood", "Blood", locus.tracks.blood]];
  const peak = Math.max(1e-6, ...tracks.flatMap(([, , values]) => values.map(Math.abs)));
  tracks.forEach(([key, label, values], index) => {
    const base = 54 + index * 52;
    const height = 40;
    const step = (W - left - right) / Math.max(1, values.length - 1);
    const points = values.map((value, i) => `${(left + i * step).toFixed(1)},${(base - Math.abs(value) / peak * height).toFixed(1)}`);
    root.append(svg("path", { class: `track ${key}`, d: `M${left},${base} L${points.join(" L")} L${W - right},${base} Z` }));
    root.append(svg("line", { class: "baseline", x1: left, x2: W - right, y1: base, y2: base }));
    root.append(svg("text", { class: "track-label", x: left - 10, y: base - 4, "text-anchor": "end" }, label));
  });
  const geneY = 150;
  root.append(svg("line", { class: "intron", x1: x(locus.start), x2: x(locus.end), y1: geneY, y2: geneY }));
  for (const exon of locus.exons) {
    const width = Math.max(3, x(exon.end) - x(exon.start));
    root.append(svg("rect", { class: exon.brain_specific ? "exon brain-specific" : "exon", x: x(exon.start), y: geneY - 9, width, height: 18, rx: 1.5 }));
  }
  const needle = x(locus.variant_pos);
  root.append(svg("line", { class: "needle", x1: needle, x2: needle, y1: 22, y2: geneY + 18 }));
  root.append(svg("circle", { class: "needle-head", cx: needle, cy: 22, r: 4 }));
  const anchor = needle > W - 200 ? "end" : needle < 200 ? "start" : "middle";
  root.append(svg("text", { class: "needle-label", x: needle, y: 14, "text-anchor": anchor }, locus.variant_id));
  root.append(svg("text", { class: "gene-label", x: left, y: geneY + 36 }, `${locus.gene}, ${locus.strand === "-" ? "read right to left" : "read left to right"}`));
  const specific = locus.exons.find((exon) => exon.brain_specific);
  if (specific) {
    root.append(svg("text", { class: "exon-label", x: x((specific.start + specific.end) / 2), y: geneY + 36, "text-anchor": "middle" }, "brain-specific exon"));
  }
  root.append(svg("text", { class: "scale", x: W - right, y: geneY + 36, "text-anchor": "end" }, `${count.format(span)} bases shown`));
  container.replaceChildren(node("h3", `${title} sits here in ${locus.gene}`), root);
  const caption = node("figcaption");
  const brainPeak = Math.max(...locus.tracks.brain.map(Math.abs));
  const bloodPeak = Math.max(...locus.tracks.blood.map(Math.abs));
  caption.textContent = locus.caption || (brainPeak > 3 * bloodPeak ?
    `${locus.gene}: the predicted effect shows in brain and barely in blood, which is why a blood test could miss it.` :
    `${locus.gene}: predicted effect in brain and blood near the variant.`);
  container.append(caption);
  container.hidden = false;
}

async function showLocus(target, container, title) {
  const version = state.version;
  container.hidden = true;
  try {
    const locus = await api(casePath(`locus?target=${target}`));
    if (version !== state.version || !locus?.exons?.length || !locus.tracks) return;
    drawLocus(container, locus, title);
  } catch {
    // The locus view is optional; the ranking and plots stand on their own.
  }
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
    byId("reveal-detail").replaceChildren(node("span", truth.gene, "gene"), node("span", truth.condition),
      node("span", truth.hidden_variant_id, "mono"));
    byId("reveal").hidden = false;
    highlight();
    focusSection("reveal-title");
    if (rank !== 1) showLocus("hidden", byId("hidden-locus"), "The hidden variant");
    showPlot("hidden", byId("hidden-plot"), "Hidden variant in brain and blood", result.plot);
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
  byId("look-variant").textContent = `${variant.gene || "Variant"} — ${variant.variant_id}`;
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
  for (const id of ["case", "investigation", "results", "reveal", "top-locus", "hidden-locus"]) byId(id).hidden = true;
  for (const id of ["random", "investigate", "reveal-button"]) byId(id).disabled = false;
  byId("reveal-button").hidden = false;
  byId("investigate").hidden = false;
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
byId("upload-form").addEventListener("submit", uploadCase);
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
const swap = document.querySelector(".swap");
if (swap) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  setTimeout(() => { swap.textContent = "A"; }, reduced ? 0 : 1200);
}
