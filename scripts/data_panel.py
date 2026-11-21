"""Build panel_regions.tsv + mane_features.tsv.gz (DATA_DIR/work and committed assets/). Idempotent.

Usage: python scripts/data_panel.py [--force]
"""
import sys

from genesleuth.data import panel


def main(force: bool = False) -> None:
    """Build the panel files unless assets/ already holds them (or force=True)."""
    if not force and (panel.ASSETS / "panel_regions.tsv").exists() and (panel.ASSETS / "mane_features.tsv.gz").exists():
        print("panel assets present; skipping")
        return
    panel.write_all()


if __name__ == "__main__":
    main("--force" in sys.argv)
