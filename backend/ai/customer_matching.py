"""12ELEVATE AI Network Building Intelligence - Customer Matching prototype (Task 2).

SYNTHETIC-ONLY. Every candidate must carry synthetic=True. Real-person data is refused
(see gate_candidates). Scoring is deterministic and explainable; the LLM never touches scores.

Three indicators are kept separate:
  match_score      : weighted fit against declared criteria (0-100)
  intent_confidence: strength of lawful intent evidence (0-1)
  data_confidence  : completeness of inputs (0-1); missing fields lower it, never count as zero
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

WEIGHTS_VERSION = "customer-v0.1-hypothesis"

# Hypothesis weights from the master plan. Not calibrated. Must be validated before any real use.
WEIGHTS: dict[str, float] = {
    "declared_wellness_interest": 0.30,
    "education_preference": 0.20,
    "declared_needs_goals": 0.20,
    "engagement_relevance": 0.15,
    "product_category_interest": 0.15,
}


@dataclass
class Candidate:
    prospect_id: str
    member_id: str
    synthetic: bool
    suppressed: bool = False
    # Each dimension is a value in [0, 1] or None (missing).
    dims: dict[str, Optional[float]] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    signals: int = 0  # number of distinct lawful intent signals


@dataclass
class MatchResult:
    prospect_id: str
    match_score: Optional[float]
    intent_confidence: float
    data_confidence: float
    reasons: list[str]
    missing_fields: list[str]
    recommended_action: str
    weights_version: str = WEIGHTS_VERSION


class RefusedInput(Exception):
    pass


def gate_candidates(candidates: list[Candidate], member_id: str) -> list[Candidate]:
    """Eligibility gate. Runs BEFORE any scoring. Fail closed."""
    allowed: list[Candidate] = []
    for c in candidates:
        if not c.synthetic:
            # Real-person data is not allowed until legal approval is recorded (contract: BLOCKED).
            raise RefusedInput(f"non-synthetic candidate refused: {c.prospect_id}")
        if c.member_id != member_id:
            continue  # tenant isolation: never read another member's prospects
        if c.suppressed:
            continue  # opt-out always wins
        allowed.append(c)
    return allowed


def score(c: Candidate) -> MatchResult:
    present = {k: v for k, v in WEIGHTS.items() if c.dims.get(k) is not None}
    missing = sorted(k for k in WEIGHTS if c.dims.get(k) is None)

    total_present_weight = sum(present.values())
    if total_present_weight == 0:
        match = None
    else:
        # Re-normalise over present dimensions so a missing dimension is not scored as zero.
        weighted = sum((c.dims[k] or 0.0) * w for k, w in present.items())
        match = round(100 * weighted / total_present_weight, 1)

    data_confidence = round(total_present_weight, 3)  # share of weight backed by real inputs
    intent_confidence = round(min(1.0, c.signals / 3), 3)  # 3+ distinct signals = strongest

    reasons = [f"{k} = {c.dims[k]:.2f} (weight {WEIGHTS[k]:.0%})" for k in sorted(present, key=lambda x: -present[x])]
    if not reasons:
        reasons = ["no scoreable data"]

    if match is None:
        action = "Do not contact yet: collect declared interests first"
    elif data_confidence < 0.5:
        action = "Ask member to verify interest before outreach"
    elif match >= 70:
        action = "Suggest relevant education session (human decides)"
    else:
        action = "Keep in nurture; no outreach"

    return MatchResult(c.prospect_id, match, intent_confidence, data_confidence, reasons, missing, action)


def rank(candidates: list[Candidate], member_id: str) -> list[MatchResult]:
    eligible = gate_candidates(candidates, member_id)
    results = [score(c) for c in eligible]
    # Unscoreable items sink to the bottom; ties broken by prospect_id for reproducibility.
    results.sort(key=lambda r: (r.match_score is None, -(r.match_score or 0), r.prospect_id))
    return results
