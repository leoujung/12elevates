"""Phase 3: members.is_admin role flag (additive, default false).

Revision ID: b2d1gp02phase3
Revises: a1c0gp01phase1b
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2d1gp02phase3"
down_revision: Union[str, None] = "a1c0gp01phase1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "members",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("members", "is_admin")
