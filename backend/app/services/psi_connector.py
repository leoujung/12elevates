"""PSI-2 shared connector interface.

A connector only maps one source type's raw body to a NormalizedEvent. Verification, source
status, permission checks, idempotency, provenance, and audit are shared and live in psi_ingest.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.services.psi_ingest_rules import (
    ALLOWED_PURPOSES,
    IngestRefused,
    normalize_email,
    normalize_name,
    normalize_whatsapp,
    validate_event_id,
)

_EVIDENCE_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    purpose: str
    consent_granted: bool
    notice_version: str
    evidence_ref: str
    name: str
    whatsapp: str | None
    email: str | None
    fields_present: tuple


class SourceConnector(ABC):
    category: str

    @abstractmethod
    def parse(self, body: dict) -> NormalizedEvent:
        """Map a decoded body to a NormalizedEvent. Raise IngestRefused on any problem."""


class InboundFormConnector(SourceConnector):
    """Synthetic-only connector for the INBOUND_LEADS category (form / webhook payloads)."""

    category = "INBOUND_LEADS"
    _TOP = frozenset({"event_id", "purpose", "consent", "notice_version", "evidence_ref", "lead"})
    _LEAD = frozenset({"name", "whatsapp", "email"})

    def parse(self, body: dict) -> NormalizedEvent:
        for key in body:
            if key not in self._TOP:
                raise IngestRefused(f"unknown_field:{key}")
        event_id = validate_event_id(body.get("event_id"))
        purpose = body.get("purpose")
        if purpose not in ALLOWED_PURPOSES:
            raise IngestRefused("purpose_not_allowlisted")
        consent = body.get("consent") is True
        notice = body.get("notice_version")
        if not isinstance(notice, str) or not 1 <= len(notice) <= 40:
            notice = ""  # service refuses with notice_missing
        evidence_ref = body.get("evidence_ref")
        if not isinstance(evidence_ref, str) or not _EVIDENCE_RE.match(evidence_ref):
            raise IngestRefused("validation:evidence_ref")
        lead = body.get("lead")
        if not isinstance(lead, dict):
            raise IngestRefused("validation:lead")
        for key in lead:
            if key not in self._LEAD:
                raise IngestRefused(f"unknown_field:{key}")
        name = normalize_name(lead.get("name"))
        whatsapp = normalize_whatsapp(lead.get("whatsapp"))
        email = normalize_email(lead.get("email"))
        present = tuple(f for f, v in (("name", name), ("whatsapp", whatsapp), ("email", email)) if v)
        return NormalizedEvent(event_id=event_id, purpose=purpose, consent_granted=consent,
                               notice_version=notice, evidence_ref=evidence_ref, name=name,
                               whatsapp=whatsapp, email=email, fields_present=present)
