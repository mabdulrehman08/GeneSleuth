import math

import pytest

from bench import _synth
from bench.metrics import (MISS_RANK, analyze, breakdowns, common_case_ids, cost_per_case, entry_cost, load_split,
                           summarize, wilson_ci)


def test_wilson_known_values():
    lo, hi = wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    lo, hi = wilson_ci(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-3)
    lo, hi = wilson_ci(10, 10)
    assert hi == pytest.approx(1.0, abs=1e-9) and lo == pytest.approx(0.7225, abs=1e-3)
    assert wilson_ci(0, 0) == (0.0, 1.0)
    # n = 30, 15 successes: half-width 0.1685
    lo, hi = wilson_ci(15, 30)
    assert (hi - lo) / 2 == pytest.approx(0.1685, abs=1e-3)


def _make(tmp_path):
    rows = [  # case, rank, region, letter
        ("c1", 1, "coding", "clean"), ("c2", 4, "intron", "clean"), ("c3", 7, "splice", "scanned"),
        ("c4", None, "intron", "scanned"), ("c5", 12, "utr5", "clean"), ("c6", 5, "coding", "scanned"),
    ]
    for cid, rk, reg, lt in rows:
        _synth.write_result(tmp_path, "test", "full", cid, rk if rk and rk <= 10 else None, region=reg, letter_type=lt,
                            n_ag=10, claims_checked=6, claims_rejected=1)
    # one errored run counts as a miss
    _synth.write_result(tmp_path, "test", "full", "c7", None, region="intron", letter_type="clean", status="error")
    for cid, rk, reg, lt in rows:
        _synth.write_result(tmp_path, "test", "atlas_only", cid, None, region=reg, letter_type=lt)
    return rows


def test_summary_hit_rates_and_breakdowns(tmp_path):
    _make(tmp_path)
    by_mode = load_split(tmp_path / "test")
    assert set(by_mode) == {"full", "atlas_only"}
    s = summarize(by_mode["full"])
    assert s["n"] == 7 and s["n_error"] == 1
    # ranks: 1,4,7,miss,miss(12),5,miss(error)  -> hit@1=1, hit@5=3, hit@10=4
    assert s["hit@1"]["k"] == 1 and s["hit@5"]["k"] == 3 and s["hit@10"]["k"] == 4
    assert s["hit@5"]["n"] == 7
    assert s["hit@5"]["p"] == pytest.approx(3 / 7)
    assert s["hit@5"]["lo"] < s["hit@5"]["p"] < s["hit@5"]["hi"]
    assert s["mrr@10"] == pytest.approx((1 + 1 / 4 + 1 / 7 + 1 / 5) / 7)
    assert s["median_rank"] == 7  # sorted 1,4,5,7,11,11,11
    assert s["filter_recall"]["k"] == 7 and s["filter_recall"]["p"] == 1.0
    assert s["median_ag_calls"] == 10
    assert s["claims_checked_total"] == 36 and s["claims_rejected_total"] == 6
    b = breakdowns(by_mode["full"])
    assert b["region_type"]["coding"]["n"] == 2 and b["region_type"]["coding"]["hit@5"]["k"] == 2
    assert b["region_type"]["non-coding"]["n"] == 5 and b["region_type"]["non-coding"]["hit@5"]["k"] == 1
    assert b["letter_type"]["scanned"]["n"] == 3 and b["letter_type"]["scanned"]["hit@5"]["k"] == 1
    a = analyze(by_mode)
    assert a["atlas_only"]["overall"]["hit@10"]["k"] == 0
    assert a["atlas_only"]["overall"]["median_rank"] == MISS_RANK
    assert a["atlas_only"]["overall"]["median_rank_is_lower_bound"]
    assert a["full"]["overall"]["stub"] is True


def test_common_case_ids(tmp_path):
    _make(tmp_path)
    by_mode = load_split(tmp_path / "test")
    assert common_case_ids(by_mode) == {"c1", "c2", "c3", "c4", "c5", "c6"}


def test_cost_explicit_and_by_case_id_and_window(tmp_path):
    assert entry_cost({"cost_usd": 0.5}) == 0.5
    assert entry_cost({"model": "gemini-decision-1"}) == pytest.approx(0.10)
    assert entry_cost({"model": "gemini-4-neon", "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000,
                                                          "thoughts_token_count": 100_000}}) == pytest.approx(3 + 3)
    assert entry_cost({"model": "unknown"}) == 0.0
    _synth.write_result(tmp_path, "test", "full", "a", 1)
    _synth.write_result(tmp_path, "test", "full", "b", 2)
    recs = load_split(tmp_path / "test")["full"]
    for r in recs:
        r.meta["t_start"], r.meta["t_end"] = 100.0, 200.0
    calls = [{"model": "gemini-4-neon", "case_id": "a", "usage": {"input_tokens": 1_000_000}},
             {"model": "gemini-decision-1", "ts": 150.0},          # in both windows: split
             {"model": "gemini-decision-1", "ts": 999.0},          # outside: ignored
             {"model": "gemini-decision-1", "source": "bench_controls", "ts": 150.0}]  # controls excluded
    c = cost_per_case(recs, calls)
    assert c["total_cost_usd"] == pytest.approx(3.0 + 0.10)
    assert c["approximate_attribution"] is True
    assert not math.isnan(c["median_cost_usd"])
