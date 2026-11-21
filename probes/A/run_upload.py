"""Timed run of upload.suspects_from_vcf on the HG00096 test VCF (probe)."""
import sys, time
from collections import Counter
from genesleuth import config
from genesleuth.data import upload
p = str(config.DATA_DIR / "work" / "test_upload_HG00096.vcf.gz")
t = time.time(); d = upload.suspects_from_vcf(p, budget_s=float(sys.argv[1]) if len(sys.argv) > 1 else 30)
print(f"wall {time.time()-t:.1f}s", d["sample_id"], d["assembly"], d["funnel"], d["timings"], d["notes"])
print(Counter(v.region for v in d["suspects"]), d["suspects"][0])
