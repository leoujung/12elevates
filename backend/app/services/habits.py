"""12-Hour Daily Habit Tracker: Core 4 + Power-Ups 8, streak, and 7-day consistency score.

Item text is copied verbatim from the 22-Nov-2026 Master Brief (section 3). Nothing here
is invented copy; if the business owner changes the wording, update HABIT_ITEMS to match.

Rules:
- Every read/write is scoped to the owning member (same isolation pattern as Prospect).
- completed_items on HabitDay is a comma-separated list of item ids, e.g. "1,2,3,4".
- Daily Win = all of Core 4 (ids 1-4) done. Max Elevate = all 12 done.
- Streak = consecutive days (including rest days) with at least a Daily Win, counting
  backward from today. A day with no HabitDay row and not marked rest breaks the streak.
- Rest Day quota (ASSUMPTION, not specified in the brief): 1 per calendar month. Flagged
  for business-owner confirmation -- change REST_DAY_QUOTA_PER_MONTH if that's wrong.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import HabitDay

REST_DAY_QUOTA_PER_MONTH = 1  # ASSUMPTION: brief did not specify a period for Streak Freeze

HABIT_ITEMS = [
    {"id": 1, "level": "core4", "title": "Fuel Your Body",
     "desc": "Konsumsi nutrisi harianmu & cek level energi pagi.", "action": None},
    {"id": 2, "level": "core4", "title": "Upgrade Ilmu 3 Menit",
     "desc": "Tonton/baca 1 micro-learning singkat di ONE Academy.", "action": None},
    {"id": 3, "level": "core4", "title": "Share Link Cek Skor",
     "desc": "Bagikan 1 konten edukasi + link asesmen gratis.", "action": "copy"},
    {"id": 4, "level": "core4", "title": "Sapa 1 Warm Lead",
     "desc": "Kirim hasil rapor kesehatan ke audiens yang baru isi kuis.", "action": "whatsapp"},
    {"id": 5, "level": "power_up", "title": "Share Momen Sehat (15 Detik)",
     "desc": "Upload 1 Story santai rutinitas sehatmu (tanpa hard-selling).", "action": None},
    {"id": 6, "level": "power_up", "title": "Komen Tulus 5 Teman",
     "desc": "Bangun interaksi organik di IG/TikTok/WA teman.", "action": None},
    {"id": 7, "level": "power_up", "title": "Cek Radar Asesmen",
     "desc": "Intip siapa saja yang baru klik atau selesai mengisi kuis.", "action": None},
    {"id": 8, "level": "power_up", "title": "Racik Chat via AI Co-Pilot",
     "desc": "Gunakan AI untuk membalas pertanyaan prospek dengan santai.", "action": None},
    {"id": 9, "level": "power_up", "title": "Latihan Ngobrol bareng AI",
     "desc": "Simulasi 2 menit menjawab pertanyaan umum calon pelanggan.", "action": None},
    {"id": 10, "level": "power_up", "title": "Check-In Bestie / Pelanggan",
     "desc": "Tanya kabar & progres kesehatan 1 pelanggan aktif.", "action": None},
    {"id": 11, "level": "power_up", "title": "Spill Progres di Komunitas",
     "desc": "Bagikan small wins atau diskusi ringan di grup 12 BUILD.", "action": None},
    {"id": 12, "level": "power_up", "title": "Cek Vibe & Insight Hari Ini",
     "desc": "Review 2 menit jumlah klik link & pilih ide konten besok.", "action": None},
]
CORE4_IDS = {1, 2, 3, 4}
ALL_IDS = {item["id"] for item in HABIT_ITEMS}


def _parse_items(s: str) -> set[int]:
    return {int(x) for x in s.split(",") if x.strip().isdigit()}


def _serialize_items(ids: set[int]) -> str:
    return ",".join(str(i) for i in sorted(ids))


def _get_or_create_day(db: Session, *, owner_member_id: str, day: str) -> HabitDay:
    stmt = select(HabitDay).where(HabitDay.owner_member_id == owner_member_id, HabitDay.day == day)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = HabitDay(owner_member_id=owner_member_id, day=day, completed_items="")
        db.add(row)
        db.flush()
    return row


def toggle_habit_item(db: Session, *, owner_member_id: str, day: str, item_id: int, done: bool) -> HabitDay:
    if item_id not in ALL_IDS:
        raise ValueError(f"unknown habit item id {item_id}")
    row = _get_or_create_day(db, owner_member_id=owner_member_id, day=day)
    items = _parse_items(row.completed_items)
    if done:
        items.add(item_id)
    else:
        items.discard(item_id)
    row.completed_items = _serialize_items(items)
    db.commit()
    return row


def _rest_days_used_this_month(db: Session, *, member_id: str, today: date) -> int:
    month_prefix = today.strftime("%Y-%m")
    stmt = select(HabitDay).where(HabitDay.owner_member_id == member_id, HabitDay.is_rest_day.is_(True))
    rows = [r for r in db.execute(stmt).scalars() if r.day.startswith(month_prefix)]
    return len(rows)


def use_rest_day(db: Session, *, owner_member_id: str, day: str) -> dict:
    """Marks a day as a rest day (Streak Freeze), subject to the monthly quota."""
    today = date.fromisoformat(day)
    used = _rest_days_used_this_month(db, member_id=owner_member_id, today=today)
    if used >= REST_DAY_QUOTA_PER_MONTH:
        raise ValueError(f"rest day quota ({REST_DAY_QUOTA_PER_MONTH}/month) already used")
    row = _get_or_create_day(db, owner_member_id=owner_member_id, day=day)
    row.is_rest_day = True
    db.commit()
    return {"day": row.day, "is_rest_day": True, "rest_days_left_this_month": REST_DAY_QUOTA_PER_MONTH - used - 1}


def _day_status(row: HabitDay | None) -> dict:
    if row is None:
        return {"completed_ids": [], "completed_count": 0, "core4_done": False, "is_rest_day": False}
    ids = sorted(_parse_items(row.completed_items))
    return {
        "completed_ids": ids,
        "completed_count": len(ids),
        "core4_done": CORE4_IDS.issubset(ids),
        "is_rest_day": row.is_rest_day,
    }


def habit_today_for_member(db: Session, *, member_id: str, today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    stmt = select(HabitDay).where(HabitDay.owner_member_id == member_id, HabitDay.day == today)
    row = db.execute(stmt).scalar_one_or_none()
    status = _day_status(row)
    count = status["completed_count"]
    if count >= 12:
        footer = "Legend! 100% tuntas. Kamu luar biasa konsisten hari ini."
    elif count >= 4:
        footer = "Keren, Daily Win aman! Lanjutkan Power-Ups untuk ekstra poin Golden Elevate Pool."
    else:
        footer = "Selesaikan 4 Core Habit dulu untuk mengamankan Daily Win hari ini!"

    streak, had_rest = _compute_streak(db, member_id=member_id, today=date.fromisoformat(today))
    rest_used = _rest_days_used_this_month(db, member_id=member_id, today=date.fromisoformat(today))

    return {
        "day": today,
        "items": HABIT_ITEMS,
        "completed_ids": status["completed_ids"],
        "completed_count": count,
        "total": 12,
        "percent": round(count / 12 * 100),
        "core4_done": status["core4_done"],
        "is_rest_day": status["is_rest_day"],
        "footer_message": footer,
        "streak_days": streak,
        "rest_day_quota_per_month": REST_DAY_QUOTA_PER_MONTH,
        "rest_days_left_this_month": max(0, REST_DAY_QUOTA_PER_MONTH - rest_used),
    }


def _compute_streak(db: Session, *, member_id: str, today: date) -> tuple[int, bool]:
    """Counts consecutive days (walking backward from today) with Daily Win or a rest day."""
    stmt = select(HabitDay).where(HabitDay.owner_member_id == member_id)
    by_day = {r.day: r for r in db.execute(stmt).scalars()}
    streak = 0
    used_rest = False
    cursor = today
    while True:
        row = by_day.get(cursor.isoformat())
        if row is None:
            break
        st = _day_status(row)
        if st["is_rest_day"]:
            used_rest = True
            streak += 1
        elif st["core4_done"]:
            streak += 1
        else:
            break
        cursor = cursor - timedelta(days=1)
    return streak, used_rest


def consistency_score(db: Session, *, member_id: str, days: int = 7) -> dict:
    """Last N days: per-day percent (for a bar chart) and the average."""
    today = date.today()
    stmt = select(HabitDay).where(HabitDay.owner_member_id == member_id)
    by_day = {r.day: r for r in db.execute(stmt).scalars()}
    series = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        row = by_day.get(d.isoformat())
        st = _day_status(row)
        pct = 100 if st["is_rest_day"] else round(st["completed_count"] / 12 * 100)
        series.append({"date": d.isoformat(), "percent": pct, "is_rest_day": st["is_rest_day"],
                       "completed_count": st["completed_count"]})
    avg = round(sum(s["percent"] for s in series) / len(series)) if series else 0
    return {"days": series, "average_percent": avg}
