"""Local ClinVar lookup with leakage guards (reads ROOT/assets/clinvar_panel.tsv.gz first, then DATA_DIR/work/clinvar_panel.tsv.gz).

Feature: look up a variant in the local table of ALL ClinVar records inside the panel regions (any significance),
written by scripts/data_clinvar_table.py. Used only behind `enabled=True` in genesleuth/lookups/api.py because the
public clinvar_lookup is DISABLED for benchmark and demo cases (it would reveal the planted variant).

Second guard (holdout): a record is reported as "not in ClinVar" when
  * its variant id is in the holdout set, or its variation id / allele id is in the holdout set, or
  * ANY record sits at the same chrom+pos as a held-out variant, or at the position of a held-out ClinVar id.
`gene_has_plp_record(gene, holdout)` is the gene-level feature allowed for the fixed recipe (it never exposes a
specific variant): does the gene have any Pathogenic / Likely pathogenic record (1+ star, not conflicting), ignoring
records hidden by the holdout.
"""
from __future__ import annotations

import csv
import functools
import re
from collections import defaultdict

from ._common import canonical_id, find_table, open_text, parse_variant_id

_VID = re.compile(r"^(chr)?(\d{1,2}|X|Y|M|MT)[-:_]\d+[-:_]")


@functools.lru_cache(maxsize=1)
def _table() -> dict:
    """Load the table once: rows plus indexes by variant id, position, variation id and allele id."""
    p = find_table("clinvar_panel.tsv.gz")
    if p is None:
        raise FileNotFoundError("clinvar_panel.tsv.gz missing in assets/ and DATA_DIR/work: run scripts/data_clinvar_table.py")
    rows: list[dict] = []
    by_id: dict[str, list[int]] = defaultdict(list)
    by_pos: dict[tuple[str, int], list[int]] = defaultdict(list)
    by_vid: dict[str, int] = {}
    by_aid: dict[str, int] = {}
    with open_text(p) as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            i = len(rows)
            r["pos"] = int(r["pos"])
            r["stars"] = int(r["stars"] or 0)
            rows.append(r)
            by_id[r["variant_id"]].append(i)
            by_pos[(r["chrom"], r["pos"])].append(i)
            by_vid[r["variation_id"]] = i
            if r["allele_id"]:
                by_aid[r["allele_id"]] = i
    return {"rows": rows, "by_id": by_id, "by_pos": by_pos, "by_vid": by_vid, "by_aid": by_aid}


def _blocked_positions(holdout: set[str]) -> tuple[set[str], set[tuple[str, int]], set[str]]:
    """Return (held-out canonical variant ids, blocked (chrom,pos) pairs, held-out ClinVar ids as strings)."""
    t = _table()
    vids: set[str] = set()
    pos: set[tuple[str, int]] = set()
    cids: set[str] = set()
    for h in holdout or set():
        h = str(h).strip()
        if _VID.match(h):
            try:
                c, p, r, a = parse_variant_id(h)
                vids.add(f"{c}-{p}-{r}-{a}")
                pos.add((c, p))
            except ValueError:
                pass
        else:
            cid = re.sub(r"^(VCV|RCV)0*", "", h)
            cids.add(cid)
            i = t["by_vid"].get(cid)
            if i is None:
                i = t["by_aid"].get(cid)
            if i is not None:
                pos.add((t["rows"][i]["chrom"], t["rows"][i]["pos"]))
    return vids, pos, cids


def clinvar_lookup(variant_id: str, holdout: set[str]) -> dict:
    """Local ClinVar record for a variant, or {found: False, note: "not in ClinVar"} (also when held out)."""
    t = _table()
    vid = canonical_id(variant_id)
    chrom, pos, _ref, _alt = parse_variant_id(vid)
    h_vids, h_pos, h_cids = _blocked_positions(holdout)
    if vid in h_vids or (chrom, pos) in h_pos:
        return {"found": False, "note": "not in ClinVar"}
    idxs = t["by_id"].get(vid, [])
    if not idxs:
        return {"found": False, "note": "not in ClinVar"}
    r = t["rows"][idxs[0]]
    if r["variation_id"] in h_cids or (r["allele_id"] and r["allele_id"] in h_cids):
        return {"found": False, "note": "not in ClinVar"}
    return {"found": True, "source": "ClinVar local table", "variation_id": r["variation_id"],
            "significance": r["clnsig"], "conditions": [c for c in r["condition_names"].split("|") if c],
            "review_status": r["review_status"], "stars": r["stars"], "gene": r["gene"]}


def gene_has_plp_record(gene: str, holdout: set[str] | None = None) -> dict:
    """Gene-level feature: {gene, has_plp, n_plp} counting P/LP records with 1+ star, not conflicting, minus the holdout."""
    t = _table()
    g = str(gene).upper()
    h_vids, h_pos, h_cids = _blocked_positions(holdout or set())
    n = 0
    for r in t["rows"]:
        if g not in r["gene"].split("|"):
            continue
        s = r["clnsig"]
        if "athogenic" not in s or "onflicting" in s or r["stars"] < 1:
            continue
        if r["variant_id"] in h_vids or (r["chrom"], r["pos"]) in h_pos or r["variation_id"] in h_cids or r["allele_id"] in h_cids:
            continue
        n += 1
    return {"gene": g, "has_plp": n > 0, "n_plp": n}
