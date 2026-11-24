"""Single enforcement path for AI matching (synthetic data only, service layer, not an HTTP endpoint).

Order of checks, fail closed:
  1. authorize(actor, "view_own_matches", member_id)  -> RBAC + tenant + audit
  2. for each candidate: may_match(ledger, member_id, prospect_id, "matching_customer")
     -> consent must be GRANTED, latest state, with an APPROVED notice
  3. rank() only over candidates that passed 1 and 2 (customer engine)

Business matching is refused here: BUSINESS_MATCHING_ENABLED is False, and the directive
requires legal basis, DPIA and verified provenance first (see DIRECTIVE_002_DEPENDENCIES.md).

Audit entries contain ids and counts only, never profile values or scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai.business_matching import BusinessCandidate  # noqa: F401  (imported so the refusal path is explicit)
from ai.consent import BUSINESS_MATCHING_ENABLED, Ledger, may_match
from ai.customer_matching import Candidate, MatchResult, rank as rank_customer
from ai.field_policy import FieldRefused, check_fields_for_matching
from ai.rbac import Actor, AuditLog, authorize


class MatchingRefused(Exception):
    pass


@dataclass
class CustomerMatchResponse:
    member_id: str
    results: list[MatchResult]
    excluded_no_consent: int      # count only, not ids
    excluded_by_gate: int         # reserved for future gate reasons


def customer_matches(actor: Actor, member_id: str, candidates: list[Candidate],
                     ledger: Ledger, audit: AuditLog, at: str) -> CustomerMatchResponse:
    # 1. authorization (audited, allowed or denied)
    if not authorize(actor, "view_own_matches", member_id, audit, at):
        raise MatchingRefused("access denied")

    # 1b. field policy: every dimension the engine would read must be allowed for customer matching.
    # Fail closed on the whole request. Field names only are audited, never values.
    used_fields = sorted({k for c in candidates for k in c.dims})
    try:
        check_fields_for_matching(used_fields, "customer")
    except FieldRefused as e:
        audit.write(actor_id=actor.actor_id, role=actor.role, action="customer_matching_run",
                    tenant_id=actor.tenant_id, target_tenant=member_id, allowed=False,
                    reason=f"field policy: {e}", at=at)
        raise MatchingRefused("field not permitted for customer matching")

    # 2. consent per prospect (tenant-scoped by member_id inside may_match)
    consented: list[Candidate] = []
    no_consent = 0
    for c in candidates:
        if may_match(ledger, member_id, c.prospect_id, "matching_customer"):
            consented.append(c)
        else:
            no_consent += 1

    # 3. rank only what passed every check
    results = rank_customer(consented, member_id) if consented else []

    audit.write(actor_id=actor.actor_id, role=actor.role, action="customer_matching_run",
                tenant_id=actor.tenant_id, target_tenant=member_id, allowed=True,
                reason=f"ranked={len(results)} excluded_no_consent={no_consent}", at=at)
    return CustomerMatchResponse(member_id=member_id, results=results,
                                 excluded_no_consent=no_consent, excluded_by_gate=0)


def business_matches(actor: Actor, member_id: str, candidates: list | None = None, *,
                     audit: AuditLog, at: str):
    """Business matching: field policy is checked first, then the directive gate refuses.

    The field check runs even while the flag is off, so a future activation cannot skip it.
    """
    used_fields = sorted({k for c in (candidates or []) for k in getattr(c, "dims", {})})
    try:
        check_fields_for_matching(used_fields, "business")
    except FieldRefused as e:
        audit.write(actor_id=actor.actor_id, role=actor.role, action="business_matching_run",
                    tenant_id=actor.tenant_id, target_tenant=member_id, allowed=False,
                    reason=f"field policy: {e}", at=at)
        raise MatchingRefused("field not permitted for business matching")
    audit.write(actor_id=actor.actor_id, role=actor.role, action="business_matching_run",
                tenant_id=actor.tenant_id, target_tenant=member_id, allowed=False,
                reason="business matching disabled (directive 002 preconditions unmet)", at=at)
    if not BUSINESS_MATCHING_ENABLED:
        raise MatchingRefused("business matching disabled")
    raise MatchingRefused("business matching path not implemented")
