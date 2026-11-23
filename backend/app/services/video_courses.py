"""Video courses: "Edukasi Produk" (Transfer Factor) and "Keuntungan Mitra" categories.

Source videos currently live in Google Drive, but Drive's iframe cannot report playback
completion (cross-origin -- our JS cannot read the player's state). So these are served
via YouTube (Unlisted) using the official IFrame API, which does fire a reliable
onStateChange -> ENDED event. The business owner is uploading the videos; youtube_id
fields are filled in as links are provided. Until filled, a video is "not ready" and the
frontend must not claim it is watchable.

Honesty note on what completion can and cannot guarantee (told to the business owner,
repeated here for future maintainers): finishing playback to the end does not prove the
member watched attentively, and a technically determined member could manipulate the
browser console. This is the same standard most non-proctored e-learning platforms use;
it is not cryptographic proof of attention.

"Keuntungan Mitra" videos are required_for_pool=True: the business owner stated these are
"salah satu dasar penilaian... bisa ikut undian dari Golden Elevate Pool" (one basis for
lottery eligibility). gep_eligible() in this module is the single source of truth for
that gate -- do not duplicate the "all required videos watched" check elsewhere.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import VideoProgress

# Titles taken verbatim from the Google Drive filenames (22-Nov-2026). youtube_id is None
# until the business owner supplies the YouTube link for that video.
# Orders 1-8 were supplied by the business owner on 22-Nov-2026 as public YouTube Shorts
# on the 12Elevates channel (verified via oEmbed: all 8 public, embeddable, correct channel).
EDUKASI_PRODUK = [
    {"order": 1, "title": "Apa itu Transfer Factor?", "youtube_id": "mTkq8hK6FLQ"},
    {"order": 2, "title": "Cara TF Bekerja di Tubuh", "youtube_id": "ir-DR-TtqFc"},
    {"order": 3, "title": "Keunikan TF 4Life", "youtube_id": "6U7WvHJFeCk"},
    {"order": 4, "title": "Kemurnian TF Tri Factor Formula", "youtube_id": "mgWIJuCt1gk"},
    {"order": 5, "title": "Cara TF Meningkatkan IQ Imun", "youtube_id": "1DYdHcABUyA"},
    {"order": 6, "title": "Hubungan TF dan Sistem Imun", "youtube_id": "_gwKmJZn1kY"},
    {"order": 7, "title": "Molekul Protein Transfer Factor", "youtube_id": "u1ZB8HcyHiY"},
    {"order": 8, "title": "Butuh Dukungan Lebih? TF Plus Jawabannya!", "youtube_id": "DQqTCQiYbus"},
    {"order": 9, "title": "Penelitian TF Plus", "youtube_id": None},
    {"order": 10, "title": "TF Chewable, Enak & Mudah", "youtube_id": None},
    {"order": 11, "title": "Riovida", "youtube_id": None},
    {"order": 12, "title": "Glucoach", "youtube_id": None},
    {"order": 13, "title": "Nutra Versi Ramadan", "youtube_id": None},
    {"order": 14, "title": "Glucoach Versi Ramadan", "youtube_id": None},
    {"order": 15, "title": "Riovida Stix Edukasi", "youtube_id": None},
    {"order": 16, "title": "Riovida Juice 1", "youtube_id": None},
    {"order": 17, "title": "Tips Riovida Juice", "youtube_id": None},
    {"order": 18, "title": "Chewable 1", "youtube_id": None},
    {"order": 19, "title": "Recall V1", "youtube_id": None},
    {"order": 20, "title": "Recall V2", "youtube_id": None},
    {"order": 21, "title": "PBGS+", "youtube_id": None},
    {"order": 22, "title": "CV", "youtube_id": None},
    {"order": 23, "title": "Renuvo", "youtube_id": None},
    {"order": 24, "title": "Bioefa", "youtube_id": None},
]

KEUNTUNGAN_MITRA = [
    {"order": 0, "title": "Opening", "youtube_id": "f1tmw4BxqSk", "required_for_pool": True},
    {"order": 1, "title": "Program Loyalty", "youtube_id": "t1OW6CklUQw", "required_for_pool": True},
    {"order": 2, "title": "Keuntungan Langsung", "youtube_id": None, "required_for_pool": True},
    {"order": 3, "title": "Bonus Rekrut", "youtube_id": None, "required_for_pool": True},
    {"order": 4, "title": "Builder Bonus", "youtube_id": None, "required_for_pool": True},
    {"order": 5, "title": "Myshop Review", "youtube_id": None, "required_for_pool": True},
    {"order": 6, "title": "Bonus Generasi", "youtube_id": None, "required_for_pool": True},
    {"order": 7, "title": "Leadership Pool", "youtube_id": None, "required_for_pool": True},
]

CATALOGS = {"edukasi_produk": EDUKASI_PRODUK, "keuntungan_mitra": KEUNTUNGAN_MITRA}


def _watched_ids(db: Session, *, member_id: str) -> set[str]:
    stmt = select(VideoProgress.youtube_video_id).where(VideoProgress.owner_member_id == member_id)
    return {row[0] for row in db.execute(stmt).all()}


def course_overview(db: Session, *, member_id: str, category: str) -> dict:
    if category not in CATALOGS:
        raise ValueError(f"unknown category {category}")
    watched = _watched_ids(db, member_id=member_id)
    videos = []
    for v in CATALOGS[category]:
        ready = v["youtube_id"] is not None
        videos.append({
            **v,
            "ready": ready,
            "watched": ready and v["youtube_id"] in watched,
        })
    total_ready = sum(1 for v in videos if v["ready"])
    completed = sum(1 for v in videos if v["watched"])
    return {
        "category": category,
        "videos": videos,
        "total": len(videos),
        "total_ready": total_ready,
        "completed": completed,
        # Progress is measured against the videos that are actually watchable, not the
        # whole catalog: 16 of the 24 "Edukasi Produk" entries have no youtube_id yet, and
        # counting those would cap a fully-watched member at 33%.
        # Half-up rounding so the API agrees with the dashboard's Math.round (1/8 -> 13%).
        "percent": int(completed / total_ready * 100 + 0.5) if total_ready else 0,
    }


def mark_watched(db: Session, *, owner_member_id: str, category: str, youtube_video_id: str) -> None:
    valid_ids = {v["youtube_id"] for v in CATALOGS.get(category, []) if v["youtube_id"]}
    if youtube_video_id not in valid_ids:
        raise ValueError("unknown or not-yet-configured video id for this category")
    stmt = select(VideoProgress).where(
        VideoProgress.owner_member_id == owner_member_id,
        VideoProgress.youtube_video_id == youtube_video_id,
    )
    if db.execute(stmt).scalar_one_or_none() is not None:
        return  # already recorded; idempotent
    db.add(VideoProgress(owner_member_id=owner_member_id, youtube_video_id=youtube_video_id))
    db.commit()


def gep_eligible(db: Session, *, member_id: str) -> dict:
    """Single source of truth for the 'Keuntungan Mitra fully watched' Golden Elevate
    Pool eligibility gate the business owner specified. Only counts videos that are
    actually ready (have a youtube_id); if none are ready yet, eligible is False and
    that is reported honestly rather than defaulting to True."""
    data = course_overview(db, member_id=member_id, category="keuntungan_mitra")
    required = [v for v in data["videos"] if v.get("required_for_pool") and v["ready"]]
    watched_required = [v for v in required if v["watched"]]
    return {
        "eligible": len(required) > 0 and len(watched_required) == len(required),
        "required_total": len(required),
        "required_watched": len(watched_required),
    }
