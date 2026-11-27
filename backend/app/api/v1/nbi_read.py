"""NBI read-only results route (staging). Member-scoped, SELECT only.

GET /v1/nbi/results
- Requires Bearer member token (same auth as other member routes).
- Returns only rows where member_id == the token's member id. Never accepts member_id from the client.
- Reads nbi_matching_results only. No writes, no AI, no scoring here.
"""
from sqlalchemy import text
from fastapi import Depends, Query


def register_nbi_read_routes(app, get_db, current_member_id):
    @app.get("/v1/nbi/results")
    def nbi_results(
        limit: int = Query(default=50, ge=1, le=200),
        member_id: str = Depends(current_member_id),
        db=Depends(get_db),
    ):
        rows = db.execute(
            text(
                """
                SELECT id, job_id, prospect_id, fit_score, intent_confidence,
                       data_confidence, reason, rules_version, is_synthetic, created_at
                FROM nbi_matching_results
                WHERE member_id = :member_id
                  AND is_synthetic = false
                ORDER BY created_at DESC, id
                LIMIT :limit
                """
            ),
            {"member_id": member_id, "limit": limit},
        ).mappings().all()
        # Interest tags for the prospects in these results. Scoped to the same member_id.
        prospect_ids = sorted({str(r["prospect_id"]) for r in rows if r["prospect_id"]})
        tags_by_prospect = {}
        if prospect_ids:
            # Portable (Postgres + SQLite tests): explicit IN list with bound params.
            keys = {f"p{i}": pid for i, pid in enumerate(prospect_ids)}
            in_clause = ", ".join(f":{k}" for k in keys)
            tag_rows = db.execute(
                text(
                    f"""
                    SELECT CAST(prospect_id AS TEXT) AS prospect_id, tag
                    FROM cp_prospect_tags
                    WHERE member_id = :member_id
                      AND CAST(prospect_id AS TEXT) IN ({in_clause})
                    ORDER BY tag
                    """
                ),
                {"member_id": member_id, **keys},
            ).mappings().all()
            for t in tag_rows:
                tags_by_prospect.setdefault(t["prospect_id"], []).append(t["tag"])
        return {
            "member_id": member_id,
            "count": len(rows),
            "items": [
                {
                    **dict(r),
                    "created_at": (r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else r["created_at"]),
                    "prospect_id": str(r["prospect_id"]) if r["prospect_id"] else None,
                    "interest_tags": tags_by_prospect.get(str(r["prospect_id"]), []) if r["prospect_id"] else [],
                }
                for r in rows
            ],
        }
