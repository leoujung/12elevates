import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.business_matching import (BusinessCandidate, RefusedInput, rank, score,
                                  LEGAL_APPROVED, WEIGHTS)

M = "mem-A"
FULL = {k: 1.0 for k in WEIGHTS}

def cand(pid, dims=FULL, member=M, opt_in=True, suppressed=False, synthetic=True,
         source="declared", signals=3):
    return BusinessCandidate(pid, member, synthetic, opt_in, suppressed, source, dims, signals)

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

# 0. profiling stays off until legal review is recorded
check("LEGAL_APPROVED is False (no real-person matching enabled)", LEGAL_APPROVED is False)

# 1. determinism
a, _ = rank([cand("p1"), cand("p2", {"declared_entrepreneurship_interest": 0.5})], M)
b, _ = rank([cand("p1"), cand("p2", {"declared_entrepreneurship_interest": 0.5})], M)
check("determinism: same input gives same ranking", [(x.prospect_id, x.match_score) for x in a] == [(x.prospect_id, x.match_score) for x in b])

# 2. opt-in gate: no explicit opt-in -> excluded, never scored
r, ex = rank([cand("yes"), cand("no", opt_in=False)], M)
check("no explicit opt-in is excluded", [x.prospect_id for x in r] == ["yes"])
check("exclusion reason recorded as no_explicit_opt_in", any(e.prospect_id == "no" and e.reason == "no_explicit_opt_in" for e in ex))

# 3. job title can never be used as experience
try:
    rank([cand("jt", source="job_title")], M)
    check("experience from job title refused", False)
except RefusedInput:
    check("experience from job title refused", True)

# 4. synthetic gate: non-synthetic refused, fail closed
try:
    rank([cand("real", synthetic=False)], M)
    check("non-synthetic candidate refused", False)
except RefusedInput:
    check("non-synthetic candidate refused", True)

# 5. tenant isolation
r, ex = rank([cand("mine"), cand("theirs", member="mem-B")], M)
check("other tenant never scored", [x.prospect_id for x in r] == ["mine"] and any(e.reason == "other_tenant" for e in ex))

# 6. suppression always wins, even with opt-in
r, ex = rank([cand("optout", suppressed=True)], M)
check("suppressed candidate excluded even with opt-in", r == [] and any(e.reason == "suppressed" for e in ex))

# 7. missing dims not scored as zero
only = score(cand("x", {"declared_entrepreneurship_interest": 1.0}))
check("missing dims re-normalised (single perfect dim = 100)", only.match_score == 100.0)
check("missing dims lower data_confidence", only.data_confidence == 0.30)
check("no data gives None, not 0", score(cand("y", {})).match_score is None)

# 8. development needs: low dimensions are surfaced
dev = score(cand("d", {"declared_entrepreneurship_interest": 0.9, "leadership_development_interest": 0.1}))
check("low dimension listed as development need", "leadership_development_interest" in dev.development_needs)

# 9. ranking order
r, _ = rank([cand("low", {"declared_entrepreneurship_interest": 0.2}), cand("high"), cand("none", {})], M)
check("ranking: highest first, unscoreable last", r[0].prospect_id == "high" and r[-1].prospect_id == "none")

# 10. reasons and separate indicators
s = score(cand("sep", signals=2))
check("every scored result has explanation", bool(s.reasons) and s.reasons[0] != "no scoreable data")
check("indicators kept separate", s.intent_confidence != s.match_score and s.data_confidence != s.match_score)

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
