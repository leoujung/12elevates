"""Member-facing referral code endpoint. Member can only get a code for themselves."""
from fastapi import Depends
from sqlalchemy import text  # noqa: F401

from app.services.referral_codes import issue_code


def register_referral_code_routes(app, get_db, current_member_id):
    @app.post("/v1/member/referral-code", status_code=200)
    def create_my_referral_code(member_id: str = Depends(current_member_id), db=Depends(get_db)):
        code = issue_code(db, member_id)
        db.commit()
        return {"success": True, "referral_code": code}
