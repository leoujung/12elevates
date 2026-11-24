"""Consent management infrastructure for 12ELEVATE AI matching (Task 4 extension, SYNTHETIC data only).

Implements the directive (Legal & Compliance, 12E-LEGAL-AI-NBI-001):
  - configurable notice versions with status DRAFT or APPROVED (DRAFT can never back a consent)
  - append-only consent ledger with hash chain (tamper evidence = audit trail)
  - withdrawal takes effect immediately for matching
  - purposes kept separate: matching_customer, matching_business, marketing
  - matching_business is DISABLED by constant (BUSINESS_MATCHING_ENABLED = False)
  - tenant (member_id) isolation on every lookup

No real personal data is accepted by this module's tests. Nothing here marks a notice as legally approved.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

PURPOSES = ("matching_customer", "matching_business", "marketing")
from ai.config import BUSINESS_MATCHING_ENABLED  # single source of truth
ACTIONS = ("GRANTED", "WITHDRAWN", "DENIED")


class ConsentError(Exception):
    pass


@dataclass(frozen=True)
class NoticeVersion:
    version_id: str
    purpose: str
    status: str                       # "DRAFT" or "APPROVED"
    text_sha256: str
    legal_record_ref: Optional[str]   # reference to written legal approval; required for APPROVED

    def __post_init__(self):
        if self.purpose not in PURPOSES:
            raise ConsentError(f"unknown purpose {self.purpose}")
        if self.status not in ("DRAFT", "APPROVED"):
            raise ConsentError(f"unknown notice status {self.status}")
        if self.status == "APPROVED" and not self.legal_record_ref:
            raise ConsentError("APPROVED notice requires a written legal_record_ref")


@dataclass
class NoticeRegistry:
    versions: dict[str, NoticeVersion] = field(default_factory=dict)

    def register(self, nv: NoticeVersion) -> None:
        if nv.version_id in self.versions:
            raise ConsentError(f"notice version already exists: {nv.version_id}")
        self.versions[nv.version_id] = nv

    def approved(self, version_id: str, purpose: str) -> bool:
        nv = self.versions.get(version_id)
        return nv is not None and nv.status == "APPROVED" and nv.purpose == purpose


@dataclass
class Ledger:
    registry: NoticeRegistry
    events: list[dict] = field(default_factory=list)

    def _prev_hash(self) -> str:
        return self.events[-1]["hash"] if self.events else "GENESIS"

    def append(self, *, member_id: str, prospect_id: str, purpose: str, action: str,
               notice_version: Optional[str], at: str) -> dict:
        if action not in ACTIONS:
            raise ConsentError(f"unknown action {action}")
        if purpose not in PURPOSES:
            raise ConsentError(f"unknown purpose {purpose}")
        if purpose == "matching_business" and not BUSINESS_MATCHING_ENABLED:
            raise ConsentError("matching_business is disabled by directive")
        if action == "GRANTED":
            if not notice_version:
                raise ConsentError("GRANTED requires a notice_version")
            if not self.registry.approved(notice_version, purpose):
                raise ConsentError("GRANTED refused: notice is not APPROVED for this purpose")
        body = {"member_id": member_id, "prospect_id": prospect_id, "purpose": purpose,
                "action": action, "notice_version": notice_version, "at": at,
                "prev_hash": self._prev_hash()}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        ev = {**body, "hash": digest}
        self.events.append(ev)
        return ev

    def state(self, member_id: str, prospect_id: str, purpose: str) -> Optional[dict]:
        """Latest event for this tenant, prospect and purpose. Tenant-scoped."""
        latest = None
        for e in self.events:
            if e["member_id"] == member_id and e["prospect_id"] == prospect_id and e["purpose"] == purpose:
                latest = e
        return latest

    def verify_chain(self) -> bool:
        prev = "GENESIS"
        for e in self.events:
            body = {k: v for k, v in e.items() if k != "hash"}
            if body["prev_hash"] != prev:
                return False
            if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != e["hash"]:
                return False
            prev = e["hash"]
        return True


def may_match(ledger: Ledger, member_id: str, prospect_id: str, purpose: str) -> bool:
    """Gate before any matching. Fails closed."""
    if purpose == "matching_business" and not BUSINESS_MATCHING_ENABLED:
        return False
    st = ledger.state(member_id, prospect_id, purpose)
    if st is None or st["action"] != "GRANTED":
        return False
    return ledger.registry.approved(st["notice_version"], purpose)
