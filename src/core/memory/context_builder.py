"""Smart context assembly for every LLM invocation.

Architecture
------------
``ContextBuilder`` is the single, mandatory entry-point for constructing
the prompt context that gets sent to the LLM.  No handler, skill, or tool
should construct context manually — always call::

    ctx = await context_builder.build(owner_id, contact_id, query)

Context layers (assembled in priority order):

1. **Owner self-memory** — query-aware personal facts about the owner.
2. **User & contact state** — live mood, message count, relationship score.
3. **Known contacts** — lightweight roster for name resolution.
4. **Semantic memories** — top-k pgvector chunks relevant to the query.
5. **Relevant summaries** — past daily summaries ranked by similarity.
6. **Recent episodic messages** — raw last-N messages for grounding.
7. **Current query** — the user's actual message.

Token budget
------------
The total character budget is derived from ``settings.max_context_tokens``
(default 30 000) × 4 chars/token.  Each layer gets a configurable fraction
of that budget.  If the assembled context exceeds the budget it is hard-
truncated and a warning is logged.

All retrieval parameters are driven by ``settings.memory_*`` config keys
so they can be tuned without code changes.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.core.config import settings
from src.core.db.crud import (
    get_all_contacts_all_platforms,
    get_contact_name,
    get_conversation_history,
    get_recent_messages,
    get_recent_messages_for_contact,
    get_relevant_summaries,
)
from src.core.llm.interface import embed
from src.core.state.persistent import get_contact_state, get_state

logger = logging.getLogger(__name__)

# Approximate characters per token (no full tokeniser needed for budgeting)
_CHARS_PER_TOKEN: int = 4


class ContextBuilder:
    """Assemble a token-budgeted context string for every LLM invocation.

    This class is the clean-architecture boundary between the memory
    subsystem and the LLM layer.  It is intentionally stateless — all
    state lives in the database or in-memory caches owned by other modules.

    Usage::

        ctx = await context_builder.build(owner_id, contact_id, query)
        reply = await generate(ctx)
    """

    async def build(
        self,
        owner_id: int,
        contact_id: Optional[int],
        query: str,
        *,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Build a complete, token-budgeted context string.

        Args:
            owner_id: The Telegram owner user ID.
            contact_id: Optional database ID of the contact being discussed.
                Pass ``None`` for generic (non-contact-scoped) queries.
            query: The current user message / question.
            max_tokens: Override the default context window (useful for
                tools that need a smaller window).

        Returns:
            A newline-joined context string ready to pass as the ``prompt``
            argument to ``generate()``.
        """
        effective_max = max_tokens or settings.max_context_tokens
        budget_chars = effective_max * _CHARS_PER_TOKEN
        parts: list[str] = []

        # -- Layer 1: Owner self-memory (query-aware) ----------------------
        owner_facts = await self._owner_facts(owner_id, query, budget_chars)
        if owner_facts:
            parts.append(owner_facts)

        # -- Layer 2: State snapshot ----------------------------------------
        parts.extend(self._state_snapshot(owner_id, contact_id))

        # -- Layer 3: Known contacts roster --------------------------------
        contacts_line = await self._contacts_roster(owner_id)
        if contacts_line:
            parts.append(contacts_line)

        # -- Layer 4: Semantic memories ------------------------------------
        if contact_id is not None:
            sem_block = await self._semantic_memories(
                query, owner_id, contact_id, budget_chars,
            )
            if sem_block:
                parts.append(sem_block)

        # -- Layer 5: Relevant summaries -----------------------------------
        if contact_id is not None:
            summary_block = await self._summaries(query, contact_id)
            if summary_block:
                parts.append(summary_block)

        # -- Layer 6: Recent episodic messages -----------------------------
        episodic_block = await self._episodic(owner_id, contact_id)
        if episodic_block:
            parts.append(episodic_block)

        # -- Layer 7: Current query ----------------------------------------
        parts.append(f"[Current message]: {query}")

        context = "\n".join(parts)

        if len(context) > budget_chars:
            context = context[:budget_chars]
            logger.warning(
                "Context truncated to %d chars (max_tokens=%d, contact_id=%s)",
                budget_chars, effective_max, contact_id,
            )
        else:
            logger.debug(
                "Context built: %d chars / %d budget (contact_id=%s)",
                len(context), budget_chars, contact_id,
            )

        return context

    # ------------------------------------------------------------------
    # Chat-messages builder (multi-turn conversation)
    # ------------------------------------------------------------------

    async def build_messages(
        self,
        owner_id: int,
        contact_id: Optional[int],
        query: str,
        system_prompt: str,
        *,
        max_tokens: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """Build a proper chat-messages list for multi-turn LLM calls.

        Instead of flattening everything into a single prompt string, this
        method returns a structured ``messages`` list suitable for chat APIs
        (OpenAI, Ollama /api/chat, xAI /chat/completions).

        Structure:
            1. **System message** — ``system_prompt`` + assembled context
               (owner facts, state, contacts, semantic memories, summaries).
            2. **Conversation history** — alternating user/assistant messages
               from the last ``memory_conversation_turns`` turns.
            3. **Current user message** — the actual query.

        Args:
            owner_id: The Telegram owner user ID.
            contact_id: Optional database ID of the contact being discussed.
            query: The current user message / question.
            system_prompt: The base system prompt (e.g. SYSTEM_PROMPT).
            max_tokens: Override the default context window.

        Returns:
            A list of dicts with ``role`` and ``content`` keys.
        """
        effective_max = max_tokens or settings.max_context_tokens
        budget_chars = effective_max * _CHARS_PER_TOKEN
        context_parts: list[str] = []

        # -- Context layers (go into system message) --------------------
        owner_facts = await self._owner_facts(owner_id, query, budget_chars)
        if owner_facts:
            context_parts.append(owner_facts)

        context_parts.extend(self._state_snapshot(owner_id, contact_id))

        contacts_line = await self._contacts_roster(owner_id)
        if contacts_line:
            context_parts.append(contacts_line)

        if contact_id is not None:
            sem_block = await self._semantic_memories(
                query, owner_id, contact_id, budget_chars,
            )
            if sem_block:
                context_parts.append(sem_block)

            summary_block = await self._summaries(query, contact_id)
            if summary_block:
                context_parts.append(summary_block)

        # Episodic (contact-scoped recent messages, for forwarded convos)
        if contact_id is not None:
            episodic_block = await self._episodic(owner_id, contact_id)
            if episodic_block:
                context_parts.append(episodic_block)

        # Assemble system message: base prompt + context
        context_str = "\n".join(context_parts)
        if context_str:
            full_system = f"{system_prompt}\n\n{context_str}"
        else:
            full_system = system_prompt

        messages: list[dict[str, str]] = [
            {"role": "system", "content": full_system},
        ]

        # -- Conversation history (user ↔ bot turns) -------------------
        chat_id = owner_id  # Owner's Telegram chat ID
        history = await self._conversation_history(chat_id)
        used_chars = len(full_system) + len(query)

        for msg in history:
            msg_chars = len(msg.text)
            if used_chars + msg_chars > budget_chars:
                logger.debug("Conversation history truncated (budget)")
                break
            role = "assistant" if msg.is_bot_reply else "user"
            messages.append({"role": role, "content": msg.text})
            used_chars += msg_chars

        # -- Current query (always last) --------------------------------
        messages.append({"role": "user", "content": query})

        logger.debug(
            "build_messages: %d messages, ~%d chars (contact_id=%s)",
            len(messages), used_chars, contact_id,
        )
        return messages

    # ------------------------------------------------------------------
    # Private layer builders
    # ------------------------------------------------------------------

    async def _owner_facts(
        self,
        owner_id: int,
        query: str,
        budget_chars: int,
    ) -> str:
        """Retrieve and format query-relevant owner self-memory facts."""
        from sqlalchemy import desc, select

        from src.core.db.models import OwnerMemory
        from src.core.db.session import get_session

        layer_budget = int(budget_chars * settings.memory_owner_budget_ratio)
        k = settings.memory_semantic_chunks

        try:
            query_emb = await embed(query[:512])
            relevance_expr = (
                1 - OwnerMemory.embedding.cosine_distance(query_emb)
            ).label("relevance")

            async with get_session() as session:
                stmt = (
                    select(
                        OwnerMemory.content,
                        OwnerMemory.category,
                        OwnerMemory.importance,
                        relevance_expr,
                    )
                    .where(
                        OwnerMemory.owner_id == owner_id,
                        relevance_expr >= settings.memory_min_owner_relevance,
                    )
                    .order_by(desc(relevance_expr))
                    .limit(k)
                )
                rows = (await session.execute(stmt)).all()

        except Exception:
            logger.warning("Owner facts vector search failed; falling back to importance order")
            try:
                async with get_session() as session:
                    stmt = (
                        select(OwnerMemory.content, OwnerMemory.category, OwnerMemory.importance)
                        .where(OwnerMemory.owner_id == owner_id)
                        .order_by(
                            desc(OwnerMemory.importance),
                            desc(OwnerMemory.created_at),
                        )
                        .limit(k)
                    )
                    rows = (await session.execute(stmt)).all()
            except Exception:
                logger.warning("Owner facts fallback also failed", exc_info=True)
                return ""

        if not rows:
            return ""

        header = "[Background knowledge about you — use only if relevant to the question]"
        lines = [header]
        used = len(header)
        for row in rows:
            line = f"- ({row.category}) {row.content}"
            if used + len(line) + 1 > layer_budget:
                break
            lines.append(line)
            used += len(line) + 1

        return "\n".join(lines)

    def _state_snapshot(
        self,
        owner_id: int,
        contact_id: Optional[int],
    ) -> list[str]:
        """Build state snapshot lines from in-memory caches."""
        parts: list[str] = []

        user_state = get_state(owner_id)
        parts.append(
            f"[User state: mood={user_state.mood}, "
            f"msgs_today={user_state.message_count_today}, "
            f"streak={user_state.streak_days}d]"
        )

        if contact_id is not None:
            contact_state = get_contact_state(owner_id, contact_id)
            parts.append(
                f"[Contact state: score={contact_state.score}/100, "
                f"mood={contact_state.mood}]"
            )

        return parts

    async def _contacts_roster(self, owner_id: int) -> str:
        """Return a compact list of known contact names."""
        try:
            contacts = await get_all_contacts_all_platforms(owner_id)
        except Exception:
            logger.warning("Failed to load contacts roster", exc_info=True)
            return ""

        if not contacts:
            return ""

        names = ", ".join(c.contact_name for c in contacts[:15])
        return f"[Known contacts (reference only): {names}]"

    async def _semantic_memories(
        self,
        query: str,
        owner_id: int,
        contact_id: int,
        budget_chars: int,
    ) -> str:
        """Retrieve top-k semantic memory chunks via hybrid search."""
        from src.core.memory.base import memory

        layer_budget = int(budget_chars * settings.memory_contact_budget_ratio)

        try:
            docs = await memory.hybrid_search(
                query,
                owner_id,
                contact_id=contact_id,
                k=settings.memory_semantic_chunks,
                include_owner_memories=False,
            )
        except Exception:
            logger.warning("Semantic memory retrieval failed", exc_info=True)
            return ""

        if not docs:
            return ""

        header = "[Relevant memories — reference only when pertinent]"
        lines = [header]
        used = len(header)
        for doc in docs:
            line = f"- {doc.content[:300]}"
            if used + len(line) > layer_budget:
                break
            lines.append(line)
            used += len(line)

        return "\n".join(lines)

    async def _summaries(self, query: str, contact_id: int) -> str:
        """Retrieve relevant daily summaries ranked by cosine similarity."""
        try:
            query_embedding = await embed(query[:512])
            summaries = await get_relevant_summaries(
                contact_id,
                query_embedding,
                limit=settings.memory_max_summaries,
            )
        except Exception:
            logger.warning("Summary retrieval failed for contact %d", contact_id, exc_info=True)
            return ""

        if not summaries:
            return ""

        lines = ["[Relevant history]"]
        for s in summaries:
            lines.append(f"- {s.date}: {s.summary_text[:300]}")
        return "\n".join(lines)

    async def _episodic(
        self,
        owner_id: int,
        contact_id: Optional[int],
    ) -> str:
        """Retrieve the most recent raw messages for conversational grounding."""
        limit = settings.memory_recent_messages
        try:
            if contact_id is not None:
                messages = await get_recent_messages_for_contact(contact_id, limit=limit)
            else:
                messages = await get_recent_messages(owner_id, limit=limit)
        except Exception:
            logger.warning("Episodic message retrieval failed", exc_info=True)
            return ""

        if not messages:
            return ""

        lines = ["[Recent messages]"]
        for m in messages:
            lines.append(f"- {m.text[:200]}")
        return "\n".join(lines)

    async def _conversation_history(
        self,
        chat_id: int,
    ) -> list:
        """Retrieve recent user ↔ bot conversation turns.

        Returns Message objects in chronological order (oldest first).
        The caller uses ``msg.is_bot_reply`` to assign the correct role.
        """
        limit = settings.memory_conversation_turns
        try:
            return await get_conversation_history(chat_id, limit=limit)
        except Exception:
            logger.warning("Conversation history retrieval failed", exc_info=True)
            return []


# ---------------------------------------------------------------------------
# Module-level singleton — import and use this directly
# ---------------------------------------------------------------------------

context_builder = ContextBuilder()
