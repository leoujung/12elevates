"""Fail-closed validator for pytest JUnit XML reports (PSI CI).

Exit codes:
  0  report is valid, all required counts satisfied
  1  any failure, error, or skipped test
  2  report missing, unparsable, or totals inconsistent (never silently passes)

Usage: python ci_junit_gate.py <junit.xml> [--min-passed N] [--max-skipped 0]
Reads only the XML counts and test names. Never prints test bodies or environment.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def load(path: str) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:  # fail closed
        print(f"GATE: cannot read report: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
    return root


def totals(root: ET.Element) -> dict[str, int]:
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if not suites:
        print("GATE: no testsuite element", file=sys.stderr)
        sys.exit(2)
    t = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for k in t:
            t[k] += int(s.get(k, "0"))
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--min-passed", type=int, default=1)
    ap.add_argument("--max-skipped", type=int, default=0)
    a = ap.parse_args()

    root = load(a.report)
    t = totals(root)
    passed = t["tests"] - t["failures"] - t["errors"] - t["skipped"]

    # Cross-check: count the testcase elements directly so a rewritten total cannot hide a skip.
    cases = list(root.iter("testcase"))
    skipped_cases = sum(1 for c in cases if c.find("skipped") is not None)
    failed_cases = sum(1 for c in cases if c.find("failure") is not None or c.find("error") is not None)
    if len(cases) != t["tests"]:
        print(f"GATE: total mismatch testcases={len(cases)} vs tests={t['tests']}", file=sys.stderr)
        return 2
    if skipped_cases != t["skipped"] or failed_cases != t["failures"] + t["errors"]:
        print("GATE: per-case counts disagree with suite totals", file=sys.stderr)
        return 2

    print(f"GATE: tests={t['tests']} passed={passed} failures={t['failures']} "
          f"errors={t['errors']} skipped={t['skipped']}")
    if t["failures"] or t["errors"]:
        return 1
    if t["skipped"] > a.max_skipped:
        return 1
    if passed < a.min_passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
