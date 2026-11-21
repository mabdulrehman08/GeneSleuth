"""Gene panel regions and MANE transcript features (feature: panel geometry).

Builds, from public MANE v1.5 files only, everything the rest of the data pipeline
needs to know about the 58-gene genetic-epilepsy panel:

  DATA_DIR/work/panel_regions.tsv      gene chrom start end strand tss ensembl_gene
                                       (chr-prefixed, GRCh38, 1-based inclusive, +/-10 kb flanks applied)
  DATA_DIR/work/panel_regions.bed      0-based BED for bcftools / tabix (chrom start end gene)
  DATA_DIR/work/panel_regions_bcftools.tsv   1-based "chrom<TAB>start<TAB>end" for `bcftools -R`
  DATA_DIR/work/mane_features.tsv.gz   exon / CDS / UTR / start+stop codon features of the panel's MANE
                                       Select transcripts (for region classification and splice distance)

Use cases:
    from genesleuth.data.panel import load_panel_regions, load_features
    regions = load_panel_regions()      # list[dict]
    gene = gene_at("chr2", 166000000)   # panel gene whose +/-10 kb span contains the position
"""
from __future__ import annotations

import gzip
import io
import os
import re
from functools import lru_cache
from pathlib import Path

import requests

from genesleuth import config

MANE_BASE = "https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current"
MANE_SUMMARY_URL = f"{MANE_BASE}/MANE.GRCh38.v1.5.summary.txt.gz"
MANE_GTF_URL = f"{MANE_BASE}/MANE.GRCh38.v1.5.ensembl_genomic.gtf.gz"
FLANK = 10_000

# 58 green PanelApp (panel 402) genes, docs/research/03-data.md section 5.
PANEL_GENES = (
    "SCN1A SCN2A SCN3A SCN8A SCN1B KCNQ2 KCNQ3 KCNT1 KCNA2 KCNB1 KCNMA1 CACNA1A CACNA1E HCN1 "
    "GRIN1 GRIN2A GRIN2B GRIN2D GABRA1 GABRB2 GABRB3 GABRG2 SLC2A1 SLC6A1 SLC12A5 SLC13A5 STXBP1 "
    "SYNGAP1 CDKL5 PCDH19 DEPDC5 NPRL2 NPRL3 TSC1 TSC2 MTOR PRRT2 CHD2 MECP2 FOXG1 ARX DNM1 "
    "ALDH7A1 PNPO POLG TBC1D24 SZT2 WWOX UBE3A MEF2C STX1B PIGA SPTAN1 GNAO1 CSTB EPM2A NHLRC1 PURA"
).split()

WORK = config.DATA_DIR / "work"
RAW = config.DATA_DIR / "raw"
REGIONS_TSV = WORK / "panel_regions.tsv"
REGIONS_BED = WORK / "panel_regions.bed"
REGIONS_R = WORK / "panel_regions_bcftools.tsv"
FEATURES_TSV = WORK / "mane_features.tsv.gz"
PANEL_NAME = "Genetic epilepsy"


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes to `path` through a temp file + rename (shared dir, other slices read concurrently)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _download(url: str, dest: Path) -> Path:
    """Idempotent download into DATA_DIR/raw."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    _atomic_write(dest, r.content)
    return dest


def _nc_to_chr(acc: str) -> str | None:
    """NC_000002.12 -> chr2, NC_000023.11 -> chrX, NC_000024 -> chrY."""
    m = re.match(r"NC_0+(\d+)\.\d+", acc)
    if not m:
        return None
    n = int(m.group(1))
    if 1 <= n <= 22:
        return f"chr{n}"
    return {23: "chrX", 24: "chrY"}.get(n)


def build_regions(genes=PANEL_GENES, flank: int = FLANK) -> list[dict]:
    """Read the MANE summary and return one dict per panel gene (MANE Select span +/- flank)."""
    path = _download(MANE_SUMMARY_URL, RAW / "MANE.GRCh38.v1.5.summary.txt.gz")
    rows: dict[str, dict] = {}
    with gzip.open(path, "rt") as fh:
        header = fh.readline().lstrip("#").rstrip("\n").split("\t")
        for line in fh:
            f = dict(zip(header, line.rstrip("\n").split("\t")))
            sym = f.get("symbol")
            if sym not in genes or f.get("MANE_status") != "MANE Select":
                continue
            chrom = _nc_to_chr(f["GRCh38_chr"])
            if not chrom:
                continue
            s, e, strand = int(f["chr_start"]), int(f["chr_end"]), f["chr_strand"]
            rows[sym] = {
                "gene": sym, "chrom": chrom, "start": max(1, s - flank), "end": e + flank, "strand": strand,
                "tss": s if strand == "+" else e, "ensembl_gene": f["Ensembl_Gene"].split(".")[0],
                "mane_transcript": f["Ensembl_nuc"].split(".")[0], "gene_start": s, "gene_end": e,
                "refseq": f["RefSeq_nuc"],
            }
    missing = [g for g in genes if g not in rows]
    if missing:
        raise RuntimeError(f"genes missing from MANE summary: {missing}")
    return [rows[g] for g in genes]


def build_features(regions: list[dict]) -> int:
    """Extract exon/CDS/UTR/codon features of the panel genes' MANE Select transcripts from the GTF."""
    path = _download(MANE_GTF_URL, RAW / "MANE.GRCh38.v1.5.ensembl_genomic.gtf.gz")
    tx_to_gene = {r["mane_transcript"]: r["gene"] for r in regions}
    out = ["gene\ttranscript\tchrom\tstart\tend\tstrand\tfeature\texon_number"]
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 9 or p[2] in ("gene", "transcript"):
                continue
            m = re.search(r'transcript_id "([^";]+)', p[8])
            if not m:
                continue
            tx = m.group(1).split(".")[0]
            gene = tx_to_gene.get(tx)
            if not gene:
                continue
            en = re.search(r'exon_number "?(\d+)', p[8])
            chrom = p[0] if p[0].startswith("chr") else f"chr{p[0]}"
            out.append("\t".join([gene, tx, chrom, p[3], p[4], p[6], p[2], en.group(1) if en else ""]))
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("\n".join(out) + "\n").encode())
    _atomic_write(FEATURES_TSV, buf.getvalue())
    return len(out) - 1


def write_all() -> list[dict]:
    """Build panel_regions.tsv / .bed / bcftools list and mane_features.tsv.gz (idempotent, atomic)."""
    regions = build_regions()
    cols = ["gene", "chrom", "start", "end", "strand", "tss", "ensembl_gene"]
    _atomic_write(REGIONS_TSV, ("\t".join(cols) + "\n" + "\n".join(
        "\t".join(str(r[c]) for c in cols) for r in regions) + "\n").encode())
    _atomic_write(REGIONS_BED, ("\n".join(
        f"{r['chrom']}\t{r['start'] - 1}\t{r['end']}\t{r['gene']}" for r in regions) + "\n").encode())
    _atomic_write(REGIONS_R, ("\n".join(
        f"{r['chrom']}\t{r['start']}\t{r['end']}" for r in regions) + "\n").encode())
    n = build_features(regions)
    print(f"{len(regions)} genes, {sum(r['end'] - r['start'] + 1 for r in regions):,} bp, {n} features")
    load_panel_regions.cache_clear()
    return regions


@lru_cache(maxsize=1)
def load_panel_regions() -> list[dict]:
    """Return panel_regions.tsv as a list of dicts (ints for start/end/tss). Builds it if missing."""
    if not REGIONS_TSV.exists():
        write_all()
    out = []
    with open(REGIONS_TSV) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            d = dict(zip(header, line.rstrip("\n").split("\t")))
            for k in ("start", "end", "tss"):
                d[k] = int(d[k])
            out.append(d)
    return out


def gene_at(chrom: str, pos: int) -> dict | None:
    """Return the panel region dict whose flanked span contains chrom:pos (nearest TSS if several overlap)."""
    hits = [r for r in load_panel_regions() if r["chrom"] == chrom and r["start"] <= pos <= r["end"]]
    if not hits:
        return None
    return min(hits, key=lambda r: abs(r["tss"] - pos))


@lru_cache(maxsize=1)
def load_features() -> dict[str, list[dict]]:
    """Return {gene: [feature dicts]} from mane_features.tsv.gz."""
    if not FEATURES_TSV.exists():
        write_all()
    feats: dict[str, list[dict]] = {}
    with gzip.open(FEATURES_TSV, "rt") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            d = dict(zip(header, line.rstrip("\n").split("\t")))
            d["start"], d["end"] = int(d["start"]), int(d["end"])
            feats.setdefault(d["gene"], []).append(d)
    return feats
