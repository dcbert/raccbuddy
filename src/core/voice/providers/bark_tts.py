"""Bark-based text-to-speech provider.

Uses the ``transformers`` library to run Suno Bark models locally.
Default model: ``suno/bark-small`` — configurable via ``tts_model``.

Model variants (all from HuggingFace, MIT license):
    - ``suno/bark-small`` — lighter, faster  ← **default**
    - ``suno/bark``       — full model, higher quality

Bark supports 13 languages natively and can express emotions,
laughter, pauses, and more via special tokens in the prompt.

Voice presets (built-in):
    - ``v2/en_speaker_0`` … ``v2/en_speaker_9`` (English)
    - ``v2/de_speaker_0`` … ``v2/de_speaker_9`` (German)
    - ``v2/fr_speaker_0`` … etc.
    - See https://suno-ai.notion.site/8b8e8749ed514b0cbf3f699013548683
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from functools import partial
from pathlib import Path
from typing import Any

from src.core.voice.base import BaseTTSProvider, SynthesisResult

logger = logging.getLogger(__name__)

_DEPENDENCIES_AVAILABLE: bool | None = None


def _check_dependencies() -> bool:
    """Return True if torch + transformers + scipy are importable."""
    global _DEPENDENCIES_AVAILABLE  # noqa: PLW0603
    if _DEPENDENCIES_AVAILABLE is not None:
        return _DEPENDENCIES_AVAILABLE
    try:
        import scipy  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401

        _DEPENDENCIES_AVAILABLE = True
    except ImportError:
        _DEPENDENCIES_AVAILABLE = False
    return _DEPENDENCIES_AVAILABLE


class BarkTTSProvider(BaseTTSProvider):
    """Text-to-speech via Suno Bark (HuggingFace transformers).

    Models are loaded lazily on first ``synthesize()`` call.
    Inference runs in a thread executor to keep the event loop free.

    Args:
        model_id: HuggingFace model identifier.  Defaults to
            ``suno/bark-small``.
        device: PyTorch device string.  If ``None``, auto-detected.
        default_voice_preset: Default voice preset for generation.
    """

    # Bark's native sample rate
    SAMPLE_RATE = 24_000

    def __init__(
        self,
        model_id: str = "suno/bark-small",
        device: str | None = None,
        default_voice_preset: str = "v2/en_speaker_6",
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._default_voice_preset = default_voice_preset
        self._processor: Any | None = None
        self._model: Any | None = None

    # -- BaseTTSProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "bark"

    @property
    def model_id(self) -> str:
        return self._model_id

    async def synthesize(
        self,
        text: str,
        *,
        output_path: Path | None = None,
        voice_preset: str | None = None,
    ) -> SynthesisResult:
        """Synthesize speech from text using Bark.

        Args:
            text: Input text.  Bark supports up to ~13 seconds of audio
                per generation.  Longer texts are split into sentences.
            output_path: Where to save the WAV file.  If ``None``, a
                temp file is created in the configured temp directory.
            voice_preset: Bark voice preset (e.g. ``"v2/en_speaker_6"``).

        Returns:
            A :class:`SynthesisResult` pointing to the generated WAV.

        Raises:
            ImportError: If dependencies are missing.
        """
        self._ensure_dependencies()
        await self._ensure_loaded()

        preset = voice_preset or self._default_voice_preset

        loop = asyncio.get_running_loop()
        audio_array, sample_rate = await loop.run_in_executor(
            None,
            partial(self._generate_audio, text, preset),
        )

        # Determine output path
        if output_path is None:
            fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="raccbuddy_tts_")
            output_path = Path(tmp)
            # Close the fd — scipy will open the file itself
            import os

            os.close(fd)

        # Write WAV file
        await loop.run_in_executor(
            None,
            partial(self._write_wav, output_path, audio_array, sample_rate),
        )

        duration = len(audio_array) / sample_rate

        logger.info(
            "Bark synthesis complete: model=%s, duration=%.1fs, preset=%s, path=%s",
            self._model_id,
            duration,
            preset,
            output_path,
        )

        return SynthesisResult(
            audio_path=output_path,
            sample_rate=sample_rate,
            duration_seconds=duration,
            format="wav",
        )

    async def warmup(self) -> None:
        """Pre-load the Bark model."""
        self._ensure_dependencies()
        await self._ensure_loaded()
        logger.info("Bark model warmed up: %s", self._model_id)

    async def cleanup(self) -> None:
        """Release model resources."""
        if self._model is not None:
            del self._model
            self._model = None
        if self._processor is not None:
            del self._processor
            self._processor = None
        logger.info("Bark model unloaded: %s", self._model_id)

    # -- Internal helpers ---------------------------------------------------

    def _ensure_dependencies(self) -> None:
        if not _check_dependencies():
            raise ImportError(
                "Voice TTS requires 'torch', 'transformers', and 'scipy'. "
                "Install them with: pip install torch transformers scipy"
            )

    async def _ensure_loaded(self) -> None:
        if self._model is not None and self._processor is not None:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_model)

    def _load_model(self) -> None:
        """Synchronous model loading — called inside executor."""
        import torch
        from transformers import AutoProcessor, BarkModel

        device = self._device
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        logger.info("Loading Bark model: %s on %s", self._model_id, device)

        self._processor = AutoProcessor.from_pretrained(self._model_id)
        self._model = BarkModel.from_pretrained(
            self._model_id,
            torch_dtype=torch.float32,  # Bark doesn't support fp16 well
        ).to(device)

        logger.info("Bark model loaded successfully: %s", self._model_id)

    def _generate_audio(
        self,
        text: str,
        voice_preset: str,
    ) -> tuple[Any, int]:
        """Run Bark generation (synchronous, called in executor).

        Returns:
            Tuple of (audio_numpy_array, sample_rate).
        """
        import numpy as np

        inputs = self._processor(text, voice_preset=voice_preset)

        # Move inputs to model device
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        audio_output = self._model.generate(**inputs)

        # Bark returns shape (1, seq_len) — squeeze to 1D
        audio_array = audio_output.cpu().numpy().squeeze()

        # Normalize to [-1, 1] range for WAV writing
        if audio_array.dtype != np.float32:
            audio_array = audio_array.astype(np.float32)
        max_val = np.abs(audio_array).max()
        if max_val > 0:
            audio_array = audio_array / max_val

        return audio_array, self.SAMPLE_RATE

    @staticmethod
    def _write_wav(path: Path, audio: Any, sample_rate: int) -> None:
        """Write a numpy audio array to a WAV file."""
        import numpy as np
        from scipy.io import wavfile

        # Convert float32 [-1, 1] → int16 for broad compatibility
        audio_int16 = (audio * 32767).astype(np.int16)
        wavfile.write(str(path), sample_rate, audio_int16)
