"""Generate blind-labelling files for two evaluators (SYNTHETIC cases only, labels left empty).

Deterministic: fixed seed, so re-running produces identical profiles.
Writes evaluator_1_labels.json and evaluator_2_labels.json with identical case_id, engine, profile.
Never writes human_label or reviewer_id. Never writes model output.
"""
import json
import random
from pathlib import Path

SEED = 20261124
N_PER_ENGINE = 100
DIMS = {
    "customer": ["declared_wellness_interest", "education_preference", "declared_needs_goals",
                 "engagement_relevance", "product_category_interest"],
    "business": ["declared_entrepreneurship_interest", "business_goals_alignment",
                 "relevant_experience_declared", "digital_business_interest", "leadership_development_interest"],
}
OUT = Path(__file__).resolve().parents[3] / "docs" / "ai" / "eval"


def make_cases(rng: random.Random) -> list[dict]:
    cases = []
    for eng in ("customer", "business"):
        for i in range(1, N_PER_ENGINE + 1):
            profile = {}
            for d in DIMS[eng]:
                # ~15% of dimensions are missing (None), so data-confidence cases are exercised.
                profile[d] = None if rng.random() < 0.15 else round(rng.random(), 2)
            cases.append({"case_id": f"syn-{eng[0]}-{i:03d}", "engine": eng, "profile": profile})
    return cases


def blind_case(c: dict) -> dict:
    return {
        "case_id": c["case_id"],
        "engine": c["engine"],
        "profile": c["profile"],
        "reviewer_id": None,
        "human_label": None,
        "comment": None,
        "reviewed_at": None,
    }


def main() -> None:
    rng = random.Random(SEED)
    cases = make_cases(rng)
    OUT.mkdir(parents=True, exist_ok=True)
    instructions = (
        "SYNTHETIC cases only (fictional ids syn-*). Label each case independently. "
        "Use RELEVANT, NOT_RELEVANT, or UNKNOWN. Do not look at any other evaluator's file. "
        "Fill reviewer_id (your name or code), comment (optional), reviewed_at (ISO-8601 with timezone)."
    )
    for n in (1, 2):
        doc = {
            "$comment": instructions,
            "evaluator": n,
            "label_values": ["RELEVANT", "NOT_RELEVANT", "UNKNOWN"],
            "cases": [blind_case(c) for c in cases],
        }
        (OUT / f"evaluator_{n}_labels.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases x 2 evaluators to {OUT}")


if __name__ == "__main__":
    main()
