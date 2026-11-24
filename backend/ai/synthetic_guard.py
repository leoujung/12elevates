"""Technical synthetic-only enforcement for evaluation paths.

Documentation alone is not enforcement. A candidate reaches the ranker only if ALL hold:
  1. candidate.synthetic is exactly True;
  2. prospect_id matches the synthetic pattern AND was registered by the synthetic generator
     in this process (register_synthetic_prospects). Unregistered ids are refused even when
     they look synthetic;
  3. member_id matches the synthetic member pattern and equals the query member;
  4. experience_source is not "job_title" (forbidden by directive);
  5. every dimension key is in the engine's allowed weight set, and every value is None or in [0, 1].

Any failure raises NonSyntheticRefused. Fail closed.

Limit (stated honestly): the registry lives in process memory. It stops accidental mixing of real
data into the evaluation path. It does not stop a developer who deliberately edits the generator.
That residual risk is governed by code review and by the RBAC developer role, not by this module.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

SYNTH_PROSPECT = re.compile(r"^syn-[cb]\d{3}-\d{2}$")
SYNTH_MEMBER = re.compile(r"^mem-q[cb]\d{3}$")
FORBIDDEN_EXPERIENCE = "job_title"

_REGISTERED: set[str] = set()


class NonSyntheticRefused(Exception):
    pass


def register_synthetic_prospects(prospect_ids: Iterable[str]) -> None:
    """Called only by the synthetic generator. Ids must match the synthetic pattern."""
    for pid in prospect_ids:
        if not SYNTH_PROSPECT.match(pid):
            raise NonSyntheticRefused(f"refusing to register non-synthetic id: {pid}")
        _REGISTERED.add(pid)


def reset_registry() -> None:
    """Test-only."""
    _REGISTERED.clear()


def assert_synthetic(candidates: list, member_id: str, allowed_dims: Mapping[str, float]) -> None:
    if not SYNTH_MEMBER.match(member_id or ""):
        raise NonSyntheticRefused(f"member is not a synthetic member id: {member_id!r}")
    for c in candidates:
        if getattr(c, "synthetic", None) is not True:
            raise NonSyntheticRefused(f"candidate not marked synthetic: {c.prospect_id}")
        if not SYNTH_PROSPECT.match(c.prospect_id) or c.prospect_id not in _REGISTERED:
            raise NonSyntheticRefused(f"candidate lacks verifiable synthetic provenance: {c.prospect_id}")
        if c.member_id != member_id:
            raise NonSyntheticRefused(f"candidate belongs to another member: {c.prospect_id}")
        if getattr(c, "experience_source", "declared") == FORBIDDEN_EXPERIENCE:
            raise NonSyntheticRefused(f"job_title experience is forbidden: {c.prospect_id}")
        for k, v in c.dims.items():
            if k not in allowed_dims:
                raise NonSyntheticRefused(f"dimension not allowed for this engine: {k}")
            if v is not None and not (0.0 <= v <= 1.0):
                raise NonSyntheticRefused(f"dimension value out of range: {k}")
