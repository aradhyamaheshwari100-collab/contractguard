"""
orchestrator/thresholds.py — All scoring thresholds and guardrails.
Centralised here so they can be overridden via env vars or config
without touching orchestrator logic.
"""
from config import settings

# ── Escalation thresholds ─────────────────────────────────────────────────────
# If suspicion score reaches or exceeds this, trigger History Agent
THRESHOLD_ESCALATE_HISTORY: int = settings.escalation_threshold_history  # default: 70

# If suspicion score reaches or exceeds this, trigger Cross-Reference Agent
THRESHOLD_ESCALATE_CROSSREF: int = settings.escalation_threshold_crossref  # default: 80

# ── Final verdict bands ───────────────────────────────────────────────────────
VERDICT_LOW_MAX: int = 30    # 0-30   → LOW
VERDICT_MEDIUM_MAX: int = 69 # 31-69  → MEDIUM
# 70-100 → HIGH

# ── Depth guardrail ───────────────────────────────────────────────────────────
# Hard cap: prevents infinite orchestrator loops regardless of score
MAX_DEPTH: int = settings.max_investigation_depth  # default: 4

# ── Suspicion score defaults ──────────────────────────────────────────────────
# When source is unavailable, code analysis returns this "uncertain" score
# to trigger escalation to on-chain history as a fallback strategy
UNCERTAIN_SCORE: int = 50

# ── Confidence labels ─────────────────────────────────────────────────────────
def score_to_verdict(score: int) -> tuple[str, str]:
    """Map a final suspicion score to (verdict enum value, human label)."""
    if score <= VERDICT_LOW_MAX:
        return "LOW", "Low Risk"
    elif score <= VERDICT_MEDIUM_MAX:
        return "MEDIUM", "Medium Risk — Proceed with Caution"
    else:
        return "HIGH", "High Fraud Risk — Do Not Interact"
