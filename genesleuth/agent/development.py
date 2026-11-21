"""Deterministic fixtures for local integration with FAKE_MODE explicitly enabled."""
from __future__ import annotations

import re
from time import monotonic

from genesleuth import config
from genesleuth.agent.reader import read_case_plan
from genesleuth.alphagenome_client import atlas_scores, score_variant
from genesleuth.schemas import CheckVerdict, Claim, InvestigationResult, RankedSuspect, ToolCall


async def simulate(case, mode, previous, request, emit) -> InvestigationResult:
    """Exercise B2's result and event contract with development-only data."""
    if previous is None:
        phenotypes, plan = read_case_plan(case.referral_pdf)
        emit("read_letter", "Gemini 4 Carbon", "Development fixture read the referral letter",
             phenotypes=[item.model_dump() for item in phenotypes])
        emit("plan", "Gemini 4 Carbon", "Development fixture created a hypothesis plan", **plan)
    else:
        phenotypes = previous.phenotypes
        emit("plan", "Gemini 4 Neon", "Development fixture received a reviewer request", request=request)
    if mode == "atlas_only":
        scores = {key: value["avi"] for key, value in atlas_scores(case.suspects).items()}
    else:
        scores = {variant.variant_id: score_variant(variant, config.BRAIN_TISSUE)["max_abs_effect"]
                  for variant in case.suspects}
    ordered = sorted(case.suspects, key=lambda variant: (-scores[variant.variant_id], variant.variant_id))
    if previous is not None:
        named_variant = next((item for item in ordered if item.variant_id in request), None)
        if named_variant is not None:
            ordered.remove(named_variant)
            ordered.insert(0, named_variant)
    calls = list(previous.tool_calls) if previous else []
    rankings = []
    rejected = previous.n_claims_rejected if previous else 0
    checked = previous.n_claims_checked if previous else 0
    if mode == "full":
        emit("plan", "Decisions API", f"Development fixture triaged {len(ordered)} suspects",
             n_suspects=len(ordered), routed_tissue=config.BRAIN_TISSUE, route_confidence=0.85, elapsed_s=0)
    start = monotonic()
    for rank, variant in enumerate(ordered[:10], start=1):
        claims = []
        verdicts = []
        tissue = config.BRAIN_TISSUE if mode in {"full", "alphagenome_only"} else None
        if mode == "full":
            if request and rank == 1:
                explicit = re.search(r"(?:UBERON|CL):\d+", request)
                tissue = explicit.group() if explicit else (
                    "UBERON:0002037" if "cerebellum" in request.lower() else config.BRAIN_TISSUE
                )
            score = score_variant(variant, tissue)
            call_id = f"c{len(calls) + 1}"
            statement = f"Fixture score {score['max_abs_effect']} in {score['tissue_name']}."
            calls.append(ToolCall(call_id=call_id, tool="alphagenome_score",
                                  args={"variant_id": variant.variant_id, "tissue_ontology_id": tissue},
                                  result=score, result_summary=statement))
            emit("alphagenome", "AlphaGenome", statement, call_id=call_id, tool="alphagenome_score",
                 args=calls[-1].args, n_tool_calls=len(calls), n_alphagenome_calls=len(calls),
                 alphagenome_budget=25, artifact_path=None)
            if rank == 1:
                rejected += 1
                checked += 1
                emit("check", "Code checker", "Development fixture rejected an incorrect tissue claim",
                     claim_id=f"{call_id}-rejected", variant_id=variant.variant_id,
                     text="Fixture claim cited the wrong tissue", verdict="unsupported", confidence=1,
                     reason="Tissue is absent from the cited result")
                emit("revise", "Gemini 4 Neon", "Development fixture revised the claim", round=1, n_rejected=1)
            claim_id = f"{call_id}-supported"
            claims.append(Claim(claim_id=claim_id, variant_id=variant.variant_id, text=statement,
                                cited_call_ids=[call_id]))
            verdicts.append(CheckVerdict(claim_id=claim_id, verdict="supported", confidence=1,
                                         reason="Development fixture", checker="fallback"))
            checked += 1
            emit("check", "Decisions API", statement, claim_id=claim_id, text=statement,
                 variant_id=variant.variant_id, verdict="supported", confidence=1, reason="Development fixture")
        rankings.append(RankedSuspect(rank=rank, variant=variant, score=scores[variant.variant_id],
                                      tissue=tissue, summary="Development fixture",
                                      claims=claims, verdicts=verdicts))
    emit("rank", "GeneSleuth", f"Returned {len(rankings)} development candidates")
    return InvestigationResult(
        case_id=case.case_id, mode=mode, status="ok", ranked=rankings,
        phenotypes=phenotypes, tool_calls=calls,
        n_alphagenome_calls=len(calls), n_tool_calls=len(calls),
        n_claims_checked=checked, n_claims_rejected=rejected,
        timings={"investigation_s": monotonic() - start},
    )
