"""Benchmark report generator.

Feature: reads bench/results/<split>/<mode>/*.json (written by bench/run.py) and writes next to them
  * report.md    headline table, breakdowns, resources, failure counts, leakage controls, named cases
  * chart.png    1600x900 projector chart: hit@5 per mode (left) and coding vs non-coding (right)
  * failures.md  every full-mode miss with its pre-registered failure category and evidence
Optionally (--fill-doc) copies the tables into the RESULTS block of docs/BENCHMARK.md.

Usage:  python -m bench.report --split test [--results-dir bench/results] [--fill-doc]

The report prints a STUB banner when any result file carries meta.stub, so dry-run output can
never be mistaken for a real result.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from bench import metrics as M
from genesleuth import config

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "bench" / "results"
DOC = ROOT / "docs" / "BENCHMARK.md"

MODE_ORDER = ["gemini_only", "atlas_only", "alphagenome_only", "fixed_recipe", "triage_only", "full"]
MODE_LABEL = {
    "full": "GeneSleuth (full agent)", "gemini_only": "Gemini 4, no tools", "atlas_only": "Atlas AVI only",
    "alphagenome_only": "AlphaGenome only (brain)", "fixed_recipe": "Fixed recipe (no LLM)", "triage_only": "Decision 1 triage only",
}
MODE_SHORT = {"full": "GeneSleuth\nfull agent", "gemini_only": "Gemini 4\nno tools", "atlas_only": "Atlas AVI\nonly",
              "alphagenome_only": "AlphaGenome\nonly", "fixed_recipe": "Fixed\nrecipe", "triage_only": "Decision 1\ntriage"}
FAILURE_CATEGORIES = ["never_inspected", "wrong_tissue", "weak_alphagenome_effect", "phenotype_mismatch", "outranked_by_coding",
                      "checker_rejected_true_claim", "unscorable_variant_type", "missed_second_hit_or_common_allele", "error"]
UNCLASSIFIED = "unclassified"  # extra bucket, used only when no pre-registered category's evidence applies
COMMON_AF = 0.001
BRAIN_WORDS = ("brain", "cortex", "neuron", "hippocamp", "cerebell", "glutamatergic", "gabaergic", "astrocyte",
               "oligodendro", "microglia", "striatum", "thalamus", "hypothalamus", "amygdala")


# ----------------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------------
def pct(p: dict) -> str:
    """'42.9% (3/7) [15.8-75.1]' for a prop dict."""
    if not p or p.get("n", 0) == 0:
        return "n/a"
    return f"{100 * p['p']:.0f}% ({p['k']}/{p['n']}) [{100 * p['lo']:.0f}-{100 * p['hi']:.0f}]"


def num(x: Optional[float], nd: int = 1) -> str:
    return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) and not float(x).is_integer() else f"{int(x)}")


def ordered_modes(modes) -> list[str]:
    return [m for m in MODE_ORDER if m in modes] + sorted(m for m in modes if m not in MODE_ORDER)


# ----------------------------------------------------------------------------
# Failure classification (pre-registered categories)
# ----------------------------------------------------------------------------
def _is_ag(tc) -> bool:
    return "alphagenome" in tc.tool.lower() or tc.tool in ("score_variant", "plot_variant", "atlas_scores")


def _tissue(tc) -> Optional[str]:
    for k in ("tissue", "tissue_ontology_id", "tissue_id", "condition"):
        if isinstance(tc.args.get(k), str):
            return tc.args[k]
    t = tc.result.get("tissue") if isinstance(tc.result, dict) else None
    return t if isinstance(t, str) else None


def _is_brain(tc) -> bool:
    t = (_tissue(tc) or "")
    name = str((tc.result or {}).get("tissue_name", "")) if isinstance(tc.result, dict) else ""
    return t == config.BRAIN_TISSUE or any(w in (t + " " + name).lower() for w in BRAIN_WORDS)


def _effect(tc) -> Optional[float]:
    v = (tc.result or {}).get("max_abs_effect") if isinstance(tc.result, dict) else None
    return float(v) if isinstance(v, (int, float)) else None


def _is_snv(variant_id: str) -> bool:
    parts = variant_id.split("-")
    return len(parts) == 4 and len(parts[2]) == 1 and len(parts[3]) == 1


def classify_failure(rec: M.CaseRecord, weak_effect_abs: float = 0.05) -> tuple[str, dict]:
    """Return (category, evidence) for a full-mode miss. Precedence is the order below.

    Rules (all computed from the result file; no peeking at anything the agent did not see):
      error                        status == error
      unscorable_variant_type      hidden variant is not a single-base substitution
      missed_second_hit_or_common_allele   a population_frequency call on the hidden variant returned af >= 0.001
      checker_rejected_true_claim  the hidden variant appears with an 'unsupported' verdict
      never_inspected              no tool call mentions the hidden variant id
      wrong_tissue                 inspected with AlphaGenome, but never in a brain-like tissue
      weak_alphagenome_effect      brain AlphaGenome effect below the median of the agent's other calls (or < weak_effect_abs
                                   when it has no other calls)
      phenotype_mismatch           phenotype_match for the hidden gene scored < 0.3
      outranked_by_coding          hidden is non-coding and at least 2 of the agent's top 3 are coding
      unclassified                 none of the above (extra bucket, reported as such)
    """
    hid = rec.hidden_id
    res = rec.result
    ev: dict = {}
    if res is None or res.status == "error":
        return "error", {"error": (res.error if res else rec.load_error)}
    if not _is_snv(hid):
        return "unscorable_variant_type", {"variant": hid}
    touching = [tc for tc in res.tool_calls if hid in json.dumps(tc.args, default=str)]
    ev["n_calls_on_hidden"] = len(touching)
    for tc in touching:
        if tc.tool == "population_frequency" and isinstance(tc.result, dict):
            af = tc.result.get("af")
            if isinstance(af, (int, float)) and af >= COMMON_AF:
                ev["af"] = af
                return "missed_second_hit_or_common_allele", ev
    for s in res.ranked:
        if s.variant.variant_id == hid and any(v.verdict == "unsupported" for v in s.verdicts):
            return "checker_rejected_true_claim", ev
    if not touching:
        return "never_inspected", ev
    ag = [tc for tc in touching if _is_ag(tc)]
    ev["tissues"] = sorted({t for t in (_tissue(tc) for tc in touching) if t})
    if ag and not any(_is_brain(tc) for tc in ag):
        return "wrong_tissue", ev
    brain = [tc for tc in ag if _is_brain(tc)]
    if brain:
        eff = max((e for e in (_effect(tc) for tc in brain) if e is not None), default=None)
        others = [e for e in (_effect(tc) for tc in res.tool_calls if _is_ag(tc) and tc not in touching) if e is not None]
        ev["hidden_effect"] = eff
        if eff is not None:
            ref = sorted(others)[len(others) // 2] if others else weak_effect_abs
            ev["reference_effect"] = ref
            if eff < ref:
                return "weak_alphagenome_effect", ev
    for tc in touching:
        if tc.tool == "phenotype_match" and isinstance(tc.result, dict):
            sc = tc.result.get("score")
            if isinstance(sc, (int, float)) and sc < 0.3:
                ev["phenotype_score"] = sc
                return "phenotype_mismatch", ev
    top3 = sorted(res.ranked, key=lambda r: r.rank)[:3]
    if rec.region_type == "non-coding" and sum(1 for s in top3 if s.variant.region == "coding") >= 2:
        return "outranked_by_coding", ev
    return UNCLASSIFIED, ev


def full_misses(by_mode: dict) -> list[M.CaseRecord]:
    return [r for r in by_mode.get("full", []) if r.rank is None or r.rank >= M.MISS_RANK]


def write_failures(by_mode: dict, out: Path) -> Counter:
    """Write failures.md and return the category counts."""
    misses = full_misses(by_mode)
    counts: Counter = Counter()
    lines = ["# Failures of the full agent", "",
             "Every full-mode case whose hidden variant did not reach the top 10, with one pre-registered category "
             "(rules in `bench/report.py:classify_failure`). Categories are assigned by code from the saved tool calls, "
             "not by reading the outcome and choosing a story.", ""]
    if by_mode and any(r.meta.get("stub") for rs in by_mode.values() for r in rs):
        lines.insert(2, "> **STUB RESULTS (dry run). These are fabricated by `bench/_stub_agent.py`, not real runs.**\n")
    if not misses:
        lines.append("No full-mode misses.")
    blocks = []
    for r in misses:
        cat, ev = classify_failure(r)
        counts[cat] += 1
        res = r.result
        top3 = sorted(res.ranked, key=lambda s: s.rank)[:3] if res else []
        tissues = sorted({t for t in (_tissue(tc) for tc in (res.tool_calls if res else [])) if t})
        looked = ev.get("n_calls_on_hidden", 0) > 0
        blocks += [f"## {r.case_id}: {r.truth.gene} {r.truth.hidden_variant_id} ({r.truth.region})", "",
                   f"- condition: {r.truth.condition}",
                   f"- hidden variant rank: {r.rank if r.rank else 'not in ranked list'}",
                   f"- category: **{cat}**",
                   f"- agent looked at the hidden variant: {'yes (%d tool calls)' % ev['n_calls_on_hidden'] if looked else 'no'}",
                   f"- tissues used in the run: {', '.join(tissues) if tissues else 'none'}",
                   f"- evidence: `{json.dumps(ev, default=str)}`",
                   "- agent top 3: " + ("; ".join(f"{s.variant.gene} {s.variant.variant_id} ({s.variant.region})" for s in top3) or "none"),
                   f"- letter: {r.letter_type}", ""]
    if counts:
        lines += ["| category | count |", "|---|---|"] + [f"| {c} | {counts.get(c, 0)} |" for c in FAILURE_CATEGORIES + [UNCLASSIFIED]
                                                       if counts.get(c, 0) or c != UNCLASSIFIED]
        lines.append("")
    out.write_text("\n".join(lines + blocks), encoding="utf-8")
    return counts


# ----------------------------------------------------------------------------
# Chart
# ----------------------------------------------------------------------------
def write_chart(analysis: dict, n_cases: int, out: Path, stub: bool = False) -> None:
    """1600x900 PNG. Left: hit@5 per mode with Wilson error bars. Right: hit@5 coding vs non-coding."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    modes = [m for m in ordered_modes(analysis) if m != "triage_only" or m in analysis]
    strong, gray_dark, gray_light, ink = "#0F766E", "#6B7280", "#B8BDC6", "#1F2937"
    plt.rcParams.update({"font.size": 20, "axes.titlesize": 24, "axes.labelsize": 22, "font.family": "DejaVu Sans"})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 9), dpi=100, gridspec_kw={"width_ratios": [1, 1.25]})
    fig.patch.set_facecolor("white")

    def err(p):  # asymmetric Wilson bars in percent
        return [[max(0.0, 100 * (p["p"] - p["lo"]))], [max(0.0, 100 * (p["hi"] - p["p"]))]]

    labels = [MODE_SHORT.get(m, m) for m in modes]
    xs = range(len(modes))
    for i, m in enumerate(modes):
        p = analysis[m]["overall"]["hit@5"]
        val = 0 if p["n"] == 0 else 100 * p["p"]
        ax1.bar(i, val, color=strong if m == "full" else gray_dark, width=0.62)
        if p["n"]:
            ax1.errorbar(i, val, yerr=err(p), color=ink, capsize=8, lw=2.5, capthick=2.5)
            ax1.text(i, min(100 * p["hi"] + 3, 103), f"{val:.0f}%", ha="center", va="bottom", fontsize=22, fontweight="bold", color=ink)
    ax1.set_xticks(list(xs))
    ax1.set_xticklabels(labels, fontsize=13)
    ax1.set_ylim(0, 112)
    ax1.set_yticks([0, 25, 50, 75, 100])
    ax1.set_ylabel("Hidden variant in top 5 (%)")
    ax1.set_title("hit@5, all cases", loc="left")

    w = 0.38
    for i, m in enumerate(modes):
        for j, g in enumerate(["coding", "non-coding"]):
            s = analysis[m]["by"]["region_type"].get(g)
            if not s:
                continue
            p = s["hit@5"]
            val = 100 * p["p"] if p["n"] else 0
            base = strong if m == "full" else (gray_dark if j == 0 else gray_light)
            x = i + (j - 0.5) * w
            ax2.bar(x, val, width=w * 0.94, color=base if m != "full" else (strong if j == 0 else "#5EAAA3"))
            if p["n"]:
                ax2.errorbar(x, val, yerr=err(p), color=ink, capsize=5, lw=2, capthick=2)
    from matplotlib.patches import Patch
    ax2.legend(handles=[Patch(color=gray_dark, label="coding"), Patch(color=gray_light, label="non-coding")], fontsize=16, frameon=False,
               loc="upper left")
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels(labels, fontsize=15)
    ax2.set_ylim(0, 112)
    ax2.set_yticks([0, 25, 50, 75, 100])
    ax2.set_title("hit@5, coding vs non-coding", loc="left")
    for ax in (ax1, ax2):
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.grid(axis="y", color="#E5E7EB", lw=1)
        ax.set_axisbelow(True)
    title = f"GeneSleuth vs baselines on {n_cases} unseen cases"
    fig.suptitle(title, fontsize=30, fontweight="bold", color=ink, x=0.02, ha="left")
    if stub:
        fig.text(0.98, 0.93, "STUB DATA - DRY RUN", fontsize=22, fontweight="bold", color="#B91C1C", ha="right")
    fig.text(0.02, 0.012, "Error bars: 95% Wilson interval. Hidden variant planted in a real 1000 Genomes background; ClinVar lookup off.",
             fontsize=14, color=gray_dark)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(out, dpi=100)
    plt.close(fig)


# ----------------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------------
def _headline_table(analysis: dict) -> list[str]:
    rows = ["| Mode | n | hit@1 | hit@5 | hit@10 | MRR@10 | median rank | filter recall |", "|---|---|---|---|---|---|---|---|"]
    for m in ordered_modes(analysis):
        s = analysis[m]["overall"]
        mr = num(s["median_rank"]) + ("+" if s["median_rank_is_lower_bound"] else "")
        rows.append(f"| {MODE_LABEL.get(m, m)} | {s['n']} | {pct(s['hit@1'])} | {pct(s['hit@5'])} | {pct(s['hit@10'])} | "
                    f"{s['mrr@10']:.2f} | {mr} | {pct(s['filter_recall'])} |")
    return rows


def _resource_table(analysis: dict, cost: dict) -> list[str]:
    rows = ["| Mode | median AlphaGenome calls | median tool calls | median time (s) | claims checked / rejected | errors | median cost / case (USD) |",
            "|---|---|---|---|---|---|---|"]
    for m in ordered_modes(analysis):
        s = analysis[m]["overall"]
        c = cost.get(m, {})
        mc = c.get("median_cost_usd")
        rows.append(f"| {MODE_LABEL.get(m, m)} | {num(s['median_ag_calls'])} | {num(s['median_tool_calls'])} | {num(s['median_time_s'])} | "
                    f"{s['claims_checked_total']} / {s['claims_rejected_total']} | {s['n_error']} | "
                    f"{'n/a' if not mc else '%.2f' % mc}{'~' if c.get('approximate_attribution') and mc else ''} |")
    return rows


def _breakdown_tables(analysis: dict) -> list[str]:
    out = []
    for key, title in (("region_type", "Region type (coding vs non-coding)"), ("letter_type", "Letter type (clean vs scanned)")):
        groups = sorted({g for m in analysis for g in analysis[m]["by"][key]})
        out += [f"#### {title}", "", "| Mode | " + " | ".join(f"{g} hit@5" for g in groups) + " |", "|---|" + "---|" * len(groups)]
        for m in ordered_modes(analysis):
            cells = []
            for g in groups:
                s = analysis[m]["by"][key].get(g)
                cells.append(pct(s["hit@5"]) if s else "n/a")
            out.append(f"| {MODE_LABEL.get(m, m)} | " + " | ".join(cells) + " |")
        out.append("")
    return out


def _controls_section(split_dir: Path) -> list[str]:
    p = split_dir / "controls.json"
    if not p.exists():
        return ["_No leakage-control results yet._", ""]
    c = json.loads(p.read_text(encoding="utf-8"))
    out = []
    if c.get("citation"):
        x = c["citation"]
        out += [f"- **Citation control (gemini_only names a publication for its top pick):** {x.get('n_correct', 'n/a')} of "
                f"{x.get('n_asked', 'n/a')} correct ({x.get('note', '')}). A correct citation counts as memorization."]
    if c.get("shuffle"):
        x = c["shuffle"]
        out += [f"- **Coordinate-shuffle control (gemini_only, {x.get('n', 'n/a')} cases):** true gene still ranked first in "
                f"{x.get('gene_rank1', 'n/a')}, in top 5 in {x.get('gene_top5', 'n/a')}; shuffled variant itself in top 10 in "
                f"{x.get('variant_top10', 'n/a')}. Gene recall without reading the variant means phenotype recall, not variant reading."]
    if c.get("cutoff"):
        x = c["cutoff"]
        out += [f"- **Pre/post-cutoff subgroup** (ClinVar snapshot {x.get('snapshot', 'n/a')}; Gemini 4 cutoff "
                f"{x.get('cutoff_note', 'unknown, snapshot assumed')}): " + "; ".join(f"{k}: {v}" for k, v in x.get("groups", {}).items())]
    return out + [""]


def _named_section(results_dir: Path) -> list[str]:
    d = results_dir / "named"
    by_mode = M.load_split(d)
    if not by_mode:
        return ["_No named-case runs yet (DNM1, MFSD8, PLA2G6 are reported separately and never pooled into TEST)._", ""]
    modes = ordered_modes(by_mode)
    rows = ["| Case | Gene | Region | " + " | ".join(MODE_LABEL.get(m, m) for m in modes) + " |", "|---|---|---|" + "---|" * len(modes)]
    ids = sorted({r.case_id for rs in by_mode.values() for r in rs})
    for cid in ids:
        recs = {m: next((r for r in by_mode[m] if r.case_id == cid), None) for m in modes}
        any_r = next(r for r in recs.values() if r)
        rows.append(f"| {cid} | {any_r.truth.gene} | {any_r.truth.region} | " +
                    " | ".join("n/a" if not r else (f"rank {r.rank}" if r.rank else "miss") for r in recs.values()) + " |")
    return rows + [""]


def build_report(split: str, results_dir: Path = RESULTS, calls_path: Optional[Path] = None) -> dict:
    """Write report.md, chart.png and failures.md for results_dir/split. Returns the pieces for reuse (BENCHMARK.md)."""
    split_dir = results_dir / split
    by_mode = M.load_split(split_dir)
    if not by_mode:
        raise SystemExit(f"no results under {split_dir}")
    analysis = M.analyze(by_mode)
    calls = M.load_calls(calls_path or (config.CACHE_DIR / "calls.jsonl"))
    cost = {m: M.cost_per_case(rs, calls) for m, rs in by_mode.items()}
    n_cases = max(len(rs) for rs in by_mode.values())
    common = M.common_case_ids(by_mode)
    stub = any(a["overall"]["stub"] for a in analysis.values())
    standins = sorted({s for a in analysis.values() for s in a["overall"]["standin"]})

    counts = write_failures(by_mode, split_dir / "failures.md")
    write_chart(analysis, n_cases, split_dir / "chart.png", stub=stub)

    L: list[str] = []
    if stub:
        L += ["> **STUB RESULTS (dry run).** Produced by `bench/_stub_agent.py` on fake cases. Not a benchmark.", ""]
    if standins:
        L += [f"> **Stand-ins used:** {', '.join(standins)}. Numbers for the affected arms are not final.", ""]
    L += [f"# Benchmark report: {split}", "",
          f"{n_cases} cases; {len(common)} case(s) have results in every mode. Hit rates show `% (hits/n) [95% Wilson interval]`. "
          f"With n this small the intervals are wide; read the interval, not the point estimate. Errored runs count as misses.", "",
          "![chart](chart.png)", "", "## Headline", ""] + _headline_table(analysis) + [
          "", "Rank 11+ or missing counts as a miss. MRR is MRR@10. Median rank treats a miss as 11 (`+` = at least that).", "",
          "## Resources", ""] + _resource_table(analysis, cost) + [
          "", "Cost is read from `calls.jsonl` (Gemini calls only; AlphaGenome calls are not billed per call here). "
              "`~` = attributed by time window, so approximate.", "",
          "## Breakdowns (hit@5)", ""] + _breakdown_tables(analysis) + ["## Full-agent failure categories", ""]
    if counts:
        L += ["| category | count |", "|---|---|"] + [f"| {c} | {n} |" for c, n in counts.most_common()] + ["", "Details in `failures.md`.", ""]
    else:
        L += ["No full-mode misses." if "full" in by_mode else "No full-mode run.", ""]
    L += ["## Leakage controls", ""] + _controls_section(split_dir) + ["## Named cases (not pooled)", ""] + _named_section(results_dir)
    (split_dir / "report.md").write_text("\n".join(L), encoding="utf-8")
    return {"analysis": analysis, "cost": cost, "counts": counts, "n_cases": n_cases, "tables": L, "stub": stub}


START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def fill_doc(split: str, report: dict, doc: Path = DOC) -> bool:
    """Replace the RESULTS block of docs/BENCHMARK.md with the tables from the report (TEST split only)."""
    if not doc.exists():
        return False
    text = doc.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    body = "\n".join(l for l in report["tables"] if not l.startswith("![chart]"))
    body = body.replace("# Benchmark report:", "### Results:")
    new = f"{START}\n\n![GeneSleuth vs baselines](../bench/results/{split}/chart.png)\n\n{body}\n\n{END}"
    text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _m: new, text, flags=re.S)
    doc.write_text(text, encoding="utf-8")
    return True


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", required=True)
    ap.add_argument("--results-dir", default=str(RESULTS))
    ap.add_argument("--calls", default=None, help="path to calls.jsonl (default DATA_DIR/cache/calls.jsonl)")
    ap.add_argument("--fill-doc", action="store_true", help="copy the tables into docs/BENCHMARK.md")
    a = ap.parse_args(argv)
    rep = build_report(a.split, Path(a.results_dir), Path(a.calls) if a.calls else None)
    print(f"wrote report.md, chart.png, failures.md under {Path(a.results_dir) / a.split}")
    if a.fill_doc:
        if rep["stub"]:
            raise SystemExit("refusing to fill docs/BENCHMARK.md from stub results")
        print("docs/BENCHMARK.md updated" if fill_doc(a.split, rep) else "docs/BENCHMARK.md has no RESULTS markers")


if __name__ == "__main__":
    main()
