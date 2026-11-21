"""Cut HG00096's non-ref variants in the panel regions out of the 1000G panel VCFs into a small test upload VCF (not committed)."""
import gzip, time
from concurrent.futures import ThreadPoolExecutor
from genesleuth import config
from genesleuth.data import panel, background
from genesleuth.data.bcf import run_shell, to_wsl_path
regs = panel.load_panel_regions(); by = {}
for r in regs: by.setdefault(r["chrom"], []).append(r)
W = config.DATA_DIR / "work"
def one(c):
    f = W / f"_t_reg_{c}.tsv"; f.write_text("".join(f"{c}\t{r['start']}\t{r['end']}\n" for r in by[c]))
    s = (f"bcftools view -s HG00096 -R {to_wsl_path(f)} {background.chrom_vcf_url(c)} 2>/dev/null | bcftools view -i 'GT=\"alt\"' 2>/dev/null")
    p = run_shell(s, timeout=900); return c, p.stdout.decode()
t = time.time()
with ThreadPoolExecutor(8) as ex: res = dict(ex.map(one, by))
header = [l for l in res["chr1"].splitlines() if l.startswith("#")]
body = [l for c in sorted(res, key=lambda x: (len(x), x)) for l in res[c].splitlines() if not l.startswith("#")]
with gzip.open(W / "test_upload_HG00096.vcf.gz", "wt") as fh: fh.write("\n".join(header + body) + "\n")
print(len(body), "records", f"{time.time()-t:.0f}s", [l for l in header if l.startswith("##contig")][:2], [l for l in header if "reference" in l.lower()][:2])
