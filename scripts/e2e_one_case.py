"""Run a real GeneSleuth demo case and report the result against held-out truth."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import monotonic

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genesleuth import config
from genesleuth.agent.api import investigate


async def run(option_id: str | None, seed: int) -> int:
    """Build one case, investigate it and reveal the held-out variant's rank."""
    if config.FAKE_MODE:
        print("Real integration requires FAKE_MODE=0", file=sys.stderr)
        return 2
    try:
        from genesleuth.data.api import build_case, holdout_for
        from genesleuth.data.cases import real_ready
    except ImportError:
        print("Side A case builder is unavailable. Pull main and run scripts/data_setup.py.", file=sys.stderr)
        return 2
    if not real_ready():
        print("Side A demo assets are incomplete. Run scripts/data_setup.py before the real integration.", file=sys.stderr)
        return 2
    start = monotonic()
    try:
        case, truth = await asyncio.to_thread(build_case, option_id=option_id, split="demo", seed=seed)
    except Exception as error:
        print(f"Side A build_case failed ({type(error).__name__}). Check the demo data bundle.", file=sys.stderr)
        return 2
    build_s = monotonic() - start

    def progress(event):
        """Print live trace summaries without raw referral content or credentials."""
        if event.step != "done":
            print(f"+{event.t:5.1f}s {event.actor} | {event.summary}", file=sys.stderr, flush=True)

    result = await investigate(case, holdout_for(truth), profile="demo", on_event=progress)
    rank = next((item.rank for item in result.ranked if item.variant.variant_id == truth.hidden_variant_id), None)
    print(json.dumps({
        "case_id": case.case_id,
        "status": result.status,
        "hidden_variant_rank": rank,
        "candidates": len(case.suspects),
        "ranked": len(result.ranked),
        "build_case_s": round(build_s, 2),
        "investigation_s": round(result.timings.get("total_s", 0), 2),
        "total_s": round(monotonic() - start, 2),
        "alphagenome_calls": result.n_alphagenome_calls,
        "claims_checked": result.n_claims_checked,
        "claims_rejected": result.n_claims_rejected,
        "error": result.error,
    }, indent=2))
    return 0 if result.status == "ok" else 1


def main() -> int:
    """Parse case selection options and execute the integration test."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-id")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    return asyncio.run(run(args.option_id, args.seed))


if __name__ == "__main__":
    raise SystemExit(main())
