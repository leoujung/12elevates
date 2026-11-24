"""Round-2 blind labelling set (SYNTHETIC). Stratified per RUBRIC_v0.2.

Design:
  - 100 customer + 100 business cases, deterministic seed.
  - Strata (25 each per engine):
      CLEAR_HIGH   key >= 0.60, supporting mixed        (rule R1)
      CLEAR_LOW    key <= 0.30, supporting mixed        (rule R2)
      MID          key in (0.30, 0.60)                  (rule R3)
      KEY_MISSING  key = null, supporting present       (rule R4)
  - Evaluator files contain ONLY case_id, engine, profile and blank label fields.
  - The stratum of each case is written to a SEPARATE key file that is never sent to evaluators.
  - Labels are never filled here. Blank by design.
"""
import json
import random
from pathlib import Path

SEED = 20261125
PER_STRATUM = 25
KEY_DIMS = {"customer": "declared_wellness_interest", "business": "declared_entrepreneurship_interest"}
SUPPORT_DIMS = {
    "customer": ["education_preference", "declared_needs_goals", "engagement_relevance", "product_category_interest"],
    "business": ["business_goals_alignment", "relevant_experience_declared", "digital_business_interest", "leadership_development_interest"],
}
OUT = Path(__file__).resolve().parents[3] / "docs" / "ai" / "eval" / "round2"


def _r(rng, lo, hi):
    return round(rng.uniform(lo, hi), 2)


def _profile(rng, eng, stratum):
    key, support = KEY_DIMS[eng], SUPPORT_DIMS[eng]
    p = {}
    if stratum == "CLEAR_HIGH":
        p[key] = _r(rng, 0.60, 1.0)
        for d in support:
            p[d] = _r(rng, 0.0, 1.0) if rng.random() < 0.7 else None
    elif stratum == "CLEAR_LOW":
        p[key] = _r(rng, 0.0, 0.30)
        for d in support:
            p[d] = _r(rng, 0.0, 1.0) if rng.random() < 0.7 else None
    elif stratum == "MID":
        p[key] = _r(rng, 0.31, 0.59)
        for d in support:
            p[d] = _r(rng, 0.0, 1.0) if rng.random() < 0.7 else None
    elif stratum == "KEY_MISSING":
        p[key] = None
        for d in support:
            p[d] = _r(rng, 0.0, 1.0) if rng.random() < 0.8 else None
        if all(v is None for v in p.values()):
            p[support[0]] = _r(rng, 0.0, 1.0)  # ensure some evidence exists
    return p


def build(rng):
    cases, key = [], []
    for eng in ("customer", "business"):
        n = 0
        for stratum in ("CLEAR_HIGH", "CLEAR_LOW", "MID", "KEY_MISSING"):
            for _ in range(PER_STRATUM):
                n += 1
                cid = f"r2-{eng[0]}-{n:03d}"
                cases.append({"case_id": cid, "engine": eng, "profile": _profile(rng, eng, stratum)})
                key.append({"case_id": cid, "engine": eng, "stratum": stratum})
    return cases, key


def blind(cases, evaluator_no):
    instructions = (
        "ROUND 2, SYNTHETIC cases only (fictional ids r2-*). Apply RUBRIC_v0.2. "
        "Label each case independently: RELEVANT, NOT_RELEVANT or UNKNOWN. "
        "Put the rule code (R1-R4) and the dimension values used in comment. "
        "Comment is REQUIRED when label is UNKNOWN. Do not look at other evaluator files."
    )
    return {
        "$comment": instructions,
        "evaluator": evaluator_no,
        "round": 2,
        "rubric": "docs/ai/eval/RUBRIC_v0.2.md",
        "label_values": ["RELEVANT", "NOT_RELEVANT", "UNKNOWN"],
        "cases": [{"case_id": c["case_id"], "engine": c["engine"], "profile": c["profile"],
                   "reviewer_id": None, "human_label": None, "comment": None, "reviewed_at": None}
                  for c in cases],
    }


def main():
    rng = random.Random(SEED)
    cases, key = build(rng)
    OUT.mkdir(parents=True, exist_ok=True)
    for n in (1, 2):
        (OUT / f"evaluator_{n}_labels_r2.json").write_text(
            json.dumps(blind(cases, n), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Kept OUT of evaluator-facing files. Used only for coverage checks after labelling.
    (OUT / "_strata_key_DO_NOT_SEND.json").write_text(
        json.dumps({"seed": SEED, "per_stratum": PER_STRATUM, "cases": key}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases x 2 evaluators, strata key separate")


if __name__ == "__main__":
    main()
