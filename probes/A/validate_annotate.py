"""Check annotate.classify against ClinVar's own MC consequence terms for panel-region P/LP SNVs (probe)."""
import gzip
from collections import Counter
from genesleuth import config
from genesleuth.data import annotate
cm = Counter(); bad = []
with gzip.open(config.ROOT / "assets" / "clinvar_panel.tsv.gz", "rt") as fh:
    h = fh.readline().rstrip("\n").split("\t")
    for ln in fh:
        d = dict(zip(h, ln.rstrip("\n").split("\t")))
        if "athogenic" not in d["clnsig"] or "onflicting" in d["clnsig"] or len(d["ref"]) != 1 or len(d["alt"]) != 1:
            continue
        mcs = {x.split("|")[-1] for x in d["mc"].split(",") if x}
        k = annotate.classify(d["chrom"], int(d["pos"]), d["ref"], d["alt"])
        # ClinVar term set for the gene's MANE-like transcripts; compare on the key terms
        key = next((t for t in ("splice_donor_variant", "splice_acceptor_variant", "splice_region_variant", "intron", "5_prime_UTR_variant", "3_prime_UTR_variant", "missense_variant", "nonsense", "synonymous_variant") if any(t in m for m in mcs)), "other:" + ",".join(sorted(mcs))[:30])
        cm[(key, k["consequence"])] += 1
for (a, b), n in sorted(cm.items(), key=lambda x: -x[1])[:25]:
    print(n, "clinvar:", a, "| ours:", b)
