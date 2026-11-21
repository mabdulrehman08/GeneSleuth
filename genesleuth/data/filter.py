"""Rarity filter (feature: population-frequency lookup for the sample's own variants).

For every background variant, the gnomAD v4.1 genomes allele frequency is streamed from the public sites VCFs
with `bcftools view -R <the sample's own positions>` (only INFO AF, AF_grpmax and AN are kept). Resolution order:
    1. gnomAD v4.1 genomes AF (global AF; alleles must match, so indel representation mismatches are not hits)
    2. the 1000 Genomes panel's own INFO AF (3,202 samples), kept by background.py
    3. myvariant.info batch lookup (only if explicitly requested; off by default)
    absent everywhere -> AF unknown -> counts as rare.

Output cache: DATA_DIR/work/gnomad_af_<sample>.tsv.gz (columns chrom pos ref alt af grpmax an).

Use cases:
    af = gnomad_for(rows)                    # {(chrom,pos,ref,alt): (af, grpmax, an)}
    rows = apply_frequency(rows, af)         # adds 'gnomad_af', 'gnomad_grpmax', 'gnomad_an', 'af_used', 'af_source'
    n = count_rare(rows, 0.001)              # funnel counting
"""
from __future__ import annotations

import gzip
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor

from genesleuth import config
from genesleuth.data.bcf import run_shell, to_wsl_path

GNOMAD_URL = ("https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/genomes/"
              "gnomad.genomes.v4.1.sites.{chrom}.vcf.bgz")
WORK = config.DATA_DIR / "work"


def _num(x: str) -> float | None:
    try:
        return float(x) if x not in ("", ".") else None
    except ValueError:
        return None


def _stream_chrom(chrom: str, positions: list[int]) -> list[tuple]:
    """Stream gnomAD records at the given positions of one chromosome; returns (chrom,pos,ref,alt,af,grpmax,an)."""
    reg = WORK / f"_gn_pos_{chrom}.tsv"
    reg.write_text("".join(f"{chrom}\t{p}\n" for p in sorted(set(positions))))
    script = (f"bcftools view -G -R {to_wsl_path(reg)} {GNOMAD_URL.format(chrom=chrom)} 2>/dev/null"
              " | bcftools query -f '%CHROM\\t%POS\\t%REF\\t%ALT\\t%INFO/AF\\t%INFO/AF_grpmax\\t%INFO/AN\\n'")
    last = ""
    for _ in range(3):
        p = run_shell(script, timeout=1500)
        if p.returncode == 0:
            out = []
            for ln in p.stdout.decode().splitlines():
                c, pos, ref, alt, af, gm, an = ln.split("\t")
                afs, gms = af.split(","), gm.split(",")
                for i, a in enumerate(alt.split(",")):
                    out.append((c, int(pos), ref, a, _num(afs[i]) if i < len(afs) else None,
                                _num(gms[i]) if i < len(gms) else None, int(an) if an.isdigit() else None))
            reg.unlink(missing_ok=True)
            return out
        last = p.stderr.decode()[-300:]
        time.sleep(2)
    raise RuntimeError(f"gnomAD stream failed for {chrom}: {last}")


def gnomad_for(rows: list[dict], sample: str, workers: int = 8, refresh: bool = False) -> dict:
    """gnomAD genome frequencies for the rows' alleles ({(chrom,pos,ref,alt): (af, grpmax, an)}), cached on disk."""
    path = WORK / f"gnomad_af_{sample}.tsv.gz"
    if path.exists() and not refresh:
        out = {}
        with gzip.open(path, "rt") as fh:
            fh.readline()
            for ln in fh:
                c, p, r, a, af, gm, an = ln.rstrip("\n").split("\t")
                out[(c, int(p), r, a)] = (_num(af), _num(gm), int(an) if an else None)
        return out
    by_chrom: dict[str, list[int]] = {}
    for r in rows:
        by_chrom.setdefault(r["chrom"], []).append(r["pos"])
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_stream_chrom, c, ps) for c, ps in by_chrom.items()]
        recs = [x for f in futs for x in f.result()]
    wanted = {(r["chrom"], r["pos"], r["ref"], r["alt"]) for r in rows}
    out = {(c, p, r, a): (af, gm, an) for c, p, r, a, af, gm, an in recs if (c, p, r, a) in wanted}
    lines = ["chrom\tpos\tref\talt\taf\tgrpmax\tan"] + [
        f"{c}\t{p}\t{r}\t{a}\t{'' if af is None else af}\t{'' if gm is None else gm}\t{'' if an is None else an}"
        for (c, p, r, a), (af, gm, an) in sorted(out.items())]
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode())
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(buf.getvalue())
    os.replace(tmp, path)
    print(f"gnomAD AF: {len(out)}/{len(wanted)} alleles found in gnomAD genomes v4.1, {time.time() - t0:.0f}s")
    return out


def apply_frequency(rows: list[dict], gn: dict) -> list[dict]:
    """Attach gnomad_af / gnomad_grpmax / gnomad_an / af_used / af_source to every row (None AF = unknown = rare)."""
    for r in rows:
        af, gm, an = gn.get((r["chrom"], r["pos"], r["ref"], r["alt"]), (None, None, None))
        r["gnomad_af"], r["gnomad_grpmax"], r["gnomad_an"] = af, gm, an
        if af is not None:
            r["af_used"], r["af_source"] = af, "gnomad_v4.1_genomes"
        elif r.get("af") is not None:
            r["af_used"], r["af_source"] = r["af"], "1000G_panel"
        else:
            r["af_used"], r["af_source"] = None, "absent"
    return rows


def is_rare(row: dict, threshold: float) -> bool:
    """AF strictly below `threshold`; unknown AF counts as rare."""
    return row["af_used"] is None or row["af_used"] < threshold


def count_rare(rows: list[dict], threshold: float) -> int:
    """Number of rows that pass the rarity filter at `threshold`."""
    return sum(is_rare(r, threshold) for r in rows)
