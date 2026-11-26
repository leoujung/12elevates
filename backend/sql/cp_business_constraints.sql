-- Migration: allow BUSINESS_INTEREST event, business_interest_processing purpose, and 'business' prospect type.
-- elevate_staging only. Each constraint is dropped and re-added with the existing values PLUS the new ones.
\set ON_ERROR_STOP on
BEGIN;

ALTER TABLE cp_prospects DROP CONSTRAINT IF EXISTS cp_prospects_prospect_type_check;
ALTER TABLE cp_prospects ADD CONSTRAINT cp_prospects_prospect_type_check
  CHECK (prospect_type IN ('customer', 'partner', 'lead', 'business'));

ALTER TABLE cp_inbound_events DROP CONSTRAINT IF EXISTS cp_inbound_events_event_type_check;
ALTER TABLE cp_inbound_events ADD CONSTRAINT cp_inbound_events_event_type_check
  CHECK (event_type IN ('LEAD_SUBMITTED', 'ASSESSMENT_COMPLETED', 'WEBINAR_REGISTERED', 'PARTNER_INQUIRY', 'BUSINESS_INTEREST'));

ALTER TABLE cp_consent_ledger DROP CONSTRAINT IF EXISTS cp_consent_ledger_purpose_check;
ALTER TABLE cp_consent_ledger ADD CONSTRAINT cp_consent_ledger_purpose_check
  CHECK (purpose IN ('registration_processing', 'assessment_processing', 'partner_contact', 'marketing_optional', 'business_interest_processing'));

COMMIT;
