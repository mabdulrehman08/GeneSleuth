"""Tests for genesleuth.data.upload (VCF upload -> suspects bundle). Small synthetic VCFs; the real HG00096 run is optional."""
import gzip

import pytest

from genesleuth import config
from genesleuth.data import upload

HDR38 = "##fileformat=VCFv4.2\n##contig=<ID=chr2,length=242193529>\n##INFO=<ID=gnomAD_AF,Number=A,Type=Float,Description=x>\n"
COLS = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tPAT\n"


def _w(tmp_path, text, name="t.vcf"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_basic_rare_and_common(tmp_path):
    body = ("2\t166000000\t.\tA\tG\t.\tPASS\tgnomAD_AF=0.0001\tGT\t0|1\n"      # rare, in SCN1A
            "chr2\t166000100\t.\tC\tT\t.\tPASS\tgnomAD_AF=0.4\tGT\t1/1\n"      # common -> dropped
            "chr2\t166000200\t.\tC\tT\t.\t.\t.\tGT\t0/0\n"                     # ref -> skipped
            "chr2\t10\t.\tC\tT\t.\t.\t.\tGT\t0/1\n")                           # outside panel
    d = upload.suspects_from_vcf(_w(tmp_path, HDR38 + COLS + body), budget_s=5)
    ids = [v.variant_id for v in d["suspects"]]
    assert ids == ["chr2-166000000-A-G"]
    assert d["suspects"][0].gene == "SCN1A" and d["suspects"][0].genotype == "0/1"
    assert d["funnel"]["variants_in_panel_regions"] == 2 and d["funnel"]["af_from_vcf"] == 2 and d["funnel"]["suspects"] == 1
    assert d["sample_id"] == "PAT" and d["assembly"] == "GRCh38"


def test_gz_and_af_unknown(tmp_path):
    p = tmp_path / "t.vcf.gz"
    with gzip.open(p, "wt") as fh:
        fh.write(HDR38 + COLS + "chr2\t166000000\t.\tA\tG\t.\tPASS\t.\tGT\t0/1\n")
    d = upload.suspects_from_vcf(str(p), budget_s=5)
    assert d["funnel"]["af_unknown"] == 1 and len(d["suspects"]) == 1


def test_grch37_rejected(tmp_path):
    text = "##fileformat=VCFv4.2\n##contig=<ID=2,length=243199373>\n" + COLS + "2\t166000000\t.\tA\tG\t.\t.\t.\tGT\t0/1\n"
    with pytest.raises(upload.UploadError, match="GRCh37 not supported"):
        upload.suspects_from_vcf(_w(tmp_path, text), budget_s=5)
    with pytest.raises(upload.UploadError, match="GRCh37"):
        upload.suspects_from_vcf(_w(tmp_path, "##fileformat=VCFv4.2\n##reference=file:///b37/hs37d5.fa\n" + COLS + "2\t1\t.\tA\tG\t.\t.\t.\tGT\t0/1\n"), budget_s=5)


def test_bad_inputs(tmp_path):
    with pytest.raises(upload.UploadError, match="not a VCF"):
        upload.suspects_from_vcf(_w(tmp_path, "hello\n"), budget_s=5)
    with pytest.raises(upload.UploadError, match="no sample"):
        upload.suspects_from_vcf(_w(tmp_path, HDR38 + "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"), budget_s=5)
    with pytest.raises(upload.UploadError, match="not found"):
        upload.suspects_from_vcf(_w(tmp_path, HDR38 + COLS), sample="NOPE", budget_s=5)
    with pytest.raises(upload.UploadError, match="no usable variants"):
        upload.suspects_from_vcf(_w(tmp_path, HDR38 + COLS + "chr2\t10\t.\tC\tT\t.\t.\t.\tGT\t0/1\n"), budget_s=5)
    with pytest.raises(upload.UploadError, match="file not found"):
        upload.suspects_from_vcf(str(tmp_path / "missing.vcf"))


def test_real_hg00096():
    p = config.DATA_DIR / "work" / "test_upload_HG00096.vcf.gz"
    if not p.exists():
        pytest.skip("HG00096 test VCF not built (probes/A/make_test_vcf.py)")
    d = upload.suspects_from_vcf(str(p), budget_s=30)
    assert d["sample_id"] == "HG00096" and 0 < len(d["suspects"]) <= 300
    assert d["timings"]["total_s"] < 40
