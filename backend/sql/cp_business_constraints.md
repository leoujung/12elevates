# cp_* constraint extension for BUSINESS_INTEREST (staging only)

Status: APPLIED to elevate_staging on 2026-11-26. NOT an Alembic revision.
Production (elevate_platform) has NO cp_* tables. Nothing here touches production.

## Why this is not an Alembic revision
The cp_* tables and their CHECK constraints were created outside Alembic.
The constraint names (cp_*_check) are not defined anywhere in the repo.
Writing an Alembic revision against constraints Alembic never created would
make the migration history misleading and not reproducible elsewhere.

## What it changes
- cp_prospects_prospect_type_check: adds 'business'
- cp_inbound_events_event_type_check: adds 'BUSINESS_INTEREST'
- cp_consent_ledger_purpose_check: adds 'business_interest_processing'

All previous values remain allowed. Existing rows were verified to satisfy the new constraints.

## Verification
- Backup before apply: elevate_staging_pre_business_v2_20261126T053802Z.dump (valid, pg_restore --list OK)
- Endpoint tested against a copy of elevate_staging (nbi_pg_copy, dropped after test):
  one valid submit writes 1 row to each of 7 tables; duplicate event_id writes 0; missing consent writes 0.
- elevate_staging counts unchanged after tests: prospects 20, consents 99, sync_queue 49, audit 49.

## Rollback
Re-create the three constraints with the original value lists. Use the backup above if needed.

## Open item
Decide how cp_* schema is managed going forward (Alembic baseline for cp_*, or a separate schema-as-code file).
This must be decided before the cp_* schema is applied to any other environment.
