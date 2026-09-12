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

DEFAULT_PLANNER_MODEL = "zai-org/GLM-5.3-Flash:baseten"
DEFAULT_REVIEWER_MODEL = DEFAULT_PLANNER_MODEL

# Vite and Next defaults, on both spellings of loopback. Enough for a dev server
# and nothing else -- a deployment either serves the frontend from the same
# origin or names its origin explicitly.
DEFAULT_DEV_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


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
        # `export KEY=value` is what people paste out of a shell, and without
        # this the key is stored as "export KEY" and never found again -- a
        # silent miss that shows up only as the model reporting itself offline.
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        # Strip one pair of matching quotes, not every quote character: a value
        # ending in a lone quote is a value, and stripping it corrupts the key.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
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


def hf_api_token() -> str:
    return os.environ.get("HF_TOKEN", "").strip()


def hf_base_url() -> str:
    return os.environ.get("HF_BASE_URL", "https://router.huggingface.co/v1").strip()


def planner_model() -> str:
    return os.environ.get("PLANNER_MODEL", DEFAULT_PLANNER_MODEL).strip()


def reviewer_model() -> str:
    return os.environ.get("REVIEWER_MODEL", DEFAULT_REVIEWER_MODEL).strip()


def allowed_origins() -> list[str]:
    """Origins permitted to call the API from a browser.

    ``ALLOWED_ORIGINS`` is a comma-separated list. Set it to ``none`` when the
    frontend is served from the same origin, which is the case for a single
    container -- then no CORS headers are sent at all, which is the safest
    posture rather than a permissive one.

    Unset falls back to local dev servers only. A wildcard is never the default:
    this API spends a paid model quota, and an open CORS policy invites any page
    the operator visits to spend it.
    """
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_DEV_ORIGINS)
    if raw.lower() in {"none", "off", "same-origin"}:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def database_path() -> str:
    return os.environ.get("DESK_DB", ":memory:").strip()


def has_model_access() -> bool:
    return bool(hf_api_token())
