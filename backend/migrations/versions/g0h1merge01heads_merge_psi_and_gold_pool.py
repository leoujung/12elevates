"""merge PSI hardening and gold pool/suppression heads (no schema change)

Revision ID: g0h1merge01heads
Revises: b8c9psi03hardening, e5f6gp05suppression
Create Date: 2026-11-26

Two Alembic branches existed (PSI ingestion chain and gold pool chain).
This empty revision joins them so `alembic upgrade head` has a single head.
It performs no DDL.
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "g0h1merge01heads"
down_revision = ("b8c9psi03hardening", "e5f6gp05suppression")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
