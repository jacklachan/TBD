"""Runtime settings, and a minimal .env loader.

Hand-rolled rather than adding python-dotenv: it is twenty lines, it avoids a
new dependency mid-event, and the parsing rules are visible.

Secrets live in ``.env`` at the repository root, which is gitignored. Never in
the repository, never in the Handoff packet, never in a commit.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"

DEFAULT_PLANNER_MODEL = "gemini-3.6-flash"
DEFAULT_REVIEWER_MODEL = "gemini-3.6-flash"
DISPLAY_NAME = "Satellite Demo"


def load_env(path: Path = ENV_PATH, override: bool = False) -> dict[str, str]:
    """Read KEY=VALUE lines into the environment. Missing file is fine.

    Blank lines and ``#`` comments are skipped, surrounding quotes are stripped,
    and an already-set variable wins unless ``override`` is true -- so an
    explicitly exported key beats whatever is in the file.
    """
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


# Loaded on import so anything reading os.environ sees the file's contents.
load_env()


def gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def planner_model() -> str:
    return os.environ.get("PLANNER_MODEL", DEFAULT_PLANNER_MODEL).strip()


def reviewer_model() -> str:
    return os.environ.get("REVIEWER_MODEL", DEFAULT_REVIEWER_MODEL).strip()


def database_path() -> str:
    return os.environ.get("DESK_DB", ":memory:").strip()


def has_model_access() -> bool:
    return bool(gemini_api_key())
