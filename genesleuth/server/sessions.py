"""Track case runs and replay the same evidence stream to reconnecting viewers."""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from genesleuth.schemas import Case, CaseTruth, InvestigationResult, TraceEvent, Variant


def public_data(value: Any) -> Any:
    """Remove provider session identifiers and local artifact paths from trace data."""
    if isinstance(value, dict):
        private = {
            "artifact_path", "raw_ref", "referral_pdf", "interaction_id",
            "previous_interaction_id", "environment_id", "api_key", "credentials",
            "hidden_variant_id", "truth", "case_truth", "holdout",
        }
        return {key: public_data(item) for key, item in value.items() if key not in private}
    if isinstance(value, list):
        return [public_data(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass
class Run:
    """Hold ordered SSE frames for one investigation or continuation."""

    id: int
    case_id: str
    started: float = field(default_factory=time.monotonic)
    frames: list[tuple[str, str]] = field(default_factory=list)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    terminal: bool = False

    def emit(self, event: TraceEvent) -> None:
        """Append an investigator event and notify connected viewers."""
        if self.terminal or event.step == "done":
            return
        payload = event.model_dump(mode="json")
        payload["data"] = public_data(payload["data"])
        self.append("trace", payload)

    def announce(self, step: str, summary: str) -> None:
        """Append a server lifecycle event using the shared event format."""
        self.emit(TraceEvent(
            case_id=self.case_id,
            t=time.monotonic() - self.started,
            step=step,
            actor="Server",
            summary=summary,
        ))

    def append(self, name: str, payload: dict) -> None:
        """Serialize the event once so clients receive identical frames."""
        self.frames.append((name, json.dumps(payload, separators=(",", ":"), allow_nan=False)))
        self.changed.set()

    async def stream(self, cursor: int):
        """Replay missing events, then wait for new events or send a heartbeat."""
        if not 0 <= cursor <= len(self.frames):
            cursor = 0
        while True:
            while cursor < len(self.frames):
                name, payload = self.frames[cursor]
                cursor += 1
                yield f"id: {self.id}:{cursor}\nevent: {name}\ndata: {payload}\n\n"
            if self.terminal:
                return
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), timeout=12)
            except TimeoutError:
                yield ": keepalive\n\n"


@dataclass
class Plot:
    """Record the current state of one brain-versus-blood figure."""

    url: str | None = None
    failure: str | None = None

    def public(self) -> dict:
        """Return the figure status without the underlying local path."""
        if self.url:
            return {"status": "ready", "url": self.url}
        if self.failure:
            return {"status": "unavailable", "message": self.failure}
        return {"status": "pending"}


@dataclass
class Session:
    """Keep the answer key and investigation state on the server."""

    case: Case
    truth: CaseTruth
    build_seconds: float
    runs: list[Run] = field(default_factory=list)
    initial_result: InvestigationResult | None = None
    result: InvestigationResult | None = None
    plots: dict[str, Plot] = field(default_factory=dict)
    revealed: bool = False

    def begin(self) -> Run:
        """Create a numbered stream without discarding previous runs."""
        run = Run(len(self.runs) + 1, self.case.case_id)
        self.runs.append(run)
        return run

    def variant(self, variant_id: str) -> Variant | None:
        """Look up one eligible candidate without consulting the answer key."""
        return next((variant for variant in self.case.suspects if variant.variant_id == variant_id), None)


def png_path(path: str | Path | None) -> Path | None:
    """Accept only an existing PNG produced by the investigator or plot client."""
    if not path:
        return None
    candidate = Path(path)
    if candidate.suffix.lower() != ".png":
        return None
    try:
        with candidate.open("rb") as image:
            return candidate.resolve() if image.read(8) == b"\x89PNG\r\n\x1a\n" else None
    except OSError:
        return None
