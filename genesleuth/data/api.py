"""Public data interface used by the agent side: demo options, case building and the leakage holdout.

Feature: the three functions below are the contract with Agent B (see section 7 of the shared brief).
With FAKE_MODE=1, or when the real case data is not ready yet, the fakes in fakes.py are used instead.
"""
from __future__ import annotations

import hashlib
import shutil
import threading
import time
from pathlib import Path

from genesleuth import config
from genesleuth.schemas import Case, CaseTruth, DemoOption, Variant
from genesleuth.data import fakes

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_VCF_BYTES = 200 * 1024 * 1024
UPLOAD_TOTAL_BUDGET_S = 45.0
UPLOAD_VCF_BUDGET_S = 30.0


def _real_ready() -> bool:
    """True when the real case builder is importable and its inputs exist (never true in FAKE_MODE)."""
    if config.FAKE_MODE:
        return False
    try:
        from genesleuth.data import cases
        return cases.real_ready()
    except Exception:
        return False


def list_demo_options() -> list[DemoOption]:
    """Return the demo picker options, labelled like 'SCN1A, splice region, Dravet syndrome'."""
    if _real_ready():
        from genesleuth.data import cases
        return cases.list_demo_options()
    return fakes.fake_demo_options()


def build_case(option_id: str | None = None, sample_id: str | None = None, split: str = "demo",
               seed: int = 0) -> tuple[Case, CaseTruth]:
    """Build a case with the chosen option planted as an unknown variant; option_id=None means a random option."""
    if _real_ready():
        from genesleuth.data import cases
        return cases.build_case(option_id, sample_id, split, seed)
    return fakes.fake_build_case(option_id, sample_id, split, seed)


def holdout_for(truth: CaseTruth) -> set[str]:
    """Variant ids and ClinVar ids to hide from lookups so the planted variant looks novel."""
    return fakes.fake_holdout_for(truth)


# ----------------------------------------------------------------- uploaded genome + letter

def _validate_upload(vcf: Path, pdf: Path) -> None:
    """Cheap checks before any work; raises ValueError with a human-readable reason."""
    if not vcf.is_file():
        raise ValueError(f"VCF file not found: {vcf.name}")
    if not pdf.is_file():
        raise ValueError(f"referral PDF not found: {pdf.name}")
    if vcf.stat().st_size == 0:
        raise ValueError("the VCF file is empty")
    if vcf.stat().st_size > MAX_VCF_BYTES:
        raise ValueError(f"the VCF is {vcf.stat().st_size / 1e6:.0f} MB, over the 200 MB limit")
    size = pdf.stat().st_size
    if size == 0 or size > MAX_PDF_BYTES:
        raise ValueError(f"the PDF is {size / 1e6:.1f} MB; it must be non-empty and under 15 MB")
    with open(pdf, "rb") as f:
        if not f.read(1024).lstrip().startswith(b"%PDF"):
            raise ValueError("the referral file is not a PDF (it does not start with %PDF)")
    try:
        from pypdf import PdfReader
        if len(PdfReader(str(pdf)).pages) < 1:
            raise ValueError("the PDF has no pages")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"the PDF cannot be read: {type(e).__name__}: {e}") from e


def _content_id(vcf: Path, pdf: Path) -> str:
    """Deterministic case id: 'up-' + 12 hex chars of sha1 over the VCF bytes then the PDF bytes (streamed)."""
    h = hashlib.sha1()
    for p in (vcf, pdf):
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return "up-" + h.hexdigest()[:12]


def _run_with_timeout(fn, timeout_s: float):
    """Run fn() in a daemon thread; return its result, re-raise its exception, or raise TimeoutError."""
    box: dict = {}

    def target():
        try:
            box["ok"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller
            box["err"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(max(timeout_s, 0.1))
    if t.is_alive():
        raise TimeoutError(f"building suspects from the VCF took longer than {UPLOAD_TOTAL_BUDGET_S:.0f} s")
    if "err" in box:
        raise box["err"]
    return box["ok"]


def _fallback(reason: str, funnel_note: str | None, t0: float, sample_id: str | None) -> tuple[Case, dict]:
    """Prepared demo case used when the upload cannot be processed; always labelled as a fallback with the real reason."""
    case, _truth = build_case(None, sample_id, "demo", 0)  # the truth is discarded: this is a stand-in, nothing is revealed
    info = {"mode": "fallback", "reason": reason, "funnel": dict(case.funnel), "seconds": round(time.time() - t0, 2),
            "n_suspects": len(case.suspects)}
    return case, info


def build_case_from_upload(vcf_path: str, referral_pdf_path: str, sample_id: str | None = None) -> tuple[Case, dict]:
    """Build a Case from the user's own VCF and referral PDF. There is NO CaseTruth: nothing is hidden, so Reveal does not apply.

    Returns (case, info) with info = {"mode": "uploaded" | "fallback", "reason": str, "funnel": dict, "seconds": float,
    "n_suspects": int}.
      - "uploaded": suspects come from genesleuth.data.upload.suspects_from_vcf (slice A1) on the uploaded genome; case_id is
        "up-" + 12 hex of sha1(VCF bytes + PDF bytes) (deterministic); referral_pdf is a copy kept under
        DATA_DIR/work/uploads/<case_id>/. Letter-derived fields are not set: the agent reads the letter itself.
      - "fallback": the upload could not be used (invalid file, UploadError, over ~45 s, anything else). A prepared demo case
        from build_case(None, ...) is returned instead and info["reason"] holds the real error text, to be shown to the user as
        "Using a prepared demo genome because: ...". It is never the user's data. This function does not raise.
    """
    t0 = time.time()
    try:
        vcf, pdf = Path(vcf_path), Path(referral_pdf_path)
        _validate_upload(vcf, pdf)
        case_id = _content_id(vcf, pdf)
        from genesleuth.data import upload  # slice A1; imported lazily so FAKE_MODE and old checkouts still work
        remaining = UPLOAD_TOTAL_BUDGET_S - (time.time() - t0)
        budget = min(UPLOAD_VCF_BUDGET_S, max(remaining - 5.0, 5.0))
        data = _run_with_timeout(lambda: upload.suspects_from_vcf(str(vcf), sample_id, budget_s=budget), max(remaining, 1.0))
        suspects = [v if isinstance(v, Variant) else Variant(**v) for v in data["suspects"]]
        if not suspects:
            raise ValueError("no rare variants in the 58 panel genes were found in the uploaded VCF")
        dest = config.DATA_DIR / "work" / "uploads" / case_id
        dest.mkdir(parents=True, exist_ok=True)
        kept = dest / "referral.pdf"
        shutil.copyfile(pdf, kept)
        funnel = {k: int(v) for k, v in dict(data.get("funnel", {})).items()}
        funnel["suspects"] = len(suspects)
        case = Case(case_id=case_id, sample_id=sample_id or data.get("sample_id") or "uploaded", referral_pdf=str(kept),
                    suspects=suspects, funnel=funnel)
        return case, {"mode": "uploaded", "reason": "", "funnel": dict(funnel), "seconds": round(time.time() - t0, 2),
                      "n_suspects": len(suspects)}
    except Exception as e:  # never crash the UI: fall back loudly
        name = type(e).__name__
        reason = str(e) or name
        if name not in ("UploadError", "ValueError", "TimeoutError"):
            reason = f"{name}: {reason}"
        return _fallback(reason, None, t0, sample_id)
