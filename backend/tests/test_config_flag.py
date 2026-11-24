import os, sys, pathlib, subprocess, re
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def flag_with_env(extra):
    """Import the flag in a fresh interpreter with extra env vars applied."""
    env = dict(os.environ)
    for k in ("AI_BUSINESS_MATCHING_ENABLED", "BUSINESS_MATCHING_ENABLED"):
        env.pop(k, None)
    env.update(extra)
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "from ai.config import BUSINESS_MATCHING_ENABLED as F; print(F)") % str(ROOT)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else "ERROR"

# Opsi 1: no environment variable may enable Business Matching, in any form.
for val in ("true", "True", "1", "yes", "on", "", "x"):
    check(f"env AI_BUSINESS_MATCHING_ENABLED={val!r} does not enable",
          flag_with_env({"AI_BUSINESS_MATCHING_ENABLED": val}) == "False")
check("env BUSINESS_MATCHING_ENABLED=true does not enable",
      flag_with_env({"BUSINESS_MATCHING_ENABLED": "true"}) == "False")
check("flag is False with no environment at all", flag_with_env({}) == "False")

# Single source: no module other than config.py assigns the flag.
assign = re.compile(r"^\s*BUSINESS_MATCHING_ENABLED\s*[:=]", re.M)
offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "ai").rglob("*.py")
             if p.name != "config.py" and assign.search(p.read_text(encoding="utf-8"))]
check("no module other than config.py assigns the flag", offenders == [])

# Source of truth is read by consent and rbac.
import ai.config as cfg, ai.consent as cs, ai.rbac as rb
check("consent reads the config flag", cs.BUSINESS_MATCHING_ENABLED is cfg.BUSINESS_MATCHING_ENABLED)
check("rbac reads the config flag", rb.BUSINESS_MATCHING_ENABLED is cfg.BUSINESS_MATCHING_ENABLED)
check("flag is False in this repo", cfg.BUSINESS_MATCHING_ENABLED is False)

# Business path still refused.
from ai.matching_service import business_matches, MatchingRefused
from ai.rbac import Actor, AuditLog
try:
    business_matches(Actor("u", "platform_admin", None), "mem-A", [], audit=AuditLog(), at="2026-11-27T09:00:00+07:00")
    blocked = False
except MatchingRefused:
    blocked = True
check("business refused with no candidates", blocked)

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
