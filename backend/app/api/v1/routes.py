"""Phase 1 API: login and member-scoped prospect endpoints.

Every prospect route derives the member from the JWT only. The client never
supplies owner_member_id, so a caller cannot ask for another member's data.
"""
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import hash_password, issue_token, member_id_from_token, verify_password
from app.models.core import Member
from app.services.habits import (
    consistency_score,
    habit_today_for_member,
    toggle_habit_item,
    use_rest_day,
)
from app.services.progress import lp_summary_for_member, record_lp
from app.services.prospects import (
    ConsentRequired,
    get_prospect_for_member,
    ingest_prospect,
    list_prospects_for_member,
)


class LoginIn(BaseModel):
    email: str
    password: str


class ProspectIn(BaseModel):
    name: str
    source: str
    consent_purpose: str | None = None
    consent_granted: bool = False
    whatsapp: str | None = None
    email: str | None = None


class LpEntryIn(BaseModel):
    points: int
    note: str | None = None


class HabitToggleIn(BaseModel):
    item_id: int
    done: bool


def create_app(session_factory) -> FastAPI:
    app = FastAPI(title="12ELEVATE AI Network Building Intelligence (Phase 1)")

    def get_db():
        db: Session = session_factory()
        try:
            yield db
        finally:
            db.close()

    def current_member_id(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
        try:
            return member_id_from_token(authorization.split(" ", 1)[1])
        except Exception:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")

    @app.post("/v1/auth/login")
    def login(body: LoginIn, db: Session = Depends(get_db)):
        member = db.query(Member).filter(Member.email == body.email.lower()).one_or_none()
        # Same error for unknown email and wrong password (no account enumeration)
        if member is None or not member.password_hash or not verify_password(body.password, member.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
        return {"access_token": issue_token(member.id), "token_type": "bearer"}

    @app.get("/v1/prospects")
    def list_mine(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        # The owner can see their own prospect's contact details (needed to act on it,
        # e.g. a WhatsApp follow-up button). Isolation between members is unaffected:
        # this query is already scoped to member_id, so no other member's data appears here.
        return [{"id": p.id, "name": p.name, "source": p.source, "status": p.status,
                 "whatsapp": p.whatsapp, "email": p.email, "created_at": p.created_at.isoformat()}
                for p in list_prospects_for_member(db, member_id=member_id)]

    @app.post("/v1/prospects", status_code=201)
    def create_mine(body: ProspectIn, member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        try:
            p = ingest_prospect(db, owner_member_id=member_id, name=body.name, source=body.source,
                                consent_purpose=body.consent_purpose, consent_granted=body.consent_granted,
                                whatsapp=body.whatsapp, email=body.email)
        except ConsentRequired:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "consent is required to store a prospect")
        return {"id": p.id, "name": p.name, "status": p.status}

    @app.get("/v1/prospects/{prospect_id}")
    def get_mine(prospect_id: str, member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        p = get_prospect_for_member(db, member_id=member_id, prospect_id=prospect_id)
        if p is None:
            # Same response whether it does not exist or belongs to someone else
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return {"id": p.id, "name": p.name, "source": p.source, "status": p.status}

    @app.post("/v1/lp", status_code=201)
    def add_lp(body: LpEntryIn, member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        try:
            entry = record_lp(db, owner_member_id=member_id, points=body.points, note=body.note)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        return {"id": entry.id, "points": entry.points}

    @app.get("/v1/lp/summary")
    def lp_summary(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        return lp_summary_for_member(db, member_id=member_id)

    @app.put("/v1/habit/today")
    def toggle_habit_today(body: HabitToggleIn, member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        from datetime import date
        try:
            toggle_habit_item(db, owner_member_id=member_id, day=date.today().isoformat(),
                              item_id=body.item_id, done=body.done)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        return habit_today_for_member(db, member_id=member_id)

    @app.get("/v1/habit/today")
    def get_habit_today(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        return habit_today_for_member(db, member_id=member_id)

    @app.post("/v1/habit/rest-day")
    def take_rest_day(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        from datetime import date
        try:
            result = use_rest_day(db, owner_member_id=member_id, day=date.today().isoformat())
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        return result

    @app.get("/v1/habit/consistency")
    def get_consistency(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        return consistency_score(db, member_id=member_id, days=7)

    return app
