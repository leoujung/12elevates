import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.consent import (NoticeVersion, NoticeRegistry, Ledger, ConsentError, may_match,
                        BUSINESS_MATCHING_ENABLED)

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def refused(fn):
    try:
        fn(); return False
    except ConsentError:
        return True

T = "2026-11-26T09:00:00+07:00"
def setup():
    reg = NoticeRegistry()
    reg.register(NoticeVersion("v-draft-cust", "matching_customer", "DRAFT", "h1", None))
    reg.register(NoticeVersion("v-appr-cust", "matching_customer", "APPROVED", "h2", "LEGAL-REF-TEST-001"))
    reg.register(NoticeVersion("v-appr-mkt", "marketing", "APPROVED", "h3", "LEGAL-REF-TEST-002"))
    return reg, Ledger(reg)

# --- notice rules ---
check("APPROVED notice without legal record reference refused",
      refused(lambda: NoticeVersion("x", "matching_customer", "APPROVED", "h", None)))
check("unknown notice status refused", refused(lambda: NoticeVersion("x", "matching_customer", "MAYBE", "h", None)))
check("DRAFT notice can exist (working draft) without legal ref",
      NoticeVersion("d", "matching_customer", "DRAFT", "h", None).status == "DRAFT")

# --- consent granting ---
reg, L = setup()
check("GRANTED with DRAFT notice refused", refused(lambda: L.append(member_id="m1", prospect_id="p1",
      purpose="matching_customer", action="GRANTED", notice_version="v-draft-cust", at=T)))
check("GRANTED without notice refused", refused(lambda: L.append(member_id="m1", prospect_id="p1",
      purpose="matching_customer", action="GRANTED", notice_version=None, at=T)))
L.append(member_id="m1", prospect_id="p1", purpose="matching_customer", action="GRANTED",
         notice_version="v-appr-cust", at=T)
check("GRANTED with APPROVED notice accepted", may_match(L, "m1", "p1", "matching_customer"))

# --- withdrawal takes effect immediately ---
L.append(member_id="m1", prospect_id="p1", purpose="matching_customer", action="WITHDRAWN",
         notice_version="v-appr-cust", at="2026-11-26T10:00:00+07:00")
check("withdrawal blocks matching immediately", may_match(L, "m1", "p1", "matching_customer") is False)
check("re-grant after withdrawal works again", (L.append(member_id="m1", prospect_id="p1", purpose="matching_customer",
      action="GRANTED", notice_version="v-appr-cust", at="2026-11-26T11:00:00+07:00") and True)
      and may_match(L, "m1", "p1", "matching_customer"))
check("withdrawal history is preserved (append-only, 3 events)", len(L.events) == 3)

# --- purpose separation ---
check("consent for customer does not grant marketing", may_match(L, "m1", "p1", "marketing") is False)

# --- matching_business is disabled ---
check("BUSINESS_MATCHING_ENABLED is False", BUSINESS_MATCHING_ENABLED is False)
check("cannot record business consent while disabled", refused(lambda: L.append(member_id="m1", prospect_id="p2",
      purpose="matching_business", action="GRANTED", notice_version="v-appr-cust", at=T)))
check("may_match business is False even with consent", may_match(L, "m1", "p1", "matching_business") is False)

# --- tenant isolation ---
check("other tenant cannot match same prospect id", may_match(L, "m-other", "p1", "matching_customer") is False)

# --- hash chain: tamper detection ---
check("untampered ledger verifies", L.verify_chain())
L.events[0]["action"] = "WITHDRAWN"   # tamper with history
check("tampered ledger fails verification", L.verify_chain() is False)

# --- unknown action / purpose rejected ---
reg2, L2 = setup()
check("unknown action refused", refused(lambda: L2.append(member_id="m", prospect_id="p", purpose="matching_customer",
      action="DELETE", notice_version=None, at=T)))
check("unknown purpose refused", refused(lambda: L2.append(member_id="m", prospect_id="p", purpose="sell",
      action="DENIED", notice_version=None, at=T)))

# --- duplicate notice version refused ---
check("duplicate notice version refused", refused(lambda: reg.register(
      NoticeVersion("v-appr-cust", "matching_customer", "APPROVED", "h", "LEGAL-REF-TEST-001"))))

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
