"""REST API for receiving messages from external platform bridges.

Exposes POST /api/messages so that Node.js / Go / etc. services
can push messages into the same pipeline as Telegram.

Authentication
--------------
When ``API_SECRET_KEY`` is set in the environment, every request to
``POST /api/messages`` must include the header::

    X-API-Key: <API_SECRET_KEY>

Requests without the correct key receive 401 Unauthorized.
Leave ``API_SECRET_KEY`` empty to disable auth (development only).
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from src.core.config import settings
from src.core.db.crud import save_message, upsert_contact

logger = logging.getLogger(__name__)

api = FastAPI(title="RaccBuddy Core API", version="0.1.0")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _verify_api_key(x_api_key: Optional[str]) -> None:
    """Raise HTTP 401 if the API key is configured but not provided / wrong.

    Args:
        x_api_key: Value of the ``X-API-Key`` request header.

    Raises:
        HTTPException: 401 when auth fails.
    """
    configured_key = settings.api_secret_key
    if not configured_key:
        # Auth is disabled — accept all requests (dev / LAN-only setups).
        return
    if x_api_key != configured_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-API-Key header.",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@api.get("/health")
async def health() -> dict[str, str]:
    """Simple liveness health-check endpoint."""
    return {"status": "ok"}


@api.post("/api/messages")
async def receive_message(
    msg: IncomingMessage,
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, str]:
    """Accept a message from an external bridge and persist it.

    The contact_handle is stored directly from the platform (e.g., phone
    number for WhatsApp, user_id for Telegram).  The contact is looked
    up/created to get its database ID, which is then used as a foreign key
    in the messages table.

    Args:
        msg: Incoming message payload from the bridge.
        x_api_key: Value of the ``X-API-Key`` header (injected by FastAPI).

    Returns:
        ``{"status": "ok"}`` on success.

    Raises:
        HTTPException: 401 on auth failure, 503 if owner not configured,
            500 on internal error.
    """
    _verify_api_key(x_api_key)

    try:
        # The canonical owner is the configured Telegram owner.
        # All external contacts are stored under this single owner.
        owner_id = settings.owner_telegram_id
        if not owner_id:
            raise HTTPException(
                status_code=503,
                detail=(
                    "OWNER_TELEGRAM_ID not configured — "
                    "run /start on Telegram first."
                ),
            )

        # Parse timestamp or fall back to now
        ts: datetime.datetime | None = None
        if msg.timestamp:
            try:
                ts = datetime.datetime.fromisoformat(msg.timestamp)
            except ValueError:
                ts = None

        # Determine if this message is from the owner
        is_owner_message = False
        if msg.platform == "whatsapp" and msg.from_me:
            is_owner_message = True
        elif msg.platform == "whatsapp" and settings.owner_whatsapp_number:
            if msg.from_id == settings.owner_whatsapp_number:
                is_owner_message = True

        # Upsert contact using the raw platform ID as the handle
        contact = await upsert_contact(
            owner_id=owner_id,
            contact_handle=msg.from_id,
            platform=msg.platform,
            contact_name=msg.contact_name or msg.from_id,
        )

        # Derive a stable positive int64 chat_id from the string chat_id
        chat_id_value = hash(msg.chat_id) & 0x7FFFFFFFFFFFFFFF

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

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to save incoming message from %s", msg.from_id)
        raise HTTPException(status_code=500, detail="Internal server error")
