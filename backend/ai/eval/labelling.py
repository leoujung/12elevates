"""Blind-labelling pipeline for 12ELEVATE matching evaluation (SYNTHETIC cases only).

Evaluators label independently in their own files. This module:
  - validates structure, completeness and cross-file consistency,
  - merges the two evaluations WITHOUT modifying either evaluator file,
  - computes Cohen's kappa and lists cases that need a third evaluator.
Nothing here assigns a label. Only human-entered values are used.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

LABELS = ("RELEVANT", "NOT_RELEVANT", "UNKNOWN")
ENGINES = ("customer", "business")
MIN_PER_ENGINE = 100
CASE_FIELDS = ("case_id", "engine", "profile", "reviewer_id", "human_label", "comment", "reviewed_at")
FORBIDDEN_KEYS = {
    "match_score", "intent_confidence", "data_confidence", "ranking", "rank",
    "reasons", "reasoning", "ai_reasoning", "recommendation", "recommended_action",
    "next_best_action", "ai_output", "model_output",
}
REPO = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO / "docs" / "ai" / "eval"
E1_FILE = EVAL_DIR / "evaluator_1_labels.json"
E2_FILE = EVAL_DIR / "evaluator_2_labels.json"
MERGED_FILE = EVAL_DIR / "merged_labels.json"
KAPPA_NOTE = "Acceptance threshold for kappa is NOT yet decided. Proposed reference only: >= 0.6. Decide before reporting."


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _index(doc: dict) -> dict:
    return {c["case_id"]: c for c in doc["cases"]}


def _forbidden_hits(obj, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in FORBIDDEN_KEYS:
                hits.append(f"{path}/{k}")
            hits += _forbidden_hits(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _forbidden_hits(v, f"{path}[{i}]")
    return hits


def _is_iso(s) -> bool:
    if not isinstance(s, str):
        return False
    try:
        dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def check_structure(doc: dict, label: str) -> list[str]:
    errs = [f"[{label}] forbidden AI field present: {h}" for h in _forbidden_hits(doc)]
    cases = doc.get("cases")
    if not isinstance(cases, list):
        return errs + [f"[{label}] 'cases' missing"]
    ids = [c.get("case_id") for c in cases]
    if len(ids) != len(set(ids)):
        errs.append(f"[{label}] duplicate case_id")
    for eng in ENGINES:
        n = sum(1 for c in cases if c.get("engine") == eng)
        if n < MIN_PER_ENGINE:
            errs.append(f"[{label}] {eng}: {n} cases, minimum is {MIN_PER_ENGINE}")
    for c in cases:
        cid = c.get("case_id", "?")
        for k in CASE_FIELDS:
            if k not in c:
                errs.append(f"[{label}] {cid}: missing field {k}")
        if c.get("engine") not in ENGINES:
            errs.append(f"[{label}] {cid}: engine must be one of {ENGINES}")
        if not isinstance(c.get("profile"), dict):
            errs.append(f"[{label}] {cid}: profile must be an object")
    return errs


def check_complete(doc: dict, label: str) -> list[str]:
    """Every case must be labelled by this evaluator, with reviewer and timestamp."""
    errs = []
    for c in doc["cases"]:
        cid = c["case_id"]
        if c.get("human_label") not in LABELS:
            errs.append(f"[{label}] {cid}: human_label not set")
        if not (isinstance(c.get("reviewer_id"), str) and c["reviewer_id"].strip()):
            errs.append(f"[{label}] {cid}: reviewer_id empty")
        if not _is_iso(c.get("reviewed_at")):
            errs.append(f"[{label}] {cid}: reviewed_at missing or not ISO-8601")
    return errs


def check_pair(d1: dict, d2: dict) -> list[str]:
    """Both files must contain the same cases with the same engine and profile."""
    errs = []
    i1, i2 = _index(d1), _index(d2)
    if set(i1) != set(i2):
        errs.append("case_id sets differ between evaluator 1 and evaluator 2")
    for cid in sorted(set(i1) & set(i2)):
        if i1[cid]["engine"] != i2[cid]["engine"]:
            errs.append(f"{cid}: engine differs between evaluators")
        if i1[cid]["profile"] != i2[cid]["profile"]:
            errs.append(f"{cid}: profile differs between evaluators")
    return errs


def cohen_kappa(a: list[str], b: list[str]):
    """Cohen's kappa for two raters over LABELS. Returns None when undefined."""
    if len(a) != len(b):
        raise ValueError("label lists differ in length")
    n = len(a)
    if n == 0:
        return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in LABELS)
    if pe == 1.0:
        return None  # only one category used by both raters: kappa is undefined
    return round((po - pe) / (1 - pe), 4)


def classify(l1, l2) -> str:
    if l1 is None or l2 is None:
        return "PENDING"
    if l1 == l2 and l1 != "UNKNOWN":
        return "AGREED"
    return "NEEDS_THIRD"  # disagreement, or either rater chose UNKNOWN


def kappa_report(rows: list[dict]) -> dict:
    out = {}
    for scope in ("customer", "business", "overall"):
        sel = [r for r in rows if scope == "overall" or r["engine"] == scope]
        both = [r for r in sel if r["eval1_label"] and r["eval2_label"]]
        a = [r["eval1_label"] for r in both]
        b = [r["eval2_label"] for r in both]
        agree = sum(1 for x, y in zip(a, b) if x == y)
        out[scope] = {
            "cases_total": len(sel),
            "both_labelled": len(both),
            "raw_agreement": round(agree / len(both), 4) if both else None,
            "cohen_kappa": cohen_kappa(a, b),
            "needs_third": sum(1 for r in sel if r["status"] == "NEEDS_THIRD"),
            "pending": sum(1 for r in sel if r["status"] == "PENDING"),
        }
    return out


def merge_docs(d1: dict, d2: dict, prev: dict | None = None) -> dict:
    """Pure function: never modifies d1, d2 or prev. Keeps eval3 labels from a previous merge."""
    prev_rows = {r["case_id"]: r for r in (prev or {}).get("cases", [])}
    i1, i2 = _index(d1), _index(d2)
    rows = []
    for cid in sorted(i1):
        c1, c2 = i1[cid], i2[cid]
        l1, l2 = c1.get("human_label"), c2.get("human_label")
        status = classify(l1, l2)
        final = l1 if status == "AGREED" else None
        eval3 = prev_rows.get(cid, {}).get("eval3_label")
        if status == "NEEDS_THIRD" and eval3 in ("RELEVANT", "NOT_RELEVANT"):
            final, status = eval3, "RESOLVED_BY_THIRD"
        rows.append({
            "case_id": cid, "engine": c1["engine"],
            "eval1_label": l1, "eval1_reviewer_id": c1.get("reviewer_id"), "eval1_reviewed_at": c1.get("reviewed_at"),
            "eval2_label": l2, "eval2_reviewer_id": c2.get("reviewer_id"), "eval2_reviewed_at": c2.get("reviewed_at"),
            "status": status, "final_label": final, "eval3_label": eval3,
        })
    counts = {s: sum(1 for r in rows if r["status"] == s)
              for s in ("AGREED", "NEEDS_THIRD", "RESOLVED_BY_THIRD", "PENDING")}
    return {
        "counts": counts,
        "kappa": kappa_report(rows),
        "kappa_note": KAPPA_NOTE,
        "needs_third_case_ids": [r["case_id"] for r in rows if r["status"] == "NEEDS_THIRD"],
        "cases": rows,
    }


def _print_errs(errs: list[str], limit: int = 15) -> None:
    if not errs:
        print("RESULT: PASS")
        return
    print(f"RESULT: FAIL ({len(errs)} issues)")
    for e in errs[:limit]:
        print("  -", e)
    if len(errs) > limit:
        print(f"  ... {len(errs) - limit} more")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "validate":
        d1, d2 = load(E1_FILE), load(E2_FILE)
        errs = check_structure(d1, "E1") + check_structure(d2, "E2") + check_pair(d1, d2)
        if "--structure-only" not in argv:
            errs += check_complete(d1, "E1") + check_complete(d2, "E2")
        _print_errs(errs)
        return 0 if not errs else 1
    if cmd == "merge":
        d1, d2 = load(E1_FILE), load(E2_FILE)
        errs = check_structure(d1, "E1") + check_structure(d2, "E2") + check_pair(d1, d2)
        if errs:
            _print_errs(errs)
            print("merge refused: fix structure first")
            return 1
        prev = load(MERGED_FILE) if MERGED_FILE.exists() else None
        out = merge_docs(d1, d2, prev)
        out["generated_from"] = [E1_FILE.name, E2_FILE.name]
        MERGED_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("counts:", out["counts"])
        for scope, v in out["kappa"].items():
            print(f"{scope}: both_labelled={v['both_labelled']} kappa={v['cohen_kappa']} needs_third={v['needs_third']} pending={v['pending']}")
        print("needs third evaluator:", len(out["needs_third_case_ids"]), out["needs_third_case_ids"][:20])
        print("wrote", MERGED_FILE.name)
        return 0
    print("usage: labelling.py validate [--structure-only] | merge")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
