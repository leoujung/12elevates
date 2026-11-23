"""Persistent global suppression list (UU PDP opt-out). Replaces the in-memory Set in Vercel.

- One row per normalised identifier (digits for WhatsApp, lowercase for email). Unique.
- Written by the opt-out endpoint, read by the intake forms before any processing.
- Survives restarts and is shared by all instances (it lives in PostgreSQL).
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6gp05suppression"
down_revision = "d4e5gp04sponsor"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "suppression_list",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identifier", sa.String(320), nullable=False, unique=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("suppression_list")
