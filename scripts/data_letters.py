"""Generate the referral letters for all DEV, TEST and DEMO options (resumable, concurrency 8) and bundle them into assets/.

Feature: runs genesleuth.data.letters.make_letter for every option in splits.json (DEV, TEST, then the first ~25 diverse DEMO
options, then the rest of DEMO), skipping letters that already exist on disk, then writes the committed bundle:
  assets/letters/<option_id>.pdf         (written directly by make_letter)
  assets/letters_meta.json.gz            (true phenotypes, scanned flag, letter text, violations per option)
  assets/clinvar_candidates.json.gz, assets/splits.json  (copied from DATA_DIR/work)
Usage: python scripts/data_letters.py [--workers 8] [--limit N] [--split dev,test,demo] [--bundle-only]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genesleuth import config  # noqa: E402
from genesleuth.data import letters, splits  # noqa: E402

ASSETS = config.ROOT / "assets"
WORK = config.DATA_DIR / "work"


def ordered_items(only: set[str]) -> list[tuple[str, dict]]:
    """(split, split-row) pairs in generation order; demo is round-robin by gene so the first ~25 are diverse."""
    s = splits.load_splits()
    items = [("dev", r) for r in s["dev"]] + [("test", r) for r in s["test"]]
    by_gene: dict[str, list] = {}
    for r in s["demo"]:
        by_gene.setdefault(r["gene"], []).append(r)
    demo, i = [], 0
    while any(by_gene.values()):
        for g in sorted(by_gene):
            if by_gene[g]:
                demo.append(by_gene[g].pop(0))
    anchor = [r for r in demo if r.get("named")]
    demo = anchor + [r for r in demo if not r.get("named")]
    items += [("demo", r) for r in demo]
    return [(sp, r) for sp, r in items if sp in only]


def bundle() -> dict:
    """Write the committed bundle files in assets/ from DATA_DIR/work and the letters dir."""
    ASSETS.mkdir(exist_ok=True)
    cand = splits.find("clinvar_candidates.json")
    if cand is not None and cand.suffix == ".json":
        d = json.loads(cand.read_text(encoding="utf-8"))
        with gzip.open(ASSETS / "clinvar_candidates.json.gz", "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(d, f, separators=(",", ":"))
    sp = WORK / "splits.json"
    if sp.exists():
        shutil.copyfile(sp, ASSETS / "splits.json")
    metas = {}
    for p in sorted((WORK / "letters").glob("*.json")):
        m = json.loads(p.read_text(encoding="utf-8"))
        metas[m["option_id"]] = m
    with gzip.open(ASSETS / "letters_meta.json.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(metas, f, separators=(",", ":"))
    sizes = [q.stat().st_size for q in (ASSETS / "letters").glob("*.pdf")]
    return {"n_meta": len(metas), "n_pdf": len(sizes), "max_pdf_kb": round(max(sizes, default=0) / 1024), "total_pdf_mb": round(sum(sizes) / 1e6, 2)}


def main(argv: list[str] | None = None) -> dict:
    """CLI entry point; idempotent and resumable."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="stop after N new letters (testing)")
    ap.add_argument("--split", default="dev,test,demo")
    ap.add_argument("--bundle-only", action="store_true")
    a = ap.parse_args(argv)
    if config.FAKE_MODE:
        raise SystemExit("FAKE_MODE must be off to generate letters")
    cands = splits.load_candidates()["by_id"]
    todo = []
    for sp, r in ordered_items(set(a.split.split(","))):
        pdf, meta = letters.letter_paths(r["option_id"])
        if not (pdf.exists() and meta.exists()):
            todo.append((sp, cands[r["option_id"]]))
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} letters to generate", flush=True)
    t0 = time.time()
    fails = 0
    if not a.bundle_only and todo:
        with ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(letters.make_letter, c, sp): c["variation_id"] for sp, c in todo}
            for i, fu in enumerate(as_completed(futs), 1):
                try:
                    m = fu.result()
                    bad = f" VIOLATIONS {m['violations']}" if m["violations"] else ""
                    print(f"[{i}/{len(todo)}] {futs[fu]} {m['gene']} scanned={m['scanned']} attempts={m['attempts']} {m['pdf_bytes']//1024}kB{bad}", flush=True)
                except Exception as e:
                    fails += 1
                    print(f"[{i}/{len(todo)}] {futs[fu]} FAILED {e}", flush=True)
    info = bundle()
    info.update({"generated": len(todo), "failed": fails, "seconds": round(time.time() - t0)})
    print(json.dumps(info))
    return info


if __name__ == "__main__":
    main()
