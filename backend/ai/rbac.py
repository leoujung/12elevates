"""RBAC and audit trail for 12ELEVATE AI matching (synthetic data only).

Directive (12E-LEGAL-AI-NBI-001) section III requires:
  a. role-based access and authorization
  b. purpose limitation and data minimisation
  c. audit trail for access and processing
  d. separation of Customer Matching, Business Matching, Marketing
  e. no access to another member's prospect or personal-data records

Rules, fail closed:
  - Every action needs an explicit role permission AND a matching tenant (member_id).
  - Platform admins do NOT get implicit read access to member prospect data.
  - Business Matching is disabled for every role (directive).
  - Every decision (allowed or denied) is written to a hash-chained audit log.
  - Audit entries store ids and outcomes only, never profile values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

from ai.config import BUSINESS_MATCHING_ENABLED  # single source of truth

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "member": frozenset({"view_own_matches", "record_own_consent"}),
    "evaluator": frozenset({"label_items"}),        # labelling only, never sees scores
    "developer": frozenset({"run_on_synthetic"}),   # synthetic data only
    "platform_admin": frozenset({"manage_roles", "view_audit"}),  # NO member data access
}
ACTIONS_NEEDING_TENANT = {"view_own_matches", "record_own_consent"}


class AccessError(Exception):
    pass


@dataclass
class Actor:
    actor_id: str
    role: str
    tenant_id: Optional[str]  # member_id; None for roles with no tenant data


@dataclass
class AuditLog:
    events: list[dict] = field(default_factory=list)

    def _prev(self) -> str:
        return self.events[-1]["hash"] if self.events else "GENESIS"

    def write(self, *, actor_id: str, role: str, action: str, tenant_id: Optional[str],
              target_tenant: Optional[str], allowed: bool, reason: str, at: str) -> dict:
        body = {"actor_id": actor_id, "role": role, "action": action, "tenant_id": tenant_id,
                "target_tenant": target_tenant, "allowed": allowed, "reason": reason,
                "at": at, "prev_hash": self._prev()}
        h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        ev = {**body, "hash": h}
        self.events.append(ev)
        return ev

    def verify(self) -> bool:
        prev = "GENESIS"
        for e in self.events:
            body = {k: v for k, v in e.items() if k != "hash"}
            if body["prev_hash"] != prev:
                return False
            if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != e["hash"]:
                return False
            prev = e["hash"]
        return True


def authorize(actor: Actor, action: str, target_tenant: Optional[str], audit: AuditLog, at: str) -> bool:
    """Returns True only if allowed. Every call is audited, allowed or not."""
    def deny(reason: str) -> bool:
        audit.write(actor_id=actor.actor_id, role=actor.role, action=action, tenant_id=actor.tenant_id,
                    target_tenant=target_tenant, allowed=False, reason=reason, at=at)
        return False

    if action == "run_matching_business" or (action == "view_business_matches"):
        return deny("business matching disabled by directive")
    perms = ROLE_PERMISSIONS.get(actor.role)
    if perms is None:
        return deny("unknown role")
    if action not in perms:
        return deny("permission not granted to role")
    if action in ACTIONS_NEEDING_TENANT:
        if not actor.tenant_id:
            return deny("tenant required")
        if target_tenant != actor.tenant_id:
            return deny("cross-tenant access refused")
    audit.write(actor_id=actor.actor_id, role=actor.role, action=action, tenant_id=actor.tenant_id,
                target_tenant=target_tenant, allowed=True, reason="ok", at=at)
    return True
