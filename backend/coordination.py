"""Two operators, one close approach: who moves.

Traffic coordination fails in a specific way. Both operators see the same
warning, both compute an avoidance burn for their own satellite, and both
execute it. A pass at kilometres per second is decided by offsets of hundreds
of metres, so two burns that each clear it can partly cancel. Each plan is safe
on its own; together they may not be. In the committed fixture they are not.

This module is the check that catches it, run on the scenario's raw states:

1. **Each operator plans independently**, exactly as it would alone: the grid
   ranked against the other satellite, then verified with the other holding.
2. **Both plans are checked together.** Every pair involving either satellite is
   screened with both burns applied, by the verifier's own screening code.
3. **Joint plans are compared under a stated rule**: of the plans that clear
   every pair by the comfortable margin, the least total delta-v wins, then the
   one where fewer operators move, then the larger closest approach. The rule is
   published in the result so both sides can apply it and get the same answer.

The agreement carries both burns and every figure, and is recomputable from the
scenario states by either party.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from backend.agent.reviewer import MARGINAL_CLEARANCE_RATIO
from backend.core.trajectory import Trajectory
from backend.planning.candidates import (
    DIRECTION_PROGRADE,
    DIRECTION_RETROGRADE,
    Candidate,
)
from backend.planning.policy import Policy
from backend.planning.search import apply_candidate, evaluate_candidates
from backend.planning.verifier import reconstruct, screen_pair

RULE = (
    "Of the joint plans that clear every pair by the comfortable margin, choose "
    "the least total delta-v; if tied, the plan where fewer operators move; if "
    "still tied, the larger closest approach. Never execute two independent "
    "plans without checking them together."
)


class CoordinationError(ValueError):
    """The scenario has no second operator to coordinate with."""


def _trajectories(document: dict) -> tuple[dict[str, Trajectory], float]:
    scenario = reconstruct(document)
    trajectories = {scenario.satellite_id: scenario.satellite, **scenario.debris}
    return trajectories, scenario.horizon_s


def operator_ids(document: dict) -> list[str]:
    """The satellite first, then every other object an operator can manoeuvre."""
    ours = document["satellite_id"]
    others = [o["object_id"] for o in document["objects"] if o.get("maneuverable") and o["object_id"] != ours]
    return [ours, *others]


def joint_check(document: dict, policy: Policy, burns: dict[str, Candidate | None]) -> dict:
    """Screen every pair involving an operator's satellite with the burns applied."""
    trajectories, horizon = _trajectories(document)
    moved = {
        object_id: (
            apply_candidate(trajectory, burns[object_id])
            if burns.get(object_id) is not None and not burns[object_id].is_baseline
            else trajectory
        )
        for object_id, trajectory in trajectories.items()
    }
    operators = operator_ids(document)
    pairs, seen = [], set()
    for mover in operators:
        for other in moved:
            key = frozenset((mover, other))
            if other == mover or key in seen:
                continue
            seen.add(key)
            found = screen_pair(moved[mover], moved[other], other, horizon)
            if found is not None:
                pairs.append({
                    "objects": [mover, other],
                    "min_separation_m": round(found.min_separation_m, 1),
                    "tca_s": round(found.tca_s, 1),
                })
    pairs.sort(key=lambda p: p["min_separation_m"])
    over_budget = [
        object_id for object_id, burn in burns.items()
        if burn is not None and burn.delta_v_mps > policy.max_delta_v_mps + 1e-12
    ]
    closest = pairs[0]["min_separation_m"] if pairs else None
    floor = policy.min_separation_m
    return {
        "burns": {
            object_id: None if burn is None or burn.is_baseline else {
                "candidate_id": burn.candidate_id,
                "burn_t_s": burn.burn_t_s,
                "direction": burn.direction,
                "delta_v_mps": burn.delta_v_mps,
            }
            for object_id, burn in burns.items()
        },
        "movers": sorted(k for k, b in burns.items() if b is not None and not b.is_baseline),
        "total_delta_v_mps": round(sum(b.delta_v_mps for b in burns.values() if b is not None), 6),
        "pairs": pairs,
        "closest_m": closest,
        "over_budget": over_budget,
        "status": "PASS" if closest is not None and closest >= floor and not over_budget else "BLOCK",
        "comfortable": closest is not None and closest >= floor * MARGINAL_CLEARANCE_RATIO and not over_budget,
    }


def independent_plan(document: dict, policy: Policy, operator: str, counterpart: str) -> dict:
    """What one operator would do alone: rank against the other, verify with it holding."""
    trajectories, horizon = _trajectories(document)
    search = evaluate_candidates(
        trajectories[operator], trajectories[counterpart], counterpart, policy, horizon
    )
    for evaluation in search.qualified:
        if evaluation.candidate.is_baseline:
            continue
        check = joint_check(document, policy, {operator: evaluation.candidate})
        if check["comfortable"]:
            return {"operator": operator, "candidate": evaluation.candidate, "solo_check": check}
    return {"operator": operator, "candidate": None, "solo_check": None}


def _mirror(candidate: Candidate) -> Candidate:
    flipped = DIRECTION_RETROGRADE if candidate.direction == DIRECTION_PROGRADE else DIRECTION_PROGRADE
    slug = "ret" if flipped == DIRECTION_RETROGRADE else "pro"
    parts = candidate.candidate_id.split("_")
    return replace(candidate, direction=flipped, candidate_id=f"{parts[0]}_{slug}_{parts[-1]}")


def coordinate(document: dict, policy: Policy, names: dict[str, str] | None = None) -> dict:
    operators = operator_ids(document)
    if len(operators) < 2:
        raise CoordinationError("this scenario has no second operator's satellite")
    ours, theirs = operators[0], operators[1]
    names = names or {}
    labels = {o["object_id"]: o.get("operator") or o["name"] for o in document["objects"]}
    labels.update(names)

    ours_plan = independent_plan(document, policy, ours, theirs)
    theirs_plan = independent_plan(document, policy, theirs, ours)
    ours_best, theirs_best = ours_plan["candidate"], theirs_plan["candidate"]

    plans = []

    def add(plan_id: str, label: str, burns: dict) -> None:
        if any(b is None for b in burns.values()):
            return
        plans.append({"plan_id": plan_id, "label": label, **joint_check(document, policy, burns)})

    baseline = joint_check(document, policy, {})
    add("both_as_planned", "Both operators burn as each planned alone", {ours: ours_best, theirs: theirs_best})
    add("only_ours", f"Only {labels.get(ours, ours)} burns", {ours: ours_best})
    add("only_theirs", f"Only {labels.get(theirs, theirs)} burns", {theirs: theirs_best})
    if ours_best is not None and theirs_best is not None:
        add("partner_reversed", "Both burn, the partner in the reverse direction", {ours: ours_best, theirs: _mirror(theirs_best)})

    acceptable = [p for p in plans if p["comfortable"]]
    agreed = min(
        acceptable,
        key=lambda p: (p["total_delta_v_mps"], len(p["movers"]), -p["closest_m"], p["plan_id"]),
    ) if acceptable else None

    result = {
        "mode": "OPERATOR_COORDINATION",
        "scenario_id": document["scenario_id"],
        "input_hash": document.get("input_hash", ""),
        "operators": [
            {"object_id": ours, "label": labels.get(ours, ours), "role": "OURS"},
            {"object_id": theirs, "label": labels.get(theirs, theirs), "role": "PARTNER"},
        ],
        "floor_m": policy.min_separation_m,
        "comfortable_m": policy.min_separation_m * MARGINAL_CLEARANCE_RATIO,
        "if_nobody_moves": baseline,
        "independent_plans": [
            {
                "operator": p["operator"],
                "candidate_id": p["candidate"].candidate_id if p["candidate"] else None,
                "burn_t_s": p["candidate"].burn_t_s if p["candidate"] else None,
                "direction": p["candidate"].direction if p["candidate"] else None,
                "delta_v_mps": p["candidate"].delta_v_mps if p["candidate"] else None,
                "solo_closest_m": p["solo_check"]["closest_m"] if p["solo_check"] else None,
            }
            for p in (ours_plan, theirs_plan)
        ],
        "plans": plans,
        "rule": RULE,
        "agreed_plan_id": agreed["plan_id"] if agreed else None,
    }
    agreement = {k: result[k] for k in ("scenario_id", "input_hash", "operators", "rule", "agreed_plan_id")}
    agreement["agreed_burns"] = agreed["burns"] if agreed else None
    result["agreement_sha256"] = hashlib.sha256(json.dumps(agreement, sort_keys=True).encode()).hexdigest()
    return result
