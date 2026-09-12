"""Pre-demo diagnostic. Run this before showing anything to anyone.

    python scripts/diagnose.py

Checks the things that actually break a demo, in the order they would break it:
the data snapshots are present, the fixtures still reproduce, the numerical
chain reaches a verified answer, the frontend is built, the server answers, and
a model key is visible. Every check prints what it found rather than just a
tick, because "passed" without a number is not evidence.

Exit code is 0 only when nothing is broken. Warnings do not fail the run -- they
are things you can demo without, and the summary says which.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OK, WARN, FAIL = "PASS", "WARN", "FAIL"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}")


# ---------------------------------------------------------------- data

section("1. Committed data")

tle = REPO / "scenarios" / "seed_tle.txt"
if tle.exists():
    lines = [l for l in tle.read_text(encoding="utf-8").splitlines() if l.strip()]
    record(
        OK if len(lines) == 3 else FAIL,
        "seed TLE",
        f"{lines[0].strip()} ({len(lines)} lines)" if lines else "empty",
    )
else:
    record(FAIL, "seed TLE", "scenarios/seed_tle.txt missing - run scripts/fetch_snapshots.py")

socrates = REPO / "data" / "context" / "socrates_snapshot.csv"
if socrates.exists():
    import csv
    import re

    rows = list(csv.DictReader(socrates.open(encoding="utf-8")))
    comms = [
        r
        for r in rows
        if re.search(
            r"STARLINK|ONEWEB|IRIDIUM|GLOBALSTAR|INTELSAT|KUIPER|KINEIS",
            f"{r['OBJECT_NAME_1']} {r['OBJECT_NAME_2']}",
            re.I,
        )
    ]
    record(
        OK if rows else FAIL,
        "SOCRATES snapshot",
        f"{len(rows)} real conjunctions, {len(comms)} involve a comms satellite",
    )
else:
    record(WARN, "SOCRATES snapshot", "missing - the real-world context panel will be empty")

for name in ("primary.json",):
    path = REPO / "scenarios" / name
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
        record(
            OK,
            f"fixture {name}",
            f"{len(doc['objects'])} objects, seed {doc['seed']}, "
            f"hash {doc.get('input_hash', '')[:12]}",
        )
    else:
        record(FAIL, f"fixture {name}", "missing - run python scenarios/gen.py")

variants = sorted((REPO / "scenarios" / "variants").glob("*.json"))
record(
    OK if len(variants) >= 3 else WARN,
    "scenario variants",
    ", ".join(p.stem for p in variants) or "none",
)

# ------------------------------------------------------------ numerics

section("2. The numerical chain")

try:
    from scripts.demo_pipeline import OUTCOME_VERIFIED, run

    started = time.perf_counter()
    record_out = run("primary")
    elapsed = time.perf_counter() - started
    rejected = [
        v["candidate_id"] for v in record_out["validations"] if v["status"] != "PASS"
    ]
    record(
        OK if record_out["outcome"] == OUTCOME_VERIFIED else FAIL,
        "signature case",
        f"{record_out['candidate_count']} options, rejected {len(rejected)}, "
        f"verified {record_out.get('approved_candidate_id')}, {elapsed:.2f}s",
    )

    worst = min(
        (
            v["max_primary_distance_disagreement_m"]
            for v in record_out["validations"]
            if v["max_primary_distance_disagreement_m"] is not None
        ),
        default=None,
    )
    record(
        OK if worst is not None else WARN,
        "search vs verifier agreement",
        f"{worst:.3e} m" if worst is not None else "no comparison recorded",
    )
except Exception as exc:  # noqa: BLE001
    record(FAIL, "signature case", f"{type(exc).__name__}: {exc}")

for scenario, expected in (
    ("no_encounter", "BASELINE_ACCEPTABLE"),
    ("no_feasible", "NO_APPROVABLE_OPTION"),
):
    try:
        from scripts.demo_pipeline import run as run_case

        outcome = run_case(scenario)["outcome"]
        record(OK if outcome == expected else FAIL, f"variant {scenario}", outcome)
    except Exception as exc:  # noqa: BLE001
        record(FAIL, f"variant {scenario}", str(exc))

section("2b. Interoperability")

try:
    from backend.interop import parse_cdm, verify_cdm, write_cdm

    from scripts.demo_pipeline import SCENARIO_PATHS

    doc = json.loads(SCENARIO_PATHS["primary"].read_text(encoding="utf-8"))
    # A minimal snapshot shaped like the API's, so this check needs no server.
    snapshot = {
        "case_id": "diagnostic",
        "scenario": {
            "epoch_utc": doc["epoch_utc"],
            "horizon_s": doc["horizon_s"],
            "satellite_id": doc["satellite_id"],
            "objects": [
                {"object_id": o["object_id"], "name": o["name"], "kind": o["kind"]}
                for o in doc["objects"]
            ],
            "provenance": doc["provenance"],
        },
        "validations": [],
    }
    text = write_cdm(snapshot, doc)
    record(OK, "CDM writer", f"{len(text.encode()):,} bytes")
except Exception as exc:  # noqa: BLE001
    record(FAIL, "CDM writer", f"{type(exc).__name__}: {exc}")

# ------------------------------------------------------------ frontend

section("3. Frontend build")

dist = REPO / "frontend" / "dist"
index = dist / "index.html"
if index.exists():
    assets = list((dist / "assets").glob("*.js")) if (dist / "assets").is_dir() else []
    total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
    record(
        OK,
        "frontend/dist",
        f"{len(assets)} js chunks, {total / 1_000_000:.1f} MB total",
    )
else:
    record(
        FAIL,
        "frontend/dist",
        "not built - run: npm --prefix frontend ci && npm --prefix frontend run build",
    )

demo = REPO / "demo" / "index.html"
if demo.exists():
    head = demo.read_bytes()[:200].lower()
    record(
        OK if b"charset" in head else FAIL,
        "walkthrough demo/index.html",
        "charset declared" if b"charset" in head else "no charset - text will mojibake",
    )
else:
    record(WARN, "walkthrough", "demo/index.html missing")

# -------------------------------------------------------------- runtime

section("4. Runtime")

try:
    from backend.config import has_model_access, planner_model

    record(
        OK if has_model_access() else WARN,
        "model access",
        f"key present, planner {planner_model()}"
        if has_model_access()
        else "no GEMINI_API_KEY - numerical controls still work, AI planner will not",
    )
except Exception as exc:  # noqa: BLE001
    record(FAIL, "model access", str(exc))

try:
    import requests

    health = requests.get("http://127.0.0.1:8000/health", timeout=3).json()
    record(
        OK,
        "server on :8000",
        f"model_access={health.get('model_access')}, {health.get('planner_model')}",
    )
except Exception:
    record(
        WARN,
        "server on :8000",
        "not running - start with: python -m uvicorn backend.api:app --port 8000",
    )

# --------------------------------------------------------------- tests

section("5. Test suites")

for label, command in (
    ("python", [sys.executable, "-m", "pytest", "tests", "-q", "--no-header"]),
):
    try:
        proc = subprocess.run(
            command, cwd=REPO, capture_output=True, text=True, timeout=900
        )
        tail = [l for l in proc.stdout.strip().splitlines() if l.strip()][-1:]
        record(
            OK if proc.returncode == 0 else FAIL,
            f"{label} tests",
            tail[0] if tail else f"exit {proc.returncode}",
        )
    except Exception as exc:  # noqa: BLE001
        record(FAIL, f"{label} tests", str(exc))

# -------------------------------------------------------------- summary

failures = [r for r in results if r[0] == FAIL]
warnings = [r for r in results if r[0] == WARN]

print("\n" + "=" * 64)
if failures:
    print(f"{len(failures)} FAILURE(S) - the demo is not safe to show:")
    for _, name, detail in failures:
        print(f"  - {name}: {detail}")
elif warnings:
    print("No failures. Demo is safe to show.")
    print(f"{len(warnings)} warning(s) - things you can demo without:")
    for _, name, detail in warnings:
        print(f"  - {name}: {detail}")
else:
    print("All checks passed. Nothing outstanding.")

print("=" * 64)
sys.exit(1 if failures else 0)
