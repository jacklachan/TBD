"""Two operators exchanging a conjunction record, end to end.

    python scripts/interop_demo.py

Operator A screens an encounter and issues a CDM. Operator B receives it, throws
away every conclusion in it, and recomputes the whole thing from the state
vectors the message carries. Then someone tampers with the record and B catches
it.

That last step is the point. Anyone can send a file. What makes a record useful
for coordinating traffic is that the receiver does not have to trust it.

Runs entirely against the local API, so it needs the server up:

    python -m uvicorn backend.api:app --port 8000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RULE = "-" * 68


def heading(step: str, title: str) -> None:
    print(f"\n{RULE}\n{step}  {title}\n{RULE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--scenario", default="primary", help="which case operator A screens"
    )
    args = parser.parse_args()
    base = args.base.rstrip("/")

    try:
        requests.get(f"{base}/health", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        print(f"cannot reach {base}: {exc}")
        print("start it with:  python -m uvicorn backend.api:app --port 8000")
        return 2

    # ---------------------------------------------------------- operator A
    heading("1.", "Operator A screens the encounter")

    case = requests.post(
        f"{base}/cases", json={"scenario_id": args.scenario}, timeout=30
    ).json()
    case_id = case["case_id"]
    provenance = case["scenario"]["provenance"]
    print(f"  case        {case_id}")
    print(
        f"  spacecraft  {provenance['object_name']} (NORAD {provenance['norad_id']})"
    )

    started = time.perf_counter()
    run_id = requests.post(
        f"{base}/cases/{case_id}/plan",
        json={
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
        timeout=30,
    ).json()["run_id"]

    while True:
        run = requests.get(f"{base}/runs/{run_id}", timeout=30).json()
        if run["status"] != "RUNNING":
            break
        time.sleep(0.3)

    snapshot = requests.get(f"{base}/cases/{case_id}", timeout=30).json()
    for validation in snapshot["validations"]:
        closest = min(validation["encounters"], key=lambda e: e["min_separation_m"])
        mark = "clear " if validation["status"] == "PASS" else "REJECT"
        print(
            f"  {mark}      {validation['candidate_id']:<14} "
            f"closest {closest['min_separation_m']:>9,.1f} m to {closest['object_id']}"
        )
    print(f"  decided in  {time.perf_counter() - started:.1f} s")

    # ---------------------------------------------------------- the record
    heading("2.", "Operator A issues a conjunction record")

    cdm = requests.get(
        f"{base}/cases/{case_id}/export", params={"format": "cdm"}, timeout=30
    ).text
    states = sum(1 for line in cdm.splitlines() if line.startswith("X_DOT"))
    print(f"  {len(cdm.encode()):,} bytes, CCSDS keyword-value notation")
    print(f"  carries {states} state vectors, so the claims can be recomputed")
    print("  carries no covariance, so it states no probability\n")
    for line in cdm.splitlines():
        if line.startswith(("TCA", "MISS_DISTANCE", "RELATIVE_SPEED", "OBJECT_NAME")):
            print(f"    {line}")

    # ---------------------------------------------------------- operator B
    heading("3.", "Operator B recomputes it, rather than believing it")

    verdict = requests.post(
        f"{base}/interop/verify-cdm", json={"text": cdm}, timeout=60
    ).json()
    print(f"  received from  {verdict['originator']}")
    print(
        f"  recomputed by  {verdict['independent_result']['method']} "
        f"at {verdict['independent_result']['sample_step_s']} s"
    )
    print()
    print(f"    {'object':<8}{'claimed':>14}{'recomputed':>14}{'difference':>16}")
    for check in verdict["checks"]:
        print(
            f"    {check['object_id']:<8}"
            f"{check['claimed_miss_distance_m']:>12,.1f} m"
            f"{check['recomputed_miss_distance_m']:>12,.1f} m"
            f"{check['distance_delta_m']:>14.2e} m"
        )
    print(f"\n  VERDICT  {verdict['verdict']}")

    # ------------------------------------------------------------ tampering
    heading("4.", "The same record, overstating its clearance")

    claimed = next(
        (
            line.split("=")[1].strip().split()[0]
            for line in cdm.splitlines()
            if line.startswith("MISS_DISTANCE")
        ),
        None,
    )
    if claimed is None:
        print("  no miss distance in the record to alter")
        return 0

    tampered = cdm.replace(
        f"MISS_DISTANCE = {claimed}", "MISS_DISTANCE = 9999.000", 1
    )
    print(f"  someone edits {claimed} m to 9999.000 m and re-sends it")

    caught = requests.post(
        f"{base}/interop/verify-cdm", json={"text": tampered}, timeout=60
    ).json()
    print(f"\n  VERDICT  {caught['verdict']}")
    for check in caught["checks"]:
        if not check["agrees"]:
            print(f"           {check['reason']}")

    print(f"\n{RULE}")
    print(
        "  The receiver never trusted the sender's number. It recomputed every"
        f"{chr(10)}  figure from the state vectors in the message, which is what"
        f"{chr(10)}  makes the record coordination rather than assertion."
    )
    print(RULE)
    return 0 if verdict["verdict"] == "AGREES" and caught["verdict"] == "DISAGREES" else 1


if __name__ == "__main__":
    sys.exit(main())
