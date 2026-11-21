"""Shared helpers for the lookup modules: paths, variant-id parsing, disk cache, error wrapping.

Feature: every public lookup in genesleuth/lookups/api.py must be cached on disk, JSON-serializable and
must never raise. This file holds the pieces they all share so each feature file stays small.

Use cases: `safe(fn)` wraps a lookup so exceptions become {"error": ...}; `cache_get/cache_put` store one
JSON file per key under DATA_DIR/cache/lookups/<namespace>/; `parse_variant_id` turns
"chr2-165991234-A-G" into its parts; `write_atomic` is the temp-file-then-rename writer shared by the
data scripts (several slices share DATA_DIR, so partial files must never be visible).
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

from genesleuth import config

_VID_RE = re.compile(r"^(?:chr)?([0-9]{1,2}|X|Y|M|MT)[-:_](\d+)[-:_]([ACGTN]+|\*|-)[-:_>]([ACGTN,]+|\*|-)$", re.I)


def data_dir() -> Path:
    """Shared data root (config.DATA_DIR), read at call time."""
    return Path(config.DATA_DIR)


def raw_dir() -> Path:
    """DATA_DIR/raw: downloaded source files."""
    d = data_dir() / "raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


def work_dir() -> Path:
    """DATA_DIR/work: derived tables shared between slices."""
    d = data_dir() / "work"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir(namespace: str) -> Path:
    """DATA_DIR/cache/lookups/<namespace>."""
    d = Path(config.CACHE_DIR) / "lookups" / namespace
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_variant_id(variant_id: str) -> tuple[str, int, str, str]:
    """Return (chrom_with_chr_prefix, pos, ref, alt) for ids like 'chr2-165991234-A-G' (chr prefix optional).

    Raises ValueError for malformed ids (callers are wrapped by `safe`).
    """
    m = _VID_RE.match(str(variant_id).strip())
    if not m:
        raise ValueError(f"bad variant_id: {variant_id!r}")
    chrom, pos, ref, alt = m.group(1).upper(), int(m.group(2)), m.group(3).upper(), m.group(4).upper()
    if chrom == "MT":
        chrom = "M"
    return f"chr{chrom}", pos, ref, alt


def canonical_id(variant_id: str) -> str:
    """Normalise to 'chrN-pos-ref-alt'."""
    c, p, r, a = parse_variant_id(variant_id)
    return f"{c}-{p}-{r}-{a}"


def write_atomic(path: Path, data: bytes | str) -> None:
    """Write `data` to `path` via a temp file in the same folder, then rename (atomic on one volume)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8") if isinstance(data, str) else data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _key_path(namespace: str, key: str) -> Path:
    safe_key = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    if len(safe_key) > 120:
        safe_key = safe_key[:100] + "_" + hashlib.sha1(key.encode()).hexdigest()[:12]
    return cache_dir(namespace) / f"{safe_key}.json"


def cache_get(namespace: str, key: str) -> Any | None:
    """Return the cached JSON value or None."""
    p = _key_path(namespace, key)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_put(namespace: str, key: str, value: Any) -> None:
    """Store a JSON-serialisable value (failures are ignored: the cache is best-effort)."""
    try:
        write_atomic(_key_path(namespace, key), json.dumps(value))
    except Exception:
        pass


def safe(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: never raise; return {"error": "<Type>: <msg>"} instead."""

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa: BLE001 - contract says never raise
            return {"error": f"{type(e).__name__}: {e}"}

    return wrapper
