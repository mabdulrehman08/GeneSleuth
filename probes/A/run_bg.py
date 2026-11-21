"""Timed run of the background streaming for one sample (probe)."""
import time
from genesleuth.data import background
t = time.time()
rows = background.load_background("NA12878", rebuild=True)
print(len(rows), f"{time.time() - t:.1f}s")
