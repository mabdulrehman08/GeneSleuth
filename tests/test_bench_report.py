import json

from PIL import Image

from bench import _synth
from bench.metrics import load_split
from bench.report import build_report, classify_failure, fill_doc
from genesleuth.schemas import ToolCall

HID = _synth.make_truth("x").hidden_variant_id


def tc(tool, args, result, i=0):
    return ToolCall(call_id=f"t{i}", tool=tool, args=args, result=result, result_summary="s")


def rec_for(tmp_path, name, **kw):
    kw.setdefault("hidden_rank", None)
    _synth.write_result(tmp_path, "test", "full", name, **kw)
    return next(r for r in load_split(tmp_path / "test")["full"] if r.case_id == name)


def test_categories(tmp_path):
    brain = {"tissue": "UBERON:0000955", "tissue_name": "brain", "max_abs_effect": 0.9}
    other = {"tissue": "UBERON:0000178", "tissue_name": "blood", "max_abs_effect": 0.9}
    strong_other = [tc("score_variant", {"variant_id": "chr1-1-A-C", "tissue": "UBERON:0000955"}, {**brain, "max_abs_effect": 0.5}, 9)]

    assert classify_failure(rec_for(tmp_path, "e", status="error"))[0] == "error"
    assert classify_failure(rec_for(tmp_path, "n"))[0] == "never_inspected"
    r = rec_for(tmp_path, "w", tool_calls=[tc("score_variant", {"variant_id": HID, "tissue": "UBERON:0000178"}, other)])
    assert classify_failure(r)[0] == "wrong_tissue"
    r = rec_for(tmp_path, "k", tool_calls=[tc("score_variant", {"variant_id": HID, "tissue": "UBERON:0000955"}, {**brain, "max_abs_effect": 0.01})] + strong_other)
    assert classify_failure(r)[0] == "weak_alphagenome_effect"
    r = rec_for(tmp_path, "p", tool_calls=[tc("score_variant", {"variant_id": HID, "tissue": "UBERON:0000955"}, brain),
                                           tc("phenotype_match", {"gene": "SCN1A", "variant_id": HID}, {"score": 0.1}, 2)] + strong_other)
    assert classify_failure(r)[0] == "phenotype_mismatch"
    r = rec_for(tmp_path, "c", tool_calls=[tc("score_variant", {"variant_id": HID, "tissue": "UBERON:0000955"}, brain)] + strong_other,
                top_regions=["coding"] * 10)
    assert classify_failure(r)[0] == "outranked_by_coding"
    r = rec_for(tmp_path, "a", tool_calls=[tc("population_frequency", {"variant_id": HID}, {"found": True, "af": 0.02})])
    assert classify_failure(r)[0] == "missed_second_hit_or_common_allele"
    r = rec_for(tmp_path, "af-bin", tool_calls=[tc("population_frequency", {"variant_id": HID}, {"af_bin": "0.1-1%"})])
    assert classify_failure(r)[0] == "missed_second_hit_or_common_allele"
    r = rec_for(tmp_path, "u", tool_calls=[tc("score_variant", {"variant_id": HID, "tissue": "UBERON:0000955"}, brain)] + strong_other,
                top_regions=["intron"] * 10)
    assert classify_failure(r)[0] == "unclassified"


def test_report_end_to_end(tmp_path):
    for i in range(6):
        for mode, rk in (("full", [1, 3, None, 6, None, 2][i]), ("atlas_only", [None, 8, None, None, 1, None][i])):
            _synth.write_result(tmp_path, "test", mode, f"case{i}", rk, region="coding" if i % 2 else "intron",
                                letter_type="clean" if i < 3 else "scanned")
    (tmp_path / "test" / "controls.json").write_text(json.dumps({"citation": {"n_correct": 0, "n_asked": 5}}))
    rep = build_report("test", tmp_path, calls_path=tmp_path / "none.jsonl")
    d = tmp_path / "test"
    assert (d / "report.md").exists() and (d / "failures.md").exists()
    with Image.open(d / "chart.png") as im:
        assert im.size == (1600, 900)
    md = (d / "report.md").read_text()
    assert "STUB RESULTS" in md and "Wilson" in md and "GeneSleuth (full agent)" in md
    assert "Citation control" in md
    assert "## case" in (d / "failures.md").read_text()
    assert rep["n_cases"] == 6


def test_fill_doc(tmp_path):
    doc = tmp_path / "B.md"
    doc.write_text("a\n<!-- RESULTS:START -->\nold\n<!-- RESULTS:END -->\nz\n")
    assert fill_doc("test", {"tables": ["# Benchmark report: test", "| t |"]}, doc)
    t = doc.read_text()
    assert "old" not in t and "| t |" in t and t.startswith("a\n") and t.endswith("z\n")
