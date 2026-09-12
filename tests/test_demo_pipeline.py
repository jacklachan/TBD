"""The Gate 2 chain must reach a defensible end state on every fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.demo_pipeline import (
    OUTCOME_BASELINE_OK,
    OUTCOME_NONE,
    OUTCOME_VERIFIED,
    SCENARIO_PATHS,
    run,
)

pytestmark = pytest.mark.skipif(
    not SCENARIO_PATHS["primary"].exists(),
    reason="fixtures not generated; run `python scenarios/gen.py`",
)


def test_signature_case_rejects_then_verifies():
    record = run("primary")

    assert record["outcome"] == OUTCOME_VERIFIED
    assert record["candidate_count"] == 25

    statuses = [(v["candidate_id"], v["status"]) for v in record["validations"]]
    rejected = [cid for cid, status in statuses if status != "PASS"]
    passed = [cid for cid, status in statuses if status == "PASS"]

    print(f"\n[pipeline] rejected {rejected} then verified {passed}")

    # The point of the case: the search's own top pick is rejected first.
    assert record["validations"][0]["provisional_rank"] == 1
    assert record["validations"][0]["status"] == "BLOCK"
    assert rejected, "nothing was rejected; the secondary conflict is not exercised"
    assert len(passed) == 1
    assert record["approved_candidate_id"] == passed[0]

    # Every rejection must name the object that caused it, and it must not be
    # the primary threat -- otherwise this is an ordinary screening failure and
    # not the secondary conflict.
    for validation in record["validations"]:
        if validation["status"] == "PASS":
            continue
        below = [
            e
            for e in validation["encounters"]
            if e["min_separation_m"] < record["policy"]["min_separation_m"]
        ]
        assert below
        assert all(e["other_object_id"] != "DEB-1" for e in below)


def test_every_validation_screened_both_objects():
    record = run("primary")
    for validation in record["validations"]:
        assert validation["evaluated_object_ids"] == ["DEB-1", "DEB-2"]
        assert validation["sample_step_s"] == 1.0


def test_search_and_verifier_agree_throughout_the_chain():
    record = run("primary")
    for validation in record["validations"]:
        if validation["max_primary_distance_disagreement_m"] is None:
            continue
        assert validation["max_primary_distance_disagreement_m"] < 1.0
        assert validation["primary_time_disagreement_s"] < 0.1


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("no_encounter", OUTCOME_BASELINE_OK),
        ("simple_conflict", OUTCOME_VERIFIED),
        ("no_feasible", OUTCOME_NONE),
    ],
)
def test_variants_reach_their_expected_outcome(scenario, expected):
    record = run(scenario)
    print(f"\n[pipeline/{scenario}] {record['outcome']} in {record['total_seconds']:.2f} s")
    assert record["outcome"] == expected


def test_infeasible_case_produces_no_approved_candidate():
    record = run("no_feasible")
    assert "approved_candidate_id" not in record
    assert record["search_status"] == "NO_PRIMARY_QUALIFIED_OPTION"


def test_record_carries_provenance_and_versions():
    record = run("primary")
    assert record["provenance"]["synthetic_conjunction"] is True
    assert record["provenance"]["norad_id"] > 0
    assert record["input_hash"]
    assert record["policy"]["policy_version"] >= 1
