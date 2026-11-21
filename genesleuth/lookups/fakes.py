"""Fake lookups for development (FAKE_MODE=1) so the agent side is never blocked on real data.

Feature: realistic, deterministic stand-ins for the six lookups in genesleuth/lookups/api.py.
Gene coordinates, phenotypes and frequencies are ILLUSTRATIVE only (rounded, not real measurements).
Use cases: agent development, UI work, tests that must run without network or data files.
Never used in benchmark or demo runs (those assert FAKE_MODE is off).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from ._common import canonical_id, parse_variant_id

# gene -> (chrom, start, end, strand, tss, ensembl_gene)   (rounded GRCh38, illustrative)
_GENES: dict[str, tuple[str, int, int, str, int, str]] = {
    "SCN1A": ("chr2", 165991000, 166149000, "-", 166149000, "ENSG00000144285"),
    "SCN2A": ("chr2", 165239000, 165392000, "+", 165239000, "ENSG00000136531"),
    "KCNQ2": ("chr20", 63400000, 63472000, "-", 63472000, "ENSG00000075043"),
    "STXBP1": ("chr9", 127585000, 127700000, "+", 127585000, "ENSG00000136854"),
    "DNM1": ("chr9", 128200000, 128260000, "+", 128200000, "ENSG00000106976"),
    "TSC2": ("chr16", 2047000, 2089000, "+", 2047000, "ENSG00000103197"),
    "CDKL5": ("chrX", 18425000, 18652000, "+", 18425000, "ENSG00000008086"),
}

_PHENO: dict[str, dict[str, Any]] = {
    "SCN1A": {
        "diseases": [{"id": "OMIM:607208", "name": "Developmental and epileptic encephalopathy 6B (Dravet syndrome)"},
                     {"id": "OMIM:604403", "name": "Generalized epilepsy with febrile seizures plus, type 2"}],
        "hpo": [("HP:0001250", "Seizure"), ("HP:0002373", "Febrile seizure (within the age range of 3 months to 6 years)"),
                ("HP:0001263", "Global developmental delay"), ("HP:0002063", "Rigidity"),
                ("HP:0001251", "Ataxia"), ("HP:0002123", "Generalized myoclonic seizure")],
    },
    "KCNQ2": {
        "diseases": [{"id": "OMIM:613720", "name": "Developmental and epileptic encephalopathy 7"},
                     {"id": "OMIM:121200", "name": "Seizures, benign familial neonatal, 1"}],
        "hpo": [("HP:0001250", "Seizure"), ("HP:0001336", "Myoclonus"), ("HP:0001263", "Global developmental delay"),
                ("HP:0002521", "Hypsarrhythmia"), ("HP:0001252", "Hypotonia")],
    },
    "DNM1": {
        "diseases": [{"id": "OMIM:616346", "name": "Developmental and epileptic encephalopathy 31"}],
        "hpo": [("HP:0001250", "Seizure"), ("HP:0002521", "Hypsarrhythmia"), ("HP:0001249", "Intellectual disability"),
                ("HP:0001252", "Hypotonia"), ("HP:0001263", "Global developmental delay")],
    },
    "STXBP1": {
        "diseases": [{"id": "OMIM:612164", "name": "Developmental and epileptic encephalopathy 4"}],
        "hpo": [("HP:0001250", "Seizure"), ("HP:0001249", "Intellectual disability"), ("HP:0001337", "Tremor"),
                ("HP:0002521", "Hypsarrhythmia")],
    },
    "TSC2": {
        "diseases": [{"id": "OMIM:613254", "name": "Tuberous sclerosis-2"}],
        "hpo": [("HP:0001250", "Seizure"), ("HP:0000957", "Cafe-au-lait spot"), ("HP:0009592", "Astrocytoma"),
                ("HP:0001249", "Intellectual disability")],
    },
}
_PARENT = {  # tiny fake ontology: child -> parent (enough for phenotype_match fakes)
    "HP:0002373": "HP:0001250", "HP:0002123": "HP:0001250", "HP:0002521": "HP:0001250",
    "HP:0001336": "HP:0001250", "HP:0001263": "HP:0001249", "HP:0001252": "HP:0001290",
}
_TERMS = [
    ("HP:0001250", "Seizure", ["Epileptic seizure", "Seizures", "Convulsions"]),
    ("HP:0002373", "Febrile seizure (within the age range of 3 months to 6 years)", ["Febrile convulsion", "Fever-induced seizure"]),
    ("HP:0002521", "Hypsarrhythmia", ["Infantile spasms EEG pattern"]),
    ("HP:0001263", "Global developmental delay", ["Developmental delay", "Delayed development"]),
    ("HP:0001249", "Intellectual disability", ["Mental retardation", "Cognitive impairment"]),
    ("HP:0001252", "Hypotonia", ["Low muscle tone", "Floppy infant"]),
    ("HP:0001251", "Ataxia", ["Incoordination", "Unsteady gait"]),
    ("HP:0001336", "Myoclonus", ["Muscle jerks"]),
    ("HP:0002123", "Generalized myoclonic seizure", ["Myoclonic jerks"]),
    ("HP:0007359", "Focal-onset seizure", ["Partial seizure", "Focal seizure"]),
    ("HP:0002069", "Bilateral tonic-clonic seizure", ["Grand mal seizure", "Generalized tonic-clonic seizure"]),
    ("HP:0011097", "Epileptic spasm", ["Infantile spasms", "West syndrome spasms"]),
    ("HP:0001320", "Cerebellar vermis hypoplasia", []),
    ("HP:0000750", "Delayed speech and language development", ["Speech delay", "Language delay"]),
    ("HP:0000717", "Autism", ["Autistic behavior"]),
    ("HP:0001289", "Confusion", []),
    ("HP:0002353", "EEG abnormality", ["Abnormal EEG"]),
    ("HP:0100543", "Cognitive impairment", ["Cognitive deficit"]),
    ("HP:0001290", "Generalized hypotonia", []),
    ("HP:0000252", "Microcephaly", ["Small head"]),
]


def _h(s: str) -> int:
    return int(hashlib.sha1(s.encode()).hexdigest()[:8], 16)


def _gene_at(chrom: str, pos: int) -> str | None:
    for g, (c, s, e, *_r) in _GENES.items():
        if c == chrom and s - 10000 <= pos <= e + 10000:
            return g
    return None


def region_context(variant_id: str) -> dict:
    """Fake region annotation (gene lookup by rounded coordinates; deterministic region otherwise)."""
    vid = canonical_id(variant_id)
    chrom, pos, ref, alt = parse_variant_id(vid)
    gene = _gene_at(chrom, pos)
    if gene is None:
        return {"variant_id": vid, "gene": None, "region": "intergenic", "consequence": "intergenic_variant",
                "distance_to_tss": None, "exon": None, "intron": None, "nearby_genes": [], "source": "fake"}
    c, s, e, strand, tss, ens = _GENES[gene]
    regions = ["intron", "intron", "splice", "coding", "utr5", "utr3", "promoter"]
    region = regions[_h(vid) % len(regions)]
    cons = {"intron": "intron_variant", "splice": "splice_region_variant", "coding": "missense_variant",
            "utr5": "5_prime_UTR_variant", "utr3": "3_prime_UTR_variant", "promoter": "upstream_gene_variant"}[region]
    dist = abs(pos - tss) if strand == "+" else abs(tss - pos)
    n = 1 + _h(vid + "n") % 26
    return {"variant_id": vid, "gene": gene, "region": region, "consequence": cons, "distance_to_tss": dist,
            "exon": n if region in ("coding", "splice") else None,
            "intron": n if region == "intron" else None,
            "strand": strand, "nearby_genes": [g for g in _GENES if g != gene and _GENES[g][0] == chrom][:3],
            "source": "fake"}


def population_frequency(variant_id: str) -> dict:
    """Fake gnomAD-style frequency: ~70% of ids are 'not observed', the rest rare."""
    vid = canonical_id(variant_id)
    h = _h(vid)
    if h % 10 < 7:
        return {"found": False, "source": "fake", "af": None, "ac": None, "an": None, "note": "not observed in gnomAD v4.1 (fake)"}
    an = 152000
    ac = 1 + h % 40
    return {"found": True, "source": "fake", "af": ac / an, "ac": ac, "an": an}


_FAKE_CLINVAR = {
    "chr2-165991234-A-G": {"significance": "Pathogenic", "conditions": ["Dravet syndrome"], "review_status": "criteria provided, single submitter", "stars": 1},
    "chr2-166037775-C-A": {"significance": "Pathogenic", "conditions": ["Severe myoclonic epilepsy in infancy"], "review_status": "criteria provided, multiple submitters, no conflicts", "stars": 2},
    "chr20-63413582-C-T": {"significance": "Pathogenic", "conditions": ["Early-infantile DEE"], "review_status": "criteria provided, single submitter", "stars": 1},
    "chr16-2048755-T-C": {"significance": "Pathogenic", "conditions": ["Tuberous sclerosis 2"], "review_status": "criteria provided, multiple submitters, no conflicts", "stars": 2},
    "chr9-128225994-G-A": {"significance": "Pathogenic", "conditions": ["Developmental and epileptic encephalopathy 31"], "review_status": "criteria provided, single submitter", "stars": 1},
}


def clinvar_lookup(variant_id: str, holdout: set[str] | None = None, enabled: bool = False) -> dict:
    """Fake ClinVar: disabled by default exactly like the real one."""
    if not enabled:
        return {"disabled": True, "note": "ClinVar lookup off to prevent leakage"}
    vid = canonical_id(variant_id)
    if holdout and vid in {canonical_id(h) for h in holdout if re.match(r"^(chr)?\w+-\d+-", str(h))}:
        return {"found": False, "note": "not in ClinVar"}
    rec = _FAKE_CLINVAR.get(vid)
    if not rec:
        return {"found": False, "note": "not in ClinVar"}
    return {"found": True, "source": "fake", **rec}


def gene_phenotypes(gene: str) -> dict:
    """Fake gene -> diseases and HPO terms."""
    g = str(gene).upper()
    rec = _PHENO.get(g)
    if not rec:
        return {"gene": g, "diseases": [], "hpo_terms": [], "note": "no fake record for this gene"}
    return {"gene": g, "diseases": list(rec["diseases"]), "hpo_terms": [{"id": i, "label": l} for i, l in rec["hpo"]]}


def _expand(t: str) -> set[str]:
    out, cur = {t}, t
    for _ in range(2):
        cur = _PARENT.get(cur)
        if not cur:
            break
        out.add(cur)
    return out


def phenotype_match(gene: str, hpo_ids: list[str]) -> dict:
    """Fake phenotype match: fraction of patient terms whose expansion meets the gene's expanded terms."""
    g = gene_phenotypes(gene)
    gt = [t["id"] for t in g["hpo_terms"]]
    labels = {t["id"]: t["label"] for t in g["hpo_terms"]}
    if not hpo_ids:
        return {"gene": g["gene"], "score": 0.0, "matched": [], "n_patient_terms": 0}
    gexp = {x: _expand(x) for x in gt}
    matched = []
    for p in hpo_ids:
        pe = _expand(p)
        hit = next((x for x in gt if pe & gexp[x]), None)
        if hit:
            matched.append({"patient_term": p, "gene_term": hit, "gene_term_label": labels.get(hit, "")})
    return {"gene": g["gene"], "score": round(len(matched) / len(hpo_ids), 3), "matched": matched, "n_patient_terms": len(hpo_ids)}


def hpo_search(text: str, k: int = 5) -> list[dict]:
    """Fake HPO search over a tiny term list (label/synonym substring, then token overlap)."""
    q = str(text).lower().strip()
    toks = set(re.findall(r"[a-z0-9]+", q))
    scored = []
    for hid, label, syns in _TERMS:
        if q == label.lower():
            scored.append((3.0, hid, label, "label"))
        elif any(q == s.lower() for s in syns):
            scored.append((2.9, hid, label, "synonym"))
        elif q and (q in label.lower() or label.lower() in q):
            scored.append((2.0, hid, label, "label"))
        else:
            for s in syns:
                if q and (q in s.lower() or s.lower() in q):
                    scored.append((1.9, hid, label, "synonym"))
                    break
            else:
                cand = set(re.findall(r"[a-z0-9]+", (label + " " + " ".join(syns)).lower()))
                ov = len(toks & cand)
                if ov:
                    scored.append((ov / max(len(toks), 1), hid, label, "token_overlap"))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"id": h, "label": l, "matched_on": m} for _, h, l, m in scored[:k]]
