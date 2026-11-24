import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.evaluation import precision_at_k, mean_precision_at_k

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

check("all top-5 relevant -> 1.0", precision_at_k(["a", "b", "c", "d", "e"], {"a", "b", "c", "d", "e"}, 5) == 1.0)
check("none relevant -> 0.0", precision_at_k(["a", "b", "c", "d", "e"], {"x"}, 5) == 0.0)
check("2 of top-5 relevant -> 0.4", precision_at_k(["a", "x", "b", "y", "z"], {"a", "b"}, 5) == 0.4)
check("only top-K counts (relevant at rank 6 ignored)", precision_at_k(["a", "b", "c", "d", "e", "f"], {"f"}, 5) == 0.0)
check("fewer than K results uses actual count", precision_at_k(["a", "b"], {"a", "b"}, 5) == 1.0)
check("empty ranking -> 0.0", precision_at_k([], {"a"}, 5) == 0.0)
check("mean over cases", mean_precision_at_k([(["a"], {"a"}), (["a"], set())], 5) == 0.5)

try:
    mean_precision_at_k([], 5)
    check("zero cases refused (no fake metric)", False)
except ValueError:
    check("zero cases refused (no fake metric)", True)

passed = sum(1 for _, ok in results if ok)
print(f"RESULT {passed} passed, {len(results) - passed} failed")
sys.exit(0 if passed == len(results) else 1)
