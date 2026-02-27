"""Whisper-based speech-to-text provider.

Uses the ``transformers`` library to run OpenAI Whisper models locally.
Default model: ``openai/whisper-small`` — configurable via ``stt_model``.

Model variants (all from HuggingFace, Apache-2.0 license):
    - ``openai/whisper-tiny``   — 39M params, fastest, lowest accuracy
    - ``openai/whisper-base``   — 74M params
    - ``openai/whisper-small``  — 244M params  ← **default** (best trade-off)
    - ``openai/whisper-medium`` — 769M params
    - ``openai/whisper-large-v3`` — 1.55B params, highest accuracy
    - ``openai/whisper-large-v3-turbo`` — distilled, fast + accurate

All models support 99+ languages with automatic language detection.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from pathlib import Path
from typing import Any

from src.core.voice.base import BaseSTTProvider, TranscriptionResult

logger = logging.getLogger(__name__)

# Lazy imports — only fail when the provider is actually used
_pipeline: Any | None = None
_DEPENDENCIES_AVAILABLE: bool | None = None


def _check_dependencies() -> bool:
    """Return True if torch + transformers are importable."""
    global _DEPENDENCIES_AVAILABLE  # noqa: PLW0603
    if _DEPENDENCIES_AVAILABLE is not None:
        return _DEPENDENCIES_AVAILABLE
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401

        _DEPENDENCIES_AVAILABLE = True
    except ImportError:
        _DEPENDENCIES_AVAILABLE = False
    return _DEPENDENCIES_AVAILABLE


class WhisperSTTProvider(BaseSTTProvider):
    """Speech-to-text via OpenAI Whisper (HuggingFace transformers).

    Models are loaded lazily on first ``transcribe()`` call to avoid
    startup overhead.  Inference runs in a thread executor so the
    async event loop is never blocked.

    Args:
        model_id: HuggingFace model identifier.  Defaults to
            ``openai/whisper-small``.
        device: PyTorch device string (``"cpu"``, ``"cuda"``, ``"mps"``).
            If ``None``, auto-detected.
    """

    def __init__(
        self,
        model_id: str = "openai/whisper-small",
        device: str | None = None,
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._pipe: Any | None = None

    # -- BaseSTTProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "whisper"

    @property
    def model_id(self) -> str:
        return self._model_id

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file using Whisper.

        Args:
            audio_path: Path to the audio file.  WAV 16 kHz mono is
                ideal, but Whisper's feature extractor handles resampling.
            language: Optional ISO-639-1 code to force (e.g. ``"en"``).

        Returns:
            A :class:`TranscriptionResult` with text and detected language.

        Raises:
            ImportError: If ``torch`` or ``transformers`` are not installed.
            FileNotFoundError: If *audio_path* does not exist.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._ensure_dependencies()
        await self._ensure_loaded()

        generate_kwargs: dict[str, Any] = {}
        if language:
            generate_kwargs["language"] = language

        loop = asyncio.get_running_loop()
        call_kwargs: dict[str, Any] = {"return_timestamps": True}
        if generate_kwargs:
            call_kwargs["generate_kwargs"] = generate_kwargs

        raw = await loop.run_in_executor(
            None,
            partial(self._pipe, str(audio_path), **call_kwargs),
        )

        text = raw.get("text", "").strip()
        chunks = raw.get("chunks", [])

        segments = [
            {
                "start": c.get("timestamp", (0,))[0],
                "end": c.get("timestamp", (0, 0))[1],
                "text": c.get("text", ""),
            }
            for c in chunks
        ]

        # Whisper doesn't directly return language in pipeline mode; we
        # record the forced language or leave it blank for auto-detect.
        detected_lang = language or ""

        logger.info(
            "Whisper transcription complete: model=%s, chars=%d, lang=%s",
            self._model_id,
            len(text),
            detected_lang or "auto",
        )

        return TranscriptionResult(
            text=text,
            language=detected_lang,
            confidence=1.0,  # Whisper pipeline doesn't expose per-utterance conf
            segments=segments,
        )

    async def warmup(self) -> None:
        """Pre-load the Whisper model into memory."""
        self._ensure_dependencies()
        await self._ensure_loaded()
        logger.info("Whisper model warmed up: %s", self._model_id)

    async def cleanup(self) -> None:
        """Release model resources."""
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            logger.info("Whisper model unloaded: %s", self._model_id)

    # -- Internal helpers ---------------------------------------------------

    def _ensure_dependencies(self) -> None:
        """Raise ImportError with a helpful message if deps are missing."""
        if not _check_dependencies():
            raise ImportError(
                "Voice STT requires 'torch' and 'transformers'. "
                "Install them with: pip install torch transformers"
            )

    async def _ensure_loaded(self) -> None:
        """Lazily load the Whisper pipeline (runs in executor)."""
        if self._pipe is not None:
            return

        loop = asyncio.get_running_loop()
        self._pipe = await loop.run_in_executor(None, self._load_pipeline)

    def _load_pipeline(self) -> Any:
        """Synchronous model loading — called inside executor."""
        import torch
        from transformers import pipeline

        device = self._device
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        # Use float16 on GPU for faster inference, float32 on CPU
        torch_dtype = torch.float16 if device != "cpu" else torch.float32

        logger.info(
            "Loading Whisper model: %s on %s (%s)",
            self._model_id,
            device,
            torch_dtype,
        )

        pipe = pipeline(
            "automatic-speech-recognition",
            model=self._model_id,
            device=device,
            torch_dtype=torch_dtype,
        )

        logger.info("Whisper model loaded successfully: %s", self._model_id)
        return pipe
