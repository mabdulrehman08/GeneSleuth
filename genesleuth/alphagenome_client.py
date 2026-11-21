"""Synchronous AlphaGenome 2 and Atlas interfaces for investigation and plotting."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256
import json
import os
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import BoundedSemaphore, Lock
from time import sleep

from genesleuth import config
from genesleuth.agent.errors import InvestigationError, safe_error
from genesleuth.agent.settings import AG_CONCURRENCY, ATLAS_WORKERS
from genesleuth.schemas import Variant


def score_variant(variant: Variant, tissue_ontology_id: str) -> dict:
    """Return one condition-specific result or a structured error."""
    if config.FAKE_MODE:
        digest = sha256(f"{variant.variant_id}/{tissue_ontology_id}".encode()).digest()
        effect = round(int.from_bytes(digest[:2], "big") / 65535, 3)
        tissue = next((item["name"] for item in list_tissues()
                       if item["ontology_id"] == tissue_ontology_id), tissue_ontology_id)
        return {
            "tissue": tissue_ontology_id, "tissue_name": tissue,
            "scores": {"SPLICE_SITE_USAGE": -effect}, "max_abs_effect": effect,
            "direction": "decrease", "gene_effects": {variant.gene: -effect} if variant.gene else {},
            "on_own_gene": bool(variant.gene), "raw_ref": None, "development": True,
        }
    try:
        return _score_live(variant, tissue_ontology_id)
    except Exception as error:
        return {"error": safe_error(error)}


def list_tissues(query: str | None = None) -> list[dict]:
    """List matching AlphaGenome reference condition names and ontology ids."""
    if config.FAKE_MODE:
        tissues = [
            {"ontology_id": config.BRAIN_TISSUE, "name": "brain"},
            {"ontology_id": config.BLOOD_TISSUE, "name": "blood"},
            {"ontology_id": "UBERON:0002037", "name": "cerebellum"},
            {"ontology_id": "UBERON:0000956", "name": "cerebral cortex"},
        ]
    else:
        tissues = _conditions()
    needle = (query or "").casefold()
    return [tissue for tissue in tissues if needle in tissue["name"].casefold()
            or needle in tissue["ontology_id"].casefold()]


def atlas_scores(variants: list[Variant]) -> dict[str, dict]:
    """Look up AlphaGenome Atlas (AG1) scores for supported candidate alleles."""
    if config.FAKE_MODE:
        return {
            variant.variant_id: {
                "avi": round(int.from_bytes(sha256(variant.variant_id.encode()).digest()[:2], "big") / 65535, 3),
                "top_features": ["splicing"], "splicing_share": 0.5, "development": True,
            }
            for variant in variants
        }
    return _atlas_live(variants)


def plot_variant(variant: Variant, tissue_ids: list[str], out_path: str) -> str:
    """Render reference and alternate tracks to a 1600 × 900 PNG."""
    if not config.FAKE_MODE:
        return _plot_live(variant, tissue_ids, out_path)
    from PIL import Image, ImageDraw

    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 900), "#f8fafc")
    canvas = ImageDraw.Draw(image)
    canvas.text((85, 60), f"{variant.gene or 'Variant'}   ·   {variant.variant_id}", fill="#14213d", font_size=40)
    canvas.text((85, 125), "DEVELOPMENT FIXTURE  /  illustrative tracks", fill="#9a3412", font_size=25)
    selected = tissue_ids[:2] or [config.BRAIN_TISSUE, config.BLOOD_TISSUE]
    for index, tissue in enumerate(selected):
        y = 225 + index * 315
        result = score_variant(variant, tissue)
        canvas.text((90, y), result["tissue_name"], fill="#14213d", font_size=35)
        canvas.rectangle((90, y + 68, 1510, y + 238), fill="white", outline="#cbd5e1", width=2)
        canvas.line([(115, y + 198), (355, y + 198), (375, y + 113), (830, y + 113),
                     (850, y + 198), (1480, y + 198)], fill="#1e40af", width=7)
        delta = round(result["max_abs_effect"] * 60)
        canvas.line([(115, y + 206), (355, y + 206), (395, y + 123 + delta),
                     (830, y + 123 + delta), (860, y + 206), (1480, y + 206)], fill="#b91c1c", width=7)
    canvas.text((90, 845), "REF · blue      ALT · red", fill="#14213d", font_size=27)
    image.save(output, format="PNG")
    return str(output)


SCORE_OUTPUTS = ("RNA_SEQ", "SPLICE_SITES", "SPLICE_SITE_USAGE", "SPLICE_JUNCTIONS")
_SCORE_SCALES = {"RNA_SEQ": 5.0, "SPLICE_SITES": 1.0, "SPLICE_SITE_USAGE": 1.0, "SPLICE_JUNCTIONS": 5.0}
_MODEL_TIMEOUT_S = 18
_CACHE_VERSION = "v2-2026-11-21"
_AG_POOL = ThreadPoolExecutor(max_workers=AG_CONCURRENCY, thread_name_prefix="alphagenome")
_AG_SLOTS = BoundedSemaphore(AG_CONCURRENCY)
_ATLAS_LOCK = Lock()
_PLOT_LOCK = Lock()


def _cache_path(namespace: str, *parts: str) -> Path:
    """Return a versioned cache name without exposing patient or allele identifiers as paths."""
    key = sha256(json.dumps([_CACHE_VERSION, *parts]).encode()).hexdigest()
    return config.CACHE_DIR / "alphagenome" / namespace / f"{key}.json"


def _read_cache(path: Path):
    """Read a completed cache entry and recover from an incomplete or invalid entry."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_cache(path: Path, value) -> None:
    """Write a cache entry atomically so concurrent readers only see complete data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(value, output, ensure_ascii=False, allow_nan=False)
            output.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def _model():
    """Create the documented AlphaGenome 2 model client on first use."""
    if not config.ALPHAGENOME_API_KEY:
        raise InvestigationError("AlphaGenome key is missing from .env")
    try:
        from alphagenome.models.v2 import dna_client
    except ImportError:
        raise InvestigationError("Install the AlphaGenome 2 Python SDK before live scoring") from None
    return dna_client.create(config.ALPHAGENOME_API_KEY, timeout=_MODEL_TIMEOUT_S)


@lru_cache(maxsize=1)
def _atlas_client():
    """Create the Atlas client using the same AlphaGenome credential."""
    if not config.ALPHAGENOME_API_KEY:
        raise InvestigationError("AlphaGenome key is missing from .env")
    try:
        from alphagenome.atlas import atlas
    except ImportError:
        raise InvestigationError("Install the Python SDK with AlphaGenome Atlas support") from None
    return atlas.create(config.ALPHAGENOME_API_KEY, timeout=_MODEL_TIMEOUT_S)


def _query(action):
    """Bound model concurrency and wait time, with one retry on throttling or unavailability."""
    for attempt in range(2):
        if not _AG_SLOTS.acquire(timeout=_MODEL_TIMEOUT_S):
            raise InvestigationError("AlphaGenome is busy")
        try:
            future = _AG_POOL.submit(action)
        except Exception:
            _AG_SLOTS.release()
            raise
        future.add_done_callback(lambda _: _AG_SLOTS.release())
        try:
            return future.result(timeout=_MODEL_TIMEOUT_S)
        except TimeoutError:
            future.cancel()
            raise InvestigationError("AlphaGenome request timed out") from None
        except Exception as error:
            code = getattr(error, "code", None)
            status = code() if callable(code) else None
            if getattr(status, "name", "") not in {"RESOURCE_EXHAUSTED", "UNAVAILABLE"}:
                raise
            if attempt == 1:
                raise InvestigationError(f"AlphaGenome request failed ({status.name})") from None
            sleep(1)


def _ag_variant(variant: Variant):
    """Convert a GRCh38 candidate with a 1-based position to an SDK variant."""
    from alphagenome.data import genome

    return genome.Variant(chromosome=variant.chrom, position=variant.pos,
                          reference_bases=variant.ref, alternate_bases=variant.alt)


@lru_cache(maxsize=1)
def _conditions() -> list[dict]:
    """Read and cache the available human reference conditions and observed outputs."""
    path = _cache_path("conditions", config.GENOME_BUILD)
    cached = _read_cache(path)
    if cached is not None:
        return cached
    model = _model()
    from alphagenome.models.v2 import dna_client

    data = _query(lambda: model.supported_conditions(dna_client.Organism.HOMO_SAPIENS))
    result = [{
        "ontology_id": str(row["condition"]),
        "name": str(row["biosample_name"]),
        "observed": [str(key) for key, value in row.items() if str(value) == "observed"],
    } for row in data.to_dict(orient="records")]
    _write_cache(path, result)
    return result


def _score_live(variant: Variant, tissue: str) -> dict:
    """Cache signed per-output maxima and the underlying per-gene score table."""
    path = _cache_path("score", variant.variant_id, variant.gene or "", tissue, *SCORE_OUTPUTS)
    cached = _read_cache(path)
    if cached is not None:
        return cached
    model = _model()
    from alphagenome.models.v2 import dna_client, variant_scorers

    ag_variant = _ag_variant(variant)
    interval = ag_variant.reference_interval.resize(dna_client.SEQUENCE_LENGTH_1MB)
    scorers = [variant_scorers.RECOMMENDED_VARIANT_SCORERS[name] for name in SCORE_OUTPUTS]
    scores = _query(lambda: model.score_variant(
        interval=interval, variant=ag_variant, condition=tissue, variant_scorers=scorers,
    ))
    frame = variant_scorers.tidy_scores([scores], match_gene_strand=True)
    clean = json.loads(frame.to_json(orient="records", double_precision=15))
    rows = [row for row in clean if row.get("raw_score") is not None and isfinite(row["raw_score"])]
    # Use observed results when available for a modality and label imputed-only modalities.
    preferred = {}
    for name in SCORE_OUTPUTS:
        candidates = [row for row in rows if row.get("output_type") == name]
        observed = [row for row in candidates if row.get("imputation_mode") == "observed"]
        if candidates:
            preferred[name] = observed or candidates
    peaks = {name: max(group, key=lambda row: abs(row["raw_score"])) for name, group in preferred.items()}
    if not peaks:
        raise InvestigationError("AlphaGenome returned no usable scores for this condition")
    signed = {name: float(row["raw_score"]) for name, row in peaks.items()}
    strongest = max(signed, key=lambda name: abs(signed[name]) / _SCORE_SCALES[name])
    combined = sum(abs(signed.get(name, 0.0)) for name in SCORE_OUTPUTS[1:]) / 5
    by_gene = {}
    for name, group in preferred.items():
        for row in group:
            gene, value = row.get("gene_name"), float(row["raw_score"])
            if gene:
                effects = by_gene.setdefault(gene, {})
                if name not in effects or abs(value) > abs(effects[name]):
                    effects[name] = value
    raw_path = path.with_name(path.stem + ".raw.json")
    _write_cache(raw_path, clean)
    largest = max(signed, key=lambda name: abs(signed[name]))
    winner = peaks[largest]
    tissue_name = winner.get("biosample_name") or tissue
    result = {
        "source": "AlphaGenome 2", "tissue": tissue, "tissue_name": tissue_name,
        "scores": signed, "splicing_score": combined,
        "normalized_effect": max(abs(signed[strongest]) / _SCORE_SCALES[strongest], combined),
        "max_abs_effect": max(abs(value) for value in signed.values()),
        "strongest_normalized_output": strongest, "strongest_normalized_gene": peaks[strongest].get("gene_name"),
        "max_effect_output": largest, "max_effect_gene": winner.get("gene_name"),
        "direction": "increase" if signed[largest] > 0 else "decrease" if signed[largest] < 0 else "unchanged",
        "gene_effects": by_gene, "on_own_gene": bool(variant.gene and variant.gene == winner.get("gene_name")),
        "imputation_modes": {name: row.get("imputation_mode") for name, row in peaks.items()},
        "raw_ref": str(raw_path),
    }
    _write_cache(path, result)
    return result


def _atlas_live(variants: list[Variant]) -> dict[str, dict]:
    """Load the Atlas model's actual AVI fields and cache successful SNV results."""
    outputs = {}
    missing = {}
    for variant in variants:
        identifier = variant.variant_id
        if len(variant.ref) != 1 or len(variant.alt) != 1 or {variant.ref, variant.alt} - set("ACGT"):
            outputs[identifier] = {"avi": None, "top_features": [], "splicing_share": None,
                                   "note": "AlphaGenome Atlas (AG1) covers SNVs"}
            continue
        path = _cache_path("atlas", identifier)
        cached = _read_cache(path)
        if cached is None:
            missing[identifier] = (variant, path)
        else:
            outputs[identifier] = cached
    if not missing:
        return outputs

    # Query sequential chunks so a timed-out segment does not start a second large fan-out.
    try:
        with _ATLAS_LOCK:
            model = _atlas_client()
            metadata = _query(model.scorer_metadata)
            keys = {str(key).casefold().replace("-", "_").replace(" ", "_"): key for key in metadata}
            score_name = next((keys[name] for name in ("avi", "avi_phred", "alphagenome_variant_impact")
                               if name in keys), None)
            if score_name is None:
                raise InvestigationError("AlphaGenome Atlas metadata did not expose an AVI scorer")
            feature_keys = [key for name, key in keys.items() if "avi" in name and
                            any(part in name for part in ("attribution", "contribution", "importance"))]
            requested = [score_name, *feature_keys]
            for start in range(0, len(missing), 50):
                subset = list(missing.values())[start:start + 50]
                ag_variants = [_ag_variant(variant) for variant, _ in subset]
                records = _query(lambda: model.query_variants(
                    ag_variants, requested_scorers=requested, max_workers=ATLAS_WORKERS, progress_bar=False))
                values = _atlas_records(records, score_name, feature_keys)
                for (variant, path), sdk_variant in zip(subset, ag_variants, strict=True):
                    result = values.get(str(sdk_variant)) or values.get(variant.variant_id)
                    if result is not None:
                        outputs[variant.variant_id] = result
                        _write_cache(path, result)
    except Exception as error:
        for identifier in missing.keys() - outputs.keys():
            outputs[identifier] = {"avi": None, "top_features": [], "splicing_share": None,
                                   "error": safe_error(error)}
    for identifier in missing.keys() - outputs.keys():
        outputs[identifier] = {"avi": None, "top_features": [], "splicing_share": None,
                               "error": "No variant-matched AVI result returned"}
    return outputs


def _atlas_records(records, score_name, feature_keys) -> dict[str, dict]:
    """Tie Atlas rows to their explicit ids and preserve feature values where provided."""
    import numpy as np

    avi = records[score_name]
    if "variant_id" not in avi.obs.columns:
        raise InvestigationError("AlphaGenome Atlas did not return variant ids for its AVI rows")
    result = {}
    for index, item in enumerate(avi.obs["variant_id"]):
        row = avi.X[index]
        values = np.asarray(row.toarray() if hasattr(row, "toarray") else row).flatten()
        numeric = [float(value) for value in values if isfinite(value)]
        if len(numeric) != 1:
            continue
        result[str(item)] = {
            "source": "AlphaGenome Atlas (AG1)", "avi": numeric[0], "top_features": [], "splicing_share": None,
        }
    for feature_key in feature_keys:
        info = records.get(feature_key)
        if info is None or "variant_id" not in info.obs.columns:
            continue
        for index, identifier in enumerate(info.obs["variant_id"]):
            value = result.get(str(identifier))
            if value is None:
                continue
            row = info.X[index]
            counts = np.asarray(row.toarray() if hasattr(row, "toarray") else row).flatten()
            features = sorted(
                ((str(name), float(weight)) for name, weight in zip(info.var_names, counts, strict=True)
                 if isfinite(weight)), key=lambda pair: -abs(pair[1]),
            )
            total = sum(abs(weight) for _, weight in features)
            value["top_features"] = [{"name": name, "weight": weight} for name, weight in features[:5]]
            if total:
                value["splicing_share"] = sum(abs(weight) for name, weight in features if "splic" in name.lower()) / total
    return result


def _plot_live(variant: Variant, tissue_ids: list[str], out_path: str) -> str:
    """Render matched REF/ALT coverage and splice arcs from AlphaGenome 2 predictions."""
    os.environ.setdefault("MPLCONFIGDIR", str(config.CACHE_DIR / "matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from PIL import Image
    from alphagenome.models.v2 import dna_client
    from alphagenome.visualization import plot_components

    tissues = list(dict.fromkeys(tissue_ids or [config.BRAIN_TISSUE, config.BLOOD_TISSUE]))[:2]
    model = _model()
    ag_variant = _ag_variant(variant)
    interval = ag_variant.reference_interval.resize(dna_client.SEQUENCE_LENGTH_1MB)
    window = ag_variant.reference_interval.resize(8_192)
    output = Path(out_path)
    cache_key = _cache_path("plots", variant.variant_id, *tissues, "RNA_SEQ", "SPLICE_JUNCTIONS")
    cached_png = cache_key.with_suffix(".png")
    output.parent.mkdir(parents=True, exist_ok=True)

    with _PLOT_LOCK:
        if not cached_png.exists():
            parts = []
            for tissue in tissues:
                prediction = _query(lambda: model.predict_variant(
                    interval=interval, variant=ag_variant, condition=tissue,
                    requested_outputs=[dna_client.OutputType.RNA_SEQ, dna_client.OutputType.SPLICE_JUNCTIONS],
                ))
                ref, alt = prediction.reference, prediction.alternate
                label = tissue.replace("{", "").replace("}", "")
                if ref.rna_seq is None or alt.rna_seq is None:
                    raise InvestigationError("AlphaGenome returned no RNA-seq tracks for the requested condition")
                parts.append(plot_components.OverlaidTracks(
                    tdata={"REF": ref.rna_seq, "ALT": alt.rna_seq},
                    colors={"REF": "#1e40af", "ALT": "#b91c1c"},
                    ylabel_template=f"{label} · RNA-seq",
                ))
                for allele, data in (("REF", ref.splice_junctions), ("ALT", alt.splice_junctions)):
                    if data is not None and data.values.size and data.values.shape[-1] > 0:
                        parts.append(plot_components.Sashimi(data, ylabel_template=f"{label} · {allele} junctions"))
            figure = plot_components.plot(parts, interval=window,
                                          annotations=[plot_components.VariantAnnotation([ag_variant])])
            try:
                figure.set_size_inches(16, 9)
                figure.suptitle(f"{variant.gene or 'Variant'}  ·  {variant.variant_id}   |   AlphaGenome 2",
                                fontsize=18)
                cached_png.parent.mkdir(parents=True, exist_ok=True)
                with NamedTemporaryFile(dir=cached_png.parent, suffix=".png", delete=False) as buffer:
                    temporary = Path(buffer.name)
                try:
                    figure.savefig(temporary, dpi=100, format="png")
                    with Image.open(temporary) as check:
                        if check.size != (1600, 900):
                            raise InvestigationError("AlphaGenome plot has unexpected dimensions")
                    temporary.replace(cached_png)
                finally:
                    temporary.unlink(missing_ok=True)
            finally:
                plt.close(figure)
    if output.resolve() != cached_png.resolve():
        output.write_bytes(cached_png.read_bytes())
    return str(output)
