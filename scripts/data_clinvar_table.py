"""Build DATA_DIR/work/clinvar_panel.tsv.gz: every ClinVar record inside the panel regions.

Feature: local ClinVar table (GRCh38, chr-prefixed) used by
  * genesleuth/lookups/clinvar.py (second-guard clinvar_lookup, DISABLED for bench/demo cases),
  * slice A3 (candidate selection) and slice A4 (fixed recipe: gene-level "has Pathogenic epilepsy record").
Source: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz (whole file ~200 MB, saved to
DATA_DIR/raw/clinvar.vcf.gz; idempotent, and waits for another slice's partial download of the same file).

Output columns (tab separated, gzip, with header):
  variant_id variation_id allele_id chrom pos ref alt clnsig review_status stars condition_names condition_dbs gene mc
  - variant_id = "chr2-165991234-A-G" (chr prefix, 1-based); variation_id = VCF ID column; allele_id = INFO/ALLELEID
  - clnsig = INFO/CLNSIG as is (e.g. Pathogenic, Likely_pathogenic, Pathogenic/Likely_pathogenic, Conflicting_...)
  - review_status = INFO/CLNREVSTAT with '_' -> ' ' ; stars: practice guideline 4, expert panel 3,
    multiple submitters no conflicts 2, single submitter or conflicting 1, otherwise 0
  - condition_names = INFO/CLNDN ('|' separated, '_' -> ' '); condition_dbs = INFO/CLNDISDB (raw, e.g. MONDO:..,MedGen:..,OMIM:..|...)
  - gene = gene symbols from INFO/GENEINFO joined by '|'; mc = INFO/MC raw (SO:id|term,...)
Regions: DATA_DIR/work/panel_regions.tsv (written by slice A1) if present, otherwise the 58-gene list of
docs/research/03-data.md section 5 with MANE v1.5 coordinates +/- 10 kb (fallback; see --regions-fallback).

Also copies the table to ROOT/assets/clinvar_panel.tsv.gz (committed bundle).
Use: python scripts/data_clinvar_table.py [--force] [--wait-regions SECONDS] [--no-bundle]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import io
import os
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from genesleuth.lookups._common import assets_dir, find_table, raw_dir, work_dir, write_atomic  # noqa: E402

CLINVAR_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz"
MANE_URL = "https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/MANE.GRCh38.v1.5.summary.txt.gz"
PANEL_GENES = ("SCN1A SCN2A SCN3A SCN8A SCN1B KCNQ2 KCNQ3 KCNT1 KCNA2 KCNB1 KCNMA1 CACNA1A CACNA1E HCN1 GRIN1 GRIN2A "
               "GRIN2B GRIN2D GABRA1 GABRB2 GABRB3 GABRG2 SLC2A1 SLC6A1 SLC12A5 SLC13A5 STXBP1 SYNGAP1 CDKL5 PCDH19 "
               "DEPDC5 NPRL2 NPRL3 TSC1 TSC2 MTOR PRRT2 CHD2 MECP2 FOXG1 ARX DNM1 ALDH7A1 PNPO POLG TBC1D24 SZT2 WWOX "
               "UBE3A MEF2C STX1B PIGA SPTAN1 GNAO1 CSTB EPM2A NHLRC1 PURA").split()
FLANK = 10_000
HEADER = ["variant_id", "variation_id", "allele_id", "chrom", "pos", "ref", "alt", "clnsig", "review_status", "stars",
          "condition_names", "condition_dbs", "gene", "mc"]


def stars_from_status(rs: str) -> int:
    """Map a CLNREVSTAT string (underscores, comma separated) to the 0-4 star rating."""
    s = rs.lower()
    if "practice_guideline" in s:
        return 4
    if "reviewed_by_expert_panel" in s:
        return 3
    if "criteria_provided" in s:
        if "multiple_submitters" in s and "no_conflicts" in s:
            return 2
        return 1  # single submitter, or conflicting classifications (1 star in ClinVar)
    return 0


def ensure_clinvar(force: bool = False) -> Path:
    """Return raw/clinvar.vcf.gz, downloading it if needed (waits for a concurrent partial download by another slice)."""
    dest = raw_dir() / "clinvar.vcf.gz"
    if dest.exists() and dest.stat().st_size > 100_000_000 and not force:
        print(f"[skip] clinvar.vcf.gz present ({dest.stat().st_size:,} bytes)")
        return dest
    other = raw_dir() / "clinvar.vcf.gz.part"
    t_wait = time.time()
    while other.exists() and time.time() - other.stat().st_mtime < 45 and time.time() - t_wait < 900 and not force:
        print("[wait] another slice is downloading clinvar.vcf.gz ...")
        time.sleep(10)
        if dest.exists() and dest.stat().st_size > 100_000_000:
            return dest
    if dest.exists() and dest.stat().st_size > 100_000_000 and not force:
        return dest
    tmp = raw_dir() / "clinvar.vcf.gz.a2part"
    t0 = time.time()
    with requests.get(CLINVAR_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    os.replace(tmp, dest)
    print(f"[download] clinvar.vcf.gz {dest.stat().st_size:,} bytes in {time.time() - t0:.1f}s")
    return dest


def regions_from_mane() -> list[tuple[str, int, int, str]]:
    """Fallback regions: MANE summary coordinates +/- 10 kb for the 58 panel genes (chr-prefixed)."""
    p = raw_dir() / "MANE.GRCh38.v1.5.summary.txt.gz"
    if not p.exists():
        r = requests.get(MANE_URL, timeout=120)
        r.raise_for_status()
        write_atomic(p, r.content)
    out = []
    want = set(PANEL_GENES)
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        for row in rd:
            sym = row.get("symbol")
            if sym in want and row.get("MANE_status", "").startswith("MANE Select"):
                acc = row["GRCh38_chr"]  # NC_0000NN.x
                n = int(acc.split("_")[1].split(".")[0])
                chrom = {23: "chrX", 24: "chrY"}.get(n, f"chr{n}")
                out.append((chrom, int(row["chr_start"]) - FLANK, int(row["chr_end"]) + FLANK, sym))
    print(f"[regions] MANE fallback: {len(out)} of {len(want)} genes")
    return out


def load_regions(wait: int = 0) -> list[tuple[str, int, int, str]]:
    """Regions (chrom, start, end, gene) from work/panel_regions.tsv (A1), polling up to `wait` s, else MANE fallback."""
    p = work_dir() / "panel_regions.tsv"
    t0 = time.time()
    while not p.exists() and time.time() - t0 < wait:
        time.sleep(5)
    if p.exists():
        out = []
        with open(p, encoding="utf-8") as fh:
            rd = csv.DictReader(fh, delimiter="\t")
            for row in rd:
                out.append((row["chrom"], int(row["start"]), int(row["end"]), row["gene"]))
        print(f"[regions] panel_regions.tsv: {len(out)} regions")
        return out
    return regions_from_mane()


class RegionIndex:
    """Sorted, merged intervals per chromosome for fast point-in-region tests."""

    def __init__(self, regions):
        by: dict[str, list[tuple[int, int]]] = {}
        for c, s, e, _g in regions:
            by.setdefault(c, []).append((s, e))
        self.starts: dict[str, list[int]] = {}
        self.ends: dict[str, list[int]] = {}
        for c, iv in by.items():
            iv.sort()
            merged = []
            for s, e in iv:
                if merged and s <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))
            self.starts[c] = [m[0] for m in merged]
            self.ends[c] = [m[1] for m in merged]

    def contains(self, chrom: str, pos: int) -> bool:
        st = self.starts.get(chrom)
        if not st:
            return False
        i = bisect.bisect_right(st, pos) - 1
        return i >= 0 and pos <= self.ends[chrom][i]


def parse_info(info: str) -> dict:
    """Parse the INFO keys we need (values are percent-decoded)."""
    d = {}
    for kv in info.split(";"):
        k, _, v = kv.partition("=")
        if k in ("ALLELEID", "CLNSIG", "CLNREVSTAT", "CLNDN", "CLNDISDB", "MC", "GENEINFO"):
            d[k] = unquote(v)
    return d


def build(vcf: Path, regions) -> int:
    """Stream the VCF and write work/clinvar_panel.tsv.gz atomically; returns the number of records written."""
    idx = RegionIndex(regions)
    buf = io.BytesIO()
    n = total = 0
    t0 = time.time()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6, mtime=0) as gz, \
            gzip.open(vcf, "rt", encoding="utf-8") as fh:
        gz.write(("\t".join(HEADER) + "\n").encode())
        for line in fh:
            if line.startswith("#"):
                continue
            total += 1
            p = line.split("\t", 8)
            if len(p) < 8:
                continue
            c = p[0]
            chrom = "chrM" if c in ("MT", "M") else "chr" + c
            pos = int(p[1])
            if not idx.contains(chrom, pos):
                continue
            ref, alt = p[3], p[4]
            info = parse_info(p[7].rstrip("\n"))
            rs = info.get("CLNREVSTAT", "")
            genes = "|".join(g.split(":")[0] for g in info.get("GENEINFO", "").split("|") if g)
            row = [f"{chrom}-{pos}-{ref}-{alt}", p[2], info.get("ALLELEID", ""), chrom, str(pos), ref, alt,
                   info.get("CLNSIG", ""), rs.replace("_", " "), str(stars_from_status(rs)),
                   info.get("CLNDN", "").replace("_", " "), info.get("CLNDISDB", ""), genes, info.get("MC", "")]
            gz.write(("\t".join(x.replace("\t", " ") for x in row) + "\n").encode())
            n += 1
    write_atomic(work_dir() / "clinvar_panel.tsv.gz", buf.getvalue())
    print(f"[build] {n} panel records out of {total} ClinVar records in {time.time() - t0:.1f}s")
    return n


def bundle() -> None:
    """Copy work/clinvar_panel.tsv.gz to ROOT/assets/ (already gzip; ~3 MB) so the other computer can use it."""
    src = work_dir() / "clinvar_panel.tsv.gz"
    if src.exists():
        write_atomic(assets_dir() / "clinvar_panel.tsv.gz", src.read_bytes())
        print("[bundle] assets/clinvar_panel.tsv.gz")


def main(argv: list[str] | None = None) -> None:
    """Idempotent entry point (also called by scripts/data_setup.py): skip when the table exists in assets/ or work/."""
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    ap.add_argument("--force", action="store_true", help="re-download and rebuild")
    ap.add_argument("--wait-regions", type=int, default=0, help="seconds to poll for work/panel_regions.tsv before using the MANE fallback")
    ap.add_argument("--no-bundle", action="store_true", help="do not copy into ROOT/assets/")
    a = ap.parse_args(argv)
    if not a.force and find_table("clinvar_panel.tsv.gz"):
        print("[skip] clinvar_panel.tsv.gz already present (assets/ or DATA_DIR/work)")
        return
    vcf = ensure_clinvar(a.force)
    regions = load_regions(a.wait_regions)
    build(vcf, regions)
    if not a.no_bundle:
        bundle()


if __name__ == "__main__":
    main()
