"""gold pool draw settings (single-row, default disabled)

Revision ID: c3e4gp03drawsettings
Revises: b2d1gp02phase3
"""
from alembic import op
import sqlalchemy as sa

revision = "c3e4gp03drawsettings"
down_revision = "b2d1gp02phase3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gp_draw_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("legal_review_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Jakarta"),
        sa.Column("zoom_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("gp_draw_settings")
