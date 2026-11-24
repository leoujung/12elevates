"""Precision@K evaluation harness (SYNTHETIC labels only).

This checks that the METRIC CODE works. It says nothing about real-world accuracy.
Real Precision@5 requires human-labelled real test cases, which are BLOCKED until legal
review and a labelling protocol exist.
"""
from __future__ import annotations


def precision_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    top = ranked_ids[:k]
    if not top:
        return 0.0
    return sum(1 for pid in top if pid in relevant_ids) / len(top)


def mean_precision_at_k(cases: list[tuple[list[str], set[str]]], k: int = 5) -> float:
    if not cases:
        raise ValueError("no cases: refusing to report a metric from zero data")
    return sum(precision_at_k(r, rel, k) for r, rel in cases) / len(cases)
