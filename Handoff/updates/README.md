# Portable implementation update

Send the entire outer `Handoff` folder. `review-and-frontend.zip` contains the changed source files, runtime assets, tests, configuration and dependency locks since pre-merge main **65ab3d1**. It includes the teammate branch merge, review fixes and frontend. It excludes dependencies, databases, credentials and recursive Handoff copies.

Read `manifest.json` for the exact full base/source commit IDs, changed files and SHA-256 hashes. The ZIP includes the same file manifest as `HANDOFF_MANIFEST.json`. This is an update to an existing checkout, not a standalone project or a complete Git history.

Prefer pulling main from `jacklachan/TBD`. For an offline handoff, compare the archive's paths against your checkout and incorporate them while preserving your local changes. Check `deleted_paths` in the manifest. Install Python and npm dependencies from the included requirement files and lockfile, then follow the root README. No environments or API keys are included.

To regenerate after committing a later update, run `python Handoff/updates/build_packet.py` from the repository. It deliberately excludes Handoff from its own archive. Commit the resulting ZIP and manifest separately.
