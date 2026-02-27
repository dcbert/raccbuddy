"""Handler for the /start command."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.core.config import settings

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "Hey {name}! 🦝\n\n"
    "I'm Raccy — your personal raccoon buddy.\n\n"
    "I'll learn from your chats, track relationships with your contacts, "
    "spot habits (good and sneaky ones), and nudge you "
    "when life needs a little push.\n\n"
    "Everything stays local. Your data never leaves your machine. 🔒\n\n"
    "📌 Your Telegram ID: {user_id}\n"
    "Set OWNER_TELEGRAM_ID={user_id} in your .env to lock this bot to you.\n\n"
    "Forward me messages from other chats, then:\n"
    "/name <Name> — label the forwarded contact\n"
    "/analyze <Name> — relationship analysis\n"
    "/insights <Name> — conversation insights\n"
    "/relationship <Name> — relationship score\n"
    "/contacts — list all contacts (all platforms)\n"
    "/skills — list active chat & nudge skills\n\n"
    "Or just chat with me naturally — I know all your contacts! 💪"
)

WELCOME_TEXT_CONFIGURED = (
    "Hey {name}! 🦝\n\n"
    "Welcome back! Your instance is locked to your account. 🔒\n\n"
    "Forward me messages from other chats, then:\n"
    "/name <Name> — label the forwarded contact\n"
    "/analyze <Name> — relationship analysis\n"
    "/insights <Name> — conversation insights\n"
    "/relationship <Name> — relationship score\n"
    "/contacts — list all contacts (all platforms)\n"
    "/skills — list active chat & nudge skills\n\n"
    "Or just chat with me naturally — I know all your contacts! 💪"
)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user with Raccy's intro message.

    If the bot is locked to an owner and someone else tries to /start,
    they receive an access-denied response.

    Args:
        update: The incoming Telegram update.
        context: The PTB context (unused here).
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    name = update.effective_user.first_name or "friend"

    if settings.owner_telegram_id and user_id != settings.owner_telegram_id:
        await update.message.reply_text(
            "🔒 This is a private RaccBuddy instance. Access denied."
        )
        return

    if settings.owner_telegram_id:
        await update.message.reply_text(WELCOME_TEXT_CONFIGURED.format(name=name))
    else:
        await update.message.reply_text(
            WELCOME_TEXT.format(name=name, user_id=user_id),
        )

    logger.info("User %d started the bot", user_id)
