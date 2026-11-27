"""Alembic: member_target_tags (member-declared business-interest tags, closed list enforced in app).

Revision k4l5targettags01 on top of j3k4cpschema01.
Table is mutable on purpose (member can change tags). Not append-only.
"""
from alembic import op
import sqlalchemy as sa

revision = "k4l5targettags01"
down_revision = "j3k4cpschema01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "member_target_tags",
        sa.Column("member_id", sa.String(64), nullable=False),
        sa.Column("tag", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("member_id", "tag", name="member_target_tags_pkey"),
        sa.CheckConstraint("length(tag) BETWEEN 1 AND 64", name="member_target_tags_tag_len"),
    )
    op.create_index("ix_member_target_tags_member", "member_target_tags", ["member_id"])


def downgrade():
    op.drop_index("ix_member_target_tags_member", table_name="member_target_tags")
    op.drop_table("member_target_tags")
