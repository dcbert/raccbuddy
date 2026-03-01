"""Abstract base classes for voice providers.

Every STT provider must inherit from :class:`BaseSTTProvider` and implement
``transcribe()``.  Every TTS provider must inherit from :class:`BaseTTSProvider`
and implement ``synthesize()``.

Providers are registered in ``providers/__init__.py`` and selected via config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptionResult:
    """Result of a speech-to-text transcription.

    Attributes:
        text: The transcribed text.
        language: Detected or forced language code (e.g. ``"en"``).
        confidence: Optional confidence score in ``[0, 1]``.
        segments: Optional list of timestamped segments.
    """

    text: str = ""
    language: str = ""
    confidence: float = 0.0
    segments: list[dict[str, object]] = field(default_factory=list)


@dataclass
class SynthesisResult:
    """Result of a text-to-speech synthesis.

    Attributes:
        audio_path: Path to the generated audio file.
        sample_rate: Sample rate of the generated audio (Hz).
        duration_seconds: Duration of the generated audio.
        format: Audio format (e.g. ``"wav"``, ``"ogg"``).
    """

    audio_path: Path
    sample_rate: int = 24_000
    duration_seconds: float = 0.0
    format: str = "wav"


class BaseSTTProvider(ABC):
    """Contract that every speech-to-text provider must fulfil."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g. ``"whisper"``)."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """HuggingFace model ID or local path."""
        ...

    @abstractmethod
    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to the audio file (WAV preferred, 16 kHz mono).
            language: Optional ISO language code to force (e.g. ``"en"``).

        Returns:
            A :class:`TranscriptionResult` with the transcribed text.
        """
        ...

    async def warmup(self) -> None:
        """Optional: pre-load models to avoid first-call latency."""

    async def cleanup(self) -> None:
        """Optional: release model resources."""


class BaseTTSProvider(ABC):
    """Contract that every text-to-speech provider must fulfil."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g. ``"bark"``)."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """HuggingFace model ID or local path."""
        ...

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        output_path: Path | None = None,
        voice_preset: str | None = None,
    ) -> SynthesisResult:
        """Synthesize speech from text.

        Args:
            text: The text to convert to speech.
            output_path: Optional path for the output file.  If ``None``,
                a temp file is created.
            voice_preset: Optional voice preset identifier.

        Returns:
            A :class:`SynthesisResult` with the path to the audio file.
        """
        ...

    async def warmup(self) -> None:
        """Optional: pre-load models to avoid first-call latency."""

    async def cleanup(self) -> None:
        """Optional: release model resources."""
