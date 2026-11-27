"""NBI deterministic matching (Phase 1, offline).

Rules:
- No LLM, no network, no database access in this module. Pure functions.
- Fit, intent and data confidence are returned separately. Never combined.
- Consent and source verification are gates decided by the caller's stored
  records, never inferred by this module or by any model.
- Business pathway never reads health or wellness assessment fields.
- Industry match alone is not intent. Intent needs an explicit signal.
"""

RULES_VERSION = "nbi-rules-v1"

PATHWAYS = ("business", "customer")

# Explicit, voluntary signals only. Each adds to intent.
INTENT_SIGNALS = {
    "explicit_inquiry": 50,
    "declared_goal": 20,
    "registration": 20,
    "requested_followup": 10,
}

# Health/assessment fields that must never feed the business pathway.
HEALTH_FIELDS = {"assessment_score", "health_answers", "declared_needs_goals"}

# Fields that make a record usable. Weighted for data confidence.
DATA_FIELDS = {
    "name": 20,
    "contact": 30,        # phone or email
    "source_key": 20,     # provenance
    "captured_at": 15,
    "consent_record": 15,
}


def _clamp(value, low=0, high=100):
    return max(low, min(high, int(round(value))))


def data_confidence(record):
    """Share of required provenance and contact fields present, 0-100."""
    present = {
        "name": bool((record.get("name") or "").strip()),
        "contact": bool(record.get("phone") or record.get("email")),
        "source_key": bool(record.get("source_key")),
        "captured_at": bool(record.get("captured_at")),
        "consent_record": bool(record.get("consent_record_id")),
    }
    total = sum(DATA_FIELDS.values())
    got = sum(w for k, w in DATA_FIELDS.items() if present[k])
    missing = [k for k, ok in present.items() if not ok]
    return _clamp(100 * got / total), missing


def fit_score(member_targets, prospect_tags, pathway):
    """Overlap between the member's target tags and the prospect's tags.

    Returns 0-100. Zero when the member declared no targets (no basis to fit).
    """
    targets = {t.strip().lower() for t in member_targets if t and t.strip()}
    tags = {t.strip().lower() for t in prospect_tags if t and t.strip()}
    if not targets:
        return 0, ["no member target tags declared"]
    overlap = targets & tags
    score = 100 * len(overlap) / len(targets)
    reasons = [f"matched target tag: {t}" for t in sorted(overlap)]
    if not overlap:
        reasons.append("no overlap between member targets and prospect tags")
    return _clamp(score), reasons


def intent_confidence(signals):
    """Sum of explicit, voluntary signals, capped at 100."""
    score = 0
    reasons = []
    for key, weight in INTENT_SIGNALS.items():
        if signals.get(key):
            score += weight
            reasons.append(f"explicit signal: {key} (+{weight})")
    if score == 0:
        reasons.append("no explicit intent signal (industry match alone is not intent)")
    return _clamp(score), reasons


def evaluate(record, member, pathway):
    """Evaluate one prospect record for one member and one pathway.

    record keys: name, phone, email, source_key, captured_at, consent_record_id,
                 consent_granted (bool), source_verified (bool), tags (list),
                 signals (dict of INTENT_SIGNALS keys -> bool),
                 duplicate_of (str or None), plus optional health fields.
    member keys: target_tags (list).
    Returns a dict. Scores are None when a gate blocks evaluation.
    """
    if pathway not in PATHWAYS:
        raise ValueError("pathway must be 'business' or 'customer'")

    result = {
        "rules_version": RULES_VERSION,
        "pathway": pathway,
        "status": None,
        "fit_score": None,
        "intent_confidence": None,
        "data_confidence": None,
        "reasons": [],
    }

    # Gate 1: consent. Without it nothing is scored or shown as a match.
    if not record.get("consent_granted") or not record.get("consent_record_id"):
        result["status"] = "rejected_no_consent"
        result["reasons"].append("no recorded consent for this purpose")
        return result

    # Gate 2: provenance. Unverified sources are quarantined, not scored.
    if not record.get("source_verified") or not record.get("source_key"):
        result["status"] = "quarantined_unverified_source"
        result["reasons"].append("source provenance not verified")
        return result

    # Gate 3: duplicates never silently transfer ownership.
    if record.get("duplicate_of"):
        result["status"] = "needs_review_duplicate"
        result["reasons"].append(f"possible duplicate of {record['duplicate_of']}")
        return result

    # Business pathway must not use health or wellness assessment data.
    if pathway == "business":
        used_health = HEALTH_FIELDS & set(record)
        if used_health:
            result["status"] = "rejected_sensitive_field"
            result["reasons"].append(
                "health/assessment fields present; not allowed in business pathway"
            )
            return result

    fit, fit_reasons = fit_score(member.get("target_tags", []), record.get("tags", []), pathway)
    intent, intent_reasons = intent_confidence(record.get("signals", {}))
    data, missing = data_confidence(record)

    result.update(
        status="scored",
        fit_score=fit,
        intent_confidence=intent,
        data_confidence=data,
    )
    result["reasons"] = fit_reasons + intent_reasons
    if missing:
        result["reasons"].append("missing data fields: " + ", ".join(missing))
    return result
