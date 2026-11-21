"""Fixed-recipe baseline (no LLM) for the GeneSleuth benchmark.

Feature: a transparent, hand-weighted ranker over the same suspects the agent sees. It answers "how far does
plain code get with the same evidence?" and is one of the benchmark arms (mode "fixed_recipe").

    score = 0.4 * phenotype_match(gene, patient phenotypes)
          + 0.3 * normalised |Atlas AVI / AlphaGenome effect|   (abs / max over this case's suspects)
          + 0.2 * consequence severity   (coding LoF 1.0, splice 0.8, missense 0.6, utr/promoter 0.4, intron 0.2, synonymous 0.1)
          + 0.1 * gene has any P/LP epilepsy ClinVar record     (gene level only, holdout records excluded)

Leakage rules honoured here:
  * never per-variant ClinVar; the gene-level feature drops every record that is held out (variant id, ClinVar
    variation id, or the same chrom+pos as the hidden variant), so the planted variant cannot lift its own gene;
  * only `case` and `holdout` go in, never the CaseTruth;
  * patient phenotypes come from the reader (genesleuth.agent.reader.read_referral) when it exists, else the caller
    passes the truth phenotypes and the result is flagged ("standins" in the info dict -> meta.standins).

The Atlas score comes from genesleuth.alphagenome_client.atlas_scores when it exists. Otherwise a clearly named
deterministic stand-in is used and flagged; benchmark runs refuse stand-ins unless --allow-standin is given.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from genesleuth import config
from genesleuth.schemas import Case, InvestigationResult, Phenotype, RankedSuspect, ToolCall, Variant

W_PHENO, W_EFFECT, W_SEVERITY, W_GENE_PLP = 0.4, 0.3, 0.2, 0.1
TOP_N = 10
LOF_TERMS = ("frameshift", "stop_gained", "start_lost", "stop_lost", "transcript_ablation")
PLP_RE = re.compile(r"^(pathogenic|likely_pathogenic|likely pathogenic)", re.I)
EPILEPSY_RE = re.compile(r"epilep|seiz|encephalopath|dravet|spasm|convuls|lennox|rett syndrome|tuberous|neuronal ceroid|febrile", re.I)


# ----------------------------------------------------------------------------
# Feature pieces
# ----------------------------------------------------------------------------
def severity(v: Variant) -> float:
    """Consequence severity in [0, 1] per the recipe. Splice terms are checked after loss-of-function terms."""
    c = (v.consequence or "").lower()
    if any(t in c for t in LOF_TERMS):
        return 1.0
    if "splice" in c or v.region == "splice":
        return 0.8
    if "missense" in c or "inframe" in c or "protein_altering" in c:
        return 0.6
    if "synonymous" in c:
        return 0.1
    if v.region in ("utr5", "utr3", "promoter") or "utr" in c or "upstream" in c:
        return 0.4
    if v.region == "intron" or "intron" in c:
        return 0.2
    if v.region == "coding":
        return 0.6
    return 0.1


def _find(name: str) -> Optional[Path]:
    """assets/ first, then DATA_DIR/work (same read order as the rest of the project)."""
    for p in (config.ROOT / "assets" / name, config.DATA_DIR / "work" / name):
        if p.exists():
            return p
    return None


@lru_cache(maxsize=1)
def _plp_epilepsy_records() -> Optional[dict[str, list[tuple[str, str, str, int]]]]:
    """gene -> [(variant_id, variation_id, chrom, pos)] for P/LP records with an epilepsy-like condition.

    Reads clinvar_panel.tsv.gz (columns variant_id variation_id allele_id chrom pos ref alt clnsig review_status stars
    condition_names condition_dbs gene mc). Returns None when the table is not available (caller flags a stand-in).
    """
    p = _find("clinvar_panel.tsv.gz")
    if p is None:
        return None
    out: dict[str, list[tuple[str, str, str, int]]] = {}
    with gzip.open(p, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            sig = row.get("clnsig") or ""
            if not PLP_RE.match(sig) or "conflicting" in sig.lower():
                continue
            if not EPILEPSY_RE.search(row.get("condition_names") or ""):
                continue
            try:
                pos = int(row.get("pos") or 0)
            except ValueError:
                continue
            rec = (row.get("variant_id") or "", str(row.get("variation_id") or ""), row.get("chrom") or "", pos)
            for g in (row.get("gene") or "").upper().split("|"):  # multi-gene entries look like ARX|LOC109610631
                if g:
                    out.setdefault(g, []).append(rec)
    return out


def _held_out_positions(holdout: set[str]) -> set[tuple[str, int]]:
    """(chrom, pos) of every held-out variant id (ids look like chr2-165991234-A-G)."""
    pos = set()
    for h in holdout:
        m = re.match(r"^(chr\w+)-(\d+)-[ACGTN]+-[ACGTN]+$", h)
        if m:
            pos.add((m.group(1), int(m.group(2))))
    return pos


def genes_with_plp(holdout: set[str]) -> Optional[set[str]]:
    """Genes with at least one P/LP epilepsy record AFTER removing every held-out record. None if no table."""
    recs = _plp_epilepsy_records()
    if recs is None:
        return None
    hpos = _held_out_positions(holdout)
    genes = set()
    for g, rows in recs.items():
        for vid, varid, chrom, pos in rows:
            if vid in holdout or varid in holdout or (chrom, pos) in hpos:
                continue
            genes.add(g)
            break
    return genes


# ----------------------------------------------------------------------------
# Atlas (or stand-in)
# ----------------------------------------------------------------------------
def standin_effect(v: Variant) -> float:
    """STAND-IN, NOT AN ATLAS SCORE: deterministic pseudo-effect (hash noise x consequence severity). Flagged in results."""
    h = int(hashlib.sha256(v.variant_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h * (0.3 + severity(v))


def _parse_atlas(raw, variants: list[Variant]) -> dict[str, float]:
    """Accept {variant_id: number | {avi|score|max_abs_effect: number}} or a list of such dicts with a variant_id."""
    def val(x):
        if isinstance(x, (int, float)):
            return abs(float(x))
        if isinstance(x, dict):
            for k in ("avi", "AVI", "score", "max_abs_effect", "effect", "atlas_score"):
                if isinstance(x.get(k), (int, float)):
                    return abs(float(x[k]))
        return None
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for k, x in raw.items():
            v = val(x)
            if v is not None:
                out[k] = v
    elif isinstance(raw, list):
        for x in raw:
            if isinstance(x, dict) and isinstance(x.get("variant_id"), str):
                v = val(x)
                if v is not None:
                    out[x["variant_id"]] = v
    return out


def atlas_effects(variants: list[Variant]) -> tuple[dict[str, float], list[str]]:
    """({variant_id: |effect|}, standins). Real scores from alphagenome_client.atlas_scores when available."""
    try:
        from genesleuth import alphagenome_client as agc
        fn = agc.atlas_scores
    except Exception:  # noqa: BLE001 - module/function not there yet
        return {v.variant_id: standin_effect(v) for v in variants}, ["atlas_scores(stand-in hash score)"]
    try:
        got = _parse_atlas(fn(variants), variants)
    except Exception as e:  # noqa: BLE001
        return {v.variant_id: standin_effect(v) for v in variants}, [f"atlas_scores(stand-in; client raised {type(e).__name__})"]
    if not got:
        return {v.variant_id: standin_effect(v) for v in variants}, ["atlas_scores(stand-in; client returned nothing parseable)"]
    # variants Atlas could not score get 0, not a made-up number
    return {v.variant_id: got.get(v.variant_id, 0.0) for v in variants}, []


# ----------------------------------------------------------------------------
# The recipe
# ----------------------------------------------------------------------------
def fixed_recipe(case: Case, holdout: set[str], phenotypes: list[Phenotype], *,
                 atlas_fn: Optional[Callable[[list[Variant]], tuple[dict[str, float], list[str]]]] = None,
                 phenotype_match_fn: Optional[Callable[[str, list[str]], dict]] = None,
                 plp_genes: Optional[set[str]] | str = "auto") -> tuple[InvestigationResult, dict]:
    """Rank all suspects with the fixed recipe. Returns (InvestigationResult, info) with info['standins'] listing flags."""
    t0 = time.time()
    standins: list[str] = []
    if phenotype_match_fn is None:
        from genesleuth.lookups.api import phenotype_match as phenotype_match_fn  # type: ignore[no-redef]
    hpo_ids = [p.hpo_id for p in phenotypes]

    genes = sorted({(v.gene or "") for v in case.suspects if v.gene})
    pheno_by_gene: dict[str, float] = {}
    for g in genes:
        r = phenotype_match_fn(g, hpo_ids) or {}
        pheno_by_gene[g] = float(r.get("score") or 0.0) if "error" not in r else 0.0

    eff, flags = (atlas_fn or atlas_effects)(case.suspects)
    standins += flags
    top = max(eff.values(), default=0.0) or 1.0

    if plp_genes == "auto":
        plp_genes = genes_with_plp(holdout)
        if plp_genes is None:
            standins.append("clinvar_gene_level(no clinvar_panel table; feature set to 0)")
            plp_genes = set()
    plp: set[str] = {g.upper() for g in (plp_genes or set())}

    scored = []
    for v in case.suspects:
        c_ph = pheno_by_gene.get(v.gene or "", 0.0)
        c_ef = min(1.0, eff.get(v.variant_id, 0.0) / top)
        c_sv = severity(v)
        c_pl = 1.0 if (v.gene or "").upper() in plp else 0.0
        s = W_PHENO * c_ph + W_EFFECT * c_ef + W_SEVERITY * c_sv + W_GENE_PLP * c_pl
        scored.append((s, v, (c_ph, c_ef, c_sv, c_pl)))
    scored.sort(key=lambda t: (-t[0], t[1].variant_id))

    ranked = [RankedSuspect(rank=i, variant=v, score=round(s, 4), tissue=config.BRAIN_TISSUE if not standins else None,
                            summary=(f"fixed recipe: phenotype {c[0]:.2f} x{W_PHENO}, effect {c[1]:.2f} x{W_EFFECT}, "
                                     f"severity {c[2]:.2f} x{W_SEVERITY}, gene P/LP {c[3]:.0f} x{W_GENE_PLP}"))
              for i, (s, v, c) in enumerate(scored[:TOP_N], start=1)]
    calls = [ToolCall(call_id="fr0", tool="fixed_recipe.phenotype_match", args={"n_genes": len(genes), "n_terms": len(hpo_ids)},
                      result={"genes_scored": len(genes)}, result_summary=f"phenotype_match for {len(genes)} genes"),
             ToolCall(call_id="fr1", tool="fixed_recipe.atlas_scores", args={"n_variants": len(case.suspects)},
                      result={"standin": bool(flags)}, result_summary="atlas effect for all suspects" + (" (STAND-IN)" if flags else ""))]
    res = InvestigationResult(case_id=case.case_id, mode="fixed_recipe", status="ok", ranked=ranked, phenotypes=phenotypes,
                              tool_calls=calls, n_alphagenome_calls=0, n_tool_calls=len(calls),
                              timings={"total": round(time.time() - t0, 3)})
    return res, {"standins": standins, "phenotype_source": None}


def get_phenotypes(case: Case, truth_phenotypes: list[Phenotype], reader: Optional[Callable] = None) -> tuple[list[Phenotype], list[str]]:
    """Phenotypes for the recipe: the reader's output when available, else the truth phenotypes (flagged)."""
    if reader is None:
        try:
            from genesleuth.agent.reader import read_referral as reader  # type: ignore[no-redef]
        except Exception:  # noqa: BLE001
            return list(truth_phenotypes), ["phenotypes(truth terms; reader not available)"]
    try:
        got = reader(case.referral_pdf)
        if got:
            return list(got), []
    except Exception as e:  # noqa: BLE001
        return list(truth_phenotypes), [f"phenotypes(truth terms; reader raised {type(e).__name__})"]
    return list(truth_phenotypes), ["phenotypes(truth terms; reader returned nothing)"]
