"""One idempotent command that makes sure the data bundle in assets/ is complete, then smoke-tests the case builder.

Feature: checks every file the case API needs under assets/ (or DATA_DIR/work), and for anything missing calls the owning
slice's scripts/data_*.py main() to rebuild it from the public sources, in dependency order:
  panel (A1) -> background suspects (A1) -> HPO (A2) -> ClinVar panel table (A2) -> candidates (A3) -> splits (A3) -> letters (A3).
It ends with a smoke test: build_case for a random demo option in under 20 s, printing the time.
Usage: python scripts/data_setup.py [--check-only] [--no-letters] [--sample NA12878]
Safe to run repeatedly; nothing that already exists is rebuilt. Letters need GEMINI_API_KEY in .env (about 130 Hydrogen requests).
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from genesleuth import config  # noqa: E402

ASSETS = ROOT / "assets"
WORK = config.DATA_DIR / "work"


def have(name: str) -> bool:
    """True if a data file exists in assets/ or DATA_DIR/work."""
    return (ASSETS / name).exists() or (WORK / name).exists()


def run_script(module: str) -> str:
    """Import scripts/<module>.py by path and call its main() (with an empty argv if it takes one)."""
    path = ROOT / "scripts" / f"{module}.py"
    if not path.exists():
        return f"SKIPPED: scripts/{module}.py not on this checkout"
    spec = importlib.util.spec_from_file_location(module, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "main", None)
    if fn is None:
        return f"SKIPPED: {module} has no main()"
    t = time.time()
    if inspect.signature(fn).parameters:
        fn([])
    else:
        fn()
    return f"ok ({time.time() - t:.0f}s)"


def steps(sample: str, with_letters: bool) -> list[tuple[str, list[str], str | None]]:
    """(label, required files, script module that builds them) in dependency order."""
    return [
        ("panel regions + MANE features (A1)", ["panel_regions.tsv", "mane_features.tsv.gz"], "data_panel"),
        (f"background suspects {sample} (A1)", [f"suspects_{sample}.json.gz"], "data_background"),
        ("HPO tables (A2)", ["hpo_terms.json.gz", "hpo_disease.tsv.gz", "hpo_gene.tsv.gz", "hpo_gene_disease.tsv.gz"], "data_hpo"),
        ("ClinVar panel table (A2)", ["clinvar_panel.tsv.gz"], "data_clinvar_table"),
        ("ClinVar candidates (A3)", ["clinvar_candidates.json.gz"], "data_clinvar_candidates"),
        ("splits (A3)", ["splits.json"], None),
        ("letters + truth phenotypes (A3)", ["letters_meta.json.gz"], "data_letters" if with_letters else None),
    ]


def build_splits() -> str:
    """Compute splits.json into DATA_DIR/work and copy it to assets/."""
    from genesleuth.data import splits
    s = splits.make_splits()
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "splits.json").write_text(json.dumps(s, indent=1))
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "splits.json").write_text(json.dumps(s, indent=1))
    return f"ok {s['counts']}"


def letters_missing() -> list[str]:
    """Option ids of DEV/TEST/DEMO whose letter PDF is absent."""
    from genesleuth.data import splits
    s = splits.load_splits()
    return [r["option_id"] for k in ("dev", "test", "demo") for r in s[k]
            if not ((ASSETS / "letters" / f"{r['option_id']}.pdf").exists() or (WORK / "letters" / f"{r['option_id']}.pdf").exists())]


def smoke_test() -> bool:
    """build_case for a random demo option; must finish in under 20 s."""
    from genesleuth.data import api
    t = time.time()
    opts = api.list_demo_options()
    case, truth = api.build_case(None, None, "demo", seed=0)
    dt = time.time() - t
    ids = {v.variant_id for v in case.suspects}
    ok = truth.hidden_variant_id in ids and dt < 20
    print(f"smoke test: {len(opts)} demo options, case {case.case_id} with {len(case.suspects)} suspects, planted {truth.gene} "
          f"{truth.hidden_variant_id}, funnel {case.funnel}, built in {dt:.2f}s -> {'PASS' if ok else 'FAIL'}")
    print(f"mode: {'FAKES' if not _real() else 'REAL data'}")
    return ok


def _real() -> bool:
    """True if the public API is serving real data."""
    from genesleuth.data import api
    return api._real_ready()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns a process exit code (0 = bundle complete and smoke test passed)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--no-letters", action="store_true", help="do not call Gemini to generate missing letters")
    ap.add_argument("--sample", default=config.DEFAULT_SAMPLE)
    a = ap.parse_args(argv)
    if config.FAKE_MODE:
        print("FAKE_MODE=1: skipping data build; running the smoke test against the fakes")
        return 0 if smoke_test() else 1
    problems = []
    for label, files, module in steps(a.sample, not a.no_letters):
        missing = [f for f in files if not have(f)]
        if not missing:
            print(f"[have] {label}")
            continue
        print(f"[MISSING] {label}: {missing}")
        if a.check_only:
            problems.append(label)
            continue
        try:
            res = build_splits() if label.startswith("splits") else (run_script(module) if module else "SKIPPED")
            print(f"    -> {res}")
        except Exception as e:  # keep going so the report shows everything that is wrong
            print(f"    -> FAILED: {type(e).__name__}: {e}")
            problems.append(label)
    try:
        miss = letters_missing()
        print(f"[letters] {len(miss)} option(s) without a letter PDF" + (f": {miss[:8]}..." if miss else ""))
        if miss and not a.check_only and not a.no_letters:
            print("    -> data_letters:", run_script("data_letters"))
    except Exception as e:
        print("[letters] could not check:", e)
    try:
        ok = smoke_test()
    except Exception as e:
        print(f"smoke test FAILED: {type(e).__name__}: {e}")
        ok = False
    total = sum(p.stat().st_size for p in ASSETS.rglob("*") if p.is_file()) / 1e6 if ASSETS.exists() else 0
    print(f"assets/ size: {total:.1f} MB (limit 50 MB)")
    return 0 if ok and not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
