"""Build a portable update from the committed changes since the pre-merge main.

Run at the end of a committed work session. Handoff itself is excluded from the
archive to prevent recursive packets; the outer folder already carries the docs.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = "65ab3d1"
DESTINATION = Path(__file__).resolve().parent


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT).decode("utf-8")


def main():
    commit = git("rev-parse", "HEAD").strip()
    paths = git("diff", "--name-only", "-z", "--diff-filter=ACMR", BASE, commit).split("\0")
    paths = [p for p in paths if p and not p.startswith("Handoff/")]
    deleted = [p for p in git("diff", "--name-only", "-z", "--diff-filter=D", BASE, commit).split("\0") if p and not p.startswith("Handoff/")]
    entries = []
    archive_path = DESTINATION / "review-and-frontend.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in paths:
            source = (ROOT / relative).resolve()
            if not source.is_relative_to(ROOT):
                raise ValueError("Update path escaped the repository")
            # Read the committed blob, not a later uncommitted editor change.
            content = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)
            entries.append({"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            archive.writestr(relative, content)
        manifest = {"base_commit": git("rev-parse", BASE).strip(), "source_commit": commit, "files": entries, "deleted_paths": deleted}
        archive.writestr("HANDOFF_MANIFEST.json", json.dumps(manifest, indent=2))
    manifest["archive_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Packed {len(entries)} files from {BASE} to {commit[:7]}; {archive_path.stat().st_size:,} bytes.")


if __name__ == "__main__":
    main()
