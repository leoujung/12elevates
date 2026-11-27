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
        return {
            "member_id": member_id,
            "count": len(rows),
            "items": [
                {
                    **dict(r),
                    "created_at": (r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else r["created_at"]),
                    "prospect_id": str(r["prospect_id"]) if r["prospect_id"] else None,
                }
                for r in rows
            ],
        }
