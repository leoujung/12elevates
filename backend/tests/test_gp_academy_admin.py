"""v4 s.7: member cannot self-report videos; admin batch records 3 NEW unique videos."""
import uuid

from app.core.security import hash_password
from app.models.core import Member
from app.models.gold_pool import GpCycle
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)


def _seed_admin(client):
    session = client.app.state.session_factory()
    try:
        andi = session.query(Member).filter(Member.email == "andi@example.test").one()
        adm = session.query(Member).filter(Member.email == "seed-admin@example.test").first()
        if adm is None:
            adm = Member(id=str(uuid.uuid4()), organization_id=andi.organization_id,
                         email="seed-admin@example.test", display_name="Seed Admin", is_admin=True,
                         password_hash=hash_password("admin-pass-789"))
            session.add(adm)
            session.commit()
    finally:
        session.close()


def test_member_cannot_self_report_watched(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.post("/v1/courses/keuntungan_mitra/watched", headers=andi,
                    json={"owner_member_id": "member-andi", "youtube_video_id": "abc"})
    assert r.status_code == 403


def test_admin_batch_records_three_then_blocks_reuse(client):
    _seed_admin(client)
    session = client.app.state.session_factory()
    cyc = GpCycle(cycle_number=901, status="OPEN")
    session.add(cyc)
    session.commit()
    cid = cyc.id
    session.close()

    admin = login(client, "seed-admin@example.test", "admin-pass-789")
    ids = ["v1", "v2", "v3"]
    r = client.post("/v1/admin/gp/academy-batch", headers=admin,
                    json={"member_id": "member-andi", "cycle_id": cid, "video_ids": ids})
    assert r.status_code == 201, r.text
    assert len(r.json()["recorded"]) == 3

    again = client.post("/v1/admin/gp/academy-batch", headers=admin,
                        json={"member_id": "member-andi", "cycle_id": cid, "video_ids": ids})
    assert again.status_code == 422, again.text
