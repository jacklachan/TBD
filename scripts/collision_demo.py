"""A strike, the best the grid can do about it, and the burn the agent designs.

    python scripts/collision_demo.py

The scenario is one where doing nothing means the two objects arrive at the
same point. That part needs no explanation: four metres between objects that are
themselves metres across is a collision, not a close call.

What the run is actually about is the next step. The enumerated grid of 25
options contains an answer, and it is a bad one -- it clears the floor by about
eleven metres, which the safety reviewer refuses. The planner is allowed to
design a burn of its own instead, and the only reason that is safe is that a
designed burn is recomputed by exactly the same independent verifier, against
every object, over the full horizon.

So this prints three things in order: what happens if nothing is done, what the
grid can offer, and what the agent designs when the grid is not enough. The
first two need no model and run offline. The third needs GEMINI_API_KEY and the
server:

    python -m uvicorn backend.api:app --port 8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RULE = "-" * 70


def heading(step: str, title: str) -> None:
    print(f"\n{RULE}\n{step}  {title}\n{RULE}")


def screen(document, policy, candidate):
    from backend.planning.verifier import validate_candidate

    result = validate_candidate(document, policy, candidate)
    closest = result.closest()
    return result, closest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the live planner and print only the numerical part",
    )
    args = parser.parse_args()

    from backend.planning.candidates import baseline_candidate, generate_candidates
    from backend.planning.policy import policy_from_document

    path = REPO / "scenarios" / "variants" / "collision.json"
    if not path.exists():
        print(f"{path.relative_to(REPO)} missing -- run python scenarios/gen.py")
        return 2
    document = json.loads(path.read_text(encoding="utf-8"))
    policy = policy_from_document(document)

    # ------------------------------------------------------------- do nothing
    heading("1.", "The current trajectory")

    _, closest = screen(document, policy, baseline_candidate())
    print(f"  spacecraft   {document['provenance']['object_name']}")
    print(f"  closest      {closest.min_separation_m:,.1f} m to {closest.other_object_id}")
    print(f"  at           T+{closest.tca_s:,.0f} s")
    print(f"  closing at   {closest.relative_speed_mps:,.0f} m/s")
    print(
        f"\n  The clearance floor is {policy.min_separation_m:,.0f} m. Both objects "
        f"are metres\n  across, so {closest.min_separation_m:,.1f} m is not a close "
        "pass. They collide."
    )

    # ------------------------------------------------------ the best the grid has
    heading("2.", "The best the enumerated grid can do")

    comfortable_ratio = 1.25
    comfortable = policy.min_separation_m * comfortable_ratio
    best = None
    for candidate in generate_candidates(1):
        if candidate.is_baseline:
            continue
        result, closest = screen(document, policy, candidate)
        if result.status != "PASS" or closest is None:
            continue
        if best is None or closest.min_separation_m > best[1].min_separation_m:
            best = (candidate, closest)

    if best is None:
        print("  no grid option clears the floor at all")
    else:
        candidate, closest = best
        print(
            f"  {candidate.candidate_id:<16} {candidate.delta_v_mps:.2f} m/s "
            f"{candidate.direction.lower()} at T+{candidate.burn_t_s:,.0f} s"
        )
        print(
            f"  clears {closest.other_object_id} by {closest.min_separation_m:,.1f} m "
            f"-- {closest.min_separation_m - policy.min_separation_m:,.1f} m "
            "above the floor"
        )
        print(
            f"\n  The safety reviewer refuses anything below {comfortable:,.0f} m "
            f"({comfortable_ratio:g}x the floor).\n  This is the grid's best answer "
            "and it is not approvable. The grid's\n  earliest burn is T+900 s and "
            f"its largest is 0.20 m/s, against a\n  {policy.max_delta_v_mps:.2f} m/s "
            "budget -- the options are the constraint, not the fuel."
        )

    if args.offline:
        print(f"\n{RULE}\n  --offline: stopping before the live planner.\n{RULE}")
        return 0

    # ------------------------------------------------------------ the agent
    heading("3.", "What the agent designs instead")

    import requests

    base = args.base.rstrip("/")
    try:
        requests.get(f"{base}/health", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        print(f"  cannot reach {base}: {exc}")
        print("  start it with:  python -m uvicorn backend.api:app --port 8000")
        print("  or re-run with --offline for the numerical part only")
        return 2

    case = requests.post(
        f"{base}/cases", json={"scenario_id": "collision"}, timeout=30
    ).json()
    case_id = case["case_id"]
    run = requests.post(
        f"{base}/cases/{case_id}/plan",
        json={
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
        timeout=30,
    ).json()

    started = time.perf_counter()
    while True:
        state = requests.get(f"{base}/runs/{run['run_id']}", timeout=30).json()
        if state["status"] != "RUNNING":
            break
        time.sleep(0.4)
    elapsed = time.perf_counter() - started

    snapshot = requests.get(f"{base}/cases/{case_id}", timeout=30).json()
    print(f"  {'option':<22}{'source':<10}{'closest':>12}{'margin':>12}")
    for validation in snapshot["validations"]:
        worst = min(validation["encounters"], key=lambda e: e["min_separation_m"])
        designed = validation["candidate_id"].startswith("free_")
        print(
            f"  {validation['candidate_id']:<22}"
            f"{'designed' if designed else 'grid':<10}"
            f"{worst['min_separation_m']:>10,.1f} m"
            f"{worst['min_separation_m'] - policy.min_separation_m:>10,.1f} m"
        )

    proposal = snapshot.get("proposal") or {}
    verdict = proposal.get("reviewer_verdict") or {}
    print(f"\n  proposed   {proposal.get('candidate_id')}")
    print(f"  reviewer   {verdict.get('decision')} {verdict.get('reason_codes') or ''}")
    print(f"  took       {elapsed:.1f} s, {state['result'].get('model_calls')} model calls")

    rationale = (proposal.get("qualitative_rationale") or "").strip()
    if rationale:
        print(f"\n  {rationale}")

    print(f"\n{RULE}")
    print(
        "  Designing a burn clears nothing on its own. Every option above --\n"
        "  grid or designed -- was recomputed against every object over the full\n"
        "  horizon by the same verifier, and the reviewer saw the manoeuvre, not\n"
        "  just the number. The freedom to leave the grid cost no safety."
    )
    print(RULE)

    approvable = verdict.get("decision") == "ALLOW"
    return 0 if approvable else 1


if __name__ == "__main__":
    sys.exit(main())
