-- =====================================================================
-- 12ELEVATE AI — Consent ledger and audit log schema (PROPOSAL, NOT APPLIED)
-- Status: DRAFT for review. Do NOT run against staging or production until approved.
-- Directive refs: 12E-LEGAL-AI-NBI-001 III.c, 12E-LEGAL-AI-NBI-002 IV.4.4 / VII.d-f / VIII.
-- Synthetic data only. Mirrors backend/ai/consent.py and backend/ai/rbac.py.
-- =====================================================================

-- Notice versions. APPROVED requires a written legal record reference.
CREATE TABLE IF NOT EXISTS ai_notice_version (
    version_id        TEXT PRIMARY KEY,
    purpose           TEXT NOT NULL CHECK (purpose IN ('matching_customer','matching_business','marketing')),
    status            TEXT NOT NULL CHECK (status IN ('DRAFT','APPROVED')),
    text_sha256       TEXT NOT NULL CHECK (length(text_sha256) = 64),
    legal_record_ref  TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT approved_needs_legal_ref
        CHECK (status = 'DRAFT' OR (legal_record_ref IS NOT NULL AND length(legal_record_ref) > 0))
);

-- Append-only consent events with hash chain.
CREATE TABLE IF NOT EXISTS ai_consent_event (
    seq               BIGSERIAL PRIMARY KEY,
    member_id         TEXT NOT NULL,
    prospect_id       TEXT NOT NULL,
    purpose           TEXT NOT NULL CHECK (purpose IN ('matching_customer','matching_business','marketing')),
    action            TEXT NOT NULL CHECK (action IN ('GRANTED','WITHDRAWN','DENIED')),
    notice_version    TEXT REFERENCES ai_notice_version(version_id),
    at                TIMESTAMPTZ NOT NULL,
    prev_hash         TEXT NOT NULL,
    hash              TEXT NOT NULL UNIQUE CHECK (length(hash) = 64),
    CONSTRAINT granted_needs_notice
        CHECK (action <> 'GRANTED' OR notice_version IS NOT NULL),
    CONSTRAINT business_disabled
        CHECK (purpose <> 'matching_business')   -- directive 002 preconditions not met; lift only by new migration
);
CREATE INDEX IF NOT EXISTS ai_consent_lookup ON ai_consent_event (member_id, prospect_id, purpose, seq DESC);

-- Append-only audit log for every authorization decision and matching run.
CREATE TABLE IF NOT EXISTS ai_audit_event (
    seq               BIGSERIAL PRIMARY KEY,
    actor_id          TEXT NOT NULL,
    role              TEXT NOT NULL,
    action            TEXT NOT NULL,
    tenant_id         TEXT,
    target_tenant     TEXT,
    allowed           BOOLEAN NOT NULL,
    reason            TEXT NOT NULL,      -- ids and counts only; never profile values or scores
    at                TIMESTAMPTZ NOT NULL,
    prev_hash         TEXT NOT NULL,
    hash              TEXT NOT NULL UNIQUE CHECK (length(hash) = 64)
);

-- Database-level gate: a GRANTED event must reference an APPROVED notice for the same purpose.
-- Without this, the rule "DRAFT can never back a consent" exists only in application code.
CREATE OR REPLACE FUNCTION ai_require_approved_notice() RETURNS trigger AS $$
DECLARE
    nv_status  TEXT;
    nv_purpose TEXT;
BEGIN
    IF NEW.action = 'GRANTED' THEN
        SELECT status, purpose INTO nv_status, nv_purpose
        FROM ai_notice_version WHERE version_id = NEW.notice_version;
        IF nv_status IS DISTINCT FROM 'APPROVED' THEN
            RAISE EXCEPTION 'GRANTED refused: notice % is not APPROVED', NEW.notice_version;
        END IF;
        IF nv_purpose <> NEW.purpose THEN
            RAISE EXCEPTION 'GRANTED refused: notice purpose % does not match %', nv_purpose, NEW.purpose;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ai_consent_require_approved ON ai_consent_event;
CREATE TRIGGER ai_consent_require_approved BEFORE INSERT ON ai_consent_event
    FOR EACH ROW EXECUTE FUNCTION ai_require_approved_notice();

-- Enforce append-only: no UPDATE, no DELETE, no TRUNCATE for any role.
CREATE OR REPLACE FUNCTION ai_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only table: % is not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ai_consent_no_update ON ai_consent_event;
CREATE TRIGGER ai_consent_no_update BEFORE UPDATE OR DELETE ON ai_consent_event
    FOR EACH ROW EXECUTE FUNCTION ai_block_mutation();
DROP TRIGGER IF EXISTS ai_consent_no_truncate ON ai_consent_event;
CREATE TRIGGER ai_consent_no_truncate BEFORE TRUNCATE ON ai_consent_event
    FOR EACH STATEMENT EXECUTE FUNCTION ai_block_mutation();

DROP TRIGGER IF EXISTS ai_audit_no_update ON ai_audit_event;
CREATE TRIGGER ai_audit_no_update BEFORE UPDATE OR DELETE ON ai_audit_event
    FOR EACH ROW EXECUTE FUNCTION ai_block_mutation();
DROP TRIGGER IF EXISTS ai_audit_no_truncate ON ai_audit_event;
CREATE TRIGGER ai_audit_no_truncate BEFORE TRUNCATE ON ai_audit_event
    FOR EACH STATEMENT EXECUTE FUNCTION ai_block_mutation();

-- Least privilege: the application role may only INSERT and SELECT.
-- The role name is a placeholder; set it when the role is defined. Not created here.
-- REVOKE ALL ON ai_consent_event, ai_audit_event FROM PUBLIC;
-- GRANT SELECT, INSERT ON ai_consent_event, ai_audit_event TO <app_role>;
-- GRANT SELECT, INSERT ON ai_notice_version TO <app_role>;

-- Open questions before this can be applied (see DIRECTIVE_002_DEPENDENCIES.md):
--   * Retention period for consent and audit rows: NOT DECIDED (BLOCKED, legal).
--   * Deletion on request vs append-only: conflicts with erasure rights; needs legal decision.
--   * Hash chain is computed by the application; the DB does not verify it.
