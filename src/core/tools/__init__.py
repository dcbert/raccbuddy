"""Tool system for LLM function calling.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.tools.registry import (
    TOOL_SCHEMAS,
    ToolHandler,
    execute_tool,
    get_all_tool_schemas,
    parse_tool_arguments,
)
from src.core.tools.response import (
    tool_already_exists,
    tool_error,
    tool_invalid_input,
    tool_success,
)

__all__ = [
    "TOOL_SCHEMAS",
    "ToolHandler",
    "execute_tool",
    "get_all_tool_schemas",
    "parse_tool_arguments",
    "tool_already_exists",
    "tool_error",
    "tool_invalid_input",
    "tool_success",
]
