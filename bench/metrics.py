"""Benchmark metrics for GeneSleuth.

Feature: turn the per-case result files written by bench/run.py into the numbers
reported in docs/BENCHMARK.md: hit@1/5/10 with 95% Wilson binomial confidence
intervals, MRR@10, median rank, filter recall, AlphaGenome calls, time, claim
checks and cost per case, each overall and split by region type (coding vs
non-coding) and letter type (clean vs scanned).

Result file layout (bench/results/<split>/<mode>/<case_id>.json):
    {"result": InvestigationResult, "truth": CaseTruth, "meta": {...}}
meta keys written by bench/run.py: letter_type, hidden_in_suspects, n_suspects,
wall_s, t_start, t_end, stub, profile.

Conventions (stated in the report as well):
  * rank = position of the hidden variant in the mode's ranked list (1-based).
    Rank 11+ or absent = miss. Errored runs stay in the denominator as misses.
  * MRR is MRR@10: 1/rank when rank <= 10, else 0.
  * median rank counts a miss as 11 (so "11" means "11 or worse").
  * Wilson interval: z = 1.96. With small n the interval is wide; the report
    prints n next to every number.
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from genesleuth.schemas import CaseTruth, InvestigationResult

MISS_RANK = 11
KS = (1, 5, 10)
Z95 = 1.959963984540054


# ----------------------------------------------------------------------------
# Wilson interval
# ----------------------------------------------------------------------------
def wilson_ci(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for k successes in n trials. n == 0 gives (0, 1)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def prop(k: int, n: int) -> dict:
    """Proportion with its Wilson CI as a plain dict."""
    lo, hi = wilson_ci(k, n)
    return {"k": k, "n": n, "p": (k / n) if n else float("nan"), "lo": lo, "hi": hi}


# ----------------------------------------------------------------------------
# Records
# ----------------------------------------------------------------------------
@dataclass
class CaseRecord:
    """One (mode, case) outcome, with the derived fields the metrics need."""
    mode: str
    case_id: str
    result: Optional[InvestigationResult]
    truth: CaseTruth
    meta: dict = field(default_factory=dict)
    path: str = ""
    load_error: Optional[str] = None

    @property
    def hidden_id(self) -> str:
        return self.truth.hidden_variant_id

    @property
    def is_error(self) -> bool:
        return self.result is None or self.result.status == "error"

    @property
    def rank(self) -> Optional[int]:
        """Rank of the hidden variant (1-based) or None if it is not in the ranked list."""
        return rank_of(self.result, self.hidden_id)

    @property
    def effective_rank(self) -> int:
        r = self.rank
        return r if (r is not None and r < MISS_RANK) else MISS_RANK

    @property
    def region_type(self) -> str:
        return "coding" if (self.truth.region or "other") == "coding" else "non-coding"

    @property
    def letter_type(self) -> str:
        return str(self.meta.get("letter_type") or "unknown")

    @property
    def time_s(self) -> Optional[float]:
        if self.result is not None:
            for key in ("total", "total_s"):
                t = self.result.timings.get(key)
                if t is not None:
                    return float(t)
        w = self.meta.get("wall_s")
        return float(w) if w is not None else None


def rank_of(result: Optional[InvestigationResult], hidden_id: str) -> Optional[int]:
    """1-based rank of hidden_id in result.ranked, or None."""
    if result is None:
        return None
    for i, s in enumerate(sorted(result.ranked, key=lambda r: r.rank), start=1):
        if s.variant.variant_id == hidden_id:
            return s.rank if s.rank else i
    return None


def load_record(path: Path, mode: str) -> CaseRecord:
    """Load one result file. Malformed files become error records (counted as misses)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    truth = CaseTruth.model_validate(raw["truth"])
    meta = raw.get("meta") or {}
    try:
        res = InvestigationResult.model_validate(raw["result"])
        err = None
    except Exception as e:  # noqa: BLE001 - report, do not crash
        res, err = None, f"{type(e).__name__}: {e}"
    return CaseRecord(mode=mode, case_id=truth.case_id, result=res, truth=truth, meta=meta,
                      path=str(path), load_error=err)


def load_split(split_dir: Path) -> dict[str, list[CaseRecord]]:
    """Load bench/results/<split>/<mode>/*.json into {mode: [CaseRecord]} (sorted by case id)."""
    out: dict[str, list[CaseRecord]] = {}
    if not split_dir.exists():
        return out
    for mode_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
        if mode_dir.name in ("logs", "cases", "controls"):
            continue
        recs = [load_record(f, mode_dir.name) for f in sorted(mode_dir.glob("*.json"))]
        if recs:
            out[mode_dir.name] = recs
    return out


# ----------------------------------------------------------------------------
# Summaries
# ----------------------------------------------------------------------------
def _median(xs: Iterable[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def summarize(records: list[CaseRecord]) -> dict:
    """All headline numbers for one set of records (one mode, optionally a subset)."""
    n = len(records)
    ranks = [r.effective_rank for r in records]
    out: dict[str, Any] = {"n": n, "n_error": sum(1 for r in records if r.is_error)}
    for k in KS:
        out[f"hit@{k}"] = prop(sum(1 for x in ranks if x <= k), n)
    out["mrr@10"] = (sum(1.0 / x for x in ranks if x <= 10) / n) if n else float("nan")
    out["median_rank"] = _median(ranks)
    out["median_rank_is_lower_bound"] = bool(n) and (out["median_rank"] == MISS_RANK)

    flags = [r.meta.get("hidden_in_suspects") for r in records if r.meta.get("hidden_in_suspects") is not None]
    out["filter_recall"] = prop(sum(1 for f in flags if f), len(flags))

    ok = [r for r in records if r.result is not None]
    out["median_ag_calls"] = _median(r.result.n_alphagenome_calls for r in ok)
    out["median_tool_calls"] = _median(r.result.n_tool_calls for r in ok)
    out["median_time_s"] = _median(r.time_s for r in records)
    out["claims_checked_total"] = sum(r.result.n_claims_checked for r in ok)
    out["claims_rejected_total"] = sum(r.result.n_claims_rejected for r in ok)
    out["median_claims_checked"] = _median(r.result.n_claims_checked for r in ok)
    out["median_claims_rejected"] = _median(r.result.n_claims_rejected for r in ok)
    out["stub"] = any(bool(r.meta.get("stub")) for r in records)
    out["standin"] = sorted({s for r in records for s in (r.meta.get("standins") or [])})
    return out


def breakdowns(records: list[CaseRecord]) -> dict[str, dict[str, dict]]:
    """Summaries by region type and by letter type: {'region_type': {'coding': summary, ...}, ...}."""
    res: dict[str, dict[str, dict]] = {"region_type": {}, "letter_type": {}}
    for key in ("region_type", "letter_type"):
        groups: dict[str, list[CaseRecord]] = {}
        for r in records:
            groups.setdefault(getattr(r, key), []).append(r)
        for g, rs in sorted(groups.items()):
            res[key][g] = summarize(rs)
    return res


def analyze(by_mode: dict[str, list[CaseRecord]]) -> dict[str, dict]:
    """{mode: {'overall': summary, 'by': breakdowns}}."""
    return {m: {"overall": summarize(rs), "by": breakdowns(rs)} for m, rs in by_mode.items()}


def common_case_ids(by_mode: dict[str, list[CaseRecord]]) -> set[str]:
    """Case ids that every mode has a result for (use to check the arms saw the same cases)."""
    sets = [{r.case_id for r in rs} for rs in by_mode.values()]
    return set.intersection(*sets) if sets else set()


# ----------------------------------------------------------------------------
# Cost per case from calls.jsonl
# ----------------------------------------------------------------------------
# USD per 1M tokens (input, output), from the builder guide promo prices; Decision 1 is per call.
PRICES = {
    "gemini-4-carbon": (2.0, 10.0),
    "gemini-4-neon": (3.0, 15.0),
    "gemini-4-hydrogen": (1.5, 7.5),
}
DECISION_PER_CALL = 0.10


def _tok(d: dict, *names: str) -> int:
    for n in names:
        v = d.get(n)
        if isinstance(v, (int, float)):
            return int(v)
    return 0


def entry_cost(e: dict) -> float:
    """USD cost of one calls.jsonl line. Uses an explicit cost field when present."""
    for k in ("cost_usd", "cost"):
        if isinstance(e.get(k), (int, float)):
            return float(e[k])
    model = str(e.get("model") or e.get("modelVersion") or "")
    if "decision" in model:
        return DECISION_PER_CALL
    usage = e.get("usage") or {}
    tin = _tok(usage, "input_tokens", "prompt_token_count", "prompt_tokens", "total_input_tokens")
    tout = _tok(usage, "output_tokens", "candidates_token_count", "completion_tokens", "total_output_tokens")
    tout += _tok(usage, "thoughts_token_count", "total_thought_tokens", "reasoning_tokens")  # billed as output
    for key, (pin, pout) in PRICES.items():
        if key in model:
            return (tin * pin + tout * pout) / 1e6
    return 0.0


def _entry_ts(e: dict) -> Optional[float]:
    for k in ("ts", "timestamp", "time", "t"):
        v = e.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                from datetime import datetime
                return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
    return None


def load_calls(path: Path) -> list[dict]:
    """Read DATA_DIR/cache/calls.jsonl (missing file -> [])."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def cost_per_case(records: list[CaseRecord], calls: list[dict]) -> dict:
    """Cost (USD) and Gemini request count per case for one mode.

    Attribution: a call line carrying case_id is assigned to that case. Otherwise it is
    assigned by time window (meta t_start..t_end of each record), split evenly if several
    cases ran at the same time; then the numbers are approximate and flagged so.
    """
    by_id = {r.case_id: [0.0, 0] for r in records}
    approx = False
    # Agent B records exact per-run cost and request count in result.timings; use those when present.
    exact = {r.case_id for r in records if r.result is not None and "cost_usd" in r.result.timings}
    for r in records:
        if r.case_id in exact:
            by_id[r.case_id] = [float(r.result.timings["cost_usd"]), float(r.result.timings.get("gemini_requests", 0))]
    windows = [(r.case_id, r.meta.get("t_start"), r.meta.get("t_end")) for r in records
               if isinstance(r.meta.get("t_start"), (int, float)) and isinstance(r.meta.get("t_end"), (int, float))]
    for e in calls:
        if e.get("source") == "bench_controls":
            continue
        c = entry_cost(e)
        cid = e.get("case_id")
        if cid in exact:
            continue
        if cid in by_id:
            by_id[cid][0] += c
            by_id[cid][1] += 1
            continue
        ts = _entry_ts(e)
        if ts is None or not windows:
            continue
        hit = [w[0] for w in windows if w[1] <= ts <= w[2] and w[0] not in exact]
        if hit:
            approx = True
            for h in hit:
                by_id[h][0] += c / len(hit)
                by_id[h][1] += 1.0 / len(hit)
    costs = [v[0] for v in by_id.values()]
    reqs = [v[1] for v in by_id.values()]
    return {
        "median_cost_usd": _median(costs),
        "total_cost_usd": sum(costs),
        "median_requests": _median(reqs),
        "total_requests": sum(reqs),
        "approximate_attribution": approx,
        "n_cases": len(records),
    }
