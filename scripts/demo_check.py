"""Check the live data bundle, provider keys, and referral path before judging."""

from __future__ import annotations

import os
from pathlib import Path
from time import monotonic

from genesleuth.config import ALPHAGENOME_API_KEY, BRAIN_TISSUE, BLOOD_TISSUE, FAKE_MODE, GEMINI_API_KEY
from genesleuth.server.integration import case_api


def check_case():
    """Build one real case and verify the local PDF and leakage boundary."""
    adapter = case_api()
    choices = adapter.list_demo_options()
    if not choices:
        raise ValueError("The demo case pool is empty.")
    case, truth = adapter.build_case(split="demo")
    with Path(case.referral_pdf).open("rb") as document:
        valid_pdf = document.read(5) == b"%PDF-"
    if not valid_pdf or not case.suspects or case.case_id != truth.case_id:
        raise ValueError("The case, referral, or candidate list is incomplete.")
    if truth.hidden_variant_id not in adapter.holdout_for(truth):
        raise ValueError("The planted case variant is missing from the holdout.")
    background = next(variant for variant in case.suspects if variant.variant_id != truth.hidden_variant_id)
    return case, background


def check_alphagenome(background) -> None:
    """Verify the configured conditions and score one background candidate."""
    from genesleuth.alphagenome_client import list_tissues, score_variant

    supported = {row["ontology_id"] for row in list_tissues()}
    if not {BRAIN_TISSUE, BLOOD_TISSUE}.issubset(supported):
        raise ValueError("Configured brain or blood condition is unavailable.")
    result = score_variant(background, BRAIN_TISSUE)
    if not isinstance(result, dict) or result.get("error") or result.get("max_abs_effect") is None:
        raise ValueError("AlphaGenome did not return a usable score.")


def check_decisions() -> None:
    """Verify the shared Decisions API client with one evidence entailment question."""
    from genesleuth.gemini_clients import decide

    answers = decide(
        [{"type": "text", "text": "Evidence: the example assay was recorded in blood."}],
        {"supports": {"type": "noul", "instructions": "Does the evidence say the assay was recorded in blood?"}},
    )
    answer = answers["supports"]
    if not (answer.noul is not None and answer.noul >= 0.7 and
            answer.confidence is not None and answer.confidence >= 0.6):
        raise ValueError("Decision 1 did not return a confident supported answer.")


def check_referral(case) -> None:
    """Confirm that the shared reader returns phenotypes from a live referral."""
    from genesleuth.agent.reader import read_referral

    if not read_referral(case.referral_pdf):
        raise ValueError("Carbon did not return any mapped referral findings.")


def run(label: str, check, *args):
    """Print a timed PASS or FAIL without exposing provider request details."""
    started = monotonic()
    try:
        result = check(*args)
        print(f"PASS {label} ({monotonic() - started:.1f} s)", flush=True)
        return True, result
    except Exception as error:
        print(f"FAIL {label} ({type(error).__name__}).", flush=True)
        return False, None


def main() -> int:
    """Run live checks while preserving a nonzero exit for any failed requirement."""
    if FAKE_MODE or os.getenv("CHECKER_FALLBACK", "").strip():
        print("FAIL live mode is required. Clear FAKE_MODE and CHECKER_FALLBACK.")
        return 1
    missing = [
        name for name, key in (
            ("GEMINI_API_KEY", GEMINI_API_KEY), ("ALPHA_GENOME_API_KEY", ALPHAGENOME_API_KEY),
        ) if not key.strip()
    ]
    if missing:
        print(f"FAIL missing settings {', '.join(missing)}.")
        return 1
    print("PASS both key settings present.")
    case_ok, data = run("real case and referral PDF", check_case)
    decisions_ok, _ = run("Decision 1", check_decisions)
    if not case_ok:
        print("FAIL AlphaGenome and Carbon checks require a real case.")
        return 1
    case, background = data
    genome_ok, _ = run("AlphaGenome brain and blood conditions and background score", check_alphagenome, background)
    referral_ok, _ = run("Carbon referral reading", check_referral, case)
    return int(not all((case_ok, decisions_ok, genome_ok, referral_ok)))


if __name__ == "__main__":
    raise SystemExit(main())
