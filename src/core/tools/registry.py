"""Tool definitions and executor for LLM function calling.

When an advanced provider (e.g. xAI) supports tools, it can autonomously
call these functions during a conversation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine

from src.core.skills.chat import collect_tool_schemas, dispatch_skill_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias for async tool handlers
# ---------------------------------------------------------------------------
ToolHandler = Callable[..., Coroutine[Any, Any, str]]

# ---------------------------------------------------------------------------
# OpenAI-compatible function schemas
# ---------------------------------------------------------------------------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_contact",
            "description": (
                "Run a relationship analysis for a specific contact. "
                "Returns a brief analysis of communication patterns, "
                "emotional tone, and suggestions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "The name of the contact to analyze.",
                    },
                },
                "required": ["contact_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_insights",
            "description": (
                "Get conversation insights for a contact: key topics, "
                "sentiment shifts, notable patterns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "The name of the contact.",
                    },
                },
                "required": ["contact_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_relationship_score",
            "description": (
                "Retrieve the current relationship score (0-100) for a contact."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "The name of the contact.",
                    },
                },
                "required": ["contact_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_contacts",
            "description": "List all known contacts across all platforms.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_contact",
            "description": (
                "Generate a daily conversation summary for a contact."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "The name of the contact to summarize.",
                    },
                },
                "required": ["contact_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_message",
            "description": (
                "Schedule a message to be sent to the user at a future time. "
                "Use this to set reminders, follow-up nudges, or scheduled "
                "check-ins. The message will be delivered via Telegram."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message text to send.",
                    },
                    "delay_minutes": {
                        "type": "integer",
                        "description": (
                            "Minutes from now to send the message. "
                            "E.g. 60 for 1 hour, 1440 for 1 day."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "Brief reason for scheduling (for logging)."
                        ),
                    },
                },
                "required": ["message", "delay_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_about_owner",
            "description": (
                "Save a new personal fact or preference about the owner to "
                "Raccy's long-term memory. Use this when the user shares "
                "something important about themselves — preferences, traits, "
                "goals, routines, emotions, or inside jokes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": (
                            "The fact to remember, e.g. 'Loves spicy ramen'."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "preference", "trait", "joke", "emotion",
                            "reflection", "fact", "goal", "routine",
                            "boundary",
                        ],
                        "description": "Category of the memory.",
                    },
                    "importance": {
                        "type": "integer",
                        "description": (
                            "Importance 1-10 (default 8). Higher = kept longer."
                        ),
                    },
                },
                "required": ["fact"],
            },
        },
    },
]


def get_all_tool_schemas() -> list[dict[str, Any]]:
    """Return built-in schemas merged with chat-skill-provided schemas."""
    return TOOL_SCHEMAS + collect_tool_schemas()


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------
async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    owner_id: int,
) -> str:
    """Execute a tool by name and return a result string for the LLM."""
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler:
        try:
            return await handler(owner_id=owner_id, **arguments)
        except Exception as exc:
            logger.exception("Tool '%s' failed", tool_name)
            return f"Error executing {tool_name}: {exc}"

    skill_result = await dispatch_skill_tool(tool_name, arguments, owner_id)
    if skill_result is not None:
        return skill_result

    return f"Error: unknown tool '{tool_name}'"


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------
async def _tool_analyze_contact(
    owner_id: int,
    contact_name: str,
) -> str:
    """Analyze relationship for a contact."""
    from src.core.db.crud import get_contact_by_name_any_platform, get_relationship
    from src.core.memory.context_builder import context_builder

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return f"Contact '{contact_name}' not found."

    ctx = await context_builder.build(
        owner_id,
        contact.id,
        f"Analyze my relationship with {contact_name}",
    )
    rel = await get_relationship(contact.id)
    score = rel.score if rel else 50
    return f"Context for {contact_name} (score {score}/100):\n{ctx}"


async def _tool_get_insights(
    owner_id: int,
    contact_name: str,
) -> str:
    """Get conversation insights for a contact."""
    from src.core.db.crud import get_contact_by_name_any_platform
    from src.core.memory.context_builder import context_builder

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return f"Contact '{contact_name}' not found."

    ctx = await context_builder.build(
        owner_id,
        contact.id,
        f"Insights about {contact_name}",
    )
    return f"Conversation context for {contact_name}:\n{ctx}"


async def _tool_get_relationship_score(
    owner_id: int,
    contact_name: str,
) -> str:
    """Get relationship score for a contact."""
    from src.core.db.crud import get_contact_by_name_any_platform, get_relationship

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return f"Contact '{contact_name}' not found."

    rel = await get_relationship(contact.id)
    score = rel.score if rel else 50
    return f"Relationship score with {contact_name}: {score}/100"


async def _tool_list_contacts(owner_id: int) -> str:
    """List all known contacts."""
    from src.core.db.crud import get_all_contacts_all_platforms

    contacts = await get_all_contacts_all_platforms(owner_id)
    if not contacts:
        return "No contacts found."

    lines = [f"• {c.contact_name} ({c.platform})" for c in contacts]
    return "Known contacts:\n" + "\n".join(lines)


async def _tool_summarize_contact(
    owner_id: int,
    contact_name: str,
) -> str:
    """Generate a daily summary for a contact."""
    from src.core.db.crud import get_contact_by_name_any_platform
    from src.summarizer import summarize_daily

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return f"Contact '{contact_name}' not found."

    result = await summarize_daily(contact.id)
    if result:
        return f"Summary for {contact_name}: {result}"
    return f"No new messages to summarize for {contact_name} today."


async def _tool_schedule_message(
    owner_id: int,
    message: str,
    delay_minutes: int,
    reason: str = "",
) -> str:
    """Schedule a message for future delivery."""
    from src.core.scheduled.jobs import schedule_llm_job

    job_id = await schedule_llm_job(
        owner_id=owner_id,
        message=message,
        delay_minutes=delay_minutes,
        reason=reason,
    )
    hours = delay_minutes // 60
    mins = delay_minutes % 60
    time_str = ""
    if hours:
        time_str += f"{hours}h"
    if mins:
        time_str += f"{mins}m"
    return f"Scheduled message (job {job_id}) to be sent in {time_str}."


async def _tool_remember_about_owner(
    owner_id: int,
    fact: str,
    category: str = "fact",
    importance: int = 8,
) -> str:
    """Save a personal fact about the owner to Raccy's self-memory."""
    from src.core.memory.base import memory

    mem = await memory.add_owner_memory(
        owner_id,
        fact,
        importance=min(max(importance, 1), 10),
        category=category,
        metadata={"source": "llm_tool"},
    )
    return (
        f'Remembered: "{fact}" (category={category}, '
        f"importance={mem.importance}). I'll keep this in mind! 🦝"
    )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------
_TOOL_HANDLERS: dict[str, ToolHandler] = {
    "analyze_contact": _tool_analyze_contact,
    "get_insights": _tool_get_insights,
    "get_relationship_score": _tool_get_relationship_score,
    "list_contacts": _tool_list_contacts,
    "summarize_contact": _tool_summarize_contact,
    "schedule_message": _tool_schedule_message,
    "remember_about_owner": _tool_remember_about_owner,
}


def parse_tool_arguments(raw: str | dict[str, Any]) -> dict[str, Any]:
    """Safely parse tool arguments from the model response."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse tool arguments: %s", raw)
        return {}
