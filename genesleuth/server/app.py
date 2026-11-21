"""Serve the judge's picker, trace stream, plots, benchmark, and reviewer workflow."""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from genesleuth.config import BLOOD_TISSUE, BRAIN_TISSUE, CACHE_DIR, FAKE_MODE, ROOT
from genesleuth.schemas import InvestigationResult, TraceEvent
from genesleuth.server.integration import case_api
from genesleuth.server.review import current_decisions, evidence_report, read_actions, record_action
from genesleuth.server.sessions import Plot, Run, Session, png_path, public_data

logger = logging.getLogger(__name__)
WEB = ROOT / "web"
BENCHMARK = ROOT / "bench" / "results" / "test"
BUILD_TIMEOUT = 20
INVESTIGATION_TIMEOUT = 180
PLOT_TIMEOUT = 40
ALPHAGENOME_BUDGET = 25


class CaseRequest(BaseModel):
    """Optional picker selection, with null representing Random."""

    option_id: str | None = Field(default=None, max_length=128)


class ReviewRequest(BaseModel):
    """An explicit reviewer decision for a candidate."""

    variant_id: str = Field(min_length=1, max_length=512)
    action: Literal["accept", "reject"]


class LookAgainRequest(BaseModel):
    """A request to extend the current investigation, scoped to one candidate."""

    variant_id: str = Field(min_length=1, max_length=512)
    tissue: str | None = Field(default=None, max_length=160)
    question: str | None = Field(default=None, max_length=1000)


def run_cost(result: InvestigationResult) -> float | None:
    """Read a run's cost from investigator telemetry, if reported."""
    for key in ("cost_usd", "total_cost_usd", "gemini_cost_usd"):
        value = result.timings.get(key)
        if value is not None and math.isfinite(value) and value >= 0:
            return value
    return None


def create_app(*, dev: bool = False) -> FastAPI:
    """Create an isolated demo app and apply the live-mode startup guard."""
    sessions: dict[str, Session] = {}
    plot_files: dict[str, Path] = {}
    tasks: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Apply demo-mode restrictions and cancel active tasks on shutdown."""
        if not dev and (FAKE_MODE or os.getenv("FAKE_MODE") == "1"):
            raise RuntimeError("FAKE_MODE=1 requires the server's --dev flag.")
        if not dev and os.getenv("CHECKER_FALLBACK", "").strip():
            raise RuntimeError("Clear CHECKER_FALLBACK before starting the live demo.")
        yield
        active = list(tasks)
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)

    service = FastAPI(title="GeneSleuth", lifespan=lifespan)
    service.mount("/static", StaticFiles(directory=WEB), name="static")

    def schedule(coroutine) -> None:
        """Keep a task alive until it completes or the server shuts down."""
        task = asyncio.create_task(coroutine)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    def session_for(case_id: str) -> Session:
        """Find a case by its opaque ID."""
        session = sessions.get(case_id)
        if session is None:
            raise HTTPException(404, "Case not found. Build a new case.")
        return session

    def completed(session: Session) -> InvestigationResult:
        """Require an accepted, completed investigation."""
        if session.result is None or session.result.status != "ok":
            raise HTTPException(409, "Complete the investigation first.")
        return session.result

    def register_plot(path: Path) -> str:
        """Expose a server-issued plot handle instead of a filesystem path."""
        file_id = f"{secrets.token_hex(16)}.png"
        plot_files[file_id] = path
        return f"/api/plots/{file_id}"

    async def generate_plot(session: Session, variant_id: str, plot: Plot) -> None:
        """Render a comparison plot through the shared client outside the event loop."""
        variant = session.variant(variant_id)
        if variant is None:
            plot.failure = "The hidden variant did not survive the candidate filter."
            return
        try:
            from genesleuth.alphagenome_client import plot_variant

            directory = CACHE_DIR / "demo_plots"
            directory.mkdir(parents=True, exist_ok=True)
            output = directory / f"{secrets.token_hex(16)}.png"
            value = await asyncio.wait_for(
                asyncio.to_thread(plot_variant, variant, [BRAIN_TISSUE, BLOOD_TISSUE], str(output)),
                timeout=PLOT_TIMEOUT,
            )
            path = png_path(value if isinstance(value, (str, Path)) else None)
            path = path or png_path(output)
            if path is None:
                plot.failure = "AlphaGenome did not return a brain-and-blood plot."
            else:
                plot.url = register_plot(path)
        except TimeoutError:
            plot.failure = "The AlphaGenome plot timed out."
        except Exception as error:
            logger.warning("Plot generation failed (%s)", type(error).__name__)
            plot.failure = "The AlphaGenome plot is unavailable for this case."

    def plot_for(session: Session, variant_id: str) -> Plot:
        """Reuse an existing two-tissue artifact or schedule one plot per candidate."""
        existing = session.plots.get(variant_id)
        if existing is not None:
            return existing
        plot = session.plots[variant_id] = Plot()
        if session.result is not None:
            for call in session.result.tool_calls:
                tissues = call.args.get("tissue_ids", [])
                if call.args.get("variant_id") != variant_id or not isinstance(tissues, list):
                    continue
                if BRAIN_TISSUE in tissues and BLOOD_TISSUE in tissues:
                    path = png_path(call.artifact_path)
                    if path is not None:
                        plot.url = register_plot(path)
                        return plot
        schedule(generate_plot(session, variant_id, plot))
        return plot

    async def run_investigation(
        session: Session, run: Run, followup: LookAgainRequest | None = None,
    ) -> None:
        """Execute the shared agent and publish exactly one terminal frame."""
        loop = asyncio.get_running_loop()
        owner = threading.get_ident()

        def on_event(event: TraceEvent) -> None:
            """Support events produced in the investigator loop or a worker thread."""
            if threading.get_ident() == owner:
                run.emit(event)
            else:
                loop.call_soon_threadsafe(run.emit, event)

        started_at = time.monotonic()
        try:
            holdout = await asyncio.to_thread(case_api(dev=dev).holdout_for, session.truth)
            if followup is None:
                from genesleuth.agent.api import investigate

                call = investigate(session.case, holdout, on_event=on_event, profile="demo")
            else:
                from genesleuth.agent.api import look_again

                request = f"Review candidate {followup.variant_id}."
                if followup.tissue:
                    request += f" Examine AlphaGenome condition {followup.tissue}."
                if followup.question:
                    request += f" Reviewer question: {followup.question}"
                call = look_again(
                    session.case, holdout, completed(session), request,
                    on_event=on_event, profile="demo",
                )
            result = await asyncio.wait_for(call, timeout=INVESTIGATION_TIMEOUT)
            if result.case_id != session.case.case_id:
                raise ValueError("The investigator returned a mismatched case ID.")
            if result.status == "error":
                message = result.error or "The investigator could not complete this run."
                # Provider exceptions can contain request details. Trace summaries come
                # from the investigator's own reporting interface.
                logger.warning("Investigation returned an error for case %s", session.case.case_id)
                run.announce("error", safe_error(message))
                run.append("failed", {"message": safe_error(message)})
                return

            payload = result.model_dump(mode="json", exclude={"error"})
            payload = public_data(payload)
            payload["build_seconds"] = session.build_seconds
            payload["investigation_seconds"] = time.monotonic() - started_at
            payload["cost_usd"] = run_cost(result)
            payload["review"] = current_decisions(read_actions(session.case.case_id))
            session.result = result
            if followup is None:
                session.initial_result = result
            if result.ranked:
                plot_for(session, result.ranked[0].variant.variant_id)
            run.append("done", payload)
        except Exception as error:
            if isinstance(error, TimeoutError):
                message = "The investigation reached the 180-second server limit."
            elif isinstance(error, ImportError):
                message = "The data or investigator integration module is missing."
            else:
                message = "The investigation failed. Check the server and provider availability."
            logger.warning("Investigation failed (%s)", type(error).__name__)
            run.announce("error", message)
            run.append("failed", {"message": message})
        finally:
            run.terminal = True
            run.changed.set()

    @service.get("/")
    async def index():
        """Serve the investigation interface."""
        return FileResponse(WEB / "index.html", media_type="text/html")

    @service.get("/api/options")
    async def options():
        """Load selectable cases from the data package."""
        try:
            def load():
                """Read the picker through the configured data adapter."""
                return case_api(dev=dev).list_demo_options()

            return await asyncio.wait_for(asyncio.to_thread(load), timeout=10)
        except Exception as error:
            logger.warning("Picker unavailable (%s)", type(error).__name__)
            raise HTTPException(503, "Case options are unavailable. Check the data bundle.") from None

    @service.post("/api/cases", status_code=201)
    async def build_case(selection: CaseRequest):
        """Build a case, retain its answer key, and expose only demo metadata."""
        started_at = time.monotonic()
        try:
            def prepare():
                """Build the selected case in a worker with real-data readiness checked."""
                adapter = case_api(dev=dev)
                option_id = selection.option_id
                if option_id is not None and all(
                    option.option_id != option_id for option in adapter.list_demo_options()
                ):
                    raise KeyError(option_id)
                return adapter.build_case(option_id=option_id, split="demo", seed=secrets.randbits(31))

            case, truth = await asyncio.wait_for(asyncio.to_thread(prepare), timeout=BUILD_TIMEOUT)
        except (KeyError, ValueError):
            raise HTTPException(404, "That case option is unavailable.") from None
        except TimeoutError:
            raise HTTPException(504, "Case preparation exceeded 20 seconds.") from None
        except Exception as error:
            logger.warning("Case build failed (%s)", type(error).__name__)
            raise HTTPException(503, "Case preparation failed. Check the data bundle.") from None
        case_id = case.case_id
        if case_id != truth.case_id or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", case_id):
            raise HTTPException(500, "The data package returned an invalid case ID.")
        if not Path(case.referral_pdf).is_file():
            raise HTTPException(503, "The data package did not create the referral PDF.")
        if case_id in sessions:
            raise HTTPException(409, "That case ID is already active. Try building it again.")
        elapsed = time.monotonic() - started_at
        sessions[case_id] = Session(case, truth, elapsed)
        return {
            "case_id": case_id, "funnel": case.funnel, "n_suspects": len(case.suspects),
            "letter_url": f"/api/cases/{case_id}/letter", "build_seconds": elapsed,
            "alphagenome_budget": ALPHAGENOME_BUDGET,
        }

    @service.get("/api/cases/{case_id}/letter")
    async def letter(case_id: str):
        """Serve the referral PDF inline under a neutral filename."""
        path = Path(session_for(case_id).case.referral_pdf)
        if not path.is_file():
            raise HTTPException(404, "Referral PDF unavailable.")
        return FileResponse(path, media_type="application/pdf", filename="referral.pdf",
                            content_disposition_type="inline")

    @service.post("/api/cases/{case_id}/investigate", status_code=202)
    async def investigate_case(case_id: str):
        """Start a demo investigation once and return its stream identifier."""
        session = session_for(case_id)
        if session.runs and (not session.runs[-1].terminal or session.result is not None):
            return {"run": session.runs[-1].id}
        run = session.begin()
        run.announce("case", "Investigation started.")
        schedule(run_investigation(session, run))
        return {"run": run.id}

    @service.get("/api/cases/{case_id}/events")
    async def events(case_id: str, request: Request, run: int | None = None):
        """Stream investigation events and resume after Last-Event-ID when supplied."""
        session = session_for(case_id)
        available = session.runs
        selected = (run if run is not None else len(available)) - 1
        if not 0 <= selected < len(available):
            raise HTTPException(404, "Investigation stream not found.")
        active = available[selected]
        last = request.headers.get("last-event-id", "")
        match = re.fullmatch(r"([0-9]{1,8}):([0-9]{1,8})", last)
        cursor = int(match[2]) if match and int(match[1]) == active.id else 0
        return StreamingResponse(active.stream(cursor), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @service.get("/api/tissues")
    async def tissues(query: str | None = None):
        """List the confirmed conditions through the shared AlphaGenome client."""
        try:
            from genesleuth.alphagenome_client import list_tissues

            return await asyncio.wait_for(asyncio.to_thread(list_tissues, query), timeout=10)
        except Exception as error:
            logger.warning("Tissue lookup failed (%s)", type(error).__name__)
            raise HTTPException(503, "AlphaGenome tissue list unavailable.") from None

    @service.post("/api/cases/{case_id}/review")
    async def review(case_id: str, action: ReviewRequest):
        """Save the reviewer's decision for a current ranked candidate."""
        session = session_for(case_id)
        result = completed(session)
        candidate = next((item for item in result.ranked if item.variant.variant_id == action.variant_id), None)
        if candidate is None:
            raise HTTPException(404, "That candidate is outside the current shortlist.")
        entry = action.model_dump()
        if action.action == "accept":
            entry["candidate"] = candidate.model_dump(mode="json")
        history = record_action(case_id, entry)
        return {"review": current_decisions(history)}

    @service.post("/api/cases/{case_id}/look-again", status_code=202)
    async def look_again_case(case_id: str, action: LookAgainRequest):
        """Extend the existing Neon session with a reviewer-specified question."""
        session = session_for(case_id)
        result = completed(session)
        if session.runs and not session.runs[-1].terminal:
            raise HTTPException(409, "A follow-up is already running.")
        if action.variant_id not in {item.variant.variant_id for item in result.ranked}:
            raise HTTPException(404, "That candidate is outside the current shortlist.")
        action.tissue = (action.tissue or "").strip() or None
        action.question = (action.question or "").strip() or None
        if not (action.tissue or action.question):
            raise HTTPException(422, "Choose a tissue or enter a review question.")
        try:
            from genesleuth.agent import api as agent_api

            if not callable(getattr(agent_api, "look_again", None)):
                raise ImportError("Missing agent continuation")
        except ImportError:
            raise HTTPException(503, "The investigator's continuation is unavailable.") from None
        record_action(case_id, {"action": "look_again", **action.model_dump()})
        run = session.begin()
        run.announce("case", "Reviewer follow-up started.")
        schedule(run_investigation(session, run, action))
        return {"run": run.id}

    @service.get("/api/cases/{case_id}/report")
    async def report(case_id: str):
        """Download the Markdown evidence report for the current shortlist."""
        result = completed(session_for(case_id))
        return PlainTextResponse(
            evidence_report(result, read_actions(case_id)), media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="genesleuth-{case_id}.md"'},
        )

    @service.post("/api/cases/{case_id}/reveal")
    async def reveal(case_id: str):
        """Reveal and score the original completed shortlist against the hidden variant."""
        session = session_for(case_id)
        completed(session)
        original = session.initial_result
        if original is None:
            raise HTTPException(409, "Complete the original investigation before revealing.")
        variant_id = session.truth.hidden_variant_id
        rank = next((item.rank for item in original.ranked
                     if item.variant.variant_id == variant_id), None)
        session.revealed = True
        return {
            "truth": session.truth.model_dump(mode="json"), "rank": rank,
            "n_suspects": len(session.case.suspects), "passed_filter": session.variant(variant_id) is not None,
            "plot": plot_for(session, variant_id).public(),
        }

    @service.get("/api/cases/{case_id}/plot")
    async def plot_status(case_id: str, target: Literal["top", "hidden"] = "top"):
        """Poll a top-ranked or previously revealed comparison plot."""
        session = session_for(case_id)
        result = completed(session)
        if target == "hidden":
            if not session.revealed:
                raise HTTPException(409, "Reveal the case before requesting its plot.")
            return plot_for(session, session.truth.hidden_variant_id).public()
        if not result.ranked:
            raise HTTPException(404, "The investigation did not return a ranked candidate.")
        return plot_for(session, result.ranked[0].variant.variant_id).public()

    @service.get("/api/plots/{file}")
    async def plot_file(file: str):
        """Serve only plot handles issued by the server."""
        path = plot_files.get(file)
        if path is None or not path.is_file():
            raise HTTPException(404, "Plot not found.")
        return FileResponse(path, media_type="image/png")

    @service.get("/benchmark")
    async def benchmark():
        """Serve the evaluation page."""
        return FileResponse(WEB / "benchmark.html", media_type="text/html")

    @service.get("/api/benchmark")
    async def benchmark_status():
        """Expose the held-out report and whether its chart is available."""
        path = BENCHMARK / "report.md"
        try:
            body = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"status": "pending"}
        return {"status": "ready", "report": body, "chart": png_path(BENCHMARK / "chart.png") is not None}

    @service.get("/api/benchmark/chart")
    async def benchmark_chart():
        """Send the held-out test chart when a completed benchmark has one."""
        path = png_path(BENCHMARK / "chart.png")
        if path is None:
            raise HTTPException(404, "Benchmark chart is pending.")
        return FileResponse(path, media_type="image/png")

    return service


def safe_error(message: str) -> str:
    """Map provider failures to brief, actionable messages without echoing details."""
    normalized = message.lower()
    if "429" in normalized or "quota" in normalized or "resource_exhausted" in normalized:
        return "A provider reached its quota or rate limit. Check the key's quota and try again."
    if "503" in normalized or "overwhelmed" in normalized:
        return "A provider is temporarily unavailable. Try the case again."
    if "timeout" in normalized or "timed out" in normalized:
        return "A provider timed out. Try the case again."
    return "The investigator could not complete this run. Check the timeline and provider status."


app = create_app()


def main() -> None:
    """Run a local, single-worker server with an explicit development switch."""
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true", help="Allow FAKE_MODE for local development.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(dev=args.dev), host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
