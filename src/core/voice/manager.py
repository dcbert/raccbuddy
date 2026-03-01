"""Voice manager — orchestrates STT and TTS providers.

The ``VoiceManager`` is the single entry-point for all voice operations.
It lazily initialises the configured STT and TTS providers on first use,
ensures audio format compatibility (OGG ↔ WAV conversion via ffmpeg),
and exposes concise ``transcribe`` / ``synthesize`` methods.

Usage::

    from src.core.voice import voice_manager

    result = await voice_manager.transcribe(Path("voice.oga"))
    print(result.text)

    audio = await voice_manager.synthesize("Hello, I'm Raccy!")
    print(audio.audio_path)
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from src.core.config import settings
from src.core.voice.base import (
    BaseSTTProvider,
    BaseTTSProvider,
    SynthesisResult,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)


class VoiceManager:
    """Orchestrator for speech-to-text and text-to-speech.

    Providers are created lazily based on config values.  Audio format
    conversions (OGG ↔ WAV) are handled transparently via ``ffmpeg``.
    """

    def __init__(self) -> None:
        self._stt: BaseSTTProvider | None = None
        self._tts: BaseTTSProvider | None = None

    # -- Public API ---------------------------------------------------------

    @property
    def is_enabled(self) -> bool:
        """Whether voice processing is enabled in config."""
        return settings.voice_enabled

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Handles OGG → WAV conversion automatically if needed.

        Args:
            audio_path: Path to the audio file (OGG, WAV, MP3, etc.).
            language: Optional language code to force.

        Returns:
            A :class:`TranscriptionResult`.

        Raises:
            RuntimeError: If voice is not enabled.
        """
        self._assert_enabled()
        provider = await self._get_stt()

        # Convert OGG/OGA to WAV if necessary (Whisper works best with WAV)
        wav_path = await self._ensure_wav(audio_path)
        try:
            return await provider.transcribe(wav_path, language=language)
        finally:
            # Clean up temporary WAV if we created one
            if wav_path != audio_path and wav_path.exists():
                wav_path.unlink(missing_ok=True)

    async def synthesize(
        self,
        text: str,
        *,
        output_format: str = "ogg",
        voice_preset: str | None = None,
    ) -> SynthesisResult:
        """Synthesize speech from text.

        If ``output_format`` is ``"ogg"``, the WAV output from the TTS
        provider is automatically converted to OGG Opus (the format
        Telegram expects for voice messages).

        Args:
            text: Text to synthesize.
            output_format: Desired output format (``"wav"`` or ``"ogg"``).
            voice_preset: Optional voice preset for the TTS provider.

        Returns:
            A :class:`SynthesisResult` with the final audio path.

        Raises:
            RuntimeError: If voice is not enabled.
        """
        self._assert_enabled()
        provider = await self._get_tts()

        result = await provider.synthesize(text, voice_preset=voice_preset)

        if output_format == "ogg" and result.format != "ogg":
            ogg_path = result.audio_path.with_suffix(".ogg")
            await self._convert_wav_to_ogg(result.audio_path, ogg_path)
            # Clean up the intermediate WAV
            result.audio_path.unlink(missing_ok=True)
            result = SynthesisResult(
                audio_path=ogg_path,
                sample_rate=result.sample_rate,
                duration_seconds=result.duration_seconds,
                format="ogg",
            )

        return result

    async def warmup(self) -> None:
        """Pre-load both STT and TTS models.

        Call during ``post_init`` to avoid first-request latency.
        """
        if not self.is_enabled:
            logger.debug("Voice disabled — skipping warmup")
            return

        logger.info("Warming up voice models…")
        stt = await self._get_stt()
        await stt.warmup()
        tts = await self._get_tts()
        await tts.warmup()
        logger.info("Voice models ready")

    async def cleanup(self) -> None:
        """Release all model resources."""
        if self._stt:
            await self._stt.cleanup()
            self._stt = None
        if self._tts:
            await self._tts.cleanup()
            self._tts = None
        logger.info("Voice models cleaned up")

    # -- Provider management ------------------------------------------------

    async def _get_stt(self) -> BaseSTTProvider:
        """Lazily instantiate the STT provider."""
        if self._stt is None:
            from src.core.voice.providers import get_stt_provider

            self._stt = get_stt_provider(
                settings.stt_provider,
                settings.stt_model,
            )
        return self._stt

    async def _get_tts(self) -> BaseTTSProvider:
        """Lazily instantiate the TTS provider."""
        if self._tts is None:
            from src.core.voice.providers import get_tts_provider

            self._tts = get_tts_provider(
                settings.tts_provider,
                settings.tts_model,
            )
        return self._tts

    # -- Audio conversion helpers -------------------------------------------

    async def _ensure_wav(self, audio_path: Path) -> Path:
        """Convert audio to WAV 16 kHz mono if it isn't already.

        Uses ``ffmpeg`` for reliable format conversion.

        Returns:
            Path to the WAV file (may be *audio_path* itself if already WAV).
        """
        if audio_path.suffix.lower() in (".wav",):
            return audio_path

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            prefix="raccbuddy_stt_",
            delete=False,
        ) as tmp:
            wav_path = Path(tmp.name)

        await self._run_ffmpeg(
            "-i",
            str(audio_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
            str(wav_path),
        )

        return wav_path

    async def _convert_wav_to_ogg(self, wav_path: Path, ogg_path: Path) -> None:
        """Convert WAV to OGG Opus (Telegram voice message format)."""
        await self._run_ffmpeg(
            "-i",
            str(wav_path),
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            "-vbr",
            "on",
            "-f",
            "ogg",
            str(ogg_path),
        )

    @staticmethod
    async def _run_ffmpeg(*args: str) -> None:
        """Run an ffmpeg command asynchronously.

        Raises:
            RuntimeError: If ffmpeg is not installed or the command fails.
        """
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg is required for voice processing but was not found. "
                "Install it with: apt install ffmpeg (Linux) or "
                "brew install ffmpeg (macOS)"
            ) from None

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "unknown error"
            raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}): {err_msg}")

    # -- Guards -------------------------------------------------------------

    def _assert_enabled(self) -> None:
        """Raise if voice is not enabled in config."""
        if not self.is_enabled:
            raise RuntimeError(
                "Voice processing is disabled. "
                "Set VOICE_ENABLED=true in your .env to enable it."
            )
