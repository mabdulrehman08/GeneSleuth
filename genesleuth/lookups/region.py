"""Compute a common MANE annotation for every candidate's region context."""

from __future__ import annotations

import functools

from genesleuth.data import annotate, panel

from ._common import cache_get, cache_put, canonical_id, parse_variant_id

SOURCE = "MANE v1.5 + VEP"
_CACHE = "region-uniform-v1"


@functools.lru_cache(maxsize=None)
def _exons(gene: str) -> tuple:
    """Return the MANE exons in transcript order."""
    return tuple(sorted(
        (feature for feature in panel.load_features().get(gene, []) if feature["feature"] == "exon"),
        key=lambda feature: int(feature["exon_number"] or 0),
    ))


def _numbers(gene: str, pos: int) -> tuple[int | None, int | None]:
    """Find an exon or the preceding intron number in transcript order."""
    exons = _exons(gene)
    for exon in exons:
        if exon["start"] <= pos <= exon["end"]:
            return int(exon["exon_number"] or 0) or None, None
    for first, second in zip(exons, exons[1:]):
        lo = min(first["end"], second["end"])
        hi = max(first["start"], second["start"])
        if lo < pos < hi:
            return None, int(first["exon_number"] or 0) or None
    return None, None


def region_context(variant_id: str) -> dict:
    """Annotate all variants uniformly, keeping optional fields present as null."""
    vid = canonical_id(variant_id)
    if (cached := cache_get(_CACHE, vid)) is not None:
        return cached

    chrom, pos, ref, alt = parse_variant_id(vid)
    annotation = annotate.classify(chrom, pos, ref, alt)
    gene = annotation["gene"]
    exon, intron = _numbers(gene, pos) if gene else (None, None)
    nearby = []
    strand = None
    for entry in panel.load_panel_regions():
        if entry["chrom"] != chrom:
            continue
        if entry["gene"] == gene:
            strand = entry["strand"]
            continue
        distance = max(entry["start"] - pos, pos - entry["end"], 0)
        if distance <= 250_000:
            nearby.append({"gene": entry["gene"], "distance_bp": distance})
    nearby.sort(key=lambda item: (item["distance_bp"], item["gene"]))

    result = {
        "variant_id": vid,
        "gene": gene,
        "region": annotation["region"] if gene else "intergenic",
        "consequence": annotation["consequence"] if gene else "intergenic_variant",
        "distance_to_tss": annotation["distance_to_tss"],
        "exon": exon,
        "intron": intron,
        "strand": strand,
        "dist_to_exon_edge": annotation["boundary_distance"] if intron is not None else None,
        "nearby_genes": nearby,
        "source": SOURCE,
    }
    cache_put(_CACHE, vid, result)
    return result
