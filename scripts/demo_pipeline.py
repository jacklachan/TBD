"""Gate 2 artifact: the whole decision chain on stdout, no UI and no model.

    python scripts/demo_pipeline.py
    python scripts/demo_pipeline.py --scenario no_feasible
    python scripts/demo_pipeline.py --json

Prints the scenario provenance, the option count actually evaluated, the
baseline result, the option the search ranks first, the verifier's independent
screening of that option, and the alternative that survives full validation.

Exit code is 0 only when the chain reaches a defensible end state -- a verified
approvable option, or an honest "no option qualifies". Anything else is a
non-zero exit, so this doubles as a gate check in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.planning.policy import policy_from_document  # noqa: E402
from backend.planning.search import (  # noqa: E402
    STATUS_NO_PRIMARY_QUALIFIED_OPTION,
    evaluate_candidates,
)
from backend.planning.verifier import (  # noqa: E402
    STATUS_PASS,
    reconstruct,
    validate_candidate,
)

SCENARIO_PATHS = {
    "primary": REPO_ROOT / "scenarios" / "primary.json",
    "no_encounter": REPO_ROOT / "scenarios" / "variants" / "no_encounter.json",
    "simple_conflict": REPO_ROOT / "scenarios" / "variants" / "simple_conflict.json",
    "no_feasible": REPO_ROOT / "scenarios" / "variants" / "no_feasible.json",
}

OUTCOME_VERIFIED = "VERIFIED_OPTION"
OUTCOME_BASELINE_OK = "BASELINE_ACCEPTABLE"
OUTCOME_NONE = "NO_APPROVABLE_OPTION"


def _metres(value: float) -> str:
    return f"{value:,.1f} m"


def run(scenario_key: str) -> dict:
    """Execute the chain and return a machine-readable record of what happened."""
    path = SCENARIO_PATHS[scenario_key]
    document = json.loads(path.read_text(encoding="utf-8"))
    policy = policy_from_document(document)
    scenario = reconstruct(document)

    started = time.perf_counter()
    search = evaluate_candidates(
        scenario.satellite,
        scenario.debris[scenario.primary_threat_id],
        scenario.primary_threat_id,
        policy,
        scenario.horizon_s,
    )
    search_seconds = time.perf_counter() - started

    record: dict = {
        "scenario_id": document["scenario_id"],
        "scenario_version": document["scenario_version"],
        "input_hash": document["input_hash"],
        "seed": document["seed"],
        "provenance": {
            "norad_id": document["provenance"]["norad_id"],
            "object_name": document["provenance"]["object_name"],
            "tle_epoch_utc": document["provenance"]["tle_epoch_utc"],
            "frame": document["provenance"]["frame"],
            "synthetic_conjunction": document["provenance"]["synthetic_conjunction"],
        },
        "policy": {
            "policy_version": policy.policy_version,
            "max_delta_v_mps": policy.max_delta_v_mps,
            "min_separation_m": policy.min_separation_m,
            "blocked_windows": [w.window_id for w in policy.blocked_windows],
        },
        "candidate_count": search.candidate_count,
        "search_status": search.status,
        "search_seconds": search_seconds,
        "baseline": {
            "min_separation_m": search.baseline.primary_encounter.min_separation_m,
            "tca_s": search.baseline.primary_encounter.tca_s,
            "primary_qualified": search.baseline.primary_qualified,
            "reason_codes": list(search.baseline.reason_codes),
        },
        "qualified_against_primary": [
            e.candidate.candidate_id for e in search.qualified if not e.candidate.is_baseline
        ],
        "validations": [],
    }

    # A safe baseline is a real answer; do not manufacture a manoeuvre for it.
    if search.baseline.primary_qualified:
        validation = validate_candidate(document, policy, search.baseline.candidate)
        record["validations"].append(_validation_record(validation, provisional_rank=None))
        record["outcome"] = (
            OUTCOME_BASELINE_OK if validation.status == STATUS_PASS else OUTCOME_NONE
        )
        record["total_seconds"] = time.perf_counter() - started
        return record

    if search.status == STATUS_NO_PRIMARY_QUALIFIED_OPTION:
        record["outcome"] = OUTCOME_NONE
        record["total_seconds"] = time.perf_counter() - started
        return record

    # Walk the ranking in order, validating each provisional pick until one
    # survives. The rejections along the way are the interesting part.
    for rank, evaluation in enumerate(search.qualified, start=1):
        if evaluation.candidate.is_baseline:
            continue
        validation = validate_candidate(
            document,
            policy,
            evaluation.candidate,
            expected_primary_encounter={
                "min_separation_m": evaluation.primary_encounter.min_separation_m,
                "tca_s": evaluation.primary_encounter.tca_s,
            },
            expected_scenario_version=document["scenario_version"],
        )
        record["validations"].append(_validation_record(validation, provisional_rank=rank))
        if validation.status == STATUS_PASS:
            record["outcome"] = OUTCOME_VERIFIED
            record["approved_candidate_id"] = validation.candidate_id
            break
    else:
        record["outcome"] = OUTCOME_NONE

    record["total_seconds"] = time.perf_counter() - started
    return record


def _validation_record(validation, provisional_rank: int | None) -> dict:
    return {
        "candidate_id": validation.candidate_id,
        "provisional_rank": provisional_rank,
        "status": validation.status,
        "reason_codes": list(validation.reason_codes),
        "validation_id": validation.validation_id,
        "evaluated_object_ids": list(validation.evaluated_object_ids),
        "sample_step_s": validation.sample_step_s,
        "method": validation.method,
        "max_primary_distance_disagreement_m": validation.max_primary_distance_disagreement_m,
        "primary_time_disagreement_s": validation.primary_time_disagreement_s,
        "encounters": [
            {
                "other_object_id": e.other_object_id,
                "tca_s": e.tca_s,
                "min_separation_m": e.min_separation_m,
                "relative_speed_mps": e.relative_speed_mps,
                "boundary_kind": e.boundary_kind,
                "ambiguous_time": e.ambiguous_time,
            }
            for e in validation.encounters
        ],
    }


def report(record: dict) -> None:
    provenance = record["provenance"]
    policy = record["policy"]

    print(f"scenario   {record['scenario_id']} v{record['scenario_version']}  seed {record['seed']}")
    print(f"           input hash {record['input_hash'][:16]}...")
    print(
        f"seed orbit {provenance['object_name']} (NORAD {provenance['norad_id']}) "
        f"epoch {provenance['tle_epoch_utc']}"
    )
    print(
        f"           frame {provenance['frame']}, "
        f"synthetic conjunction: {provenance['synthetic_conjunction']}"
    )
    print(
        f"policy     v{policy['policy_version']}  budget {policy['max_delta_v_mps']} m/s  "
        f"floor {policy['min_separation_m']:,.0f} m  "
        f"blocked windows {policy['blocked_windows'] or 'none'}"
    )
    print()

    baseline = record["baseline"]
    verdict = "acceptable" if baseline["primary_qualified"] else "UNSAFE"
    print(
        f"do nothing         {_metres(baseline['min_separation_m'])} at "
        f"{baseline['tca_s']:,.0f} s  -> {verdict}  {baseline['reason_codes']}"
    )
    print(
        f"search             {record['candidate_count']} options evaluated, "
        f"{len(record['qualified_against_primary'])} qualify against the primary "
        f"threat  [{record['search_status']}]  {record['search_seconds']:.2f} s"
    )
    print()

    for entry in record["validations"]:
        rank = f"rank {entry['provisional_rank']}" if entry["provisional_rank"] else "baseline"
        marker = "PASS " if entry["status"] == STATUS_PASS else entry["status"]
        print(f"validate {entry['candidate_id']:<14} ({rank})  -> {marker}  {entry['reason_codes']}")
        print(
            f"         screened {entry['evaluated_object_ids']} at "
            f"{entry['sample_step_s']} s via {entry['method']}"
        )
        for encounter in entry["encounters"]:
            flag = "  <-- below floor" if encounter["min_separation_m"] < policy["min_separation_m"] else ""
            print(
                f"           {encounter['other_object_id']}  "
                f"{_metres(encounter['min_separation_m']):>14}  at "
                f"{encounter['tca_s']:>9,.1f} s  "
                f"{encounter['relative_speed_mps']:>8,.0f} m/s  "
                f"{encounter['boundary_kind']}{flag}"
            )
        if entry["max_primary_distance_disagreement_m"] is not None:
            print(
                f"         search agreement: "
                f"{entry['max_primary_distance_disagreement_m']:.3e} m, "
                f"{entry['primary_time_disagreement_s']:.3e} s"
            )
        print()

    outcome = record["outcome"]
    if outcome == OUTCOME_VERIFIED:
        rejected = [v["candidate_id"] for v in record["validations"] if v["status"] != STATUS_PASS]
        print(f"OUTCOME    verified option {record['approved_candidate_id']}")
        if rejected:
            print(f"           rejected on the way: {', '.join(rejected)}")
    elif outcome == OUTCOME_BASELINE_OK:
        print("OUTCOME    no action needed; doing nothing passes full validation")
    else:
        print("OUTCOME    no safe option found in the supported search set")
    print(f"           {record['total_seconds']:.2f} s total")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIO_PATHS), default="primary")
    parser.add_argument("--json", action="store_true", help="emit the record as JSON")
    args = parser.parse_args()

    path = SCENARIO_PATHS[args.scenario]
    if not path.exists():
        print(f"{path.relative_to(REPO_ROOT)} missing -- run `python scenarios/gen.py`")
        return 2

    record = run(args.scenario)

    if args.json:
        print(json.dumps(record, indent=2))
    else:
        report(record)

    # Reaching a defensible end state is the pass condition. "No safe option"
    # is defensible; failing to decide is not.
    return 0 if record["outcome"] in (OUTCOME_VERIFIED, OUTCOME_BASELINE_OK, OUTCOME_NONE) else 1


if __name__ == "__main__":
    sys.exit(main())
