import gzip

import pytest

from bench import baselines as B
from genesleuth.schemas import Case, Phenotype, Variant


def var(i, gene, region, cons, pos=None):
    pos = pos or 1000 + i
    return Variant(variant_id=f"chr1-{pos}-A-G", chrom="chr1", pos=pos, ref="A", alt="G", gene=gene, region=region,
                   consequence=cons, genotype="0/1")


def test_severity_table():
    assert B.severity(var(1, "G", "coding", "frameshift_variant")) == 1.0
    assert B.severity(var(2, "G", "splice", "splice_acceptor_variant")) == 0.8
    assert B.severity(var(3, "G", "coding", "missense_variant")) == 0.6
    assert B.severity(var(4, "G", "utr5", "5_prime_UTR_variant")) == 0.4
    assert B.severity(var(5, "G", "promoter", "upstream_gene_variant")) == 0.4
    assert B.severity(var(6, "G", "intron", "intron_variant")) == 0.2
    assert B.severity(var(7, "G", "coding", "synonymous_variant")) == 0.1


def test_recipe_weights_and_ranking():
    a = var(1, "SCN1A", "intron", "intron_variant")          # high pheno, strong effect
    b = var(2, "KCNQ2", "coding", "frameshift_variant")      # low pheno, no effect, LoF
    c = var(3, "OTHER", "coding", "synonymous_variant")
    case = Case(case_id="x", sample_id="s", referral_pdf="p.pdf", suspects=[c, b, a], funnel={})
    pm = lambda g, ids: {"score": {"SCN1A": 1.0, "KCNQ2": 0.2}.get(g, 0.0)}
    atlas = lambda vs: ({a.variant_id: 2.0, b.variant_id: 0.0, c.variant_id: 0.5}, [])
    res, info = B.fixed_recipe(case, set(), [Phenotype(hpo_id="HP:1", label="x")], atlas_fn=atlas, phenotype_match_fn=pm,
                               plp_genes={"SCN1A"})
    assert res.mode == "fixed_recipe" and res.status == "ok" and info["standins"] == []
    assert [r.variant.variant_id for r in res.ranked] == [a.variant_id, b.variant_id, c.variant_id]
    # a: 0.4*1 + 0.3*1 + 0.2*0.2 + 0.1*1
    assert res.ranked[0].score == pytest.approx(0.4 + 0.3 + 0.04 + 0.1)
    # b: 0.4*0.2 + 0 + 0.2*1 + 0
    assert res.ranked[1].score == pytest.approx(0.08 + 0.2)
    assert res.n_alphagenome_calls == 0


def test_atlas_with_no_scores_is_reported_not_faked(monkeypatch):
    from genesleuth import alphagenome_client as agc
    vs = [var(1, "SCN1A", "intron", "intron_variant"), var(2, "KCNQ2", "coding", "missense_variant")]
    monkeypatch.setattr(agc, "atlas_scores", lambda variants: {v.variant_id: {"avi": None, "error": "No variant-matched AVI result returned"} for v in variants})
    eff, flags = B.atlas_effects(vs)
    assert set(eff.values()) == {0.0} and "atlas_no_scores" in flags[0] and "No variant-matched" in flags[0]
    monkeypatch.setattr(agc, "atlas_scores", lambda variants: {vs[0].variant_id: {"avi": 12.5}})
    eff, flags = B.atlas_effects(vs)
    assert eff == {vs[0].variant_id: 12.5, vs[1].variant_id: 0.0} and flags == []

    def boom(variants):
        raise RuntimeError("down")
    monkeypatch.setattr(agc, "atlas_scores", boom)
    eff, flags = B.atlas_effects(vs)
    assert set(eff.values()) == {0.0} and "RuntimeError" in flags[0]


def test_gene_level_clinvar_excludes_holdout(tmp_path, monkeypatch):
    p = tmp_path / "clinvar_panel.tsv.gz"
    hdr = "variant_id\tvariation_id\tallele_id\tchrom\tpos\tref\talt\tclnsig\treview_status\tstars\tcondition_names\tcondition_dbs\tgene\tmc\n"
    rows = [
        "chr1-500-A-G\t11\t1\tchr1\t500\tA\tG\tPathogenic\tcriteria\t1\tDravet syndrome\tOMIM\tSCN1A\tintron_variant\n",   # only record of SCN1A
        "chr1-900-A-G\t12\t2\tchr1\t900\tA\tG\tPathogenic\tcriteria\t1\tDevelopmental and epileptic encephalopathy\tOMIM\tKCNQ2\tmissense\n",
        "chr1-901-A-G\t13\t3\tchr1\t901\tA\tG\tBenign\tcriteria\t1\tEpilepsy\tOMIM\tSTXBP1\tmissense\n",
        "chr1-902-A-G\t14\t4\tchr1\t902\tA\tG\tPathogenic\tcriteria\t1\tCardiomyopathy\tOMIM\tMYH7\tmissense\n",
        "chr1-903-A-G\t15\t5\tchr1\t903\tA\tG\tConflicting_interpretations_of_pathogenicity\tcriteria\t1\tEpilepsy\tOMIM\tSCN2A\tmissense\n",
    ]
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        fh.write(hdr + "".join(rows))
    monkeypatch.setattr(B, "_find", lambda name: p)
    B._plp_epilepsy_records.cache_clear()
    try:
        assert B.genes_with_plp(set()) == {"SCN1A", "KCNQ2"}
        # holding out the SCN1A record by variant id, by ClinVar id, or by a different allele at the same position
        assert B.genes_with_plp({"chr1-500-A-G"}) == {"KCNQ2"}
        assert B.genes_with_plp({"11"}) == {"KCNQ2"}
        assert B.genes_with_plp({"chr1-500-T-C"}) == {"KCNQ2"}
    finally:
        B._plp_epilepsy_records.cache_clear()


def test_missing_clinvar_table_is_flagged(monkeypatch):
    monkeypatch.setattr(B, "_find", lambda name: None)
    B._plp_epilepsy_records.cache_clear()
    try:
        case = Case(case_id="x", sample_id="s", referral_pdf="p", suspects=[var(1, "SCN1A", "intron", "intron_variant")], funnel={})
        res, info = B.fixed_recipe(case, set(), [], atlas_fn=lambda vs: ({}, []), phenotype_match_fn=lambda g, i: {"score": 0.5})
        assert any("clinvar_gene_level" in s for s in info["standins"])
    finally:
        B._plp_epilepsy_records.cache_clear()


def test_get_phenotypes_fallback_flag():
    case = Case(case_id="x", sample_id="s", referral_pdf="p", suspects=[], funnel={})
    truth = [Phenotype(hpo_id="HP:1", label="a")]
    got, flags = B.get_phenotypes(case, truth, reader=lambda pdf: [])
    assert got == truth and flags
    got, flags = B.get_phenotypes(case, truth, reader=lambda pdf: [Phenotype(hpo_id="HP:2", label="b")])
    assert got[0].hpo_id == "HP:2" and not flags
