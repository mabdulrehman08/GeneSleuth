"""Stable Gemini Interactions and beta Decisions/Managed Agents in one boundary."""
from __future__ import annotations

import base64
import json
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from time import monotonic, sleep

from genesleuth import config
from genesleuth.agent.errors import InvestigationError
from genesleuth.agent.settings import (
    DECISION_MAX_QUESTIONS, GEMINI_OVERLOAD_RETRIES, GEMINI_TIMEOUT_MS, MANAGED_TIMEOUT_MS, PRICES_USD,
)

_LOG_LOCK = Lock()
_SECRET = re.compile(r"AQ\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}")


@dataclass
class RunUsage:
    """Collect provider usage estimates across parallel calls in one investigation."""
    cost_usd: float = 0
    calls: int = 0
    cost_available: bool = True


run_usage: ContextVar[RunUsage | None] = ContextVar("gemini_run_usage", default=None)


class GatewayError(InvestigationError):
    """A provider failure with sanitized context and a retryable status when available."""

    def __init__(self, operation: str, model: str, status: int | None, kind: str):
        """Retain only the operation, configured model and public error category."""
        detail = f"HTTP {status}" if status is not None else kind
        if status == 429:
            detail += " (check the AI Studio quota or spend cap)"
        super().__init__(f"{operation} on {model} failed: {detail}")
        self.status = status
        self.overloaded = status == 503
        self.timed_out = kind in {"APITimeoutError", "ReadTimeout", "TimeoutException", "DeadlineExceeded"} or status == 504


@lru_cache(maxsize=3)
def _sdk(api_version: str, timeout_ms: int):
    """Create an SDK client only when a live operation needs it."""
    if config.FAKE_MODE:
        raise InvestigationError("Gemini calls are disabled in development fixture mode")
    if not config.GEMINI_API_KEY:
        raise InvestigationError("Gemini key is missing from .env")
    try:
        from google import genai
    except ImportError:
        raise InvestigationError("Install google-genai>=3.2.0 before making live calls") from None
    return genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options={"api_version": api_version, "timeout": timeout_ms,
                      "retry_options": {"attempts": 1}},
    )


class _Interactions:
    """Expose the usual SDK interaction entry points to the other project modules."""

    def __init__(self, beta: bool):
        """Select the stable or beta transport."""
        self.beta = beta

    def create(self, **kwargs):
        """Make a logged Interactions call on the appropriate API version."""
        if kwargs.get("stream"):
            return _stream(self.beta, kwargs)
        model = _model_name(kwargs)
        return _call("interactions.create", model, kwargs,
                     lambda: _client(self.beta, kwargs).interactions.create(**kwargs))

    def get(self, id: str):
        """Read an interaction whose steps are needed for continuation."""
        return _call("interactions.get", "unknown", {"id": id},
                     lambda: _client(self.beta, {}).interactions.get(id=id), billable=False)


class _Decisions:
    """Provide the official Decisions API shape through the logged beta client."""

    def create(self, *, model: str = config.DECISION_MODEL, input, questions: dict):
        """Send one bounded batch of Decision 1 questions."""
        if not 1 <= len(questions) <= DECISION_MAX_QUESTIONS:
            raise ValueError("Decisions API accepts 1 to 1,000 questions")
        request = {"model": model, "input": input, "questions": questions}
        return _call("decisions.create", model, request,
                     lambda: _client(True, {}).decisions.create(**request), retries=1)


class _Client:
    """A lazy SDK facade that keeps direct project calls in the same usage log."""

    def __init__(self, beta: bool):
        """Expose model interactions and beta decisions."""
        self.interactions = _Interactions(beta)
        self._beta = beta
        if beta:
            self.decisions = _Decisions()

    def __getattr__(self, name: str):
        """Provide access to additional configured SDK surfaces."""
        return getattr(_client(self._beta, {}), name)


client = _Client(beta=False)
beta_client = _Client(beta=True)


def _client(beta: bool, request: dict):
    """Choose the beta timeout for the managed runtime."""
    timeout = MANAGED_TIMEOUT_MS if request.get("agent") else GEMINI_TIMEOUT_MS
    return _sdk("v1beta" if beta else "v1", timeout)


def _model_name(request: dict) -> str:
    """Identify the billed model independently from the agent version."""
    return request.get("model") or request.get("agent_config", {}).get("model", config.NEON)


def dump(value):
    """Convert SDK records into plain Python values for logging and validation."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=False, exclude_none=True)
    return value


def _redact(value):
    """Strip inline document/image payloads and all known key formats recursively."""
    value = dump(value)
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {"api_key", "key", "token", "authorization", "x_goog_api_key"}:
                clean[key] = "[redacted]"
            elif key in {"inline_data", "inlineData"} or (
                key == "data" and value.get("type") in {"document", "image", "audio", "video"}
            ):
                clean[key] = "[inline media]"
            else:
                clean[key] = _redact(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        for secret in (config.GEMINI_API_KEY, config.ALPHAGENOME_API_KEY):
            if secret:
                value = value.replace(secret, "[redacted]")
        return _SECRET.sub("[redacted]", value)
    return value


def _usage_cost(model: str, usage: dict) -> float | None:
    """Estimate standard pricing from the usage fields actually returned."""
    if model not in PRICES_USD or not usage:
        return None
    input_price, output_price = PRICES_USD[model]
    input_tokens = usage.get("total_input_tokens", 0)
    cached = min(input_tokens, usage.get("total_cached_tokens", 0))
    reasoning = usage.get("total_thought_tokens", 0)
    output_tokens = usage.get("total_output_tokens", 0) + reasoning
    return ((input_tokens - cached + cached * 0.05) * input_price +
            output_tokens * output_price) / 1_000_000


def _record(operation, model, request, response, duration, status=None, billable=True):
    """Write one private JSONL record and attribute known cost to the current run."""
    response_data = dump(response) or {}
    if not isinstance(response_data, dict):
        response_data = {}
    usage = dump(response_data.get("usage")) or {}
    model_version = response_data.get("model_version") or response_data.get("modelVersion")
    cost = _usage_cost(model, usage) if billable and status is None else None
    tally = run_usage.get()
    record = {
        "operation": operation, "model": model, "modelVersion": model_version,
        "prompt": request.get("input"), "config": {k: v for k, v in request.items() if k != "input"},
        "output": response_data, "latency_s": round(duration, 4), "usage": usage,
        "estimated_cost_usd": cost, "error": status,
    }
    line = json.dumps(_redact(record), ensure_ascii=False, default=str)
    with _LOG_LOCK:
        if tally is not None and billable:
            tally.calls += 1
            if cost is not None:
                tally.cost_usd += cost
            elif status is None:
                tally.cost_available = False
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(config.CACHE_DIR / "calls.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as output:
            output.write(line + "\n")


def _gateway_error(operation: str, model: str, error: Exception) -> GatewayError:
    """Retain quota and overload categories without logging input or provider error bodies."""
    code = getattr(error, "code", None)
    status = code if isinstance(code, int) else getattr(error, "status_code", None)
    status = status if isinstance(status, int) else None
    return GatewayError(operation, model, status, type(error).__name__)


def _call(operation, model, request, invoke, *, billable=True, retries=GEMINI_OVERLOAD_RETRIES):
    """Retry bounded overload responses and record each provider attempt."""
    for attempt in range(retries + 1):
        start = monotonic()
        try:
            response = invoke()
        except InvestigationError:
            raise
        except Exception as error:
            failure = _gateway_error(operation, model, error)
            _record(operation, model, request, None, monotonic() - start, str(failure), billable)
            if not failure.overloaded or attempt == retries:
                raise failure from None
            sleep(0.5 * 2 ** attempt)
        else:
            _record(operation, model, request, response, monotonic() - start, billable=billable)
            return response


def _stream(beta: bool, request: dict):
    """Log a managed stream once and retry only before receiving any event."""
    operation, model = "interactions.stream", _model_name(request)
    for attempt in range(GEMINI_OVERLOAD_RETRIES + 1):
        start = monotonic()
        final = None
        had_events = False
        try:
            for event in _client(beta, request).interactions.create(**request):
                had_events = True
                if getattr(event, "interaction", None) is not None:
                    final = event.interaction
                if getattr(event, "event_type", None) == "error":
                    raise InvestigationError("Managed interaction returned a stream error")
                yield event
        except Exception as error:
            failure = _gateway_error(operation, model, error)
            _record(operation, model, request, final, monotonic() - start, str(failure))
            if had_events or not failure.overloaded or attempt == GEMINI_OVERLOAD_RETRIES:
                raise failure from None
            sleep(0.5 * 2 ** attempt)
        else:
            _record(operation, model, request, final, monotonic() - start)
            return


def media_block(payload: bytes, mime_type: str) -> dict:
    """Encode a PDF or image for the Interactions and Decisions APIs."""
    return {"type": "document" if mime_type == "application/pdf" else "image",
            "mime_type": mime_type, "data": base64.b64encode(payload).decode("ascii")}


def structured(model: str, input_data, schema: dict, *, thinking: str, instruction: str = "", store: bool = False):
    """Ask one model for a native JSON-schema response."""
    options = {"system_instruction": instruction} if instruction else {}
    response = client.interactions.create(
        model=model, input=input_data, store=store,
        generation_config={"thinking_level": thinking},
        response_format={"type": "text", "mime_type": "application/json", "schema": schema},
        **options,
    )
    try:
        return json.loads(response.output_text)
    except (TypeError, ValueError):
        raise InvestigationError(f"{model} did not return the requested structured response") from None


def decide(input_data, questions: dict):
    """Return typed Decision 1 answers to a bounded collection of questions."""
    return beta_client.decisions.create(input=input_data, questions=questions).answers
