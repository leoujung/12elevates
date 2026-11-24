import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.customer_matching import Candidate, RefusedInput, rank, score

M = "mem-A"
FULL = {"declared_wellness_interest": 1.0, "education_preference": 1.0, "declared_needs_goals": 1.0,
        "engagement_relevance": 1.0, "product_category_interest": 1.0}

def cand(pid, dims, signals=3, member=M, suppressed=False, synthetic=True):
    return Candidate(pid, member, synthetic, suppressed, dims, [], signals)

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

# 1. determinism: same input -> identical output
a = rank([cand("p1", FULL), cand("p2", {"declared_wellness_interest": 0.5})], M)
b = rank([cand("p1", FULL), cand("p2", {"declared_wellness_interest": 0.5})], M)
check("determinism: same input gives same ranking and scores", [(r.prospect_id, r.match_score) for r in a] == [(r.prospect_id, r.match_score) for r in b])

# 2. missing data is NOT zero: a candidate with only 1 dimension must not be penalised as if others were 0
only_one = score(cand("x", {"declared_wellness_interest": 1.0}))
check("missing dims are excluded and re-normalised (single perfect dim scores 100)", only_one.match_score == 100.0)
check("missing dims lower data_confidence", only_one.data_confidence == 0.30)
check("missing fields are listed", "education_preference" in only_one.missing_fields)

# 3. no data at all -> no score, not a fake 0
none = score(cand("y", {}))
check("no data gives match_score None (not 0)", none.match_score is None)
check("no data gives recommended action to collect first", "collect" in none.recommended_action.lower())

# 4. ranking order: higher score first, unscoreable last
r = rank([cand("low", {"declared_wellness_interest": 0.2}), cand("high", FULL), cand("none", {})], M)
check("ranking: highest match first", [x.prospect_id for x in r][0] == "high")
check("ranking: unscoreable last", [x.prospect_id for x in r][-1] == "none")

# 5. synthetic gate: any non-synthetic candidate is refused (fail closed)
try:
    rank([cand("real", FULL, synthetic=False)], M)
    check("non-synthetic input refused", False)
except RefusedInput:
    check("non-synthetic input refused", True)

# 6. tenant isolation: other member's prospects never appear
t = rank([cand("mine", FULL), cand("theirs", FULL, member="mem-B")], M)
check("tenant isolation: other tenant excluded", [x.prospect_id for x in t] == ["mine"])

# 7. suppression always wins
s = rank([cand("ok", FULL), cand("optout", FULL, suppressed=True)], M)
check("suppressed prospect is never matched", [x.prospect_id for x in s] == ["ok"])

# 8. intent confidence is derived from signal count, capped at 1.0
check("intent_confidence 0 signals", score(cand("i0", FULL, signals=0)).intent_confidence == 0.0)
check("intent_confidence capped at 1.0", score(cand("i9", FULL, signals=9)).intent_confidence == 1.0)

# 9. match_score / intent / data stay separate fields
rr = score(cand("sep", FULL, signals=2))
check("three indicators kept separate", rr.match_score is not None and rr.intent_confidence != rr.match_score and rr.data_confidence != rr.match_score)

# 10. explanation present for every scored result
check("every scored result has reasons", all(x.reasons for x in rank([cand("e", FULL)], M)))

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
