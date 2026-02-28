"""LangGraph StateGraph with 4 nodes + supervisor routing.

Nodes
-----
1. **ContextKeeper** — Assembles the current context via ``context_builder``.
2. **NudgePlanner**  — Evaluates registered nudge skills to find candidates.
3. **Crafter**       — Generates final nudge text via LLM for each candidate.
4. **Reflector**     — Quality-gates crafted nudges (approve / discard).

The supervisor routes linearly: ContextKeeper → NudgePlanner → Crafter → Reflector → END.
If NudgePlanner finds no candidates, it short-circuits to END.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.agentic.state import AgenticState, CraftedNudge, NudgeCandidate
from src.core.config import settings

logger = logging.getLogger(__name__)

# LangGraph's END sentinel value (avoids top-level langgraph import)
_END = "__end__"

# Approximate chars-per-token ratio for budget calculations
_CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


async def context_keeper(state: AgenticState) -> dict[str, Any]:
    """Assemble the context snapshot for this agentic cycle."""
    from src.core.memory.context_builder import context_builder

    owner_id = state.get("owner_id", settings.owner_telegram_id)
    if not owner_id:
        return {"error": "No owner_id configured", "next_node": _END}

    try:
        ctx = await context_builder.build(
            owner_id,
            contact_id=None,
            query="Proactive nudge evaluation — what should I check on?",
            max_tokens=settings.max_cycle_tokens,
        )
    except Exception:
        logger.exception("ContextKeeper failed")
        return {"error": "context_builder.build() failed", "next_node": _END}

    logger.info("ContextKeeper: built context (%d chars)", len(ctx))
    return {"context": ctx, "owner_id": owner_id, "next_node": "nudge_planner"}


async def nudge_planner(state: AgenticState) -> dict[str, Any]:
    """Evaluate all registered nudge skills and collect candidates."""
    from src.core.agentic.tools import evaluate_nudge_skill, get_available_nudge_skills
    from src.core.skills.base import get_registered_skills

    if state.get("error"):
        return {"next_node": _END}

    all_skills = get_registered_skills()
    skills = await get_available_nudge_skills()
    candidates: list[NudgeCandidate] = []

    for skill_info in skills:
        if skill_info["on_cooldown"]:
            logger.debug("NudgePlanner: %s on cooldown", skill_info["name"])
            continue

        check = await evaluate_nudge_skill(skill_info["name"])
        if check is None or not check.fire:
            continue

        # Build the prompt using the skill's template
        skill_obj = all_skills.get(skill_info["name"])
        if skill_obj is None:
            continue

        prompt = skill_obj.build_prompt(check)
        candidates.append(
            NudgeCandidate(
                skill_name=skill_info["name"],
                trigger=skill_info["trigger"],
                reason=check.reason,
                prompt=prompt,
                context=check.context,
            )
        )

    if not candidates:
        logger.info("NudgePlanner: no candidates — ending cycle")
        return {"candidates": [], "next_node": _END}

    logger.info("NudgePlanner: %d candidate(s) found", len(candidates))
    return {"candidates": candidates, "next_node": "crafter"}


async def crafter(state: AgenticState) -> dict[str, Any]:
    """Generate final nudge text for each candidate via the LLM."""
    from src.core.llm.interface import generate

    if state.get("error"):
        return {"next_node": _END}

    candidates = state.get("candidates", [])
    if not candidates:
        return {"crafted": [], "next_node": _END}

    context = state.get("context", "")
    crafted: list[CraftedNudge] = []

    for candidate in candidates:
        enriched_prompt = (
            f"{context}\n\n"
            f"[Nudge trigger: {candidate['trigger']}]\n"
            f"[Reason: {candidate['reason']}]\n\n"
            f"{candidate['prompt']}"
        )
        try:
            text = await generate(enriched_prompt)
            crafted.append(
                CraftedNudge(
                    skill_name=candidate["skill_name"],
                    trigger=candidate["trigger"],
                    reason=candidate["reason"],
                    text=text,
                )
            )
            logger.info(
                "Crafter: generated text for %s (%d chars)",
                candidate["skill_name"],
                len(text),
            )
        except Exception:
            logger.exception(
                "Crafter: LLM generation failed for %s",
                candidate["skill_name"],
            )

    return {"crafted": crafted, "next_node": "reflector"}


async def reflector(state: AgenticState) -> dict[str, Any]:
    """Quality-gate: approve or discard each crafted nudge.

    The Reflector asks the LLM to evaluate whether the nudge is:
    - Relevant given the current context
    - Well-written and not annoying
    - Appropriately timed

    If the LLM response contains "APPROVE" the nudge is approved;
    otherwise it is discarded.
    """
    from src.core.llm.interface import generate

    if state.get("error"):
        return {"next_node": _END}

    crafted = state.get("crafted", [])
    if not crafted:
        return {"approved": [], "discarded": [], "next_node": _END}

    context = state.get("context", "")
    approved: list[CraftedNudge] = []
    discarded: list[CraftedNudge] = []

    # Use a configurable budget for the reflector context slice
    reflector_budget = settings.max_cycle_tokens * _CHARS_PER_TOKEN // 3

    for nudge in crafted:
        reflection_prompt = (
            f"You are a quality evaluator for proactive nudge messages.\n\n"
            f"Context:\n{context[:reflector_budget]}\n\n"
            f"Nudge to evaluate:\n"
            f"- Trigger: {nudge['trigger']}\n"
            f"- Reason: {nudge['reason']}\n"
            f"- Text: {nudge['text']}\n\n"
            f"Is this nudge relevant, well-written, appropriately timed, "
            f"and not annoying? Reply with exactly 'APPROVE' or 'DISCARD' "
            f"followed by a brief reason."
        )
        try:
            verdict = await generate(reflection_prompt)
            first_word = verdict.strip().split()[0].upper() if verdict.strip() else ""
            if first_word == "APPROVE":
                approved.append(nudge)
                logger.info("Reflector: APPROVED %s", nudge["skill_name"])
            else:
                discarded.append(nudge)
                logger.info(
                    "Reflector: DISCARDED %s — %s",
                    nudge["skill_name"],
                    verdict[:100],
                )
        except Exception:
            logger.exception(
                "Reflector: LLM evaluation failed for %s — discarding",
                nudge["skill_name"],
            )
            discarded.append(nudge)

    return {"approved": approved, "discarded": discarded, "next_node": _END}


# ---------------------------------------------------------------------------
# Supervisor routing
# ---------------------------------------------------------------------------


def supervisor_router(state: AgenticState) -> str:
    """Route to the next node based on ``state["next_node"]``."""
    return state.get("next_node", _END)


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    """Construct and return an uncompiled LangGraph StateGraph.

    The caller is responsible for compiling with a checkpointer via
    ``graph.compile(checkpointer=...)``.

    Returns:
        An uncompiled ``StateGraph``.
    """
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgenticState)

    # Add nodes
    graph.add_node("context_keeper", context_keeper)
    graph.add_node("nudge_planner", nudge_planner)
    graph.add_node("crafter", crafter)
    graph.add_node("reflector", reflector)

    # Set entry point
    graph.set_entry_point("context_keeper")

    # Conditional routing from each node
    graph.add_conditional_edges(
        "context_keeper",
        supervisor_router,
        {"nudge_planner": "nudge_planner", END: END},
    )
    graph.add_conditional_edges(
        "nudge_planner",
        supervisor_router,
        {"crafter": "crafter", END: END},
    )
    graph.add_conditional_edges(
        "crafter",
        supervisor_router,
        {"reflector": "reflector", END: END},
    )
    graph.add_conditional_edges(
        "reflector",
        supervisor_router,
        {END: END},
    )

    return graph
