"""Synthetic patient phenotypes from public HPO disease annotations.

Feature: for a planted ClinVar variant, take its linked disease (OMIM id from ClinVar, else a name match, else the gene's
HPO-linked disease), sample 5-8 HPO terms weighted by annotation frequency, replace about 30% of them with a direct parent
term (clinically realistic imprecision), and add 1-2 unrelated decoy terms. The seed is fixed per case, so the result is
reproducible. These terms are the ground truth that the referral letter is written from (CaseTruth.true_phenotypes).

Inputs (written by slice A2): DATA_DIR/work/hpo_terms.json, hpo_disease.tsv, hpo_gene_disease.tsv.
Use cases: letters.py (letter text), build_case (CaseTruth), bench fixed recipe (truth phenotypes).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import random
from functools import lru_cache

from genesleuth import config
from genesleuth.schemas import Phenotype

WORK = config.DATA_DIR / "work"
ASSETS = config.ROOT / "assets"


def _open(name: str):
    """Open a text table: committed assets/<name>.gz first, then DATA_DIR/work/<name>."""
    gz = ASSETS / (name + ".gz")
    if gz.exists():
        return gzip.open(gz, "rt", encoding="utf-8")
    return open(WORK / name, encoding="utf-8")


FREQ_WEIGHT = {"HP:0040280": 1.0, "HP:0040281": 0.9, "HP:0040282": 0.55, "HP:0040283": 0.17, "HP:0040284": 0.03, "HP:0040285": 0.0}
UNKNOWN_WEIGHT = 0.3
ABNORMALITY_ROOT = "HP:0000118"
TOO_GENERAL = {"HP:0000118", "HP:0000001", "HP:0000924", "HP:0000707", "HP:0000152", "HP:0001626", "HP:0001939"}
# Common, clinically incidental findings for decoys (verified against hpo_terms.json at load; missing ones are skipped).
DECOY_CANDIDATES = ["HP:0000486", "HP:0000964", "HP:0002019", "HP:0000388", "HP:0002099", "HP:0002020", "HP:0000545", "HP:0001945",
                    "HP:0000939", "HP:0000518", "HP:0002650", "HP:0000508", "HP:0012393", "HP:0100518", "HP:0000028"]


def _rng(*parts) -> random.Random:
    """Deterministic RNG from arbitrary parts."""
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16))


@lru_cache(maxsize=1)
def _terms() -> dict:
    """HPO term table: {hpo_id: {label, synonyms, parents}}."""
    with _open("hpo_terms.json") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _diseases() -> tuple[dict, dict]:
    """(disease_id -> {name, terms:{hpo_id: weight}}, lower-case name -> [disease_id])."""
    dis: dict = {}
    with _open("hpo_disease.tsv") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            d = dis.setdefault(r["disease_id"], {"name": r["disease_name"], "terms": {}})
            fr = r["frequency"].strip()
            if fr.startswith("HP:"):
                w = FREQ_WEIGHT.get(fr, UNKNOWN_WEIGHT)
            elif "/" in fr:
                try:
                    a, b = fr.split("/")
                    w = int(a) / int(b) if int(b) else UNKNOWN_WEIGHT
                except ValueError:
                    w = UNKNOWN_WEIGHT
            elif fr.endswith("%"):
                try:
                    w = float(fr[:-1]) / 100
                except ValueError:
                    w = UNKNOWN_WEIGHT
            else:
                w = UNKNOWN_WEIGHT
            d["terms"][r["hpo_id"]] = max(w, d["terms"].get(r["hpo_id"], 0.0))
    names: dict = {}
    for k, v in dis.items():
        names.setdefault(v["name"].lower(), []).append(k)
    return dis, names


@lru_cache(maxsize=1)
def _gene_diseases() -> dict:
    """gene -> [disease_id]."""
    out: dict = {}
    with _open("hpo_gene_disease.tsv") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out.setdefault(r["gene"], []).append(r["disease_id"])
    return out


@lru_cache(maxsize=None)
def _ancestors(hpo_id: str) -> frozenset:
    """All ancestors of a term (excluding itself)."""
    t = _terms()
    seen: set = set()
    stack = list(t.get(hpo_id, {}).get("parents", []))
    while stack:
        p = stack.pop()
        if p not in seen:
            seen.add(p)
            stack.extend(t.get(p, {}).get("parents", []))
    return frozenset(seen)


def _is_abnormality(hpo_id: str) -> bool:
    """True for terms under 'Phenotypic abnormality' (drops inheritance, clinical-course modifiers and the like)."""
    return hpo_id in _terms() and ABNORMALITY_ROOT in _ancestors(hpo_id)


def pick_disease(candidate: dict) -> tuple[str | None, str]:
    """Choose the HPO disease id for a ClinVar candidate: OMIM id first, then name match, then the gene's linked disease."""
    dis, names = _diseases()
    for o in candidate.get("omim_ids", []):
        did = f"OMIM:{o}"
        if did in dis and any(_is_abnormality(h) for h in dis[did]["terms"]):
            return did, "omim"
    cond = candidate.get("condition", "").lower()
    for did in names.get(cond, []):
        return did, "name"
    gd = [d for d in _gene_diseases().get(candidate.get("gene", ""), []) if d in dis]
    gd.sort(key=lambda d: (not d.startswith("OMIM"), -len(dis[d]["terms"])))
    if gd:
        return gd[0], "gene"
    return None, "none"


def synthesize(candidate: dict, seed: int = 0) -> tuple[list[Phenotype], dict]:
    """Return (phenotypes in letter order, detail dict) for one ClinVar candidate; deterministic per (variant, seed)."""
    t = _terms()
    dis, _ = _diseases()
    rng = _rng("pheno", candidate["variant_id"], seed)
    did, how = pick_disease(candidate)
    pool = {h: w for h, w in (dis[did]["terms"].items() if did else []) if _is_abnormality(h) and h not in TOO_GENERAL and w > 0}
    if not pool:  # no usable annotation: fall back to a generic seizure picture so the case still exists
        pool = {"HP:0001250": 1.0, "HP:0001263": 0.6, "HP:0001252": 0.4, "HP:0002133": 0.3, "HP:0002376": 0.3}
        how += "+generic"
    k = min(rng.randint(5, 8), len(pool))
    # weighted sample without replacement (Efraimidis-Spirakis)
    keyed = sorted(pool.items(), key=lambda kv: rng.random() ** (1.0 / max(kv[1], 1e-6)), reverse=True)
    chosen = [h for h, _ in keyed[:k]]
    n_parent = round(0.3 * len(chosen))
    replaced: dict = {}
    for h in rng.sample(chosen, n_parent):
        ps = [p for p in t.get(h, {}).get("parents", []) if p not in TOO_GENERAL and p not in chosen and _is_abnormality(p)]
        if ps:
            p = rng.choice(ps)
            chosen[chosen.index(h)] = p
            replaced[h] = p
    own = set(pool) | {a for h in pool for a in _ancestors(h)}
    decoy_pool = [d for d in DECOY_CANDIDATES if d in t and d not in own]
    decoys = rng.sample(decoy_pool, min(rng.randint(1, 2), len(decoy_pool)))
    final = chosen + decoys
    rng.shuffle(final)
    phenos = [Phenotype(hpo_id=h, label=t[h]["label"]) for h in final if h in t]
    detail = {"disease_id": did, "disease_name": dis[did]["name"] if did else None, "disease_source": how,
              "sampled": [h for h in chosen if h not in replaced.values()] + list(replaced), "parent_replaced": replaced, "decoys": decoys}
    return phenos, detail
