"""Tests for src.core.llm facade and provider system."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm import (
    embed,
    generate,
    generate_chat,
    generate_with_tools,
    provider_supports_tools,
)
from src.core.llm.base import BaseLLMProvider, GenerationResult
from src.core.llm.providers import (
    PROVIDER_REGISTRY,
    get_provider,
    register_provider,
    reset_provider,
)


@pytest.fixture(autouse=True)
def _reset_provider():
    """Ensure provider cache is cleared and default to ollama for tests."""
    reset_provider()
    with patch("src.core.config.settings") as mock_settings:
        # Mirror all real defaults so tests are deterministic
        mock_settings.llm_provider = "ollama"
        mock_settings.embedding_provider = "ollama"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_settings.ollama_model = "llama3.2:3b"
        mock_settings.ollama_embed_model = "nomic-embed-text"
        mock_settings.xai_api_key = ""
        mock_settings.xai_model = "grok-4-1-fast-reasoning"
        yield
    reset_provider()


def _make_httpx_mock(response_data: dict) -> MagicMock:
    """Build a mock httpx.AsyncClient returning response_data from .json()."""
    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _make_xai_mock(response_data: dict) -> MagicMock:
    """Build a mock xai_sdk.AsyncClient returning a response object from .chat.create().sample()."""
    # Response object returned by chat.sample()
    response = MagicMock()
    # content is the primary field used by provider
    response.content = response_data.get("content", "")
    # optional tool_calls list (SDK objects)
    response.tool_calls = response_data.get("tool_calls", [])

    # chat.handle where chat.create(...) returns an object with sample coroutine
    chat_obj = MagicMock()

    async def _sample():
        return response

    chat_obj.sample = AsyncMock(side_effect=_sample)

    # Client mock where .chat.create(...) returns chat_obj
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.create = MagicMock(return_value=chat_obj)
    return mock_client


# -------------------------------------------------------------------
# Facade tests (generate / embed via default Ollama provider)
# -------------------------------------------------------------------
@pytest.mark.asyncio
class TestGenerate:
    """Validate LLM generation wrapper delegates to provider."""

    @patch("src.core.llm.providers.ollama.httpx.AsyncClient")
    async def test_generate_returns_response(self, mock_client_cls: MagicMock) -> None:
        mock_client = _make_httpx_mock({"response": "Hey legend!"})
        mock_client_cls.return_value = mock_client

        result = await generate("test prompt")
        assert result == "Hey legend!"

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["stream"] is False

    @patch("src.core.llm.providers.ollama.httpx.AsyncClient")
    async def test_generate_with_custom_system(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client = _make_httpx_mock({"response": "summary"})
        mock_client_cls.return_value = mock_client

        result = await generate("summarize", system="Custom system")
        assert result == "summary"


@pytest.mark.asyncio
class TestEmbed:
    """Validate embedding generation wrapper delegates to provider."""

    @patch("src.core.llm.providers.ollama.AsyncOpenAI")
    async def test_embed_returns_vector(self, mock_openai_cls: MagicMock) -> None:
        fake_embedding = [0.1] * 768

        # Mock the OpenAI client's embeddings.create method
        mock_data = MagicMock()
        mock_data.embedding = fake_embedding
        mock_response = MagicMock()
        mock_response.data = [mock_data]

        mock_client = MagicMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        mock_openai_cls.return_value = mock_client

        result = await embed("test text")
        assert len(result) == 768

    @patch("src.core.llm.providers.ollama.AsyncOpenAI")
    async def test_embed_empty_fallback(self, mock_openai_cls: MagicMock) -> None:
        # Mock empty response
        mock_response = MagicMock()
        mock_response.data = []

        mock_client = MagicMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        mock_openai_cls.return_value = mock_client

        result = await embed("test")
        assert result == []


# -------------------------------------------------------------------
# Provider registry tests
# -------------------------------------------------------------------
class TestProviderRegistry:
    """Validate provider registration and factory."""

    def test_default_providers_registered(self) -> None:
        assert "ollama" in PROVIDER_REGISTRY
        assert "xai" in PROVIDER_REGISTRY

    def test_get_provider_returns_ollama_by_default(self) -> None:
        provider = get_provider()
        assert provider.name == "ollama"

    def test_get_provider_raises_for_unknown(self) -> None:
        with patch("src.core.config.settings") as mock_settings:
            mock_settings.llm_provider = "nonexistent"
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                reset_provider()
                get_provider()

    def test_register_custom_provider(self) -> None:
        class DummyProvider(BaseLLMProvider):
            @property
            def name(self) -> str:
                return "dummy"

            async def generate(self, prompt: str, system: str) -> str:
                return "dummy"

            async def embed(self, text: str) -> list[float]:
                return []

        register_provider("dummy", DummyProvider)
        assert "dummy" in PROVIDER_REGISTRY
        # Cleanup
        PROVIDER_REGISTRY.pop("dummy", None)

    def test_register_non_subclass_raises(self) -> None:
        with pytest.raises(TypeError):
            register_provider("bad", dict)  # type: ignore[arg-type]


# -------------------------------------------------------------------
# XAI provider tests
# -------------------------------------------------------------------
@pytest.mark.asyncio
class TestXAIProvider:
    """Validate xAI provider generate and embed."""

    @patch("src.core.llm.providers.xai.settings")
    @patch("src.core.llm.providers.xai.AsyncClient")
    async def test_xai_generate(
        self,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.xai_api_key = "test-key"
        mock_settings.xai_model = "grok-4-1-fast-reasoning"

        mock_client = _make_xai_mock({"content": "Grok says hi"})
        mock_client_cls.return_value = mock_client

        from src.core.llm.providers.xai import XAIProvider

        provider = XAIProvider()
        result = await provider.generate("hello", "system prompt")
        assert result == "Grok says hi"

    @patch("src.core.llm.providers.xai.settings")
    async def test_xai_generate_no_key_raises(
        self,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.xai_api_key = ""

        from src.core.llm.providers.xai import XAIProvider

        provider = XAIProvider()
        with pytest.raises(RuntimeError, match="xAI not configured"):
            await provider.generate("hello", "system")

    @patch("src.core.llm.providers.xai.AsyncClient")
    async def test_xai_embed_uses_xai_api(
        self,
        mock_client_cls: MagicMock,
    ) -> None:
        from src.core.llm.providers.xai import XAIProvider

        provider = XAIProvider()
        with pytest.raises(NotImplementedError):
            await provider.embed("test")


# -------------------------------------------------------------------
# Tool support tests
# -------------------------------------------------------------------
class TestProviderToolSupport:
    """Validate supports_tools property and facade."""

    def test_ollama_does_not_support_tools(self) -> None:
        from src.core.llm.providers.ollama import OllamaProvider

        assert OllamaProvider().supports_tools is False

    def test_xai_supports_tools(self) -> None:
        from src.core.llm.providers.xai import XAIProvider

        assert XAIProvider().supports_tools is True

    def test_facade_provider_supports_tools_default(self) -> None:
        # Default provider is Ollama
        assert provider_supports_tools() is False


@pytest.mark.asyncio
class TestGenerateWithTools:
    """Validate generate_with_tools facade."""

    @patch("src.core.llm.providers.ollama.httpx.AsyncClient")
    async def test_fallback_for_non_tool_provider(
        self,
        mock_client_cls: MagicMock,
    ) -> None:
        """Ollama provider should fall back to plain generate."""
        mock_client = _make_httpx_mock({"response": "plain answer"})
        mock_client_cls.return_value = mock_client

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ]
        result = await generate_with_tools(messages, [])
        assert isinstance(result, GenerationResult)
        assert result.text == "plain answer"
        assert result.finished is True
        assert result.tool_calls == []


@pytest.mark.asyncio
class TestXAIToolCalling:
    """Validate xAI provider tool-calling responses."""

    @patch("src.core.llm.providers.xai.settings")
    @patch("src.core.llm.providers.xai.AsyncClient")
    async def test_xai_returns_tool_calls(
        self,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.xai_api_key = "test-key"
        mock_settings.xai_model = "grok-4-1-fast-reasoning"
        # Build a fake SDK-style tool_call object
        tc = MagicMock()
        tc.id = "call_123"
        tc.function = MagicMock()
        tc.function.name = "list_contacts"
        tc.function.arguments = "{}"

        mock_client = _make_xai_mock({"content": "", "tool_calls": [tc]})
        mock_client_cls.return_value = mock_client

        from src.core.llm.providers.xai import XAIProvider

        provider = XAIProvider()
        result = await provider.generate_with_tools(
            [{"role": "user", "content": "show contacts"}],
            [{"type": "function", "function": {"name": "list_contacts"}}],
        )
        assert not result.finished
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "list_contacts"
        assert result.tool_calls[0].id == "call_123"

    @patch("src.core.llm.providers.xai.settings")
    @patch("src.core.llm.providers.xai.AsyncClient")
    async def test_xai_returns_text_when_no_tools(
        self,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.xai_api_key = "test-key"
        mock_settings.xai_model = "grok-4-1-fast-reasoning"

        mock_client = _make_xai_mock({"content": "Here you go!", "tool_calls": []})
        mock_client_cls.return_value = mock_client

        from src.core.llm.providers.xai import XAIProvider

        provider = XAIProvider()
        result = await provider.generate_with_tools(
            [{"role": "user", "content": "hi"}],
            [],
        )
        assert result.finished is True
        assert result.text == "Here you go!"
        assert result.tool_calls == []


# -------------------------------------------------------------------
# generate_chat tests (multi-turn conversation support)
# -------------------------------------------------------------------
@pytest.mark.asyncio
class TestGenerateChatFacade:
    """Validate generate_chat facade delegates to provider."""

    @patch("src.core.llm.providers.ollama.httpx.AsyncClient")
    async def test_generate_chat_ollama(self, mock_client_cls: MagicMock) -> None:
        """Ollama generate_chat should use /api/chat endpoint."""
        mock_client = _make_httpx_mock({"message": {"content": "Hey there!"}})
        mock_client_cls.return_value = mock_client

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ]
        result = await generate_chat(messages)
        assert result == "Hey there!"

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["messages"] == messages
        assert payload["stream"] is False
        assert "api/chat" in call_kwargs[0][0]


@pytest.mark.asyncio
class TestOllamaGenerateChat:
    """Validate Ollama provider generate_chat method."""

    @patch("src.core.llm.providers.ollama.httpx.AsyncClient")
    async def test_sends_messages_array(self, mock_client_cls: MagicMock) -> None:
        mock_client = _make_httpx_mock({"message": {"content": "multi-turn reply"}})
        mock_client_cls.return_value = mock_client

        from src.core.llm.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
        ]
        result = await provider.generate_chat(messages)
        assert result == "multi-turn reply"

        payload = mock_client.post.call_args[1]["json"]
        assert payload["messages"] == messages
        assert payload["stream"] is False

    @patch("src.core.llm.providers.ollama.httpx.AsyncClient")
    async def test_empty_message_returns_empty(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client = _make_httpx_mock({"message": {}})
        mock_client_cls.return_value = mock_client

        from src.core.llm.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        result = await provider.generate_chat([{"role": "user", "content": "hi"}])
        assert result == ""


@pytest.mark.asyncio
class TestXAIGenerateChat:
    """Validate xAI provider generate_chat method."""

    @patch("src.core.llm.providers.xai.settings")
    @patch("src.core.llm.providers.xai.AsyncClient")
    async def test_sends_messages_array(
        self,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.xai_api_key = "test-key"
        mock_settings.xai_model = "grok-4-1-fast-reasoning"

        mock_client = _make_xai_mock({"content": "multi-turn xai reply"})
        mock_client_cls.return_value = mock_client

        from src.core.llm.providers.xai import XAIProvider

        provider = XAIProvider()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
        ]
        result = await provider.generate_chat(messages)
        assert result == "multi-turn xai reply"

        call_kwargs = mock_client.chat.create.call_args
        # messages should be passed to chat.create as a list of SDK message objects
        assert "messages" in call_kwargs[1]
        assert len(call_kwargs[1]["messages"]) == len(messages)

    @patch("src.core.llm.providers.xai.settings")
    @patch("src.core.llm.providers.xai.AsyncClient")
    async def test_empty_choices_returns_empty(
        self,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.xai_api_key = "test-key"
        mock_settings.xai_model = "grok-4-1-fast-reasoning"

        mock_client = _make_xai_mock({"content": ""})
        mock_client_cls.return_value = mock_client

        from src.core.llm.providers.xai import XAIProvider

        provider = XAIProvider()
        result = await provider.generate_chat([{"role": "user", "content": "hi"}])
        assert result == ""


@pytest.mark.asyncio
class TestBaseLLMProviderGenerateChatFallback:
    """Validate the default generate_chat fallback on BaseLLMProvider."""

    async def test_fallback_extracts_system_and_user(self) -> None:
        class FakeProvider(BaseLLMProvider):
            @property
            def name(self) -> str:
                return "fake"

            async def generate(self, prompt: str, system: str) -> str:
                return f"system={system}|prompt={prompt}"

            async def embed(self, text: str) -> list[float]:
                return []

        provider = FakeProvider()
        messages = [
            {"role": "system", "content": "be nice"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "user", "content": "how are you?"},
        ]
        result = await provider.generate_chat(messages)
        assert "system=be nice" in result
        assert "hello" in result
        assert "how are you?" in result
