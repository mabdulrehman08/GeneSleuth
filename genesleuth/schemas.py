"""Shared contract between Agent A (data + proof) and Agent B (agent + demo). Both agents keep this file byte-identical. Do not edit."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

Region = Literal["coding", "splice", "utr5", "utr3", "intron", "promoter", "intergenic", "other"]


class Variant(BaseModel):
    variant_id: str                      # "chr2-165991234-A-G" (GRCh38, 1-based, gnomAD-style with chr prefix)
    chrom: str                           # "chr2"
    pos: int
    ref: str
    alt: str
    gene: Optional[str] = None
    region: Region = "other"
    consequence: Optional[str] = None    # most severe consequence term (VEP / Sequence Ontology)
    genotype: Optional[str] = None       # "0/1" or "1/1"
    distance_to_tss: Optional[int] = None


class Phenotype(BaseModel):
    hpo_id: str                          # "HP:0001250"
    label: str                           # "Seizure"
    source_quote: Optional[str] = None   # text span from the referral letter


class Case(BaseModel):
    case_id: str                         # random hex; reveals nothing
    sample_id: str                       # 1000 Genomes background sample
    referral_pdf: str                    # path to the referral letter PDF
    suspects: list[Variant]              # filtered candidates, shuffled; the hidden variant is somewhere in here
    funnel: dict[str, int]               # e.g. {"variants_in_panel_regions": 13049, "rare": 812, "suspects": 205}
    panel_name: str = "Genetic epilepsy"


class CaseTruth(BaseModel):              # NEVER passed to the agent or shown before Reveal
    case_id: str
    hidden_variant_id: str
    gene: str
    condition: str
    clinvar_id: Optional[str] = None
    region: str = "other"
    true_phenotypes: list[Phenotype] = Field(default_factory=list)
    split: Literal["dev", "test", "demo"] = "test"


class DemoOption(BaseModel):
    option_id: str                       # ClinVar variation id
    gene: str
    region: Region
    condition: str
    label: str                           # short label for the judge's picker


class ToolCall(BaseModel):
    call_id: str
    tool: str
    args: dict
    result: dict
    result_summary: str
    artifact_path: Optional[str] = None  # e.g. AlphaGenome plot PNG


class Claim(BaseModel):
    claim_id: str
    variant_id: str
    text: str
    cited_call_ids: list[str]


class CheckVerdict(BaseModel):
    claim_id: str
    verdict: Literal["supported", "unsupported", "unsure"]
    confidence: float
    reason: str
    checker: Literal["code", "decisions_api", "fallback"]


class RankedSuspect(BaseModel):
    rank: int
    variant: Variant
    score: float
    tissue: Optional[str] = None         # ontology id of the decisive AlphaGenome call, if any
    summary: str
    claims: list[Claim] = Field(default_factory=list)
    verdicts: list[CheckVerdict] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    case_id: str
    mode: Literal["full", "alphagenome_only", "atlas_only", "gemini_only", "fixed_recipe"]
    status: Literal["ok", "error"]
    ranked: list[RankedSuspect]
    phenotypes: list[Phenotype] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    n_alphagenome_calls: int = 0
    n_tool_calls: int = 0
    n_claims_checked: int = 0
    n_claims_rejected: int = 0
    timings: dict[str, float] = Field(default_factory=dict)
    error: Optional[str] = None


class TraceEvent(BaseModel):
    case_id: str
    t: float                             # seconds since start
    step: Literal["case", "read_letter", "plan", "tool", "alphagenome", "claim", "check", "revise", "rank", "done", "error"]
    actor: str                           # "Data", "Gemini 4 Carbon", "Gemini 4 Neon", "Gemini 4 Hydrogen", "AlphaGenome", "Code checker", "Decisions API", "Managed Agent"
    summary: str                         # one human-readable line
    data: dict = Field(default_factory=dict)
