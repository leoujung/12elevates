"""Member target tags: member declares their own target tags from a CLOSED list.

Closed list on purpose: free text can carry health or sensitive detail (see the
'declared_needs_goals' rule). Tags are business-interest categories only.
"""
from sqlalchemy import text

# CLOSED list of business-interest categories a member may target. PROPOSED — needs Leo's approval.
# Deliberately no health, wellness-condition or personal-data categories.
ALLOWED_TAGS = frozenset({
    "business-coach",
    "executive-coach",
    "personal-branding-coach",
    "consultant",
    "business-owner",
    "online-course-creator",
    "agency-owner",
    "service-business",
    "startup",
    "real-estate",
    "ecommerce",
    "local-business",
})

MAX_TAGS = 10


def get_tags(db, member_id: str) -> list[str]:
    rows = db.execute(
        text("select tag from member_target_tags where member_id = :m order by tag"),
        {"m": member_id},
    ).all()
    return [r[0] for r in rows]


def set_tags(db, member_id: str, tags: list[str]) -> list[str]:
    """Replace the member's tags. Validates against ALLOWED_TAGS, max MAX_TAGS, de-duplicated."""
    clean = sorted({t.strip().lower() for t in tags if t and t.strip()})
    unknown = [t for t in clean if t not in ALLOWED_TAGS]
    if unknown:
        raise ValueError("unknown_tag")
    if len(clean) > MAX_TAGS:
        raise ValueError("too_many_tags")
    db.execute(text("delete from member_target_tags where member_id = :m"), {"m": member_id})
    for t in clean:
        db.execute(
            text("insert into member_target_tags (member_id, tag, created_at) values (:m, :t, now())"),
            {"m": member_id, "t": t},
        )
    return clean
