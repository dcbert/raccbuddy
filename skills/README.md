# Custom Chat Skills

Drop your custom chat skill files here. RaccBuddy will auto-load any `.py`
file in this directory at startup.

## What are chat skills?

Chat skills let you personalise how RaccBuddy behaves during conversation.
A skill can:

- **Add to the system prompt** — shape the raccoon's personality or focus.
- **Add new tools** — give the LLM new abilities it can call autonomously.
- **Pre-process messages** — transform user input before it reaches the LLM.
- **Post-process replies** — modify the LLM's output before sending it.

## How to create a chat skill

1. Create a new `.py` file in this folder (e.g. `mood_tracker.py`).
2. Subclass `BaseChatSkill` and implement the required properties.
3. Override any optional hooks you need.
4. Call `register_chat_skill()` at module level.

### Minimal template (system prompt only)

```python
"""Add daily affirmation vibes to every reply."""

from src.core.skills.chat import BaseChatSkill, register_chat_skill


class AffirmationSkill(BaseChatSkill):
    name = "affirmation"
    description = "Add a positive affirmation to replies."
    system_prompt_fragment = (
        "End every reply with a brief, uplifting affirmation."
    )


register_chat_skill(AffirmationSkill())
```

### Template with a custom tool

```python
"""Let the LLM roll dice during conversations."""

from src.core.skills.chat import BaseChatSkill, register_chat_skill
import random


class DiceRollSkill(BaseChatSkill):
    name = "dice_roll"
    description = "Roll dice when the user asks."

    @property
    def tool_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "roll_dice",
                    "description": "Roll one or more dice.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sides": {
                                "type": "integer",
                                "description": "Number of sides (default 6).",
                            },
                            "count": {
                                "type": "integer",
                                "description": "How many dice to roll (default 1).",
                            },
                        },
                    },
                },
            },
        ]

    async def execute_tool(self, tool_name, arguments, owner_id):
        sides = arguments.get("sides", 6)
        count = arguments.get("count", 1)
        rolls = [random.randint(1, sides) for _ in range(count)]
        return f"Rolled {count}d{sides}: {rolls} (total: {sum(rolls)})"


register_chat_skill(DiceRollSkill())
```

### Template with pre/post processing

```python
"""Translate common abbreviations before the LLM sees them."""

from src.core.skills.chat import BaseChatSkill, register_chat_skill


class SlangExpanderSkill(BaseChatSkill):
    name = "slang_expander"
    description = "Expand common chat abbreviations."

    async def pre_process(self, message, owner_id):
        replacements = {"brb": "be right back", "ttyl": "talk to you later"}
        for short, full in replacements.items():
            message = message.replace(short, full)
        return message


register_chat_skill(SlangExpanderSkill())
```

## Available hooks

| Hook                     | When it runs                        | Required? |
|--------------------------|-------------------------------------|-----------|
| `name`                   | Always (identifier)                 | Yes       |
| `description`            | `/skills` command listing           | Yes       |
| `system_prompt_fragment` | Prepended to system prompt          | No        |
| `tool_schemas`           | Added to LLM tool list              | No        |
| `execute_tool()`         | When LLM calls a skill-defined tool | No        |
| `pre_process()`          | Before LLM generation               | No        |
| `post_process()`         | After LLM generation                | No        |

See `src/core/skills/chat.py` for the full `BaseChatSkill` API.
