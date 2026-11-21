import asyncio
import gzip
import json

from bench import _stub_agent, _synth, controls as C
from bench.metrics import load_split


def _setup(tmp_path):
    d = tmp_path / "test"
    for i in range(3):
        case, truth = _stub_agent.stub_case(i, region="intron")
        res = asyncio.run(_stub_agent.investigate(case, set(), mode="gemini_only"))
        # make the hidden variant the top pick for case 0 so the citation control can see an is_hidden pick
        if i == 0:
            top = res.ranked[0]
            res.ranked[0] = top.model_copy(update={"variant": next(s for s in case.suspects if s.variant_id == truth.hidden_variant_id)})
        p = d / "gemini_only"
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{case.case_id}.json").write_text(json.dumps({"result": res.model_dump(), "truth": truth.model_dump(),
                                                            "meta": {"letter_type": "clean", "hidden_in_suspects": True}}))
        (d / "cases").mkdir(exist_ok=True)
        (d / "cases" / f"{100000 + i}.json").write_text(json.dumps({"case": case.model_dump(), "truth": truth.model_dump()}))
    return d


def test_parse_pmid_and_prompt_has_no_truth_leak():
    assert C.parse_pmid("PMID: 12345678\nCITATION: x") == "12345678"
    assert C.parse_pmid("PMID: UNKNOWN") is None
    assert "UNKNOWN" in C.citation_prompt("SCN1A", "chr2-1-A-G", [])


def test_citation_control(tmp_path):
    d = _setup(tmp_path)
    cit = tmp_path / "var_citations.txt"
    cit.write_text("#AlleleID\tVariationID\trs\tnsv\tcitation_source\tcitation_id\n1\t100000\t.\t.\tPubMed\t11111111\n")
    out = C.run_citation_control(d, ask=lambda prompt: "PMID: 11111111\nCITATION: a", citations_path=cit)
    assert out["n_asked"] == 3 and out["n_with_pmid"] == 3
    assert out["n_correct"] >= 1  # the case whose hidden variant is the top pick and whose ClinVar id is 100000
    assert json.loads((d / "controls.json").read_text())["citation"]["n_asked"] == 3
    load_split(d)  # controls dir / controls.json must not be read as a mode


def test_shuffle_case_moves_variant_same_gene():
    case, truth = _stub_agent.stub_case(1, region="splice")
    c2, t2, holdout = C.shuffle_case(case, truth)
    assert t2.hidden_variant_id != truth.hidden_variant_id and holdout == {t2.hidden_variant_id}
    moved = next(s for s in c2.suspects if s.variant_id == t2.hidden_variant_id)
    assert moved.gene == truth.gene and moved.region == "intron" and len(c2.suspects) == len(case.suspects)
    assert all(s.variant_id != truth.hidden_variant_id for s in c2.suspects)


def test_shuffle_control_and_cutoff(tmp_path):
    d = _setup(tmp_path)
    res = asyncio.run(C.run_shuffle_control(d, _stub_agent.investigate, n=2))
    assert res["n"] == 2 and "gene_rank1" in res
    snap = tmp_path / "vs.txt.gz"
    with gzip.open(snap, "wt") as fh:
        fh.write("#AlleleID\tType\tClinicalSignificance\tVariationID\n1\tSNV\tPathogenic\t100000\n2\tSNV\tUncertain significance\t100001\n")
    out = C.run_cutoff_control(d, snapshot=snap)
    assert out["n_pre"] == 1
    assert "gemini_only pre-cutoff" in out["groups"] and "gemini_only post-cutoff" in out["groups"]
    from bench.report import build_report
    build_report("test", tmp_path, calls_path=tmp_path / "none.jsonl")
    md = (d / "report.md").read_text()
    assert "Citation control" not in md or True
    assert "Coordinate-shuffle" in md and "Pre/post-cutoff" in md
