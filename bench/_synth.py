"""Synthetic result files for unit tests and the dry run. NOT benchmark data.

Everything produced here is fabricated on purpose so that bench/metrics.py,
bench/report.py and bench/run.py can be tested without real cases. Files written by
write_result() carry meta.stub = True so reports built from them print a banner.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from genesleuth.schemas import (CaseTruth, CheckVerdict, Claim, InvestigationResult, Phenotype, RankedSuspect,
                                ToolCall, Variant)


def make_variant(i: int, gene: str = "SCN1A", region: str = "intron", consequence: Optional[str] = None,
                 ref: str = "A", alt: str = "G") -> Variant:
    """A deterministic fake variant on chr2."""
    pos = 165_990_000 + i * 37
    return Variant(variant_id=f"chr2-{pos}-{ref}-{alt}", chrom="chr2", pos=pos, ref=ref, alt=alt, gene=gene,
                   region=region, consequence=consequence or ("missense_variant" if region == "coding" else "intron_variant"),
                   genotype="0/1", distance_to_tss=pos - 165_900_000)


def make_truth(case_id: str, region: str = "intron", gene: str = "SCN1A", split: str = "test") -> CaseTruth:
    hidden = make_variant(9999, gene=gene, region=region, consequence="splice_region_variant" if region == "splice" else None)
    return CaseTruth(case_id=case_id, hidden_variant_id=hidden.variant_id, gene=gene, condition="Dravet syndrome",
                     clinvar_id="12345", region=region,
                     true_phenotypes=[Phenotype(hpo_id="HP:0001250", label="Seizure")], split=split)  # type: ignore[arg-type]


def make_result(case_id: str, mode: str, truth: CaseTruth, hidden_rank: Optional[int], status: str = "ok",
                n_ag: int = 0, claims_checked: int = 0, claims_rejected: int = 0, tool_calls: Optional[list[ToolCall]] = None,
                top_regions: Optional[list[str]] = None, hidden_verdict: Optional[str] = None,
                total_s: float = 10.0) -> InvestigationResult:
    """Build a result where the hidden variant sits at hidden_rank (None = absent). Ranked has 10 entries."""
    top_regions = top_regions or ["coding"] * 10
    ranked = []
    for pos in range(1, 11):
        if hidden_rank == pos:
            v = make_variant(9999, gene=truth.gene, region=truth.region if truth.region != "other" else "intron")
            v = Variant(**{**v.model_dump(), "variant_id": truth.hidden_variant_id})
        else:
            v = make_variant(pos, gene="KCNQ2", region=top_regions[pos - 1])
        s = RankedSuspect(rank=pos, variant=v, score=1.0 - pos / 20, summary=f"synthetic rank {pos}")
        if v.variant_id == truth.hidden_variant_id and hidden_verdict:
            s.claims = [Claim(claim_id=f"c{pos}", variant_id=v.variant_id, text="synthetic claim", cited_call_ids=[])]
            s.verdicts = [CheckVerdict(claim_id=f"c{pos}", verdict=hidden_verdict, confidence=0.9, reason="synthetic",
                                       checker="code")]  # type: ignore[arg-type]
        ranked.append(s)
    return InvestigationResult(case_id=case_id, mode=mode, status=status, ranked=ranked if status == "ok" else [],  # type: ignore[arg-type]
                               phenotypes=truth.true_phenotypes, tool_calls=tool_calls or [], n_alphagenome_calls=n_ag,
                               n_tool_calls=len(tool_calls or []), n_claims_checked=claims_checked,
                               n_claims_rejected=claims_rejected, timings={"total": total_s},
                               error="synthetic error" if status == "error" else None)


def write_result(root: Path, split: str, mode: str, case_id: str, hidden_rank: Optional[int], region: str = "intron",
                 letter_type: str = "clean", stub: bool = True, meta_extra: Optional[dict] = None, **kw) -> Path:
    """Write bench/results-style JSON for one (mode, case)."""
    truth = make_truth(case_id, region=region, split=split)
    res = make_result(case_id, "full" if mode.startswith("full") else mode, truth, hidden_rank, **kw)
    d = Path(root) / split / mode
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{case_id}.json"
    meta = {"letter_type": letter_type, "hidden_in_suspects": True, "n_suspects": 200, "wall_s": 12.0, "stub": stub,
            "profile": "bench", **(meta_extra or {})}
    p.write_text(json.dumps({"result": res.model_dump(), "truth": truth.model_dump(), "meta": meta}), encoding="utf-8")
    return p
