"""Tests for api.build_case_from_upload: success path, loud fallback paths, deterministic case_id.

Slice A1's genesleuth.data.upload may not exist yet, so the tests inject a stand-in module with the agreed signature
suspects_from_vcf(vcf_path, sample=None, budget_s=30.0) and UploadError(reason).
"""
from __future__ import annotations

import sys
import time
import types

import pytest

from genesleuth import config
from genesleuth.data import api, fakes
from genesleuth.schemas import Phenotype


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    """Fakes on (no real data needed) and uploads written under a temp DATA_DIR."""
    monkeypatch.setattr(config, "FAKE_MODE", True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    fakes_dir = tmp_path / "data"
    fakes_dir.mkdir()


def _files(tmp_path, vcf_text="##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\nchr2\t100\t.\tA\tG\t.\t.\t.\tGT\t0/1\n"):
    vcf = tmp_path / "g.vcf"
    vcf.write_text(vcf_text)
    pdf = tmp_path / "letter.pdf"
    fakes.write_placeholder_letter(pdf, [Phenotype(hpo_id="HP:0001250", label="Seizure")])
    return vcf, pdf


def _install_upload(monkeypatch, fn):
    """Install a stand-in genesleuth.data.upload module."""
    mod = types.ModuleType("genesleuth.data.upload")

    class UploadError(Exception):
        pass

    mod.UploadError = UploadError
    mod.suspects_from_vcf = fn
    monkeypatch.setitem(sys.modules, "genesleuth.data.upload", mod)
    monkeypatch.setattr("genesleuth.data.upload", mod, raising=False)
    return mod


def _good(vcf_path, sample=None, budget_s=30.0):
    case, truth = fakes.fake_build_case("100001", None, "demo", 1)
    sus = [v for v in case.suspects if v.variant_id != truth.hidden_variant_id]
    return {"sample_id": sample or "S1", "funnel": {"variants_in_panel_regions": 5000, "rare": len(sus), "suspects": len(sus)},
            "suspects": [v.model_dump() for v in sus]}


def test_success_path(monkeypatch, tmp_path):
    """A valid upload gives mode=uploaded, an up- case id, the user's suspects and a kept copy of the PDF."""
    _install_upload(monkeypatch, _good)
    vcf, pdf = _files(tmp_path)
    case, info = api.build_case_from_upload(str(vcf), str(pdf))
    assert info["mode"] == "uploaded" and info["reason"] == ""
    assert case.case_id.startswith("up-") and len(case.case_id) == 15
    assert info["n_suspects"] == len(case.suspects) == case.funnel["suspects"] > 100
    assert info["funnel"] == case.funnel and info["seconds"] >= 0
    assert str(config.DATA_DIR) in case.referral_pdf and open(case.referral_pdf, "rb").read(4) == b"%PDF"
    assert case.sample_id == "S1"


def test_case_id_is_deterministic(monkeypatch, tmp_path):
    """Same bytes give the same id; a different PDF gives a different id."""
    _install_upload(monkeypatch, _good)
    vcf, pdf = _files(tmp_path)
    a, _ = api.build_case_from_upload(str(vcf), str(pdf))
    b, _ = api.build_case_from_upload(str(vcf), str(pdf))
    assert a.case_id == b.case_id
    pdf2 = tmp_path / "other.pdf"
    fakes.write_placeholder_letter(pdf2, [Phenotype(hpo_id="HP:0001263", label="Global developmental delay")])
    c, _ = api.build_case_from_upload(str(vcf), str(pdf2))
    assert c.case_id != a.case_id


def test_fallback_on_upload_error(monkeypatch, tmp_path):
    """UploadError from A1 gives a labelled fallback with the real reason, not a crash."""
    def boom(vcf_path, sample=None, budget_s=30.0):
        raise mod.UploadError("VCF has no genotype column")
    mod = _install_upload(monkeypatch, boom)
    vcf, pdf = _files(tmp_path)
    case, info = api.build_case_from_upload(str(vcf), str(pdf))
    assert info["mode"] == "fallback" and "no genotype column" in info["reason"]
    assert not case.case_id.startswith("up-") and len(case.suspects) >= 100 and info["n_suspects"] == len(case.suspects)


@pytest.mark.parametrize("which", ["not_pdf", "empty_vcf", "missing", "big_vcf", "big_pdf", "truncated_pdf"])
def test_fallback_on_garbage_input(monkeypatch, tmp_path, which):
    """Garbage or oversized input never reaches A1 and falls back with a readable reason."""
    called = []
    _install_upload(monkeypatch, lambda *a, **k: called.append(1) or _good(*a, **k))
    vcf, pdf = _files(tmp_path)
    if which == "not_pdf":
        pdf.write_bytes(b"hello this is not a pdf")
    elif which == "empty_vcf":
        vcf.write_text("")
    elif which == "missing":
        vcf = tmp_path / "nope.vcf"
    elif which == "big_vcf":
        monkeypatch.setattr(api, "MAX_VCF_BYTES", 10)
    elif which == "big_pdf":
        monkeypatch.setattr(api, "MAX_PDF_BYTES", 10)
    elif which == "truncated_pdf":
        pdf.write_bytes(b"%PDF-1.4\n garbage without structure")
    case, info = api.build_case_from_upload(str(vcf), str(pdf))
    assert info["mode"] == "fallback" and info["reason"]
    assert not called, "A1's function must not run on invalid input"
    assert len(case.suspects) >= 100


def test_fallback_on_timeout_and_crash(monkeypatch, tmp_path):
    """A slow or crashing suspects builder falls back; the timeout is enforced."""
    vcf, pdf = _files(tmp_path)
    _install_upload(monkeypatch, lambda *a, **k: time.sleep(5))
    monkeypatch.setattr(api, "UPLOAD_TOTAL_BUDGET_S", 0.5)
    t = time.time()
    _, info = api.build_case_from_upload(str(vcf), str(pdf))
    assert info["mode"] == "fallback" and "longer than" in info["reason"] and time.time() - t < 4
    _install_upload(monkeypatch, lambda *a, **k: 1 / 0)
    _, info = api.build_case_from_upload(str(vcf), str(pdf))
    assert info["mode"] == "fallback" and "ZeroDivisionError" in info["reason"]


def test_fallback_when_no_suspects_or_module_missing(monkeypatch, tmp_path):
    """Zero suspects, or A1's module absent, falls back with a reason."""
    vcf, pdf = _files(tmp_path)
    _install_upload(monkeypatch, lambda *a, **k: {"sample_id": "S", "funnel": {}, "suspects": []})
    _, info = api.build_case_from_upload(str(vcf), str(pdf))
    assert info["mode"] == "fallback" and "no rare variants" in info["reason"]
    monkeypatch.setitem(sys.modules, "genesleuth.data.upload", None)  # makes the import fail
    _, info = api.build_case_from_upload(str(vcf), str(pdf))
    assert info["mode"] == "fallback" and "upload" in info["reason"].lower()
