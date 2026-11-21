import gzip
from collections import Counter
from genesleuth import config
from genesleuth.data import annotate
c = Counter(); ex = {}
with gzip.open(config.ROOT / "assets" / "clinvar_panel.tsv.gz", "rt") as fh:
    h = fh.readline().rstrip("\n").split("\t")
    for ln in fh:
        d = dict(zip(h, ln.rstrip("\n").split("\t")))
        if "athogenic" not in d["clnsig"] or len(d["ref"]) != 1 or len(d["alt"]) != 1: continue
        mcs = d["mc"]
        if "5_prime_UTR" in mcs and "missense" not in mcs and "nonsense" not in mcs:
            k = annotate.classify(d["chrom"], int(d["pos"]), d["ref"], d["alt"])
            if k["region"] == "coding":
                c[k["gene"]] += 1; ex.setdefault(k["gene"], (d["chrom"], d["pos"], d["gene"], mcs))
print(c.most_common(6)); print(list(ex.items())[:4])
