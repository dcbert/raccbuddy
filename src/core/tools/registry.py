"""Tool definitions and executor for LLM function calling.

Every tool returns **structured JSON** (via ``src.core.tools.response``
helpers) so that reasoning models can detect completion and stop looping.

Key guarantees:
- ``status`` in every response: ``success | already_exists | error | invalid_input``
- ``final_instruction`` on terminal responses forces the agent to stop.
- Idempotency: stateful tools (schedule, remember) check for duplicates.
- Input validation: invalid arguments yield ``invalid_input`` immediately.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine

from src.core.skills.chat import collect_tool_schemas, dispatch_skill_tool
from src.core.tools.response import (
    tool_already_exists,
    tool_error,
    tool_invalid_input,
    tool_success,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias for async tool handlers
# ---------------------------------------------------------------------------
ToolHandler = Callable[..., Coroutine[Any, Any, str]]

# ---------------------------------------------------------------------------
# OpenAI-compatible function schemas
#
# Each description mentions:
#   • what the tool does
#   • when to use it
#   • that it returns structured JSON with status/action/message
#   • idempotency semantics where applicable
# ---------------------------------------------------------------------------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_contact",
            "description": (
                "Run a relationship analysis for a specific contact. "
                "Returns structured JSON with communication patterns, "
                "emotional tone, relationship score, and suggestions. "
                "Response contains 'status', 'action', 'message', and "
                "'final_instruction'. On success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": (
                            "The name of the contact to analyze. "
                            "Must be a non-empty string."
                        ),
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
                "sentiment shifts, notable patterns. Returns structured "
                "JSON with 'status', 'action', 'context', and "
                "'final_instruction'. On success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": ("The name of the contact. Must be non-empty."),
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
                "Retrieve the current relationship score (0-100) for a "
                "contact. Returns structured JSON with 'status', 'score', "
                "and 'final_instruction'. On success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": ("The name of the contact. Must be non-empty."),
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
            "description": (
                "List all known contacts across all platforms. Returns "
                "structured JSON with 'status', 'contacts' array, and "
                "'final_instruction'. On success, stop calling tools."
            ),
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
                "Generate a daily conversation summary for a contact. "
                "Returns structured JSON with 'status', 'summary', and "
                "'final_instruction'. On success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": (
                            "The name of the contact to summarize. "
                            "Must be non-empty."
                        ),
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
                "Schedule a one-time message or reminder to be sent to the "
                "user at a future time. Use this whenever the user says "
                "things like 'remind me', 'tell me later', 'in X minutes', "
                "'in X hours', 'tomorrow', 'ping me', 'follow up', "
                "'check back', 'notify me', or any request that implies a "
                "delayed action. IDEMPOTENT: if an identical reminder "
                "already exists, returns 'already_exists' without creating "
                "a duplicate. Returns structured JSON with 'status', "
                "'job_id', 'delay', and 'final_instruction'. "
                "When status is 'success' or 'already_exists', the task "
                "is 100% complete — do NOT call any tool again. "
                "Common conversions: 1 hour = 60, 2 hours = 120, "
                "1 day = 1440, 1 week = 10080."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": (
                            "A detailed, actionable instruction that will be "
                            "executed at delivery time. Write it as a clear "
                            "task prompt the LLM can act on autonomously. "
                            "Must be non-empty. Examples: "
                            "'Remind the user to take their medication.', "
                            "'Search the latest news about X and summarise "
                            "the key updates for the user.'"
                        ),
                    },
                    "delay_minutes": {
                        "type": "integer",
                        "description": (
                            "How many minutes from now to deliver the message. "
                            "Must be >= 1. "
                            "Examples: 5 = 5 min, 60 = 1 hour, 1440 = 1 day."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "A detailed description of WHY this job was "
                            "scheduled and WHAT it should accomplish. This "
                            "context is included when the job fires so the "
                            "LLM understands the background. Always fill "
                            "this in."
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
            "name": "schedule_recurring_message",
            "description": (
                "Schedule a message that repeats on a regular schedule. "
                "Use this whenever the user says 'every day', 'every "
                "morning', 'every Monday', 'weekly', 'daily', 'each "
                "weekday', 'regularly', 'on a schedule', 'every X hours'. "
                "IDEMPOTENT: if an identical recurring job already exists, "
                "returns 'already_exists' without duplicating. Returns "
                "structured JSON with 'status', 'job_id', 'recurrence', "
                "and 'final_instruction'. When status is 'success' or "
                "'already_exists', the task is 100% complete — do NOT "
                "call any tool again."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": (
                            "A detailed, actionable instruction executed at "
                            "each occurrence. Must be non-empty. Examples: "
                            "'Check the weather forecast for Rome and suggest "
                            "what to wear today.', "
                            "'Give the user a motivational morning message.'"
                        ),
                    },
                    "recurrence_type": {
                        "type": "string",
                        "enum": ["daily", "weekly", "cron"],
                        "description": (
                            "Type of recurrence. 'daily' for every-day "
                            "schedules, 'weekly' for specific days, 'cron' "
                            "for advanced schedules."
                        ),
                    },
                    "recurrence_rule": {
                        "type": "string",
                        "description": (
                            "The schedule rule. Must be non-empty. Format:\n"
                            "• daily: 'HH:MM' (24h). E.g. '09:00'.\n"
                            "• weekly: 'HH:MM|day1,day2,...'. E.g. "
                            "'09:00|mon,wed,fri'.\n"
                            "• cron: 5-field cron expression. E.g. "
                            "'0 9 * * 1-5'."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "A detailed description of WHY this recurring "
                            "job was created. Always fill this in."
                        ),
                    },
                },
                "required": ["message", "recurrence_type", "recurrence_rule"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_jobs",
            "description": (
                "List all pending one-shot and active recurring scheduled "
                "jobs for the user. Returns structured JSON with 'status', "
                "'jobs' array, and 'final_instruction'. Call this BEFORE "
                "cancel_scheduled_job to get the correct job_id. On "
                "success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_job",
            "description": (
                "Cancel a scheduled or recurring job by its job ID. "
                "IMPORTANT: call list_scheduled_jobs first to get the "
                "correct job_id. Returns structured JSON with 'status' "
                "and 'final_instruction'. On success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": (
                            "The exact job ID string (e.g. 'a1b2c3d4') "
                            "obtained from list_scheduled_jobs. Must be "
                            "non-empty. Never guess — always look it up."
                        ),
                    },
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo for current events, news, "
                "facts, weather, or real-time information. Returns "
                "structured JSON with 'status', 'results' array, and "
                "'final_instruction'. On success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": ("The search query. Must be non-empty."),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": (
                            "Maximum number of results to return "
                            "(default 8, max 20)."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_webpage",
            "description": (
                "Fetch and read the content of a web page. Use when the "
                "user shares a URL or you need to read an article. Returns "
                "structured JSON with 'status', 'content', and "
                "'final_instruction'. On success, stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": (
                            "The full URL of the web page to read. Must "
                            "start with http:// or https://."
                        ),
                    },
                    "max_length": {
                        "type": "integer",
                        "description": (
                            "Maximum characters of page text to return "
                            "(default 4000, max 10000)."
                        ),
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_about_owner",
            "description": (
                "Save a personal fact or preference about the owner to "
                "Raccy's long-term memory. IDEMPOTENT: semantically "
                "similar facts are merged automatically instead of "
                "duplicated. Returns structured JSON with 'status', "
                "'fact', 'category', and 'final_instruction'. On success, "
                "stop calling tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": (
                            "The fact to remember. Must be non-empty. "
                            "E.g. 'Loves spicy ramen'."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "preference",
                            "trait",
                            "joke",
                            "emotion",
                            "reflection",
                            "fact",
                            "goal",
                            "routine",
                            "boundary",
                        ],
                        "description": "Category of the memory.",
                    },
                    "importance": {
                        "type": "integer",
                        "description": (
                            "Importance 1-10 (default 8). Higher = kept " "longer."
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
    """Execute a tool by name and return a structured JSON string.

    Wraps all exceptions in structured error JSON so the LLM never sees
    raw tracebacks or unstructured text.
    """
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler:
        try:
            return await handler(owner_id=owner_id, **arguments)
        except Exception as exc:
            logger.exception("Tool '%s' failed", tool_name)
            return tool_error(
                action=f"{tool_name}_failed",
                message=f"Tool '{tool_name}' encountered an internal error.",
                error_code="tool_execution_error",
                suggestion="Retry with different parameters or inform the user.",
                tool_name=tool_name,
                exception=str(exc),
            )

    # Try chat skills
    skill_result = await dispatch_skill_tool(tool_name, arguments, owner_id)
    if skill_result is not None:
        return skill_result

    return tool_error(
        action="tool_not_found",
        message=f"Unknown tool '{tool_name}'.",
        error_code="unknown_tool",
        suggestion=(
            "Check available tools and use one of them. " "Do not invent tool names."
        ),
        tool_name=tool_name,
    )


# ---------------------------------------------------------------------------
# Input-validation helpers
# ---------------------------------------------------------------------------


def _validate_non_empty_string(
    value: Any,
    field_name: str,
    action: str,
) -> str | None:
    """Return a ``tool_invalid_input`` JSON string if *value* is empty/missing.

    Returns ``None`` when validation passes.
    """
    if not value or not isinstance(value, str) or not value.strip():
        return tool_invalid_input(
            action=action,
            message=f"'{field_name}' is required and must be a non-empty string.",
            error_code="missing_required_field",
            suggestion=f"Provide a valid '{field_name}' and try again.",
        )
    return None


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------


async def _tool_analyze_contact(
    owner_id: int,
    contact_name: str = "",
) -> str:
    """Analyze relationship for a contact."""
    err = _validate_non_empty_string(contact_name, "contact_name", "analyze_contact")
    if err:
        return err

    from src.core.db.crud import get_contact_by_name_any_platform, get_relationship
    from src.core.memory.context_builder import context_builder

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return tool_error(
            action="analyze_contact",
            message=f"Contact '{contact_name}' not found.",
            error_code="contact_not_found",
            suggestion="Use list_contacts to see available contacts.",
        )

    ctx = await context_builder.build(
        owner_id,
        contact.id,
        f"Analyze my relationship with {contact_name}",
    )
    rel = await get_relationship(contact.id)
    score = rel.score if rel else 50

    return tool_success(
        action="contact_analyzed",
        message=f"Relationship analysis for {contact_name} complete.",
        contact_name=contact_name,
        relationship_score=score,
        context=ctx,
    )


async def _tool_get_insights(
    owner_id: int,
    contact_name: str = "",
) -> str:
    """Get conversation insights for a contact."""
    err = _validate_non_empty_string(contact_name, "contact_name", "get_insights")
    if err:
        return err

    from src.core.db.crud import get_contact_by_name_any_platform
    from src.core.memory.context_builder import context_builder

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return tool_error(
            action="get_insights",
            message=f"Contact '{contact_name}' not found.",
            error_code="contact_not_found",
            suggestion="Use list_contacts to see available contacts.",
        )

    ctx = await context_builder.build(
        owner_id,
        contact.id,
        f"Insights about {contact_name}",
    )

    return tool_success(
        action="insights_retrieved",
        message=f"Conversation insights for {contact_name} retrieved.",
        contact_name=contact_name,
        context=ctx,
    )


async def _tool_get_relationship_score(
    owner_id: int,
    contact_name: str = "",
) -> str:
    """Get relationship score for a contact."""
    err = _validate_non_empty_string(
        contact_name, "contact_name", "get_relationship_score"
    )
    if err:
        return err

    from src.core.db.crud import get_contact_by_name_any_platform, get_relationship

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return tool_error(
            action="get_relationship_score",
            message=f"Contact '{contact_name}' not found.",
            error_code="contact_not_found",
            suggestion="Use list_contacts to see available contacts.",
        )

    rel = await get_relationship(contact.id)
    score = rel.score if rel else 50

    return tool_success(
        action="score_retrieved",
        message=f"Relationship score with {contact_name}: {score}/100.",
        contact_name=contact_name,
        score=score,
    )


async def _tool_list_contacts(owner_id: int) -> str:
    """List all known contacts."""
    from src.core.db.crud import get_all_contacts_all_platforms

    contacts = await get_all_contacts_all_platforms(owner_id)

    contact_list = [{"name": c.contact_name, "platform": c.platform} for c in contacts]

    return tool_success(
        action="contacts_listed",
        message=(
            f"Found {len(contact_list)} contact(s)."
            if contact_list
            else "No contacts found."
        ),
        contacts=contact_list,
        total=len(contact_list),
    )


async def _tool_summarize_contact(
    owner_id: int,
    contact_name: str = "",
) -> str:
    """Generate a daily summary for a contact."""
    err = _validate_non_empty_string(contact_name, "contact_name", "summarize_contact")
    if err:
        return err

    from src.core.db.crud import get_contact_by_name_any_platform
    from src.summarizer import summarize_daily

    contact = await get_contact_by_name_any_platform(owner_id, contact_name)
    if not contact:
        return tool_error(
            action="summarize_contact",
            message=f"Contact '{contact_name}' not found.",
            error_code="contact_not_found",
            suggestion="Use list_contacts to see available contacts.",
        )

    result = await summarize_daily(contact.id)

    if result:
        return tool_success(
            action="contact_summarized",
            message=f"Daily summary for {contact_name} generated.",
            contact_name=contact_name,
            summary=result,
        )

    return tool_success(
        action="contact_summarized",
        message=f"No new messages to summarize for {contact_name} today.",
        contact_name=contact_name,
        summary=None,
    )


async def _tool_schedule_message(
    owner_id: int,
    message: str = "",
    delay_minutes: int = 0,
    reason: str = "",
) -> str:
    """Schedule a one-shot message for future delivery."""
    # --- Input validation ---
    err = _validate_non_empty_string(message, "message", "schedule_message")
    if err:
        return err

    if not isinstance(delay_minutes, int) or delay_minutes < 1:
        return tool_invalid_input(
            action="schedule_message",
            message="'delay_minutes' must be an integer >= 1.",
            error_code="invalid_delay",
            suggestion="Provide delay_minutes as a positive integer (e.g. 60 for 1 hour).",
        )

    from src.core.scheduled.jobs import schedule_llm_job

    result = await schedule_llm_job(
        owner_id=owner_id,
        message=message,
        delay_minutes=delay_minutes,
        reason=reason,
    )

    hours = delay_minutes // 60
    mins = delay_minutes % 60
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    delay_str = "".join(parts) or "<1m"

    if result.is_duplicate:
        return tool_already_exists(
            action="job_already_scheduled",
            message=(
                f"An identical reminder already exists (job {result.job_id}). "
                "No duplicate created."
            ),
            job_id=result.job_id,
            delay=delay_str,
        )

    return tool_success(
        action="job_scheduled",
        message=f"Reminder scheduled (job {result.job_id}) — fires in {delay_str}.",
        job_id=result.job_id,
        delay=delay_str,
        delay_minutes=delay_minutes,
    )


async def _tool_schedule_recurring_message(
    owner_id: int,
    message: str = "",
    recurrence_type: str = "",
    recurrence_rule: str = "",
    reason: str = "",
) -> str:
    """Schedule a recurring message."""
    # --- Input validation ---
    err = _validate_non_empty_string(message, "message", "schedule_recurring_message")
    if err:
        return err

    valid_types = {"daily", "weekly", "cron"}
    if recurrence_type not in valid_types:
        return tool_invalid_input(
            action="schedule_recurring_message",
            message=(
                f"Invalid recurrence_type '{recurrence_type}'. "
                f"Must be one of: {', '.join(sorted(valid_types))}."
            ),
            error_code="invalid_recurrence_type",
            suggestion="Use 'daily', 'weekly', or 'cron'.",
        )

    err = _validate_non_empty_string(
        recurrence_rule, "recurrence_rule", "schedule_recurring_message"
    )
    if err:
        return err

    from src.core.scheduled.jobs import schedule_recurring_job

    try:
        result = await schedule_recurring_job(
            owner_id=owner_id,
            message=message,
            recurrence_type=recurrence_type,
            recurrence_rule=recurrence_rule,
            reason=reason,
        )
    except ValueError as exc:
        return tool_invalid_input(
            action="schedule_recurring_message",
            message=str(exc),
            error_code="invalid_recurrence_rule",
            suggestion="Check the recurrence_rule format for the chosen type.",
        )

    recurrence_str = f"{recurrence_type}: {recurrence_rule}"

    if result.is_duplicate:
        return tool_already_exists(
            action="recurring_job_already_exists",
            message=(
                f"An identical recurring job already exists (job {result.job_id}). "
                "No duplicate created."
            ),
            job_id=result.job_id,
            recurrence=recurrence_str,
        )

    return tool_success(
        action="recurring_job_scheduled",
        message=f"Recurring job {result.job_id} created ({recurrence_str}).",
        job_id=result.job_id,
        recurrence=recurrence_str,
    )


async def _tool_list_scheduled_jobs(owner_id: int) -> str:
    """List all pending/active scheduled jobs."""
    from src.core.scheduled.jobs import get_pending_jobs

    jobs = await get_pending_jobs(owner_id)

    job_list: list[dict[str, Any]] = []
    for j in jobs:
        entry: dict[str, Any] = {
            "job_id": j["job_id"],
            "type": j.get("type", "unknown"),
            "message": j["message"][:120],
        }
        if j.get("type") == "recurring":
            entry["recurrence_type"] = j.get("recurrence_type")
            entry["recurrence_rule"] = j.get("recurrence_rule")
            entry["next_fire_at"] = j.get("next_fire_at")
        else:
            entry["fire_at"] = j.get("fire_at")
        job_list.append(entry)

    return tool_success(
        action="jobs_listed",
        message=(
            f"Found {len(job_list)} scheduled job(s)."
            if job_list
            else "No scheduled jobs found."
        ),
        jobs=job_list,
        total=len(job_list),
    )


async def _tool_cancel_scheduled_job(
    owner_id: int,
    job_id: str = "",
) -> str:
    """Cancel a scheduled job by ID."""
    err = _validate_non_empty_string(job_id, "job_id", "cancel_scheduled_job")
    if err:
        return err

    from src.core.scheduled.jobs import cancel_job

    success = await cancel_job(job_id)

    if success:
        return tool_success(
            action="job_cancelled",
            message=f"Job {job_id} cancelled successfully.",
            job_id=job_id,
        )

    return tool_error(
        action="cancel_scheduled_job",
        message=f"Job '{job_id}' not found or already cancelled.",
        error_code="job_not_found",
        suggestion=("Call list_scheduled_jobs first to get valid job IDs."),
        job_id=job_id,
    )


async def _tool_web_search(
    owner_id: int,
    query: str = "",
    max_results: int = 8,
) -> str:
    """Search the web via DuckDuckGo and return structured results."""
    err = _validate_non_empty_string(query, "query", "web_search")
    if err:
        return err

    # Clamp max_results
    max_results = max(1, min(max_results or 8, 20))

    import asyncio

    from ddgs import DDGS

    def _search() -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for r in ddgs.text(
                query,
                max_results=max_results,
                region="us-en",
                safesearch="moderate",
                timelimit="m",
            ):
                snippet = r.get("body", "") or ""
                if len(snippet) > 280:
                    snippet = snippet[:280] + "..."
                results.append(
                    {
                        "title": r["title"],
                        "snippet": snippet,
                        "url": r["href"],
                    }
                )
        return results

    try:
        results = await asyncio.to_thread(_search)
    except Exception as exc:
        logger.exception("Web search failed for query '%s'", query)
        return tool_error(
            action="web_search",
            message=f"Web search failed for '{query}'.",
            error_code="search_error",
            suggestion="Try a different query or try again later.",
            exception=str(exc),
        )

    return tool_success(
        action="search_completed",
        message=(
            f"Found {len(results)} result(s) for '{query}'."
            if results
            else f"No results found for '{query}'."
        ),
        query=query,
        results=results,
        total=len(results),
    )


async def _tool_browse_webpage(
    owner_id: int,
    url: str = "",
    max_length: int = 4000,
) -> str:
    """Fetch a web page and return its main text content."""
    err = _validate_non_empty_string(url, "url", "browse_webpage")
    if err:
        return err

    if not url.startswith(("http://", "https://")):
        return tool_invalid_input(
            action="browse_webpage",
            message="URL must start with 'http://' or 'https://'.",
            error_code="invalid_url",
            suggestion="Provide a full URL including the protocol.",
        )

    # Clamp max_length
    max_length = max(500, min(max_length or 4000, 10000))

    from html.parser import HTMLParser

    import httpx

    class _TextExtractor(HTMLParser):
        """Minimal HTML-to-text extractor that skips script/style tags."""

        def __init__(self) -> None:
            super().__init__()
            self._pieces: list[str] = []
            self._skip = False

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if tag in ("script", "style", "noscript"):
                self._skip = True

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style", "noscript"):
                self._skip = False
            if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"):
                self._pieces.append("\n")

        def handle_data(self, data: str) -> None:
            if not self._skip:
                self._pieces.append(data)

        def get_text(self) -> str:
            import re

            raw = "".join(self._pieces)
            raw = re.sub(r"[^\S\n]+", " ", raw)
            raw = re.sub(r"\n{3,}", "\n\n", raw)
            return raw.strip()

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers={"User-Agent": "RaccBuddy/1.0 (web-browse tool)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        logger.exception("Failed to fetch URL '%s'", url)
        return tool_error(
            action="browse_webpage",
            message=f"Failed to fetch page at '{url}'.",
            error_code="fetch_error",
            suggestion="Check if the URL is correct and accessible.",
            exception=str(exc),
        )

    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return tool_error(
            action="browse_webpage",
            message=f"Page returned non-text content ({content_type}).",
            error_code="unsupported_content_type",
            suggestion="This URL does not serve readable text or HTML.",
        )

    extractor = _TextExtractor()
    extractor.feed(resp.text)
    text = extractor.get_text()

    if not text:
        return tool_error(
            action="browse_webpage",
            message="Could not extract meaningful text from the page.",
            error_code="empty_extraction",
            suggestion="The page may be JavaScript-rendered or empty.",
        )

    truncated = False
    if len(text) > max_length:
        text = text[:max_length]
        truncated = True

    return tool_success(
        action="page_browsed",
        message=f"Content from {url} retrieved.",
        url=url,
        content=text,
        truncated=truncated,
        content_length=len(text),
    )


async def _tool_remember_about_owner(
    owner_id: int,
    fact: str = "",
    category: str = "fact",
    importance: int = 8,
) -> str:
    """Save a personal fact about the owner to Raccy's self-memory."""
    err = _validate_non_empty_string(fact, "fact", "remember_about_owner")
    if err:
        return err

    valid_categories = {
        "preference",
        "trait",
        "joke",
        "emotion",
        "reflection",
        "fact",
        "goal",
        "routine",
        "boundary",
    }
    if category not in valid_categories:
        category = "fact"

    importance = max(1, min(importance if isinstance(importance, int) else 8, 10))

    from src.core.memory.base import memory

    mem = await memory.add_owner_memory(
        owner_id,
        fact,
        importance=importance,
        category=category,
        metadata={"source": "llm_tool"},
    )

    return tool_success(
        action="fact_remembered",
        message=f'Remembered: "{fact}"',
        fact=fact,
        category=category,
        importance=mem.importance,
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
    "schedule_recurring_message": _tool_schedule_recurring_message,
    "list_scheduled_jobs": _tool_list_scheduled_jobs,
    "cancel_scheduled_job": _tool_cancel_scheduled_job,
    "web_search": _tool_web_search,
    "browse_webpage": _tool_browse_webpage,
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
