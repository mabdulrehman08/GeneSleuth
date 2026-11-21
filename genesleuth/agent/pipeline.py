"""Run the real reader, investigation and matched-data evaluation baselines."""
from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from time import monotonic

from pydantic import BaseModel, Field

from genesleuth import config
from genesleuth.agent.errors import InvestigationError
from genesleuth.agent.investigator import Conversation, investigate_tools
from genesleuth.agent.reader import read_case_plan
from genesleuth.agent.settings import AG_CONCURRENCY, PROFILE_LIMITS
from genesleuth.agent.tools import ToolLedger
from genesleuth.agent.triage import Triage, candidate_row, triage_candidates
from genesleuth.alphagenome_client import atlas_scores, list_tissues, score_variant
from genesleuth.gemini_clients import RunUsage, run_usage, structured
from genesleuth.schemas import Case, InvestigationResult, RankedSuspect


@dataclass
class Session:
    """Preserve the live interaction and evidence context through reviewer follow-up."""
    conversation: Conversation
    atlas: dict
    tissue_list: list[dict]
    triage: Triage
    variant_ids: frozenset[str]
    plan: dict
    latest_result: InvestigationResult | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_SESSIONS: OrderedDict[str, Session] = OrderedDict()


class BaselineItem(BaseModel):
    """One candidate ranked by Gemini without tools."""
    variant_id: str
    score: float = Field(ge=0, le=1)
    publication_if_known: str | None = None


class BaselineReport(BaseModel):
    """A bounded output schema for the single-call Gemini baseline."""
    candidates: list[BaselineItem] = Field(max_length=10)


def _ranked(ordered, tissue: str | None = None) -> list[RankedSuspect]:
    """Convert up to ten scored candidates into the shared ranking schema."""
    return [RankedSuspect(rank=rank, variant=variant, score=score, tissue=tissue, summary=summary)
            for rank, (variant, score, summary) in enumerate(ordered[:10], start=1)]


def _atlas_ranking(case: Case, atlas: dict) -> list[RankedSuspect]:
    """Rank the candidates with a variant-matched Atlas AVI result."""
    ordered = []
    for variant in case.suspects:
        value = atlas.get(variant.variant_id, {}).get("avi")
        if isinstance(value, (int, float)):
            ordered.append((variant, value, f"AlphaGenome Atlas (AG1) AVI score {value:g}"))
    if not ordered:
        raise InvestigationError("AlphaGenome Atlas returned no usable AVI scores")
    ordered.sort(key=lambda item: (-item[1], item[0].variant_id))
    return _ranked(ordered)


async def _score_ranking(case: Case, emit) -> tuple[list[RankedSuspect], int]:
    """Score every candidate in the same configured brain condition and rank by effect."""
    concurrency = asyncio.Semaphore(AG_CONCURRENCY)
    count = 0

    async def score(variant):
        """Score a single candidate without unbounded live concurrency."""
        nonlocal count
        async with concurrency:
            value = await asyncio.to_thread(score_variant, variant, config.BRAIN_TISSUE)
            count += 1
        emit("alphagenome", "AlphaGenome", f"Scored {variant.variant_id} in the fixed baseline condition",
             variant_id=variant.variant_id, n_alphagenome_calls=count, alphagenome_budget=len(case.suspects),
             **({"error": value["error"]} if "error" in value else {}))
        return variant, value

    results = await asyncio.gather(*(score(variant) for variant in case.suspects))
    ordered = [(variant, score["normalized_effect"], f"Normalized AlphaGenome 2 effect {score['normalized_effect']:g}")
               for variant, score in results if "normalized_effect" in score]
    if not ordered:
        raise InvestigationError("AlphaGenome returned no usable scores in the fixed baseline condition")
    ordered.sort(key=lambda item: (-item[1], item[0].variant_id))
    return _ranked(ordered, config.BRAIN_TISSUE), count


async def _gemini_ranking(case: Case, phenotypes, profile: str) -> list[RankedSuspect]:
    """Rank the case table with Neon in a single Interactions call and no tools."""
    variants = {item.variant_id: item for item in case.suspects}
    expected = min(10, len(variants))
    context = {
        "phenotypes": [item.model_dump(exclude={"source_quote"}) for item in phenotypes],
        "suspects": [candidate_row(item) for item in case.suspects],
    }
    response = await asyncio.to_thread(
        structured, config.NEON, json.dumps(context, ensure_ascii=False), BaselineReport.model_json_schema(),
        thinking=PROFILE_LIMITS[profile]["thinking"],
        instruction=(
            f"Rank {expected} unique variant ids from the provided table for research review. "
            "Return them in rank order with a relative prioritization score between zero and one. "
            "Use only the table and supplied HPO terms for ranking. If you already recognize a specific "
            "published report for a variant, note the citation for a memorization check, otherwise leave it null."
        ),
    )
    result = BaselineReport.model_validate(response)
    returned = [item.variant_id for item in result.candidates]
    if len(returned) != expected or len(set(returned)) != expected or any(item not in variants for item in returned):
        raise InvestigationError("Gemini baseline did not return a complete valid shortlist")
    return _ranked([(variants[item.variant_id], item.score, "Gemini-only prioritization")
                    for item in result.candidates])


def _new_conversation() -> Conversation:
    """Select the runtime for new sessions without bypassing the report gate."""
    return Conversation(managed=config.USE_MANAGED_AGENT)


def _same_result(current: InvestigationResult | None, previous: InvestigationResult) -> bool:
    """Require the latest completed session result before adding reviewer evidence."""
    if current is None:
        return False
    return (current.ranked == previous.ranked and current.tool_calls == previous.tool_calls
            and current.phenotypes == previous.phenotypes)


async def _run_full(case, holdout, phenotypes, session, profile, emit, previous=None, request=None):
    """Continue one locally serialized case session with the saved evidence context."""
    async with session.lock:
        if previous is not None and not _same_result(session.latest_result, previous):
            raise InvestigationError("Reload the latest investigation result before sending another review request")
        conversation = replace(session.conversation, pending=list(session.conversation.pending))
        ledger = ToolLedger(
            case, holdout, phenotypes, session.triage.rows, session.atlas, session.tissue_list, profile, emit,
            frequencies=session.triage.frequencies, phenotype_matches=session.triage.phenotype_matches,
            previous_calls=previous.tool_calls if previous else None,
        )
        context = {
            "phenotypes": [item.model_dump(exclude={"source_quote"}) for item in phenotypes],
            "panel": case.panel_name, "funnel": case.funnel, "first_suspects": session.triage.rows[:50],
            "candidate_conditions": session.triage.tissues, "routed_condition": session.triage.route,
            "hypothesis_plan": session.plan,
        }
        ranked, checked, rejected = await investigate_tools(ledger, context, conversation, followup=request)
        result = InvestigationResult(
            case_id=case.case_id, mode="full", status="ok", ranked=ranked, phenotypes=phenotypes,
            tool_calls=sorted(ledger.calls, key=lambda call: int(call.call_id[1:])), n_tool_calls=len(ledger.calls),
            n_alphagenome_calls=(previous.n_alphagenome_calls if previous else 0) + ledger.score_count,
            n_claims_checked=(previous.n_claims_checked if previous else 0) + checked,
            n_claims_rejected=(previous.n_claims_rejected if previous else 0) + rejected,
        )
        session.conversation = conversation
        session.latest_result = result.model_copy(deep=True)
        return result


async def run(case, holdout, mode, profile, previous, request, emit) -> InvestigationResult:
    """Calculate the requested live result, retaining per-phase timing and provider cost."""
    start = monotonic()
    timings = {}
    usage = RunUsage()
    token = run_usage.set(usage)
    try:
        if previous is not None:
            session = _SESSIONS.get(case.case_id)
            if session is None or session.variant_ids != frozenset(item.variant_id for item in case.suspects):
                raise InvestigationError("No resumable Gemini session is available for this case")
            if len(request) > 1_000:
                raise InvestigationError("Reviewer requests must fit within 1,000 characters")
            emit("plan", "Gemini 4 Neon", "Continuing the case with reviewer input")
            result = await _run_full(case, holdout, previous.phenotypes, session, profile, emit, previous, request)
        else:
            start_reader = monotonic()
            phenotypes, plan = await asyncio.to_thread(read_case_plan, case.referral_pdf)
            timings["read_letter_s"] = monotonic() - start_reader
            model = plan.pop("reader_model", config.CARBON)
            actor = "Gemini 4 Carbon" if model == config.CARBON else "Gemini 4 Neon"
            if model != config.CARBON:
                emit("plan", actor, "Referral reader fell back from Carbon to Neon",
                     fallback_from=config.CARBON, fallback_to=model)
            emit("read_letter", actor, f"Read referral letter. Matched {len(phenotypes)} findings to HPO.",
                 phenotypes=[item.model_dump(mode="json") for item in phenotypes])
            emit("plan", actor, "Proposed candidate genes, mechanisms and tissues", **plan)

            if mode == "full":
                stage = monotonic()
                atlas, tissues = await asyncio.gather(
                    asyncio.to_thread(atlas_scores, case.suspects), asyncio.to_thread(list_tissues),
                )
                timings["atlas_and_conditions_s"] = monotonic() - stage
                available = sum(item.get("avi") is not None for item in atlas.values())
                emit("plan", "AlphaGenome Atlas (AG1)", f"Retrieved AVI evidence for {available} candidates",
                     n_atlas_scored=available, n_suspects=len(case.suspects))
                stage = monotonic()
                triage = await triage_candidates(case.suspects, phenotypes, plan, atlas, tissues, emit)
                timings["triage_s"] = monotonic() - stage
                session = Session(_new_conversation(), atlas, tissues, triage,
                                  frozenset(item.variant_id for item in case.suspects), plan)
                result = await _run_full(case, holdout, phenotypes, session, profile, emit)
                _SESSIONS[case.case_id] = session
                _SESSIONS.move_to_end(case.case_id)
                if len(_SESSIONS) > 48:
                    _SESSIONS.popitem(last=False)
            else:
                count = 0
                if mode == "atlas_only":
                    atlas = await asyncio.to_thread(atlas_scores, case.suspects)
                    ranked = _atlas_ranking(case, atlas)
                elif mode == "alphagenome_only":
                    ranked, count = await _score_ranking(case, emit)
                else:
                    ranked = await _gemini_ranking(case, phenotypes, profile)
                result = InvestigationResult(case_id=case.case_id, mode=mode, status="ok",
                                             ranked=ranked, phenotypes=phenotypes, n_alphagenome_calls=count)
    finally:
        run_usage.reset(token)

    timings["investigation_s"] = monotonic() - start
    timings["gemini_requests"] = float(usage.calls)
    if usage.cost_available:
        timings["cost_usd"] = usage.cost_usd
    result.timings.update(timings)
    emit("rank", "GeneSleuth", f"Ranked {len(result.ranked)} candidates", n_ranked=len(result.ranked))
    return result
