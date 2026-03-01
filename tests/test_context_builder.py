"""Tests for src.core.memory.context_builder — ContextBuilder pipeline.

All tests patch ContextBuilder layer methods directly (patch.object) to avoid
the import-path ambiguity that arises because src.core.memory.__init__.py
re-exports the ``context_builder`` instance alongside the module of the same
name.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.memory.context_builder import ContextBuilder, context_builder

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_module_level_singleton_is_context_builder(self) -> None:
        assert isinstance(context_builder, ContextBuilder)

    def test_same_instance(self) -> None:
        from src.core.memory.context_builder import context_builder as cb2

        assert context_builder is cb2


# ---------------------------------------------------------------------------
# ContextBuilder.build — structural tests via method-level mocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBuild:
    """Validate the context assembled by ContextBuilder.build().

    Every test mocks the six private layer methods so the only real logic
    under test is the orchestration in ``build()`` itself.
    """

    def _patch_all_layers(
        self,
        cb: ContextBuilder,
        *,
        owner_facts: str = "",
        state_snapshot: list[str] | None = None,
        contacts_roster: str = "",
        semantic_memories: str = "",
        summaries: str = "",
        episodic: str = "",
    ):
        """Context manager stack that replaces all six layer methods."""
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(
            patch.object(
                cb, "_owner_facts", new_callable=AsyncMock, return_value=owner_facts
            )
        )
        stack.enter_context(
            patch.object(
                cb,
                "_state_snapshot",
                return_value=state_snapshot
                or ["[User state: mood=neutral, msgs_today=0, streak=0d]"],
            )
        )
        stack.enter_context(
            patch.object(
                cb,
                "_contacts_roster",
                new_callable=AsyncMock,
                return_value=contacts_roster,
            )
        )
        stack.enter_context(
            patch.object(
                cb,
                "_semantic_memories",
                new_callable=AsyncMock,
                return_value=semantic_memories,
            )
        )
        stack.enter_context(
            patch.object(
                cb, "_summaries", new_callable=AsyncMock, return_value=summaries
            )
        )
        stack.enter_context(
            patch.object(cb, "_episodic", new_callable=AsyncMock, return_value=episodic)
        )
        return stack

    async def test_always_includes_current_query(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers(cb):
            result = await cb.build(
                owner_id=100, contact_id=None, query="hello raccoon"
            )
        assert "[Current message]: hello raccoon" in result

    async def test_includes_user_state_snapshot(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers(
            cb, state_snapshot=["[User state: mood=happy, msgs_today=5, streak=3d]"]
        ):
            result = await cb.build(owner_id=100, contact_id=None, query="hi")
        assert "[User state:" in result
        assert "mood=happy" in result

    async def test_includes_owner_facts_when_non_empty(self) -> None:
        cb = ContextBuilder()
        facts = "[Background knowledge about you]\n- (preference) Loves hiking"
        with self._patch_all_layers(cb, owner_facts=facts):
            result = await cb.build(owner_id=100, contact_id=None, query="hi")
        assert "[Background knowledge about you]" in result
        assert "Loves hiking" in result

    async def test_omits_owner_facts_when_empty(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers(cb, owner_facts=""):
            result = await cb.build(owner_id=100, contact_id=None, query="hi")
        assert "[Background knowledge" not in result

    async def test_includes_contacts_roster_when_non_empty(self) -> None:
        cb = ContextBuilder()
        roster = "[Known contacts (reference only): Alice, Bob]"
        with self._patch_all_layers(cb, contacts_roster=roster):
            result = await cb.build(owner_id=100, contact_id=None, query="hi")
        assert "Alice" in result
        assert "Bob" in result

    async def test_includes_episodic_when_non_empty(self) -> None:
        cb = ContextBuilder()
        episodic = "[Recent messages]\n- How are you doing today?"
        with self._patch_all_layers(cb, episodic=episodic):
            result = await cb.build(owner_id=100, contact_id=None, query="hi")
        assert "[Recent messages]" in result
        assert "How are you doing today?" in result

    async def test_skips_contact_layers_when_contact_id_none(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers(cb):
            _ = await cb.build(owner_id=100, contact_id=None, query="hi")
            # _semantic_memories and _summaries should NOT be called when contact_id=None
            cb._semantic_memories.assert_not_called()
            cb._summaries.assert_not_called()

    async def test_calls_contact_layers_when_contact_provided(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers(
            cb, semantic_memories="[Relevant memories]\n- fact"
        ):
            _ = await cb.build(owner_id=100, contact_id=42, query="hi")
            cb._semantic_memories.assert_called_once()
            cb._summaries.assert_called_once()

    async def test_respects_max_tokens_budget(self) -> None:
        cb = ContextBuilder()
        # Override owner_facts with massive content to trigger truncation
        # max_tokens=10 → budget = 10*4 = 40 chars
        giant = "x" * 10_000
        with self._patch_all_layers(cb, owner_facts=giant):
            result = await cb.build(
                owner_id=100,
                contact_id=None,
                query="hi",
                max_tokens=10,
            )
        # Budget = 10 tokens × 4 chars/token = 40 chars
        assert len(result) <= 40

    async def test_layers_joined_with_newlines(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers(
            cb,
            owner_facts="FACT_LAYER",
            contacts_roster="ROSTER_LAYER",
            episodic="EPISODIC_LAYER",
        ):
            result = await cb.build(owner_id=100, contact_id=None, query="q")
        # Layers should be separated by newlines
        assert "\n" in result
        parts = result.split("\n")
        assert len(parts) >= 3


# ---------------------------------------------------------------------------
# Helper: get the real context_builder MODULE (not the ContextBuilder instance)
# ---------------------------------------------------------------------------


def _ctx_module():
    """Return the context_builder MODULE from sys.modules.

    We cannot use ``import src.core.memory.context_builder as m`` because
    ``src.core.memory.__init__`` re-exports the ``context_builder`` *instance*
    under the same name, causing ``as m`` to resolve to the instance rather
    than the module.  Using ``sys.modules`` avoids this ambiguity.
    """
    return sys.modules["src.core.memory.context_builder"]


# ---------------------------------------------------------------------------
# ContextBuilder._contacts_roster (tests the real implementation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContactsRoster:
    async def test_empty_when_no_contacts(self) -> None:
        m = _ctx_module()
        orig = m.get_all_contacts_all_platforms
        m.get_all_contacts_all_platforms = AsyncMock(return_value=[])
        try:
            cb = ContextBuilder()
            result = await cb._contacts_roster(owner_id=100)
        finally:
            m.get_all_contacts_all_platforms = orig
        assert result == ""

    async def test_lists_contact_names(self) -> None:
        m = _ctx_module()
        c = MagicMock()
        c.contact_name = "Charlie"
        orig = m.get_all_contacts_all_platforms
        m.get_all_contacts_all_platforms = AsyncMock(return_value=[c])
        try:
            cb = ContextBuilder()
            result = await cb._contacts_roster(owner_id=100)
        finally:
            m.get_all_contacts_all_platforms = orig
        assert "Charlie" in result
        assert "[Known contacts" in result

    async def test_returns_empty_on_error(self) -> None:
        m = _ctx_module()
        orig = m.get_all_contacts_all_platforms
        m.get_all_contacts_all_platforms = AsyncMock(side_effect=Exception("db error"))
        try:
            cb = ContextBuilder()
            result = await cb._contacts_roster(owner_id=100)
        finally:
            m.get_all_contacts_all_platforms = orig
        assert result == ""


# ---------------------------------------------------------------------------
# ContextBuilder._episodic (tests the real implementation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEpisodic:
    async def test_no_contact_uses_owner_messages(self) -> None:
        m = _ctx_module()
        msg = MagicMock()
        msg.text = "Owner message here"
        orig = m.get_recent_messages
        m.get_recent_messages = AsyncMock(return_value=[msg])
        try:
            cb = ContextBuilder()
            result = await cb._episodic(owner_id=100, contact_id=None)
        finally:
            m.get_recent_messages = orig
        assert "[Recent messages]" in result
        assert "Owner message here" in result

    async def test_with_contact_uses_contact_messages(self) -> None:
        m = _ctx_module()
        msg = MagicMock()
        msg.text = "Contact message here"
        orig = m.get_recent_messages_for_contact
        m.get_recent_messages_for_contact = AsyncMock(return_value=[msg])
        try:
            cb = ContextBuilder()
            result = await cb._episodic(owner_id=100, contact_id=42)
        finally:
            m.get_recent_messages_for_contact = orig
        assert "[Recent messages]" in result
        assert "Contact message here" in result

    async def test_empty_when_no_messages(self) -> None:
        m = _ctx_module()
        orig = m.get_recent_messages
        m.get_recent_messages = AsyncMock(return_value=[])
        try:
            cb = ContextBuilder()
            result = await cb._episodic(owner_id=100, contact_id=None)
        finally:
            m.get_recent_messages = orig
        assert result == ""


# ---------------------------------------------------------------------------
# ContextBuilder._conversation_history (tests the real implementation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConversationHistory:
    async def test_returns_conversation_messages(self) -> None:
        m = _ctx_module()
        msg1 = MagicMock()
        msg1.text = "Hello Raccy"
        msg1.is_bot_reply = False
        msg2 = MagicMock()
        msg2.text = "Hey there! 🦝"
        msg2.is_bot_reply = True
        orig = m.get_conversation_history
        m.get_conversation_history = AsyncMock(return_value=[msg1, msg2])
        try:
            cb = ContextBuilder()
            result = await cb._conversation_history(chat_id=100)
        finally:
            m.get_conversation_history = orig
        assert len(result) == 2
        assert result[0].is_bot_reply is False
        assert result[1].is_bot_reply is True

    async def test_empty_when_no_history(self) -> None:
        m = _ctx_module()
        orig = m.get_conversation_history
        m.get_conversation_history = AsyncMock(return_value=[])
        try:
            cb = ContextBuilder()
            result = await cb._conversation_history(chat_id=100)
        finally:
            m.get_conversation_history = orig
        assert result == []

    async def test_returns_empty_on_error(self) -> None:
        m = _ctx_module()
        orig = m.get_conversation_history
        m.get_conversation_history = AsyncMock(side_effect=Exception("db error"))
        try:
            cb = ContextBuilder()
            result = await cb._conversation_history(chat_id=100)
        finally:
            m.get_conversation_history = orig
        assert result == []


# ---------------------------------------------------------------------------
# ContextBuilder.build_messages — structural tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBuildMessages:
    """Validate the chat messages list assembled by build_messages().

    Uses the same layer-mocking approach as TestBuild plus mocking
    _conversation_history for the conversation turns.
    """

    def _patch_all_layers_and_history(
        self,
        cb: ContextBuilder,
        *,
        owner_facts: str = "",
        state_snapshot: list[str] | None = None,
        contacts_roster: str = "",
        semantic_memories: str = "",
        summaries: str = "",
        episodic: str = "",
        conversation_history: list | None = None,
    ):
        """Context manager that replaces all layer methods + history."""
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(
            patch.object(
                cb, "_owner_facts", new_callable=AsyncMock, return_value=owner_facts
            )
        )
        stack.enter_context(
            patch.object(
                cb,
                "_state_snapshot",
                return_value=state_snapshot
                or ["[User state: mood=neutral, msgs_today=0, streak=0d]"],
            )
        )
        stack.enter_context(
            patch.object(
                cb,
                "_contacts_roster",
                new_callable=AsyncMock,
                return_value=contacts_roster,
            )
        )
        stack.enter_context(
            patch.object(
                cb,
                "_semantic_memories",
                new_callable=AsyncMock,
                return_value=semantic_memories,
            )
        )
        stack.enter_context(
            patch.object(
                cb, "_summaries", new_callable=AsyncMock, return_value=summaries
            )
        )
        stack.enter_context(
            patch.object(cb, "_episodic", new_callable=AsyncMock, return_value=episodic)
        )
        stack.enter_context(
            patch.object(
                cb,
                "_conversation_history",
                new_callable=AsyncMock,
                return_value=conversation_history or [],
            )
        )
        return stack

    async def test_returns_list_of_message_dicts(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers_and_history(cb):
            result = await cb.build_messages(
                owner_id=100,
                contact_id=None,
                query="hello",
                system_prompt="You are helpful.",
            )
        assert isinstance(result, list)
        assert all(isinstance(m, dict) for m in result)
        assert all("role" in m and "content" in m for m in result)

    async def test_first_message_is_system(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers_and_history(cb):
            result = await cb.build_messages(
                owner_id=100,
                contact_id=None,
                query="hi",
                system_prompt="You are RaccBuddy.",
            )
        assert result[0]["role"] == "system"
        assert "You are RaccBuddy." in result[0]["content"]

    async def test_last_message_is_current_query(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers_and_history(cb):
            result = await cb.build_messages(
                owner_id=100,
                contact_id=None,
                query="what's up?",
                system_prompt="sys",
            )
        assert result[-1]["role"] == "user"
        assert result[-1]["content"] == "what's up?"

    async def test_includes_conversation_history(self) -> None:
        msg1 = MagicMock()
        msg1.text = "hey Raccy"
        msg1.is_bot_reply = False
        msg2 = MagicMock()
        msg2.text = "Hey! 🦝"
        msg2.is_bot_reply = True

        cb = ContextBuilder()
        with self._patch_all_layers_and_history(cb, conversation_history=[msg1, msg2]):
            result = await cb.build_messages(
                owner_id=100,
                contact_id=None,
                query="new question",
                system_prompt="sys",
            )
        # System + 2 history turns + current query = 4 messages
        assert len(result) == 4
        assert result[1] == {"role": "user", "content": "hey Raccy"}
        assert result[2] == {"role": "assistant", "content": "Hey! 🦝"}
        assert result[3] == {"role": "user", "content": "new question"}

    async def test_context_in_system_message(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers_and_history(
            cb,
            owner_facts="[Background knowledge]\n- Loves hiking",
            contacts_roster="[Known contacts: Alice]",
        ):
            result = await cb.build_messages(
                owner_id=100,
                contact_id=None,
                query="hi",
                system_prompt="You are Raccy.",
            )
        system_content = result[0]["content"]
        assert "You are Raccy." in system_content
        assert "Loves hiking" in system_content
        assert "Alice" in system_content

    async def test_no_history_still_works(self) -> None:
        cb = ContextBuilder()
        with self._patch_all_layers_and_history(cb, conversation_history=[]):
            result = await cb.build_messages(
                owner_id=100,
                contact_id=None,
                query="first message",
                system_prompt="sys",
            )
        # System + current query only
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "first message"
