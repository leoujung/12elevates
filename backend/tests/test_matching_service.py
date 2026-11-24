import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.customer_matching import Candidate
from ai.consent import NoticeVersion, NoticeRegistry, Ledger
from ai.rbac import Actor, AuditLog
from ai.matching_service import customer_matches, business_matches, MatchingRefused

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def refused(fn):
    try:
        fn(); return False
    except MatchingRefused:
        return True

T = "2026-11-26T12:00:00+07:00"
reg = NoticeRegistry()
reg.register(NoticeVersion("v-cust", "matching_customer", "APPROVED", "h", "LEGAL-REF-TEST-001"))
reg.register(NoticeVersion("v-draft", "matching_customer", "DRAFT", "h2", None))
L = Ledger(reg)
AUD = AuditLog()

def cand(pid, member="mem-A"):
    return Candidate(pid, member, True, False,
                     {"declared_wellness_interest": 0.9, "education_preference": 0.8}, [], 2)

member = Actor("u-a", "member", "mem-A")

# consent: p1 and p2 granted, p3 never granted, p4 withdrawn
L.append(member_id="mem-A", prospect_id="p1", purpose="matching_customer", action="GRANTED", notice_version="v-cust", at=T)
L.append(member_id="mem-A", prospect_id="p2", purpose="matching_customer", action="GRANTED", notice_version="v-cust", at=T)
L.append(member_id="mem-A", prospect_id="p4", purpose="matching_customer", action="GRANTED", notice_version="v-cust", at=T)
L.append(member_id="mem-A", prospect_id="p4", purpose="matching_customer", action="WITHDRAWN", notice_version="v-cust", at=T)
pool = [cand("p1"), cand("p2"), cand("p3"), cand("p4")]

r = customer_matches(member, "mem-A", pool, L, AUD, T)
ids = [m.prospect_id for m in r.results]
check("only consented prospects are ranked", set(ids) == {"p1", "p2"})
check("never-consented prospect excluded", "p3" not in ids)
check("withdrawn prospect excluded immediately", "p4" not in ids)
check("exclusion count reported (no ids)", r.excluded_no_consent == 2)

# another tenant cannot use this member's consent or results
other = Actor("u-b", "member", "mem-B")
check("other tenant refused outright", refused(lambda: customer_matches(other, "mem-A", pool, L, AUD, T)))

# platform admin has no member-data access
admin = Actor("u-adm", "platform_admin", None)
check("platform admin refused", refused(lambda: customer_matches(admin, "mem-A", pool, L, AUD, T)))

# candidates from another tenant in the pool are never ranked for this member
mixed = pool + [cand("x1", member="mem-B")]
L.append(member_id="mem-A", prospect_id="x1", purpose="matching_customer", action="GRANTED", notice_version="v-cust", at=T)
r2 = customer_matches(member, "mem-A", mixed, L, AUD, T)
check("foreign-tenant candidate never ranked", "x1" not in [m.prospect_id for m in r2.results])

# a DRAFT notice can never create a consent that reaches matching
try:
    L.append(member_id="mem-A", prospect_id="p9", purpose="matching_customer", action="GRANTED", notice_version="v-draft", at=T)
    draft_blocked = False
except Exception:
    draft_blocked = True
check("DRAFT-backed consent cannot be recorded", draft_blocked)
r3 = customer_matches(member, "mem-A", [cand("p9")], L, AUD, T)
check("prospect without valid consent is not ranked", r3.results == [])

# business path always refused, and audited
check("business matching refused", refused(lambda: business_matches(member, "mem-A", audit=AUD, at=T)))
check("business refusal is audited", AUD.events[-1]["allowed"] is False and AUD.events[-1]["action"] == "business_matching_run")

# every customer run audited with counts only
runs = [e for e in AUD.events if e["action"] == "customer_matching_run"]
check("each completed run audited", len(runs) == 3)
check("audit entry contains no profile values", all("0.9" not in e["reason"] and "declared" not in e["reason"] for e in AUD.events))
check("audit chain verifies", AUD.verify())

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
