"""Tests for src.core.memory — four-layer memory system with owner self-memory."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.memory import (
    CHARS_PER_TOKEN,
    MAX_CONTEXT_CHARS,
    MAX_RECENT_MESSAGES,
    MAX_SUMMARIES,
    OWNER_MEMORY_DEFAULT_IMPORTANCE,
    OWNER_MEMORY_PRUNE_FLOOR,
    Document,
    OwnerMemory,
    PostgresMemory,
    SemanticMemory,
    build_context_for_contact,
    memory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem() -> PostgresMemory:
    """Return a fresh PostgresMemory instance for each test."""
    return PostgresMemory()


# ---------------------------------------------------------------------------
# Constants & Document dataclass
# ---------------------------------------------------------------------------


class TestConstants:
    """Validate module-level constants."""

    def test_max_context_chars_uses_config(self) -> None:
        from src.core.config import settings

        assert MAX_CONTEXT_CHARS == settings.max_context_tokens * CHARS_PER_TOKEN

    def test_owner_memory_defaults(self) -> None:
        assert OWNER_MEMORY_DEFAULT_IMPORTANCE == 8
        assert OWNER_MEMORY_PRUNE_FLOOR == 7

    def test_max_recent_messages(self) -> None:
        assert MAX_RECENT_MESSAGES == 5

    def test_max_summaries(self) -> None:
        assert MAX_SUMMARIES == 3


class TestDocument:
    """Validate the Document dataclass."""

    def test_default_values(self) -> None:
        doc = Document(content="test")
        assert doc.content == "test"
        assert doc.score == 0.0
        assert doc.importance == 5
        assert doc.source == "unknown"
        assert doc.created_at is None
        assert doc.metadata == {}

    def test_custom_values(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = Document(
            content="fact",
            score=0.95,
            importance=9,
            source="owner_memory",
            created_at=now,
            metadata={"key": "val"},
        )
        assert doc.score == 0.95
        assert doc.source == "owner_memory"
        assert doc.metadata["key"] == "val"


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class TestSemanticMemoryModel:
    """Validate SemanticMemory ORM model definition."""

    def test_tablename(self) -> None:
        assert SemanticMemory.__tablename__ == "semantic_memories"

    def test_default_importance(self) -> None:
        # Column default is 5
        col = SemanticMemory.__table__.columns["importance"]
        assert col.default.arg == 5

    def test_default_category(self) -> None:
        col = SemanticMemory.__table__.columns["category"]
        assert col.default.arg == "general"


class TestOwnerMemoryModel:
    """Validate OwnerMemory ORM model definition."""

    def test_tablename(self) -> None:
        assert OwnerMemory.__tablename__ == "owner_memories"

    def test_default_importance_is_high(self) -> None:
        col = OwnerMemory.__table__.columns["importance"]
        assert col.default.arg == OWNER_MEMORY_DEFAULT_IMPORTANCE

    def test_default_category(self) -> None:
        col = OwnerMemory.__table__.columns["category"]
        assert col.default.arg == "fact"


# ---------------------------------------------------------------------------
# PostgresMemory.add_semantic_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddSemanticMemory:
    """Validate semantic memory storage."""

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_stores_with_embedding(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        result = await mem.add_semantic_memory(
            owner_id=100,
            content="Giulia likes hiking",
            contact_id=42,
            importance=6,
            category="topic",
        )

        mock_embed.assert_called_once()
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert isinstance(result, SemanticMemory)
        assert result.content == "Giulia likes hiking"
        assert result.importance == 6
        assert result.category == "topic"

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_defaults_to_importance_5(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        result = await mem.add_semantic_memory(
            owner_id=100,
            content="Some observation",
        )

        assert result.importance == 5

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_truncates_long_content_for_embedding(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        long_content = "x" * 1000
        await mem.add_semantic_memory(owner_id=100, content=long_content)

        # Embedding input should be truncated to 512 chars
        embed_input = mock_embed.call_args[0][0]
        assert len(embed_input) == 512


# ---------------------------------------------------------------------------
# PostgresMemory.add_owner_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddOwnerMemory:
    """Validate owner self-memory storage."""

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_stores_owner_memory(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        result = await mem.add_owner_memory(
            owner_id=100,
            content="Loves spicy ramen",
            category="preference",
        )

        assert isinstance(result, OwnerMemory)
        assert result.content == "Loves spicy ramen"
        assert result.category == "preference"
        assert result.importance == OWNER_MEMORY_DEFAULT_IMPORTANCE
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_custom_importance(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        result = await mem.add_owner_memory(
            owner_id=100,
            content="Birthday is March 15",
            importance=10,
            category="fact",
        )

        assert result.importance == 10

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_metadata_stored(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        result = await mem.add_owner_memory(
            owner_id=100,
            content="Codes best at night",
            metadata={"source": "reflection"},
        )

        assert result.metadata_["source"] == "reflection"


# ---------------------------------------------------------------------------
# PostgresMemory.get_owner_personal_facts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetOwnerPersonalFacts:
    """Validate owner fact retrieval and formatting."""

    @patch("src.core.memory.base.get_session")
    async def test_returns_empty_when_no_facts(
        self,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await mem.get_owner_personal_facts(owner_id=100)

        assert result == ""

    @patch("src.core.memory.base.get_session")
    async def test_formats_facts_with_categories(
        self,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Mock rows with named attributes
        row1 = MagicMock()
        row1.content = "Loves spicy ramen"
        row1.category = "preference"
        row1.importance = 9

        row2 = MagicMock()
        row2.content = "Night owl"
        row2.category = "trait"
        row2.importance = 8

        mock_result = MagicMock()
        mock_result.all.return_value = [row1, row2]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await mem.get_owner_personal_facts(owner_id=100)

        assert "[What Raccy knows about you]" in result
        assert "(preference) Loves spicy ramen" in result
        assert "(trait) Night owl" in result

    @patch("src.core.memory.base.get_session")
    async def test_respects_budget(
        self,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Create many facts that would exceed budget
        rows = []
        for i in range(50):
            row = MagicMock()
            row.content = f"Fact number {i} with some extra text to fill space"
            row.category = "fact"
            row.importance = 8
            rows.append(row)

        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await mem.get_owner_personal_facts(owner_id=100)

        budget = int(MAX_CONTEXT_CHARS * 0.30)
        assert len(result) <= budget


# ---------------------------------------------------------------------------
# PostgresMemory.get_relevant_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetRelevantContext:
    """Validate the main context builder."""

    @patch("src.core.memory.base.get_recent_messages_for_contact", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_relevant_summaries", new_callable=AsyncMock)
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_all_contacts_all_platforms", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_contact_name", new_callable=AsyncMock)
    async def test_includes_owner_facts_first(
        self,
        mock_contact_name: AsyncMock,
        mock_all_contacts: AsyncMock,
        mock_embed: AsyncMock,
        mock_summaries: AsyncMock,
        mock_msgs: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768
        mock_contact_name.return_value = "Giulia"
        mock_all_contacts.return_value = []
        mock_summaries.return_value = []
        mock_msgs.return_value = []

        # Mock get_owner_personal_facts to return a known string
        with patch.object(
            mem, "get_owner_personal_facts",
            new_callable=AsyncMock,
            return_value="[What Raccy knows about you]\n- (trait) Night owl",
        ), patch.object(
            mem, "hybrid_search",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mem.get_relevant_context(
                owner_id=100, contact_id=42, query="hello",
            )

        # Owner facts should be at the very top
        assert result.startswith("[What Raccy knows about you]")
        assert "[Current message]: hello" in result

    @patch("src.core.memory.base.get_recent_messages", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_all_contacts_all_platforms", new_callable=AsyncMock)
    async def test_handles_no_contact(
        self,
        mock_all_contacts: AsyncMock,
        mock_msgs: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_all_contacts.return_value = []
        mock_msgs.return_value = []

        with patch.object(
            mem, "get_owner_personal_facts",
            new_callable=AsyncMock,
            return_value="",
        ):
            result = await mem.get_relevant_context(
                owner_id=100, contact_id=None, query="hi",
            )

        assert "[Current message]: hi" in result
        # Should not contain contact-specific sections
        assert "[Contact:" not in result

    @patch("src.core.memory.base.get_recent_messages_for_contact", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_relevant_summaries", new_callable=AsyncMock)
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_all_contacts_all_platforms", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_contact_name", new_callable=AsyncMock)
    async def test_includes_recent_messages(
        self,
        mock_contact_name: AsyncMock,
        mock_all_contacts: AsyncMock,
        mock_embed: AsyncMock,
        mock_summaries: AsyncMock,
        mock_msgs: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768
        mock_contact_name.return_value = "Giulia"
        mock_all_contacts.return_value = []
        mock_summaries.return_value = []

        msg = MagicMock()
        msg.text = "Hey there!"
        mock_msgs.return_value = [msg]

        with patch.object(
            mem, "get_owner_personal_facts",
            new_callable=AsyncMock,
            return_value="",
        ), patch.object(
            mem, "hybrid_search",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mem.get_relevant_context(
                owner_id=100, contact_id=42, query="hello",
            )

        assert "[Recent messages]" in result
        assert "Hey there!" in result

    @patch("src.core.memory.base.get_recent_messages_for_contact", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_relevant_summaries", new_callable=AsyncMock)
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_all_contacts_all_platforms", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_contact_name", new_callable=AsyncMock)
    async def test_truncates_when_over_budget(
        self,
        mock_contact_name: AsyncMock,
        mock_all_contacts: AsyncMock,
        mock_embed: AsyncMock,
        mock_summaries: AsyncMock,
        mock_msgs: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768
        mock_contact_name.return_value = "Giulia"
        mock_all_contacts.return_value = []
        mock_summaries.return_value = []
        mock_msgs.return_value = []

        # Return massive owner facts that exceed budget
        giant_facts = "x" * (MAX_CONTEXT_CHARS + 1000)

        with patch.object(
            mem, "get_owner_personal_facts",
            new_callable=AsyncMock,
            return_value=giant_facts,
        ), patch.object(
            mem, "hybrid_search",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mem.get_relevant_context(
                owner_id=100, contact_id=42, query="hello",
            )

        assert len(result) <= MAX_CONTEXT_CHARS


# ---------------------------------------------------------------------------
# PostgresMemory.add_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddMessage:
    """Validate episodic message storage."""

    @patch("src.core.db.crud.save_message", new_callable=AsyncMock)
    async def test_delegates_to_save_message(
        self,
        mock_save: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_msg = MagicMock()
        mock_msg.id = 1
        mock_save.return_value = mock_msg

        result = await mem.add_message(
            platform="telegram",
            chat_id=200,
            from_contact_id=42,
            text_content="hello",
        )

        mock_save.assert_called_once_with(
            platform="telegram",
            chat_id=200,
            from_contact_id=42,
            text_content="hello",
            timestamp=None,
        )
        assert result == mock_msg

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    @patch("src.core.db.crud.save_message", new_callable=AsyncMock)
    async def test_embeds_high_importance_messages(
        self,
        mock_save: AsyncMock,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_msg = MagicMock()
        mock_msg.id = 1
        mock_save.return_value = mock_msg
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_session

        await mem.add_message(
            platform="telegram",
            chat_id=200,
            from_contact_id=42,
            text_content="important message",
            importance=7,
        )

        mock_embed.assert_called_once()
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("src.core.db.crud.save_message", new_callable=AsyncMock)
    async def test_skips_embedding_for_low_importance(
        self,
        mock_save: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_msg = MagicMock()
        mock_msg.id = 1
        mock_save.return_value = mock_msg

        with patch("src.core.memory.base.embed", new_callable=AsyncMock) as mock_embed:
            await mem.add_message(
                platform="telegram",
                chat_id=200,
                from_contact_id=42,
                text_content="casual message",
                importance=3,
            )
            mock_embed.assert_not_called()


# ---------------------------------------------------------------------------
# PostgresMemory.prune_old_memories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPruneOldMemories:
    """Validate importance-aware memory pruning."""

    @patch("src.core.memory.base.get_session")
    async def test_deletes_low_importance(
        self,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Simulate 3 semantic + 2 owner deletions
        mock_result_sem = MagicMock()
        mock_result_sem.rowcount = 3
        mock_result_own = MagicMock()
        mock_result_own.rowcount = 2
        mock_session.execute = AsyncMock(
            side_effect=[mock_result_sem, mock_result_own],
        )
        mock_get_session.return_value = mock_session

        deleted = await mem.prune_old_memories(days=90)

        assert deleted == 5
        assert mock_session.execute.call_count == 2
        mock_session.commit.assert_called_once()

    @patch("src.core.memory.base.get_session")
    async def test_zero_deletions(
        self,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_result],
        )
        mock_get_session.return_value = mock_session

        deleted = await mem.prune_old_memories(days=30)

        assert deleted == 0


# ---------------------------------------------------------------------------
# PostgresMemory.consolidate_memories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConsolidateMemories:
    """Validate reflection / consolidation job."""

    @patch("src.core.memory.base.get_session")
    async def test_returns_none_when_no_recent(
        self,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await mem.consolidate_memories(owner_id=100)

        assert result is None

    @patch.object(PostgresMemory, "add_owner_memory", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_session")
    async def test_extracts_facts_from_reflection(
        self,
        mock_get_session: MagicMock,
        mock_add_owner: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            "User mentioned loving pasta",
            "User seems to be a morning person",
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        llm_output = (
            "(preference) Loves pasta\n"
            "(trait) Morning person\n"
        )

        with patch(
            "src.core.llm.interface.generate",
            new_callable=AsyncMock,
            return_value=llm_output,
        ):
            result = await mem.consolidate_memories(owner_id=100)

        assert result == llm_output
        assert mock_add_owner.call_count == 2

        # Verify categories were parsed correctly
        calls = mock_add_owner.call_args_list
        assert calls[0][1]["category"] == "preference"
        assert calls[1][1]["category"] == "trait"

    @patch.object(PostgresMemory, "add_owner_memory", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_session")
    async def test_skips_short_lines(
        self,
        mock_get_session: MagicMock,
        mock_add_owner: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["Some memory"]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        llm_output = "ok\n\n(fact) Real fact here\n"

        with patch(
            "src.core.llm.interface.generate",
            new_callable=AsyncMock,
            return_value=llm_output,
        ):
            await mem.consolidate_memories(owner_id=100)

        # "ok" is too short (<5 chars), only the real fact should be saved
        assert mock_add_owner.call_count == 1

    @patch.object(PostgresMemory, "add_owner_memory", new_callable=AsyncMock)
    @patch("src.core.memory.base.get_session")
    async def test_defaults_to_fact_category(
        self,
        mock_get_session: MagicMock,
        mock_add_owner: AsyncMock,
        mem: PostgresMemory,
    ) -> None:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["A memory"]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        # Line without a category tag
        llm_output = "User enjoys cooking on weekends\n"

        with patch(
            "src.core.llm.interface.generate",
            new_callable=AsyncMock,
            return_value=llm_output,
        ):
            await mem.consolidate_memories(owner_id=100)

        mock_add_owner.assert_called_once()
        assert mock_add_owner.call_args[1]["category"] == "fact"


# ---------------------------------------------------------------------------
# PostgresMemory.hybrid_search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHybridSearch:
    """Validate hybrid vector + full-text search."""

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_returns_empty_on_failure(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))
        mock_get_session.return_value = mock_session

        result = await mem.hybrid_search(
            "test", owner_id=100, contact_id=42,
        )

        assert result == []

    @patch("src.core.memory.base.get_session")
    @patch("src.core.memory.base.embed", new_callable=AsyncMock)
    async def test_respects_k_limit(
        self,
        mock_embed: AsyncMock,
        mock_get_session: MagicMock,
        mem: PostgresMemory,
    ) -> None:
        mock_embed.return_value = [0.1] * 768

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Return more rows than k
        rows = []
        for i in range(20):
            row = MagicMock()
            row.content = f"Memory {i}"
            row.importance = 5
            row.category = "general"
            row.created_at = datetime.datetime.now(datetime.timezone.utc)
            row.metadata_ = {}
            row.vec_score = 0.9 - i * 0.01
            row.fts_score = 0.1
            rows.append(row)

        mock_result = MagicMock()
        mock_result.all.return_value = rows[:10]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value = mock_session

        result = await mem.hybrid_search(
            "test", owner_id=100, k=5,
            include_owner_memories=False,
        )

        assert len(result) <= 5


# ---------------------------------------------------------------------------
# Backward-compatible build_context_for_contact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBuildContextForContact:
    """Validate the backward-compatible wrapper."""

    async def test_delegates_to_memory_singleton(self) -> None:
        with patch.object(
            memory, "get_relevant_context",
            new_callable=AsyncMock,
            return_value="mocked context",
        ) as mock_ctx:
            result = await build_context_for_contact(100, 42, "hello")

        mock_ctx.assert_called_once_with(100, 42, "hello")
        assert result == "mocked context"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """Validate the module-level memory singleton."""

    def test_memory_is_postgres_memory(self) -> None:
        assert isinstance(memory, PostgresMemory)

    def test_memory_is_same_instance(self) -> None:
        from src.core.memory import memory as mem2

        assert memory is mem2
