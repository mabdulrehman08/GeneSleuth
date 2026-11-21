"""Tests for the case API (fakes and, when the data is present, the real builder).

Checks: the planted variant is among the suspects; no field of Case singles it out; determinism per seed; build time < 20 s;
holdout contents; letter PDF exists; split sanity (disjoint, DNM1 only in DEMO, named cases never in TEST).
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter

import pytest

from genesleuth import config
from genesleuth.data import api, fakes
from genesleuth.schemas import Case, CaseTruth


def _case_checks(case: Case, truth: CaseTruth) -> None:
    """Shared invariants for fake and real cases."""
    ids = [v.variant_id for v in case.suspects]
    assert truth.hidden_variant_id in ids, "planted variant must be among the suspects"
    assert len(set(ids)) == len(ids), "no duplicate suspects"
    planted = next(v for v in case.suspects if v.variant_id == truth.hidden_variant_id)
    others = [v for v in case.suspects if v is not planted]
    # same field set: a field is None for the planted variant only if it is None for a good share of the others
    for f in ("gene", "region", "consequence", "genotype", "distance_to_tss"):
        share_none = sum(getattr(v, f) is None for v in others) / len(others)
        if getattr(planted, f) is None:
            assert share_none > 0.01, f"{f} is None only for the planted variant"
        else:
            assert share_none < 0.99, f"{f} is set only for the planted variant"
    # same annotation source: consequence is set and consistent with the region field style of the others
    assert planted.consequence and planted.region in {v.region for v in others} | {"splice", "coding", "intron", "utr5", "utr3", "promoter", "intergenic"}
    # the genotype is a normal one
    assert planted.genotype in {v.genotype for v in others}
    # the case payload mentions the hidden variant id exactly once (inside suspects) and never the truth strings
    payload = case.model_dump_json()
    assert payload.count(truth.hidden_variant_id) == 1
    assert truth.condition not in payload
    assert str(truth.clinvar_id) not in case.case_id
    assert truth.hidden_variant_id not in case.referral_pdf
    # the planted variant is not at the start or end of the list (shuffled) on average: check suspects are not sorted by position
    assert [v.variant_id for v in case.suspects] != sorted(ids, key=lambda i: (i.split("-")[0], int(i.split("-")[1])))
    assert os.path.exists(case.referral_pdf)
    assert case.funnel["suspects"] == len(case.suspects)
    assert api.holdout_for(truth) == {truth.hidden_variant_id, truth.clinvar_id}


def test_fake_case_invariants(monkeypatch):
    """The fake case satisfies all invariants and is deterministic per seed."""
    monkeypatch.setattr(config, "FAKE_MODE", True)
    opts = api.list_demo_options()
    assert len(opts) >= 15 and all(o.label.startswith(o.gene) for o in opts)
    case, truth = api.build_case(None, seed=5)
    _case_checks(case, truth)
    case2, truth2 = api.build_case(None, seed=5)
    assert [v.variant_id for v in case.suspects] == [v.variant_id for v in case2.suspects]
    case3, _ = api.build_case(None, seed=6)
    assert [v.variant_id for v in case.suspects] != [v.variant_id for v in case3.suspects] or case.case_id != case3.case_id


def test_fake_build_is_fast(monkeypatch):
    """Fake build_case finishes in well under 20 s."""
    monkeypatch.setattr(config, "FAKE_MODE", True)
    t = time.time()
    api.build_case(None, seed=1)
    assert time.time() - t < 20


def test_candidate_filters():
    """Region mapping and condition cleaning in the candidate script behave as specified."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("cc", os.path.join(os.path.dirname(__file__), "..", "scripts", "data_clinvar_candidates.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.region_of(["nonsense"]) == "coding"
    assert m.region_of(["intron_variant", "splice_donor_variant"]) == "splice"
    assert m.region_of(["intron_variant"]) == "intron"
    assert m.region_of(["5_prime_UTR_variant"]) == "utr5"
    names, dbs = m.clean_conditions("not_provided|Dravet_syndrome", "MedGen:C1|MedGen:C2,OMIM:607208")
    assert names == ["Dravet syndrome"] and dbs == [["MedGen:C2", "OMIM:607208"]]


def test_letter_checker():
    """The leakage regex catches gene symbols, HGVS, chr notation, HPO ids and condition names."""
    from genesleuth.data import letters
    genes = {"SCN1A", "DNM1"}
    assert letters.check_letter("Dear colleague, the child has seizures.", "SCN1A", "Dravet syndrome", genes) == []
    assert any(v.startswith("gene") for v in letters.check_letter("Testing showed SCN1A changes", "SCN1A", "Dravet syndrome", genes))
    assert "hgvs" in letters.check_letter("variant c.1335+1605G>A found", "DNM1", "x y", genes)
    assert "chr" in letters.check_letter("at chr9 position", "DNM1", "x y", genes)
    assert "hpo_id" in letters.check_letter("Seizure (HP:0001250)", "DNM1", "x y", genes)
    assert any(v.startswith("condition") for v in letters.check_letter("consistent with Dravet-like illness", "SCN1A", "Severe myoclonic epilepsy of infancy (Dravet syndrome)", genes))


def test_phenotypes_synthesis():
    """Synthetic phenotypes are deterministic per seed, 5-8 sampled terms plus 1-2 decoys, and differ across seeds."""
    from genesleuth.data import phenotypes
    cand = {"variant_id": "chr2-1-A-G", "gene": "SCN1A", "omim_ids": ["607208"], "condition": "Dravet syndrome"}
    try:
        a, da = phenotypes.synthesize(cand, 0)
    except FileNotFoundError:
        pytest.skip("HPO tables not available")
    b, _ = phenotypes.synthesize(cand, 0)
    assert [p.hpo_id for p in a] == [p.hpo_id for p in b]
    assert 6 <= len(a) <= 10 and 1 <= len(da["decoys"]) <= 2
    assert [p.hpo_id for p in phenotypes.synthesize(cand, 1)[0]] != [p.hpo_id for p in a]


def test_splits_sane():
    """Splits are disjoint, sized as planned, and named cases are never in TEST."""
    from genesleuth.data import splits
    try:
        s = splits.load_splits()
    except FileNotFoundError:
        pytest.skip("candidates not available")
    ids = {k: {r["option_id"] for r in s[k]} for k in ("dev", "test", "demo")}
    assert not (ids["dev"] & ids["test"]) and not (ids["dev"] & ids["demo"]) and not (ids["test"] & ids["demo"])
    assert len(ids["dev"]) == 5 and 30 <= len(ids["test"]) <= 40
    assert "4855726" in ids["demo"] and "4855726" not in ids["test"]
    assert not any(r.get("named") for r in s["test"] + s["dev"])


@pytest.mark.skipif(config.FAKE_MODE, reason="real data only")
def test_real_case_if_available():
    """With real data present: invariants, determinism per seed and build time under 20 s."""
    from genesleuth.data import cases
    if not cases.real_ready():
        pytest.skip("real data not ready (needs background suspects and letters)")
    opts = api.list_demo_options()
    assert opts, "no demo options with letters"
    t = time.time()
    case, truth = api.build_case(opts[1].option_id, seed=3)
    dt = time.time() - t
    print(f"real build_case: {dt:.2f}s, {len(case.suspects)} suspects, funnel {case.funnel}")
    assert dt < 20
    _case_checks(case, truth)
    case2, _ = api.build_case(opts[1].option_id, seed=3)
    assert [v.variant_id for v in case.suspects] == [v.variant_id for v in case2.suspects]
    assert case.case_id == case2.case_id
    case3, _ = api.build_case(opts[1].option_id, seed=4)
    assert [v.variant_id for v in case.suspects] != [v.variant_id for v in case3.suspects]
    assert truth.true_phenotypes, "true phenotypes missing"
