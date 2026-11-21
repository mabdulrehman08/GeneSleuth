"""Leakage / memorization controls for the benchmark.

Feature: three checks on whether Gemini "solves" cases by recall instead of reading the variant. Results are merged into
bench/results/<split>/controls.json, which bench/report.py prints in report.md. Run after the arms have run.

  1. citation   Ask gemini_only's top pick for a publication (PMID). A PMID that ClinVar lists for that variant counts as
                memorization. Verification is automatic against ClinVar var_citations.txt; PMIDs we cannot check are listed.
  2. shuffle    Move the true variant to a different, uninformative intronic position in the same gene and rerun gemini_only
                on 5 cases. If the true gene still ranks first, the model is recalling the gene from the phenotype.
  3. cutoff     Split TEST cases into "already Pathogenic/Likely pathogenic in the 2025-01 ClinVar snapshot" (pre-cutoff) and
                the rest (post-cutoff or reclassified), and compare hit@5 per arm. Gemini 4's real knowledge cutoff is not
                known to us, so 2025-01 is an assumption and is stated as one.

Usage: python -m bench.controls --split test --which citation,shuffle,cutoff
Real runs only (asserts FAKE_MODE is off). Gemini requests are few: one per gemini_only case for the citation control and
one per shuffled case.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import re
import time
from pathlib import Path
from typing import Callable, Optional

from bench import metrics as M
from genesleuth import config
from genesleuth.schemas import Case, CaseTruth, Phenotype, Variant

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "bench" / "results"
SNAPSHOT = "2025-01"
PLP = re.compile(r"^(pathogenic|likely pathogenic|pathogenic/likely pathogenic)", re.I)


def _merge_controls(split_dir: Path, key: str, value: dict) -> None:
    p = split_dir / "controls.json"
    cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    cur[key] = value
    p.write_text(json.dumps(cur, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------------
# Gemini call (kept tiny; logged to calls.jsonl with source=bench_controls)
# ----------------------------------------------------------------------------
def ask_gemini(prompt: str, model: Optional[str] = None, tag: str = "citation") -> str:
    """One Interactions API call (builder-guide shape), up to 4 tries on transient errors, logged without prompts' secrets."""
    try:
        from genesleuth.gemini_clients import client  # Agent B's module when it exists
    except Exception:  # noqa: BLE001
        from google import genai
        client = genai.Client()
    model = model or config.NEON
    last: Optional[Exception] = None
    for attempt in range(4):
        t0 = time.time()
        try:
            r = client.interactions.create(model=model, input=prompt, generation_config={"thinking_level": "medium"})
            text = r.output_text
            usage = getattr(r, "usage", None)
            _log_call(model, tag, prompt, text, time.time() - t0, usage)
            return text
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"gemini call failed after 4 tries: {last}")


def _log_call(model: str, tag: str, prompt: str, text: str, latency: float, usage) -> None:
    p = config.CACHE_DIR / "calls.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    u = {}
    if usage is not None:
        for k in ("input_tokens", "output_tokens", "total_input_tokens", "total_output_tokens", "total_thought_tokens"):
            v = getattr(usage, k, None)
            if isinstance(v, int):
                u[k] = v
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.time(), "source": "bench_controls", "tag": tag, "model": model, "prompt": prompt[:2000],
                             "output": text[:2000], "latency_s": round(latency, 2), "usage": u}) + "\n")


# ----------------------------------------------------------------------------
# 1. Citation control
# ----------------------------------------------------------------------------
def citation_prompt(gene: str, variant_id: str, phenotypes: list[Phenotype]) -> str:
    terms = "; ".join(p.label for p in phenotypes[:8])
    return (f"A patient has: {terms}. Consider the variant {variant_id} (GRCh38) in the gene {gene}. "
            "Name the publication that first reported this exact variant as disease-causing. "
            "If you do not know of one, say UNKNOWN; do not guess. "
            "Answer in exactly this format on two lines:\nPMID: <number or UNKNOWN>\nCITATION: <first author, year, journal, title, or UNKNOWN>")


def parse_pmid(text: str) -> Optional[str]:
    m = re.search(r"PMID:\s*(\d{4,9})", text or "")
    return m.group(1) if m else None


def clinvar_citations(variation_ids: set[str], path: Optional[Path] = None) -> dict[str, set[str]]:
    """{VariationID: {PMID}} from ClinVar var_citations.txt (PubMed rows only). Empty dict values mean 'no citations listed'."""
    path = path or (config.DATA_DIR / "raw" / "var_citations.txt")
    out: dict[str, set[str]] = {v: set() for v in variation_ids}
    if not path.exists():
        raise FileNotFoundError(f"{path} missing (download ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/var_citations.txt)")
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline().lstrip("#").rstrip("\n").split("\t")
        iv, isrc, iid = header.index("VariationID"), header.index("citation_source"), header.index("citation_id")
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) > iid and f[iv] in out and f[isrc].lower().startswith("pubmed"):
                out[f[iv]].add(f[iid])
    return out


def variation_id_of(variant_id: str, table: Optional[Path] = None) -> Optional[str]:
    """ClinVar VariationID for a variant id from the local panel table (assets/ first). None when ClinVar has no record."""
    from bench.baselines import _find
    p = table or _find("clinvar_panel.tsv.gz")
    if p is None:
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        iv, ii = header.index("variant_id"), header.index("variation_id")
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if f[iv] == variant_id:
                return f[ii]
    return None


def run_citation_control(split_dir: Path, ask: Callable[[str], str] = ask_gemini, citations_path: Optional[Path] = None,
                         max_n: Optional[int] = None) -> dict:
    """Ask for a publication for each gemini_only top pick and verify the PMID against ClinVar's citation list."""
    recs = [r for r in M.load_split(split_dir).get("gemini_only", []) if r.result and r.result.ranked]
    recs = recs[:max_n] if max_n else recs
    rows, ids = [], set()
    for r in recs:
        top = sorted(r.result.ranked, key=lambda s: s.rank)[0].variant
        is_hidden = top.variant_id == r.hidden_id
        vid = r.truth.clinvar_id if is_hidden else variation_id_of(top.variant_id)
        out = ask(citation_prompt(top.gene or "", top.variant_id, r.result.phenotypes or r.truth.true_phenotypes))
        rows.append({"case_id": r.case_id, "pick": top.variant_id, "is_hidden": is_hidden, "variation_id": vid,
                     "pmid": parse_pmid(out), "answer": out[:300]})
        if vid:
            ids.add(str(vid))
    cites = clinvar_citations(ids, citations_path) if ids else {}
    n_pmid = n_correct = n_correct_hidden = n_unverifiable = 0
    for row in rows:
        if row["pmid"]:
            n_pmid += 1
            if not row["variation_id"]:
                row["verdict"] = "unverifiable (variant has no ClinVar record)"
                n_unverifiable += 1
            elif row["pmid"] in cites.get(str(row["variation_id"]), set()):
                row["verdict"] = "correct (PMID listed by ClinVar for this variant)"
                n_correct += 1
                n_correct_hidden += int(row["is_hidden"])
            else:
                row["verdict"] = "not in ClinVar citations for this variant"
        else:
            row["verdict"] = "no PMID given"
    res = {"n_asked": len(rows), "n_with_pmid": n_pmid, "n_correct": n_correct, "n_correct_on_hidden": n_correct_hidden,
           "n_unverifiable": n_unverifiable,
           "note": "correct = the PMID is listed in ClinVar var_citations for that variant; a different relevant paper counts as "
                   "incorrect, so this is a lower bound on memorization", "rows": rows}
    _merge_controls(split_dir, "citation", res)
    return res


# ----------------------------------------------------------------------------
# 2. Coordinate-shuffle control
# ----------------------------------------------------------------------------
def shuffle_case(case: Case, truth: CaseTruth, seed: int = 7) -> tuple[Case, CaseTruth, set[str]]:
    """Copy of the case where the true variant sits at a different position in the same gene, labelled intronic."""
    import random
    rng = random.Random(f"{truth.case_id}-{seed}")
    hidden = next(s for s in case.suspects if s.variant_id == truth.hidden_variant_id)
    taken = {s.variant_id for s in case.suspects}
    for _ in range(50):
        shift = rng.choice([-1, 1]) * rng.randint(2000, 9000)
        pos = hidden.pos + shift
        vid = f"{hidden.chrom}-{pos}-{hidden.ref}-{hidden.alt}"
        if vid not in taken:
            break
    moved = hidden.model_copy(update={"variant_id": vid, "pos": pos, "region": "intron", "consequence": "intron_variant",
                                      "distance_to_tss": (hidden.distance_to_tss + shift) if hidden.distance_to_tss is not None else None})
    new_id = "shuf" + case.case_id
    suspects = [moved if s.variant_id == hidden.variant_id else s for s in case.suspects]
    c2 = case.model_copy(update={"case_id": new_id, "suspects": suspects})
    t2 = truth.model_copy(update={"case_id": new_id, "hidden_variant_id": vid, "region": "intron"})
    return c2, t2, {vid}


def gene_rank(result, gene: str) -> Optional[int]:
    """Best (lowest) rank of any ranked variant in the gene, or None."""
    ranks = [s.rank for s in result.ranked if (s.variant.gene or "").upper() == gene.upper()]
    return min(ranks) if ranks else None


async def run_shuffle_control(split_dir: Path, investigate: Callable, n: int = 5) -> dict:
    """Rerun gemini_only on n shuffled cases (non-coding cases first) and summarise gene-level and variant-level recall."""
    by_mode = M.load_split(split_dir)
    gem = {r.case_id: r for r in by_mode.get("gemini_only", [])}
    chosen = sorted(gem.values(), key=lambda r: (r.region_type == "coding", r.case_id))[:n]
    out_dir = split_dir / "controls" / "shuffle"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in chosen:
        cf = next((f for f in (split_dir / "cases").glob("*.json") if json.loads(f.read_text(encoding="utf-8"))["case"]["case_id"] == r.case_id), None)
        if cf is None:
            continue
        raw = json.loads(cf.read_text(encoding="utf-8"))
        case, truth = Case.model_validate(raw["case"]), CaseTruth.model_validate(raw["truth"])
        c2, t2, holdout = shuffle_case(case, truth)
        res = await investigate(c2, holdout, mode="gemini_only", on_event=None, profile="bench")
        (out_dir / f"{c2.case_id}.json").write_text(json.dumps({"result": res.model_dump(), "truth": t2.model_dump()}), encoding="utf-8")
        gr = gene_rank(res, truth.gene) if res.status == "ok" else None
        orig_gr = gene_rank(r.result, truth.gene) if r.result else None
        rows.append({"case_id": r.case_id, "gene": truth.gene, "shuffled_variant_rank": M.rank_of(res, t2.hidden_variant_id),
                     "gene_rank": gr, "original_gene_rank": orig_gr, "original_variant_rank": r.rank})
    k = lambda f: sum(1 for x in rows if f(x))  # noqa: E731
    summary = {"n": len(rows), "gene_rank1": k(lambda x: x["gene_rank"] == 1), "gene_top5": k(lambda x: x["gene_rank"] and x["gene_rank"] <= 5),
               "variant_top10": k(lambda x: x["shuffled_variant_rank"] and x["shuffled_variant_rank"] <= 10),
               "orig_gene_rank1": k(lambda x: x["original_gene_rank"] == 1), "rows": rows,
               "note": "shuffled position is offset 2-9 kb from the true one and labelled intronic without an exon check"}
    _merge_controls(split_dir, "shuffle", summary)
    return summary


# ----------------------------------------------------------------------------
# 3. Pre/post-cutoff subgroup
# ----------------------------------------------------------------------------
def plp_variation_ids_in_snapshot(snapshot: Path, wanted: set[str]) -> set[str]:
    """Wanted VariationIDs that were Pathogenic / Likely pathogenic in the archived variant_summary snapshot."""
    found: set[str] = set()
    with gzip.open(snapshot, "rt", encoding="utf-8", errors="replace") as fh:
        header = fh.readline().lstrip("#").rstrip("\n").split("\t")
        iv, isig = header.index("VariationID"), header.index("ClinicalSignificance")
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) > max(iv, isig) and f[iv] in wanted and PLP.match(f[isig]):
                found.add(f[iv])
    return found


def run_cutoff_control(split_dir: Path, snapshot: Optional[Path] = None) -> dict:
    """hit@5 per arm for cases whose variant was P/LP in the 2025-01 snapshot (pre) vs not (post)."""
    from bench.report import pct
    snapshot = snapshot or (config.DATA_DIR / "raw" / f"variant_summary_{SNAPSHOT}.txt.gz")
    by_mode = M.load_split(split_dir)
    ids = {str(r.truth.clinvar_id) for rs in by_mode.values() for r in rs if r.truth.clinvar_id}
    pre_ids = plp_variation_ids_in_snapshot(snapshot, ids)
    groups: dict[str, str] = {}
    for mode, rs in sorted(by_mode.items()):
        for name, pick in (("pre-cutoff", lambda r: str(r.truth.clinvar_id) in pre_ids),
                           ("post-cutoff", lambda r: str(r.truth.clinvar_id) not in pre_ids)):
            sub = [r for r in rs if pick(r)]
            groups[f"{mode} {name}"] = pct(M.summarize(sub)["hit@5"]) if sub else "n/a (0 cases)"
    res = {"snapshot": SNAPSHOT, "cutoff_note": f"unknown; assumed ClinVar {SNAPSHOT} snapshot", "n_pre": len(pre_ids), "n_cases": len(ids),
           "groups": groups}
    _merge_controls(split_dir, "cutoff", res)
    return res


# ----------------------------------------------------------------------------
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True)
    ap.add_argument("--which", default="citation,shuffle,cutoff")
    ap.add_argument("--out", default=str(RESULTS))
    ap.add_argument("--n-shuffle", type=int, default=5)
    a = ap.parse_args(argv)
    from bench.run import assert_real_run, resolve_investigate
    assert_real_run()
    split_dir = Path(a.out) / a.split
    which = {w.strip() for w in a.which.split(",")}
    if "citation" in which:
        r = run_citation_control(split_dir)
        print(f"citation: asked {r['n_asked']}, with PMID {r['n_with_pmid']}, correct {r['n_correct']} (on hidden: {r['n_correct_on_hidden']})")
    if "shuffle" in which:
        r = asyncio.run(run_shuffle_control(split_dir, resolve_investigate(False), a.n_shuffle))
        print(f"shuffle: n={r['n']} gene_rank1={r['gene_rank1']} gene_top5={r['gene_top5']} variant_top10={r['variant_top10']}")
    if "cutoff" in which:
        r = run_cutoff_control(split_dir)
        print("cutoff:", json.dumps(r["groups"], indent=1))


if __name__ == "__main__":
    main()
