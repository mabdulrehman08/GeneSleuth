"""Tests for genesleuth/lookups: 3 known variants and 2 genes, real data and FAKE_MODE=1.

Run: PYTHONPATH=. python -m pytest tests/test_lookups.py -q          (real tables from assets/ or DATA_DIR/work)
     FAKE_MODE=1 PYTHONPATH=. python -m pytest tests/test_lookups.py -q   (fakes only, no data, no network)
Known variants (ClinVar P/LP, GRCh38): SCN1A splice donor chr2-166037775-C-A, KCNQ2 splice acceptor
chr20-63413582-C-T, TSC2 splice donor chr16-2048755-T-C. Known genes: SCN1A, KCNQ2.
The gnomAD test is skipped when the API is rate limited.
"""
import json

import pytest

from genesleuth import config
from genesleuth.lookups import api

FAKE = bool(config.FAKE_MODE)
VARIANTS = ["chr2-166037775-C-A", "chr20-63413582-C-T", "chr16-2048755-T-C"]
GENES = ["SCN1A", "KCNQ2"]


@pytest.mark.parametrize("vid", VARIANTS)
def test_region_context(vid):
    r = api.region_context(vid)
    assert "error" not in r
    json.dumps(r)
    assert r["gene"] in {"SCN1A", "KCNQ2", "TSC2"} or FAKE
    assert r["region"] in {"coding", "splice", "utr5", "utr3", "intron", "promoter", "intergenic", "other"}
    if not FAKE:
        assert r["region"] == "splice"
        assert r["consequence"] == "splice_donor_variant" or r["consequence"] == "splice_acceptor_variant"
        assert r["intron"] is not None


def test_region_context_bad_id_never_raises():
    assert "error" in api.region_context("not-a-variant")


def test_region_context_outside_panel():
    r = api.region_context("chr1-100000-A-G")
    assert "error" not in r and r["gene"] is None


def test_population_frequency_shape():
    r = api.population_frequency("chr17-7675088-C-T")  # TP53 R248Q-like site, very rare in gnomAD
    if r.get("source") == "unavailable":
        pytest.skip("gnomAD API rate limited")
    assert set(r) >= {"found", "source", "af", "ac", "an"}
    json.dumps(r)
    if not FAKE:
        assert r["found"] is True and r["af"] < 0.001


def test_clinvar_disabled_by_default():
    for v in VARIANTS:
        r = api.clinvar_lookup(v, {v})
        assert r == {"disabled": True, "note": "ClinVar lookup off to prevent leakage"}


def test_clinvar_holdout_second_guard():
    v = VARIANTS[0]
    open_r = api.clinvar_lookup(v, set(), enabled=True)
    assert open_r.get("found") is True
    if not FAKE:
        assert "Pathogenic" in open_r["significance"]
    # held-out variant id, and a different alt at the same position, are both hidden
    assert api.clinvar_lookup(v, {v}, enabled=True)["found"] is False
    same_pos = "chr2-166037775-C-G"
    assert api.clinvar_lookup(same_pos, {v}, enabled=True)["found"] is False


@pytest.mark.parametrize("gene", GENES)
def test_gene_phenotypes(gene):
    r = api.gene_phenotypes(gene)
    assert r["gene"] == gene and r["diseases"] and r["hpo_terms"]
    assert "HP:0001250" in {t["id"] for t in r["hpo_terms"]}
    json.dumps(r)


def test_phenotype_match_scores():
    seizure_terms = ["HP:0001250", "HP:0002373"]
    hit = api.phenotype_match("SCN1A", seizure_terms)
    assert hit["score"] == 1.0 and len(hit["matched"]) == 2
    assert all({"patient_term", "gene_term"} <= set(m) for m in hit["matched"])
    assert api.phenotype_match("KCNQ2", [])["score"] == 0.0
    if not FAKE:
        # a pure-skeletal phenotype should not match an epilepsy gene better than seizures do
        assert api.phenotype_match("KCNQ2", ["HP:0001250"])["score"] >= api.phenotype_match("KCNQ2", ["HP:0000925"])["score"]
        assert api.phenotype_match("NOTAGENE", ["HP:0001250"])["score"] == 0.0


def test_hpo_search():
    res = api.hpo_search("seizures", 5)
    assert res and res[0]["id"] == "HP:0001250"
    assert {"id", "label", "matched_on"} <= set(res[0])
    res = api.hpo_search("low muscle tone", 5)
    assert any(r["id"] in ("HP:0001252", "HP:0001290") for r in res)
    assert api.hpo_search("", 3) == [] or FAKE
