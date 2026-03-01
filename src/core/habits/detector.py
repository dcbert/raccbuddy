"""Real habit detection from messaging patterns and LLM extraction.

Two detection strategies:
1. **Frequency analysis** — find time-of-day and day-of-week clusters.
2. **LLM pattern extraction** — scan recent summaries for behavioural patterns.
"""

from __future__ import annotations

import datetime
import logging
from collections import Counter

from sqlalchemy import select

logger = logging.getLogger(__name__)

_MIN_MESSAGES_FOR_PATTERN = 5
_DOW_LABELS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


class HabitDetector:
    """Detect recurring behavioural patterns from message data."""

    async def detect_frequency_habits(self, owner_id: int) -> list[dict]:
        """Analyse message timestamps for recurring patterns."""
        from src.core.db.models import Message
        from src.core.db.session import get_session

        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=30
        )

        async with get_session() as session:
            result = await session.execute(
                select(Message.timestamp).where(
                    Message.chat_id == owner_id,
                    Message.timestamp >= cutoff,
                )
            )
            timestamps = [row[0] for row in result.all()]

        if len(timestamps) < _MIN_MESSAGES_FOR_PATTERN:
            return []

        habits: list[dict] = []

        # --- Time-of-day clustering ---
        hour_counts: Counter[str] = Counter()
        for ts in timestamps:
            hour = ts.hour
            if 5 <= hour < 12:
                bucket = "morning"
            elif 12 <= hour < 17:
                bucket = "afternoon"
            elif 17 <= hour < 22:
                bucket = "evening"
            else:
                bucket = "night"
            hour_counts[bucket] += 1

        total = sum(hour_counts.values())
        for bucket, count in hour_counts.most_common(2):
            ratio = count / total
            if ratio >= 0.35:
                habits.append(
                    {
                        "trigger": f"Most active in the {bucket}",
                        "category": "timing",
                        "frequency": round(ratio, 2),
                        "confidence": min(1.0, ratio + 0.1),
                        "suggestion": f"You tend to chat most in the {bucket} — plan deep work around that!",
                    }
                )

        # --- Day-of-week clustering ---
        dow_counts: Counter[int] = Counter()
        for ts in timestamps:
            dow_counts[ts.weekday()] += 1

        for dow, count in dow_counts.most_common(2):
            ratio = count / total
            if ratio >= 0.20:
                day_name = _DOW_LABELS[dow]
                habits.append(
                    {
                        "trigger": f"Heavy messaging on {day_name}s",
                        "category": "day_pattern",
                        "frequency": round(ratio, 2),
                        "confidence": min(1.0, ratio + 0.05),
                        "suggestion": f"You're especially chatty on {day_name}s.",
                    }
                )

        return habits

    async def detect_llm_habits(self, owner_id: int) -> list[dict]:
        """Use the LLM to extract behavioural patterns from recent summaries."""
        from src.core.db.models import Summary
        from src.core.db.session import get_session
        from src.core.llm.interface import generate

        cutoff = datetime.date.today() - datetime.timedelta(days=7)

        async with get_session() as session:
            result = await session.execute(
                select(Summary.summary_text)
                .where(
                    Summary.date >= cutoff,
                )
                .order_by(Summary.date.desc())
                .limit(10)
            )
            texts = result.scalars().all()

        if len(texts) < 2:
            return []

        block = "\n".join(f"- {t[:200]}" for t in texts)[:1500]

        prompt = (
            "Below are recent conversation summaries.\n"
            "Identify 1–3 recurring habits or behavioural patterns "
            "(e.g. 'always vents about work on Wednesdays', 'mentions gym regularly').\n"
            "Output each on its own line in the format:\n"
            "HABIT: <description> | SUGGESTION: <actionable tip>\n\n"
            f"Summaries:\n{block}"
        )

        try:
            raw = await generate(
                prompt,
                system="You are a pattern-detection assistant. Output only habit lines.",
            )
            return self._parse_llm_habits(raw)
        except Exception:
            logger.warning("LLM habit detection failed", exc_info=True)
            return []

    async def run_full_detection(self, owner_id: int) -> int:
        """Run all detection strategies and persist new habits."""
        freq_habits = await self.detect_frequency_habits(owner_id)
        llm_habits = await self.detect_llm_habits(owner_id)

        all_habits = freq_habits + llm_habits
        saved = 0

        for h in all_habits:
            saved += await self._persist_habit(owner_id, h)

        if saved:
            logger.info("Detected %d new habits for owner %d", saved, owner_id)
        return saved

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_llm_habits(raw: str) -> list[dict]:
        """Parse LLM output into habit dicts."""
        habits: list[dict] = []
        for line in raw.strip().splitlines():
            line = line.strip().lstrip("- ")
            if "HABIT:" not in line:
                continue

            parts = line.split("|")
            trigger = parts[0].replace("HABIT:", "").strip()
            suggestion = ""
            if len(parts) >= 2:
                suggestion = parts[1].replace("SUGGESTION:", "").strip()

            if trigger:
                habits.append(
                    {
                        "trigger": trigger[:200],
                        "category": "llm_detected",
                        "frequency": 0.0,
                        "confidence": 0.6,
                        "suggestion": suggestion[:500] or None,
                    }
                )
        return habits

    @staticmethod
    async def _persist_habit(owner_id: int, habit: dict) -> int:
        """Insert a habit if it doesn't already exist (by trigger text)."""
        from src.core.db.models import Habit
        from src.core.db.session import get_session

        async with get_session() as session:
            existing = await session.execute(
                select(Habit).where(
                    Habit.owner_id == owner_id,
                    Habit.trigger == habit["trigger"],
                )
            )
            if existing.scalar_one_or_none():
                return 0

            row = Habit(
                owner_id=owner_id,
                trigger=habit["trigger"],
                category=habit.get("category", "general"),
                frequency=habit.get("frequency", 0.0),
                confidence=habit.get("confidence", 0.5),
                suggestion=habit.get("suggestion"),
            )
            session.add(row)
            await session.commit()
        return 1


# Module-level singleton
habit_detector = HabitDetector()
