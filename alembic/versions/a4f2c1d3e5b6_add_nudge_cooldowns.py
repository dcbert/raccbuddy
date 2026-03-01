"""add_nudge_cooldowns

Adds the ``nudge_cooldowns`` table that persists per-owner, per-skill
cooldown timestamps so they survive bot restarts.

Revision ID: a4f2c1d3e5b6
Revises: c617a5efbe23
Create Date: 2026-02-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4f2c1d3e5b6"
down_revision: Union[str, Sequence[str], None] = "c617a5efbe23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the nudge_cooldowns table."""
    op.create_table(
        "nudge_cooldowns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_name", sa.String(length=200), nullable=False),
        sa.Column(
            "last_fired_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "skill_name",
            name="uq_owner_skill_cooldown",
        ),
    )
    op.create_index(
        op.f("ix_nudge_cooldowns_owner_id"),
        "nudge_cooldowns",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the nudge_cooldowns table."""
    op.drop_index(
        op.f("ix_nudge_cooldowns_owner_id"),
        table_name="nudge_cooldowns",
    )
    op.drop_table("nudge_cooldowns")
