# Custom Nudge Skills

Drop your custom nudge skill files here. RaccBuddy will auto-load any `.py`
file in this directory at startup.

## How to create a nudge skill

1. Create a new `.py` file in this folder (e.g. `weekend_checkin.py`).
2. Subclass `BaseNudgeSkill` and implement the required methods.
3. Call `register_skill()` at module level so it registers on import.

### Template

```python
"""My custom nudge skill."""

from src.core.skills.base import BaseNudgeSkill, NudgeCheck, register_skill


class WeekendCheckinSkill(BaseNudgeSkill):
    """Send a chill nudge on weekends."""

    name = "weekend_checkin"
    trigger = "weekend"
    default_prompt = (
        "It's the weekend! Send a relaxed raccoon check-in. Max 2 sentences."
    )

    @property
    def cooldown_minutes(self) -> int:
        return 60 * 12  # once per 12 hours

    async def should_fire(self, owner_id: int) -> NudgeCheck:
        import datetime

        if datetime.datetime.now(datetime.timezone.utc).weekday() >= 5:
            return NudgeCheck(fire=True, reason="It's the weekend")
        return NudgeCheck(fire=False, reason="Not a weekend day")


# Register on import
register_skill(WeekendCheckinSkill())
```

### Key rules

- **`should_fire()` must NOT call the LLM.** Only use DB queries, timestamps,
  or other cheap checks. The LLM is invoked automatically when `fire=True`.
- Set `cooldown_minutes` to prevent spam (default is 120 min).
- `default_prompt` can contain `{placeholders}` — fill them via
  `NudgeCheck(context={"key": "value"})`.

### Available DB helpers

```python
from src.core.db import (
    count_messages_since,
    count_messages_from_contact_since,
    get_all_contacts_all_platforms,
    get_last_message_ts_for_contact,
    get_all_habits,
)
```

See `src/core/skills/base.py` for the full `BaseNudgeSkill` API.
