"""Two operators on one pass, where the independent fixes cancel out.

The partner satellite is constructed backward from a near head-on encounter with
our satellite. The case is accepted only when the physics produces the failure
coordination exists to catch -- searched for, not staged:

* each operator's own best burn (ranked and verified with the other holding)
  clears the pass comfortably,
* both burns executed together bring the satellites back under the floor,
* and at least one joint plan clears every pair.

    python scenarios/coordination.py           # write scenarios/variants/two_operators.json
    python scenarios/coordination.py --check   # build and verify, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.coordination import coordinate  # noqa: E402
from backend.planning.policy import policy_from_document  # noqa: E402
from backend.planning.verifier import reconstruct  # noqa: E402
from scenarios.gen import GenerationError, construct_debris, verify_construction  # noqa: E402

SCENARIO_ID = "two_operators"
SEED = 4001
MAX_ATTEMPTS = 150
OUTPUT = REPO_ROOT / "scenarios" / "variants" / f"{SCENARIO_ID}.json"


def _entry(object_id, name, kind, maneuverable, trajectory, operator):
    arc = trajectory.arcs[0]
    return {
        "object_id": object_id,
        "name": name,
        "kind": kind,
        "maneuverable": maneuverable,
        "operator": operator,
        "initial_state": {"r_m": [float(x) for x in arc.r0_m], "v_mps": [float(x) for x in arc.v0_mps]},
    }


def build(seed: int = SEED) -> dict:
    primary = json.loads((REPO_ROOT / "scenarios" / "primary.json").read_text(encoding="utf-8"))
    policy = policy_from_document(primary)
    satellite = reconstruct(primary).satellite
    satellite_entry = next(o for o in primary["objects"] if o["object_id"] == "SAT-1")
    rng = np.random.default_rng(seed)
    rejected: list[str] = []

    for attempt in range(MAX_ATTEMPTS):
        try:
            tca = float(rng.uniform(14_400.0, 18_000.0))
            miss = float(rng.uniform(60.0, 200.0))
            partner = construct_debris(satellite, tca, miss, float(rng.uniform(11_000.0, 14_500.0)),
                                       float(rng.uniform(0.0, 2.0 * np.pi)))
            distractor = construct_debris(satellite, float(rng.uniform(6000.0, 9000.0)),
                                          float(rng.uniform(40_000.0, 90_000.0)),
                                          float(rng.uniform(6000.0, 12000.0)),
                                          float(rng.uniform(0.0, 2.0 * np.pi)))
        except GenerationError as exc:
            rejected.append(f"attempt {attempt}: construction -- {exc}")
            continue
        ok, detail = verify_construction(satellite, partner, "OPS-B", tca, miss)
        if not ok:
            rejected.append(f"attempt {attempt}: pass did not reproduce -- {detail}")
            continue

        document = json.loads(json.dumps(primary))
        document.pop("input_hash", None)
        document["objects"] = [
            {**satellite_entry, "operator": "Orion West"},
            _entry("OPS-B", "Partner communications satellite", "SATELLITE", True, partner, "Partner operator"),
            _entry("DEB-1", "Synthetic debris 1", "DEBRIS", False, distractor, None),
        ]
        document["primary_threat_id"] = "OPS-B"
        document["scenario_id"] = SCENARIO_ID
        document["seed"] = seed

        result = coordinate(document, policy)
        plans = {p["plan_id"]: p for p in result["plans"]}
        naive = plans.get("both_as_planned")
        if naive is None:
            rejected.append(f"attempt {attempt}: an operator has no comfortable solo plan")
            continue
        if naive["status"] != "BLOCK":
            rejected.append(f"attempt {attempt}: both burning together is still safe")
            continue
        if result["agreed_plan_id"] is None:
            rejected.append(f"attempt {attempt}: no joint plan clears every pair")
            continue

        agreed = plans[result["agreed_plan_id"]]
        document["description"] = (
            "The close approach is with another operator's active satellite. Each "
            "operator's own avoidance burn clears it; both burns together do not."
        )
        document["provenance"]["note"] = (
            "Satellite initial state derived from a real catalogue TLE at its own "
            "epoch. The partner satellite and the debris object are synthetic; the "
            "partner is constructed backward from a chosen near head-on pass. No "
            "conjunction here is real."
        )
        document["generation_evidence"] = {
            "attempts_used": attempt + 1,
            "baseline_closest_m": result["if_nobody_moves"]["closest_m"],
            "ours_plan": result["independent_plans"][0],
            "partner_plan": result["independent_plans"][1],
            "both_as_planned_closest_m": naive["closest_m"],
            "agreed_plan_id": result["agreed_plan_id"],
            "agreed_closest_m": agreed["closest_m"],
            "agreed_total_delta_v_mps": agreed["total_delta_v_mps"],
            "rejected_attempts": rejected[-5:],
        }
        payload = json.dumps(document, sort_keys=True).encode("utf-8")
        document["input_hash"] = hashlib.sha256(payload).hexdigest()
        return document

    raise GenerationError(f"no coordination case in {MAX_ATTEMPTS} attempts: {rejected[-5:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = build(args.seed)
    for key, value in document["generation_evidence"].items():
        if key != "rejected_attempts":
            print(f"  {key:28s} {value}")
    if args.check:
        print("--check: coordination case built and verified; nothing written.")
        return 0
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"  written -> {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
