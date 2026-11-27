"""cp_* central prospect tables (business intake, consent ledger, inbound events).

Revision ID: j3k4cpschema01
Revises: i2j3nbischema01
Create Date: 2026-11-27

Source of truth: schema captured from staging elevate_staging (structure only),
which was created outside Alembic. This revision makes it reproducible.
Does NOT include PSI tables. Ledger is append-only (trigger blocks UPDATE/DELETE).
"""
from alembic import op

revision = "j3k4cpschema01"
down_revision = "i2j3nbischema01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE OR REPLACE FUNCTION public.cp_block_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  RAISE EXCEPTION 'cp_consent_ledger is append-only (% blocked)', TG_OP;
END;
$$;
""")

    op.execute("""
CREATE TABLE public.cp_prospects (
    prospect_id uuid NOT NULL,
    member_id character varying(64) NOT NULL,
    prospect_type character varying(16) NOT NULL,
    display_name character varying(200),
    status character varying(32) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cp_prospects_prospect_type_check CHECK (((prospect_type)::text = ANY ((ARRAY['customer'::character varying, 'partner'::character varying, 'lead'::character varying, 'business'::character varying])::text[])))
);
ALTER TABLE ONLY public.cp_prospects ADD CONSTRAINT cp_prospects_pkey PRIMARY KEY (prospect_id);
CREATE INDEX cp_prospects_member_idx ON public.cp_prospects USING btree (member_id);
""")

    op.execute("""
CREATE TABLE public.cp_inbound_events (
    event_id character varying(100) NOT NULL,
    event_type character varying(40) NOT NULL,
    member_id character varying(64) NOT NULL,
    prospect_id uuid,
    status character varying(32) NOT NULL,
    payload_minimal jsonb DEFAULT '{}'::jsonb NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cp_inbound_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['LEAD_SUBMITTED'::character varying, 'ASSESSMENT_COMPLETED'::character varying, 'WEBINAR_REGISTERED'::character varying, 'PARTNER_INQUIRY'::character varying, 'BUSINESS_INTEREST'::character varying])::text[]))),
    CONSTRAINT cp_inbound_events_status_check CHECK (((status)::text = ANY ((ARRAY['received'::character varying, 'persisted'::character varying, 'rejected_consent'::character varying, 'rejected_validation'::character varying, 'suppressed'::character varying, 'duplicate_ignored'::character varying, 'failed'::character varying])::text[])))
);
ALTER TABLE ONLY public.cp_inbound_events ADD CONSTRAINT cp_inbound_events_pkey PRIMARY KEY (member_id, event_id);
ALTER TABLE ONLY public.cp_inbound_events ADD CONSTRAINT cp_inbound_events_prospect_id_fkey FOREIGN KEY (prospect_id) REFERENCES public.cp_prospects(prospect_id) ON DELETE RESTRICT;
""")

    op.execute("""
CREATE TABLE public.cp_prospect_identifiers (
    id uuid NOT NULL,
    prospect_id uuid NOT NULL,
    member_id character varying(64) NOT NULL,
    kind character varying(10) NOT NULL,
    value_normalized character varying(320) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cp_prospect_identifiers_kind_check CHECK (((kind)::text = ANY ((ARRAY['phone'::character varying, 'email'::character varying])::text[])))
);
ALTER TABLE ONLY public.cp_prospect_identifiers ADD CONSTRAINT cp_identifier_unique_per_tenant UNIQUE (member_id, kind, value_normalized);
ALTER TABLE ONLY public.cp_prospect_identifiers ADD CONSTRAINT cp_prospect_identifiers_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cp_prospect_identifiers ADD CONSTRAINT cp_prospect_identifiers_prospect_id_fkey FOREIGN KEY (prospect_id) REFERENCES public.cp_prospects(prospect_id) ON DELETE RESTRICT;
""")

    op.execute("""
CREATE TABLE public.cp_provenance (
    prospect_id uuid NOT NULL,
    source_page character varying(200),
    campaign character varying(100),
    referral_code character varying(50),
    first_event_id character varying(100),
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    member_id character varying(64) NOT NULL
);
ALTER TABLE ONLY public.cp_provenance ADD CONSTRAINT cp_provenance_pkey PRIMARY KEY (prospect_id);
ALTER TABLE ONLY public.cp_provenance ADD CONSTRAINT cp_provenance_event_fk FOREIGN KEY (member_id, first_event_id) REFERENCES public.cp_inbound_events(member_id, event_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.cp_provenance ADD CONSTRAINT cp_provenance_prospect_id_fkey FOREIGN KEY (prospect_id) REFERENCES public.cp_prospects(prospect_id) ON DELETE RESTRICT;
""")

    op.execute("""
CREATE SEQUENCE public.cp_audit_log_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
CREATE TABLE public.cp_audit_log (
    id bigint NOT NULL DEFAULT nextval('public.cp_audit_log_id_seq'::regclass),
    member_id character varying(64),
    actor character varying(64) NOT NULL,
    action character varying(60) NOT NULL,
    target_id character varying(100),
    reason character varying(300),
    at timestamp with time zone DEFAULT now() NOT NULL
);
ALTER SEQUENCE public.cp_audit_log_id_seq OWNED BY public.cp_audit_log.id;
ALTER TABLE ONLY public.cp_audit_log ADD CONSTRAINT cp_audit_log_pkey PRIMARY KEY (id);
""")

    op.execute("""
CREATE SEQUENCE public.cp_consent_ledger_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
CREATE TABLE public.cp_consent_ledger (
    id bigint NOT NULL DEFAULT nextval('public.cp_consent_ledger_id_seq'::regclass),
    prospect_id uuid NOT NULL,
    member_id character varying(64) NOT NULL,
    purpose character varying(40) NOT NULL,
    granted boolean NOT NULL,
    notice_version character varying(40) NOT NULL,
    source character varying(100) NOT NULL,
    event_id character varying(100),
    recorded_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cp_consent_ledger_purpose_check CHECK (((purpose)::text = ANY ((ARRAY['registration_processing'::character varying, 'assessment_processing'::character varying, 'partner_contact'::character varying, 'marketing_optional'::character varying, 'business_interest_processing'::character varying, 'business_matching'::character varying, 'business_followup'::character varying])::text[])))
);
ALTER SEQUENCE public.cp_consent_ledger_id_seq OWNED BY public.cp_consent_ledger.id;
ALTER TABLE ONLY public.cp_consent_ledger ADD CONSTRAINT cp_consent_ledger_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cp_consent_ledger ADD CONSTRAINT cp_consent_ledger_event_fk FOREIGN KEY (member_id, event_id) REFERENCES public.cp_inbound_events(member_id, event_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.cp_consent_ledger ADD CONSTRAINT cp_consent_ledger_prospect_id_fkey FOREIGN KEY (prospect_id) REFERENCES public.cp_prospects(prospect_id) ON DELETE RESTRICT;
CREATE INDEX cp_consent_prospect_idx ON public.cp_consent_ledger USING btree (prospect_id, purpose, recorded_at);
CREATE TRIGGER cp_consent_ledger_no_update BEFORE DELETE OR UPDATE ON public.cp_consent_ledger FOR EACH ROW EXECUTE FUNCTION public.cp_block_mutation();
""")

    op.execute("""
CREATE SEQUENCE public.cp_sync_queue_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
CREATE TABLE public.cp_sync_queue (
    id bigint NOT NULL DEFAULT nextval('public.cp_sync_queue_id_seq'::regclass),
    prospect_id uuid NOT NULL,
    event_id character varying(100),
    destination character varying(40) NOT NULL,
    idempotency_key character varying(200) NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    last_error_code character varying(60),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    member_id character varying(64) NOT NULL,
    CONSTRAINT cp_sync_queue_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'sent'::character varying, 'failed'::character varying, 'dead'::character varying])::text[])))
);
ALTER SEQUENCE public.cp_sync_queue_id_seq OWNED BY public.cp_sync_queue.id;
ALTER TABLE ONLY public.cp_sync_queue ADD CONSTRAINT cp_sync_queue_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cp_sync_queue ADD CONSTRAINT cp_sync_queue_tenant_idempotency_key UNIQUE (member_id, idempotency_key);
ALTER TABLE ONLY public.cp_sync_queue ADD CONSTRAINT cp_sync_queue_event_fk FOREIGN KEY (member_id, event_id) REFERENCES public.cp_inbound_events(member_id, event_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.cp_sync_queue ADD CONSTRAINT cp_sync_queue_prospect_id_fkey FOREIGN KEY (prospect_id) REFERENCES public.cp_prospects(prospect_id) ON DELETE RESTRICT;
CREATE INDEX cp_sync_due_idx ON public.cp_sync_queue USING btree (status, next_attempt_at);
""")

    op.execute("""
GRANT SELECT, INSERT, UPDATE ON TABLE public.cp_audit_log TO elevate_app;
GRANT SELECT, USAGE ON SEQUENCE public.cp_audit_log_id_seq TO elevate_app;
GRANT SELECT, INSERT ON TABLE public.cp_consent_ledger TO elevate_app;
GRANT SELECT, USAGE ON SEQUENCE public.cp_consent_ledger_id_seq TO elevate_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.cp_inbound_events TO elevate_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.cp_prospect_identifiers TO elevate_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.cp_prospects TO elevate_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.cp_provenance TO elevate_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.cp_sync_queue TO elevate_app;
GRANT SELECT, USAGE ON SEQUENCE public.cp_sync_queue_id_seq TO elevate_app;
""")


def downgrade() -> None:
    # Ledger is append-only: dropping it is destructive. Downgrade is intentionally
    # not automated; restore from backup instead.
    raise NotImplementedError("cp_* downgrade is manual (append-only ledger). Restore from backup.")
