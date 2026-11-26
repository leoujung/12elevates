"""Member referral codes (additive table, no change to members).

Revision ID: h1i2refcodes01
Revises: g0h1merge01heads
"""
from alembic import op
import sqlalchemy as sa

revision = "h1i2refcodes01"
down_revision = "g0h1merge01heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_referral_codes",
        sa.Column("code", sa.String(40), primary_key=True),
        sa.Column("member_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("member_referral_codes")
