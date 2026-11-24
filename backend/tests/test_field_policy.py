import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.field_policy import check_fields_for_matching, FieldRefused, approved_for_operational_use, FIELD_POLICY

results = []
# Hardcoded from Addendum 003 section IV. Deliberately NOT derived from FIELD_POLICY,
# so that reclassifying a health field in the policy cannot silently remove it from the test.
HEALTH_FIELDS_FIXED = ["medical_diagnosis", "declared_condition", "medication", "medical_history",
                       "health_indicator", "assessment_medical_answers"]
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def refused(fn):
    try:
        fn(); return False
    except FieldRefused:
        return True

check("general wellness interest accepted for customer matching",
      check_fields_for_matching(["declared_wellness_interest", "education_preference"], "customer") == ["declared_wellness_interest", "education_preference"])
check("business fields accepted for business matching",
      check_fields_for_matching(["declared_entrepreneurship_interest"], "business") == ["declared_entrepreneurship_interest"])
check("health condition refused for customer matching", refused(lambda: check_fields_for_matching(["declared_condition"], "customer")))
check("health condition refused for business matching", refused(lambda: check_fields_for_matching(["medical_diagnosis"], "business")))
check("medication refused", refused(lambda: check_fields_for_matching(["medication"], "customer")))
check("assessment medical answers refused", refused(lambda: check_fields_for_matching(["assessment_medical_answers"], "customer")))
check("health field mixed with valid field: whole request refused",
      refused(lambda: check_fields_for_matching(["education_preference", "medical_history"], "customer")))
check("unclassified field refused (fail closed)", refused(lambda: check_fields_for_matching(["mystery_field"], "customer")))
check("business field refused for customer engine", refused(lambda: check_fields_for_matching(["declared_entrepreneurship_interest"], "customer")))
check("wellness field refused for business engine", refused(lambda: check_fields_for_matching(["declared_wellness_interest"], "business")))
check("marketing field refused for matching", refused(lambda: check_fields_for_matching(["marketing_opt_in"], "customer")))
check("unknown engine refused", refused(lambda: check_fields_for_matching(["education_preference"], "other")))
check("nothing is APPROVED for operational use yet",
      not any(approved_for_operational_use(f) for f in FIELD_POLICY))
check("declared_wellness_interest is PENDING_REVIEW, not approved",
      FIELD_POLICY["declared_wellness_interest"]["status"] == "PENDING_REVIEW")
check("every health-condition field is EXCLUDED",
      all(m["status"] == "EXCLUDED" for m in FIELD_POLICY.values() if m["class"] == "HEALTH_CONDITION"))
check("every health field refused on BOTH engines (independent of class check)",
      all(refused(lambda f=f, e=e: check_fields_for_matching([f], e))
          for f in HEALTH_FIELDS_FIXED for e in ("customer", "business")))
check("hardcoded health list matches policy (no silent additions or removals)",
      set(HEALTH_FIELDS_FIXED) == {f for f, m in FIELD_POLICY.items() if m["class"] == "HEALTH_CONDITION"})

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
