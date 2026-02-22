"""REST API for receiving messages from external platform bridges.

Exposes POST /api/messages so that Node.js / Go / etc. services
can push messages into the same pipeline as Telegram.
"""

import datetime
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.config import settings
from src.core.db.crud import save_message, upsert_contact

logger = logging.getLogger(__name__)

api = FastAPI(title="RaccBuddy Core API", version="0.1.0")


class IncomingMessage(BaseModel):
    """Schema for messages arriving from external bridges (WhatsApp, etc.)."""

    platform: str
    chat_id: str
    from_id: str
    contact_name: Optional[str] = None
    text: str
    timestamp: Optional[str] = None
    is_group: Optional[bool] = False
    group_name: Optional[str] = None
    from_me: Optional[bool] = False  # True if message is from the owner


@api.get("/health")
async def health() -> dict[str, str]:
    """Simple health-check endpoint."""
    return {"status": "ok"}


@api.post("/api/messages")
async def receive_message(msg: IncomingMessage) -> dict[str, str]:
    """Accept a message from an external bridge and persist it.

    The contact_handle is stored directly from the platform (e.g., phone number
    for WhatsApp, user_id for Telegram). The contact is looked up/created to get
    its database ID, which is then used as a foreign key in the messages table.
    """
    try:
        # The canonical owner is the configured Telegram owner.
        # All external contacts are stored under this single owner.
        owner_id = settings.owner_telegram_id
        if not owner_id:
            raise HTTPException(
                status_code=503,
                detail="OWNER_TELEGRAM_ID not configured — run /start on Telegram first",
            )

        # Parse timestamp or use now
        ts: datetime.datetime | None = None
        if msg.timestamp:
            try:
                ts = datetime.datetime.fromisoformat(msg.timestamp)
            except ValueError:
                ts = None

        # Check if this message is from the owner on WhatsApp
        is_owner_message = False
        if msg.platform == "whatsapp" and msg.from_me:
            # Outgoing WhatsApp message from owner - from_id is the recipient
            is_owner_message = True
        elif msg.platform == "whatsapp" and settings.owner_whatsapp_number:
            # Check if incoming message is from owner's WhatsApp number
            if msg.from_id == settings.owner_whatsapp_number:
                is_owner_message = True

        # Upsert contact using the raw platform ID as the handle
        # For owner's outgoing messages, from_id is the recipient
        contact = await upsert_contact(
            owner_id=owner_id,
            contact_handle=msg.from_id,
            platform=msg.platform,
            contact_name=msg.contact_name or msg.from_id,
        )

        # For chat_id, we'll use a simple hash for now to maintain BigInteger compatibility
        # This keeps group chat IDs distinct from contact IDs
        chat_id_value = hash(msg.chat_id) & 0x7FFFFFFFFFFFFFFF  # Positive int64

        # Persist the message with the contact's database ID
        await save_message(
            platform=msg.platform,
            chat_id=chat_id_value,
            from_contact_id=contact.id,
            text_content=msg.text,
            timestamp=ts,
        )

        logger.info(
            "Saved %s message %s %s%s (handle: %s)",
            msg.platform,
            "to" if msg.from_me else "from",
            msg.contact_name or msg.from_id,
            " [OWNER]" if is_owner_message else "",
            msg.from_id,
        )
        return {"status": "ok"}

    except Exception as e:
        logger.exception("Failed to save incoming message: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
