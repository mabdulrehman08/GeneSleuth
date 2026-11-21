"""STUB investigator for bench dry runs and tests. FABRICATED BEHAVIOUR, NEVER A RESULT.

Feature: a stand-in for genesleuth.agent.api.investigate so the benchmark pipeline (run -> metrics -> report -> chart)
can be exercised end to end before Agent B's agent is on main. It has the same signature and returns real
InvestigationResult objects, but its "reasoning" is seeded noise plus a consequence-severity prior. It never sees
the CaseTruth. bench/run.py only uses it with --dry-run, writes meta.stub = True, and the report prints a STUB banner.

Also provides stub_case(i): a self-contained fake (Case, CaseTruth) pair for unit tests, independent of Agent A's fakes.
"""
from __future__ import annotations

import asyncio
import hashlib
import random
from typing import Callable, Optional

from genesleuth.schemas import (Case, CaseTruth, InvestigationResult, Phenotype, RankedSuspect, ToolCall, TraceEvent,
                                Variant)

_SEV = {"coding": 0.6, "splice": 0.8, "utr5": 0.4, "utr3": 0.4, "promoter": 0.4, "intron": 0.2}
BRAIN, BLOOD = "UBERON:0000955", "UBERON:0000178"


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16))


async def investigate(case: Case, holdout: set[str], mode: str = "full",
                      on_event: Optional[Callable[[TraceEvent], None]] = None, profile: str = "bench") -> InvestigationResult:
    """Stub with the real signature. Quality per mode is arbitrary (full > alphagenome_only > atlas_only > gemini_only)."""
    rng = _rng(case.case_id, mode)
    await asyncio.sleep(0.01)
    noise = {"full": 0.25, "alphagenome_only": 0.5, "atlas_only": 0.6, "gemini_only": 1.2}.get(mode, 0.8)
    scored = [(_SEV.get(v.region, 0.1) + rng.gauss(0, noise), v) for v in case.suspects]
    scored.sort(key=lambda t: -t[0])
    ranked = [RankedSuspect(rank=i, variant=v, score=round(s, 3), tissue=BRAIN if mode in ("full", "alphagenome_only") else None,
                            summary=f"STUB {mode} score {s:.2f}") for i, (s, v) in enumerate(scored[:10], start=1)]
    calls: list[ToolCall] = []
    n_ag = 0
    if mode in ("full", "alphagenome_only"):
        picks = [v for _, v in scored[:14]]
        for k, v in enumerate(picks):
            tissue = BRAIN if (mode == "alphagenome_only" or rng.random() < 0.8) else BLOOD
            calls.append(ToolCall(call_id=f"stub{k}", tool="score_variant", args={"variant_id": v.variant_id, "tissue": tissue},
                                  result={"stub": True, "tissue": tissue, "tissue_name": "brain" if tissue == BRAIN else "blood",
                                          "max_abs_effect": round(rng.random(), 3)}, result_summary="STUB AlphaGenome score"))
        n_ag = len(calls)
    checked = rejected = 0
    if mode == "full":
        checked, rejected = 10, rng.choice([0, 1, 1, 2])
    return InvestigationResult(case_id=case.case_id, mode=mode if mode in ("full", "alphagenome_only", "atlas_only", "gemini_only",
                                                                           "fixed_recipe") else "full",  # type: ignore[arg-type]
                               status="ok", ranked=ranked, phenotypes=[], tool_calls=calls, n_alphagenome_calls=n_ag,
                               n_tool_calls=len(calls), n_claims_checked=checked, n_claims_rejected=rejected,
                               timings={"total": round(rng.uniform(5, 40), 1)})


def stub_case(i: int, split: str = "test", region: str = "intron", gene: str = "SCN1A") -> tuple[Case, CaseTruth]:
    """A fake 60-suspect case; the hidden variant is one of the suspects, indistinguishable by field set."""
    rng = _rng("stubcase", i)
    genes = ["SCN1A", "KCNQ2", "STXBP1", "DNM1", "CDKL5"]
    regions = ["intron", "intron", "coding", "splice", "utr5", "promoter"]
    sus: list[Variant] = []
    for k in range(60):
        pos = 1_000_000 + rng.randrange(0, 900_000)
        ref, alt = rng.sample("ACGT", 2)
        r = rng.choice(regions)
        sus.append(Variant(variant_id=f"chr2-{pos}-{ref}-{alt}", chrom="chr2", pos=pos, ref=ref, alt=alt, gene=rng.choice(genes), region=r,
                           consequence="missense_variant" if r == "coding" else ("intron_variant" if r == "intron" else "splice_region_variant"),
                           genotype="0/1", distance_to_tss=rng.randrange(-5000, 80000)))  # type: ignore[arg-type]
    hidden = sus[rng.randrange(60)]
    hidden = hidden.model_copy(update={"gene": gene, "region": region})
    sus = [hidden if s.variant_id == hidden.variant_id else s for s in sus]
    cid = "%012x" % rng.getrandbits(48)
    pdf = f"stub_letter_{'scanned_' if i % 2 else ''}{cid}.pdf"
    case = Case(case_id=cid, sample_id="STUB", referral_pdf=pdf, suspects=sus, funnel={"suspects": len(sus)})
    truth = CaseTruth(case_id=cid, hidden_variant_id=hidden.variant_id, gene=gene, condition="STUB condition", clinvar_id=str(100000 + i),
                      region=region, true_phenotypes=[Phenotype(hpo_id="HP:0001250", label="Seizure")], split=split)  # type: ignore[arg-type]
    return case, truth
