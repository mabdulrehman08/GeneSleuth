"""population_frequency: gnomAD v4.1 allele frequency for one variant.

Feature: live gnomAD GraphQL query (https://gnomad.broadinstitute.org/api, dataset gnomad_r4, variant id without the
'chr' prefix, e.g. "2-166036402-A-C"), combining the genome and exome cohorts.
Measured Nov 21 2026: ~2 s per request and HTTP 429 after roughly 4-10 requests in quick succession (about 10 requests
per minute), so calls are spaced by MIN_INTERVAL seconds, a 429 is retried at most twice, and every definitive answer
(including "not found in gnomAD", i.e. not observed) is cached on disk under DATA_DIR/cache/lookups/popfreq/.
Order: (1) disk cache, (2) the gnomAD v4.1 genome frequencies slice A1 precomputed for every background variant of the
sample (`frequencies` in suspects_<sample>.json[.gz], instant), (3) live gnomAD GraphQL (only for variants outside that
table, e.g. the one planted variant). Without (2) every lookup costs ~7 s and an investigation can time out.
Fallback chain when gnomAD cannot be reached: the allele frequency stored on the annotated suspect (keys af /
gnomad_af / af_1kg / kg_af, if slice A1 stored one), otherwise {found: False, source: "unavailable"} with a note.
Fallback answers are NOT cached, so a later call retries gnomAD.
Result: {found, source, af, ac, an, genome: {ac,an,af}|None, exome: {ac,an,af}|None, note?}
"""
from __future__ import annotations

import functools
import threading
import time

import requests

from ._common import cache_get, cache_put, canonical_id, parse_variant_id

GNOMAD_URL = "https://gnomad.broadinstitute.org/api"
DATASET = "gnomad_r4"
MIN_INTERVAL = 6.5   # seconds between live requests (measured limit ~10/min)
MAX_RETRIES = 2
TIMEOUT = 25
_QUERY = """query($id:String!){ variant(variantId:$id, dataset: gnomad_r4){ variant_id
  genome{ac an af} exome{ac an af} } }"""
_lock = threading.Lock()
_last_call = 0.0


def _gnomad_id(vid: str) -> str:
    c, p, r, a = parse_variant_id(vid)
    return f"{c[3:]}-{p}-{r}-{a}"


def _post(gid: str) -> requests.Response:
    """Rate-limited POST (process-wide spacing)."""
    global _last_call
    with _lock:
        wait = MIN_INTERVAL - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            return requests.post(GNOMAD_URL, json={"query": _QUERY, "variables": {"id": gid}}, timeout=TIMEOUT)
        finally:
            _last_call = time.time()


def _query_gnomad(vid: str) -> dict | None:
    """Return a definitive result dict, or None when gnomAD is unreachable / rate limited."""
    gid = _gnomad_id(vid)
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = _post(gid)
        except requests.RequestException:
            continue
        if r.status_code == 429:
            time.sleep(10)
            continue
        if r.status_code != 200:
            return None
        try:
            js = r.json()
        except ValueError:
            return None
        v = (js.get("data") or {}).get("variant")
        if v:
            g, e = v.get("genome"), v.get("exome")
            ac = sum(x["ac"] for x in (g, e) if x and x.get("ac") is not None)
            an = sum(x["an"] for x in (g, e) if x and x.get("an"))
            return {"found": True, "source": "gnomAD v4.1 (GraphQL, genomes+exomes)", "af": (ac / an) if an else None,
                    "ac": ac, "an": an, "genome": g, "exome": e}
        errs = " ".join(x.get("message", "") for x in js.get("errors", []))
        if "not found" in errs.lower():
            return {"found": False, "source": "gnomAD v4.1 (GraphQL)", "af": None, "ac": None, "an": None,
                    "genome": None, "exome": None, "note": "not observed in gnomAD v4.1"}
        return None
    return None


@functools.lru_cache(maxsize=1)
def _precomputed() -> dict[str, dict]:
    """variant_id -> frequency record from suspects_<sample>.json[.gz] `frequencies` (assets/ first, then DATA_DIR/work)."""
    import gzip
    import json
    from ._common import assets_dir, data_dir
    out: dict[str, dict] = {}
    for d in (assets_dir(), data_dir() / "work"):
        for p in sorted(d.glob("suspects_*.json*")):
            try:
                txt = gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")
                for k, v in (json.loads(txt).get("frequencies") or {}).items():
                    out.setdefault(k, v)
            except (OSError, ValueError):
                continue
    return out


def _precomputed_af(vid: str) -> dict | None:
    """gnomAD v4.1 genome AF precomputed for background variants (None when the variant is not in the table)."""
    rec = _precomputed().get(vid)
    if not rec or rec.get("gnomad_af") is None or not str(rec.get("af_source", "")).startswith("gnomad"):
        return None
    an = rec.get("gnomad_an")
    af = float(rec["gnomad_af"])
    return {"found": True, "source": "gnomAD v4.1 genomes (precomputed for the background genome)", "af": af,
            "ac": int(round(af * an)) if an else None, "an": int(an) if an else None, "genome": None, "exome": None,
            "popmax_af": rec.get("gnomad_grpmax")}


def _stored_af(vid: str) -> dict | None:
    """AF kept on the annotated suspect by slice A1, if any."""
    from .region import _suspect_index
    s = _suspect_index().get(vid)
    if not s:
        return None
    for k in ("gnomad_af", "af", "af_1kg", "kg_af", "AF"):
        if s.get(k) is not None:
            return {"found": True, "source": f"stored suspect annotation ({k})", "af": float(s[k]), "ac": None, "an": None,
                    "genome": None, "exome": None}
    return None


def population_frequency(variant_id: str) -> dict:
    """Allele frequency from gnomAD v4.1, with cached results and documented fallbacks (see module header)."""
    vid = canonical_id(variant_id)
    hit = cache_get("popfreq", vid)
    if hit is not None:
        return hit
    pre = _precomputed_af(vid)
    if pre is not None:
        return pre
    res = _query_gnomad(vid)
    if res is not None:
        cache_put("popfreq", vid, res)
        return res
    fb = _stored_af(vid)
    if fb:
        fb["note"] = "gnomAD GraphQL unavailable (rate limited); using stored frequency"
        return fb
    return {"found": False, "source": "unavailable", "af": None, "ac": None, "an": None, "genome": None, "exome": None,
            "note": "gnomAD GraphQL unavailable (rate limited) and no stored frequency; treat as not observed"}
