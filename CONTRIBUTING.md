# Contributing to RaccBuddy

Thank you for your interest in contributing to RaccBuddy! 🦝

This document provides guidelines and instructions for contributing to the project.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Areas We Need Help](#areas-we-need-help)

---

## Code of Conduct

### Our Standards

- **Be respectful** and considerate in all interactions
- **Welcome newcomers** and help them get started
- **Focus on what's best** for the community and project
- **Accept constructive criticism** gracefully
- **Show empathy** towards other community members

### Unacceptable Behavior

- Harassment, discrimination, or unwelcoming conduct
- Trolling, insulting comments, or personal attacks
- Publishing private information without permission
- Any conduct that would be inappropriate in a professional setting

If you witness or experience unacceptable behavior, please contact the maintainers.

---

## Getting Started

### Before You Begin

1. **Check existing issues** to see if your idea/bug is already being discussed
2. **Search closed PRs** to avoid duplicating work
3. **Read the documentation** (README, inline docs, instruction files)
4. **Join discussions** to propose significant changes before implementing

### Ways to Contribute

- 🐛 **Report bugs** - Found something broken? Let us know!
- 💡 **Suggest features** - Have an idea? Open a discussion!
- 📝 **Improve documentation** - Typos, clarity, examples
- 🧪 **Write tests** - Expand coverage, add integration tests
- 🔌 **Build integrations** - New platform bridges, LLM providers
- 🎯 **Create skills** - Custom nudges, chat behaviors
- 🔒 **Security audits** - Review code for vulnerabilities
- ⚡ **Optimize performance** - Make things faster, more efficient

---

## Development Setup

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/raccbuddy.git
cd raccbuddy
```

### 2. Create a Virtual Environment

```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install Development Tools

```bash
pip install black ruff mypy pytest pytest-asyncio
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your test bot token and settings
```

### 5. Start Services

```bash
# Start PostgreSQL
docker compose up -d db

# Run migrations
alembic upgrade head

# (Optional) Install Ollama
# Download from https://ollama.ai
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

### 6. Run Tests

```bash
pytest tests/ -v
```

---

## Making Changes

### 1. Create a Feature Branch

```bash
git checkout -b feat/your-feature-name
# or
git checkout -b fix/bug-description
```

Branch naming conventions:
- `feat/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `test/` - Test additions/changes
- `refactor/` - Code restructuring
- `chore/` - Maintenance tasks

### 2. Make Your Changes

- Follow the [coding standards](#coding-standards) below
- Write tests for new functionality
- Update documentation as needed
- Keep changes focused and atomic

### 3. Test Your Changes

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_memory.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Format code
black .

# Check linting
ruff check .

# Type checking (optional but recommended)
mypy src/
```

---

## Coding Standards

### Python Style

- **Python 3.12+** required
- **Type hints everywhere**: Use `typing` module for all function signatures
- **Async/await**: Use for all I/O operations (DB, API calls, LLM)
- **Docstrings**: Document classes and non-obvious functions
- **Line length**: 88 characters (Black default)

### Project-Specific Rules

Read these carefully:
- [.github/copilot-instructions.md](.github/copilot-instructions.md) - Core project rules
- [.github/instructions/plugins.instructions.md](.github/instructions/plugins.instructions.md) - Plugin development
- [.github/instructions/python.instructions.md](.github/instructions/python.instructions.md) - Python conventions

### Key Principles

1. **Privacy First**: Never send unnecessary data to external services
2. **Token Efficient**: Always consider LLM context limits (2000 tokens max)
3. **Separation of Concerns**:
   - Core logic in `src/core/`
   - Handlers in `src/handlers/`
   - Plugins in `src/plugins/`
4. **Error Handling**: Log errors, reply gracefully to users, never crash
5. **No Magic**: Explicit is better than implicit

### Code Formatting

```bash
# Format all code
black .

# Check for issues
ruff check .

# Auto-fix safe issues
ruff check . --fix
```

---

## Testing

### Writing Tests

- **Test file location**: `tests/test_<module>.py`
- **Test naming**: `test_<function_name>_<scenario>()`
- **Use fixtures**: See existing tests for patterns
- **Mock external services**: Don't hit real APIs in tests
- **Assert meaningfully**: Check specific values, not just "no error"

### Test Structure

```python
import pytest
from src.core.memory import MemoryManager

@pytest.mark.asyncio
async def test_memory_retrieval_returns_relevant_context():
    """Test that semantic search retrieves relevant memories."""
    manager = MemoryManager(...)

    # Setup
    await manager.store_memory(...)

    # Execute
    results = await manager.retrieve_similar(query="test")

    # Assert
    assert len(results) > 0
    assert results[0].similarity > 0.7
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# With output
pytest tests/ -v -s

# Specific file
pytest tests/test_memory.py -v

# Specific test
pytest tests/test_memory.py::test_memory_retrieval_returns_relevant_context -v

# Coverage report
pytest tests/ --cov=src --cov-report=term-missing
```

---

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/) for clear change history.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Adding or updating tests
- `refactor:` - Code restructuring (no behavior change)
- `perf:` - Performance improvements
- `chore:` - Maintenance (dependencies, tooling)
- `ci:` - CI/CD changes
- `build:` - Build system changes

### Examples

```bash
# Simple feature
git commit -m "feat: add voice message transcription"

# Bug fix with scope
git commit -m "fix(nudges): prevent duplicate evening check-ins"

# Breaking change
git commit -m "feat(llm)!: change provider interface to async"

# With body
git commit -m "feat: implement Signal bridge

Add new platform bridge for Signal using signal-cli.
Includes message forwarding and contact sync.

Closes #42"
```

---

## Pull Request Process

### 1. Update Documentation

- Add/update docstrings
- Update README if adding features
- Add entry to CHANGELOG.md (Unreleased section)

### 2. Ensure Tests Pass

```bash
pytest tests/ -v
black . --check
ruff check .
```

### 3. Push to Your Fork

```bash
git push origin feat/your-feature
```

### 4. Open a Pull Request

- **Title**: Use conventional commit format
- **Description**: Explain what, why, and how
- **Link issues**: Use "Closes #123" or "Fixes #456"
- **Screenshots**: If UI changes (future)
- **Testing**: Describe how you tested

### PR Template

```markdown
## Description
Brief description of changes.

## Motivation
Why is this change needed?

## Changes Made
- Added X feature
- Fixed Y bug
- Updated Z documentation

## Testing
- [ ] Unit tests pass
- [ ] Manual testing completed
- [ ] Documentation updated

## Checklist
- [ ] Code follows project style guidelines
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] No breaking changes (or marked with !)

## Related Issues
Closes #123
```

### 5. Review Process

- Maintainers will review within 1-7 days (beta phase)
- Address feedback with new commits
- Once approved, maintainers will merge

---

## Areas We Need Help

### 🌐 Platform Integrations
- **Signal bridge** - Using signal-cli
- **Discord bot** - Native Discord integration
- **Matrix server** - Self-hosted messaging
- **iMessage bridge** - macOS only
- **Slack bot** - Workplace integration

### 🎯 Skills & Features
- **More nudge skills**: Morning motivation, exercise reminders, gratitude prompts
- **Voice support**: Transcription (Whisper), TTS (Coqui, Piper)
- **Multi-user mode**: Family/team support with access control
- **Habit analytics**: Better visualization and insights
- **Calendar integration**: Sync with Google Calendar, iCal

### 🔒 Security & Privacy
- **Security audit**: Review for vulnerabilities
- **Penetration testing**: Attempt to break in
- **Privacy policy generator**: Template for self-hosters
- **Data export**: GDPR-compliant export functionality

### ⚡ Performance
- **Query optimization**: Faster database queries
- **Caching strategies**: Reduce redundant LLM calls
- **Token efficiency**: Better context compression
- **Async improvements**: Identify blocking operations

### 📚 Documentation
- **Video tutorials**: Installation, usage, customization
- **Blog posts**: Deep dives into features
- **API documentation**: Auto-generated from docstrings
- **Localization**: Translate README, docs to other languages

### 🧪 Testing
- **Integration tests**: End-to-end testing
- **Load testing**: Stress test with high message volume
- **Platform-specific tests**: WhatsApp, Telegram edge cases
- **Coverage**: Aim for >80% code coverage

### 🎨 Design (Future)
- **Logo improvements**: Better icon, banner
- **Web dashboard mockups**: UI for insights page
- **Dark mode designs**: Theme system planning
- **Mobile app concept**: Potential mobile interface

---

## Questions?

- **Documentation**: Check README and inline code comments
- **Troubleshooting**: See README troubleshooting section
- **Discussions**: Open a [GitHub Discussion](https://github.com/dcbert/raccbuddy/discussions)
- **Issues**: Search [existing issues](https://github.com/dcbert/raccbuddy/issues) first
- **Direct contact**: Comment on relevant issues or discussions

---

Thank you for contributing to RaccBuddy! Your help makes this project better for everyone. 🦝❤️
