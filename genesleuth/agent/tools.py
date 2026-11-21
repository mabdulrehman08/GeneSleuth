"""Native investigator tool declarations and a per-case evidence ledger."""
from __future__ import annotations

import asyncio
import json
from hashlib import sha256

from pydantic import BaseModel, Field, ValidationError

from genesleuth import config
from genesleuth.agent.errors import InvestigationError, safe_error
from genesleuth.agent.settings import MAX_PLOTS, PROFILE_LIMITS
from genesleuth.alphagenome_client import plot_variant, score_variant
from genesleuth.gemini_clients import structured
from genesleuth.schemas import Case, Phenotype, ToolCall


class ProposedClaim(BaseModel):
    """Evidence statement submitted by the investigator for checking."""
    text: str = Field(min_length=1, max_length=600)
    cited_call_ids: list[str] = Field(max_length=8)


class Candidate(BaseModel):
    """One native submitted shortlist entry and its evidence statements."""
    variant_id: str
    score: float = Field(ge=0, le=1)
    tissue: str | None = None
    summary: str = Field(max_length=600)
    claims: list[ProposedClaim] = Field(max_length=4)


class Report(BaseModel):
    """The only native finish operation for a ranked investigation."""
    items: list[Candidate] = Field(min_length=1, max_length=10)


class GenomeSummary(BaseModel):
    """Hydrogen's compact description of one condition-specific score."""
    summary: str
    max_abs_effect: float
    direction: str
    on_own_gene: bool


HYDROGEN_INSTRUCTION = (
    "Summarize this AlphaGenome output for a geneticist in at most 60 words: tissue, output types, "
    "the direction and size of the largest effects with numbers copied exactly as given, and whether "
    "the largest effect is on the variant's own gene. Return JSON {summary, max_abs_effect, direction, "
    "on_own_gene: bool}."
)


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Create an Interactions-native function declaration."""
    return {
        "type": "function", "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


_TEXT = {"type": "string"}
_TEXT_LIST = {"type": "array", "items": _TEXT}
TOOL_DECLARATIONS = [
    _tool("list_suspects", "Page triaged candidates, with optional region or gene filters.",
          {"region": _TEXT, "gene": _TEXT, "limit": {"type": "integer"}, "offset": {"type": "integer"}}, []),
    _tool("region_context", "Read the annotated region and nearby gene context of a candidate.",
          {"variant_id": _TEXT}, ["variant_id"]),
    _tool("population_frequency", "Look up the gnomAD population frequency bucket for a candidate.",
          {"variant_id": _TEXT}, ["variant_id"]),
    _tool("gene_phenotypes", "Look up phenotype associations for a candidate gene.", {"gene": _TEXT}, ["gene"]),
    _tool("phenotype_match", "Measure semantic match to this patient's HPO terms.", {"gene": _TEXT}, ["gene"]),
    _tool("atlas_lookup", "Read AlphaGenome Atlas (AG1) AVI scores and available feature attributions.",
          {"variant_ids": _TEXT_LIST}, ["variant_ids"]),
    _tool("search_tissues", "Find available AlphaGenome 2 reference conditions by name or ontology id.",
          {"query": _TEXT}, ["query"]),
    _tool("alphagenome_score", "Use one score-budget slot on a single candidate and condition.",
          {"variant_id": _TEXT, "tissue_ontology_id": _TEXT}, ["variant_id", "tissue_ontology_id"]),
    _tool("alphagenome_plot", "Compare REF and ALT tracks in one or two conditions after ranking.",
          {"variant_id": _TEXT, "tissue_ids": _TEXT_LIST}, ["variant_id", "tissue_ids"]),
    _tool("submit_report", "Submit the unique shortlist and specific claims citing tool-call ids.",
          {
              "items": {"type": "array", "items": {
                  "type": "object",
                  "properties": {
                      "variant_id": _TEXT, "score": {"type": "number"}, "tissue": _TEXT,
                      "summary": _TEXT, "claims": {"type": "array", "items": {
                          "type": "object", "properties": {"text": _TEXT, "cited_call_ids": _TEXT_LIST},
                          "required": ["text", "cited_call_ids"],
                      }},
                  },
                  "required": ["variant_id", "score", "summary", "claims"],
              }},
          }, ["items"]),
]


class ToolLedger:
    """Execute bounded, candidate-scoped tools and record structured evidence."""

    def __init__(self, case: Case, holdout: set[str], phenotypes: list[Phenotype],
                 rows: list[dict], atlas: dict, tissue_list: list[dict], profile: str, emit,
                 frequencies: dict | None = None, phenotype_matches: dict | None = None,
                 previous_calls: list[ToolCall] | None = None):
        """Create one budget and appendable evidence ledger for an investigation turn."""
        self.case_id = case.case_id
        self.variants = {item.variant_id: item for item in case.suspects}
        self.genes = {item.gene for item in case.suspects if item.gene}
        self.holdout = frozenset(holdout)
        self.hpo_ids = list(dict.fromkeys(item.hpo_id for item in phenotypes))
        self.rows = rows
        self.atlas = atlas
        self.tissues = {item["ontology_id"]: item for item in tissue_list}
        self.frequencies = frequencies or {}
        self.phenotype_matches = phenotype_matches or {}
        self.emit = emit
        self.limits = PROFILE_LIMITS[profile]
        self.calls = list(previous_calls or [])
        self.book = {call.call_id: call for call in self.calls}
        self._next_id = len(self.calls) + 1
        self.score_count = 0
        self.tool_count = 0
        self.plot_count = 0
        self._score_cache = {}
        self._score_tasks = {}
        self._closed = False

    def close(self) -> None:
        """Stop accepting computational tools while allowing final report submission."""
        self._closed = True

    def count(self, tool: str) -> int:
        """Count all recorded calls to a tool including the prior review ledger."""
        return sum(call.tool == tool for call in self.calls)

    async def execute(self, tool: str, args: dict) -> dict:
        """Run a declared lookup and create a citation identifier for its result."""
        if tool == "clinvar_lookup":
            return {"disabled": True, "note": "ClinVar lookup off to prevent leakage"}
        handler = {
            "list_suspects": self._list, "region_context": self._region, "population_frequency": self._frequency,
            "gene_phenotypes": self._gene_phenotypes, "phenotype_match": self._phenotype,
            "atlas_lookup": self._atlas, "search_tissues": self._find_tissue,
            "alphagenome_score": self._score, "alphagenome_plot": self._plot,
        }.get(tool)
        if handler is None:
            return {"error": "Unknown evidence tool"}
        if self._closed or self.tool_count >= self.limits["tool_calls"]:
            return {"error": "budget exhausted"}
        self.tool_count += 1
        identifier = f"c{self._next_id}"
        self._next_id += 1
        try:
            data, summary, artifact = await handler(**args)
        except (TypeError, ValueError, KeyError):
            data, summary, artifact = {"error": "Invalid arguments for this tool"}, "Invalid tool arguments", None
        except Exception as error:
            message = safe_error(error)
            data, summary, artifact = {"error": message}, message, None
        call = ToolCall(call_id=identifier, tool=tool, args=args, result=data,
                        result_summary=summary, artifact_path=artifact)
        self.calls.append(call)
        self.book[identifier] = call
        step = "alphagenome" if tool in {"alphagenome_score", "alphagenome_plot"} else "tool"
        actor = "AlphaGenome" if step == "alphagenome" else "Gemini 4 Neon"
        self.emit(step, actor, summary, call_id=identifier, tool=tool, args=args, artifact_path=artifact,
                  n_tool_calls=len(self.calls), n_alphagenome_calls=self.score_count,
                  alphagenome_budget=self.limits["score_calls"], **({"error": data["error"]} if "error" in data else {}))
        return {"call_id": identifier, "result": {key: val for key, val in data.items() if key != "raw_ref"},
                "summary": summary}

    async def _list(self, region=None, gene=None, limit=50, offset=0):
        """Read a bounded page of the triage-ranked suspect list."""
        filtered = [row for row in self.rows if (region is None or row["region"] == region)
                    and (gene is None or row["gene"] == gene)]
        limit, offset = min(50, max(1, int(limit))), max(0, int(offset))
        return {"items": filtered[offset:offset + limit], "total": len(filtered),
                "offset": offset}, f"Read a suspect page from {len(filtered)} matching candidates", None

    async def _region(self, variant_id: str):
        """Read external annotations only for a known candidate."""
        from genesleuth.lookups.api import region_context
        variant = self.variants[variant_id]
        data = await asyncio.to_thread(region_context, variant_id)
        canonical = {"gene": variant.gene, "region": variant.region, "consequence": variant.consequence,
                     "distance_to_tss": variant.distance_to_tss}
        return (canonical if "error" in data else data), f"Read region context for {variant_id}", None

    async def _frequency(self, variant_id: str):
        """Read the precomputed lookup or find frequency for a known candidate."""
        from genesleuth.lookups.api import population_frequency
        self.variants[variant_id]
        value = self.frequencies.get(variant_id)
        if value is None:
            value = await asyncio.to_thread(population_frequency, variant_id)
        return value, f"Read population frequency for {variant_id}", None

    async def _gene_phenotypes(self, gene: str):
        """Read established ontology annotations for a candidate gene."""
        from genesleuth.lookups.api import gene_phenotypes
        if gene not in self.genes:
            raise ValueError("Unknown gene")
        result = await asyncio.to_thread(gene_phenotypes, gene)
        return result, f"Read phenotype annotations for {gene}", None

    async def _phenotype(self, gene: str):
        """Return semantic phenotype matching for a candidate gene."""
        from genesleuth.lookups.api import phenotype_match
        if gene not in self.genes:
            raise ValueError("Unknown gene")
        result = self.phenotype_matches.get(gene)
        if result is None:
            result = await asyncio.to_thread(phenotype_match, gene, self.hpo_ids)
        return result, f"Compared {gene} to the patient's HPO findings", None

    async def _atlas(self, variant_ids: list[str]):
        """Retrieve precomputed Atlas rows for a small candidate group."""
        ids = list(dict.fromkeys(variant_ids))[:30]
        if any(identifier not in self.variants for identifier in ids):
            raise ValueError("Unknown variant")
        return {"variants": {identifier: self.atlas.get(identifier, {"avi": None}) for identifier in ids}}, (
            f"Read AlphaGenome Atlas (AG1) evidence for {len(ids)} variants"
        ), None

    async def _find_tissue(self, query: str):
        """Search AlphaGenome condition names and ids without spending predictions."""
        needle = query.strip().casefold()
        matches = [item for item in self.tissues.values()
                   if needle in item["name"].casefold() or needle in item["ontology_id"].casefold()]
        return {"tissues": matches[:15]}, f"Found {len(matches)} reference conditions for {query[:60]}", None

    async def _score(self, variant_id: str, tissue_ontology_id: str):
        """Deduplicate parallel scoring requests and enforce the configured budget."""
        variant = self.variants[variant_id]
        tissue = self.tissues[tissue_ontology_id]
        key = (variant_id, tissue_ontology_id)
        if key not in self._score_cache:
            if key not in self._score_tasks:
                if self.score_count >= self.limits["score_calls"]:
                    return {"error": "budget exhausted"}, "AlphaGenome score budget exhausted", None
                self.score_count += 1
                self._score_tasks[key] = asyncio.create_task(self._run_score(variant, tissue))
            task = self._score_tasks[key]
            try:
                self._score_cache[key] = await task
            finally:
                self._score_tasks.pop(key, None)
        return self._score_cache[key]

    async def _run_score(self, variant, tissue):
        """Fetch raw AlphaGenome evidence, then request a bounded Hydrogen summary."""
        condition = tissue["ontology_id"]
        data = await asyncio.to_thread(score_variant, variant, condition)
        if "error" in data:
            return data, f"AlphaGenome could not score {variant.variant_id} in {tissue['name']}", None
        numbers = ", ".join(f"{key} {value}" for key, value in data["scores"].items())
        summary = f"{tissue['name']}: {numbers}."
        compact = {key: value for key, value in data.items() if key not in {"raw_ref", "gene_effects"}}
        compact["candidate_gene"] = variant.gene
        try:
            raw = await asyncio.to_thread(
                structured, config.HYDROGEN, json.dumps(compact), GenomeSummary.model_json_schema(),
                thinking="low", instruction=HYDROGEN_INSTRUCTION,
            )
            worker = GenomeSummary.model_validate(raw)
            if (len(worker.summary.split()) <= 60 and worker.max_abs_effect == data["max_abs_effect"]
                    and worker.direction == data["direction"] and worker.on_own_gene == data["on_own_gene"]):
                summary = worker.summary
            self.emit("tool", "Gemini 4 Hydrogen", f"Summarized AlphaGenome evidence for {variant.variant_id}",
                      variant_id=variant.variant_id, tissue_ontology_id=condition)
        except (InvestigationError, ValidationError) as error:
            self.emit("tool", "Gemini 4 Hydrogen", "Hydrogen summary unavailable. Using the structured score fields.",
                      variant_id=variant.variant_id, tissue_ontology_id=condition, error=safe_error(error))
        return data, f"Scored {variant.variant_id}. {summary}", None

    async def _plot(self, variant_id: str, tissue_ids: list[str]):
        """Render a bounded tissue comparison and attach the PNG to the ledger."""
        variant = self.variants[variant_id]
        ids = list(dict.fromkeys(tissue_ids))
        if not 1 <= len(ids) <= 2 or any(identifier not in self.tissues for identifier in ids):
            raise ValueError("A plot needs one or two known conditions")
        if self.plot_count >= MAX_PLOTS:
            return {"error": "budget exhausted"}, "AlphaGenome plot budget exhausted", None
        self.plot_count += 1
        digest = sha256(json.dumps([self.case_id, variant_id, ids]).encode()).hexdigest()[:24]
        path = config.CACHE_DIR / "plots" / f"{digest}.png"
        plotted = await asyncio.to_thread(plot_variant, variant, ids, str(path))
        return {"variant_id": variant_id, "tissue_ids": ids,
                "tissue_names": [self.tissues[identifier]["name"] for identifier in ids]}, (
            f"Rendered AlphaGenome reference and alternate tracks for {variant_id}"
        ), plotted
