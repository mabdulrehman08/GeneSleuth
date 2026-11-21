"""Background suspects (feature: the ~100-300 rare, annotated variants of the background sample).

Pipeline (computed once per sample, cached):
    background.load_background  -> every non-reference variant of the sample in the 58 panel regions
    filter.gnomad_for           -> gnomAD v4.1 genome AF streamed at the sample's own positions
    rarity threshold            -> AF < 0.001 or AF < 0.01, whichever leaves 100-300 suspects (both counts recorded)
    annotate.annotate_many      -> region / consequence / distance_to_tss from the MANE Select models
    trimming                    -> if more than 300 remain, keep all coding/splice/UTR/promoter variants and the
                                   introns closest to exon boundaries

Output (no planted variant inside):
    DATA_DIR/work/suspects_<sample>.json and the committed bundle assets/suspects_<sample>.json.gz
        {"sample_id", "af_threshold", "funnel": {ints}, "suspects": [Variant dicts],
         "frequencies": {variant_id: {gnomad_af, gnomad_grpmax, gnomad_an, kg_af, af_source}}}
    `frequencies` also covers every variant of the background (not only suspects) for population_frequency lookups.

Use cases:
    data = load_suspects("NA12878")      # dict; data["suspects"] is a list[Variant]
    raw = load_suspects_raw("NA12878")   # the JSON as stored (Variant dicts)
"""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

from genesleuth import config
from genesleuth.data import annotate, background, filter as flt, panel
from genesleuth.schemas import Variant

WORK = config.DATA_DIR / "work"
ASSETS = config.ROOT / "assets"
TARGET_MIN, TARGET_MAX = 100, 300
THRESHOLDS = (0.001, 0.01)


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def choose_threshold(counts: dict[float, int]) -> float:
    """Strictest threshold leaving 100-300 suspects; otherwise the one closest to 200."""
    for t in THRESHOLDS:
        if TARGET_MIN <= counts[t] <= TARGET_MAX:
            return t
    return min(THRESHOLDS, key=lambda t: abs(counts[t] - 200))


def build_suspects(sample: str | None = None, force: bool = False) -> dict:
    """Build (or return the cached) suspects bundle for `sample`; writes work/ json and assets/ json.gz."""
    sample = sample or config.DEFAULT_SAMPLE
    if not force:
        try:
            return load_suspects_raw(sample)
        except FileNotFoundError:
            pass
    rows = background.load_background(sample)
    gn = flt.gnomad_for(rows, sample)
    rows = flt.apply_frequency(rows, gn)
    counts = {t: flt.count_rare(rows, t) for t in THRESHOLDS}
    thr = choose_threshold(counts)
    rare = [r for r in rows if flt.is_rare(r, thr)]
    ann = annotate.annotate_many([(r["chrom"], r["pos"], r["ref"], r["alt"], r["gt"]) for r in rare])
    kept = [(v, k) for v, k in ann if v.gene]
    if len(kept) > TARGET_MAX:
        keep_all = [x for x in kept if x[0].region != "intron"]
        introns = sorted((x for x in kept if x[0].region == "intron"),
                         key=lambda x: x[1]["boundary_distance"] if x[1]["boundary_distance"] is not None else 10**9)
        kept = keep_all + introns[:max(0, TARGET_MAX - len(keep_all))]
    kept.sort(key=lambda x: (x[0].chrom, x[0].pos))
    suspects = [v for v, _ in kept]
    funnel = {"variants_in_panel_regions": len(rows), "rare_af_lt_0.01": counts[0.01], "rare_af_lt_0.001": counts[0.001],
              "rare": len(rare), "suspects": len(suspects)}
    freqs = {annotate.variant_id(r["chrom"], r["pos"], r["ref"], r["alt"]): {
        "gnomad_af": r["gnomad_af"], "gnomad_grpmax": r["gnomad_grpmax"], "gnomad_an": r["gnomad_an"],
        "kg_af": r["af"], "af_source": r["af_source"]} for r in rows}
    data = {"sample_id": sample, "af_threshold": thr, "funnel": funnel,
            "suspects": [v.model_dump() for v in suspects], "frequencies": freqs}
    raw = json.dumps(data, separators=(",", ":")).encode()
    _atomic(WORK / f"suspects_{sample}.json", raw)
    _atomic(ASSETS / f"suspects_{sample}.json.gz", gzip.compress(raw, 9, mtime=0))
    print("funnel", funnel, "threshold", thr)
    return data


def load_suspects_raw(sample_id: str | None = None) -> dict:
    """The stored JSON (assets/ first, then DATA_DIR/work). Raises FileNotFoundError if not built."""
    sample_id = sample_id or config.DEFAULT_SAMPLE
    gz = ASSETS / f"suspects_{sample_id}.json.gz"
    if gz.exists():
        return json.loads(gzip.decompress(gz.read_bytes()))
    p = WORK / f"suspects_{sample_id}.json"
    if p.exists():
        return json.loads(p.read_text())
    raise FileNotFoundError(f"suspects bundle for {sample_id} not built (run scripts/data_background.py)")


def load_suspects(sample_id: str | None = None) -> dict:
    """Stored bundle with `suspects` parsed into genesleuth.schemas.Variant objects (builds it if missing)."""
    try:
        d = load_suspects_raw(sample_id)
    except FileNotFoundError:
        d = build_suspects(sample_id)
    d = dict(d)
    d["suspects"] = [Variant(**v) for v in d["suspects"]]
    return d
