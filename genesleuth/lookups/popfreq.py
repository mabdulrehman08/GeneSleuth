"""Serve population frequency as a bucket from the local gnomAD v4.1 bundle."""

from __future__ import annotations

import functools
import json

from ._common import assets_dir, cache_get, cache_put, canonical_id, data_dir, open_text

SOURCE = "gnomAD v4.1"
LOW_AF_BIN = "<0.1%"
HIGH_AF_BIN = "0.1-1%"
_CACHE = "popfreq-bins-v1"


@functools.lru_cache(maxsize=4)
def _precomputed(assets, work) -> dict[str, dict]:
    """Load the bundled frequency records, preferring committed assets."""
    records = {}
    for directory in (assets, work):
        for path in sorted(directory.glob("suspects_*.json*")):
            try:
                with open_text(path) as stream:
                    frequencies = json.load(stream).get("frequencies") or {}
            except (OSError, ValueError):
                continue
            for variant_id, record in frequencies.items():
                records.setdefault(variant_id, record)
    return records


def _bucket(variant_id: str) -> str:
    """Bucket a prepared genome AF, treating absent local observations as rare."""
    frequency = _precomputed(assets_dir(), data_dir() / "work").get(variant_id, {}).get("gnomad_af")
    return HIGH_AF_BIN if isinstance(frequency, (float, int)) and frequency >= 0.001 else LOW_AF_BIN


def prepare_frequency_bins(variant_ids: list[str]) -> None:
    """Precompute all case candidates, including the spike-in, through the same path."""
    for variant_id in variant_ids:
        vid = canonical_id(variant_id)
        bucket = _bucket(vid)
        if cache_get(_CACHE, vid) != bucket:
            cache_put(_CACHE, vid, bucket)


def population_frequency(variant_id: str) -> dict:
    """Return only the frequency bucket and constant source, without a network call."""
    vid = canonical_id(variant_id)
    bucket = cache_get(_CACHE, vid)
    if bucket not in (LOW_AF_BIN, HIGH_AF_BIN):
        bucket = _bucket(vid)
    return {"af_bin": bucket, "source": SOURCE}
