"""Operational limits and pricing for a bounded case investigation."""
from genesleuth import config

GEMINI_TIMEOUT_MS = 90_000   # Neon turns measured at 26-54 s (60k input tokens); 30 s killed them
MANAGED_TIMEOUT_MS = 75_000
GEMINI_OVERLOAD_RETRIES = 3
DECISION_MAX_QUESTIONS = 1000
CONFIDENCE_MIN = 0.6
SUPPORT_MIN = 0.7
REJECT_MAX = 0.3
MAX_REVISIONS = 2
MAX_PLOTS = 3
MAX_REFERRAL_BYTES = 20 * 1024 * 1024
AG_CONCURRENCY = 4
ATLAS_WORKERS = 10
TISSUE_CANDIDATES = 12
PREFETCH_TOP = 10   # candidates whose cheap evidence is gathered in code before Neon starts
PROFILE_LIMITS = {
    "demo": {"score_calls": 25, "tool_calls": 70, "thinking": "medium", "submit_after_s": 75, "deadline_s": 135},
    "bench": {"score_calls": 30, "tool_calls": 100, "thinking": "high", "submit_after_s": 300, "deadline_s": 360},
}
# Published standard paid-tier prices per one million tokens for the event.
PRICES_USD = {
    config.CARBON: (2.0, 10.0),
    config.NEON: (3.0, 15.0),
    config.HYDROGEN: (1.50, 7.50),
    config.DECISION_MODEL: (0.10, 0.0),
}
