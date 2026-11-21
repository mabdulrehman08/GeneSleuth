"""HPO-based lookups: gene_phenotypes, phenotype_match, hpo_search.

Feature: gene -> disease/phenotype information and patient-phenotype matching from the HPO work tables written by
scripts/data_hpo.py (hpo_terms.json, hpo_gene.tsv, hpo_gene_disease.tsv, hpo_alt_ids.json; read from ROOT/assets first, then DATA_DIR/work).
Use cases: the agent asks "does this gene explain the patient's phenotypes?" (phenotype_match), looks up a gene's
known diseases (gene_phenotypes) and maps free-text findings from the referral letter to HPO ids (hpo_search).

Scoring (phenotype_match): each patient HPO term is expanded to itself plus its ancestors up to 2 levels; the gene's
HPO terms are expanded the same way. score = fraction of patient terms whose expanded set intersects the gene's
expanded set. For every matched patient term the closest pair (smallest total distance up the tree) is returned.

Data tables are loaded once per process (a few MB) and small results are cached on disk under
DATA_DIR/cache/lookups/{genepheno,hposearch}/.
"""
from __future__ import annotations

import csv
import functools
import json
import re
from collections import defaultdict
from typing import Any

from ._common import cache_get, cache_put, find_table, open_text

MAX_LEVELS = 2
_STOP = {"of", "the", "a", "an", "and", "or", "in", "to", "with", "for", "on", "at", "by", "is", "are", "from", "as"}


@functools.lru_cache(maxsize=1)
def _terms() -> dict[str, dict]:
    """hpo_terms.json: {hpo_id: {label, synonyms, parents}}."""
    p = find_table("hpo_terms.json")
    if p is None:
        raise FileNotFoundError("hpo_terms.json missing in assets/ and DATA_DIR/work: run scripts/data_hpo.py")
    with open_text(p) as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=1)
def _alts() -> dict[str, str]:
    p = find_table("hpo_alt_ids.json")
    try:
        with open_text(p) as fh:
            return json.load(fh)
    except (OSError, ValueError, TypeError):
        return {}


@functools.lru_cache(maxsize=1)
def _gene_terms() -> dict[str, list[str]]:
    """gene symbol (upper case) -> sorted list of HPO ids."""
    p = find_table("hpo_gene.tsv")
    if p is None:
        raise FileNotFoundError("hpo_gene.tsv missing in assets/ and DATA_DIR/work: run scripts/data_hpo.py")
    d: dict[str, set[str]] = defaultdict(set)
    with open_text(p) as fh:
        rd = csv.reader(fh, delimiter="\t")
        next(rd, None)
        for row in rd:
            if len(row) >= 2:
                d[row[0].upper()].add(row[1])
    return {g: sorted(v) for g, v in d.items()}


@functools.lru_cache(maxsize=1)
def _gene_diseases() -> dict[str, list[dict]]:
    """gene symbol (upper) -> [{id, name}]."""
    p = find_table("hpo_gene_disease.tsv")
    d: dict[str, list[dict]] = defaultdict(list)
    if p is not None:
        with open_text(p) as fh:
            rd = csv.reader(fh, delimiter="\t")
            next(rd, None)
            for row in rd:
                if len(row) >= 3:
                    d[row[0].upper()].append({"id": row[1], "name": row[2]})
    return dict(d)


def _canon(hid: str) -> str:
    """Normalise an HPO id (strip, upper case, map alternative ids to the primary id)."""
    h = str(hid).strip().upper().replace("HP_", "HP:")
    if re.fullmatch(r"\d{7}", h):
        h = "HP:" + h
    return _alts().get(h, h)


def _expand(term: str) -> dict[str, int]:
    """{term: distance} for the term itself (0) and ancestors up to MAX_LEVELS levels above it (shortest distance)."""
    terms = _terms()
    out = {term: 0}
    frontier = [term]
    for lvl in range(1, MAX_LEVELS + 1):
        nxt = []
        for t in frontier:
            for p in terms.get(t, {}).get("parents", []):
                if p not in out:
                    out[p] = lvl
                    nxt.append(p)
        frontier = nxt
    return out


@functools.lru_cache(maxsize=4096)
def _gene_expanded(gene: str) -> dict[str, tuple[int, str]]:
    """expanded gene term -> (distance, originating gene term); closest origin wins."""
    best: dict[str, tuple[int, str]] = {}
    for gt in _gene_terms().get(gene, []):
        for t, dist in _expand(gt).items():
            if t not in best or dist < best[t][0]:
                best[t] = (dist, gt)
    return best


def gene_phenotypes(gene: str) -> dict:
    """{gene, diseases: [{id, name}], hpo_terms: [{id, label}]} for a gene symbol (case-insensitive)."""
    g = str(gene).strip().upper()
    hit = cache_get("genepheno", g)
    if hit is not None:
        return hit
    terms = _terms()
    ids = _gene_terms().get(g, [])
    out: dict[str, Any] = {"gene": g,
                           "diseases": _gene_diseases().get(g, []),
                           "hpo_terms": [{"id": i, "label": terms.get(i, {}).get("label", "")} for i in ids]}
    if not ids and not out["diseases"]:
        out["note"] = "gene has no HPO annotations"
    cache_put("genepheno", g, out)
    return out


def phenotype_match(gene: str, hpo_ids: list[str]) -> dict:
    """Score how well a gene's known phenotypes cover the patient's HPO terms.

    Returns {gene, score (0-1), matched: [{patient_term, patient_label, gene_term, gene_label, distance}],
    unmatched: [patient ids], n_patient_terms, n_gene_terms}.
    """
    g = str(gene).strip().upper()
    terms = _terms()
    gexp = _gene_expanded(g)
    pts = []
    for h in hpo_ids or []:
        c = _canon(h)
        if c not in pts:
            pts.append(c)
    matched, unmatched = [], []
    for p in pts:
        best = None
        for t, d_p in _expand(p).items():
            if t in gexp:
                d_g, origin = gexp[t]
                tot = d_p + d_g
                if best is None or tot < best[0]:
                    best = (tot, origin)
        if best is None:
            unmatched.append(p)
        else:
            matched.append({"patient_term": p, "patient_label": terms.get(p, {}).get("label", ""),
                            "gene_term": best[1], "gene_label": terms.get(best[1], {}).get("label", ""),
                            "distance": best[0]})
    score = round(len(matched) / len(pts), 4) if pts else 0.0
    return {"gene": g, "score": score, "matched": matched, "unmatched": unmatched,
            "n_patient_terms": len(pts), "n_gene_terms": len(_gene_terms().get(g, []))}


# ---------------------------------------------------------------------------------------------- hpo_search
def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _tok(s: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _STOP]


@functools.lru_cache(maxsize=1)
def _search_index() -> dict:
    """Exact label/synonym maps plus a token -> [(term, text_index)] inverted index."""
    terms = _terms()
    lab: dict[str, list[str]] = defaultdict(list)
    syn: dict[str, list[str]] = defaultdict(list)
    texts: list[tuple[str, str, frozenset]] = []  # (term id, kind, token set)
    inv: dict[str, list[int]] = defaultdict(list)
    for hid, t in terms.items():
        lab[t["label"].lower()].append(hid)
        entries = [("label", t["label"])] + [("synonym", s) for s in t.get("synonyms", [])]
        for kind, text in entries:
            if kind == "synonym":
                syn[text.lower()].append(hid)
            ts = frozenset(_tok(text))
            if not ts:
                continue
            idx = len(texts)
            texts.append((hid, kind, ts))
            for w in ts:
                inv[w].append(idx)
    return {"lab": lab, "syn": syn, "texts": texts, "inv": inv}


def hpo_search(text: str, k: int = 5) -> list[dict]:
    """Case-insensitive exact label, exact synonym, then token-overlap ranking. Returns [{id, label, matched_on}]."""
    q = str(text).strip()
    if not q:
        return []
    key = f"{q.lower()}|{k}"
    hit = cache_get("hposearch", key)
    if hit is not None:
        return hit
    terms = _terms()
    idx = _search_index()
    out: list[dict] = []
    seen: set[str] = set()

    def add(hid: str, how: str, score: float | None = None) -> None:
        if hid in seen or hid not in terms:
            return
        seen.add(hid)
        r = {"id": hid, "label": terms[hid]["label"], "matched_on": how}
        if score is not None:
            r["score"] = round(score, 3)
        out.append(r)

    ql = q.lower()
    for hid in idx["lab"].get(ql, []):
        add(hid, "label")
    for hid in idx["syn"].get(ql, []):
        add(hid, "synonym")
    if len(out) < k:
        qt = set(_tok(q))
        if qt:
            cand: dict[int, int] = defaultdict(int)
            for w in qt:
                for i in idx["inv"].get(w, []):
                    cand[i] += 1
            scored = []
            for i, ov in cand.items():
                hid, kind, ts = idx["texts"][i]
                prec, rec = ov / len(ts), ov / len(qt)
                s = 0.6 * rec + 0.4 * prec + (0.02 if kind == "label" else 0.0)
                if ql in terms[hid]["label"].lower() or any(ql in x.lower() for x in terms[hid].get("synonyms", [])):
                    s += 0.3  # substring bonus
                scored.append((s, hid, kind))
            scored.sort(key=lambda x: (-x[0], len(terms[x[1]]["label"]), x[1]))
            for s, hid, kind in scored:
                if len(out) >= k:
                    break
                add(hid, "synonym_overlap" if kind == "synonym" else "token_overlap", s)
    out = out[:k]
    cache_put("hposearch", key, out)
    return out
