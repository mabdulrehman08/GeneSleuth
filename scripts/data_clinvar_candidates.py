"""Select ClinVar pathogenic variants to plant as benchmark and demo cases.

Feature: reads ClinVar records in the panel genes (from slice A2's DATA_DIR/work/clinvar_panel.tsv.gz when it exists,
otherwise straight from the public ClinVar GRCh38 VCF in DATA_DIR/raw, downloaded idempotently) and keeps
Pathogenic / Likely_pathogenic SNVs (no Conflicting), >= 1 review star, with a linked condition name.
Writes DATA_DIR/work/clinvar_candidates.json with the main benchmark pool (splice / non-coding SNVs), the demo
picker pool (deep non-coding SNVs) and a report of the named cases (DNM1, MFSD8, PLA2G6).

Usage: python scripts/data_clinvar_candidates.py [--force]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genesleuth import config  # noqa: E402

RAW = config.DATA_DIR / "raw"
WORK = config.DATA_DIR / "work"
CLINVAR_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz"
CLINVAR_VCF = RAW / "clinvar.vcf.gz"
CLINVAR_PANEL_TSV = WORK / "clinvar_panel.tsv.gz"
OUT = WORK / "clinvar_candidates.json"

# The 58 green PanelApp genes from docs/research/03-data.md section 5.
PANEL_GENES = ("SCN1A SCN2A SCN3A SCN8A SCN1B KCNQ2 KCNQ3 KCNT1 KCNA2 KCNB1 KCNMA1 CACNA1A CACNA1E HCN1 GRIN1 GRIN2A GRIN2B "
               "GRIN2D GABRA1 GABRB2 GABRB3 GABRG2 SLC2A1 SLC6A1 SLC12A5 SLC13A5 STXBP1 SYNGAP1 CDKL5 PCDH19 DEPDC5 NPRL2 "
               "NPRL3 TSC1 TSC2 MTOR PRRT2 CHD2 MECP2 FOXG1 ARX DNM1 ALDH7A1 PNPO POLG TBC1D24 SZT2 WWOX UBE3A MEF2C STX1B "
               "PIGA SPTAN1 GNAO1 CSTB EPM2A NHLRC1 PURA").split()
STARS = {"practice guideline": 4, "reviewed by expert panel": 3, "criteria provided, multiple submitters, no conflicts": 2,
         "criteria provided, single submitter": 1}  # 'no assertion criteria provided' and conflicting records are not >= 1 star here
PLP = {"Pathogenic", "Likely_pathogenic", "Pathogenic/Likely_pathogenic"}
CODING_TERMS = {"nonsense", "missense_variant", "synonymous_variant", "stop_gained", "stop_lost", "start_lost", "initiator_codon_variant",
                "frameshift_variant", "inframe_deletion", "inframe_insertion", "protein_altering_variant", "coding_sequence_variant",
                "stop_retained_variant", "start_retained_variant", "incomplete_terminal_codon_variant"}
CANON_SPLICE = {"splice_donor_variant", "splice_acceptor_variant"}
DEEP_OK = {"non-coding_transcript_variant", "intron_variant", "5_prime_UTR_variant", "3_prime_UTR_variant", "splice_region_variant", "non_coding_transcript_variant",
           "non_coding_transcript_exon_variant", "upstream_gene_variant", "downstream_gene_variant", "2KB_upstream_variant",
           "500B_downstream_variant", "genic_upstream_transcript_variant", "genic_downstream_transcript_variant",
           "splice_donor_5th_base_variant", "splice_donor_region_variant", "splice_polypyrimidine_tract_variant"}
NAMED = {  # name: (chrom, pos, ref, alt, gene)
    "DNM1_c.1335+1605G>A": ("chr9", 128225994, "G", "A", "DNM1"),
    "PLA2G6_c.2034+355G>A": ("chr22", 38115172, "C", "T", "PLA2G6"),
}


def ensure_clinvar_vcf() -> Path:
    """Download the ClinVar GRCh38 VCF into DATA_DIR/raw if it is not there yet (idempotent, atomic)."""
    if CLINVAR_VCF.exists() and CLINVAR_VCF.stat().st_size > 100_000_000:
        return CLINVAR_VCF
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = CLINVAR_VCF.with_suffix(".gz.part")
    print(f"downloading {CLINVAR_URL}", flush=True)
    urllib.request.urlretrieve(CLINVAR_URL, tmp)
    os.replace(tmp, CLINVAR_VCF)
    return CLINVAR_VCF


def region_of(terms: list[str]) -> str:
    """Map a record's ClinVar molecular-consequence terms to one schema Region."""
    s = set(terms)
    if s & CODING_TERMS:
        return "coding"
    if s & CANON_SPLICE:
        return "splice"
    if "splice_region_variant" in s or s & {"splice_donor_5th_base_variant", "splice_donor_region_variant", "splice_polypyrimidine_tract_variant"}:
        return "splice"
    if "5_prime_UTR_variant" in s:
        return "utr5"
    if "3_prime_UTR_variant" in s:
        return "utr3"
    if s & {"upstream_gene_variant", "2KB_upstream_variant", "genic_upstream_transcript_variant"}:
        return "promoter"
    if "intron_variant" in s:
        return "intron"
    return "other"


def parse_info(info: str) -> dict[str, str]:
    """Split a VCF INFO string into a dict."""
    out = {}
    for kv in info.split(";"):
        k, _, v = kv.partition("=")
        out[k] = v
    return out


def iter_vcf_records(path: Path):
    """Yield raw ClinVar rows (dicts) from the VCF for every record with a CLNSIG."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        yield from iter_vcf_lines(f)


def iter_vcf_lines(lines):
    """Parse ClinVar VCF lines into row dicts."""
    for line in lines:
        if line.startswith("#"):
            continue
        c = line.rstrip("\n").split("\t", 8)
        info = parse_info(c[7])
        if "CLNSIG" not in info:
            continue
        chrom = c[0] if c[0].startswith("chr") else "chr" + c[0]
        if chrom == "chrMT":
            chrom = "chrM"
        genes = [g.split(":")[0] for g in info.get("GENEINFO", "").split("|") if g]
        mc = [t.split("|")[1] for t in info.get("MC", "").split(",") if "|" in t]
        yield {"variation_id": c[2], "allele_id": info.get("ALLELEID", ""), "chrom": chrom, "pos": int(c[1]), "ref": c[3], "alt": c[4],
               "clnsig": info["CLNSIG"], "review_status": info.get("CLNREVSTAT", "").replace("_", " "), "condition_names": info.get("CLNDN", ""),
               "condition_dbs": info.get("CLNDISDB", ""), "genes": genes, "mc": mc, "clnvc": info.get("CLNVC", "")}


def iter_a2_records(path: Path):
    """Yield the same row dicts from slice A2's clinvar_panel.tsv.gz."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            mc = [t.split("|")[-1] for t in r["mc"].replace(";", ",").split(",") if t]
            yield {"variation_id": r["variation_id"], "allele_id": r["allele_id"], "chrom": r["chrom"], "pos": int(r["pos"]), "ref": r["ref"],
                   "alt": r["alt"], "clnsig": r["clnsig"], "review_status": r["review_status"], "condition_names": r["condition_names"],
                   "condition_dbs": r["condition_dbs"], "genes": [g for g in r["gene"].split("|") if g], "mc": mc,
                   "clnvc": "single_nucleotide_variant" if len(r["ref"]) == 1 and len(r["alt"]) == 1 else ""}


def clean_conditions(names: str, dbs: str) -> tuple[list[str], list[list[str]]]:
    """Split pipe-joined condition names and their database ids; drop 'not_provided' / 'not_specified' entries."""
    ns = names.replace("_", " ").split("|") if names else []
    ds = dbs.split("|") if dbs else []
    keep_n, keep_d = [], []
    for i, n in enumerate(ns):
        if n.strip().lower() in ("not provided", "not specified", "see cases", ""):
            continue
        keep_n.append(n.strip())
        keep_d.append([x for x in (ds[i].split(",") if i < len(ds) else []) if x])
    return keep_n, keep_d


def select(records) -> tuple[list[dict], dict]:
    """Apply the candidate rules; returns (candidates, counters)."""
    panel = set(PANEL_GENES)
    cnt: Counter = Counter()
    out = []
    for r in records:
        gene = next((g for g in r["genes"] if g in panel), None)
        if not gene:
            continue
        cnt["in_panel_gene"] += 1
        if r["clnsig"] not in PLP:
            continue
        cnt["plp_no_conflict"] += 1
        stars = STARS.get(r["review_status"].replace("_", " ").strip(), 0)
        if stars < 1:
            continue
        cnt["stars_ge_1"] += 1
        if not (len(r["ref"]) == 1 and len(r["alt"]) == 1 and r["ref"] in "ACGT" and r["alt"] in "ACGT"):
            continue
        cnt["snv"] += 1
        names, dbs = clean_conditions(r["condition_names"], r["condition_dbs"])
        if not names:
            continue
        cnt["has_condition"] += 1
        region = region_of(r["mc"])
        terms = set(r["mc"])
        is_coding = region == "coding" or bool(terms & CODING_TERMS)
        deep = (not is_coding) and not (terms & CANON_SPLICE) and bool(terms) and terms <= DEEP_OK
        omim = [x.split(":", 1)[1] for ds in dbs for x in ds if x.startswith("OMIM:")]
        out.append({"variant_id": f"{r['chrom']}-{r['pos']}-{r['ref']}-{r['alt']}", "variation_id": r["variation_id"],
                    "allele_id": r["allele_id"], "chrom": r["chrom"], "pos": r["pos"], "ref": r["ref"], "alt": r["alt"], "gene": gene,
                    "region": region, "mc": r["mc"], "clnsig": r["clnsig"], "review_status": r["review_status"], "stars": stars,
                    "condition": names[0], "conditions": names, "condition_dbs": dbs, "omim_ids": omim,
                    "noncoding": not is_coding, "deep_noncoding": deep})
    return out, dict(cnt)


def named_case_report(vcf_path: Path | None, candidates: list[dict]) -> dict:
    """Check whether the named cases exist in ClinVar / the candidate pool and in the panel."""
    rep = {}
    by_id = {c["variant_id"]: c for c in candidates}
    wanted = {(v[0], v[1]): k for k, v in NAMED.items()}
    found: dict[str, dict] = {}
    if vcf_path and vcf_path.exists():
        keys = {(c.removeprefix("chr"), str(p)): k for (c, p), k in wanted.items()}
        with gzip.open(vcf_path, "rt", encoding="utf-8") as f:  # cheap chrom/pos pre-check before parsing INFO
            for line in f:
                if line[0] == "#":
                    continue
                c = line.split("\t", 2)
                k = keys.get((c[0], c[1]))
                if k:
                    for row in iter_vcf_lines([line]):
                        found[k] = {kk: row[kk] for kk in ("variation_id", "chrom", "pos", "ref", "alt", "clnsig", "review_status", "condition_names", "genes", "mc")}
    for name, (chrom, pos, ref, alt, gene) in NAMED.items():
        vid = f"{chrom}-{pos}-{ref}-{alt}"
        rep[name] = {"expected": vid, "gene_in_panel": gene in PANEL_GENES, "in_clinvar_vcf": found.get(name),
                     "in_candidate_pool": vid in by_id}
    rep["MFSD8_c.999-556C>G"] = {"gene_in_panel": "MFSD8" in PANEL_GENES, "status": "UNVERIFIED (coordinate to be derived via VariantValidator)"}
    return rep


def main(argv: list[str] | None = None) -> None:
    """CLI entry point (callable from scripts/data_setup.py)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute even if the output exists")
    ap.add_argument("--vcf-only", action="store_true", help="ignore A2's table and parse the VCF")
    a = ap.parse_args(argv)
    if OUT.exists() and not a.force:
        print(f"{OUT} exists; use --force to recompute")
        return
    vcf = None
    try:
        vcf = ensure_clinvar_vcf()
    except Exception as e:  # network failure is fine when A2's table exists
        print("clinvar vcf unavailable:", e)
    if CLINVAR_PANEL_TSV.exists() and not a.vcf_only:
        print("source: A2 clinvar_panel.tsv.gz")
        source, recs = "clinvar_panel.tsv.gz", iter_a2_records(CLINVAR_PANEL_TSV)
    else:
        print("source: ClinVar VCF", vcf)
        source, recs = "clinvar.vcf.gz", iter_vcf_records(vcf)
    cands, cnt = select(recs)
    pool = [c for c in cands if c["noncoding"]]
    deep = [c for c in cands if c["deep_noncoding"]]
    by_region = Counter(c["region"] for c in cands)
    pool_by_region = Counter(c["region"] for c in pool)
    deep_by_region = Counter(c["region"] for c in deep)
    named = named_case_report(vcf, cands)
    report = {"source": source, "counters": cnt, "n_candidates": len(cands), "n_noncoding_pool": len(pool), "n_deep_noncoding": len(deep),
              "by_region_all": dict(by_region), "by_region_noncoding_pool": dict(pool_by_region), "by_region_deep": dict(deep_by_region),
              "noncoding_fraction": round(len(pool) / max(1, len(cands)), 3),
              "top_genes_noncoding_pool": Counter(c["gene"] for c in pool).most_common(10),
              "top_genes_deep": Counter(c["gene"] for c in deep).most_common(10), "named_cases": named}
    WORK.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.part")
    tmp.write_text(json.dumps({"report": report, "candidates": cands}, indent=1))
    os.replace(tmp, OUT)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
