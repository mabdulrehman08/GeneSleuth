"""Populate shared Atlas and AlphaGenome caches from background variants only."""

from __future__ import annotations

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from genesleuth.config import ALPHAGENOME_API_KEY, BLOOD_TISSUE, BRAIN_TISSUE, DEFAULT_SAMPLE, FAKE_MODE
from genesleuth.schemas import Variant


def background(sample_id: str, source: Path | None) -> list[Variant]:
    """Read Side A's background bundle and exclude potential spike-in positions."""
    from genesleuth.data import cases, splits

    if source is None:
        rows = cases.load_background(sample_id)["suspects"]
    else:
        read = gzip.open if source.suffix == ".gz" else open
        with read(source, "rt", encoding="utf-8") as stream:
            exported = json.load(stream)
        rows = exported["suspects"] if isinstance(exported, dict) else exported

    excluded = {
        (candidate["chrom"], candidate["pos"])
        for candidate in splits.load_candidates()["by_id"].values()
    }
    variants = [Variant.model_validate(row) for row in rows]
    return [variant for variant in variants if (variant.chrom, variant.pos) not in excluded]


def prewarm(variants: list[Variant], workers: int) -> int:
    """Score the supplied background candidates in both demo conditions."""
    from genesleuth.alphagenome_client import atlas_scores, score_variant

    atlas = atlas_scores(variants)
    available = sum(row.get("avi") is not None for row in atlas.values())
    print(f"AlphaGenome Atlas (AG1) AVI present for {available}/{len(variants)} background candidates.", flush=True)
    jobs = [(variant, tissue) for variant in variants for tissue in (BRAIN_TISSUE, BLOOD_TISSUE)]

    def score(job: tuple[Variant, str]) -> bool:
        """Evaluate one cacheable background variant and tissue pair."""
        result = score_variant(*job)
        return result.get("error") is None and result.get("max_abs_effect") is not None

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, ok in enumerate(pool.map(score, jobs), start=1):
            failures += not ok
            if index % 20 == 0 or index == len(jobs):
                print(f"AlphaGenome live score cache {index - failures}/{index} successful "
                      f"({len(jobs)} pairs scheduled).", flush=True)
    return failures


def main() -> int:
    """Run prewarming with bounded concurrency and an optional background export."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default=DEFAULT_SAMPLE)
    parser.add_argument("--background", type=Path, help="Side A's background-only JSON or JSON.gz bundle")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    if FAKE_MODE or not ALPHAGENOME_API_KEY:
        print("FAIL prewarm requires live mode and an AlphaGenome API key.")
        return 1
    try:
        variants = list({item.variant_id: item for item in background(args.sample, args.background)}.values())
        if not variants:
            print("FAIL no background suspects were provided.")
            return 1
        failures = prewarm(variants, args.workers)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        print(f"FAIL background or cache unavailable ({type(error).__name__}). "
              "Check Side A's background export and AlphaGenome setup.")
        return 1
    except Exception as error:
        print(f"FAIL AlphaGenome prewarm failed ({type(error).__name__}).")
        return 1
    print("PASS background caches populated." if not failures else f"FAIL {failures} live score pairs need retry.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
