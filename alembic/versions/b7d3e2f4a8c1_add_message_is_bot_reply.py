"""add_message_is_bot_reply

Adds ``is_bot_reply`` boolean column to the ``messages`` table so
RaccBuddy can distinguish its own replies from user messages, enabling
proper multi-turn conversation history.

Revision ID: b7d3e2f4a8c1
Revises: a4f2c1d3e5b6
Create Date: 2026-02-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3e2f4a8c1"
down_revision: Union[str, Sequence[str], None] = "a4f2c1d3e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_bot_reply column to messages table."""
    op.add_column(
        "messages",
        sa.Column(
            "is_bot_reply",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Remove is_bot_reply column from messages table."""
    op.drop_column("messages", "is_bot_reply")
