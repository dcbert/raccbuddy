"""add_last_response_to_scheduled_jobs

Adds ``last_response`` column to the ``scheduled_jobs`` table so recurring
jobs can store the most recent LLM-generated response for context in
subsequent iterations.

Revision ID: e9f3a7b2c6d5
Revises: d8e5f2a1b3c4
Create Date: 2026-03-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9f3a7b2c6d5"
down_revision: Union[str, Sequence[str], None] = "d8e5f2a1b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_response column to scheduled_jobs."""
    op.add_column(
        "scheduled_jobs",
        sa.Column("last_response", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove last_response column from scheduled_jobs."""
    op.drop_column("scheduled_jobs", "last_response")
