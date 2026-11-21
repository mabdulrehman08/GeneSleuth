"""Build DATA_DIR/work/panel_regions.tsv (+ BED, bcftools region list, mane_features.tsv.gz). Usage: python scripts/data_panel.py"""
from genesleuth.data import panel

if __name__ == "__main__":
    panel.write_all()
