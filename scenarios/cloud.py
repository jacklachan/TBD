"""The signature case, flown through a synthetic breakup debris stream.

Starts from the committed ``primary.json`` -- the satellite, DEB-1 and DEB-2 are
kept exactly, so the verified first trap (133.7 m, then 523.2 m) is unchanged --
and adds two things, both searched for rather than hand-tuned:

* **A second trap.** One fragment is constructed backward from an encounter
  with the option that would otherwise be the answer, so the obvious second fix
  fails too and the verified answer is further down the ranking.
* **A breakup stream.** A synthetic parent object crosses the satellite's orbit a
  few kilometres away and broke up hours before epoch; its fragments spread
  along its track and the satellite passes through them repeatedly. Each
  fragment is kept only if it stays clear of every screened option by a margin,
  so the stream adds objects to screen without silently changing a verdict.

Every accepted fixture is then re-verified end to end with the independent
verifier against all objects, and the facts are recorded as generation evidence.

    python scenarios/cloud.py           # write scenarios/variants/debris_cloud.json
    python scenarios/cloud.py --check   # build and verify, write nothing
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.kepler import propagate  # noqa: E402
from backend.planning.candidates import generate_candidates  # noqa: E402
from backend.planning.policy import policy_from_document  # noqa: E402
from backend.planning.search import apply_candidate, evaluate_candidates  # noqa: E402
from backend.planning.verifier import (  # noqa: E402
    STATUS_BLOCK,
    STATUS_PASS,
    reconstruct,
    validate_candidate,
)
from backend.agent.reviewer import MARGINAL_CLEARANCE_RATIO  # noqa: E402
from scenarios.gen import (  # noqa: E402
    HORIZON_S,
    GenerationError,
    _closest,
    construct_debris,
    is_supported_orbit,
    verify_construction,
)

SCENARIO_ID = "debris_cloud"
SEED = 3001
FRAGMENT_COUNT = 10
MAX_ATTEMPTS = 120
MAX_FRAGMENT_DRAWS = 600
OUTPUT = REPO_ROOT / "scenarios" / "variants" / f"{SCENARIO_ID}.json"

# A stream fragment must stay this many floors away from the baseline and every
# grid option, so it can never be the reason a verdict changes.
STREAM_CLEARANCE_FLOORS = 1.5


def _entry(object_id: str, name: str, r: np.ndarray, v: np.ndarray) -> dict:
    return {
        "object_id": object_id,
        "name": name,
        "kind": "DEBRIS",
        "maneuverable": False,
        "initial_state": {"r_m": [float(x) for x in r], "v_mps": [float(x) for x in v]},
    }


def _validate_all(document: dict, policy, candidates) -> dict:
    return {
        c.candidate_id: validate_candidate(document, policy, c)
        for c in candidates
    }


def build(seed: int = SEED) -> dict:
    primary = json.loads((REPO_ROOT / "scenarios" / "primary.json").read_text(encoding="utf-8"))
    policy = policy_from_document(primary)
    floor = policy.min_separation_m
    comfortable = floor * MARGINAL_CLEARANCE_RATIO
    scenario = reconstruct(primary)
    satellite = scenario.satellite

    search = evaluate_candidates(
        satellite, scenario.debris["DEB-1"], "DEB-1", policy, HORIZON_S
    )
    ranked = [e.candidate for e in search.qualified if not e.candidate.is_baseline]
    trajectories = {c.candidate_id: apply_candidate(satellite, c) for c in ranked}
    trap = ranked[0]

    before = _validate_all(primary, policy, ranked)
    rescue = next(c for c in ranked if before[c.candidate_id].status == STATUS_PASS)

    rng = np.random.default_rng(seed)
    rejected: list[str] = []
    others = [c for c in ranked if c.candidate_id not in (trap.candidate_id, rescue.candidate_id)]

    for attempt in range(MAX_ATTEMPTS):
        # ---- second trap: a fragment on the rescue option's path -------------
        try:
            tca = float(rng.uniform(14_000.0, 20_500.0))
            miss = float(rng.uniform(150.0, 500.0))
            trap2 = construct_debris(
                trajectories[rescue.candidate_id],
                tca,
                miss,
                float(rng.uniform(6000.0, 12000.0)),
                float(rng.uniform(0.0, 2.0 * np.pi)),
            )
        except GenerationError as exc:
            rejected.append(f"attempt {attempt}: second trap construction -- {exc}")
            continue
        ok, detail = verify_construction(trajectories[rescue.candidate_id], trap2, "T2", tca, miss)
        if not ok:
            rejected.append(f"attempt {attempt}: second trap did not reproduce -- {detail}")
            continue
        baseline_vs = _closest(satellite, trap2, "T2")
        if baseline_vs is None or baseline_vs.min_separation_m < 3.0 * floor:
            rejected.append(f"attempt {attempt}: second trap is near the baseline")
            continue
        # Some other option must clear it comfortably, or the case has no answer.
        if not any(
            (enc := _closest(trajectories[c.candidate_id], trap2, "T2")) is not None
            and enc.min_separation_m >= comfortable
            and before[c.candidate_id].status == STATUS_PASS
            and before[c.candidate_id].closest().min_separation_m >= comfortable
            for c in others
        ):
            rejected.append(f"attempt {attempt}: no other option clears the second trap")
            continue

        # ---- breakup stream ----------------------------------------------------
        try:
            parent = construct_debris(
                satellite,
                float(rng.uniform(2_500.0, 9_000.0)),
                float(rng.uniform(4_000.0, 9_000.0)),
                float(rng.uniform(7000.0, 11000.0)),
                float(rng.uniform(0.0, 2.0 * np.pi)),
            )
        except GenerationError as exc:
            rejected.append(f"attempt {attempt}: parent construction -- {exc}")
            continue
        breakup_s = -float(rng.uniform(3_600.0, 10_800.0))
        r_b, v_b = propagate(parent.arcs[0].r0_m, parent.arcs[0].v0_mps, np.array([breakup_s]))

        stream: list[tuple[np.ndarray, np.ndarray, float]] = []
        paths = [satellite, *trajectories.values()]
        for _ in range(MAX_FRAGMENT_DRAWS):
            if len(stream) == FRAGMENT_COUNT:
                break
            direction = rng.normal(size=3)
            direction /= np.linalg.norm(direction)
            dv = direction * float(rng.uniform(0.3, 4.0))
            r_e, v_e = propagate(r_b[0], v_b[0] + dv, np.array([-breakup_s]))
            if not is_supported_orbit(r_e[0], v_e[0]):
                continue
            from backend.core.trajectory import Trajectory

            fragment = Trajectory.from_state(r_e[0], v_e[0])
            closest = min(
                (e.min_separation_m for p in paths if (e := _closest(p, fragment, "F")) is not None),
                default=float("inf"),
            )
            if closest < STREAM_CLEARANCE_FLOORS * floor:
                continue
            stream.append((r_e[0], v_e[0], closest))

        if len(stream) < FRAGMENT_COUNT:
            rejected.append(f"attempt {attempt}: stream too thin ({len(stream)} fragments kept)")
            continue

        # ---- assemble, with the second trap hidden among the fragments ---------
        slot = int(rng.integers(0, FRAGMENT_COUNT + 1))
        fragments = [(r, v) for r, v, _ in stream]
        fragments.insert(slot, (trap2.arcs[0].r0_m, trap2.arcs[0].v0_mps))
        document = copy.deepcopy(primary)
        document.pop("input_hash", None)
        for index, (r, v) in enumerate(fragments, start=1):
            document["objects"].append(_entry(f"FRG-{index:02d}", f"Breakup fragment {index}", r, v))
        trap2_id = f"FRG-{slot + 1:02d}"

        # ---- the facts, re-verified against every object -----------------------
        after = _validate_all(document, policy, ranked)
        trap_result = after[trap.candidate_id]
        rescue_result = after[rescue.candidate_id]
        answer = next((c for c in ranked if after[c.candidate_id].status == STATUS_PASS), None)
        if trap_result.status != STATUS_BLOCK or trap_result.closest().other_object_id != "DEB-2":
            rejected.append(f"attempt {attempt}: first trap no longer blocked by DEB-2")
            continue
        if rescue_result.status != STATUS_BLOCK or rescue_result.closest().other_object_id != trap2_id:
            rejected.append(f"attempt {attempt}: second trap does not block the old answer")
            continue
        if answer is None or after[answer.candidate_id].closest().min_separation_m < comfortable:
            rejected.append(f"attempt {attempt}: first verified answer is marginal or missing")
            continue
        baseline_result = validate_candidate(document, policy, generate_candidates(1)[0])
        if baseline_result.closest().other_object_id != "DEB-1":
            rejected.append(f"attempt {attempt}: baseline's closest object is not DEB-1")
            continue

        answer_closest = after[answer.candidate_id].closest()
        document["scenario_id"] = SCENARIO_ID
        document["seed"] = seed
        document["description"] = (
            "The second encounter inside a breakup debris stream: the satellite "
            f"crosses {FRAGMENT_COUNT + 1} fragments' paths, and the obvious second "
            "fix runs into one of them."
        )
        document["provenance"]["note"] = (
            "Satellite initial state derived from a real catalogue TLE at its own "
            "epoch. Every other object is synthetic. DEB-1, DEB-2 and one fragment "
            "are constructed backward from chosen encounters; the remaining "
            "fragments come from a simulated breakup of a synthetic parent object "
            "(isotropic 0.3-4 m/s spread) and are kept only if they stay "
            f"{STREAM_CLEARANCE_FLOORS:g} floors clear of every grid option. No "
            "conjunction here is real."
        )
        document["generation_evidence"] = {
            "attempts_used": attempt + 1,
            "based_on": "primary.json",
            "object_count": len(document["objects"]),
            "fragment_count": len(fragments),
            "breakup_s_before_epoch": round(-breakup_s, 1),
            "baseline_vs_primary_m": baseline_result.closest().min_separation_m,
            "trap_candidate_id": trap.candidate_id,
            "trap_blocked_by": "DEB-2",
            "trap_vs_blocking_m": trap_result.closest().min_separation_m,
            "second_trap_candidate_id": rescue.candidate_id,
            "second_trap_blocked_by": trap2_id,
            "second_trap_vs_blocking_m": rescue_result.closest().min_separation_m,
            "answer_candidate_id": answer.candidate_id,
            "answer_closest_m": answer_closest.min_separation_m,
            "answer_closest_object": answer_closest.other_object_id,
            "stream_closest_to_any_option_m": min(c for _, _, c in stream),
            "passing_options": sorted(k for k, v in after.items() if v.status == STATUS_PASS),
            "rejected_attempts": rejected[-5:],
        }
        payload = json.dumps(document, sort_keys=True).encode("utf-8")
        document["input_hash"] = hashlib.sha256(payload).hexdigest()
        return document

    raise GenerationError(
        f"no debris-cloud case in {MAX_ATTEMPTS} attempts. Last reasons: {rejected[-5:]}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = build(args.seed)
    for key, value in document["generation_evidence"].items():
        if key != "rejected_attempts":
            print(f"  {key:32s} {value:,.3f}" if isinstance(value, float) else f"  {key:32s} {value}")
    if args.check:
        print("--check: debris cloud built and verified; nothing written.")
        return 0
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"  written -> {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
