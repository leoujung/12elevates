import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.rbac import Actor, AuditLog, authorize, BUSINESS_MATCHING_ENABLED

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

T = "2026-11-26T09:00:00+07:00"
A = AuditLog()
member = Actor("u-m1", "member", "mem-A")
other = Actor("u-m2", "member", "mem-B")
admin = Actor("u-adm", "platform_admin", None)
dev = Actor("u-dev", "developer", None)
ev = Actor("u-ev", "evaluator", None)

check("member can view own matches", authorize(member, "view_own_matches", "mem-A", A, T))
check("member cannot view another tenant's matches", authorize(member, "view_own_matches", "mem-B", A, T) is False)
check("member cannot read another member's consent records", authorize(other, "record_own_consent", "mem-A", A, T) is False)
check("platform_admin has NO member data access", authorize(admin, "view_own_matches", "mem-A", A, T) is False)
check("platform_admin can manage roles", authorize(admin, "manage_roles", None, A, T))
check("developer cannot touch member matches", authorize(dev, "view_own_matches", "mem-A", A, T) is False)
check("evaluator can label items", authorize(ev, "label_items", None, A, T))
check("evaluator cannot view matches", authorize(ev, "view_own_matches", None, A, T) is False)
check("unknown role denied", authorize(Actor("x", "hacker", "mem-A"), "view_own_matches", "mem-A", A, T) is False)
check("member without tenant denied", authorize(Actor("u", "member", None), "view_own_matches", None, A, T) is False)
check("business matching disabled for all roles", BUSINESS_MATCHING_ENABLED is False
      and authorize(admin, "run_matching_business", None, A, T) is False)
check("view_business_matches denied even for owner", authorize(member, "view_business_matches", "mem-A", A, T) is False)

# every decision audited, allowed AND denied
n_before = len(A.events)
authorize(other, "view_own_matches", "mem-A", A, T)  # denied cross-tenant
check("denied cross-tenant attempt is audited", len(A.events) == n_before + 1 and A.events[-1]["allowed"] is False)
check("denied entry records reason, not profile values",
      A.events[-1]["reason"] == "cross-tenant access refused" and "profile" not in str(A.events[-1]))
check("audit chain verifies", A.verify())
A.events[2]["allowed"] = True   # tamper
check("tampered audit chain fails verification", A.verify() is False)

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
