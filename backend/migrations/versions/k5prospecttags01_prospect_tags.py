"""Migration k5prospecttags01: prospect interest tags (closed list, same as member tags).

Tags describe the prospect's BUSINESS interest category, chosen from a closed list.
Not free text (no health or sensitive data). Stored per prospect; upsert on re-submit.
"""
from alembic import op
import sqlalchemy as sa

revision = "k5prospecttags01"
down_revision = "k4l5targettags01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cp_prospect_tags",
        sa.Column("prospect_id", sa.String(36), nullable=False),
        sa.Column("member_id", sa.String(64), nullable=False),
        sa.Column("tag", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("prospect_id", "tag", name="cp_prospect_tags_pkey"),
        sa.CheckConstraint("length(tag) BETWEEN 1 AND 64", name="cp_prospect_tags_tag_len"),
    )
    op.create_index("ix_cp_prospect_tags_member", "cp_prospect_tags", ["member_id"])


def downgrade():
    op.drop_index("ix_cp_prospect_tags_member", table_name="cp_prospect_tags")
    op.drop_table("cp_prospect_tags")
