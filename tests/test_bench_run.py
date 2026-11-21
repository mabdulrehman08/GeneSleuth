import asyncio
import json

import pytest

from bench import _stub_agent
from bench.metrics import load_split
from bench.report import build_report
from bench.run import assert_real_run, run_split


def loader_factory():
    cases = {}

    def loader(split, oid, seed, case_dir):
        if oid not in cases:
            cases[oid] = _stub_agent.stub_case(int(oid), split=split, region=["intron", "coding", "splice"][int(oid) % 3])
        case, truth = cases[oid]
        return case, truth, {truth.hidden_variant_id}
    return loader


MODES = ["atlas_only", "alphagenome_only", "gemini_only", "full", "fixed_recipe"]


def test_run_resume_retry_and_report(tmp_path, monkeypatch):
    # fixed_recipe needs the lookups + baselines pieces; use their fakes/stand-ins without touching real data
    from bench import baselines
    monkeypatch.setattr(baselines, "get_phenotypes", lambda case, tp, reader=None: (list(tp), ["phenotypes(test)"]))
    orig = baselines.fixed_recipe
    monkeypatch.setattr(baselines, "fixed_recipe", lambda case, holdout, ph, **kw: orig(
        case, holdout, ph, atlas_fn=lambda vs: ({v.variant_id: 0.1 for v in vs}, ["atlas(test stand-in)"]),
        phenotype_match_fn=lambda g, ids: {"score": 0.5}, plp_genes=set()))

    stats = asyncio.run(run_split("test", MODES, ["1", "2", "3", "4"], tmp_path, loader_factory(), _stub_agent.investigate,
                                  dry_run=True, concurrency=2, letter_type_fn=lambda p: "scanned" if "scanned" in p else "clean"))
    assert stats["done"] == 20 and stats["errors"] == 0
    by_mode = load_split(tmp_path / "test")
    assert set(by_mode) == set(MODES) and all(len(v) == 4 for v in by_mode.values())
    rec = by_mode["full"][0]
    assert rec.meta["stub"] is True and rec.meta["hidden_in_suspects"] is True
    assert {r.letter_type for r in by_mode["full"]} == {"clean", "scanned"}
    assert "atlas(test stand-in)" in by_mode["fixed_recipe"][0].meta["standins"]
    # the stub never sees the truth, and the saved file keeps truth separate from the result
    raw = json.loads(next((tmp_path / "test" / "full").glob("*.json")).read_text())
    assert set(raw) == {"result", "truth", "meta"} and "hidden_variant_id" not in json.dumps(raw["result"])

    # resume: nothing re-runs
    stats = asyncio.run(run_split("test", MODES, ["1", "2", "3", "4"], tmp_path, loader_factory(), _stub_agent.investigate, dry_run=True))
    assert stats["done"] == 0 and stats["skipped"] == 20

    # a crashing agent is logged as an error result, and only errored pairs re-run with --retry-errors
    async def boom(*a, **k):
        raise RuntimeError("agent exploded")
    victim = next((tmp_path / "test" / "full").glob("*.json"))
    victim.unlink()
    stats = asyncio.run(run_split("test", ["full"], ["1", "2", "3", "4"], tmp_path, loader_factory(), boom, dry_run=True))
    assert stats["errors"] == 1 and stats["done"] == 1
    rec = next(r for r in load_split(tmp_path / "test")["full"] if r.is_error)
    assert "agent exploded" in rec.result.error
    stats = asyncio.run(run_split("test", ["full"], ["1", "2", "3", "4"], tmp_path, loader_factory(), _stub_agent.investigate,
                                  dry_run=True, retry_errors=True))
    assert stats["done"] == 1
    assert any(r.meta["retried"] for r in load_split(tmp_path / "test")["full"])

    rep = build_report("test", tmp_path, calls_path=tmp_path / "none.jsonl")
    assert rep["stub"] is True and (tmp_path / "test" / "chart.png").exists()


def test_real_run_refuses_fake_mode(monkeypatch):
    from genesleuth import config
    monkeypatch.setattr(config, "FAKE_MODE", True)
    with pytest.raises(SystemExit):
        assert_real_run()
    monkeypatch.setattr(config, "FAKE_MODE", False)
    monkeypatch.setenv("FAKE_MODE", "1")
    with pytest.raises(SystemExit):
        assert_real_run()
    monkeypatch.setenv("FAKE_MODE", "0")
    assert_real_run()
