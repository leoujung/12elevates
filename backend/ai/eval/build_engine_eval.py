"""Blind evaluation of ENGINE OUTPUT for Precision@5 (SYNTHETIC candidates only).

Flow:
  1. For each query (a synthetic member), run the real engine (customer or business) on a
     pool of synthetic candidates and keep the top-5.
  2. Evaluator files contain the UNIQUE top-5 items only, shuffled, with opaque item_ids.
     No rank, no match_score, no confidence, no reasons, no query grouping.
  3. The mapping item_id -> (query, rank, score) is written to a PRIVATE key outside the repo.
  4. After labelling, precision_at_5() joins labels with the key.

Evaluators judge relevance from the profile itself (holistic judgement). They do NOT apply
rubric R1-R4: this step measures the engine against human judgement, not rule consistency.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "backend"))

from ai.customer_matching import Candidate, rank as rank_customer  # noqa: E402
from ai.business_matching import BusinessCandidate, rank as rank_business  # noqa: E402
from ai.customer_matching import WEIGHTS as CW  # noqa: E402
from ai.business_matching import WEIGHTS as BW  # noqa: E402

SEED = 20261126
QUERIES_PER_ENGINE = 25     # 25 x top-5 = up to 125 slots; dedupe must leave >= MIN_ITEMS
POOL_SIZE = 12
MIN_ITEMS = 100
TOP_K = 5
EVAL_DIR = REPO / "docs" / "ai" / "eval" / "engine_eval"
PRIVATE_DIR = Path("C:/Users/ASUS/AppData/Local/hermes/cache/scratch/private_keys")
EVAL_LABEL_VALUES = ("RELEVANT", "NOT_RELEVANT", "UNKNOWN")


def _rand_dims(rng: random.Random, dims) -> dict:
    return {d: (None if rng.random() < 0.15 else round(rng.random(), 2)) for d in dims}


def _item_id(engine: str, query: str, prospect: str) -> str:
    h = hashlib.sha256(f"{SEED}|{engine}|{query}|{prospect}".encode()).hexdigest()[:12]
    return f"e{engine[0]}-{h}"


def build(rng: random.Random):
    """Return (evaluator_items, private_key) for both engines."""
    items, key = {}, []
    for engine in ("customer", "business"):
        for q in range(1, QUERIES_PER_ENGINE + 1):
            member = f"mem-q{engine[0]}{q:03d}"
            pool = []
            for i in range(POOL_SIZE):
                pid = f"syn-{engine[0]}{q:03d}-{i:02d}"
                if engine == "customer":
                    dims = _rand_dims(rng, CW)
                    pool.append(Candidate(pid, member, True, False, dims, [], rng.randint(0, 4)))
                else:
                    dims = _rand_dims(rng, BW)
                    pool.append(BusinessCandidate(pid, member, True, True, False, "declared", dims, rng.randint(0, 4)))
            ranked = rank_customer(pool, member) if engine == "customer" else rank_business(pool, member)[0]
            top = ranked[:TOP_K]
            profiles = {c.prospect_id: (c.dims) for c in pool}
            for rank_pos, r in enumerate(top, start=1):
                iid = _item_id(engine, member, r.prospect_id)
                items.setdefault(iid, {"item_id": iid, "engine": engine, "profile": profiles[r.prospect_id]})
                key.append({"item_id": iid, "engine": engine, "query": member, "rank": rank_pos,
                            "prospect_id": r.prospect_id, "match_score": r.match_score,
                            "intent_confidence": r.intent_confidence, "data_confidence": r.data_confidence})
    return items, key


def write(items: dict, key: list) -> None:
    rng = random.Random(SEED + 1)
    ordered = list(items.values())
    rng.shuffle(ordered)  # no meaningful order leaks through file order
    for engine in ("customer", "business"):
        n = sum(1 for x in ordered if x["engine"] == engine)
        if n < MIN_ITEMS:
            raise SystemExit(f"{engine}: {n} unique items, minimum is {MIN_ITEMS}. Increase QUERIES_PER_ENGINE.")
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    instructions = (
        "SYNTHETIC candidates only (fictional ids). For each item, judge from the profile alone whether this "
        "person is a reasonable candidate for a wellness/business education invitation. Use RELEVANT, "
        "NOT_RELEVANT or UNKNOWN. Use your own judgement; there is no scoring rule to apply. Do not guess "
        "missing values. Fill reviewer_id, reviewed_at, and an optional comment (one short sentence). "
        "Do not try to find out how the ranking was produced."
    )
    for n in (1, 2):
        doc = {"$comment": instructions, "evaluator": n, "task": "engine_output_precision_at_5",
               "label_values": list(EVAL_LABEL_VALUES),
               "items": [{"item_id": x["item_id"], "engine": x["engine"], "profile": x["profile"],
                          "human_label": None, "reviewer_id": None, "comment": None, "reviewed_at": None}
                         for x in ordered]}
        (EVAL_DIR / f"evaluator_{n}_engine_eval.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (PRIVATE_DIR / "engine_eval_KEY_DO_NOT_COMMIT.json").write_text(
        json.dumps({"seed": SEED, "top_k": TOP_K, "rows": key}, indent=2) + "\n", encoding="utf-8")


def precision_at_5(key_rows: list, labels: dict, engine: str) -> dict:
    """labels: item_id -> agreed human label. Missing labels are counted as not relevant and reported."""
    queries: dict[str, list] = {}
    for r in key_rows:
        if r["engine"] == engine:
            queries.setdefault(r["query"], []).append(r)
    per_query = []
    missing = 0
    for q, rows in queries.items():
        top = sorted(rows, key=lambda r: r["rank"])[:TOP_K]
        hits = 0
        for r in top:
            lab = labels.get(r["item_id"])
            if lab is None:
                missing += 1
            if lab == "RELEVANT":
                hits += 1
        per_query.append(hits / TOP_K)
    p5 = sum(per_query) / len(per_query) if per_query else None
    return {"engine": engine, "queries": len(per_query), "precision_at_5": None if p5 is None else round(p5, 4),
            "unlabelled_slots": missing}


if __name__ == "__main__":
    items, key = build(random.Random(SEED))
    write(items, key)
    per = {e: sum(1 for x in items.values() if x["engine"] == e) for e in ("customer", "business")}
    print("unique items per engine:", per)
    print("wrote evaluator files to", EVAL_DIR)
    print("wrote private key to", PRIVATE_DIR / "engine_eval_KEY_DO_NOT_COMMIT.json")
