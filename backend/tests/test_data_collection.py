import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.data_collection import (RejectedRecord, validate_engagement_event, validate_consent, may_enter_matching)

APPROVED = set()  # no notice version has a written legal record yet
results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def rejects(fn):
    try:
        fn(); return False
    except RejectedRecord:
        return True

ok_event = {"event_id": "evt_1", "member_id": "mem-A", "prospect_id": "p1",
            "event_type": "WEBINAR_ATTENDED", "occurred_at": "2026-11-24T10:00:00+07:00"}
check("valid engagement event accepted", validate_engagement_event(ok_event).event_id == "evt_1")
check("unknown event type rejected", rejects(lambda: validate_engagement_event({**ok_event, "event_type": "CLICKED_ANYTHING"})))
check("missing event_id rejected (no idempotency key)", rejects(lambda: validate_engagement_event({k: v for k, v in ok_event.items() if k != "event_id"})))
check("raw assessment answers refused", rejects(lambda: validate_engagement_event({**ok_event, "raw_answers": ["a", "b"]})))
check("missing member_id (tenant) rejected", rejects(lambda: validate_engagement_event({k: v for k, v in ok_event.items() if k != "member_id"})))

check("consent granted=True without approved notice refused", rejects(lambda: validate_consent(
    {"purpose": "matching_customer", "granted": True, "notice_version": "v1", "granted_at": "2026-11-24T10:00:00+07:00"}, APPROVED)))
check("consent granted=True with no notice refused", rejects(lambda: validate_consent(
    {"purpose": "matching_customer", "granted": True, "granted_at": "2026-11-24T10:00:00+07:00"}, APPROVED)))
check("pre-checked consent (granted missing) refused", rejects(lambda: validate_consent(
    {"purpose": "matching_customer", "notice_version": "v1", "granted_at": "x"}, APPROVED)))
check("unknown purpose refused", rejects(lambda: validate_consent({"purpose": "sell", "granted": False}, APPROVED)))

APPROVED_TEST = {"v-test-only"}
c = validate_consent({"purpose": "matching_customer", "granted": True, "notice_version": "v-test-only",
                      "granted_at": "2026-11-24T10:00:00+07:00"}, APPROVED_TEST)
check("consent accepted only when notice is in approved record", c.granted is True)

check("matching gate: no consent record -> blocked", may_enter_matching(None, "matching_customer") is False)
check("matching gate: granted and active -> allowed", may_enter_matching(c, "matching_customer") is True)
check("matching gate: wrong purpose -> blocked", may_enter_matching(c, "matching_business") is False)

withdrawn = validate_consent({"purpose": "matching_customer", "granted": True, "notice_version": "v-test-only",
                              "granted_at": "x", "withdrawn_at": "y"}, APPROVED_TEST)
check("matching gate: withdrawn consent blocks immediately", may_enter_matching(withdrawn, "matching_customer") is False)

denied = validate_consent({"purpose": "matching_customer", "granted": False, "notice_version": None,
                           "granted_at": None}, APPROVED)
check("matching gate: explicit refusal blocks", may_enter_matching(denied, "matching_customer") is False)

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
