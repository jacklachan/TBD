"""Publish committed application inputs to an existing, explicitly named Space.

Run with huggingface_hub installed (the app itself does not require that SDK):
    uv run --no-project --with huggingface_hub python scripts/deploy_space.py --space Auenchanters/TBH

Hub deployment uses the CLI login. Runtime inference uses HF_TOKEN from .env.
Only the allowlisted committed Git blobs are uploaded; never the working folder.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import urlsplit

from huggingface_hub import CommitOperationAdd, HfApi, get_token

ROOT = Path(__file__).resolve().parents[1]
FILES = {"README.md", "Dockerfile", ".dockerignore", "requirements.txt"}
PREFIXES = ("backend/", "scenarios/", "data/context/", "data/catalog/", "frontend/")


def deploy_token() -> str | None:
    """A Hub token for uploading, kept apart from the runtime inference token.

    ``HF_DEPLOY_TOKEN`` (environment, or the ignored local .env) is used only to
    talk to the Hub. It is read without loading the rest of .env, so an
    ``HF_TOKEN`` there can never be picked up as the upload credential or --
    worse -- a write token pushed into the Space as its inference secret.
    Falls back to the CLI login.
    """
    value = os.environ.get("HF_DEPLOY_TOKEN", "").strip()
    env_path = ROOT / ".env"
    if not value and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition("=")
            if key.strip() == "HF_DEPLOY_TOKEN":
                value = raw.strip().strip("\"'")
    return value or None


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--code-only", action="store_true",
        help="Upload the committed application files only. Every Space secret and "
             "variable stays exactly as it is -- no token copied, no password minted.")
    parser.add_argument(
        "--keep-space-hf-token", action="store_true",
        help="Leave the Space's existing HF_TOKEN secret untouched. For a teammate "
             "redeploying code who does not hold the inference token locally.")
    args = parser.parse_args()
    source_commit = git("rev-parse", "HEAD").decode().strip()
    paths = git("ls-tree", "-r", "--name-only", "HEAD").decode().splitlines()
    paths = [p for p in paths if (p in FILES or p.startswith(PREFIXES))
             and not p.startswith("frontend/e2e/")]
    # Defense against accidentally committing a secret inside an allowed prefix.
    for path in paths:
        parts = Path(path).parts
        if (Path(path).name.startswith(".env") or any(p in {"node_modules", ".venv", "__pycache__", "dist", "test-results"} for p in parts)
                or Path(path).suffix in {".sqlite", ".sqlite3", ".db", ".pem", ".key"}):
            raise ValueError(f"Refusing runtime/secret file: {path}")
    print(f"Source {source_commit}: {len(paths)} committed files -> {args.space}")
    if args.dry_run:
        print("\n".join(paths))
        return

    # Capture the Hub login before loading the inference-only runtime token.
    api = HfApi(token=deploy_token() or get_token())
    info = api.space_info(args.space)
    if info.sdk != "docker":
        raise ValueError("Target must be an existing Docker Space")
    origin = urlsplit(info.host or "")
    if origin.scheme != "https" or not origin.hostname:
        raise ValueError("Target Space has no HTTPS application host")
    space_origin = f"https://{origin.netloc}"
    if not args.code_only:
        configure_runtime(api, args, space_origin)
    result = api.create_commit(
        repo_id=args.space, repo_type="space",
        commit_message=f"Deploy verified application from {source_commit[:7]}",
        operations=[CommitOperationAdd(path_in_repo=p, path_or_fileobj=git("show", f"{source_commit}:{p}")) for p in paths],
    )
    report = {"space": args.space, "source_commit": source_commit, "code_only": args.code_only,
              "space_commit": result.oid, "uploaded_files": len(paths), "commit_url": result.commit_url}
    print(json.dumps(report, indent=2))
    print("Upload done; values withheld. Verify the Space build and live behaviour next.")


def configure_runtime(api, args, space_origin: str) -> None:
    """Secrets and variables. Skipped entirely by --code-only.

    A missing local DESK_ACCESS_TOKEN mints a new operator password and pushes
    it, which locks out everyone using the old one -- right for a first deploy,
    wrong for a teammate redeploying code, which is what --code-only is for.
    """
    sys.path.insert(0, str(ROOT))
    from backend.config import hf_api_token, hf_base_url, planner_model, reviewer_model
    if not hf_api_token() and not args.keep_space_hf_token:
        raise ValueError("Set HF_TOKEN in the local .env before deployment, "
                         "or pass --keep-space-hf-token to keep the Space's existing secret")

    access = os.environ.get("DESK_ACCESS_TOKEN", "").strip()
    if not access:
        access = secrets.token_urlsafe(32)
        env_path = ROOT / ".env"
        lines = env_path.read_text(encoding="utf-8").splitlines()
        lines = [line for line in lines if line.partition("=")[0].strip() != "DESK_ACCESS_TOKEN"]
        env_path.write_text("\n".join(lines) + "\nDESK_ACCESS_TOKEN=" + access + "\n", encoding="utf-8")
    if not args.keep_space_hf_token:
        api.add_space_secret(args.space, "HF_TOKEN", hf_api_token())
    api.add_space_secret(args.space, "DESK_ACCESS_TOKEN", access)
    for key, value in {"PLANNER_MODEL": planner_model(), "REVIEWER_MODEL": reviewer_model(),
                       "HF_BASE_URL": hf_base_url(), "ALLOWED_ORIGINS": space_origin}.items():
        api.add_space_variable(args.space, key, value)


if __name__ == "__main__":
    main()
