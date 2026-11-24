"""Field classification policy for AI matching (Addendum 12E-LEGAL-AI-NBI-003, synthetic data only).

Rules from the addendum:
  - Classification is decided by ACTUAL CONTENT, not by field name alone.
  - General wellness interests (healthy lifestyle, nutrition, fitness education, webinar
    preference) may be used for Customer Matching after classification and legal-basis check.
  - Information revealing a health condition (diagnosis, disease, treatment, medication,
    medical history, health indicators, medical assessment answers) is EXCLUDED from general
    matching by default.
  - declared_wellness_interest must be reviewed against its actual values and collection
    method before operational use. Until then it is marked PENDING_REVIEW, not APPROVED.

Fail closed: any field not in the table is refused.
"""
from __future__ import annotations

GENERAL_WELLNESS = "GENERAL_WELLNESS"      # eligible for Customer Matching after review
HEALTH_CONDITION = "HEALTH_CONDITION"      # excluded from general matching
BUSINESS_INTEREST = "BUSINESS_INTEREST"    # eligible for Business Matching after preconditions
MARKETING = "MARKETING"                    # separate purpose, never matching
UNCLASSIFIED = "UNCLASSIFIED"

# status per field: APPROVED only after the addendum's review. Nothing is APPROVED yet.
FIELD_POLICY: dict[str, dict] = {
    "declared_wellness_interest": {"class": GENERAL_WELLNESS, "status": "PENDING_REVIEW",
        "note": "addendum III: review actual values and collection method first"},
    "education_preference": {"class": GENERAL_WELLNESS, "status": "PENDING_REVIEW", "note": ""},
    "product_category_interest": {"class": GENERAL_WELLNESS, "status": "PENDING_REVIEW", "note": ""},
    "declared_needs_goals": {"class": GENERAL_WELLNESS, "status": "PENDING_REVIEW",
        "note": "free-text risk: must not carry medical content"},
    "engagement_relevance": {"class": GENERAL_WELLNESS, "status": "PENDING_REVIEW", "note": ""},
    "declared_entrepreneurship_interest": {"class": BUSINESS_INTEREST, "status": "PENDING_REVIEW", "note": ""},
    "business_goals_alignment": {"class": BUSINESS_INTEREST, "status": "PENDING_REVIEW", "note": ""},
    "digital_business_interest": {"class": BUSINESS_INTEREST, "status": "PENDING_REVIEW", "note": ""},
    "leadership_development_interest": {"class": BUSINESS_INTEREST, "status": "PENDING_REVIEW", "note": ""},
    "relevant_experience_declared": {"class": BUSINESS_INTEREST, "status": "PENDING_REVIEW",
        "note": "declared only; never inferred from job title"},
    # health-condition fields: never eligible for general matching
    "medical_diagnosis": {"class": HEALTH_CONDITION, "status": "EXCLUDED", "note": ""},
    "declared_condition": {"class": HEALTH_CONDITION, "status": "EXCLUDED", "note": ""},
    "medication": {"class": HEALTH_CONDITION, "status": "EXCLUDED", "note": ""},
    "medical_history": {"class": HEALTH_CONDITION, "status": "EXCLUDED", "note": ""},
    "health_indicator": {"class": HEALTH_CONDITION, "status": "EXCLUDED", "note": ""},
    "assessment_medical_answers": {"class": HEALTH_CONDITION, "status": "EXCLUDED", "note": ""},
    "marketing_opt_in": {"class": MARKETING, "status": "PENDING_REVIEW", "note": "separate purpose"},
}


class FieldRefused(Exception):
    pass


def check_fields_for_matching(fields: list[str], engine: str) -> list[str]:
    """Return the fields that may be used for the engine. Raises on any refused field.

    engine: 'customer' or 'business'. Health fields and unknown fields always raise.
    """
    allowed_classes = {
        "customer": {GENERAL_WELLNESS},
        "business": {BUSINESS_INTEREST},
    }.get(engine)
    if allowed_classes is None:
        raise FieldRefused(f"unknown engine {engine}")
    accepted: list[str] = []
    for f in fields:
        meta = FIELD_POLICY.get(f)
        if meta is None:
            raise FieldRefused(f"unclassified field refused: {f}")
        if meta["class"] == HEALTH_CONDITION:
            raise FieldRefused(f"health-condition field excluded from general matching: {f}")
        if meta["class"] not in allowed_classes:
            raise FieldRefused(f"field {f} is not eligible for {engine} matching")
        accepted.append(f)
    return accepted


def approved_for_operational_use(field: str) -> bool:
    """True only after the addendum's review is recorded. Nothing is approved yet."""
    meta = FIELD_POLICY.get(field)
    return bool(meta) and meta["status"] == "APPROVED"
