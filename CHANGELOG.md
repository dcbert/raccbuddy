# Changelog

All notable changes to RaccBuddy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-beta] - 2026-02-22

### 🎉 Initial Beta Release

**RaccBuddy is ready for beta testing!** This release includes all core features for a privacy-first, local AI personal companion.

### Added

#### Core Features
- **Telegram bot integration** with natural conversation support
- **WhatsApp bridge** via Node.js service (whatsapp-web.js)
- **REST API** for external platform integrations (`POST /api/messages`)
- **PostgreSQL database** with pgvector for semantic search
- **Multi-LLM support**: Ollama (local) and xAI Grok (cloud with function calling)
- **Smart memory system** with embedding-based retrieval
- **Automatic conversation summarization** to keep context efficient
- **Owner memory deduplication** (cosine similarity > 0.9)

#### Relationship & Habits
- **Dynamic relationship scoring** with four weighted signals:
  - Message frequency (30%)
  - Recency (30%)
  - Sentiment (25%)
  - Reply rate (15%)
- **Mood/sentiment detection** on every message
- **Habit detection** combining frequency analysis and LLM pattern extraction
- **Contact management** across multiple platforms
- **Relationship score change history** tracking

#### Proactive Features
- **Nudge engine** with configurable check intervals
- **Built-in nudge skills**:
  - Idle detection (activity-based check-ins)
  - Contact quiet alerts (reminds to reach out)
  - Evening check-ins
  - Habit tracking reminders
- **Custom nudge skills** via extensible system (see `nudges/` folder)

#### LLM & AI
- **Function calling support** for advanced providers (xAI)
- **LLM Tools**:
  - `analyze_contact` - Run relationship analysis
  - `get_insights` - Get conversation insights
  - `get_relationship_score` - Retrieve score (0-100)
  - `list_contacts` - List all contacts
  - `summarize_contact` - Summarize recent history
  - `schedule_message` - Schedule future messages
- **Token-efficient context management** (max 2000 tokens)
- **Semantic embedding search** with retrieval

#### Extensibility
- **Chat skills system** for customizing conversation behavior
- **Nudge skills system** for proactive reminders
- **Auto-discovery** of custom skills from `skills/` and `nudges/` folders
- **Plugin base class** for future platform extensions

#### Infrastructure
- **Docker Compose setup** with PostgreSQL + pgvector
- **Multi-stage Dockerfile** for optimized builds
- **Alembic migrations** for database schema management
- **DB-backed persistent state** (survives restarts)
- **Scheduled jobs system** with database persistence
- **Health check endpoint** (`GET /health`)
- **Comprehensive test suite** with pytest

#### Developer Experience
- **Full type hints** throughout codebase (Python 3.12+)
- **Async/await** for all I/O operations
- **Black + Ruff** code formatting
- **Comprehensive documentation** (README, inline docs)
- **Example skills** in `skills/` and `nudges/` folders
- **GitHub Copilot instructions** for contributors

### Configuration
- **Environment-based configuration** via `.env` file
- **Flexible LLM provider selection** (ollama, xai)
- **Configurable token limits** and performance tuning
- **Adjustable relationship scoring weights**
- **Memory retention policies** (90-day default for owner memories)

### Documentation
- Complete README with installation instructions
- Troubleshooting guide
- API reference
- Security & Privacy section
- FAQ
- Contributing guidelines
- Skills & extensibility docs

### Security & Privacy
- **Local-first architecture** (all data on your machine)
- **No cloud dependencies** (unless you choose xAI)
- **Proper .gitignore** for sensitive files
- **Non-root Docker user** for security
- **No hardcoded credentials**

---

## [Unreleased]

### Planned for Future Releases

#### Phase 6 (Voice Support)
- Voice message transcription
- Text-to-speech responses
- Audio file handling

#### Phase 7 (Multi-User)
- Family/team mode support
- Per-user state management
- Access control system

#### Phase 8 (More Platforms)
- Signal bridge
- Discord integration
- Matrix server support
- iMessage bridge (macOS)

#### Phase 9 (Web Dashboard)
- Web UI for insights
- Relationship visualization
- Habit tracking dashboard
- Configuration interface

#### Phase 10 (Community)
- Plugin marketplace
- Skill sharing platform
- Community nudge library

---

## Version History

- **0.1.0-beta** (2026-02-22) - Initial beta release

---

**Note**: This is a beta release. While all core features are implemented and tested, expect occasional updates and improvements. Please report bugs and feedback via [GitHub Issues](https://github.com/dcbert/raccbuddy/issues).
