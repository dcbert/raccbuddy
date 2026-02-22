"""Tool system for LLM function calling.

Re-exports the full public API for backward compatibility.
"""

from __future__ import annotations

from src.core.tools.registry import TOOL_SCHEMAS, ToolHandler, execute_tool, get_all_tool_schemas, parse_tool_arguments

__all__ = [
    "TOOL_SCHEMAS",
    "ToolHandler",
    "execute_tool",
    "get_all_tool_schemas",
    "parse_tool_arguments",
]
