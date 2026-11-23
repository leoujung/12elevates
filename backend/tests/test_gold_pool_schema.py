"""Phase 1b schema checks: ORM model and Alembic migration must describe the same gp_* tables."""
import re
from pathlib import Path

from app.models.core import Base
import app.models.gold_pool  # noqa: F401  (registers gp_* tables on Base.metadata)

MIGRATION = Path(__file__).resolve().parents[1] / "migrations/versions/a1c0gp01phase1b_gold_pool_tables.py"


def _gp_tables():
    return {name: t for name, t in Base.metadata.tables.items() if name.startswith("gp_")}


def test_twelve_gp_tables_in_model():
    assert len(_gp_tables()) == 12


def test_migration_creates_exactly_the_model_tables():
    src = MIGRATION.read_text(encoding="utf-8")
    created = set(re.findall(r'op\.create_table\(\s*"(gp_[a-z_]+)"', src))
    assert created == set(_gp_tables().keys())


def test_migration_drop_list_matches_create_list():
    src = MIGRATION.read_text(encoding="utf-8")
    created = set(re.findall(r'op\.create_table\(\s*"(gp_[a-z_]+)"', src))
    dropped = set(re.findall(r'op\.drop_table\("(gp_[a-z_]+)"\)', src))
    assert created == dropped


def test_model_unique_constraints_present_in_migration():
    src = MIGRATION.read_text(encoding="utf-8")
    for t in _gp_tables().values():
        for uc in t.constraints:
            if uc.__class__.__name__ == "UniqueConstraint" and uc.name:
                assert uc.name in src, f"{uc.name} on {t.name} missing from migration"


def test_one_coupon_per_transaction_constraint():
    cons = [c.name for c in _gp_tables()["gp_coupons"].constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert "uq_gp_coupon_one_per_transaction" in cons


def test_one_snapshot_and_one_draw_per_cycle():
    assert _gp_tables()["gp_draw_snapshots"].c.cycle_id.unique
    assert _gp_tables()["gp_draws"].c.cycle_id.unique


def test_participation_unique_member_draw():
    names = [c.name for c in _gp_tables()["gp_draw_participations"].constraints]
    assert "uq_gp_participation_member_draw" in names


def test_snapshot_entries_unique_position_and_coupon():
    names = [c.name for c in _gp_tables()["gp_draw_entries"].constraints]
    assert "uq_gp_entry_snapshot_coupon" in names and "uq_gp_entry_snapshot_position" in names
