"""Regression tests for deterministic evidence validation."""
import pytest

from genesleuth.checker.gate import code_check
from genesleuth.schemas import Claim, ToolCall, Variant


@pytest.fixture
def evidence():
    """Construct a candidate and its one brain score result."""
    variant = Variant(variant_id="chr2-123456-A-G", chrom="chr2", pos=123456, ref="A", alt="G", gene="SCN1A")
    call = ToolCall(
        call_id="c17", tool="alphagenome_score",
        args={"variant_id": variant.variant_id, "tissue_ontology_id": "UBERON:0000955"},
        result={"tissue": "UBERON:0000955", "tissue_name": "brain",
                "scores": {"SPLICE_SITE_USAGE": -0.7132}, "max_abs_effect": 0.7132},
        result_summary="Brain predicted effect of -0.7132",
    )
    return variant, {call.call_id: call}


@pytest.mark.parametrize(("text", "citations", "reason"), [
    ("Predicted brain effect of -0.57", ["c17"], "number"),
    ("Predicted blood effect of -0.71", ["c17"], "tissue"),
    ("Predicted brain effect of -0.71", [], "citation"),
    ("Predicted brain effect of -0.71", ["c19"], "citation"),
    ("Predicted brain effect of -0.71 for chr3-765432-G-A", ["c17"], "variant"),
    ("SCN1A has a predicted brain effect of -0.71 (UBERON:0000955) [c17].", ["c17"], None),
])
def test_code_check(evidence, text, citations, reason):
    """Require relevant and numerically matched evidence before a semantic check."""
    variant, ledger = evidence
    claim = Claim(claim_id="claim-1", variant_id=variant.variant_id, text=text, cited_call_ids=citations)
    verdict, relevant = code_check(claim, variant, ledger)
    if reason is None:
        assert verdict is None and set(relevant) == {"c17"}
    else:
        assert verdict.verdict == "unsupported" and reason in verdict.reason
