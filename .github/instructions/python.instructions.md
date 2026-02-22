# Python-specific Instructions for RaccBuddy (Professional Organization)

Apply these rules to **EVERY** `.py` file and any folder structure changes.

## 1. Overall Package Structure (MUST follow)

RaccBuddy must use this clean, scalable, professional layout:

```text
src/
└── raccbuddy/                  # ← rename src/ → src/raccbuddy/ when possible (proper package)
    ├── __init__.py
    ├── main.py                 # optional entrypoint
    ├── bot.py
    ├── api.py
    ├── summarizer.py
    ├── core/                   # ← ALL business logic (never more than 8 files flat)
    │   ├── __init__.py
    │   ├── config.py
    │   ├── db/
    │   │   ├── __init__.py
    │   │   ├── models.py       # ALL SQLAlchemy models in ONE file
    │   │   ├── session.py      # engine, sessionmaker, get_db()
    │   │   └── migrations/     # Alembic (after setup)
    │   ├── memory/
    │   │   ├── __init__.py
    │   │   ├── base.py         # PostgresMemory base class
    │   │   ├── owner.py        # owner-specific logic
    │   │   ├── contact.py      # contact-scoped logic
    │   │   └── utils.py        # shared helpers (hybrid_search, etc.)
    │   ├── llm/
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── providers/
    │   │   │   ├── __init__.py
    │   │   │   ├── ollama.py
    │   │   │   └── xai.py
    │   │   └── interface.py    # llm.py facade
    │   ├── state/
    │   │   ├── __init__.py
    │   │   └── persistent.py   # PersistentUserState, PersistentContactState
    │   ├── relationship/
    │   │   ├── __init__.py
    │   │   └── manager.py
    │   ├── habits/
    │   │   ├── __init__.py
    │   │   └── detector.py
    │   ├── sentiment/
    │   │   ├── __init__.py
    │   │   └── analyzer.py
    │   ├── skills/
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── chat.py
    │   │   └── nudge.py
    │   ├── tools/
    │   │   ├── __init__.py
    │   │   └── registry.py
    │   ├── nudges/
    │   │   ├── __init__.py
    │   │   └── engine.py
    │   ├── scheduled/
    │   │   ├── __init__.py
    │   │   └── jobs.py
    │   └── utils.py            # only truly shared helpers
    ├── handlers/
    │   ├── __init__.py
    │   ├── chat.py
    │   └── start.py
    └── plugins/                # remains flat (user drop-in files)

2. Strict Organization Rules

Never put more than 8–10 .py files directly in src/raccbuddy/core/.
Every new domain gets its own subpackage (e.g. relationship/, habits/, sentiment/, state/, etc.).
Each subpackage must contain:
__init__.py that exposes the public API
One focused file per responsibility

All SQLAlchemy models → core/db/models.py (single file)
Alembic migrations → core/db/migrations/
Keep functions short (< 40 lines)
Classes follow Single Responsibility Principle

3. Import & Code Style

Imports grouped like this (with blank lines):Python# stdlib
import logging
from datetime import datetime

# third-party
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

# local
from raccbuddy.core.db.models import Contact
from raccbuddy.core.memory import PostgresMemory
Use absolute imports everywhere (from raccbuddy.core.xxx)
Add from __future__ import annotations at the top of every file
Every new file starts with a one-sentence module docstring
Use Google-style docstrings only for public classes and functions
Logging: logger = logging.getLogger(__name__) — never print()
All DB/LLM/I/O code must be async def unless explicitly sync

4. When Generating or Refactoring Code

Put new features in the correct subpackage automatically
After creating subpackages, update all import statements in the same generation
Always keep backward-compatible public APIs (e.g. from raccbuddy.core.memory import memory still works via __init__.py)
Enforce this structure in every future edit