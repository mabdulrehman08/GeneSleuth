"""region_context: gene, region class, consequence, distance to TSS, exon/intron number and nearby genes.

Feature: classify a variant against the MANE Select transcripts of the 58 panel genes using
  * panel_regions.tsv (gene span +/- 10 kb, strand, TSS) and mane_features.tsv.gz (exon / CDS / UTR / codon
    features), both written by slice A1 and read from ROOT/assets first, then DATA_DIR/work;
  * if slice A1's annotated background suspects (suspects_<sample>.json[.gz], VEP/MANE annotations) contain the
    variant, gene / region / consequence / distance_to_tss are taken from there so the answer is identical to what
    the agent sees in Case.suspects; exon/intron numbers are still computed here.
Rules (documented fallback when a variant is not a known suspect):
  coding = inside a CDS exon; utr5 / utr3 = exonic outside the CDS (before start / after stop in transcript order);
  splice = intronic within 8 bp of an exon edge (splice_donor/acceptor_variant at 1-2 bp, else splice_region_variant);
  intron = other intronic; promoter = within 2 kb upstream of the TSS (upstream_gene_variant); other flank = intergenic.
Use cases: the agent calls region_context(variant_id) for cheap context before spending AlphaGenome calls.
Results are cached on disk under DATA_DIR/cache/lookups/region/.
"""
from __future__ import annotations

import csv
import functools
import json
from collections import defaultdict

from ._common import assets_dir, cache_get, cache_put, canonical_id, data_dir, find_table, open_text, parse_variant_id

SPLICE_WINDOW = 8
PROMOTER_BP = 2000
UPSTREAM_BP = 5000


@functools.lru_cache(maxsize=1)
def _genes() -> dict[str, dict]:
    """gene -> {chrom,start,end,strand,tss,ensembl_gene} from panel_regions.tsv (flanks included in start/end)."""
    p = find_table("panel_regions.tsv")
    if p is None:
        raise FileNotFoundError("panel_regions.tsv missing in assets/ and DATA_DIR/work")
    out = {}
    with open_text(p) as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            out[r["gene"]] = {"chrom": r["chrom"], "start": int(r["start"]), "end": int(r["end"]), "strand": r["strand"],
                              "tss": int(r["tss"]), "ensembl_gene": r.get("ensembl_gene", "")}
    return out


@functools.lru_cache(maxsize=1)
def _structure() -> dict[str, dict]:
    """gene -> {exons: [(start,end)] in transcript order, cds: (min,max) or None}."""
    p = find_table("mane_features.tsv.gz")
    if p is None:
        raise FileNotFoundError("mane_features.tsv.gz missing in assets/ and DATA_DIR/work")
    ex: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    cds: dict[str, list[int]] = defaultdict(list)
    with open_text(p) as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            g = r["gene"]
            s, e = int(r["start"]), int(r["end"])
            f = r["feature"]
            if f == "exon":
                ex[g].append((int(r["exon_number"] or 0), s, e))
            elif f in ("CDS", "start_codon", "stop_codon"):
                cds[g] += [s, e]
    out = {}
    for g, lst in ex.items():
        lst.sort()
        out[g] = {"exons": [(s, e) for _n, s, e in lst], "cds": (min(cds[g]), max(cds[g])) if cds.get(g) else None}
    return out


@functools.lru_cache(maxsize=1)
def _suspect_index() -> dict[str, dict]:
    """variant_id -> Variant dict from any suspects_<sample>.json[.gz] found in assets/ or DATA_DIR/work (may be empty)."""
    import gzip
    out: dict[str, dict] = {}
    for d in (assets_dir(), data_dir() / "work"):
        for p in sorted(d.glob("suspects_*.json*")):
            try:
                txt = gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")
                for v in json.loads(txt).get("suspects", []):
                    out.setdefault(v["variant_id"], v)
            except (OSError, ValueError, KeyError):
                continue
    return out


def _classify(gene: str, pos: int) -> dict:
    """Region class and consequence of `pos` relative to the gene's MANE Select transcript."""
    g = _genes()[gene]
    st = _structure().get(gene)
    strand = g["strand"]
    tss = g["tss"]
    res = {"region": "intergenic", "consequence": "intergenic_variant", "exon": None, "intron": None}
    # signed offset along the transcript: negative = upstream of the TSS
    off = (pos - tss) if strand == "+" else (tss - pos)
    if not st:
        return res
    exons = st["exons"]
    gene_lo = min(s for s, _ in exons)
    gene_hi = max(e for _, e in exons)
    if pos < gene_lo or pos > gene_hi:
        upstream = (pos < gene_lo) == (strand == "+")
        d = abs(pos - (gene_lo if pos < gene_lo else gene_hi))
        if upstream and d <= PROMOTER_BP:
            res.update(region="promoter", consequence="upstream_gene_variant")
        elif upstream and d <= UPSTREAM_BP:
            res.update(region="intergenic", consequence="upstream_gene_variant")
        elif not upstream and d <= UPSTREAM_BP:
            res.update(region="intergenic", consequence="downstream_gene_variant")
        return res
    n = len(exons)
    for i, (s, e) in enumerate(exons, 1):
        if s <= pos <= e:
            res["exon"] = i
            cds = st["cds"]
            if cds and cds[0] <= pos <= cds[1]:
                res.update(region="coding", consequence="coding_sequence_variant")
            else:
                before_cds = cds and ((pos < cds[0]) == (strand == "+"))
                res.update(region="utr5" if before_cds else "utr3",
                           consequence="5_prime_UTR_variant" if before_cds else "3_prime_UTR_variant")
            return res
    # intronic: find flanking exons (exons are in transcript order; coordinates descend on the minus strand)
    for i in range(n - 1):
        a, b = exons[i], exons[i + 1]
        lo, hi = (a[1] + 1, b[0] - 1) if strand == "+" else (b[1] + 1, a[0] - 1)
        if lo <= pos <= hi:
            res["intron"] = i + 1
            d_prev = (pos - a[1]) if strand == "+" else (a[0] - pos)  # distance past the preceding exon (donor side)
            d_next = (b[0] - pos) if strand == "+" else (pos - b[1])  # distance before the next exon (acceptor side)
            d = min(d_prev, d_next)
            if d <= SPLICE_WINDOW:
                if d <= 2:
                    cons = "splice_donor_variant" if d_prev < d_next else "splice_acceptor_variant"
                else:
                    cons = "splice_region_variant"
                res.update(region="splice", consequence=cons)
            else:
                res.update(region="intron", consequence="intron_variant")
            res["dist_to_exon_edge"] = d
            return res
    return res


def region_context(variant_id: str) -> dict:
    """Context for a variant: {variant_id, gene, region, consequence, distance_to_tss, exon, intron, strand, nearby_genes, source}."""
    vid = canonical_id(variant_id)
    hit = cache_get("region", vid)
    if hit is not None:
        return hit
    chrom, pos, _ref, _alt = parse_variant_id(vid)
    genes = _genes()
    inside = [g for g, v in genes.items() if v["chrom"] == chrom and v["start"] <= pos <= v["end"]]
    if not inside:
        near = sorted(((min(abs(pos - v["start"]), abs(pos - v["end"])), g) for g, v in genes.items() if v["chrom"] == chrom))
        res = {"variant_id": vid, "gene": None, "region": "intergenic", "consequence": "intergenic_variant",
               "distance_to_tss": None, "exon": None, "intron": None, "strand": None,
               "nearby_genes": [{"gene": g, "distance_bp": d} for d, g in near[:3] if d <= 250_000],
               "source": "MANE v1.5 panel geometry (variant outside all panel regions)"}
        cache_put("region", vid, res)
        return res
    gene = min(inside, key=lambda g: abs(pos - genes[g]["tss"]))
    g = genes[gene]
    cls = _classify(gene, pos)
    dist = abs(pos - g["tss"])
    source = "MANE v1.5 panel geometry"
    sus = _suspect_index().get(vid)
    if sus:
        gene = sus.get("gene") or gene
        for k in ("region", "consequence"):
            if sus.get(k):
                cls[k] = sus[k]
        if sus.get("distance_to_tss") is not None:
            dist = sus["distance_to_tss"]
        source = "annotated suspects (VEP/MANE) + MANE v1.5 exon numbering"
    res = {"variant_id": vid, "gene": gene, "region": cls["region"], "consequence": cls["consequence"],
           "distance_to_tss": dist, "exon": cls.get("exon"), "intron": cls.get("intron"), "strand": g["strand"],
           "nearby_genes": [{"gene": o, "distance_bp": min(abs(pos - genes[o]["start"]), abs(pos - genes[o]["end"]))}
                            for o in genes if o != gene and genes[o]["chrom"] == chrom
                            and min(abs(pos - genes[o]["start"]), abs(pos - genes[o]["end"])) <= 250_000],
           "source": source}
    if "dist_to_exon_edge" in cls:
        res["dist_to_exon_edge"] = cls["dist_to_exon_edge"]
    cache_put("region", vid, res)
    return res
