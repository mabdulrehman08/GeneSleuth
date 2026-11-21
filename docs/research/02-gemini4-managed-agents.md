# 02 — Gemini 4 + Managed Agents research brief (GeneSleuth)

Researched 2026-11-19. Event: Sat Nov 21, 9 AM–10 PM EST, NYC. "UNVERIFIED" means I couldn't confirm it in official docs.

## Recommended design hooks (the "Why Gemini 4?" answer)

1. **Managed Agents (Antigravity agent + `agents.create`) as the investigator runtime.** We register a saved agent called "genesleuth" (an `AGENTS.md` playbook plus a `SKILL.md` per tool: ClinVar, gnomAD, HPO, AlphaGenome). Each case then runs as one `interactions.create(..., environment="remote")` call that forks a clean sandbox where the agent writes and runs its own Python over the ~400 variants. This is the strongest claim on the $5k prize.
2. **Hooks (`pre_tool_execution`) plus a custom `submit_report` function as the deterministic citation checker.** A hook gates `write_to_file` on `report.md`. Whenever a claim lacks a tool-result ID it returns `deny` with a reason, and the model "sees your rejection reason and adapts" in the same turn. The authoritative check also runs client-side when `submit_report` comes back (see gotchas).
3. **Unified 1M-token window and long decode on `gemini-4-argon`/`gemini-4-carbon`.** The full variant table, the HPO term set, and every raw tool response all fit in one context, so the agent can cite across all of them. `background=True` lets a long final report go past 64K tokens, using server-side continuation hops.
4. **Thinking levels as a per-role knob.** Planning and hypothesis ranking run on Carbon or Argon at `high`. Routine variant lookups run on Hydrogen at `low`/`medium`. The model splits are locked per saved agent, so we can show the "clear job per model" story on one slide.
5. **SSE streaming of agent steps.** `stream=True` emits step deltas (reasoning, tool calls, code execution) plus `step.stop` with usage. We pipe that straight into the live UI. A `post_tool_execution` HTTP hook can also send an audit event for every code run.

Supporting point for the theme: DeepMind's Minecraft result showed four Argon agents running a 27-hour unattended loop that wrote 2,783 programs. That is the same "agent writes its own analysis code" pattern, applied to a genome.

## 1. What's new in Gemini 4 vs Gemini 3

- **Models** ([models](https://aistudio.google.com/docs/models), [changelog](https://aistudio.google.com/docs/changelog)):
  - `gemini-4-carbon`: strongest reasoning, spends more thinking tokens.
  - `gemini-4-argon`: GA Oct 13 2026. Efficient frontier reasoning, default thinking `medium`.
  - `gemini-4-neon`: GA Nov 18 2026. $3/$15 per 1M tokens, levels low/medium/high/xhigh.
  - `gemini-4-hydrogen`: fast, $1.50/$7.50, **has a Free tier**, default `high`, adds `xhigh`.
  - **There is no "Gemini 4 Flash/Pro" naming.** The Gemini 3 line continues as `gemini-3.8-flash`, `gemini-3.6-flash`, and so on.
- **Pricing for Argon and Carbon** ([what's new Argon](https://aistudio.google.com/docs/whats-new-gemini-4-argon)):
  - Intro price is $2 in / $10 out through Nov 30, then $4 / $20.
  - Neither model is on the Free tier.
- **Context**: one unified 1,048,576-token window shared by input, thinking, and output. Gemini 3.8 Flash had 1M input plus 64K output.
- **Long decode and the continuation token**: one synchronous hop stops at 65,536 tokens, or 32,768 for non-streaming raw HTTP. The response then has `finishReason: CONTINUATION` and an opaque `continuationToken`, an encrypted hash of the prompt plus the generation so far. To continue, you resend the *identical* request with that token and do not append partial text. The GenAI SDK does this automatically (`automatic_continuation`), and the Interactions API's `background=True` does it server-side. Streaming emits checkpoint tokens every 5K tokens after the first 32K. Sources: [Vertex inference ref](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/inference), [long decode guide](https://aistudio.google.com/docs/long-decode). The 5K checkpoint detail comes from a [Medium post](https://medium.com/google-cloud/gemini-4-argon-long-decode-part-2-handling-empty-thinking-only-hops-and-5k-stream-checkpoints-4760e6024769) and is UNVERIFIED officially.
- **Breaking changes**:
  - `temperature`, `top_p`, and `top_k` are ignored, and on Hydrogen they can return a 400.
  - Explicit context caching has been removed. Implicit caching (≥4,096-token prompts) gives 95% off.
  - Hydrogen rejects the `minimal` thinking level.
  - Docs recommend `max_output_tokens` ≥32K and client timeouts ≥15 minutes.
- **Hydrogen claims** ([what's new Hydrogen](https://aistudio.google.com/docs/whats-new-gemini-4-hydrogen)): more than 5x fewer fabricated claims than 3.8 Flash ("flags missing context instead of guessing"), parallel batched read/search tool calls, and better recovery when tool calls fail. These are useful framing points for an evidence-grounded report.
- **Recent API features**:
  - Function responses can now carry files, with slicing by page, cell range, or time interval (Nov 18).
  - Agentic video understanding is GA.
  - Built-in tools combined with custom functions in one call dates from Mar 2026, so it is a Gemini 3-era feature, not new in 4.
- **Interactions API** is the primary surface. Server-side state goes through `previous_interaction_id`.
- **Deferred tier** (Nov 16): 50% off, 24-hour target, `background=true`. Good for an offline benchmark ([releasebot summary](https://releasebot.io/updates/google); UNVERIFIED against the primary page).
- **Minecraft demo is real**: four Argon agents running Mineflayer bots, 27 h 14 m, 2,783 programs, 229 messages, 605 deaths ([arXiv 2610.22319](https://arxiv.org/abs/2610.22319), [DeepMind post](https://x.com/GoogleDeepMind/status/2111127991401247033)). Tom's Hardware estimates about $520 in tokens.
- **Free-tier RPM/RPD for Gemini 4** isn't published in the docs. It is shown only per project at [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit).

## 2. Managed Agents

- **What it is**: Gemini API (AI Studio). It launched May 19 2026 and is in **Public Preview** ([blog](https://blog.google/innovation-and-ai/technology/developers-tools/managed-agents-gemini-api/), [overview](https://aistudio.google.com/docs/agents)). An enterprise variant runs on Gemini Enterprise Agent Platform, formerly Vertex ([docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/managed-agents)).
- **Agents offered**:
  - The **Antigravity agent** (`antigravity-preview-09-2026`). It defaults to `gemini-4-hydrogen` and can be set to carbon, argon, neon, or 3.x Flash via `agent_config.model`.
  - The **Deep Research** agent.
- **What you get**:
  - A hosted agent loop in a Google-hosted Ubuntu sandbox with Python 3.12 and Node 22.
  - Built-in tools: `code_execution` (bash/python/node), `google_search`, `url_context`, and filesystem tools.
  - Automatic context compaction at about 135K tokens.
  - Persistent environments, deleted after 7 days idle.
  - Sources mounted from inline content, Git, or GCS.
  - Network allowlists.
  - Managed credentials that an egress proxy injects, so secrets never sit in the sandbox.
  - Hooks, cron Triggers, `background=True` with cancel, and `max_total_tokens` budget caps (the run returns `incomplete`, and you continue it with `"continue"`).
- **Core calls** (`google-genai`, `api_version="v1beta"`): `client.interactions.create(agent=..., input=..., environment="remote"|env_id|{config}, tools=[...], agent_config={...}, stream=True, background=True, previous_interaction_id=...)`, `client.interactions.get/cancel`, `client.agents.create(id, base_agent, agent_config, system_instruction, base_environment)`, and `client.triggers.*`.
- **Custom tools**:
  - Define `{"type":"function", name, description, parameters}`. The interaction returns `status="requires_action"`. You run the function client-side and reply with `{"type":"function_result", call_id, result}` along with `previous_interaction_id`. This is stateful only.
  - Alternatively, use a remote `mcp_server` over Streamable HTTP. The name must be lowercase, and SSE transport is not supported.
- **Streaming**: `stream=True` gives step deltas, and `step.stop` carries usage ([quickstart](https://aistudio.google.com/docs/managed-agents-quickstart), [streaming](https://aistudio.google.com/docs/streaming)).
- **Pricing and access**:
  - Available on Free and paid tiers. You pay model tokens plus tools; sandbox compute is free during preview.
  - Typical runs: data analysis is 300K–3M input tokens, about $0.70–$3.25. Heavy runs reach about $5 ([Antigravity agent](https://aistudio.google.com/docs/antigravity-agent)).
  - Templates: [github.com/google-gemini/gemini-managed-agents-templates](https://github.com/google-gemini/gemini-managed-agents-templates). There is also an [ADK `ManagedAgent`](https://adk.dev/agents/managed-agents/).

## 3. Hooks

See the top section.

## 4. Gotchas

- **Billing caps can kill the benchmark.**
  - Tier 1 means billing is linked, with a **$250 billing-tier cap** and a **$10 per 10-minute spend limit**.
  - Tier 2 needs $100 already paid **and 3 days** since the first payment. That is not reachable by Saturday if you start today.
  - Math: 100 cases × about $1–3 = $100–300. That runs into the cap, and the $10/10 min limit keeps it to about 3–10 cases per 10 minutes.
  - Plan: run about 20–30 cases live on Argon (or Hydrogen), and run the full set through the Deferred tier at 50% off or batch overnight ([rate limits](https://aistudio.google.com/docs/rate-limits)).
- **Free tier limits.** Argon and Carbon aren't available on the Free tier. On Free, the agent is limited to Hydrogen.
- **Search grounding** is capped at 1,500 RPD per project.
- **Hooks are not a trustworthy checker on their own.**
  - They **fail open**: a crash, timeout, or bad JSON is treated as `allow`.
  - They don't fire for custom `function` or MCP tools.
  - The agent can edit `.agents/hooks.json` unless the config is mounted read-only.
  - Fix: make the final gate a client-side `submit_report` function result.
- **Antigravity agent limits.**
  - No structured output.
  - No `max_output_tokens`, temperature, or `stop_sequences` (these return a 400).
  - Only text and image input, with images as inline base64.
  - No `file_search`.
  - Whether thinking level can be set inside `agent_config` is UNVERIFIED.
- **The sandbox has open network egress by default.** It can call ClinVar/gnomAD/NCBI directly, but expect cold starts after VM spin-down. Store the AlphaGenome key as a managed credential.
- **AlphaGenome**: free for non-commercial use only. You need a separate API key, and the rate "varies with demand"; Atlas lookups are faster than live predictions ([repo](https://github.com/google-deepmind/alphagenome)). Request the key now.
- **API keys.** Unrestricted API keys have been rejected since Jun 19 2026. Use keys generated in AI Studio.
- **Preview status.** Schemas may change. Pin `antigravity-preview-09-2026`.
- **Model-routing reports.** Forum users report `gemini-4-carbon` streams ending with `modelVersion` set to a Flash-Lite model ([thread](https://discuss.ai.google.dev/t/gemini-4-carbon-changes-modelversion-to-flash-lite-at-stop-native-https-repro/199710)). This is UNVERIFIED. Log `modelVersion` in the benchmark.
- **Regions/waitlist**: no waitlist found for Managed Agents in the Gemini API. Regional limits are UNVERIFIED.

## 5. Hackathon specifics

[cerebralvalley.ai/e/gemini-4-nyc](https://cerebralvalley.ai/e/gemini-4-nyc):

- Hosts are Cerebral Valley and Google DeepMind.
- $20K in prizes: 1st $7.5K, 2nd $5K, 3rd $2.5K, and Best use of Managed Agents $5K.
- Teams of up to 4. Approval is required.
- Judges include Thor Schaeff, Jack Wotherspoon, Mike Swift (MLH), and others.

**No API credits or resources are announced on the page (UNVERIFIED; often handed out on the day).** Don't count on them.

## Setup to do before Saturday

1. Create a dedicated GCP project and an AI Studio API key. Link billing now so it reaches Tier 1, and check tier and limits at aistudio.google.com/rate-limit.
2. Set a budget alert. Note that the intro price ends Nov 30.
3. Throwaway hello-world checks (not project code):
   - `interactions.create(model="gemini-4-argon", input="hi")`
   - The Antigravity agent with `environment="remote"` and `stream=True`, to check what the step event types look like.
   - One custom-function round trip through `requires_action`.
   - One `pre_tool_execution` deny hook, to confirm the model re-plans.
   - `agent_config.model="gemini-4-argon"`, to confirm paid-tier access.
   - `max_total_tokens` → `incomplete` → `"continue"`.
4. Request an AlphaGenome API key. Check that the sandbox can reach the ClinVar, gnomAD, and HPO endpoints.
5. Measure the real cost and wall time of one realistic 15-tool-call run. That number tells you how big a benchmark you can afford.
6. `pip install -U google-genai`, and confirm `client.interactions` and `client.agents` exist in the installed version.
