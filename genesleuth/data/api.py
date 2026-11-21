"""Public data interface used by the agent side: demo options, case building and the leakage holdout.

Feature: the three functions below are the contract with Agent B (see section 7 of the shared brief).
With FAKE_MODE=1, or when the real case data is not ready yet, the fakes in fakes.py are used instead.
"""
from __future__ import annotations

from genesleuth import config
from genesleuth.schemas import Case, CaseTruth, DemoOption
from genesleuth.data import fakes


def _real_ready() -> bool:
    """True when the real case builder is importable and its inputs exist (never true in FAKE_MODE)."""
    if config.FAKE_MODE:
        return False
    try:
        from genesleuth.data import cases
        return cases.real_ready()
    except Exception:
        return False


def list_demo_options() -> list[DemoOption]:
    """Return the demo picker options, labelled like 'SCN1A, splice region, Dravet syndrome'."""
    if _real_ready():
        from genesleuth.data import cases
        return cases.list_demo_options()
    return fakes.fake_demo_options()


def build_case(option_id: str | None = None, sample_id: str | None = None, split: str = "demo",
               seed: int = 0) -> tuple[Case, CaseTruth]:
    """Build a case with the chosen option planted as an unknown variant; option_id=None means a random option."""
    if _real_ready():
        from genesleuth.data import cases
        return cases.build_case(option_id, sample_id, split, seed)
    return fakes.fake_build_case(option_id, sample_id, split, seed)


def holdout_for(truth: CaseTruth) -> set[str]:
    """Variant ids and ClinVar ids to hide from lookups so the planted variant looks novel."""
    return fakes.fake_holdout_for(truth)
