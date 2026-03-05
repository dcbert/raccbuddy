"""add_recurrence_to_scheduled_jobs

Adds recurrence columns to the ``scheduled_jobs`` table so jobs can
repeat on daily, weekly, or cron schedules.

Revision ID: d8e5f2a1b3c4
Revises: b7d3e2f4a8c1
Create Date: 2026-03-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8e5f2a1b3c4"
down_revision: Union[str, Sequence[str], None] = "b7d3e2f4a8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add recurrence columns to scheduled_jobs."""
    op.add_column(
        "scheduled_jobs",
        sa.Column("recurrence_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "scheduled_jobs",
        sa.Column("recurrence_rule", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "scheduled_jobs",
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scheduled_jobs",
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scheduled_jobs",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    """Remove recurrence columns from scheduled_jobs."""
    op.drop_column("scheduled_jobs", "is_active")
    op.drop_column("scheduled_jobs", "last_executed_at")
    op.drop_column("scheduled_jobs", "next_fire_at")
    op.drop_column("scheduled_jobs", "recurrence_rule")
    op.drop_column("scheduled_jobs", "recurrence_type")
