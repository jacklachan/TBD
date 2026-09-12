"""Publish committed application inputs to an existing, explicitly named Space.

Run with huggingface_hub installed (the app itself does not require that SDK):
    uv run --no-project --with huggingface_hub python scripts/deploy_space.py --space Auenchanters/TBH

Hub deployment uses the CLI login. Runtime inference uses HF_TOKEN from .env.
Only the allowlisted committed Git blobs are uploaded; never the working folder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import urlsplit

from huggingface_hub import CommitOperationAdd, HfApi, get_token

ROOT = Path(__file__).resolve().parents[1]
FILES = {"README.md", "Dockerfile", ".dockerignore", "requirements.txt"}
PREFIXES = ("backend/", "scenarios/", "data/context/", "frontend/")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True)
    parser.add_argument("--dry-run", action="store_true")
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
    api = HfApi(token=get_token())
    info = api.space_info(args.space)
    if info.sdk != "docker":
        raise ValueError("Target must be an existing Docker Space")
    origin = urlsplit(info.host or "")
    if origin.scheme != "https" or not origin.hostname:
        raise ValueError("Target Space has no HTTPS application host")
    space_origin = f"https://{origin.netloc}"
    sys.path.insert(0, str(ROOT))
    from backend.config import hf_api_token, hf_base_url, planner_model, reviewer_model
    if not hf_api_token():
        raise ValueError("Set HF_TOKEN in the local .env before deployment")

    import os
    access = os.environ.get("DESK_ACCESS_TOKEN", "").strip()
    if not access:
        access = secrets.token_urlsafe(32)
        env_path = ROOT / ".env"
        lines = env_path.read_text(encoding="utf-8").splitlines()
        lines = [line for line in lines if line.partition("=")[0].strip() != "DESK_ACCESS_TOKEN"]
        env_path.write_text("\n".join(lines) + "\nDESK_ACCESS_TOKEN=" + access + "\n", encoding="utf-8")
    api.add_space_secret(args.space, "HF_TOKEN", hf_api_token())
    api.add_space_secret(args.space, "DESK_ACCESS_TOKEN", access)
    for key, value in {"PLANNER_MODEL": planner_model(), "REVIEWER_MODEL": reviewer_model(),
                       "HF_BASE_URL": hf_base_url(), "ALLOWED_ORIGINS": space_origin}.items():
        api.add_space_variable(args.space, key, value)
    result = api.create_commit(
        repo_id=args.space, repo_type="space",
        commit_message=f"Deploy verified application from {source_commit[:7]}",
        operations=[CommitOperationAdd(path_in_repo=p, path_or_fileobj=git("show", f"{source_commit}:{p}")) for p in paths],
    )
    report = {"space": args.space, "source_commit": source_commit,
              "space_commit": result.oid, "uploaded_files": len(paths), "commit_url": result.commit_url}
    print(json.dumps(report, indent=2))
    print("Runtime secrets configured; values withheld. Verify Space build and live behavior next.")


if __name__ == "__main__":
    main()
