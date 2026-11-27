"""Member-scoped endpoints for declared target tags. Member id ONLY from the token, never from the body."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app.services import member_target_tags as mtt


class TargetTagsIn(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=mtt.MAX_TAGS)


def register_target_tag_routes(app, get_db, current_member_id):
    @app.get("/v1/member/target-tags")
    def get_target_tags(member_id: str = Depends(current_member_id), db=Depends(get_db)):
        return {"member_id": member_id, "tags": mtt.get_tags(db, member_id),
                "allowed": sorted(mtt.ALLOWED_TAGS)}

    @app.put("/v1/member/target-tags")
    def put_target_tags(body: TargetTagsIn, member_id: str = Depends(current_member_id),
                        db=Depends(get_db)):
        try:
            saved = mtt.set_tags(db, member_id, body.tags)
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc))
        return {"member_id": member_id, "tags": saved}
