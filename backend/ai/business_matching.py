"""12ELEVATE AI Network Building Intelligence - Business Builder Matching prototype (Task 3).

SYNTHETIC-ONLY. Real-person profiling and member introductions are NOT enabled:
LEGAL_APPROVED is False (contract: business matching legal basis = BLOCKED).
Gates, applied in order, fail closed:
  1. non-synthetic input -> refused (RefusedInput)
  2. experience inferred from job title -> refused (RefusedInput)
  3. other tenant -> skipped
  4. suppressed -> skipped
  5. no explicit candidate opt-in -> skipped (excluded with reason)
Scores are deterministic. The LLM never sets scores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

WEIGHTS_VERSION = "business-v0.1-hypothesis"
# Contract: business_matching legal_basis = BLOCKED until legal review is recorded.
LEGAL_APPROVED = False

# Hypothesis weights from the master plan. Not calibrated.
WEIGHTS: dict[str, float] = {
    "declared_entrepreneurship_interest": 0.30,
    "business_goals_alignment": 0.25,
    "relevant_experience_declared": 0.15,
    "digital_business_interest": 0.15,
    "leadership_development_interest": 0.15,
}

LOW_DIM_THRESHOLD = 0.4


class RefusedInput(Exception):
    pass


@dataclass
class BusinessCandidate:
    prospect_id: str
    member_id: str
    synthetic: bool
    business_opt_in: bool = False
    suppressed: bool = False
    experience_source: str = "declared"  # "declared" | "job_title" (job_title is forbidden)
    dims: dict[str, Optional[float]] = field(default_factory=dict)
    signals: int = 0


@dataclass
class BusinessMatch:
    prospect_id: str
    match_score: Optional[float]
    intent_confidence: float
    data_confidence: float
    reasons: list[str]
    missing_fields: list[str]
    development_needs: list[str]
    recommended_action: str
    weights_version: str = WEIGHTS_VERSION


@dataclass
class Excluded:
    prospect_id: str
    reason: str


def check_input(c: BusinessCandidate) -> None:
    """Hard refusals. Raise, never silently score."""
    if not c.synthetic:
        raise RefusedInput(f"non-synthetic business candidate refused: {c.prospect_id}")
    if c.experience_source == "job_title":
        raise RefusedInput(f"experience inferred from job title is forbidden: {c.prospect_id}")


def eligibility(c: BusinessCandidate, member_id: str) -> Optional[str]:
    """Return None if eligible, else the exclusion reason."""
    if c.member_id != member_id:
        return "other_tenant"
    if c.suppressed:
        return "suppressed"
    if not c.business_opt_in:
        return "no_explicit_opt_in"
    return None


def score(c: BusinessCandidate) -> BusinessMatch:
    present = {k: v for k, v in WEIGHTS.items() if c.dims.get(k) is not None}
    missing = sorted(k for k in WEIGHTS if c.dims.get(k) is None)
    total_present_weight = sum(present.values())

    if total_present_weight == 0:
        match = None
    else:
        weighted = sum((c.dims[k] or 0.0) * w for k, w in present.items())
        match = round(100 * weighted / total_present_weight, 1)

    data_confidence = round(total_present_weight, 3)
    intent_confidence = round(min(1.0, c.signals / 3), 3)

    reasons = [f"{k} = {c.dims[k]:.2f} (weight {WEIGHTS[k]:.0%})"
               for k in sorted(present, key=lambda x: -present[x])] or ["no scoreable data"]
    development = sorted(k for k in present if (c.dims[k] or 0.0) < LOW_DIM_THRESHOLD)

    if match is None:
        action = "Do not invite yet: collect declared business interests first"
    elif data_confidence < 0.5:
        action = "Ask candidate to confirm business interests before any invitation"
    elif match >= 70:
        action = "Offer an opt-in business education invitation (member decides; no automatic message)"
    else:
        action = "Nurture only; no invitation"

    return BusinessMatch(c.prospect_id, match, intent_confidence, data_confidence,
                         reasons, missing, development, action)


def rank(candidates: list[BusinessCandidate], member_id: str) -> tuple[list[BusinessMatch], list[Excluded]]:
    eligible: list[BusinessCandidate] = []
    excluded: list[Excluded] = []
    for c in candidates:
        check_input(c)  # raises on violation; runs for every candidate
        reason = eligibility(c, member_id)
        if reason is None:
            eligible.append(c)
        else:
            excluded.append(Excluded(c.prospect_id, reason))
    results = [score(c) for c in eligible]
    results.sort(key=lambda r: (r.match_score is None, -(r.match_score or 0), r.prospect_id))
    return results, excluded
