"""Structured JSON response builder for LLM tool calls.

Every tool MUST return a structured JSON response via one of the helpers
in this module.  This ensures:

1. Consistent ``status`` / ``action`` / ``message`` / ``final_instruction``
   fields so the reasoning model can detect completion and stop looping.
2. Idempotency semantics (``already_exists`` status) are first-class.
3. Strong input-validation errors are surfaced with ``error_code`` and
   ``suggestion``.
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Status literals
# ---------------------------------------------------------------------------
STATUS_SUCCESS = "success"
STATUS_ALREADY_EXISTS = "already_exists"
STATUS_ERROR = "error"
STATUS_INVALID_INPUT = "invalid_input"

# Sentinel instruction appended on every terminal (non-retry) response.
_FINAL = "Task complete - do not call any tool again"


# ---------------------------------------------------------------------------
# Public helpers — every tool handler should use one of these
# ---------------------------------------------------------------------------


def tool_success(
    action: str,
    message: str,
    **extra: Any,
) -> str:
    """Return a successful tool response as a JSON string.

    Args:
        action: Machine-readable verb (e.g. ``"job_scheduled"``).
        message: Human-friendly summary for the LLM to relay to the user.
        **extra: Additional tool-specific key/value pairs merged into the
            top-level JSON object.
    """
    payload: dict[str, Any] = {
        "status": STATUS_SUCCESS,
        "action": action,
        "message": message,
        "final_instruction": _FINAL,
        **extra,
    }
    return json.dumps(payload, ensure_ascii=False)


def tool_already_exists(
    action: str,
    message: str,
    **extra: Any,
) -> str:
    """Return an ``already_exists`` response (idempotent duplicate)."""
    payload: dict[str, Any] = {
        "status": STATUS_ALREADY_EXISTS,
        "action": action,
        "message": message,
        "final_instruction": _FINAL,
        **extra,
    }
    return json.dumps(payload, ensure_ascii=False)


def tool_error(
    action: str,
    message: str,
    *,
    error_code: str = "unknown_error",
    suggestion: str = "",
    **extra: Any,
) -> str:
    """Return a structured error response."""
    payload: dict[str, Any] = {
        "status": STATUS_ERROR,
        "action": action,
        "message": message,
        "error_code": error_code,
        "suggestion": suggestion or "Check your input and try again.",
        **extra,
    }
    return json.dumps(payload, ensure_ascii=False)


def tool_invalid_input(
    action: str,
    message: str,
    *,
    error_code: str = "invalid_input",
    suggestion: str = "",
    **extra: Any,
) -> str:
    """Return a structured input-validation error."""
    payload: dict[str, Any] = {
        "status": STATUS_INVALID_INPUT,
        "action": action,
        "message": message,
        "error_code": error_code,
        "suggestion": suggestion or "Provide valid input and try again.",
        **extra,
    }
    return json.dumps(payload, ensure_ascii=False)
