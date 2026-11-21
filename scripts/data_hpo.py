"""Download the Human Phenotype Ontology files and build the lookup work tables.

Feature: idempotent HPO data preparation for the lookups and for the case builder (slices A3 / A4).
Source: latest release of https://github.com/obophenotype/human-phenotype-ontology (files hp.obo, hp.json,
genes_to_phenotype.txt, phenotype.hpoa), verified Nov 21 2026 (release v2026-09-01).

Writes (DATA_DIR = genesleuth.config.DATA_DIR):
  raw/hp.obo, raw/hp.json, raw/genes_to_phenotype.txt, raw/phenotype.hpoa, raw/hpo_release.txt
  work/hpo_terms.json        {hpo_id: {"label": str, "synonyms": [str], "parents": [hpo_id]}}
  work/hpo_gene.tsv          gene <tab> hpo_id                (unique pairs, from genes_to_phenotype)
  work/hpo_disease.tsv       disease_id <tab> disease_name <tab> hpo_id <tab> frequency
                             (phenotype.hpoa, aspect P, rows with qualifier NOT dropped)
  work/hpo_gene_disease.tsv  gene <tab> disease_id <tab> disease_name   (extra, used by gene_phenotypes)

Also writes ROOT/assets/<table>.gz copies (the committed bundle read first by the lookups).
Use: python scripts/data_hpo.py [--force] [--skip-download] [--no-bundle]
License / attribution: see docs/DATA_SOURCES.md (HPO license text and required citation are recorded there).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gzip  # noqa: E402

from genesleuth.lookups._common import assets_dir, find_table, raw_dir, work_dir, write_atomic  # noqa: E402

TABLES = ["hpo_terms.json", "hpo_gene.tsv", "hpo_disease.tsv", "hpo_gene_disease.tsv", "hpo_alt_ids.json"]

BASE = "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/"
FILES = ["hp.obo", "hp.json", "genes_to_phenotype.txt", "phenotype.hpoa"]
API_LATEST = "https://api.github.com/repos/obophenotype/human-phenotype-ontology/releases/latest"


def download(name: str, force: bool = False) -> Path:
    """Download one release asset into raw/ (skip if present and non-empty). Atomic via temp file."""
    dest = raw_dir() / name
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"[skip] {name} already present ({dest.stat().st_size:,} bytes)")
        return dest
    t0 = time.time()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(BASE + name, stream=True, timeout=120, allow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    tmp.replace(dest)
    print(f"[download] {name} {dest.stat().st_size:,} bytes in {time.time() - t0:.1f}s")
    return dest


def record_release() -> None:
    """Write raw/hpo_release.txt with the release tag/date (best effort)."""
    try:
        d = requests.get(API_LATEST, timeout=30).json()
        write_atomic(raw_dir() / "hpo_release.txt", f"{d.get('tag_name')}\t{d.get('published_at')}\n")
    except Exception as e:  # noqa: BLE001
        print("[warn] could not record release tag:", e)


def parse_obo(path: Path) -> tuple[dict, dict]:
    """Parse hp.obo into {hpo_id: {label, synonyms, parents}}; obsolete terms are skipped, alt_ids point to the main term."""
    terms: dict[str, dict] = {}
    alts: dict[str, str] = {}
    cur: dict | None = None
    syn_re = re.compile(r'^synonym:\s+"(.*)"\s+[A-Z]+')
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line == "[Term]":
                cur = {"id": None, "label": "", "synonyms": [], "parents": [], "obsolete": False}
                continue
            if line.startswith("[") and line != "[Term]":
                cur = None
                continue
            if cur is None or not line:
                if not line and cur is not None and cur["id"]:
                    if not cur["obsolete"]:
                        terms[cur["id"]] = {"label": cur["label"], "synonyms": cur["synonyms"], "parents": cur["parents"]}
                    cur = None
                continue
            if line.startswith("id: "):
                cur["id"] = line[4:].strip()
            elif line.startswith("name: "):
                cur["label"] = line[6:].strip()
            elif line.startswith("is_a: "):
                cur["parents"].append(line[6:].split("!")[0].strip())
            elif line.startswith("alt_id: ") and cur["id"]:
                alts[line[8:].strip()] = cur["id"]
            elif line.startswith("is_obsolete: true"):
                cur["obsolete"] = True
            elif line.startswith("synonym:"):
                m = syn_re.match(line)
                if m:
                    cur["synonyms"].append(m.group(1))
        if cur and cur["id"] and not cur["obsolete"]:
            terms[cur["id"]] = {"label": cur["label"], "synonyms": cur["synonyms"], "parents": cur["parents"]}
    # keep only HP: terms
    return {k: v for k, v in terms.items() if k.startswith("HP:")}, alts


def build_tables() -> dict:
    """Build the work tables from the raw files; returns counts."""
    raw, work = raw_dir(), work_dir()
    terms, alts = parse_obo(raw / "hp.obo")
    write_atomic(work / "hpo_terms.json", json.dumps(terms))
    write_atomic(work / "hpo_alt_ids.json", json.dumps(alts))

    pairs: set[tuple[str, str]] = set()
    gene_dis: set[tuple[str, str]] = set()
    with open(raw / "genes_to_phenotype.txt", encoding="utf-8") as fh:
        rd = csv.reader(fh, delimiter="\t")
        header = next(rd)
        col = {h.lower(): i for i, h in enumerate(header)}
        gi, hi = col["gene_symbol"], col["hpo_id"]
        di = col.get("disease_id")
        for row in rd:
            if len(row) <= max(gi, hi):
                continue
            pairs.add((row[gi], row[hi]))
            if di is not None and len(row) > di:
                gene_dis.add((row[gi], row[di]))

    dis_rows, dis_names = [], {}
    with open(raw / "phenotype.hpoa", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            if line.startswith("database_id"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 11:
                continue
            did, name, qual, hid, _ref, _ev, _onset, freq, _sex, _mod, aspect = p[:11]
            dis_names.setdefault(did, name)
            if aspect != "P" or qual.strip().upper() == "NOT":
                continue
            dis_rows.append((did, name, hid, freq))

    def tsv(rows, header):
        out = ["\t".join(header)] + ["\t".join(r) for r in rows]
        return "\n".join(out) + "\n"

    write_atomic(work / "hpo_gene.tsv", tsv(sorted(pairs), ["gene", "hpo_id"]))
    write_atomic(work / "hpo_disease.tsv", tsv(dis_rows, ["disease_id", "disease_name", "hpo_id", "frequency"]))
    gd_rows = [(g, d, dis_names.get(d, "")) for g, d in sorted(gene_dis)]
    write_atomic(work / "hpo_gene_disease.tsv", tsv(gd_rows, ["gene", "disease_id", "disease_name"]))
    counts = {"terms": len(terms), "gene_hpo_pairs": len(pairs), "genes": len({g for g, _ in pairs}),
              "disease_rows": len(dis_rows), "diseases": len({r[0] for r in dis_rows}), "gene_disease_rows": len(gd_rows)}
    print("[build]", counts)
    return counts


def bundle() -> list[str]:
    """Copy the work tables gzip-compressed to ROOT/assets/ (committed bundle, ~6 MB total); returns written names."""
    out = []
    for name in TABLES:
        src = work_dir() / name
        if not src.exists():
            continue
        dst = assets_dir() / (name + ".gz")
        write_atomic(dst, gzip.compress(src.read_bytes(), compresslevel=9, mtime=0))
        out.append(dst.name)
    print("[bundle]", out)
    return out


def main(argv: list[str] | None = None) -> None:
    """Idempotent entry point (also called by scripts/data_setup.py): skip when tables exist in assets/ or work/."""
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    ap.add_argument("--force", action="store_true", help="re-download and rebuild")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--no-bundle", action="store_true", help="do not write ROOT/assets/*.gz")
    a = ap.parse_args(argv)
    if not a.force and all(find_table(t) for t in TABLES):
        print("[skip] HPO tables already present (assets/ or DATA_DIR/work)")
        return
    if not a.skip_download:
        for f in FILES:
            download(f, a.force)
        record_release()
    build_tables()
    if not a.no_bundle:
        bundle()


if __name__ == "__main__":
    main()
