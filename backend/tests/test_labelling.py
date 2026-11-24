import sys, pathlib, copy, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai.eval import labelling as L

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

d1 = L.load(L.E1_FILE); d2 = L.load(L.E2_FILE)

# --- dataset shape ---
check("evaluator 1 has >=100 customer cases", sum(c["engine"] == "customer" for c in d1["cases"]) >= 100)
check("evaluator 1 has >=100 business cases", sum(c["engine"] == "business" for c in d1["cases"]) >= 100)
check("both evaluator files have identical case_id set", set(c["case_id"] for c in d1["cases"]) == set(c["case_id"] for c in d2["cases"]))
check("profiles identical across evaluators", L.check_pair(d1, d2) == [])
check("blind files contain no AI fields", not L._forbidden_hits(d1) and not L._forbidden_hits(d2))
check("no label pre-filled by generator", all(c["human_label"] is None and c["reviewer_id"] is None for c in d1["cases"] + d2["cases"]))
check("structure passes", L.check_structure(d1, "E1") == [] and L.check_structure(d2, "E2") == [])

# --- completeness gate: blank files must FAIL validation ---
check("blank files are NOT complete", len(L.check_complete(d1, "E1")) > 0)

# --- negative: forbidden AI field is detected ---
bad = copy.deepcopy(d1); bad["cases"][0]["match_score"] = 77
check("match_score in evaluator file is refused", any("match_score" in e for e in L.check_structure(bad, "E1")))
bad2 = copy.deepcopy(d1); bad2["cases"][0]["reasons"] = ["x"]
check("AI reasons in evaluator file is refused", any("reasons" in e for e in L.check_structure(bad2, "E1")))

# --- negative: profile mismatch between evaluators is detected ---
mm = copy.deepcopy(d2); mm["cases"][5]["profile"]["declared_wellness_interest"] = 0.123456
check("profile mismatch between evaluators detected", any("profile differs" in e for e in L.check_pair(d1, mm)))

# --- kappa correctness (hand-checked) ---
# perfect agreement over both categories -> 1.0
check("kappa perfect agreement = 1.0", L.cohen_kappa(["RELEVANT", "NOT_RELEVANT"], ["RELEVANT", "NOT_RELEVANT"]) == 1.0)
# a=[R,R,N,N], b=[R,N,N,R]: po=0.5, pe=0.5 -> kappa=0.0
check("kappa chance-level = 0.0", L.cohen_kappa(["RELEVANT", "RELEVANT", "NOT_RELEVANT", "NOT_RELEVANT"],
                                                 ["RELEVANT", "NOT_RELEVANT", "NOT_RELEVANT", "RELEVANT"]) == 0.0)
# a=[R,R,R,N], b=[R,R,N,N]: po=0.75, pe=0.5 -> kappa=0.5
check("kappa hand-computed 0.5", L.cohen_kappa(["RELEVANT"]*3 + ["NOT_RELEVANT"], ["RELEVANT"]*2 + ["NOT_RELEVANT"]*2) == 0.5)
check("kappa undefined when one category only -> None", L.cohen_kappa(["RELEVANT"]*3, ["RELEVANT"]*3) is None)

# --- merge logic on synthetic filled data (test fixture, NOT real labels) ---
f1 = copy.deepcopy(d1); f2 = copy.deepcopy(d2)
for c in f1["cases"]: c.update(human_label="RELEVANT", reviewer_id="TEST-A", reviewed_at="2026-11-24T10:00:00+07:00")
for c in f2["cases"]: c.update(human_label="RELEVANT", reviewer_id="TEST-B", reviewed_at="2026-11-24T10:05:00+07:00")
f2["cases"][0]["human_label"] = "NOT_RELEVANT"   # disagreement -> needs third
f2["cases"][1]["human_label"] = "UNKNOWN"        # UNKNOWN -> needs third
m = L.merge_docs(f1, f2)
check("disagreement routed to NEEDS_THIRD", f1["cases"][0]["case_id"] in m["needs_third_case_ids"])
check("UNKNOWN routed to NEEDS_THIRD", f1["cases"][1]["case_id"] in m["needs_third_case_ids"])
check("agreed case gets final_label", next(r for r in m["cases"] if r["case_id"] == f1["cases"][2]["case_id"])["final_label"] == "RELEVANT")
check("merge does not modify evaluator inputs", f1["cases"][0]["human_label"] == "RELEVANT" and f2["cases"][0]["human_label"] == "NOT_RELEVANT")
m3 = L.merge_docs(f1, f2, prev={"cases": [{"case_id": f1["cases"][0]["case_id"], "eval3_label": "NOT_RELEVANT"}]})
r0 = next(r for r in m3["cases"] if r["case_id"] == f1["cases"][0]["case_id"])
check("third evaluator resolves disagreement", r0["status"] == "RESOLVED_BY_THIRD" and r0["final_label"] == "NOT_RELEVANT")

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
