"""Background genome extraction (feature: the sample's own variants in the panel regions).

Streams one 1000 Genomes high-coverage (NYGC, GRCh38, phased) sample's non-reference genotypes inside the
58-gene panel regions (+/-10 kb) straight from the remote per-chromosome VCFs with bcftools -R (tabix index
over https, so only the needed BGZF blocks are fetched). Chromosomes run in parallel. SNVs and indels up to
10 bp are kept (this panel has FILTER "." rather than PASS, so "." and PASS are both accepted); the panel's
own INFO AF (3,202 samples) is kept for the rarity fallback.

Output: DATA_DIR/work/background_<sample>.tsv.gz with columns
    chrom pos ref alt gt filter af
and the count `variants_in_panel_regions` (len of that table).

Use cases:
    rows = load_background("NA12878")        # builds + caches on first use (about a minute)
"""
from __future__ import annotations

import gzip
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from genesleuth import config
from genesleuth.data import panel
from genesleuth.data.bcf import run_shell, to_wsl_path

KG_BASE = ("https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/"
           "working/20220422_3202_phased_SNV_INDEL_SV")
MAX_INDEL = 10
WORK = config.DATA_DIR / "work"


def chrom_vcf_url(chrom: str) -> str:
    """Remote phased-panel VCF URL for a chr-prefixed chromosome (chrX has a .v2 suffix, v1 was withdrawn)."""
    suffix = ".v2" if chrom == "chrX" else ""
    return f"{KG_BASE}/1kGP_high_coverage_Illumina.{chrom}.filtered.SNV_INDEL_SV_phased_panel{suffix}.vcf.gz"


def _parse(line: str, sample_chrom: str) -> list[dict]:
    """Turn one `bcftools query` line into 0..n variant dicts (one per ALT allele carried by the sample)."""
    c, pos, ref, alt, gt, flt, af = line.rstrip("\n").split("\t")
    alleles = [a for a in gt.replace("|", "/").split("/") if a not in (".", "0", "")]
    if not alleles:
        return []
    alts = alt.split(",")
    afs = af.split(",")
    out = []
    for idx in sorted(set(alleles)):
        i = int(idx) - 1
        if i >= len(alts):
            continue
        a = alts[i]
        if a.startswith("<") or "*" in a or abs(len(ref) - len(a)) > MAX_INDEL:
            continue
        if len(ref) == len(a) and len(ref) > 1:      # MNV: out of scope (SNVs and indels only)
            continue
        if flt not in ("PASS", "."):
            continue
        g = "1/1" if alleles.count(idx) == 2 and all(x == idx for x in alleles) else "0/1"
        try:
            afv = float(afs[i]) if i < len(afs) and afs[i] != "." else None
        except ValueError:
            afv = None
        out.append({"chrom": sample_chrom, "pos": int(pos), "ref": ref, "alt": a, "gt": g, "filter": flt, "af": afv})
    return out


def _stream_chrom(sample: str, chrom: str, regions: list[dict]) -> list[dict]:
    """Stream one chromosome's panel regions for the sample (blocking; run in a worker thread)."""
    reg = WORK / f"_bg_regions_{chrom}.tsv"
    reg.write_text("".join(f"{chrom}\t{r['start']}\t{r['end']}\n" for r in regions))
    script = (f"bcftools view -s {sample} -R {to_wsl_path(reg)} {chrom_vcf_url(chrom)} 2>/dev/null"
              " | bcftools view -i 'GT=\"alt\"' 2>/dev/null"
              " | bcftools query -f '%CHROM\\t%POS\\t%REF\\t%ALT\\t[%GT]\\t%FILTER\\t%INFO/AF\\n'")
    last = ""
    for attempt in range(3):
        p = run_shell(script, timeout=900)
        if p.returncode == 0 and p.stdout is not None:
            rows = []
            for ln in p.stdout.decode().splitlines():
                if ln:
                    rows.extend(_parse(ln, chrom))
            reg.unlink(missing_ok=True)
            return rows
        last = p.stderr.decode()[-300:]
        time.sleep(2)
    raise RuntimeError(f"bcftools failed for {sample} {chrom}: {last}")


def build_background(sample: str, workers: int = 8) -> list[dict]:
    """Stream all panel chromosomes in parallel, dedupe overlapping regions, write the cache file."""
    regions = panel.load_panel_regions()
    by_chrom: dict[str, list[dict]] = {}
    for r in regions:
        by_chrom.setdefault(r["chrom"], []).append(r)
    WORK.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {c: ex.submit(_stream_chrom, sample, c, rs) for c, rs in by_chrom.items()}
        results = {c: f.result() for c, f in futs.items()}
    seen, rows = set(), []
    for c in sorted(results, key=lambda x: (len(x), x)):
        for v in results[c]:
            k = (v["chrom"], v["pos"], v["ref"], v["alt"])
            if k not in seen:
                seen.add(k)
                rows.append(v)
    rows.sort(key=lambda v: (v["chrom"], v["pos"]))
    lines = ["chrom\tpos\tref\talt\tgt\tfilter\taf"] + [
        f"{v['chrom']}\t{v['pos']}\t{v['ref']}\t{v['alt']}\t{v['gt']}\t{v['filter']}\t{'' if v['af'] is None else v['af']}"
        for v in rows]
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode())
    path = background_path(sample)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(buf.getvalue())
    os.replace(tmp, path)
    print(f"background {sample}: {len(rows)} variants in panel regions, {time.time() - t0:.0f}s")
    return rows


def background_path(sample: str) -> Path:
    """Cache path DATA_DIR/work/background_<sample>.tsv.gz."""
    return WORK / f"background_{sample}.tsv.gz"


def load_background(sample: str | None = None, rebuild: bool = False) -> list[dict]:
    """Return the sample's panel-region variants as dicts (builds + caches if missing)."""
    sample = sample or config.DEFAULT_SAMPLE
    path = background_path(sample)
    if rebuild or not path.exists():
        return build_background(sample)
    rows = []
    with gzip.open(path, "rt") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            d = dict(zip(header, line.rstrip("\n").split("\t")))
            d["pos"] = int(d["pos"])
            d["af"] = float(d["af"]) if d["af"] != "" else None
            rows.append(d)
    return rows
