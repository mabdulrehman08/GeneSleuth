"""Synthetic pediatric neurology referral letters (PDF), written by Gemini 4 Hydrogen from the true phenotypes.

Feature: for one option (a ClinVar variant to plant) it
  1. builds the synthetic phenotype set (phenotypes.synthesize),
  2. asks Gemini 4 Hydrogen (Interactions API, thinking_level=medium, no temperature/top_p) for a realistic one-page letter
     that never names the gene, variant or condition, and has no HPO ids,
  3. regex-checks the text for gene symbols, 'chr', c./p. notation, HPO ids and condition names and regenerates (capped),
  4. renders a clean PDF with reportlab, or a 'scanned' image-only PDF (rotated 0.5-1.5 degrees, gray paper, noise,
     JPEG-compressed at about 150 dpi) drawn with Pillow,
  5. stores the PDF at assets/letters/<option_id>.pdf (committed bundle) and metadata in DATA_DIR/work/letters/<option_id>.json
     (true phenotypes, disease source, scanned flag, letter text, violations).
Every genai call is logged to DATA_DIR/cache/calls.jsonl (model, prompt, config, output, latency, usage), never keys.
Use cases: scripts/data_letters.py (batch, resumable), cases.build_case (attaches the pre-generated letter).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import threading
import time
from pathlib import Path

from genesleuth import config
from genesleuth.data import phenotypes as ph
from genesleuth.data import splits
from genesleuth.schemas import Phenotype

ASSETS_LETTERS = config.ROOT / "assets" / "letters"
WORK_LETTERS = config.DATA_DIR / "work" / "letters"
CALLS_LOG = config.CACHE_DIR / "calls.jsonl"
MAX_REGEN = 3
_LOG_LOCK = threading.Lock()
_GENE_LIKE = re.compile(r"\b[A-Z][A-Z0-9]{2,}\d[A-Z0-9]*\b")
_STOP_CAPS = {"type", "syndrome", "disease", "disorder", "early", "infantile", "autosomal", "dominant", "recessive", "linked", "familial",
              "developmental", "epileptic", "encephalopathy", "intellectual", "with", "and", "the", "due", "to", "of", "in"}


def _panel_genes() -> set[str]:
    """Panel gene symbols from panel_regions.tsv (assets first), with a fallback to the candidate genes."""
    p = splits.find("panel_regions.tsv")
    genes: set[str] = set()
    if p:
        with open(p, encoding="utf-8") as f:
            next(f, None)
            genes = {ln.split("\t", 1)[0] for ln in f if ln.strip()}
    return genes


def log_call(rec: dict) -> None:
    """Append one record to DATA_DIR/cache/calls.jsonl (never contains keys)."""
    CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK, open(CALLS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def hydrogen_text(prompt: str, purpose: str, thinking_level: str = "medium", retries: int = 4) -> str:
    """Call gemini-4-hydrogen through the Interactions API with backoff on 503/overload; logs every attempt."""
    try:
        from genesleuth.gemini_clients import client  # owned by Agent B, preferred
    except Exception:
        from genesleuth.data._clients_tmp import client
    cfg = {"thinking_level": thinking_level}
    last: Exception | None = None
    for attempt in range(retries):
        t0 = time.time()
        try:
            r = client.interactions.create(model=config.HYDROGEN, input=prompt, generation_config=cfg)
            dt = time.time() - t0
            usage = {}
            model_version = None
            try:
                d = r.model_dump(mode="json")
                usage = d.get("usage", {})
                model_version = d.get("model")
            except Exception:
                pass
            text = r.output_text or ""
            log_call({"ts": time.time(), "slice": "a3", "purpose": purpose, "model": config.HYDROGEN, "modelVersion": model_version,
                      "prompt": prompt, "config": cfg, "output": text, "latency_s": round(dt, 2), "usage": usage, "attempt": attempt})
            return text
        except Exception as e:  # network / overload
            last = e
            log_call({"ts": time.time(), "slice": "a3", "purpose": purpose, "model": config.HYDROGEN, "config": cfg, "error": str(e)[:300],
                      "latency_s": round(time.time() - t0, 2), "attempt": attempt})
            time.sleep(min(2 ** attempt * 2, 20))
    raise RuntimeError(f"hydrogen call failed after {retries} tries: {last}")


def forbidden_terms(gene: str, condition: str) -> list[str]:
    """Condition-derived strings that must not appear in the letter: the full name, its segments and eponyms."""
    cond = re.sub(r"\s+", " ", condition.replace("_", " ")).strip()
    terms = {cond}
    for seg in re.split(r"[,;()]", cond):
        seg = seg.strip()
        if len(seg.split()) >= 2 and not re.fullmatch(r"[\d\s]+", seg):
            terms.add(seg)
    for tok in re.findall(r"[A-Z][a-z]+(?:-[A-Z][a-z]+)*", cond)[1:] + re.findall(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)+\b", cond):
        if tok.lower() not in _STOP_CAPS and len(tok) > 3:
            terms.add(tok)
    m = re.match(r"([A-Z][a-z]+(?:-[A-Z][a-z]+)*)\s+(syndrome|disease)", cond)
    if m:
        terms.add(m.group(1))
    return sorted(t for t in terms if t)


def check_letter(text: str, gene: str, condition: str, genes: set[str] | None = None) -> list[str]:
    """Return a list of violations (empty = the letter is clean)."""
    v = []
    genes = (genes if genes is not None else _panel_genes()) | {gene}
    low = text.lower()
    for g in genes:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(g)}(?![A-Za-z0-9])", text):
            v.append(f"gene:{g}")
    for m in _GENE_LIKE.finditer(text):
        v.append(f"gene_like:{m.group(0)}")
    if re.search(r"\bchr(?:\d{1,2}|[XYM])\b", text, re.I):
        v.append("chr")
    if re.search(r"\b[cgmnr]\.\s?[\d*-]", text) or re.search(r"\bp\.\s?[A-Z(]", text):
        v.append("hgvs")
    if re.search(r"HP:\d+", text):
        v.append("hpo_id")
    for t in forbidden_terms(gene, condition):
        if t.lower() in low:
            v.append(f"condition:{t}")
    return sorted(set(v))


def _patient_profile(option_id: str, seed: int) -> dict:
    """Deterministic synthetic patient facts used in the prompt (no real person)."""
    r = random.Random(int(hashlib.sha256(f"pt|{option_id}|{seed}".encode()).hexdigest()[:12], 16))
    sex = r.choice(["girl", "boy"])
    names = {"girl": ["Maya", "Lucia", "Hannah", "Priya", "Zoe", "Amara", "Nora", "Ines"], "boy": ["Leo", "Omar", "Mateo", "Elias", "Arjun", "Noah", "Kai", "Theo"]}
    return {"sex": sex, "first_name": r.choice(names[sex]), "age_years": r.randint(2, 10), "month_hint": r.choice(["January", "March", "May", "September", "October", "November"])}


def build_prompt(profile: dict, phenos: list[Phenotype], avoid: list[str]) -> str:
    """Prompt for the letter writer; lists findings in plain words and states the hard constraints."""
    findings = "\n".join(f"- {p.label}" for p in phenos)
    extra = ""
    if avoid:
        extra = ("\nA previous draft was rejected because it contained forbidden terms: " + ", ".join(avoid) +
                 ". Do not use these or anything similar.\n")
    return f"""Write a realistic one-page referral letter from a community pediatrician to a pediatric neurology / genetics clinic about a patient whose seizures and development have not been explained by routine work-up.

Patient: a {profile['age_years']}-year-old {profile['sex']} called {profile['first_name']} (invented first name only; no surname, no date of birth, no hospital or real clinician names; sign with a plausible invented clinician name and the title "Pediatrician").
The letter is dated in {profile['month_hint']}.

Clinical findings the letter must convey, in natural clinical language (rephrase freely, merge related findings, do not copy a list; a couple may be incidental findings noted in passing; invent plausible ages of onset and a brief timeline, but add no further diagnoses):
{findings}

Hard rules:
- Never name a gene, a genetic variant, DNA position, HGVS notation (no "c." or "p." notation), or any named syndrome or diagnosis. Do not say what condition the child has; the cause is unknown.
- No HPO codes or ontology terms in brackets, no markdown, no bullet characters, no bold. Plain paragraphs only.
- 230 to 320 words. A short subject line starting with "Re:" , a greeting, 3-4 paragraphs (history, examination/investigations done so far with normal or non-diagnostic results, what is being asked), and a sign-off.
- Mention that routine testing has not given an answer and ask for further evaluation.
{extra}
Output only the letter text."""


def clean_text(t: str) -> str:
    """Strip markdown emphasis and surrounding whitespace from model output."""
    t = re.sub(r"[*_`#]+", "", t)
    return t.strip()


def generate_letter_text(option_id: str, gene: str, condition: str, phenos: list[Phenotype], seed: int = 0) -> tuple[str, list[str], int]:
    """Generate the letter text, regenerating up to MAX_REGEN times on violations. Returns (text, violations, attempts)."""
    genes = _panel_genes()
    profile = _patient_profile(option_id, seed)
    avoid: list[str] = []
    text, viol = "", []
    for attempt in range(1, MAX_REGEN + 1):
        text = clean_text(hydrogen_text(build_prompt(profile, phenos, avoid), f"letter:{option_id}"))
        viol = check_letter(text, gene, condition, genes)
        if not viol:
            return text, [], attempt
        avoid = sorted({x.split(":", 1)[1] for x in viol})
    return text, viol, MAX_REGEN


# ---------------------------------------------------------------- rendering

def render_clean_pdf(text: str, out: Path) -> None:
    """Render the letter as a one-page text PDF with reportlab (font shrinks until it fits)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape
    out.parent.mkdir(parents=True, exist_ok=True)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for size in (10.5, 10, 9.5, 9, 8.5, 8):
        st = ParagraphStyle("b", fontName="Helvetica", fontSize=size, leading=size * 1.35, spaceAfter=size * 0.7)
        flow = [Paragraph("Pediatric Associates &#8226; Primary Care Referral", ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=size + 2, spaceAfter=10)), Spacer(1, 6)]
        flow += [Paragraph(escape(p).replace("\n", "<br/>"), st) for p in paras]
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=letter, leftMargin=64, rightMargin=64, topMargin=56, bottomMargin=56).build(flow)
        from pypdf import PdfReader
        if len(PdfReader(io.BytesIO(buf.getvalue())).pages) == 1:
            break
    tmp = out.with_suffix(".pdf.part")
    tmp.write_bytes(buf.getvalue())
    os.replace(tmp, out)


def _font(size: int):
    """Find a TrueType font (Arial on Windows, DejaVu on Linux) or fall back to Pillow's default."""
    from PIL import ImageFont
    for p in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def render_scanned_pdf(text: str, out: Path, seed: int = 0) -> None:
    """Render a 'scanned' letter: page drawn with Pillow at ~150 dpi, rotated 0.5-1.5 degrees, gray paper, noise, JPEG, image-only PDF."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    rng = random.Random(seed)
    W, H = 1275, 1650  # 8.5 x 11 in at 150 dpi
    margin = 110
    for size in (30, 28, 26, 24, 22, 20):
        font = _font(size)
        img = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(img)
        y = margin
        d.text((margin, y), "Pediatric Associates  -  Primary Care Referral", font=_font(size + 6), fill=20)
        y += int((size + 6) * 2.2)
        ok = True
        for para in [p for p in re.split(r"\n\s*\n", text) if p.strip()]:
            for raw in para.split("\n"):
                words, line = raw.split(), ""
                for w in words:
                    trial = (line + " " + w).strip()
                    if d.textlength(trial, font=font) > W - 2 * margin:
                        d.text((margin, y), line, font=font, fill=20)
                        y += int(size * 1.35)
                        line = w
                    else:
                        line = trial
                d.text((margin, y), line, font=font, fill=20)
                y += int(size * 1.35)
            y += int(size * 0.7)
        if y < H - margin:
            break
    angle = rng.choice([-1, 1]) * rng.uniform(0.5, 1.5)
    page = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255).filter(ImageFilter.GaussianBlur(0.7))
    arr = np.asarray(page, dtype=np.float32)
    gen = np.random.default_rng(seed)
    arr = arr * 0.86 + 20 + gen.normal(0, 7, arr.shape)  # gray paper tone + sensor noise
    yy, xx = np.mgrid[0:H, 0:W]
    arr -= 14 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)  # vignette
    img2 = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "L")
    buf = io.BytesIO()
    img2.save(buf, "JPEG", quality=55, dpi=(150, 150))
    buf.seek(0)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".pdf.part")
    c = canvas.Canvas(str(tmp), pagesize=letter)
    c.drawImage(ImageReader(buf), 0, 0, width=letter[0], height=letter[1])
    c.save()
    os.replace(tmp, out)


# ---------------------------------------------------------------- per-option orchestration

def letter_paths(option_id: str) -> tuple[Path, Path]:
    """(bundle PDF path, working metadata path) for an option."""
    return ASSETS_LETTERS / f"{option_id}.pdf", WORK_LETTERS / f"{option_id}.json"


def is_scanned(option_id: str, split: str) -> bool:
    """Deterministic scanned/clean assignment: 50% of DEV/TEST letters, 25% of DEMO letters."""
    h = int(hashlib.sha256(f"scan|{option_id}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < (0.25 if split == "demo" else 0.5)


def make_letter(candidate: dict, split: str, seed: int = 0, force: bool = False) -> dict:
    """Create (or reuse) the letter for one candidate; resumable. Returns the metadata dict."""
    oid = candidate["variation_id"]
    pdf, meta_path = letter_paths(oid)
    if meta_path.exists() and pdf.exists() and not force:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    phenos, detail = ph.synthesize(candidate, seed)
    text, viol, attempts = generate_letter_text(oid, candidate["gene"], candidate["condition"], phenos, seed)
    scanned = is_scanned(oid, split)
    if scanned:
        render_scanned_pdf(text, pdf, seed=int(oid) % 100000)
    else:
        render_clean_pdf(text, pdf)
    meta = {"option_id": oid, "split": split, "gene": candidate["gene"], "condition": candidate["condition"], "scanned": scanned,
            "phenotypes": [p.model_dump() for p in phenos], "detail": detail, "letter_text": text, "violations": viol, "attempts": attempts,
            "pdf_bytes": pdf.stat().st_size, "seed": seed}
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = meta_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    os.replace(tmp, meta_path)
    return meta


def load_meta(option_id: str) -> dict | None:
    """Load letter metadata for an option from DATA_DIR/work/letters or the committed assets/letters_meta.json.gz bundle."""
    _, mp = letter_paths(option_id)
    if mp.exists():
        return json.loads(mp.read_text(encoding="utf-8"))
    import gzip
    bundle = config.ROOT / "assets" / "letters_meta.json.gz"
    if bundle.exists():
        with gzip.open(bundle, "rt", encoding="utf-8") as f:
            return json.load(f).get(option_id)
    return None
