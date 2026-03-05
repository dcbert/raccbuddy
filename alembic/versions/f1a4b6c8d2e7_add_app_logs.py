"""add_app_logs

Adds the ``app_logs`` table that persists WARNING-level-and-above log
records from the entire application so they can be queried, audited, and
triaged after the fact.

Revision ID: f1a4b6c8d2e7
Revises: e9f3a7b2c6d5
Create Date: 2026-03-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a4b6c8d2e7"
down_revision: Union[str, Sequence[str], None] = "e9f3a7b2c6d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the app_logs table."""
    op.create_table(
        "app_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("logger_name", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("module", sa.String(length=255), nullable=True),
        sa.Column("func_name", sa.String(length=255), nullable=True),
        sa.Column("line_no", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_logs_level"),
        "app_logs",
        ["level"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_logs_logger_name"),
        "app_logs",
        ["logger_name"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the app_logs table."""
    op.drop_index(op.f("ix_app_logs_logger_name"), table_name="app_logs")
    op.drop_index(op.f("ix_app_logs_level"), table_name="app_logs")
    op.drop_table("app_logs")
