"""Real case builder: plants one ClinVar pathogenic variant into a real 1000 Genomes background sample.

Feature: list_demo_options() and build_case() backed by real data (see api.py for the public wrappers).
How a case is built (target < 20 s, normally well under 1 s because everything heavy is pre-computed):
  1. the background suspects of the sample (slice A1: suspects_<sample>.json[.gz], real 1000G variants in the panel regions after
     the rarity filter, annotated with the same pipeline) are loaded once and cached in memory;
  2. the chosen ClinVar variant is injected as genotype 0/1, annotated with the same annotator and the same Variant field set
     as every background suspect (the Variant schema has no allele-frequency field, so nothing reveals the planted one);
  3. suspects are shuffled with a seeded RNG, the funnel counts include the planted variant, the pre-generated referral
     letter is attached and a deterministic hex case_id (hash of option, sample and seed) is assigned;
  4. CaseTruth carries the hidden variant, gene, condition, ClinVar id, region and the synthetic true phenotypes.
Data is read from the committed assets/ bundle first, then DATA_DIR/work.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import time
from functools import lru_cache
from pathlib import Path

from genesleuth import config
from genesleuth.data import letters, splits
from genesleuth.schemas import Case, CaseTruth, DemoOption, Phenotype, Variant

WORK = config.DATA_DIR / "work"
ASSETS = config.ROOT / "assets"
REGION_WORD = {"splice": "splice region", "intron": "deep intronic", "utr5": "5' UTR", "utr3": "3' UTR", "promoter": "promoter",
               "coding": "coding", "intergenic": "intergenic", "other": "other"}


# ----------------------------------------------------------------- data access

def _sample(sample_id: str | None) -> str:
    """Resolve the background sample id."""
    return sample_id or config.DEFAULT_SAMPLE


def _suspects_path(sample: str) -> Path | None:
    """Locate the background suspects file (assets/ first, then DATA_DIR/work)."""
    for n in (f"suspects_{sample}.json.gz", f"suspects_{sample}.json"):
        p = splits.find(n)
        if p:
            return p
    return None


@lru_cache(maxsize=4)
def load_background(sample: str) -> dict:
    """Load {'sample_id', 'funnel', 'suspects'} from A1's file; cached in memory."""
    p = _suspects_path(sample)
    if p is None:
        raise FileNotFoundError(f"suspects_{sample}.json(.gz) not found in assets/ or DATA_DIR/work (slice A1 output)")
    d = json.loads(gzip.open(p, "rt", encoding="utf-8").read()) if p.suffix == ".gz" else json.loads(p.read_text(encoding="utf-8"))
    return d


def _letter_pdf(option_id: str) -> Path | None:
    """Path of the pre-generated letter PDF (assets/letters first, then DATA_DIR/work/letters)."""
    for base in (ASSETS / "letters", WORK / "letters"):
        p = base / f"{option_id}.pdf"
        if p.exists():
            return p
    return None


def real_ready(sample: str | None = None) -> bool:
    """True when the splits, candidates, letters and the background suspects are all available."""
    try:
        if _suspects_path(_sample(sample)) is None:
            return False
        splits.load_candidates()
        s = splits.load_splits()
        return any(_letter_pdf(r["option_id"]) for r in s["demo"])
    except Exception:
        return False


# ----------------------------------------------------------------- options

def short_condition(name: str) -> str:
    """Short disease label for the picker: prefers a parenthesised syndrome name, drops ClinVar underscores."""
    n = name.replace("_", " ").strip()
    if "(" in n and ")" in n:
        inner = n[n.index("(") + 1: n.rindex(")")]
        if any(k in inner.lower() for k in ("syndrome", "disease", "disorder", "epilepsy", "encephalopathy")):
            return inner.strip()
    return n


def region_word(row: dict, cand: dict | None = None) -> str:
    """Region wording for labels: 'splice site' for canonical splice, else the schema region word."""
    if row["region"] == "splice" and cand and set(cand.get("mc", [])) & {"splice_donor_variant", "splice_acceptor_variant"}:
        return "splice site"
    return REGION_WORD.get(row["region"], row["region"])


def _demo_rows() -> list[dict]:
    """Demo split rows that have a letter, anchor first, then genes round-robin so the top of the list is diverse."""
    cands = splits.load_candidates()["by_id"]
    rows = [r for r in splits.load_splits()["demo"] if _letter_pdf(r["option_id"])]
    by_gene: dict[str, list] = {}
    for r in rows:
        by_gene.setdefault(r["gene"], []).append(r)
    out = []
    while any(by_gene.values()):
        for g in sorted(by_gene):
            if by_gene[g]:
                out.append(by_gene[g].pop(0))
    anchor = [r for r in out if r.get("named")]
    rest = [r for r in out if not r.get("named")]
    for r in rest:
        r["_cand"] = cands.get(r["option_id"])
    return anchor + rest


def list_demo_options() -> list[DemoOption]:
    """Demo picker options labelled like 'SCN1A, splice site, Dravet syndrome' (only those whose letter is ready)."""
    cands = splits.load_candidates()["by_id"]
    out = []
    for r in _demo_rows():
        c = cands.get(r["option_id"])
        cond = short_condition(r["condition"])
        out.append(DemoOption(option_id=r["option_id"], gene=r["gene"], region=r["region"], condition=cond,
                              label=f"{r['gene']}, {region_word(r, c)}, {cond}"))
    return out


# ----------------------------------------------------------------- annotation of the planted variant

def annotate_planted(cand: dict) -> Variant:
    """Annotate the planted variant with the same annotator as the background suspects (slice A1), else a documented stand-in."""
    try:
        from genesleuth.data.annotate import annotate_variant  # slice A1: MANE Select geometry, same code as the background suspects
    except ImportError:
        return _standin_annotate(cand)
    return annotate_variant(cand["chrom"], cand["pos"], cand["ref"], cand["alt"], genotype="0/1")


def _standin_annotate(cand: dict) -> Variant:
    """Stand-in annotator (used only until slice A1's annotate_variant is on main): MANE exon geometry from panel.py."""
    from genesleuth.data import panel
    chrom, pos, gene = cand["chrom"], cand["pos"], cand["gene"]
    reg = next((r for r in panel.load_panel_regions() if r["gene"] == gene), None)
    feats = panel.load_features().get(gene, [])
    strand = reg["strand"] if reg else "+"
    exons = sorted((f["start"], f["end"]) for f in feats if f["feature"] == "exon")
    cds = [(f["start"], f["end"]) for f in feats if f["feature"] == "CDS"]
    region, conseq = "intergenic", "intergenic_variant"
    in_exon = next((e for e in exons if e[0] <= pos <= e[1]), None)
    gene_lo = min(e[0] for e in exons) if exons else pos
    gene_hi = max(e[1] for e in exons) if exons else pos
    if in_exon:
        if any(s <= pos <= e for s, e in cds):
            region, conseq = "coding", "coding_sequence_variant"
        else:
            cds_lo = min(s for s, _ in cds) if cds else gene_lo
            five = (pos < cds_lo) if strand == "+" else (pos > max(e for _, e in cds) if cds else False)
            region, conseq = ("utr5", "5_prime_UTR_variant") if five else ("utr3", "3_prime_UTR_variant")
    elif gene_lo < pos < gene_hi:
        d, side = min(((abs(pos - e[1]), "after") if pos > e[1] else (abs(e[0] - pos), "before") for e in exons if pos > e[1] or pos < e[0]),
                      key=lambda t: t[0])
        donor = (side == "after") == (strand == "+")
        if d <= 2:
            region, conseq = "splice", "splice_donor_variant" if donor else "splice_acceptor_variant"
        elif d <= 8:
            region, conseq = "splice", "splice_region_variant"
        else:
            region, conseq = "intron", "intron_variant"
    elif reg:
        up = (pos < gene_lo) if strand == "+" else (pos > gene_hi)
        if up:
            region, conseq = ("promoter", "upstream_gene_variant") if abs(pos - reg["tss"]) <= 2000 else ("intergenic", "upstream_gene_variant")
        else:
            region, conseq = "intergenic", "downstream_gene_variant"
    tss_dist = (pos - reg["tss"]) * (1 if strand == "+" else -1) if reg else None
    return Variant(variant_id=cand["variant_id"], chrom=chrom, pos=pos, ref=cand["ref"], alt=cand["alt"], gene=gene, region=region,
                   consequence=conseq, genotype="0/1", distance_to_tss=tss_dist)


# ----------------------------------------------------------------- case building

def _case_id(option_id: str, sample: str, seed: int) -> str:
    """Deterministic random-looking hex id (reveals nothing about the variant)."""
    return hashlib.sha256(f"gs|{option_id}|{sample}|{seed}".encode()).hexdigest()[:16]


def build_case(option_id: str | None = None, sample_id: str | None = None, split: str = "demo",
               seed: int = 0) -> tuple[Case, CaseTruth]:
    """Build (Case, CaseTruth): plant the ClinVar variant of `option_id` (random demo option if None) into the background."""
    t0 = time.time()
    sample = _sample(sample_id)
    cands = splits.load_candidates()["by_id"]
    bg = load_background(sample)
    bg_pos = {(v["chrom"], v["pos"]) for v in bg["suspects"]}
    if option_id is None:
        rng = random.Random(seed) if seed else random.SystemRandom()
        pool = [r for r in _demo_rows() if (cands[r["option_id"]]["chrom"], cands[r["option_id"]]["pos"]) not in bg_pos] or _demo_rows()
        option_id = rng.choice(pool)["option_id"]
    option_id = str(option_id)
    if option_id not in cands:
        raise KeyError(f"unknown option_id {option_id}")
    cand = cands[option_id]
    real_split = splits.split_of(option_id) or split
    pdf = _letter_pdf(option_id)
    if pdf is None:  # slow path: generate the letter now (not expected for listed options)
        letters.make_letter(cand, real_split)
        pdf = _letter_pdf(option_id)
    meta = letters.load_meta(option_id) or {}
    planted = annotate_planted(cand)
    suspects = [Variant(**v) for v in bg["suspects"]
                if (v["chrom"], v["pos"]) != (planted.chrom, planted.pos)]  # a background record at the same position is replaced
    replaced = len(bg["suspects"]) - len(suspects)
    suspects.append(planted)
    random.Random(f"{option_id}|{sample}|{seed}").shuffle(suspects)
    funnel = dict(bg["funnel"])
    for k in list(funnel):
        if k == "variants_in_panel_regions" or k.startswith("rare") or k == "suspects":
            funnel[k] = int(funnel[k]) + (1 if k != "suspects" else 0)
    funnel["suspects"] = len(suspects)
    cid = _case_id(option_id, sample, seed)
    case = Case(case_id=cid, sample_id=sample, referral_pdf=str(pdf), suspects=suspects, funnel=funnel)
    truth = CaseTruth(case_id=cid, hidden_variant_id=planted.variant_id, gene=cand["gene"], condition=cand["condition"].replace("_", " "),
                      clinvar_id=str(cand["variation_id"]), region=cand["region"],
                      true_phenotypes=[Phenotype(**p) for p in meta.get("phenotypes", [])],
                      split=real_split if real_split in ("dev", "test", "demo") else "demo")
    try:  # materialise the truth next to the case for the bench and debugging (never given to the agent)
        d = WORK / "cases"
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"truth_{cid}.json.part"
        tmp.write_text(truth.model_dump_json(indent=1))
        os.replace(tmp, d / f"truth_{cid}.json")
    except OSError:
        pass
    if replaced:
        print(f"[build_case] note: replaced {replaced} background suspect at the planted position")
    return case, truth
