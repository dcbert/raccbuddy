"""Owner authentication for single-user RaccBuddy instance."""

from __future__ import annotations

import logging

from telegram import Update

from src.core.config import settings

logger = logging.getLogger(__name__)

_NOT_OWNER_MSG = "🔒 This is a private RaccBuddy instance. Access denied."


def is_owner(user_id: int) -> bool:
    """Check whether *user_id* matches the configured owner.

    Returns ``True`` if no owner is configured yet (setup mode).
    """
    if not settings.owner_telegram_id:
        return True
    return user_id == settings.owner_telegram_id


async def reject_non_owner(update: Update) -> bool:
    """Send a rejection message if the user is not the owner.

    Returns ``True`` (= rejected) when the user is NOT the owner,
    ``False`` when the user IS the owner and may proceed.
    """
    if not update.effective_user:
        return True

    if is_owner(update.effective_user.id):
        return False

    logger.warning(
        "Unauthorized access attempt by user %d", update.effective_user.id,
    )
    if update.message:
        await update.message.reply_text(_NOT_OWNER_MSG)
    return True
