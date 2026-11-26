"""Member sponsor + registration channel (for future network features).

- sponsor_name: sponsor / upline name taken from the 4Life myshop link (nullable).
- sponsor_ref: 4Life sponsor or member ID from the myshop link (nullable).
- registration_channel: how the signed form was delivered: WA, EMAIL, or NULL (nullable).

All nullable so existing members are unaffected.
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5gp04sponsor"
down_revision = "c3e4gp03drawsettings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("members", sa.Column("sponsor_name", sa.String(200), nullable=True))
    op.add_column("members", sa.Column("sponsor_ref", sa.String(100), nullable=True))
    op.add_column("members", sa.Column("registration_channel", sa.String(10), nullable=True))


def downgrade():
    op.drop_column("members", "registration_channel")
    op.drop_column("members", "sponsor_ref")
    op.drop_column("members", "sponsor_name")
