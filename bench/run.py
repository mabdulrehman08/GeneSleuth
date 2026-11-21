"""Benchmark runner: build each case once, run every requested arm on it, save one JSON per (mode, case).

Usage:
  python -m bench.run --split dev  --modes atlas_only,alphagenome_only,gemini_only,full,fixed_recipe
  python -m bench.run --split test --modes ... [--max-cases N] [--out bench/results] [--concurrency 2]
  python -m bench.run --split dev --modes full --calibrate        # time + request count of ONE case, sizing hint
  python -m bench.run --split dev --dry-run                       # stub agent + fake cases, output goes to DATA_DIR/work/bench_dry_run

Output: <out>/<split>/<mode>/<case_id>.json = {"result": InvestigationResult, "truth": CaseTruth, "meta": {...}}
        <out>/<split>/cases/<option_id>.json (the exact case that was run)
Resumable: finished (mode, case) pairs are skipped; --retry-errors re-runs only the errored ones (and tags meta.retried).
Errors are logged per case, never raised. Real runs assert FAKE_MODE is off and refuse the stub agent / stand-ins.
"""
from __future__ import annotations

import os
import sys

if "--dry-run" in sys.argv:  # must happen before genesleuth.config is imported
    os.environ["FAKE_MODE"] = "1"

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from genesleuth import config
from genesleuth.schemas import Case, CaseTruth, InvestigationResult, Phenotype

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "bench" / "results"
ALL_MODES = ["atlas_only", "alphagenome_only", "gemini_only", "full", "fixed_recipe"]
VALID_MODES = {"full", "alphagenome_only", "atlas_only", "gemini_only", "fixed_recipe"}
log = logging.getLogger("bench.run")
RUN_NOTES: dict = {}  # run-level settings copied into every result's meta (e.g. the Gemini timeout override)


# ----------------------------------------------------------------------------
# Guards
# ----------------------------------------------------------------------------
def assert_real_run() -> None:
    """Benchmark runs must never use mocks (builder-guide rule)."""
    if config.FAKE_MODE or os.getenv("FAKE_MODE", "0") == "1":
        raise SystemExit("FAKE_MODE is on: refusing to run a real benchmark with fakes. Unset FAKE_MODE (or use --dry-run).")


def warm_gemini_clients() -> None:
    """Create Agent B's cached Gemini SDK clients once in the main thread.

    Without this, the first concurrent calls from several worker threads race on the lru_cache'd client creation and
    fail with RuntimeError('Cannot send a request, as the client has been closed.') (reproduced on 3 parallel letter reads).
    """
    try:
        import genesleuth.gemini_clients as gc
        for version in ("v1", "v1beta"):
            gc._sdk(version, gc.GEMINI_TIMEOUT_MS)
    except Exception as e:  # noqa: BLE001
        print(f"warning: could not pre-create Gemini clients: {type(e).__name__}: {e}", flush=True)


def resolve_investigate(dry_run: bool) -> Callable:
    """Agent B's investigate for real runs; the stub only for --dry-run."""
    if dry_run:
        from bench._stub_agent import investigate
        return investigate
    try:
        from genesleuth.agent.api import investigate
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"genesleuth.agent.api.investigate is not importable yet ({type(e).__name__}: {e}); "
                         f"refusing to substitute the stub in a real run")
    return investigate


def preflight(modes: list[str], dry_run: bool, allow_standin: bool) -> list[str]:
    """Return the list of stand-ins a real run would use; abort unless allowed. Empty list = clean."""
    problems: list[str] = []
    if dry_run:
        return problems
    if "fixed_recipe" in modes:
        try:
            from genesleuth.alphagenome_client import atlas_scores  # noqa: F401
        except Exception:  # noqa: BLE001
            problems.append("alphagenome_client.atlas_scores not available (fixed_recipe would use a stand-in)")
        try:
            from genesleuth.agent.reader import read_referral  # noqa: F401
        except Exception:  # noqa: BLE001
            problems.append("agent.reader.read_referral not available (fixed_recipe would use truth phenotypes)")
        from bench import baselines
        if baselines._plp_epilepsy_records() is None:
            problems.append("clinvar_panel.tsv.gz not found in assets/ or DATA_DIR/work")
    if problems and not allow_standin:
        raise SystemExit("preflight failed (use --allow-standin to run anyway, results will be flagged):\n  - " + "\n  - ".join(problems))
    return problems


# ----------------------------------------------------------------------------
# One (case, mode)
# ----------------------------------------------------------------------------
def _error_result(case_id: str, mode: str, err: str) -> InvestigationResult:
    kw = dict(case_id=case_id, status="error", ranked=[], error=err)
    try:
        return InvestigationResult(mode=mode, **kw)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - mode not in the schema's literal
        return InvestigationResult.model_construct(mode=mode, phenotypes=[], tool_calls=[], n_alphagenome_calls=0, n_tool_calls=0,
                                                   n_claims_checked=0, n_claims_rejected=0, timings={}, **kw)


def _cached_reader(case_id: str) -> Optional[Callable]:
    """read_referral wrapped with a disk cache so the Carbon read happens once per case, not once per arm."""
    try:
        from genesleuth.agent.reader import read_referral
    except Exception:  # noqa: BLE001
        return None
    f = config.CACHE_DIR / "bench_phenotypes" / f"{case_id}.json"

    def reader(pdf: str) -> list[Phenotype]:
        if f.exists():
            return [Phenotype.model_validate(p) for p in json.loads(f.read_text(encoding="utf-8"))]
        got = read_referral(pdf)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps([p.model_dump() for p in got]), encoding="utf-8")
        return got
    return reader


async def run_mode(mode: str, case: Case, truth: CaseTruth, holdout: set[str], investigate: Callable, profile: str,
                   timeout_s: float, dry_run: bool) -> tuple[InvestigationResult, dict]:
    """Run one arm on one case. Never raises: failures become an error result."""
    extra: dict = {}
    t0 = time.time()
    try:
        if mode == "fixed_recipe":
            from bench import baselines
            reader = _cached_reader(case.case_id) if not dry_run else (lambda pdf: [])
            phenos, flags = baselines.get_phenotypes(case, truth.true_phenotypes, reader=reader)
            res, info = await asyncio.wait_for(asyncio.to_thread(baselines.fixed_recipe, case, holdout, phenos), timeout_s)
            extra["standins"] = flags + info["standins"]
        else:
            res = await asyncio.wait_for(investigate(case, holdout, mode=mode, on_event=None, profile=profile), timeout_s)
    except asyncio.TimeoutError:
        res = _error_result(case.case_id, mode, f"timeout after {timeout_s:.0f}s")
    except Exception as e:  # noqa: BLE001
        log.exception("case %s mode %s failed", case.case_id, mode)
        res = _error_result(case.case_id, mode, f"{type(e).__name__}: {e}")
    extra["wall_s"] = round(time.time() - t0, 2)
    return res, extra


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _existing_status(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["result"].get("status", "ok")
    except Exception:  # noqa: BLE001
        return "error"


# ----------------------------------------------------------------------------
# A split
# ----------------------------------------------------------------------------
async def run_split(split: str, modes: list[str], options: list[str], out_root: Path, case_loader: Callable, investigate: Callable,
                    *, profile: str = "bench", concurrency: int = 2, timeout_s: float = 900, dry_run: bool = False,
                    retry_errors: bool = False, seed_base: int = 1000, letter_type_fn: Optional[Callable[[str], str]] = None,
                    profile_by_mode: Optional[dict] = None, parallel_modes: bool = False) -> dict:
    """Run all modes on all options. Returns {'done': n, 'skipped': n, 'errors': n}."""
    if letter_type_fn is None:
        from bench._cases import detect_letter_type as letter_type_fn
    out = out_root / split
    case_dir = out / "cases"
    sem = asyncio.Semaphore(concurrency)
    stats = {"done": 0, "skipped": 0, "errors": 0}

    async def one(idx: int, oid: str) -> None:
        async with sem:
            try:
                case, truth, holdout = await asyncio.to_thread(case_loader, split, oid, seed_base + idx, case_dir)
            except Exception as e:  # noqa: BLE001
                log.exception("build_case failed for option %s", oid)
                print(f"[{split}] option {oid}: build_case FAILED: {type(e).__name__}: {e}", flush=True)
                stats["errors"] += 1
                return
            hidden_in = any(s.variant_id == truth.hidden_variant_id for s in case.suspects)
            ltype = letter_type_fn(case.referral_pdf)
            async def one_mode(mode: str) -> None:
                path = out / mode / f"{case.case_id}.json"
                st = _existing_status(path)
                retried = False
                if st == "ok" or (st == "error" and not retry_errors):
                    stats["skipped"] += 1
                    return
                retried = st == "error"
                prof = (profile_by_mode or {}).get(mode, profile)
                t_start = time.time()
                res, extra = await run_mode(mode, case, truth, holdout, investigate, prof, timeout_s, dry_run)
                meta = {"option_id": oid, "letter_type": ltype, "hidden_in_suspects": hidden_in, "n_suspects": len(case.suspects),
                        "t_start": t_start, "t_end": time.time(), "profile": prof, "stub": dry_run, "retried": retried,
                        "standins": extra.get("standins", []), "wall_s": extra["wall_s"], "region": truth.region, **RUN_NOTES}
                _write(path, {"result": res.model_dump(), "truth": truth.model_dump(), "meta": meta})
                stats["done"] += 1
                if res.status == "error":
                    stats["errors"] += 1
                rank = next((s.rank for s in res.ranked if s.variant.variant_id == truth.hidden_variant_id), None)
                print(f"[{split}] {case.case_id} {truth.gene:8s} {truth.region:8s} {mode:17s} rank={rank if rank else '-':>3} "
                      f"{res.status} {extra['wall_s']:.1f}s ag={res.n_alphagenome_calls}" + (f" ERR {res.error}" if res.error else ""),
                      flush=True)

            if parallel_modes:
                await asyncio.gather(*(one_mode(m) for m in modes))
            else:
                for m in modes:
                    await one_mode(m)

    await asyncio.gather(*(one(i, oid) for i, oid in enumerate(options)))
    return stats


# ----------------------------------------------------------------------------
# Calibration
# ----------------------------------------------------------------------------
def _calls_len() -> int:
    p = config.CACHE_DIR / "calls.jsonl"
    return sum(1 for _ in p.open("rb")) if p.exists() else 0


async def calibrate(modes: list[str], options: list[str], investigate: Callable, args, case_loader: Callable) -> None:
    """Run ONE case in each requested mode and print wall time, requests logged and a TEST sizing hint."""
    from bench import metrics as M
    oid = options[0]
    case, truth, holdout = await asyncio.to_thread(case_loader, args.split, oid, 1000, Path(args.out) / args.split / "cases")
    total = 0.0
    for mode in modes:
        before = _calls_len()
        res, extra = await run_mode(mode, case, truth, holdout, investigate, args.profile, args.timeout_s, args.dry_run)
        n_req = _calls_len() - before
        calls = M.load_calls(config.CACHE_DIR / "calls.jsonl")[before:]
        cost = sum(M.entry_cost(c) for c in calls)
        total += extra["wall_s"]
        print(f"CALIBRATE {mode:17s} {extra['wall_s']:6.1f}s  gemini_requests_logged={n_req}  est_cost=${cost:.2f}  "
              f"ag_calls={res.n_alphagenome_calls}  status={res.status}"
              f"  gemini_requests={res.timings.get('gemini_requests', 'n/a')}  cost_usd={res.timings.get('cost_usd', 'n/a')}"
              + (f"  ERROR={res.error}" if res.error else ""), flush=True)
    per_case = max(total, 1e-6)
    budget = args.budget_min * 60 * args.concurrency
    print(f"SIZING: one case, all listed modes = {per_case:.0f}s. At concurrency {args.concurrency} and {args.budget_min} min of budget "
          f"that is about {int(budget // per_case)} cases.")


# ----------------------------------------------------------------------------
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True)
    ap.add_argument("--modes", default=",".join(ALL_MODES))
    ap.add_argument("--max-cases", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--profile", default="bench")
    ap.add_argument("--timeout-s", type=float, default=900)
    ap.add_argument("--dry-run", action="store_true", help="stub agent + fake cases; output under DATA_DIR/work/bench_dry_run")
    ap.add_argument("--retry-errors", action="store_true")
    ap.add_argument("--allow-standin", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--budget-min", type=float, default=30)
    ap.add_argument("--seed-base", type=int, default=1000)
    ap.add_argument("--full-profile", default=None, help="profile for mode 'full' only (e.g. demo); other arms use --profile")
    ap.add_argument("--parallel-modes", action="store_true", help="run the arms of one case concurrently (wall time is then contended)")
    ap.add_argument("--note", default=None, help="free-text note stored in every result's meta (e.g. why a rerun was done)")
    ap.add_argument("--gemini-timeout-ms", type=int, default=None,
                    help="override Agent B's per-request Gemini timeout for this run (recorded in meta); default = unchanged")
    a = ap.parse_args(argv)

    modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    bad = [m for m in modes if m not in VALID_MODES]
    if bad:
        raise SystemExit(f"unknown/unsupported modes {bad}; valid: {sorted(VALID_MODES)}")
    if a.dry_run:
        if not config.FAKE_MODE:
            raise SystemExit("--dry-run must be given on the command line of `python -m bench.run` (it sets FAKE_MODE=1 at import)")
        a.out = a.out or str(config.DATA_DIR / "work" / "bench_dry_run")
    else:
        assert_real_run()
        a.out = a.out or str(RESULTS)
    logdir = RESULTS / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(logdir / f"run_{a.split}_{int(time.time())}.log"), level=logging.INFO)

    if a.gemini_timeout_ms:
        import genesleuth.gemini_clients as gc
        gc.GEMINI_TIMEOUT_MS = a.gemini_timeout_ms
        print(f"NOTE: Gemini request timeout overridden to {a.gemini_timeout_ms} ms (recorded in meta)", flush=True)
    RUN_NOTES["gemini_timeout_ms"] = a.gemini_timeout_ms
    if a.note:
        RUN_NOTES["note"] = a.note
    if not a.dry_run:
        warm_gemini_clients()
    standins = preflight(modes, a.dry_run, a.allow_standin)
    investigate = resolve_investigate(a.dry_run)
    from bench._cases import list_split_options, load_or_build
    options = list_split_options(a.split, a.max_cases)
    if a.max_cases:
        options = options[: a.max_cases]
    print(f"split={a.split} cases={len(options)} modes={modes} out={a.out} dry_run={a.dry_run} standins={standins or 'none'}", flush=True)
    if a.calibrate:
        asyncio.run(calibrate(modes, options, investigate, a, load_or_build))
        return
    t0 = time.time()
    stats = asyncio.run(run_split(a.split, modes, options, Path(a.out), load_or_build, investigate, profile=a.profile,
                                  concurrency=a.concurrency, timeout_s=a.timeout_s, dry_run=a.dry_run, retry_errors=a.retry_errors,
                                  seed_base=a.seed_base, parallel_modes=a.parallel_modes,
                                  profile_by_mode={"full": a.full_profile} if a.full_profile else None))
    print(f"finished in {time.time() - t0:.0f}s: {stats}")
    if a.dry_run:
        print(f"report: python -m bench.report --split {a.split} --results-dir {a.out}")


if __name__ == "__main__":
    main()
