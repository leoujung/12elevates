import re
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.customer_matching import Candidate
from ai.business_matching import BusinessCandidate
from ai.rbac import Actor, AuditLog
from ai.matching_service import synthetic_eval_rank, MatchingRefused
from ai.synthetic_guard import register_synthetic_prospects, reset_registry

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def refused(fn):
    try:
        fn(); return False
    except MatchingRefused:
        return True

DEV = Actor("dev-1", "developer", None)
MEM = "mem-qc001"
AT = "2026-11-27T09:00:00+07:00"

def good(pid="syn-c001-00", member=MEM, dims=None, synthetic=True):
    return Candidate(pid, member, synthetic, False, dims if dims is not None else {"declared_wellness_interest": 0.7}, [], 2)

def run(cands, actor=DEV, member=MEM, engine="customer", audit=None):
    reset_registry()
    register_synthetic_prospects(["syn-c001-00", "syn-c001-01"])
    return synthetic_eval_rank(actor, member, engine, cands, audit or AuditLog(), AT)

# --- positive control: well-formed synthetic input ranks ---
check("valid synthetic input ranks", len(run([good()])) == 1)

# --- negative: non-synthetic data ---
check("synthetic=False refused", refused(lambda: run([good(synthetic=False)])))
check("real-looking id (not synthetic pattern) refused",
      refused(lambda: run([Candidate("john-smith-42", MEM, True, False, {"declared_wellness_interest": 0.7}, [], 2)])))
check("synthetic-looking id NOT registered by generator refused",
      refused(lambda: (reset_registry(), synthetic_eval_rank(DEV, MEM, "customer",
              [Candidate("syn-c001-09", MEM, True, False, {"declared_wellness_interest": 0.7}, [], 2)],
              AuditLog(), AT))))
try:
    register_synthetic_prospects(["real-person-1"]); reg_refused = False
except Exception:
    reg_refused = True
check("generator cannot register a non-synthetic id", reg_refused)
check("member id not synthetic pattern refused", refused(lambda: run([good()], member="mem-real-ana")))
check("cross-member candidate refused", refused(lambda: run([good(member="mem-qc002")])))
check("job_title experience refused",
      refused(lambda: (reset_registry(), register_synthetic_prospects(["syn-c001-00"]),
              synthetic_eval_rank(DEV, MEM, "customer",
                  [type("C", (), {"prospect_id": "syn-c001-00", "member_id": MEM, "synthetic": True,
                                   "dims": {"declared_wellness_interest": 0.7}, "experience_source": "job_title"})()],
                  AuditLog(), AT))))
check("unknown dimension refused", refused(lambda: run([good(dims={"mystery": 0.5})])))
check("health dimension refused by field policy", refused(lambda: run([good(dims={"medical_history": 0.5})])))
check("out-of-range value refused", refused(lambda: run([good(dims={"declared_wellness_interest": 1.7})])))
check("negative value refused", refused(lambda: run([good(dims={"declared_wellness_interest": -0.1})])))

# --- RBAC and entry point ---
check("member role cannot run synthetic eval",
      refused(lambda: run([good()], actor=Actor("m1", "member", MEM))))
check("platform_admin cannot run synthetic eval on member data",
      refused(lambda: run([good()], actor=Actor("a1", "platform_admin", None))))
check("business engine refused at the entry point", refused(lambda: run([good()], engine="business")))
check("unknown engine refused", refused(lambda: run([good()], engine="other")))

# --- audit: every refusal and every run is recorded, ids and counts only ---
A = AuditLog()
refused(lambda: run([good(synthetic=False)], audit=A))
run([good()], audit=A)
check("refused run is audited", any(e["allowed"] is False for e in A.events))
check("allowed run is audited", any(e["allowed"] is True for e in A.events))
check("audit chain verifies", A.verify())
check("audit does not contain profile values",
      all("0.7" not in e["reason"] for e in A.events))

# --- source-level: evaluation script ranks only via the guarded entry point ---
src = (ROOT / "ai" / "eval" / "build_engine_eval.py").read_text(encoding="utf-8")
check("eval script does not call rank() directly",
      not re.search(r"(?<![A-Za-z_])rank(_customer|_business)?\(", src))
check("eval script uses synthetic_eval_rank", "synthetic_eval_rank(" in src)

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
