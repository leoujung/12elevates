"""gold elevate pool phase 1b tables

Revision ID: a1c0gp01phase1b
Revises: f643e61a09bc
Create Date: 2026-11-23

Additive only. Creates gp_* tables. Does not alter any existing table.
Matches app/models/gold_pool.py (Spec v4.1 carry-forward and snapshot model).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c0gp01phase1b"
down_revision: Union[str, None] = "f643e61a09bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gp_cycles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_number"),
    )
    op.create_table(
        "gp_transactions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("owner_member_id", sa.String(36), nullable=False),
        sa.Column("tx_type", sa.String(24), nullable=False),
        sa.Column("lp", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("recorded_by", sa.String(36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_member_id"], ["members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index("ix_gp_transactions_owner_member_id", "gp_transactions", ["owner_member_id"])
    op.create_table(
        "gp_draw_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("cycle_id", sa.String(36), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("locked_by", sa.String(36), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cycle_id"], ["gp_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id"),
    )
    op.create_table(
        "gp_coupons",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("transaction_pk", sa.String(36), nullable=False),
        sa.Column("owner_member_id", sa.String(36), nullable=False),
        sa.Column("original_cycle_id", sa.String(36), nullable=False),
        sa.Column("lp_at_issue", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["transaction_pk"], ["gp_transactions.id"]),
        sa.ForeignKeyConstraint(["owner_member_id"], ["members.id"]),
        sa.ForeignKeyConstraint(["original_cycle_id"], ["gp_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_pk", name="uq_gp_coupon_one_per_transaction"),
    )
    op.create_index("ix_gp_coupons_owner_member_id", "gp_coupons", ["owner_member_id"])
    op.create_index("ix_gp_coupons_original_cycle_id", "gp_coupons", ["original_cycle_id"])
    op.create_index("ix_gp_coupons_status", "gp_coupons", ["status"])
    op.create_table(
        "gp_coupon_allocations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("coupon_id", sa.String(36), nullable=False),
        sa.Column("source_cycle_id", sa.String(36), nullable=True),
        sa.Column("target_cycle_id", sa.String(36), nullable=False),
        sa.Column("allocation_type", sa.String(16), nullable=False),
        sa.Column("eligibility_status", sa.String(32), nullable=False),
        sa.Column("reasons", sa.String(255), nullable=True),
        sa.Column("snapshot_id", sa.String(36), nullable=True),
        sa.Column("included_in_snapshot", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["coupon_id"], ["gp_coupons.id"]),
        sa.ForeignKeyConstraint(["source_cycle_id"], ["gp_cycles.id"]),
        sa.ForeignKeyConstraint(["target_cycle_id"], ["gp_cycles.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["gp_draw_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coupon_id", "target_cycle_id", name="uq_gp_alloc_coupon_target_cycle"),
    )
    op.create_index("ix_gp_coupon_allocations_coupon_id", "gp_coupon_allocations", ["coupon_id"])
    op.create_index("ix_gp_coupon_allocations_target_cycle_id", "gp_coupon_allocations", ["target_cycle_id"])
    op.create_table(
        "gp_academy_usage",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("member_id", sa.String(36), nullable=False),
        sa.Column("video_id", sa.String(64), nullable=False),
        sa.Column("cycle_id", sa.String(36), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.ForeignKeyConstraint(["cycle_id"], ["gp_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "video_id", name="uq_gp_academy_member_video"),
    )
    op.create_index("ix_gp_academy_usage_member_id", "gp_academy_usage", ["member_id"])
    op.create_index("ix_gp_academy_usage_cycle_id", "gp_academy_usage", ["cycle_id"])
    op.create_table(
        "gp_draws",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("cycle_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("winning_coupon_id", sa.String(36), nullable=False),
        sa.Column("winning_member_id", sa.String(36), nullable=False),
        sa.Column("winning_index", sa.Integer(), nullable=False),
        sa.Column("selection_method", sa.String(32), nullable=False),
        sa.Column("executed_by", sa.String(36), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cycle_id"], ["gp_cycles.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["gp_draw_snapshots.id"]),
        sa.ForeignKeyConstraint(["winning_coupon_id"], ["gp_coupons.id"]),
        sa.ForeignKeyConstraint(["winning_member_id"], ["members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id"),
        sa.UniqueConstraint("snapshot_id"),
    )
    op.create_table(
        "gp_draw_entries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("coupon_id", sa.String(36), nullable=False),
        sa.Column("member_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["gp_draw_snapshots.id"]),
        sa.ForeignKeyConstraint(["coupon_id"], ["gp_coupons.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "coupon_id", name="uq_gp_entry_snapshot_coupon"),
        sa.UniqueConstraint("snapshot_id", "position", name="uq_gp_entry_snapshot_position"),
    )
    op.create_index("ix_gp_draw_entries_snapshot_id", "gp_draw_entries", ["snapshot_id"])
    op.create_table(
        "gp_draw_participations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("member_id", sa.String(36), nullable=False),
        sa.Column("draw_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.ForeignKeyConstraint(["draw_id"], ["gp_draws.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "draw_id", name="uq_gp_participation_member_draw"),
    )
    op.create_index("ix_gp_draw_participations_member_id", "gp_draw_participations", ["member_id"])
    op.create_index("ix_gp_draw_participations_draw_id", "gp_draw_participations", ["draw_id"])
    op.create_table(
        "gp_winner_cooldowns",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("member_id", sa.String(36), nullable=False),
        sa.Column("draw_id", sa.String(36), nullable=False),
        sa.Column("excluded_cycle_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.ForeignKeyConstraint(["draw_id"], ["gp_draws.id"]),
        sa.ForeignKeyConstraint(["excluded_cycle_id"], ["gp_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draw_id"),
    )
    op.create_index("ix_gp_winner_cooldowns_member_id", "gp_winner_cooldowns", ["member_id"])
    op.create_table(
        "gp_prizes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("draw_id", sa.String(36), nullable=False),
        sa.Column("winner_member_id", sa.String(36), nullable=False),
        sa.Column("prize_status", sa.String(32), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["draw_id"], ["gp_draws.id"]),
        sa.ForeignKeyConstraint(["winner_member_id"], ["members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draw_id"),
    )
    op.create_table(
        "gp_audit_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Reverse dependency order. Drops only gp_* tables created above.
    op.drop_table("gp_audit_logs")
    op.drop_table("gp_prizes")
    op.drop_table("gp_winner_cooldowns")
    op.drop_table("gp_draw_participations")
    op.drop_table("gp_draw_entries")
    op.drop_table("gp_draws")
    op.drop_table("gp_academy_usage")
    op.drop_table("gp_coupon_allocations")
    op.drop_table("gp_coupons")
    op.drop_table("gp_draw_snapshots")
    op.drop_table("gp_transactions")
    op.drop_table("gp_cycles")
