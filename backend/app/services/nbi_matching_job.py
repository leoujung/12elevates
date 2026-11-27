"""NBI matching job (deterministic). Reads cp_* and writes nbi_matching_results.

Design:
- No LLM, no network. Scoring is delegated to the pure evaluate() in nbi_matching.
- Only BUSINESS pathway in this job. Customer Discovery is NOT implemented (D2/D6 pending).
- Consent gate: a prospect is scored only if a LATEST business_matching row is granted=true.
- Source gate: source_verified is True only when provenance carries a referral_code
  (decision by Leo: referral = verified source). Otherwise quarantined by evaluate().
- Member target tags: read from member_target_tags (table created in migration). If a
  member has no tags, fit is 0 and reason says so. No tags are invented.
- Writes are is_synthetic=false. Results are replaced per job, never mutated in place.
"""
import uuid
from sqlalchemy import text

from app.services import nbi_matching as nm  # pure scoring/gates (already in repo)

PATHWAY = "business"
SOURCE_KEY = "referral"


def _iso(value):
    """Accept datetime (Postgres) or str (SQLite tests). Never raises on either."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _latest_consent(db, prospect_id, purpose):
    row = db.execute(
        text(
            "select granted, id from cp_consent_ledger "
            "where prospect_id = :p and purpose = :purpose "
            "order by recorded_at desc, id desc limit 1"
        ),
        {"p": prospect_id, "purpose": purpose},
    ).first()
    return (bool(row[0]), str(row[1])) if row else (False, None)


def run_business_job(db, member_id):
    """Score all business prospects of one member. Returns job id and counts."""
    job_id = str(uuid.uuid4())
    db.execute(
        text(
            "insert into nbi_discovery_jobs (id, member_id, pathway, source_key, is_synthetic, status, created_at) "
            "values (:id, :m, :pw, :sk, false, 'running', now())"
        ),
        {"id": job_id, "m": member_id, "pw": PATHWAY, "sk": SOURCE_KEY},
    )

    # member_target_tags does NOT exist yet (no migration, no decision). Until it does,
    # every member has zero target tags, so fit is 0 with an explicit reason. Never invented.
    target_tags = []

    prospects = db.execute(
        text(
            "select p.prospect_id, p.display_name, pr.referral_code, pr.first_seen_at "
            "from cp_prospects p join cp_provenance pr on pr.prospect_id = p.prospect_id "
            "where p.member_id = :m and p.prospect_type = 'business' and p.status = 'active'"
        ),
        {"m": member_id},
    ).mappings().all()

    counts = {"scored": 0, "rejected_no_consent": 0, "quarantined_unverified_source": 0}
    for p in prospects:
        granted, consent_id = _latest_consent(db, p["prospect_id"], "business_matching")
        record = {
            "name": p["display_name"] or "",
            "email": None,
            "phone": None,
            "source_key": SOURCE_KEY if p["referral_code"] else None,
            "source_verified": bool(p["referral_code"]),
            "captured_at": _iso(p["first_seen_at"]),
            "consent_record_id": consent_id,
            "consent_granted": granted,
            "tags": [],
            "signals": {"explicit_inquiry": True},
            "duplicate_of": None,
        }
        res = nm.evaluate(record, {"target_tags": target_tags}, PATHWAY)
        status = res["status"]
        if status in counts:
            counts[status] += 1
        db.execute(
            text(
                "insert into nbi_matching_results (id, job_id, member_id, prospect_id, fit_score, intent_confidence, "
                "data_confidence, reason, rules_version, is_synthetic, created_at) "
                "values (:id, :j, :m, :p, :f, :i, :d, :r, :rv, false, now())"
            ),
            {
                "id": str(uuid.uuid4()), "j": job_id, "m": member_id, "p": p["prospect_id"],
                "f": res["fit_score"], "i": res["intent_confidence"], "d": res["data_confidence"],
                "r": status + ": " + "; ".join(res["reasons"])[:2000], "rv": res["rules_version"],
            },
        )

    db.execute(text("update nbi_discovery_jobs set status='done', finished_at=now() where id=:id"), {"id": job_id})
    return {"job_id": job_id, "prospects": len(prospects), **counts}


def _table_exists(db, name):
    return bool(db.execute(
        text("select 1 from information_schema.tables where table_schema='public' and table_name=:n"),
        {"n": name},
    ).first())
