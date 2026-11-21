"""Extract the sample's panel-region variants (cached in DATA_DIR/work). Idempotent.

Usage: python scripts/data_background.py [SAMPLE] [--force]
Also builds the rarity-filtered suspects bundle (assets/suspects_<sample>.json.gz) via genesleuth.data.suspects.
"""
import sys

from genesleuth import config
from genesleuth.data import background


def main(sample: str | None = None, force: bool = False) -> None:
    """Build background_<sample>.tsv.gz, then the suspects bundle (skips what already exists unless force)."""
    sample = sample or config.DEFAULT_SAMPLE
    from genesleuth.data import suspects
    if not force:
        try:
            suspects.load_suspects_raw(sample)
            print(f"suspects bundle for {sample} present; skipping")
            return
        except FileNotFoundError:
            pass
    background.load_background(sample, rebuild=force)
    suspects.build_suspects(sample, force=force)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else None, "--force" in sys.argv)
