"""Deterministic DEV / TEST / DEMO splits over the ClinVar candidate pool (seed 42).

Feature: turns clinvar_candidates.json (written by scripts/data_clinvar_candidates.py) into three disjoint option lists.
  - DEV: 5 non-coding cases (the only cases the team looks at while tuning).
  - TEST: 30 non-coding cases stratified by region type, plus 6 coding controls so the coding vs non-coding contrast is
    measurable (36 in all). Named cases are never in TEST.
  - DEMO: the deep non-coding pool minus DEV and TEST (the judge's picker), plus the DNM1 anchor case as a named option.
An option_id is the ClinVar variation id. Only candidates with a usable HPO disease annotation (OMIM or exact-name match)
are eligible, because the letter needs real phenotypes. Per-gene caps keep one gene from dominating a split.
The result is cached in DATA_DIR/work/splits.json (committed copy: assets/splits.json).

Usage: python -m genesleuth.data.splits   (prints the real split sizes)
"""
from __future__ import annotations

import gzip
import json
import os
import random
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from genesleuth import config

ASSETS = config.ROOT / "assets"
WORK = config.DATA_DIR / "work"
SEED = 42
# Named anchor case: ClinVar has this variant as VUS, so it is not in the P/LP pool; it is added by hand as a demo option.
DNM1_ANCHOR = {"variation_id": "4855726", "variant_id": "chr9-128225994-G-A", "chrom": "chr9", "pos": 128225994, "ref": "G", "alt": "A",
               "gene": "DNM1", "region": "intron", "condition": "Developmental and epileptic encephalopathy, 31", "named": "DNM1_anchor",
               "omim_ids": ["616346"], "mc": ["intron_variant"], "clnsig": "Uncertain_significance", "stars": 2, "noncoding": True,
               "deep_noncoding": True, "conditions": ["Developmental and epileptic encephalopathy, 31"], "condition_dbs": [["OMIM:616346"]],
               "allele_id": ""}


def find(name: str) -> Path | None:
    """Locate a data file: assets/ first, then DATA_DIR/work. Returns None if it is in neither."""
    for base in (ASSETS, WORK):
        p = base / name
        if p.exists():
            return p
    return None


def _read_json(p: Path):
    """Read .json or .json.gz."""
    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_candidates() -> dict:
    """Return {'report': ..., 'by_id': {variation_id: candidate}}; assets copy holds the non-coding pool plus coding controls."""
    for n in ("clinvar_candidates.json.gz", "clinvar_candidates.json"):
        p = find(n)
        if p:
            d = _read_json(p)
            by_id = {c["variation_id"]: c for c in d["candidates"]}
            by_id.setdefault(DNM1_ANCHOR["variation_id"], dict(DNM1_ANCHOR))
            return {"report": d.get("report", {}), "by_id": by_id}
    raise FileNotFoundError("clinvar_candidates.json(.gz) not found in assets/ or DATA_DIR/work; run scripts/data_clinvar_candidates.py")


def eligible(c: dict) -> bool:
    """A candidate is usable when its disease maps to an HPO annotation by OMIM id or exact name."""
    from genesleuth.data import phenotypes
    return phenotypes.pick_disease(c)[1] in ("omim", "name")


def _canon(c: dict) -> bool:
    """True for canonical splice donor/acceptor variants."""
    return bool(set(c["mc"]) & {"splice_donor_variant", "splice_acceptor_variant"})


def _stratum(c: dict) -> str:
    """Region stratum used for TEST stratification."""
    if c["region"] == "intron":
        return "intron"
    if c["region"] == "splice":
        return "splice_canonical" if _canon(c) else "splice_region"
    if c["region"] in ("utr5", "utr3", "promoter"):
        return "utr_promoter"
    return c["region"]


def _take(rng: random.Random, pool: list[dict], n: int, gene_cap: int, used_genes: Counter) -> list[dict]:
    """Randomly take up to n candidates with at most gene_cap per gene (counting used_genes)."""
    pool = pool[:]
    rng.shuffle(pool)
    out = []
    for c in pool:
        if len(out) >= n:
            break
        if used_genes[c["gene"]] >= gene_cap:
            continue
        used_genes[c["gene"]] += 1
        out.append(c)
    return out


def make_splits(seed: int = SEED) -> dict:
    """Compute the splits from the candidate pool (deterministic for a given pool and seed)."""
    cands = [c for c in load_candidates()["by_id"].values() if not c.get("named")]
    cands = sorted((c for c in cands if eligible(c)), key=lambda c: int(c["variation_id"]))
    nc = [c for c in cands if c["noncoding"]]
    coding = [c for c in cands if not c["noncoding"] and c["region"] == "coding"]
    rng = random.Random(seed)
    taken: set = set()

    def avail(pool):
        return [c for c in pool if c["variation_id"] not in taken]

    # DEV: 5 non-coding, one per gene, mixed strata.
    dev: list[dict] = []
    used: Counter = Counter()
    for stratum, n in (("intron", 2), ("splice_canonical", 2), ("splice_region", 1)):
        got = _take(rng, avail([c for c in nc if _stratum(c) == stratum]), n, 1, used)
        dev += got
        taken |= {c["variation_id"] for c in got}
    if len(dev) < 5:
        got = _take(rng, avail(nc), 5 - len(dev), 1, used)
        dev += got
        taken |= {c["variation_id"] for c in got}
    # TEST: 30 non-coding stratified + 6 coding controls, gene cap 3 (coding cap 1).
    quotas = {"intron": 11, "splice_canonical": 12, "splice_region": 4, "utr_promoter": 3}
    test: list[dict] = []
    used = Counter()
    for stratum, n in quotas.items():
        got = _take(rng, avail([c for c in nc if _stratum(c) == stratum]), n, 3, used)
        test += got
        taken |= {c["variation_id"] for c in got}
    if len(test) < 30:  # top up from any non-coding stratum
        got = _take(rng, avail(nc), 30 - len(test), 3, used)
        test += got
        taken |= {c["variation_id"] for c in got}
    got = _take(rng, avail(coding), 6, 1, Counter())
    test += got
    taken |= {c["variation_id"] for c in got}
    # DEMO: deep non-coding pool minus DEV/TEST, DNM1 anchor included.
    demo = [c for c in cands if c["deep_noncoding"] and c["variation_id"] not in taken]
    demo.append(dict(DNM1_ANCHOR))

    def row(c, split):
        return {"option_id": c["variation_id"], "split": split, "gene": c["gene"], "region": c["region"], "stratum": _stratum(c) if c.get("mc") else c["region"],
                "condition": c["condition"], "variant_id": c["variant_id"], "named": c.get("named")}

    return {"seed": seed, "dev": [row(c, "dev") for c in dev], "test": [row(c, "test") for c in test],
            "demo": [row(c, "demo") for c in sorted(demo, key=lambda c: (c["gene"], int(c["variation_id"])))],
            "counts": {"eligible_total": len(cands), "eligible_noncoding": len(nc), "dev": len(dev), "test": len(test),
                       "test_noncoding": len(test) - len(got), "test_coding": len(got), "demo": len(demo)},
            "test_by_stratum": dict(Counter(_stratum(c) for c in test)), "dev_by_stratum": dict(Counter(_stratum(c) for c in dev))}


@lru_cache(maxsize=1)
def load_splits() -> dict:
    """Load splits.json from assets/ or DATA_DIR/work; compute and cache it in DATA_DIR/work if absent."""
    p = find("splits.json")
    if p:
        return json.loads(p.read_text(encoding="utf-8"))
    s = make_splits()
    WORK.mkdir(parents=True, exist_ok=True)
    tmp = WORK / "splits.json.part"
    tmp.write_text(json.dumps(s, indent=1))
    os.replace(tmp, WORK / "splits.json")
    return s


def split_of(option_id: str) -> str | None:
    """Return 'dev', 'test' or 'demo' for an option id, or None if it is in no split."""
    s = load_splits()
    for k in ("dev", "test", "demo"):
        if any(r["option_id"] == option_id for r in s[k]):
            return k
    return None


if __name__ == "__main__":
    s = make_splits()
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "splits.json").write_text(json.dumps(s, indent=1))
    print(json.dumps({k: s[k] for k in ("counts", "test_by_stratum", "dev_by_stratum")}, indent=1))
    print("TEST genes:", Counter(r["gene"] for r in s["test"]).most_common())
    print("DEMO genes:", Counter(r["gene"] for r in s["demo"]).most_common(8))
