"""Fake data for development: a realistic 200-suspect case with a hidden SCN1A splice variant.

Feature: lets the agent side (and the benchmark runner) work before the real data pipeline is ready.
Use cases: FAKE_MODE=1 runs, early integration tests, unit tests. Nothing here is used in benchmark or demo runs.

The planted variant has exactly the same field set as every other suspect, and its consequence term is drawn
from the same vocabulary, so nothing in the Case reveals which suspect is planted. Suspects are shuffled with the seed.
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from genesleuth import config
from genesleuth.schemas import Case, CaseTruth, DemoOption, Phenotype, Variant

# gene -> (chrom, approx_start). Coordinates are approximate and only used for fake data.
_FAKE_GENES = {
    "SCN1A": ("chr2", 165_991_000), "SCN2A": ("chr2", 165_239_000), "KCNQ2": ("chr20", 63_400_000),
    "STXBP1": ("chr9", 127_600_000), "CDKL5": ("chrX", 18_400_000), "DNM1": ("chr9", 128_200_000),
    "SLC2A1": ("chr1", 42_900_000), "PCDH19": ("chrX", 100_300_000), "TSC2": ("chr16", 2_040_000),
    "GABRG2": ("chr5", 162_900_000), "SCN8A": ("chr12", 51_600_000), "CHD2": ("chr15", 92_800_000),
    "SYNGAP1": ("chr6", 33_400_000), "KCNT1": ("chr9", 135_700_000), "GRIN2A": ("chr16", 9_800_000),
    "DEPDC5": ("chr22", 31_800_000), "ARX": ("chrX", 25_000_000), "CACNA1A": ("chr19", 13_300_000),
    "SLC6A1": ("chr3", 11_000_000), "MFSD8": ("chr4", 127_900_000),
}
_REGION_CONSEQ = {
    "coding": ["missense_variant", "synonymous_variant", "missense_variant", "stop_gained", "inframe_deletion"],
    "splice": ["splice_region_variant", "splice_donor_variant", "splice_acceptor_variant", "splice_polypyrimidine_tract_variant"],
    "utr5": ["5_prime_UTR_variant"], "utr3": ["3_prime_UTR_variant"],
    "promoter": ["upstream_gene_variant"], "intron": ["intron_variant"],
}
_REGION_WORD = {"splice": "splice region", "intron": "deep intronic", "utr5": "5' UTR", "utr3": "3' UTR",
                "promoter": "promoter", "coding": "coding", "intergenic": "intergenic", "other": "other"}
# (option_id, gene, region, condition)
_FAKE_OPTIONS = [
    ("100001", "SCN1A", "splice", "Dravet syndrome"),
    ("100002", "DNM1", "intron", "Developmental and epileptic encephalopathy 31"),
    ("100003", "KCNQ2", "splice", "Early infantile epileptic encephalopathy 7"),
    ("100004", "STXBP1", "intron", "Developmental and epileptic encephalopathy 4"),
    ("100005", "CDKL5", "splice", "CDKL5 deficiency disorder"),
    ("100006", "SLC2A1", "utr5", "GLUT1 deficiency syndrome"),
    ("100007", "SCN2A", "intron", "Developmental and epileptic encephalopathy 11"),
    ("100008", "PCDH19", "splice", "PCDH19-related epilepsy"),
    ("100009", "TSC2", "intron", "Tuberous sclerosis complex 2"),
    ("100010", "GABRG2", "promoter", "Generalized epilepsy with febrile seizures plus"),
    ("100011", "SCN8A", "intron", "Developmental and epileptic encephalopathy 13"),
    ("100012", "CHD2", "splice", "Developmental and epileptic encephalopathy 94"),
    ("100013", "SYNGAP1", "utr3", "Intellectual developmental disorder, autosomal dominant 5"),
    ("100014", "KCNT1", "intron", "Developmental and epileptic encephalopathy 14"),
    ("100015", "GRIN2A", "splice", "Landau-Kleffner syndrome"),
    ("100016", "DEPDC5", "intron", "Familial focal epilepsy with variable foci"),
    ("100017", "ARX", "utr5", "Developmental and epileptic encephalopathy 1"),
    ("100018", "CACNA1A", "splice", "Developmental and epileptic encephalopathy 42"),
    ("100019", "SLC6A1", "intron", "Myoclonic-atonic epilepsy"),
    ("100020", "MFSD8", "intron", "Neuronal ceroid lipofuscinosis 7"),
]
_FAKE_PHENO = [("HP:0001250", "Seizure"), ("HP:0002373", "Febrile seizure (within the age range of 3 months to 6 years)"),
               ("HP:0001263", "Global developmental delay"), ("HP:0001252", "Hypotonia"),
               ("HP:0002123", "Generalized myoclonic seizure"), ("HP:0001336", "Myoclonus")]
_DECOY_PHENO = [("HP:0000518", "Cataract"), ("HP:0000396", "Prominent antihelix")]


def _rng(*parts) -> random.Random:
    """Deterministic RNG from arbitrary parts."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def fake_demo_options() -> list[DemoOption]:
    """Return ~20 fake demo options labelled like 'SCN1A, splice region, Dravet syndrome'."""
    return [DemoOption(option_id=oid, gene=g, region=r, condition=c, label=f"{g}, {_REGION_WORD[r]}, {c}")
            for oid, g, r, c in _FAKE_OPTIONS]


def _random_variant(rng: random.Random, gene: str, chrom: str, start: int, region: str, genotype: str) -> Variant:
    """One suspect near a panel gene; identical field set for planted and background variants."""
    pos = start + rng.randint(-10_000, 160_000)
    ref, alt = rng.sample("ACGT", 2)
    return Variant(variant_id=f"{chrom}-{pos}-{ref}-{alt}", chrom=chrom, pos=pos, ref=ref, alt=alt, gene=gene, region=region,
                   consequence=rng.choice(_REGION_CONSEQ.get(region, ["intergenic_variant"])), genotype=genotype,
                   distance_to_tss=pos - start)


def write_placeholder_letter(path: Path, phenotypes: list[Phenotype]) -> str:
    """Write a placeholder one-page referral letter PDF with reportlab (no gene, variant or condition names)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 740
    lines = ["Pediatric Neurology Referral (placeholder)", "", "Dear colleague,", "",
             "Thank you for seeing this 4-year-old child with recurrent seizures and developmental concerns.",
             "Clinical findings noted at our clinic:"] + [f" - {p.label}" for p in phenotypes] + [
             "", "Prior routine testing has not given an answer. We would appreciate your assessment.", "", "Sincerely,",
             "Referring physician"]
    for line in lines:
        c.drawString(72, y, line[:100])
        y -= 18
    c.save()
    return str(path)


def fake_build_case(option_id: str | None = None, sample_id: str | None = None, split: str = "demo",
                    seed: int = 0) -> tuple[Case, CaseTruth]:
    """Build a fake 200-suspect case with the chosen (or random) option planted as a hidden variant."""
    rng = _rng("fakecase", option_id, seed)
    by_id = {o[0]: o for o in _FAKE_OPTIONS}
    oid, gene, region, cond = by_id.get(option_id) or _FAKE_OPTIONS[0]
    chrom, start = _FAKE_GENES[gene]
    hidden = _random_variant(rng, gene, chrom, start, region, "0/1")
    genes = list(_FAKE_GENES)
    suspects = [hidden]
    seen = {hidden.variant_id}
    while len(suspects) < 200:
        g = rng.choice(genes)
        ch, st = _FAKE_GENES[g]
        v = _random_variant(rng, g, ch, st, rng.choices(list(_REGION_CONSEQ), weights=[3, 2, 1, 1, 1, 5])[0],
                            rng.choice(["0/1", "0/1", "1/1"]))
        if v.variant_id not in seen:
            seen.add(v.variant_id)
            suspects.append(v)
    rng.shuffle(suspects)
    case_id = "%016x" % rng.getrandbits(64)
    phenos = [Phenotype(hpo_id=h, label=l) for h, l in _FAKE_PHENO[:5]] + [Phenotype(hpo_id=h, label=l) for h, l in _DECOY_PHENO[:1]]
    pdf = write_placeholder_letter(config.DATA_DIR / "work" / "letters" / f"fake_{case_id}.pdf", phenos)
    funnel = {"variants_in_panel_regions": 13049 + rng.randint(-300, 300), "rare_af_lt_0.01": 812 + rng.randint(-50, 50),
              "rare_af_lt_0.001": 260 + rng.randint(-20, 20), "suspects": len(suspects)}
    case = Case(case_id=case_id, sample_id=sample_id or config.DEFAULT_SAMPLE, referral_pdf=pdf, suspects=suspects, funnel=funnel)
    truth = CaseTruth(case_id=case_id, hidden_variant_id=hidden.variant_id, gene=gene, condition=cond, clinvar_id=oid,
                      region=region, true_phenotypes=phenos, split=split if split in ("dev", "test", "demo") else "demo")
    return case, truth


def fake_holdout_for(truth: CaseTruth) -> set[str]:
    """Variant id and ClinVar id to hide from lookups."""
    return {x for x in (truth.hidden_variant_id, truth.clinvar_id) if x}
