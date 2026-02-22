"""Auto-loader for user-provided nudge skills and chat skills.

At startup, call ``load_all_user_skills()`` to import every ``.py`` file
from ``nudges/`` and ``skills/`` directories.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_NUDGES_DIR = _PROJECT_ROOT / "nudges"
_SKILLS_DIR = _PROJECT_ROOT / "skills"


def _import_py_files(directory: Path, namespace: str) -> int:
    """Import all ``.py`` files from *directory* (non-recursive).

    Returns the number of files successfully loaded.
    """
    if not directory.is_dir():
        logger.debug("Skill directory not found: %s", directory)
        return 0

    loaded = 0
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue

        module_name = f"{namespace}.{path.stem}"
        if module_name in sys.modules:
            logger.debug("Already loaded: %s", module_name)
            loaded += 1
            continue

        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning("Could not create spec for %s", path)
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            logger.info("Loaded user skill: %s", path.name)
            loaded += 1
        except Exception:
            logger.exception("Failed to load skill from %s", path)

    return loaded


def load_user_nudge_skills() -> int:
    """Import user-provided nudge skills from ``nudges/``."""
    count = _import_py_files(_NUDGES_DIR, "user_nudges")
    if count:
        logger.info("Loaded %d user nudge skill(s)", count)
    return count


def load_user_chat_skills() -> int:
    """Import user-provided chat skills from ``skills/``."""
    count = _import_py_files(_SKILLS_DIR, "user_skills")
    if count:
        logger.info("Loaded %d user chat skill(s)", count)
    return count


def load_all_user_skills() -> int:
    """Load both nudge and chat skills from their directories."""
    return load_user_nudge_skills() + load_user_chat_skills()
