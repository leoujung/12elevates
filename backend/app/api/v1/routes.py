from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
"""Phase 1 API: login and member-scoped prospect endpoints.

Every prospect route derives the member from the JWT only. The client never
supplies owner_member_id, so a caller cannot ask for another member's data.
"""
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import hash_password, issue_token, member_id_from_token, verify_password
from app.models.core import Member
from app.services.academy import academy_overview
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
from app.services.video_courses import course_overview, gep_eligible, mark_watched
from app.services import gold_pool_issuance as issuance
from app.services import gold_pool_draw as draw
from app.services.draw_schedule import DrawNotAllowed
from app.models.core import Member as _Member


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


class DrawScheduleIn(BaseModel):
    scheduled_at: datetime | None = None
    zoom_url: str | None = None
    legal_review_approved: bool = False
    timezone: str = "Asia/Jakarta"


class AcademyBatchIn(BaseModel):
    member_id: str
    cycle_id: str
    video_ids: list[str]


class VideoWatchedIn(BaseModel):
    owner_member_id: str
    youtube_video_id: str


class AdminTxIn(BaseModel):
    member_email: str
    transaction_id: str
    tx_type: str
    lp: int
    verified_at: str


class AdminCsvIn(BaseModel):
    csv: str


def create_app(session_factory) -> FastAPI:
    app = FastAPI(title="12ELEVATE AI Network Building Intelligence (Phase 1)")
    # CORS: only the official 12ELEVATE front-ends may call the API from a browser (approved by Leo, 2026-11-23).
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://12elevates.com", "https://app.12elevates.com"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.session_factory = session_factory  # used by tests and admin tooling

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

    def require_admin(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)) -> str:
        # Admin status is read from the database on every request, never from the token.
        m = db.get(_Member, member_id)
        if m is None or not m.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
        return member_id

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

    @app.post("/v1/lp", status_code=410)
    def add_lp_disabled(member_id: str = Depends(current_member_id)):
        # Members can no longer self-report LP. Verified transactions come only from
        # the admin import path (/v1/admin/transactions*), per Gold Elevate Pool v4.0 §5.
        raise HTTPException(status.HTTP_410_GONE,
                            "self-reported LP is disabled; transactions are verified by an administrator")

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

    @app.get("/v1/academy/overview")
    def get_academy(member_id: str = Depends(current_member_id)):
        # member_id required for auth only; academy content is not yet member-specific
        return academy_overview()

    @app.get("/v1/courses/{category}")
    def get_course(category: str, member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        try:
            return course_overview(db, member_id=member_id, category=category)
        except ValueError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))

    @app.post("/v1/courses/{category}/watched", status_code=201)
    def post_watched(category: str, body: VideoWatchedIn, actor: str = Depends(require_admin),
                      db: Session = Depends(get_db)):
        # Admin-only (v4 s.7.2): a member cannot self-report a video as completed.
        try:
            mark_watched(db, owner_member_id=body.owner_member_id, category=category, youtube_video_id=body.youtube_video_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        return {"ok": True}

    @app.post("/v1/admin/gp/academy-batch", status_code=201)
    def admin_academy_batch(body: AcademyBatchIn, actor: str = Depends(require_admin),
                            db: Session = Depends(get_db)):
        # Records a qualification batch of 3 NEW verified videos (v4 s.7.3). Unique per member+video.
        from app.models.gold_pool import GpAcademyUsage, GpCycle
        from app.services.gold_pool_rules import validate_academy_batch, AcademyBatchError
        cycle = db.get(GpCycle, body.cycle_id)
        if cycle is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "cycle not found")
        used = {r[0] for r in db.execute(select(GpAcademyUsage.video_id).where(
            GpAcademyUsage.member_id == body.member_id)).all()}
        try:
            chosen = validate_academy_batch([(v, True) for v in body.video_ids], used)
        except AcademyBatchError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        for vid in chosen:
            db.add(GpAcademyUsage(member_id=body.member_id, video_id=vid, cycle_id=body.cycle_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "video already used by this member")
        return {"ok": True, "recorded": chosen, "cycle_id": body.cycle_id}

    # ---- Gold Pool draw schedule (v4 s.6, s.13, s.33). Nothing here executes a draw. ----
    @app.get("/v1/me")
    def get_me(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        m = db.get(Member, member_id)
        if m is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "member not found")
        return {"id": m.id, "display_name": m.display_name, "email": m.email, "is_admin": bool(m.is_admin)}

    @app.get("/v1/gp/draw-schedule")
    def get_draw_schedule(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        return draw.member_status(db)

    @app.put("/v1/admin/gp/draw-schedule")
    def put_draw_schedule(body: DrawScheduleIn, actor: str = Depends(require_admin),
                          db: Session = Depends(get_db)):
        return draw.admin_update(db, scheduled_at=body.scheduled_at, zoom_url=body.zoom_url,
                                 legal_review_approved=body.legal_review_approved,
                                 timezone_name=body.timezone)

    @app.post("/v1/admin/gp/draw-enable")
    def post_draw_enable(actor: str = Depends(require_admin), db: Session = Depends(get_db)):
        try:
            return draw.admin_enable(db)
        except DrawNotAllowed as e:
            raise HTTPException(status.HTTP_409_CONFLICT, {"code": e.code, "detail": e.detail})

    @app.post("/v1/admin/gp/draw-disable")
    def post_draw_disable(actor: str = Depends(require_admin), db: Session = Depends(get_db)):
        return draw.admin_disable(db)

    @app.get("/v1/gep/eligibility")
    def get_gep_eligibility(member_id: str = Depends(current_member_id), db: Session = Depends(get_db)):
        return gep_eligible(db, member_id=member_id)


    # ---- Admin: Gold Pool transaction verification (Phase 3) ----
    @app.post("/v1/admin/transactions", status_code=201)
    def admin_record_transaction(body: AdminTxIn, actor: str = Depends(require_admin),
                                 db: Session = Depends(get_db)):
        try:
            res = issuance.record_manual(db, actor_id=actor, member_email=body.member_email,
                                         transaction_id=body.transaction_id, tx_type=body.tx_type,
                                         lp=body.lp, verified_at=body.verified_at)
        except issuance.VerificationError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, e.code)
        return {"transaction_id": res.transaction_id, "status": res.status,
                "coupon_id": res.coupon_id, "reason": res.reason}

    @app.post("/v1/admin/transactions/import-csv", status_code=201)
    def admin_import_csv(body: AdminCsvIn, actor: str = Depends(require_admin), db: Session = Depends(get_db)):
        try:
            return issuance.import_csv(db, actor_id=actor, content=body.csv)
        except issuance.VerificationError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, e.code)

    return app
