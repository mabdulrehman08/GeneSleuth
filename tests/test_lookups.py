"""Tests for genesleuth/lookups: 3 known variants and 2 genes, real data and FAKE_MODE=1.

Run: PYTHONPATH=. python -m pytest tests/test_lookups.py -q          (real tables from assets/ or DATA_DIR/work)
     FAKE_MODE=1 PYTHONPATH=. python -m pytest tests/test_lookups.py -q   (fakes only, no data, no network)
Known variants (ClinVar P/LP, GRCh38): SCN1A splice donor chr2-166037775-C-A, KCNQ2 splice acceptor
chr20-63413582-C-T, TSC2 splice donor chr16-2048755-T-C. Known genes: SCN1A, KCNQ2.
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
    result = api.population_frequency("chr17-7675088-C-T")
    assert result.keys() == {"af_bin", "source"}
    assert result["source"] == "gnomAD v4.1"
    assert result["af_bin"] in {"<0.1%", "0.1-1%"}
    json.dumps(result)


def test_five_cases_have_uniform_evidence(monkeypatch, tmp_path):
    from genesleuth.data import api as cases
    from genesleuth.lookups._common import cache_get, cache_put

    if not cases._real_ready():
        pytest.skip("Real demo assets are required for the leakage regression")

    def reject_network(*args, **kwargs):
        pytest.fail("Case preparation or lookups attempted a network request")

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr("requests.post", reject_network)
    options = cases.list_demo_options()[:5]
    assert len(options) == 5
    for seed, option in enumerate(options):
        case, truth = cases.build_case(option.option_id, seed=seed)
        hidden_id = truth.hidden_variant_id
        background = [v for v in case.suspects if v.variant_id != hidden_id]

        cache_put("popfreq", hidden_id, {"found": False, "source": "legacy", "note": "not observed"})
        cache_put("region", hidden_id, {"source": "legacy", "region": "legacy"})
        hidden_freq = api.population_frequency(hidden_id)
        hidden_region = api.region_context(hidden_id)
        assert hidden_freq.keys() == {"af_bin", "source"}
        assert hidden_freq["source"] == "gnomAD v4.1"
        assert hidden_region["source"] == "MANE v1.5 + VEP"
        assert "error" not in hidden_region
        assert cache_get("popfreq-bins-v1", hidden_id) == hidden_freq["af_bin"]

        seen_bins = set()
        for variant in background:
            frequency = api.population_frequency(variant.variant_id)
            region = api.region_context(variant.variant_id)
            assert frequency.keys() == hidden_freq.keys()
            assert frequency["source"] == hidden_freq["source"]
            assert region.keys() == hidden_region.keys()
            assert region["source"] == hidden_region["source"]
            assert region["consequence"] == variant.consequence
            seen_bins.add(frequency["af_bin"])
        assert seen_bins == {"<0.1%", "0.1-1%"}
        assert hidden_freq["af_bin"] in seen_bins


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
