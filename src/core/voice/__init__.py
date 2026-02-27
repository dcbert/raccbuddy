"""Voice processing module — speech-to-text and text-to-speech.

Public API
----------
- ``voice_manager`` — singleton :class:`VoiceManager` for transcription + synthesis.
- ``transcribe(audio_path)`` — convenience shortcut.
- ``synthesize(text)``       — convenience shortcut.

Provider architecture mirrors ``src/core/llm/``: abstract base classes in
``base.py``, concrete implementations in ``providers/``, and a manager that
orchestrates lazy model loading + provider selection based on config.

Both STT and TTS providers are fully swappable via config:
    ``stt_provider`` / ``stt_model`` and ``tts_provider`` / ``tts_model``.
"""

from __future__ import annotations

from src.core.voice.manager import VoiceManager

voice_manager = VoiceManager()

# Convenience shortcuts
transcribe = voice_manager.transcribe
synthesize = voice_manager.synthesize

__all__ = [
    "VoiceManager",
    "voice_manager",
    "transcribe",
    "synthesize",
]
