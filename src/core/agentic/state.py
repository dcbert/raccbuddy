"""AgenticState TypedDict for the LangGraph supervisor graph.

This module defines the shared state schema that flows between all nodes
in the proactive agentic cycle.  Each field is annotated so that
LangGraph can merge partial updates automatically.
"""

from __future__ import annotations

from typing import Any, TypedDict


class NudgeCandidate(TypedDict):
    """A single nudge candidate produced by the NudgePlanner."""

    skill_name: str
    trigger: str
    reason: str
    prompt: str
    context: dict[str, Any]


class CraftedNudge(TypedDict):
    """A nudge after the Crafter has generated final text."""

    skill_name: str
    trigger: str
    reason: str
    text: str


class AgenticState(TypedDict, total=False):
    """Shared state for the 4-node supervisor graph.

    Fields are intentionally ``total=False`` so that each node only needs
    to return the keys it updates.
    """

    # ContextKeeper populates these
    owner_id: int
    context: str
    contacts_summary: str

    # NudgePlanner populates these
    candidates: list[NudgeCandidate]

    # Crafter populates these
    crafted: list[CraftedNudge]

    # Reflector populates these
    approved: list[CraftedNudge]
    discarded: list[CraftedNudge]

    # Supervisor routing
    next_node: str

    # Error / metadata
    error: str
    cycle_id: str
