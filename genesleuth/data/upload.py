"""Patient VCF upload (feature: suspects from a user-supplied VCF).

`suspects_from_vcf(vcf_path, sample=None, budget_s=30)` turns an uploaded GRCh38 VCF (.vcf or .vcf.gz) into the
same bundle shape as `suspects.load_suspects` (sample_id, funnel with real counts, suspects as Variant objects,
af_threshold, frequencies) so build_case can consume it.

Steps: parse (pure Python, no WSL) -> assembly check (GRCh38 only) -> keep het/hom-alt SNVs and indels <= 10 bp
inside the 58 panel regions -> allele frequency, never invented, in this order:
    (a) an allele-frequency INFO field in the VCF (gnomAD_AF, gnomad_af, AF_popmax, AF_grpmax, ...)
    (b) the gnomAD v4.1 frequencies precomputed in assets/suspects_NA12878.json.gz (match by variant id)
    (c) gnomAD v4.1 genomes streamed with bcftools -R (same path as filter.py) inside the remaining time budget,
        most informative variants first (non-intron, then introns closest to exon boundaries)
    (d) otherwise AF stays None and is counted in funnel["af_unknown"] (kept as a suspect candidate).
Plain INFO/AF is NOT used (in a patient VCF it is often an allele fraction or cohort frequency, not a population AF).
Threshold = the NA12878 path's threshold (AF < 0.01). Cap of 300 suspects, ranked: non-intron before intron,
known-rare before AF-unknown, then closest to an exon boundary (introns) / by position.
Anything wrong raises UploadError with a readable reason; nothing is faked.
"""
from __future__ import annotations

import bisect
import gzip
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait

from genesleuth import config
from genesleuth.data import annotate, panel
from genesleuth.data.bcf import run_shell, to_wsl_path
from genesleuth.data.filter import GNOMAD_URL
from genesleuth.schemas import Variant

AF_THRESHOLD = 0.01
CAP = 300
MAX_INDEL = 10
AF_FIELDS = ["gnomAD_AF", "gnomad_AF", "gnomad_af", "GNOMAD_AF", "gnomAD_genomes_AF", "gnomAD_AF_popmax",
             "AF_popmax", "AF_grpmax", "gnomad_AF_popmax", "gnomAD_AF_grpmax", "gnomADg_AF", "gnomAD_exomes_AF"]
G38 = {"chr1": 248956422, "chr2": 242193529, "chr3": 198295559, "chrX": 156040895, "chr7": 159345973}
G37 = {"chr1": 249250621, "chr2": 243199373, "chr3": 198022430, "chrX": 155270560, "chr7": 159138663}
_RANK = {"splice": 5, "coding": 4, "utr5": 3, "utr3": 3, "promoter": 2, "intergenic": 1, "intron": 0, "other": 0}
_TMP = config.DATA_DIR / "work" / "_upload_tmp"


class UploadError(Exception):
    """The uploaded file cannot be used; the message is meant to be shown to the user."""


def _norm_chrom(c: str) -> str:
    c = c.strip()
    c = c[3:] if c.lower().startswith("chr") else c
    return "chr" + ("M" if c in ("MT", "M") else c)


def _open(path: str):
    try:
        with open(path, "rb") as fh:
            magic = fh.read(2)
    except OSError as e:
        raise UploadError(f"cannot read file: {e}")
    return gzip.open(path, "rt", errors="replace") if magic == b"\x1f\x8b" else open(path, "rt", errors="replace")


def _check_assembly(header: list[str]) -> str:
    """Return 'GRCh38' (verified) or 'GRCh38 (unverified)'; raise UploadError for GRCh37 / other builds."""
    text = "\n".join(header)
    if re.search(r"hg19|grch37|b37|hs37|human_g1k_v37|hg18|ncbi36|build\s*37", text, re.I) and not re.search(r"grch38|hg38", text, re.I):
        raise UploadError("GRCh37/hg19 VCF detected (header names a GRCh37/hg19 reference). GRCh37 not supported, "
                          "please lift the file over to GRCh38 (e.g. CrossMap or bcftools +liftover) and upload again.")
    seen = {}
    for ln in header:
        m = re.match(r"##contig=<.*?ID=([^,>]+).*?length=(\d+)", ln)
        if m:
            seen[_norm_chrom(m.group(1))] = int(m.group(2))
    hit38 = [c for c, n in seen.items() if G38.get(c) == n]
    hit37 = [c for c, n in seen.items() if G37.get(c) == n]
    if hit37 and not hit38:
        raise UploadError("GRCh37/hg19 contig lengths detected in the VCF header. GRCh37 not supported, "
                          "please lift the file over to GRCh38 and upload again.")
    if re.search(r"grch38|hg38", text, re.I) or hit38:
        return "GRCh38"
    return "GRCh38 (unverified: the header has no ##reference or recognised ##contig lengths)"


def _parse(path: str, sample: str | None, deadline: float) -> tuple[list[dict], dict, str, str]:
    """Read the VCF; return (rows in panel regions, counts, sample name, assembly note)."""
    regions: dict[str, list[tuple[int, int]]] = {}
    for r in panel.load_panel_regions():
        regions.setdefault(r["chrom"], []).append((r["start"], r["end"]))
    for c in regions:
        regions[c].sort()
    starts = {c: [s for s, _ in v] for c, v in regions.items()}
    header: list[str] = []
    rows, seen = [], set()
    n_records = n_genotyped = 0
    sample_name, sidx, assembly = None, None, None
    with _open(path) as fh:
        first = fh.readline()
        if not first.startswith("##fileformat=VCF"):
            raise UploadError("not a VCF file (first line must start with ##fileformat=VCF); BCF and other formats are not supported.")
        header.append(first)
        for ln in fh:
            if ln.startswith("##"):
                header.append(ln)
                continue
            if ln.startswith("#CHROM"):
                cols = ln.rstrip("\n").split("\t")
                if len(cols) < 10:
                    raise UploadError("VCF has no sample/genotype column (sites-only file); a patient genotype column is required.")
                names = cols[9:]
                if sample is None:
                    sample_name, sidx = names[0], 0
                elif sample in names:
                    sample_name, sidx = sample, names.index(sample)
                else:
                    raise UploadError(f"sample '{sample}' not found in the VCF (samples: {', '.join(names[:8])}).")
                assembly = _check_assembly(header)
                continue
            if sidx is None:
                raise UploadError("VCF has no #CHROM header line.")
            n_records += 1
            if n_records % 20000 == 0 and time.time() > deadline:
                raise UploadError("VCF too large to process within the time budget; upload a panel-sized or smaller file.")
            p = ln.split("\t", 9 + sidx + 1) if False else ln.rstrip("\n").split("\t")
            if len(p) < 10:
                continue
            chrom = _norm_chrom(p[0])
            if chrom not in regions:
                continue
            try:
                pos = int(p[1])
            except ValueError:
                raise UploadError(f"malformed VCF record at {p[0]}:{p[1]}")
            i = bisect.bisect_right(starts[chrom], pos) - 1
            if not any(s <= pos <= e for s, e in regions[chrom][max(0, i - 2):i + 2]):
                continue
            fmt = p[8].split(":")
            if "GT" not in fmt:
                continue
            try:
                gt = p[9 + sidx].split(":")[fmt.index("GT")]
            except IndexError:
                continue
            alleles = [a for a in re.split(r"[/|]", gt) if a not in (".", "0", "")]
            if not alleles:
                continue
            n_genotyped += 1
            ref, alts, flt = p[3].upper(), p[4].upper().split(","), p[6]
            info = {}
            for kv in p[7].split(";"):
                k, _, v = kv.partition("=")
                info[k] = v
            afv, afsrc = None, None
            for idx in sorted(set(alleles)):
                if not idx.isdigit() or int(idx) < 1 or int(idx) > len(alts):
                    continue
                a = alts[int(idx) - 1]
                if a.startswith("<") or "*" in a or not re.fullmatch(r"[ACGTN]+", a) or not re.fullmatch(r"[ACGTN]+", ref):
                    continue
                if abs(len(ref) - len(a)) > MAX_INDEL or (len(ref) == len(a) and len(ref) > 1):
                    continue
                for f in AF_FIELDS:
                    if f in info and info[f] not in ("", "."):
                        vals = info[f].split(",")
                        try:
                            v = vals[int(idx) - 1] if len(vals) >= int(idx) else vals[0]
                            afv, afsrc = float(v), f"vcf_info:{f}"
                            break
                        except ValueError:
                            continue
                g = "1/1" if (len(alleles) == 2 and alleles[0] == alleles[1]) else "0/1"
                key = (chrom, pos, ref, a)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"chrom": chrom, "pos": pos, "ref": ref, "alt": a, "gt": g, "af_used": afv, "af_source": afsrc})
    if sidx is None:
        raise UploadError("VCF has no #CHROM header line.")
    return rows, {"records": n_records, "genotyped": n_genotyped}, sample_name, assembly


def _stream_gnomad(rows: list[dict], deadline: float, notes: list[str], workers: int = 16, chunk: int = 80) -> int:
    """(c) gnomAD v4.1 AF for unresolved rows within the deadline; most informative positions first."""
    todo = [r for r in rows if r["af_source"] is None]
    if not todo or time.time() > deadline - 3:
        return 0
    todo.sort(key=lambda r: r["_prio"])
    buckets: dict[str, list[dict]] = {}
    chunks = []
    for r in todo:
        b = buckets.setdefault(r["chrom"], [])
        b.append(r)
        if len(b) >= chunk:
            chunks.append(b)
            buckets[r["chrom"]] = []
    chunks += [b for b in buckets.values() if b]
    _TMP.mkdir(parents=True, exist_ok=True)

    def run(ch: list[dict]) -> list[tuple]:
        left = int(deadline - time.time())
        if left < 3:
            return []
        f = _TMP / f"{uuid.uuid4().hex}.tsv"
        f.write_text("".join(f"{ch[0]['chrom']}\t{p}\n" for p in sorted({r['pos'] for r in ch})))
        script = (f"timeout {left} bcftools view -G -R {to_wsl_path(f)} {GNOMAD_URL.format(chrom=ch[0]['chrom'])} 2>/dev/null"
                  " | bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\t%INFO/AF\t%INFO/AF_grpmax\t%INFO/AN\n'")
        try:
            p = run_shell(script, timeout=left + 5)
        finally:
            f.unlink(missing_ok=True)
        out = []
        for ln in p.stdout.decode().splitlines():
            c, pos, ref, alt, af, gm, an = ln.split("\t")
            afs, gms = af.split(","), gm.split(",")
            for i, a in enumerate(alt.split(",")):
                out.append((c, int(pos), ref, a, afs[i] if i < len(afs) else ".", gms[i] if i < len(gms) else ".", an))
        return out

    ex = ThreadPoolExecutor(max_workers=workers)
    futs = [ex.submit(run, c) for c in chunks]
    done, pending = wait(futs, timeout=max(1.0, deadline - time.time()))
    ex.shutdown(wait=False, cancel_futures=True)
    idx = {(r["chrom"], r["pos"], r["ref"], r["alt"]): r for r in todo}
    covered = set()
    n = 0
    for f in done:
        try:
            recs = f.result()
        except Exception as e:  # stream failed: leave those unknown, but say so
            notes.append(f"gnomAD stream error: {e}")
            continue
        for c, pos, ref, a, af, gm, an in recs:
            r = idx.get((c, pos, ref, a))
            if r is not None and af not in (".", ""):
                r["af_used"], r["af_source"] = float(af), "gnomad_v4.1_genomes"
                r["gnomad_grpmax"] = None if gm in (".", "") else float(gm)
                r["gnomad_an"] = int(an) if an.isdigit() else None
                n += 1
    if pending:
        notes.append(f"gnomAD streaming hit the time budget: {len(pending)} of {len(futs)} chunks unfinished")
    return n


def suspects_from_vcf(vcf_path: str, sample: str | None = None, budget_s: float = 30.0) -> dict:
    """Build the suspects bundle for an uploaded VCF (see module docstring). Raises UploadError on any problem."""
    t0 = time.time()
    deadline = t0 + float(budget_s) - 4.0   # reserve ~4 s for annotation and ranking
    if not os.path.exists(vcf_path):
        raise UploadError(f"file not found: {vcf_path}")
    rows, counts, sample_name, assembly = _parse(vcf_path, sample, deadline)
    notes: list[str] = []
    if not rows:
        raise UploadError(f"no usable variants inside the 58 epilepsy-panel regions (read {counts['records']} records, "
                          f"{counts['genotyped']} genotyped in panel regions). Check that the file is GRCh38 and has genotypes.")
    t_parse = time.time() - t0
    # classification (pure python) -> priority for AF streaming and capping
    cls = {}
    for r in rows:
        k = annotate.classify(r["chrom"], r["pos"], r["ref"], r["alt"])
        cls[(r["chrom"], r["pos"], r["ref"], r["alt"])] = k
        bd = k["boundary_distance"] if k["boundary_distance"] is not None else 10**6
        r["_prio"] = (k["region"] == "intron", bd, r["pos"])
    rows = [r for r in rows if cls[(r["chrom"], r["pos"], r["ref"], r["alt"])]["gene"]]
    n_panel = len(rows)
    # (b) precomputed gnomAD frequencies from the committed NA12878 bundle
    n_assets = 0
    try:
        from genesleuth.data.suspects import load_suspects_raw
        fr = load_suspects_raw(config.DEFAULT_SAMPLE)["frequencies"]
    except Exception:
        fr = {}
    for r in rows:
        if r["af_source"] is None:
            e = fr.get(annotate.variant_id(r["chrom"], r["pos"], r["ref"], r["alt"]))
            if e and e.get("gnomad_af") is not None:
                r["af_used"], r["af_source"] = e["gnomad_af"], "assets:gnomad_v4.1_genomes"
                r["gnomad_grpmax"], r["gnomad_an"] = e.get("gnomad_grpmax"), e.get("gnomad_an")
                n_assets += 1
    n_vcf = sum(1 for r in rows if r["af_source"] and r["af_source"].startswith("vcf_info"))
    # (c) stream gnomAD within what is left of the budget
    n_stream = 0
    try:
        n_stream = _stream_gnomad(rows, deadline, notes)
    except Exception as e:
        notes.append(f"gnomAD streaming unavailable: {e}")
    known = [r for r in rows if r["af_used"] is not None]
    unknown = [r for r in rows if r["af_used"] is None]
    cand = [r for r in rows if r["af_used"] is None or r["af_used"] < AF_THRESHOLD]
    ann = annotate.annotate_many([(r["chrom"], r["pos"], r["ref"], r["alt"], r["gt"]) for r in cand])
    meta = {annotate.variant_id(r["chrom"], r["pos"], r["ref"], r["alt"]): r for r in cand}
    items = [(v, k, meta[v.variant_id]) for v, k in ann if v.gene]

    def rank(x):
        v, k, r = x
        bd = k["boundary_distance"] if k["boundary_distance"] is not None else 10**6
        return (v.region == "intron", r["af_used"] is None, bd if v.region == "intron" else 0, -_RANK.get(v.region, 0), v.chrom, v.pos)
    items.sort(key=rank)
    suspects: list[Variant] = [v for v, _, _ in items[:CAP]]
    funnel = {"variants_in_upload": counts["records"], "variants_in_panel_regions": n_panel,
              "af_known": len(known), "af_unknown": len(unknown),
              "af_from_vcf": n_vcf, "af_from_assets": n_assets, "af_from_gnomad_stream": n_stream,
              "rare_af_lt_0.01": sum(1 for r in known if r["af_used"] < 0.01), "rare_af_lt_0.001": sum(1 for r in known if r["af_used"] < 0.001),
              "rare": len(cand), "suspects": len(suspects)}
    freqs = {}
    for v, _, r in items[:CAP]:
        freqs[v.variant_id] = {"gnomad_af": r["af_used"] if r["af_source"] and "gnomad" in r["af_source"] else None,
                               "gnomad_grpmax": r.get("gnomad_grpmax"), "gnomad_an": r.get("gnomad_an"),
                               "kg_af": None, "af_source": r["af_source"] or "absent",
                               "af_used": r["af_used"]}
    if len(cand) > CAP:
        notes.append(f"{len(cand)} candidates capped to {CAP}: non-intron first, known-rare before AF-unknown, then introns nearest an exon boundary")
    if unknown:
        notes.append(f"{len(unknown)} variants have no available allele frequency (kept as candidates, not assumed rare)")
    return {"sample_id": sample_name, "af_threshold": AF_THRESHOLD, "funnel": funnel, "suspects": suspects,
            "frequencies": freqs, "assembly": assembly, "notes": notes,
            "timings": {"parse_s": round(t_parse, 2), "total_s": round(time.time() - t0, 2)}}
