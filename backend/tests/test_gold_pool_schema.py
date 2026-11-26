"""Phase 1b schema checks: ORM model and Alembic migrations must describe the same gp_* tables."""
import re
from pathlib import Path

from app.models.core import Base
import app.models.gold_pool  # noqa: F401  (registers gp_* tables on Base.metadata)
import app.services.gold_pool_draw  # noqa: F401  (registers gp_draw_settings)

VERSIONS = Path(__file__).resolve().parents[1] / "migrations/versions"
MIGRATIONS = sorted(VERSIONS.glob("*gp0*.py"))  # all gold-pool migrations, incl. later phases


def _gp_tables():
    return {name: t for name, t in Base.metadata.tables.items() if name.startswith("gp_")}


def _migration_src():
    return "\n".join(p.read_text(encoding="utf-8") for p in MIGRATIONS)


def test_thirteen_gp_tables_in_model():
    assert len(_gp_tables()) == 13


def test_migration_creates_exactly_the_model_tables():
    created = set(re.findall(r'op\.create_table\(\s*"(gp_[a-z_]+)"', _migration_src()))
    assert created == set(_gp_tables().keys())


def test_migration_drop_list_matches_create_list():
    src = _migration_src()
    created = set(re.findall(r'op\.create_table\(\s*"(gp_[a-z_]+)"', src))
    dropped = set(re.findall(r'op\.drop_table\("(gp_[a-z_]+)"\)', src))
    assert created == dropped


def test_coupon_one_per_transaction_constraint_exists():
    cons = [c.name for c in _gp_tables()["gp_coupons"].constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert "uq_gp_coupon_one_per_transaction" in cons


def test_snapshot_and_draw_are_unique_per_cycle():
    assert _gp_tables()["gp_draw_snapshots"].c.cycle_id.unique
    assert _gp_tables()["gp_draws"].c.cycle_id.unique


def test_participation_unique_per_member_and_draw():
    names = [c.name for c in _gp_tables()["gp_draw_participations"].constraints]
    assert "uq_gp_participation_member_draw" in names


def test_entries_unique_per_snapshot_coupon_and_position():
    names = [c.name for c in _gp_tables()["gp_draw_entries"].constraints]
    assert "uq_gp_entry_snapshot_coupon" in names and "uq_gp_entry_snapshot_position" in names


def test_model_columns_match_migration_columns_exactly():
    """Guards against model/migration drift (a phantom column broke production in Phase 3)."""
    src = _migration_src()
    for name, table in _gp_tables().items():
        block = re.search(rf'op\.create_table\(\s*"{name}"(.*?)\n    \)\n', src, re.S)
        assert block, f"{name} not created by migration"
        mig_cols = set(re.findall(r'sa\.Column\("([a-z_]+)"', block.group(1)))
        model_cols = {c.name for c in table.columns}
        assert model_cols == mig_cols, f"{name}: model-only={model_cols - mig_cols}, migration-only={mig_cols - model_cols}"
