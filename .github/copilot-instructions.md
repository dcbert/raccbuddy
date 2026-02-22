# RaccBuddy Project Instructions for GitHub Copilot

You are helping build RaccBuddy: a privacy-first, local-only AI personal companion (raccoon mascot "Raccy") that analyzes relationships and habits from chat messages across platforms and gives proactive, personalized nudges.

## Core Rules (always follow strictly)
- Write clean, professional Python 3.12+ code only — no bloat, no magic.
- Use async (asyncio) for I/O-bound operations (Telegram, DB, LLM calls).
- Strict separation of concerns: core logic in /src/core/, handlers in /src/handlers/, plugins in /src/plugins/.
- Full type hints everywhere (use typing and Mapped from sqlalchemy).
- Keep LLM context under 2000 tokens: use summaries + pgvector retrieval, never send raw message history.
- Follow black + ruff formatting.
- Database: PostgreSQL with SQLAlchemy + pgvector for embeddings.
- LLM: Ollama (default llama3.2:3b or qwen2.5:7b).
- Privacy: all data local, no external APIs except optional Ollama/Groq.
- Personality in generated responses: friendly, slightly cheeky raccoon tone (use 🦝 emoji sparingly).

## Tech & Conventions
- Telegram bot first (python-telegram-bot v21+).
- Future plugins: extend via base plugin class.
- Error handling: log + graceful user reply, never crash bot.
- Tests: aim for unit tests in future /tests/ folder.
- Commit messages: conventional (feat:, fix:, chore:, etc.).

When suggesting code:
- Prefer minimal changes.
- Explain why if non-obvious.
- Suggest improvements for token efficiency, scalability, or readability.

Follow these rules in every suggestion, chat response, code generation, and review.