"""Initial schema: consents and checkins tables

Revision ID: 001
Revises:
Create Date: 2025-10-14

"""

import sqlalchemy as sa

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("terms_version", sa.String(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("adherence", sa.Integer(), nullable=False),
        sa.Column("mood_trend", sa.Integer(), nullable=False),
        sa.Column("cravings", sa.Integer(), nullable=False),
        sa.Column("sleep_hours", sa.Float(), nullable=False),
        sa.Column("isolation", sa.Integer(), nullable=False),
        sa.Column("ts", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_checkins_user_id", "checkins", ["user_id"])
    op.create_index("ix_checkins_ts", "checkins", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_checkins_ts", table_name="checkins")
    op.drop_index("ix_checkins_user_id", table_name="checkins")
    op.drop_table("checkins")
    op.drop_table("consents")
