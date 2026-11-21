"""Variant annotation from the MANE Select transcripts (feature: region / consequence / TSS distance).

Classifies a variant against the committed MANE Select exon / CDS / UTR features of the 58 panel genes
(genesleuth.data.panel) instead of calling VEP for every variant: that is exact for non-coding positions
(splice sites, introns, UTRs, promoter) and takes microseconds. VEP REST (cached, one batch call) is used only
to name the most severe consequence of CODING variants (missense vs synonymous vs stop ...), because that needs
the reference codon; if VEP is unreachable the coding term falls back to a generic one from the GTF.

Rules (SO terms, MANE Select only, transcript orientation):
    splice   : intron bases 1-2 from an exon boundary (splice_donor/acceptor_variant) or 3-8 (splice_region_variant)
    coding   : inside CDS/start/stop codon (VEP term; frameshift/inframe for indels from the length change)
    utr5/utr3: inside a UTR exon
    intron   : other intronic positions (consequence intron_variant)
    promoter : upstream of the TSS, <= 2,000 bp (upstream_gene_variant)
    intergenic: flank positions further upstream or downstream (upstream/downstream_gene_variant)
distance_to_tss is signed in transcript orientation (negative = upstream of the TSS).

Use cases:
    annotate_variant("chr2", 166000000, "A", "G", genotype="0/1") -> genesleuth.schemas.Variant
    classify("chr2", 166000000, "A", "G") -> dict incl. min distance to the nearest exon boundary
"""
from __future__ import annotations

import json
import os
import time
from functools import lru_cache

import requests

from genesleuth import config
from genesleuth.data import panel
from genesleuth.schemas import Variant

PROMOTER_BP = 2000
VEP_URL = "https://rest.ensembl.org/vep/homo_sapiens/region"
VEP_CACHE = config.CACHE_DIR / "a1_vep_coding.json"
_REGION_RANK = {"splice": 5, "coding": 4, "utr5": 3, "utr3": 3, "intron": 2, "promoter": 1, "intergenic": 0, "other": 0}
_VEP_CODING = {"missense_variant", "synonymous_variant", "stop_gained", "stop_lost", "start_lost", "frameshift_variant",
               "inframe_insertion", "inframe_deletion", "protein_altering_variant", "stop_retained_variant",
               "start_retained_variant", "incomplete_terminal_codon_variant", "coding_sequence_variant"}


def variant_id(chrom: str, pos: int, ref: str, alt: str) -> str:
    """gnomAD-style id with chr prefix, e.g. chr2-165991234-A-G."""
    return f"{chrom}-{pos}-{ref}-{alt}"


@lru_cache(maxsize=None)
def _gene_model(gene: str) -> dict:
    """Exons (sorted), CDS bounds and UTR intervals for one gene's MANE Select transcript."""
    feats = panel.load_features()[gene]
    exons = sorted(((f["start"], f["end"]) for f in feats if f["feature"] == "exon"))
    cds = [(f["start"], f["end"]) for f in feats if f["feature"] in ("CDS", "start_codon", "stop_codon")]
    utr = [(f["start"], f["end"]) for f in feats if f["feature"] == "UTR"]
    strand = feats[0]["strand"]
    return {"exons": exons, "cds": cds, "utr": utr, "strand": strand,
            "cds_min": min(s for s, _ in cds) if cds else None, "cds_max": max(e for _, e in cds) if cds else None,
            "tx_start": exons[0][0], "tx_end": exons[-1][1]}


def _gene_for(chrom: str, pos: int) -> dict | None:
    """Panel region for a position: prefer the gene whose transcript body contains it, else nearest TSS."""
    hits = [r for r in panel.load_panel_regions() if r["chrom"] == chrom and r["start"] <= pos <= r["end"]]
    if not hits:
        return None
    body = [r for r in hits if r["gene_start"] <= pos <= r["gene_end"]] if "gene_start" in hits[0] else []
    if not body:
        body = [r for r in hits if _gene_model(r["gene"])["tx_start"] <= pos <= _gene_model(r["gene"])["tx_end"]]
    return min(body or hits, key=lambda r: abs(r["tss"] - pos))


def _classify_pos(gene: str, strand: str, tss: int, pos: int) -> tuple[str, str, int | None]:
    """Return (region, consequence, boundary_distance) for one reference position of one gene."""
    m = _gene_model(gene)
    if m["tx_start"] <= pos <= m["tx_end"]:
        for s, e in m["exons"]:
            if s <= pos <= e:
                if any(us <= pos <= ue for us, ue in m["utr"]):
                    five = (pos < m["cds_min"]) if strand == "+" else (pos > m["cds_max"])
                    return ("utr5", "5_prime_UTR_variant", 0) if five else ("utr3", "3_prime_UTR_variant", 0)
                return "coding", "coding_sequence_variant", 0
        exons = m["exons"]
        for (s1, e1), (s2, e2) in zip(exons, exons[1:]):
            if e1 < pos < s2:
                d_left, d_right = pos - e1, s2 - pos            # bases from the exon on each side
                d = min(d_left, d_right)
                if d <= 2:
                    donor_side_left = (strand == "+")            # on '+', the left exon's end is the donor
                    is_donor = (d_left <= 2) == donor_side_left
                    return "splice", ("splice_donor_variant" if is_donor else "splice_acceptor_variant"), d
                if d <= 8:
                    return "splice", "splice_region_variant", d
                return "intron", "intron_variant", d
        return "other", "intron_variant", None
    up = (pos < m["tx_start"]) if strand == "+" else (pos > m["tx_end"])
    dist = abs(pos - tss)
    if up:
        return (("promoter", "upstream_gene_variant", dist) if dist <= PROMOTER_BP
                else ("intergenic", "upstream_gene_variant", dist))
    return "intergenic", "downstream_gene_variant", dist


def classify(chrom: str, pos: int, ref: str, alt: str) -> dict:
    """Classify one variant against the panel's MANE Select models (no network)."""
    g = _gene_for(chrom, pos)
    if g is None:
        return {"gene": None, "region": "other", "consequence": None, "distance_to_tss": None, "boundary_distance": None}
    start = pos + 1 if len(ref) != len(alt) else pos            # indel: first affected base after the anchor
    end = max(start, pos + len(ref) - 1)
    cands = [_classify_pos(g["gene"], g["strand"], g["tss"], p) for p in sorted({start, end})]
    region, cons, bd = max(cands, key=lambda c: _REGION_RANK[c[0]])
    if region == "coding" and len(ref) != len(alt):
        diff = abs(len(ref) - len(alt))
        cons = "frameshift_variant" if diff % 3 else ("inframe_insertion" if len(alt) > len(ref) else "inframe_deletion")
    tss_d = (pos - g["tss"]) * (1 if g["strand"] == "+" else -1)
    return {"gene": g["gene"], "region": region, "consequence": cons, "distance_to_tss": tss_d, "boundary_distance": bd}


def _load_vep_cache() -> dict:
    try:
        return json.loads(VEP_CACHE.read_text())
    except Exception:
        return {}


def vep_most_severe(variants: list[tuple[str, int, str, str]]) -> dict[str, str]:
    """VEP REST most_severe_consequence for (chrom,pos,ref,alt) tuples (batches of 200, disk-cached by variant id)."""
    cache = _load_vep_cache()
    todo = [v for v in variants if variant_id(*v) not in cache]
    for i in range(0, len(todo), 200):
        batch = todo[i:i + 200]
        body = {"variants": [f"{c.replace('chr', '')} {p} . {r} {a} . . ." for c, p, r, a in batch]}
        for attempt in range(3):
            try:
                resp = requests.post(VEP_URL, json=body, headers={"Accept": "application/json"}, timeout=60)
                if resp.status_code == 429:
                    time.sleep(2 + attempt * 2)
                    continue
                resp.raise_for_status()
                by_input = {d["input"]: d.get("most_severe_consequence") for d in resp.json()}
                for (c, p, r, a) in batch:
                    k = f"{c.replace('chr', '')} {p} . {r} {a} . . ."
                    if by_input.get(k):
                        cache[variant_id(c, p, r, a)] = by_input[k]
                break
            except Exception:
                time.sleep(1)
    if todo:
        VEP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = VEP_CACHE.with_name(VEP_CACHE.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(cache))
        os.replace(tmp, VEP_CACHE)
    return {variant_id(*v): cache[variant_id(*v)] for v in variants if variant_id(*v) in cache}


def annotate_many(items: list[tuple[str, int, str, str, str | None]]) -> list[tuple[Variant, dict]]:
    """Annotate (chrom,pos,ref,alt,genotype) tuples: GTF classification, then one VEP batch for coding ones."""
    cls = [classify(c, p, r, a) for c, p, r, a, _ in items]
    coding = [(c, p, r, a) for (c, p, r, a, _), k in zip(items, cls) if k["region"] == "coding"]
    vep = vep_most_severe(coding) if coding else {}
    out = []
    for (c, p, r, a, gt), k in zip(items, cls):
        vid = variant_id(c, p, r, a)
        cons = k["consequence"]
        if k["region"] == "coding" and vid in vep:
            cons = vep[vid]
        out.append((Variant(variant_id=vid, chrom=c, pos=p, ref=r, alt=a, gene=k["gene"], region=k["region"],
                            consequence=cons, genotype=gt, distance_to_tss=k["distance_to_tss"]), k))
    return out


def annotate_variant(chrom: str, pos: int, ref: str, alt: str, genotype: str | None = "0/1") -> Variant:
    """Annotate one variant exactly like the background suspects (used by build_case for the planted variant)."""
    if not chrom.startswith("chr"):
        chrom = "chr" + chrom
    return annotate_many([(chrom, int(pos), ref, alt, genotype)])[0][0]
