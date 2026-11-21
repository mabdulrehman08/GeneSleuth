"""Timed gnomAD AF streaming for the sample's background variants (probe)."""
import time
from genesleuth.data import background, filter as flt
rows = background.load_background("NA12878")
t = time.time()
gn = flt.gnomad_for(rows, "NA12878", refresh=True)
rows = flt.apply_frequency(rows, gn)
print(len(rows), f"{time.time() - t:.1f}s")
for th in (0.1, 0.01, 0.001, 0.0001):
    print(th, flt.count_rare(rows, th))
from collections import Counter
print(Counter(r["af_source"] for r in rows))
