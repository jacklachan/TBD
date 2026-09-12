"""End-to-end check against a running server with a real model.

    uvicorn backend.api:app --port 8000
    python scripts/live_api_check.py

Drives the whole operator workflow over HTTP: create a case, plan, fetch the
visualization bundle, change a constraint in plain English, confirm it, replan,
approve, export, reset. Prints timings for each leg.

This is the path a judge exercises. The unit tests cover the same endpoints with
a scripted provider; this is the one that proves the real thing works end to end,
including serialization, the background run pool and the live model.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import load_env  # noqa: E402

load_env()  # Read the local operator token too; never print it.

TRAP = "t30_ret_100"
RESCUE = "t30_ret_200"


class Checker:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.failures: list[str] = []
        token = os.environ.get("DESK_ACCESS_TOKEN", "").strip()
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def ok(self, label: str, condition: bool, detail: str = "") -> bool:
        mark = "PASS" if condition else "FAIL"
        print(f"  [{mark}] {label}" + (f" - {detail}" if detail else ""))
        if not condition:
            self.failures.append(label)
        return condition

    def get(self, path: str, **params):
        response = requests.get(f"{self.base}{path}", params=params or None, headers=self.headers, timeout=120)
        return response

    def post(self, path: str, payload: dict):
        return requests.post(f"{self.base}{path}", json=payload, headers=self.headers, timeout=120)

    def wait(self, run_id: str, timeout_s: float = 180.0) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            run = self.get(f"/runs/{run_id}").json()
            if run["status"] != "RUNNING":
                return run
            time.sleep(0.3)
        raise AssertionError(f"run {run_id} never finished")


def versions(snapshot: dict) -> dict:
    return {
        "expected_scenario_version": snapshot["scenario_version"],
        "expected_policy_version": snapshot["policy_version"],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    check = Checker(args.base)

    try:
        health = check.get("/health").json()
    except requests.RequestException as exc:
        print(f"cannot reach {args.base}: {exc}")
        print("start it with:  uvicorn backend.api:app --port 8000")
        return 2

    print(f"server     {args.base}  model_version={health['model_version']}\n")

    # ---------------------------------------------------------------- case
    print("1. create case")
    started = time.perf_counter()
    case = check.post("/cases", {"scenario_id": "primary"}).json()
    case_id = case["case_id"]
    provenance = case["scenario"]["provenance"]
    check.ok("case created", case["policy_version"] == 1, case_id)
    check.ok(
        "provenance is honest",
        provenance["synthetic_conjunction"] is True and provenance["norad_id"] > 0,
        f"NORAD {provenance['norad_id']}, epoch {provenance['tle_epoch_utc']}",
    )
    print(f"     {time.perf_counter() - started:.2f}s\n")

    # ---------------------------------------------------------------- plan
    print("2. plan with the live model")
    started = time.perf_counter()
    run_id = check.post(f"/cases/{case_id}/plan", versions(case)).json()["run_id"]
    run = check.wait(run_id)
    plan_seconds = time.perf_counter() - started
    result = run.get("result") or {}
    check.ok("run finished", run["status"] == "DONE", run.get("error", ""))
    check.ok(
        "proposal ready",
        result.get("status") == "PROPOSAL_READY",
        f"{result.get('model_calls')} model calls, {result.get('tool_calls')} tool calls",
    )
    check.ok("no invented figures", not result.get("flagged_numbers"), str(result.get("flagged_numbers")))

    snapshot = check.get(f"/cases/{case_id}").json()
    if result.get("status") != "PROPOSAL_READY" or not snapshot.get("proposal"):
        for event in snapshot.get("events", []):
            if event.get("event_type") in {"model_error", "unresolved", "limit", "grid_audit"}:
                print(f"  {event['event_type']}: {event['summary']}")
        print("FAILED: no reviewed proposal; the remaining workflow needs a working provider.")
        return 1
    statuses = {v["candidate_id"]: v["status"] for v in snapshot["validations"]}
    check.ok("an option was rejected", any(s == "BLOCK" for s in statuses.values()), str(statuses))
    check.ok("an option passed", any(s == "PASS" for s in statuses.values()))
    proposal = snapshot["proposal"]
    check.ok("proposal is READY", proposal and proposal["status"] == "READY", proposal["candidate_id"])
    verdict = proposal.get("reviewer_verdict") or {}
    check.ok("reviewer answered", verdict.get("decision") == "ALLOW", verdict.get("rationale", "")[:70])
    print(f"     {plan_seconds:.1f}s\n")

    print("   rationale:")
    for line in (proposal["qualitative_rationale"] or "").splitlines():
        if line.strip():
            print(f"     {line.strip()}")
    print()

    # ------------------------------------------------------- visualization
    print("3. visualization bundle")
    started = time.perf_counter()
    bundle = check.get(
        f"/cases/{case_id}/visualization",
        candidate_ids=f"baseline,{TRAP},{RESCUE}",
        **versions(snapshot),
    ).json()
    times = bundle["t_s"]
    check.ok("one shared time grid", times == sorted(times) and len(times) == len(set(times)))
    aligned = all(
        len(v["min_to_any_m"]) == len(times)
        and all(len(s) == len(times) for s in v["pair_separations_m"].values())
        and all(len(p) == len(times) for p in v["positions_m"].values())
        for v in bundle["variants"]
    )
    check.ok("every array aligns with t_s", aligned, f"{len(times)} samples")
    grid = set(times)
    check.ok(
        "encounter times are real samples",
        all(e["tca_s"] in grid for v in bundle["variants"] for e in v["encounters"]),
    )
    print(f"     {time.perf_counter() - started:.2f}s, {len(times)} samples, {len(bundle['variants'])} variants\n")

    # -------------------------------------------------------- judge sentence
    print("4. judge changes a constraint in plain English")
    started = time.perf_counter()
    preview = check.post(
        f"/cases/{case_id}/policy-preview",
        {**versions(snapshot), "text": "we lost a thruster, halve the fuel budget"},
    )
    check.ok("preview accepted", preview.status_code == 200, preview.text[:120])
    diff = preview.json()["diff"]
    change = diff["changes"][0] if diff["changes"] else {}
    check.ok(
        "backend computed the new budget",
        diff["status"] == "READY" and change.get("after") == 0.1,
        f"{change.get('before')} -> {change.get('after')} m/s",
    )
    print(f"     {time.perf_counter() - started:.1f}s\n")

    print("5. confirm, and the old proposal goes stale")
    confirm = check.post(
        f"/cases/{case_id}/policy-confirm", {**versions(snapshot), "diff_id": diff["diff_id"]}
    ).json()
    check.ok("policy bumped to v2", confirm["policy_version"] == 2)
    after = check.get(f"/cases/{case_id}").json()
    check.ok("prior proposal is STALE", after["proposal"]["status"] == "STALE")
    stale_attempt = check.post(
        f"/cases/{case_id}/approve",
        {
            **versions(after),
            "proposal_id": after["proposal"]["proposal_id"],
            "idempotency_key": "stale-attempt",
        },
    )
    check.ok("stale proposal cannot be approved", stale_attempt.status_code == 409,
             str(stale_attempt.json().get("detail", {}).get("error")))
    print()

    # ------------------------------------------------------------- replan
    print("6. replan under the reduced budget")
    started = time.perf_counter()
    run_id = check.post(f"/cases/{case_id}/plan", versions(after)).json()["run_id"]
    run2 = check.wait(run_id)
    replan_seconds = time.perf_counter() - started
    status2 = run2["result"].get("status")
    check.ok("replan finished", run2["status"] == "DONE", status2 or run2.get("error", ""))
    check.ok(
        "honest infeasibility",
        status2 == "NO_APPROVABLE_OPTION",
        "0.10 m/s tier is unsafe against DEB-2 and 0.20 m/s is now over budget",
    )
    print(f"     {replan_seconds:.1f}s\n")

    # ------------------------------------------------------------ approve
    print("7. approve on a fresh case, twice")
    fresh = check.post(f"/cases/{case_id}/reset", versions(after)).json()
    fresh_id = fresh["case_id"]
    check.ok("reset made a new case", fresh_id != case_id and fresh["parent_case_id"] == case_id)
    run_id = check.post(f"/cases/{fresh_id}/plan", versions(fresh)).json()["run_id"]
    run3 = check.wait(run_id)
    fresh_snapshot = check.get(f"/cases/{fresh_id}").json()

    if run3["result"].get("status") == "PROPOSAL_READY" and fresh_snapshot["proposal"]:
        body = {
            **versions(fresh_snapshot),
            "proposal_id": fresh_snapshot["proposal"]["proposal_id"],
            "idempotency_key": "judge-click-1",
        }
        first = check.post(f"/cases/{fresh_id}/approve", body).json()
        second = check.post(f"/cases/{fresh_id}/approve", body).json()
        check.ok("execution created once", first["created"] is True)
        check.ok(
            "repeat returns the same record",
            second["created"] is False
            and second["execution"]["execution_id"] == first["execution"]["execution_id"],
            first["execution"]["execution_id"],
        )
    else:
        check.ok("fresh plan produced a proposal", False, str(run3["result"].get("status")))
    print()

    # ------------------------------------------------------- export, context
    print("8. export and context")
    markdown = check.get(f"/cases/{fresh_id}/export", format="markdown").text
    check.ok(
        "markdown states its limits",
        all(
            phrase in markdown
            for phrase in ("synthetic", "No collision probability is computed", "Simulated only")
        ),
        f"{len(markdown)} chars",
    )
    socrates = check.get("/context/socrates")
    if socrates.status_code == 200:
        payload = socrates.json()
        check.ok(
            "real conjunctions served from disk",
            0 < payload["row_count"] <= 10,
            f"{payload['row_count']} rows, closest {payload['rows'][0]['TCA_RANGE_KM']} km",
        )
    print()

    print("=" * 60)
    if check.failures:
        print(f"FAILED: {len(check.failures)} check(s) — {', '.join(check.failures)}")
        return 1
    print("ALL CHECKS PASSED")
    print(f"  plan {plan_seconds:.1f}s | replan {replan_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
