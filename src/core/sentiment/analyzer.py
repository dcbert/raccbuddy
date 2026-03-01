"""Lightweight mood / sentiment detection via LLM provider.

Keeps LLM calls cheap by using a short, structured prompt and parsing
the response into a mood label + numeric valence.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Allowed mood labels
_MOODS = frozenset(
    {
        "happy",
        "sad",
        "angry",
        "anxious",
        "excited",
        "neutral",
        "frustrated",
        "grateful",
        "lonely",
        "loving",
    }
)

# Valence lookup (fallback when the model doesn't return a number)
_VALENCE_MAP: dict[str, float] = {
    "happy": 0.8,
    "excited": 0.9,
    "grateful": 0.7,
    "loving": 0.85,
    "neutral": 0.0,
    "sad": -0.6,
    "lonely": -0.5,
    "anxious": -0.4,
    "frustrated": -0.5,
    "angry": -0.7,
}


class MoodAnalyzer:
    """Detect mood and valence from a message snippet."""

    async def detect_mood(self, text: str) -> tuple[str, float]:
        """Classify mood of *text* and return ``(label, valence)``."""
        from src.core.llm.providers import get_provider

        snippet = text[:300].strip()
        if not snippet:
            return "neutral", 0.0

        prompt = (
            "Classify the mood of the following message into EXACTLY ONE word from this list: "
            "happy, sad, angry, anxious, excited, neutral, frustrated, grateful, lonely, loving.\n"
            "Then on a new line, give a valence score from -1.0 to 1.0.\n"
            "Reply with ONLY two lines: the mood word and the number.\n\n"
            f"Message: {snippet}"
        )

        try:
            provider = get_provider()
            raw = await provider.generate(
                prompt,
                system="You are a sentiment classifier. Output only the mood word and valence number.",
            )
            return self._parse_response(raw)
        except Exception:
            logger.warning(
                "Mood detection failed, defaulting to neutral", exc_info=True
            )
            return "neutral", 0.0

    async def detect_and_store(
        self,
        text: str,
        owner_id: int,
        contact_id: int | None = None,
    ) -> tuple[str, float]:
        """Detect mood, persist a ``MoodEntry``, and return the result."""
        mood, valence = await self.detect_mood(text)

        try:
            from src.core.db.models import MoodEntry
            from src.core.db.session import get_session

            entry = MoodEntry(
                owner_id=owner_id,
                contact_id=contact_id,
                mood=mood,
                valence=valence,
                message_snippet=text[:200],
            )
            async with get_session() as session:
                session.add(entry)
                await session.commit()
        except Exception:
            logger.warning("Failed to persist mood entry", exc_info=True)

        return mood, valence

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> tuple[str, float]:
        """Extract mood label and valence from LLM output."""
        lines = [ln.strip().lower() for ln in raw.strip().splitlines() if ln.strip()]

        mood = "neutral"
        valence = 0.0

        if lines:
            candidate = lines[0].strip(".- ")
            if candidate in _MOODS:
                mood = candidate

        if len(lines) >= 2:
            try:
                valence = max(-1.0, min(1.0, float(lines[1])))
            except ValueError:
                valence = _VALENCE_MAP.get(mood, 0.0)
        else:
            valence = _VALENCE_MAP.get(mood, 0.0)

        return mood, valence


# Module-level singleton
mood_analyzer = MoodAnalyzer()
