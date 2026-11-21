"""Public lookup interface for GeneSleuth (the contract in section 7 of the Agent A prompt).

Feature: six cached, JSON-serialisable lookups used by the investigator agent and the bench:
  region_context(variant_id), population_frequency(variant_id), clinvar_lookup(variant_id, holdout),
  gene_phenotypes(gene), phenotype_match(gene, hpo_ids), hpo_search(text, k=5).

Rules every function follows:
  * never raises; on failure returns {"error": "..."} (hpo_search returns [{"error": "..."}] so callers can iterate);
  * results are cached on disk under DATA_DIR/cache/lookups/;
  * FAKE_MODE=1 (genesleuth.config.FAKE_MODE, read at call time) routes everything to lookups/fakes.py.

IMPORTANT, ClinVar and leakage: clinvar_lookup is DISABLED for every benchmark and demo case. By default it returns
  {"disabled": true, "note": "ClinVar lookup off to prevent leakage"}.
The holdout logic (hide held-out variant ids, ClinVar ids and ANY record at the same chrom+pos) is kept as a second
guard behind the flag `enabled=True`; only tests and exploratory use should ever pass it.
"""
from __future__ import annotations

from typing import Any

from genesleuth import config

from ._common import safe


def _fake() -> bool:
    return bool(config.FAKE_MODE)


@safe
def region_context(variant_id: str) -> dict:
    """Gene, region, consequence, distance_to_tss, exon/intron number and nearby genes for a variant id."""
    if _fake():
        from . import fakes
        return fakes.region_context(variant_id)
    from . import region
    return region.region_context(variant_id)


@safe
def population_frequency(variant_id: str) -> dict:
    """{found, source, af, ac, an}: gnomAD v4.1 (GraphQL), else the 1000G AF stored on the suspect, else not observed."""
    if _fake():
        from . import fakes
        return fakes.population_frequency(variant_id)
    from . import popfreq
    return popfreq.population_frequency(variant_id)


@safe
def clinvar_lookup(variant_id: str, holdout: set[str] | None = None, enabled: bool = False) -> dict:
    """ClinVar record for a variant. DISABLED by default (leakage guard); see module header."""
    if not enabled:
        return {"disabled": True, "note": "ClinVar lookup off to prevent leakage"}
    if _fake():
        from . import fakes
        return fakes.clinvar_lookup(variant_id, holdout, enabled=True)
    from . import clinvar
    return clinvar.clinvar_lookup(variant_id, holdout or set())


@safe
def gene_phenotypes(gene: str) -> dict:
    """{gene, diseases: [{id, name}], hpo_terms: [{id, label}]} from HPO genes_to_phenotype + phenotype.hpoa."""
    if _fake():
        from . import fakes
        return fakes.gene_phenotypes(gene)
    from . import phenotypes
    return phenotypes.gene_phenotypes(gene)


@safe
def phenotype_match(gene: str, hpo_ids: list[str]) -> dict:
    """{score: 0-1, matched: [{patient_term, gene_term}]} between patient HPO ids and a gene's HPO terms."""
    if _fake():
        from . import fakes
        return fakes.phenotype_match(gene, hpo_ids)
    from . import phenotypes
    return phenotypes.phenotype_match(gene, hpo_ids)


def hpo_search(text: str, k: int = 5) -> list[dict]:
    """[{id, label, matched_on}] by label/synonym match then token overlap. On failure: [{"error": ...}]."""
    try:
        if _fake():
            from . import fakes
            return fakes.hpo_search(text, k)
        from . import phenotypes
        return phenotypes.hpo_search(text, k)
    except Exception as e:  # noqa: BLE001
        return [{"error": f"{type(e).__name__}: {e}"}]
