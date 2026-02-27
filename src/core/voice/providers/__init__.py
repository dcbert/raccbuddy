"""Voice provider registry.

Mirrors ``src/core/llm/providers/__init__.py`` — maps config names to
concrete provider classes.  New providers are registered here and
selected via ``stt_provider`` / ``tts_provider`` in config.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.voice.base import BaseSTTProvider, BaseTTSProvider

logger = logging.getLogger(__name__)


def get_stt_provider(provider_name: str, model_id: str) -> BaseSTTProvider:
    """Instantiate and return the configured STT provider.

    Args:
        provider_name: Provider key from config (e.g. ``"whisper"``).
        model_id: HuggingFace model ID (e.g. ``"openai/whisper-small"``).

    Returns:
        A concrete :class:`BaseSTTProvider` instance.

    Raises:
        ValueError: If the provider name is unknown.
        ImportError: If required dependencies are missing.
    """
    if provider_name == "whisper":
        from src.core.voice.providers.whisper_stt import WhisperSTTProvider

        return WhisperSTTProvider(model_id=model_id)

    raise ValueError(
        f"Unknown STT provider: {provider_name!r}. "
        f"Available: 'whisper'.  Add new providers in "
        f"src/core/voice/providers/__init__.py"
    )


def get_tts_provider(provider_name: str, model_id: str) -> BaseTTSProvider:
    """Instantiate and return the configured TTS provider.

    Args:
        provider_name: Provider key from config (e.g. ``"bark"``).
        model_id: HuggingFace model ID (e.g. ``"suno/bark-small"``).

    Returns:
        A concrete :class:`BaseTTSProvider` instance.

    Raises:
        ValueError: If the provider name is unknown.
        ImportError: If required dependencies are missing.
    """
    if provider_name == "bark":
        from src.core.voice.providers.bark_tts import BarkTTSProvider

        return BarkTTSProvider(model_id=model_id)

    raise ValueError(
        f"Unknown TTS provider: {provider_name!r}. "
        f"Available: 'bark'.  Add new providers in "
        f"src/core/voice/providers/__init__.py"
    )
