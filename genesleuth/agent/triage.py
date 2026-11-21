"""Build one shared evidence input for variant triage and tissue routing."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from time import monotonic

from genesleuth import config
from genesleuth.agent.errors import InvestigationError
from genesleuth.agent.settings import CONFIDENCE_MIN, DECISION_MAX_QUESTIONS, TISSUE_CANDIDATES
from genesleuth.gemini_clients import decide
from genesleuth.schemas import Phenotype, Variant


@dataclass
class Triage:
    """The sorted candidate context and tissue recommendations passed to Neon."""
    rows: list[dict]
    tissues: list[dict]
    route: dict | None
    frequencies: dict[str, dict]
    phenotype_matches: dict[str, dict]


def candidate_row(variant: Variant) -> dict:
    """Select the same candidate columns for the investigator and its baselines."""
    return variant.model_dump(include={"variant_id", "gene", "region", "consequence", "distance_to_tss"})


def _route_options(plan: dict, tissue_list: list[dict]) -> list[dict]:
    """Prefer requested observed conditions and include both comparison defaults."""
    indexed = {condition["ontology_id"]: condition for condition in tissue_list}
    result = [indexed[value] for value in (config.BRAIN_TISSUE, config.BLOOD_TISSUE) if value in indexed]
    selected = {item["ontology_id"] for item in result}
    terms = [*plan.get("tissues_to_test", []), "cerebral cortex", "cerebellum", "hippocampus",
             "glutamatergic neuron", "astrocyte", "brain", "blood"]
    for query in terms:
        query = query.strip().casefold()
        if not query:
            continue
        matches = [item for item in tissue_list if item["ontology_id"] not in selected and
                   (query in item["name"].casefold() or query == item["ontology_id"].casefold())]
        matches.sort(key=lambda item: (
            query != item["name"].casefold(),
            -sum("rna_seq" in name.lower() or "splice" in name.lower() for name in item.get("observed", [])),
            len(item["name"]),
        ))
        for condition in matches[:2]:
            if len(result) >= TISSUE_CANDIDATES:
                return result
            result.append(condition)
            selected.add(condition["ontology_id"])
    return result


def _cached_frequency(variant_id: str) -> dict:
    """Use precomputed evidence so triage never fans out to gnomAD."""
    try:
        from genesleuth.lookups._common import cache_get, canonical_id
        from genesleuth.lookups.popfreq import _stored_af

        key = canonical_id(variant_id)
        value = cache_get("popfreq", key)
        if value is not None:
            return value
        annotation = _stored_af(key)
        if annotation is not None:
            return annotation
    except (ImportError, OSError, ValueError):
        pass
    return {"found": False, "source": "unavailable", "af": None, "note": "No cached frequency evidence"}


async def triage_candidates(
    variants: list[Variant], phenotypes: list[Phenotype], plan: dict, atlas: dict,
    tissue_list: list[dict], emit,
) -> Triage:
    """Get cheap evidence for each suspect and submit one batch whenever it fits."""
    from genesleuth.lookups.api import phenotype_match

    hpo_ids = list(dict.fromkeys(item.hpo_id for item in phenotypes))
    genes = sorted({variant.gene for variant in variants if variant.gene})
    gate = asyncio.Semaphore(8)

    async def lookup(function, *args):
        """Bound local lookup concurrency for batched evidence collection."""
        async with gate:
            return await asyncio.to_thread(function, *args)

    freq, matches = await asyncio.gather(
        asyncio.gather(*(lookup(_cached_frequency, item.variant_id) for item in variants)),
        asyncio.gather(*(lookup(phenotype_match, gene, hpo_ids) for gene in genes)),
    )
    frequencies = dict(zip((item.variant_id for item in variants), freq, strict=True))
    by_gene = dict(zip(genes, matches, strict=True))
    rows = []
    for variant in variants:
        pop = frequencies[variant.variant_id]
        scores = atlas.get(variant.variant_id, {})
        rows.append({
            **candidate_row(variant), "frequency": pop.get("af"), "frequency_source": pop.get("source"),
            "phenotype_match": by_gene.get(variant.gene, {}).get("score"),
            "AVI": scores.get("avi"), "top_atlas_feature": next(iter(scores.get("top_features") or []), None),
        })
    tissues = _route_options(plan, tissue_list)
    if not tissues:
        raise InvestigationError("No verified AlphaGenome reference conditions are available")
    tissue_keys = {f"t_{index}": item for index, item in enumerate(tissues)}
    route = None
    route_confidence = None
    start = monotonic()
    cursor = 0
    while cursor < len(rows):
        limit = DECISION_MAX_QUESTIONS - (cursor == 0)
        chunk = rows[cursor:cursor + limit]
        questions = {
            f"s_{index}": {
                "type": "noul",
                "instructions": (
                    f"For only suspect index {index} ({row['variant_id']}), given the observed patient "
                    "phenotypes and this variant's rarity, region, phenotype match and AVI evidence, "
                    "is it worth a live, tissue-specific AlphaGenome call?"
                ),
            }
            for index, row in enumerate(chunk, start=cursor)
        }
        if cursor == 0:
            questions["tissue"] = {
                "type": "choice", "instructions": "Which condition is most informative for the first AlphaGenome score?",
                "criteria": {**{key: f"{value['name']} ({value['ontology_id']})"
                                for key, value in tissue_keys.items()},
                             "other": "The case suggests searching for a different condition"},
            }
        data = {
            "phenotypes": [item.model_dump(exclude={"source_quote"}) for item in phenotypes],
            "hypothesis_plan": {key: value for key, value in plan.items() if key != "reader_model"},
            "suspects": [{"index": index, **row} for index, row in enumerate(chunk, start=cursor)],
        }
        answers = await asyncio.to_thread(decide, json.dumps(data, ensure_ascii=False, default=str), questions)
        for index, row in enumerate(chunk, start=cursor):
            answer = answers.get(f"s_{index}")
            probability = getattr(answer, "noul", None)
            confidence = getattr(answer, "confidence", None)
            valid = isinstance(probability, (int, float)) and 0 <= probability <= 1
            certainty = isinstance(confidence, (int, float)) and CONFIDENCE_MIN <= confidence <= 1
            row["triage_p"] = probability if valid else None
            row["triage_confidence"] = confidence if isinstance(confidence, (int, float)) and 0 <= confidence <= 1 else None
            row["triage_uncertain"] = not (valid and certainty)
        if cursor == 0:
            decision = answers.get("tissue")
            route_confidence = getattr(decision, "confidence", None)
            if isinstance(route_confidence, (int, float)) and CONFIDENCE_MIN <= route_confidence <= 1:
                route = tissue_keys.get(getattr(decision, "choice", None))
        cursor += len(chunk)

    def order(row):
        """Give uncertain scores a neutral priority so Neon can inspect them."""
        probability = 0.5 if row["triage_uncertain"] else row["triage_p"]
        return (-probability, -float(row["AVI"] or 0), row["variant_id"])

    rows.sort(key=order)
    elapsed = monotonic() - start
    name = route["name"] if route else "Neon will choose"
    emit("plan", "Decisions API", f"Decision 1 triaged {len(rows)} suspects in {elapsed:.1f} s. Tissue: {name}",
         n_suspects=len(rows), routed_tissue=route["ontology_id"] if route else None,
         routed_tissue_name=route["name"] if route else None, route_confidence=route_confidence, elapsed_s=elapsed,
         n_uncertain=sum(row["triage_uncertain"] for row in rows))
    return Triage(rows=rows, tissues=tissues, route=route, frequencies=frequencies, phenotype_matches=by_gene)
