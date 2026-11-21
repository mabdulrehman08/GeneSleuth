"""Application and benchmark entry points for the GeneSleuth investigator."""
from __future__ import annotations

from time import monotonic
from typing import Callable

from genesleuth import config
from genesleuth.schemas import Case, InvestigationResult, TraceEvent

MODES = {"full", "alphagenome_only", "atlas_only", "gemini_only"}
PROFILES = {"demo", "bench"}
EventCallback = Callable[[TraceEvent], None]


def event_emitter(case_id: str, start: float, callback: EventCallback | None):
    """Bind events to a case and measure elapsed time on a monotonic clock."""
    def emit(step: str, actor: str, summary: str, **data):
        """Send a single structured trace event if a listener is attached."""
        if callback is not None:
            callback(TraceEvent(case_id=case_id, t=monotonic() - start, step=step,
                                actor=actor, summary=summary, data=data))
    return emit


async def investigate(
    case: Case,
    holdout: set[str],
    mode: str = "full",
    on_event: EventCallback | None = None,
    profile: str = "bench",
) -> InvestigationResult:
    """Run one research investigation or baseline and stream its trace."""
    return await _run(case, holdout, mode, on_event, profile)


async def look_again(
    case: Case,
    holdout: set[str],
    previous: InvestigationResult,
    request: str,
    on_event: EventCallback | None = None,
    profile: str = "demo",
) -> InvestigationResult:
    """Continue a completed full investigation with a reviewer request."""
    return await _run(case, holdout, "full", on_event, profile, previous, request)


async def _run(case, holdout, mode, on_event, profile, previous=None, request=None):
    """Validate inputs and return the shared failure result for an unsuccessful run."""
    start = monotonic()
    emit = event_emitter(case.case_id, start, on_event)
    try:
        if mode not in MODES:
            raise ValueError("Unknown investigation mode")
        if profile not in PROFILES:
            raise ValueError("Unknown investigation profile")
        if previous is not None and (
            previous.case_id != case.case_id or previous.status != "ok"
            or previous.mode != "full" or not request or not request.strip()
        ):
            raise ValueError("A completed full result and a reviewer request are required")
        if not case.suspects:
            raise ValueError("The case has no candidate variants")
        if config.FAKE_MODE:
            from genesleuth.agent.development import simulate
            result = await simulate(case, mode, previous, request, emit)
        else:
            from genesleuth.agent.pipeline import run
            result = await run(case, holdout, mode, profile, previous, request, emit)
    except Exception as error:
        from genesleuth.agent.errors import safe_error
        message = safe_error(error)
        result = InvestigationResult(
            case_id=case.case_id, mode=mode if mode in MODES else "full",
            status="error", ranked=[], error=message,
        )
        emit("error", "GeneSleuth", message)
    result.timings["total_s"] = monotonic() - start
    if result.status == "ok":
        emit("done", "GeneSleuth", "Investigation complete",
             result=result.model_dump(mode="json"), cost_usd=result.timings.get("cost_usd"))
    return result
