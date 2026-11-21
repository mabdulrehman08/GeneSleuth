"""Build suspects for the default sample and print region distribution (probe)."""
import time
from collections import Counter
from genesleuth.data import suspects, annotate
t = time.time()
d = suspects.build_suspects("NA12878", force=True)
print(f"{time.time()-t:.1f}s")
S = suspects.load_suspects("NA12878")["suspects"]
print(Counter(v.region for v in S)); print(Counter(v.consequence for v in S).most_common(12)); print(Counter(v.gene for v in S).most_common(8))
t = time.time(); v = annotate.annotate_variant("chr9", 128225994, "G", "A"); print(v, f"{time.time()-t:.2f}s")
t = time.time(); v = annotate.annotate_variant("chr2", 166000000, "A", "G"); print(v, f"{time.time()-t:.2f}s")
