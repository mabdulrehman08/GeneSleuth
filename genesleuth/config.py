import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("GENESLEUTH_DATA_DIR") or (ROOT / "data"))
CACHE_DIR = DATA_DIR / "cache"
FAKE_MODE = os.getenv("FAKE_MODE", "0") == "1"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ALPHAGENOME_API_KEY = os.getenv("ALPHA_GENOME_API_KEY", "")
ARGON = "gemini-4-argon"
CARBON = "gemini-4-carbon"
NEON = "gemini-4-neon"
HYDROGEN = "gemini-4-hydrogen"
DECISION_MODEL = "gemini-decision-1"
GENOME_BUILD = "GRCh38"
BRAIN_TISSUE = os.getenv("BRAIN_TISSUE", "UBERON:0000955")
BLOOD_TISSUE = os.getenv("BLOOD_TISSUE", "UBERON:0000178")
DEFAULT_SAMPLE = os.getenv("DEFAULT_SAMPLE", "NA12878")
USE_MANAGED_AGENT = os.getenv("USE_MANAGED_AGENT", "0") == "1"
ANTIGRAVITY_AGENT = "antigravity-preview-09-2026"
