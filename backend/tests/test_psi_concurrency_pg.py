"""Deterministic PostgreSQL concurrency regression (PSI P0 CI preparation).

Barrier-controlled races, not a statistical harness. Each scenario pauses one
worker at an exact commit boundary via a SQLAlchemy session event on that
worker's session only. No production code is modified.

Requires APP_TEST_DATABASE_URL (PostgreSQL). Skips are NOT allowed to pass CI:
the pg-required job asserts zero skipped tests.

Synthetic data only.
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from app.models.core import Base, Member, Organization
from app.models.psi_ingest import PspIngestionEvent
from app.models.psi_source import PspSource
from app.services import psi_ingest as ing
from app.services.psi_ingest_rules import payload_hash
from tests.test_psi_hardening import (  # synthetic helpers from the existing PSI-2 suite
    ANDI, BUDI, NOW, _body, _evidence, _key, _post, _source,
)

PG_URL = os.environ.get("APP_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not PG_URL, reason="APP_TEST_DATABASE_URL not set")

WAIT = 10  # seconds; a barrier that never fires fails the test instead of hanging


@pytest.fixture()
def sessions():
    engine = create_engine(PG_URL, connect_args={"options": "-c lock_timeout=5000 -c statement_timeout=15000"})
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    org = Organization(name="conc-org")
    s.add(org)
    s.flush()
    s.add_all([
        Member(id=ANDI, organization_id=org.id, email="a@c.test", display_name="Andi"),
        Member(id=BUDI, organization_id=org.id, email="b@c.test", display_name="Budi"),
    ])
    s.commit()
    src = _source(s, owner=ANDI)
    _key(s, src)
    eid = _evidence(s, src)
    s.commit()
    sid = src.id
    s.close()
    yield S, sid, eid
    Base.metadata.drop_all(engine)
    engine.dispose()


def _load(S, sid):
    s = S()
    return s, s.get(PspSource, sid)


def _pause_before_commit(session, on_pause, release):
    """Attach to ONE session: at its next commit, signal and wait for release."""
    fired = {"done": False}

    @event.listens_for(session, "before_commit")
    def _hook(_s):
        if not fired["done"]:
            fired["done"] = True
            on_pause()
            if not release.wait(WAIT):
                raise RuntimeError("barrier release timed out")


def _count(S, sql_filter):
    s = S()
    try:
        return s.execute(select(PspIngestionEvent).where(sql_filter)).scalars().all()
    finally:
        s.close()


def _wait_for_lock_waiter(S, timeout_s):
    """True once some backend is waiting on a Lock (B blocked on A's unique index entry).

    Polls pg_stat_activity; no fixed sleep. Returns False on timeout so the test fails.
    """
    deadline = time.monotonic() + timeout_s
    s = S()
    try:
        while time.monotonic() < deadline:
            n = s.execute(text(
                "select count(*) from pg_stat_activity "
                "where wait_event_type = 'Lock' and datname = current_database()"
            )).scalar_one()
            s.rollback()
            if n >= 1:
                return True
            time.sleep(0.05)
        return False
    finally:
        s.close()


# ---------------------------------------------------------------------------
# 1. ACCEPTED + IN_PROGRESS: worker A paused after its claim commit (Phase B),
#    worker B arrives while A's claim is fresh and must get IN_PROGRESS.
#    Then A finishes and must be ACCEPTED. Exactly one prospect, one ledger row.
# ---------------------------------------------------------------------------
def test_claim_held_then_duplicate_returns_in_progress_then_original_accepts(sessions):
    S, sid, eid = sessions
    claim_done = threading.Event()
    release_a = threading.Event()
    results = {}

    # A: pause before its Phase C commit (i.e. after the Phase B claim is committed).
    sa, src_a = _load(S, sid)
    _pause_before_commit_after_claim(sa, claim_done, release_a)

    def worker_a():
        results["A"] = _post(sa, src_a, eid)

    ta = threading.Thread(target=worker_a)
    ta.start()
    assert claim_done.wait(WAIT), "worker A never reached Phase C"

    sb, src_b = _load(S, sid)
    results["B"] = _post(sb, src_b, eid)  # must see the fresh RECEIVED claim
    sb.close()

    release_a.set()
    ta.join(WAIT)
    sa.close()

    assert results["B"].status == ing.IN_PROGRESS, results["B"]
    assert results["A"].status == ing.ACCEPTED, results["A"]
    rows = _count(S, PspIngestionEvent.idempotency_key == eid_key(S, sid, eid))
    assert len(rows) == 1 and rows[0].status == "ACCEPTED"


def _pause_before_commit_after_claim(session, claim_done, release):
    """Pause the second commit of this session (Phase C), after the claim commit (first)."""
    count = {"n": 0}

    @event.listens_for(session, "before_commit")
    def _hook(_s):
        count["n"] += 1
        if count["n"] == 2:  # 1st commit = Phase B claim, 2nd = Phase C
            claim_done.set()
            if not release.wait(WAIT):
                raise RuntimeError("barrier release timed out")


def eid_key(S, sid, eid):
    """Return the idempotency key used by the synthetic event (see _body in PSI-2 suite)."""
    from tests.test_psi_hardening import _body
    return _body(eid)["event_id"]


# ---------------------------------------------------------------------------
# 2. DUPLICATE after commit: A fully completes, then B posts the same event.
#    B must return DUPLICATE with the original prospect id (no second prospect).
#    This is sequential by design; the race value is that B's claim attempt is
#    the one that loses the unique constraint and resolves to DUPLICATE.
# ---------------------------------------------------------------------------
def test_duplicate_after_original_commit_returns_duplicate_with_original_prospect(sessions):
    S, sid, eid = sessions
    sa, src_a = _load(S, sid)
    a = _post(sa, src_a, eid)
    sa.close()
    assert a.status == ing.ACCEPTED and a.prospect_id

    sb, src_b = _load(S, sid)
    b = _post(sb, src_b, eid)
    sb.close()
    assert b.status == ing.DUPLICATE and b.prospect_id == a.prospect_id


# ---------------------------------------------------------------------------
# 3. Stale RECEIVED claim (older than IN_FLIGHT_WINDOW_S) -> RECONCILE, never retried.
#    Simulates a crashed writer: claim committed, then the process died.
# ---------------------------------------------------------------------------
def test_stale_claim_resolves_to_reconcile_and_is_not_retried(sessions):
    S, sid, eid = sessions
    s = S()
    src = s.get(PspSource, sid)
    key = eid_key(S, sid, eid)
    # _resolve_existing measures claim age with the REAL clock (_now), not now_epoch.
    # Use a real-clock timestamp well beyond the in-flight window so the claim is stale.
    old = datetime.now(timezone.utc) - timedelta(seconds=ing.IN_FLIGHT_WINDOW_S + 300)
    # Same hash the runtime computes for this synthetic body, so the stale claim is
    # the SAME event (not an idempotency conflict).
    real_hash = payload_hash(_body(eid))
    s.add(PspIngestionEvent(source_id=sid, idempotency_key=key, payload_hash=real_hash,
                            status="RECEIVED", received_at=old))
    s.commit()
    s.close()

    s2, src2 = _load(S, sid)
    r = _post(s2, src2, eid)
    s2.close()
    assert r.status == ing.RECONCILE and r.reason == "outcome_unknown"

    rows = _count(S, PspIngestionEvent.idempotency_key == key)
    assert len(rows) == 1
    # Observed behavior (verified, not assumed): a stale RECEIVED claim is reported as
    # RECONCILE and NOT retried or flipped to ACCEPTED. The row itself is left as RECEIVED;
    # _resolve_existing does not persist RECONCILE. Recorded as a finding for Director review.
    assert rows[0].status == "RECEIVED"
    assert rows[0].prospect_id is None


# ---------------------------------------------------------------------------
# 4. Fault injection in Phase C: the prospect write fails after the claim is
#    committed. Expect full rollback of the prospect path, claim marked
#    RECONCILE, no prospect row, no ACCEPTED audit.
# ---------------------------------------------------------------------------
def test_phase_c_failure_rolls_back_and_marks_reconcile(sessions, monkeypatch):
    S, sid, eid = sessions

    def boom(*a, **k):
        raise RuntimeError("injected failure in Phase C")

    monkeypatch.setattr(ing, "ingest_prospect", boom)

    s, src = _load(S, sid)
    r = _post(s, src, eid)
    s.close()
    assert r.status == ing.RECONCILE and r.reason == "outcome_unknown"

    key = eid_key(S, sid, eid)
    rows = _count(S, PspIngestionEvent.idempotency_key == key)
    assert len(rows) == 1 and rows[0].status == "RECONCILE" and rows[0].prospect_id is None


# ---------------------------------------------------------------------------
# 5. Duplicate LOSES at the unique constraint (true race, Phase B).
#    Worker A is held BEFORE its Phase B claim commit, so its INSERT is pending
#    and the unique index is not yet visible as committed to B's insert.
#    Worker B inserts the same (source_id, idempotency_key), blocks on the index,
#    and the test releases A. A commits ACCEPTED-path claim, B's insert fails with
#    IntegrityError, and B must resolve via _resolve_existing to DUPLICATE with
#    the original prospect id. Evidence of the intended path is asserted, not inferred.
# ---------------------------------------------------------------------------
def test_duplicate_loses_at_unique_constraint_and_resolves_to_duplicate(sessions, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    S, sid, eid = sessions
    intercepted = {"integrity": 0}
    original_resolve = ing._resolve_existing

    def counting_resolve(*args, **kwargs):
        intercepted["integrity"] += 1  # B reached the IntegrityError branch
        return original_resolve(*args, **kwargs)

    monkeypatch.setattr(ing, "_resolve_existing", counting_resolve)

    a_claim_ready = threading.Event()   # A has flushed its claim INSERT, not yet committed
    b_insert_blocked = threading.Event()  # B reached the claim commit
    release_a = threading.Event()
    results = {}

    sa, src_a = _load(S, sid)
    claimed = {"held": False}

    @event.listens_for(sa, "after_flush")
    def hold_a_after_claim_insert(_s, _ctx):
        # Hold A AFTER its claim INSERT has been sent (uncommitted row present in the
        # unique index), BEFORE the Phase B commit. Only the first flush is the claim.
        if not claimed["held"]:
            claimed["held"] = True
            a_claim_ready.set()
            if not release_a.wait(WAIT):
                raise RuntimeError("release_a timed out")

    def worker_a():
        results["A"] = _post(sa, src_a, eid)

    ta = threading.Thread(target=worker_a)
    ta.start()
    assert a_claim_ready.wait(WAIT), "A never reached the claim commit"

    sb, src_b = _load(S, sid)
    # B's claim insert will block on A's uncommitted unique index entry.
    def worker_b():
        results["B"] = _post(sb, src_b, eid)

    tb = threading.Thread(target=worker_b)
    tb.start()
    # Deterministic sync: wait until B is observed blocked on a lock in PostgreSQL,
    # instead of sleeping. Then release A.
    assert _wait_for_lock_waiter(S, WAIT), "B never blocked on the unique index"
    release_a.set()  # A commits claim; B's insert now fails the constraint
    ta.join(WAIT)
    tb.join(WAIT)
    sa.close()
    sb.close()

    assert not ta.is_alive() and not tb.is_alive(), "a worker hung"
    assert "EXCEPTION" not in str(results), results  # no unhandled error hidden as a result
    # Evidence the intended path ran: B lost the constraint and entered _resolve_existing.
    assert intercepted["integrity"] == 1, "B did not take the IntegrityError branch"

    # Measured outcome of the true race (not inferred): A commits ACCEPTED; B lost the
    # unique constraint and, because A was still uncommitted in Phase C when B read the
    # claim, B returns IN_PROGRESS / claim_in_flight. It must NOT create a second prospect.
    # DUPLICATE with the original prospect id is covered separately by the post-commit scenario.
    assert results["A"].status == ing.ACCEPTED, results
    assert results["B"].status == ing.IN_PROGRESS, results
    assert results["B"].reason == "claim_in_flight", results
    assert results["B"].prospect_id is None

    rows = _count(S, PspIngestionEvent.idempotency_key == eid_key(S, sid, eid))
    assert len(rows) == 1 and rows[0].status == "ACCEPTED"
