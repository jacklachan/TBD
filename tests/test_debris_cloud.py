"""The debris-stream fixture, re-checked from its serialized JSON.

Rebuilds every trajectory with the independent verifier rather than trusting
the generation evidence, the same way test_scenarios.py checks the others.
"""

import json
from pathlib import Path

import pytest

from backend.agent.reviewer import MARGINAL_CLEARANCE_RATIO
from backend.planning.candidates import candidate_from_id
from backend.planning.policy import policy_from_document
from backend.planning.verifier import validate_candidate

FIXTURE = Path(__file__).resolve().parents[1] / "scenarios" / "variants" / "debris_cloud.json"


@pytest.fixture(scope="module")
def cloud():
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return document, policy_from_document(document)


def _check(cloud, candidate_id):
    document, policy = cloud
    return validate_candidate(document, policy, candidate_from_id(candidate_id, 1))


def test_the_stream_is_more_than_two_objects(cloud):
    document, _ = cloud
    debris = [o for o in document["objects"] if o["kind"] == "DEBRIS"]
    assert len(debris) >= 12
    assert document["provenance"]["synthetic_conjunction"] is True


def test_doing_nothing_still_meets_the_primary_threat(cloud):
    result = _check(cloud, "baseline")
    assert result.status == "BLOCK"
    assert result.closest().other_object_id == "DEB-1"
    assert result.closest().min_separation_m == pytest.approx(133.698, abs=1e-2)


def test_both_obvious_fixes_are_vetoed_by_different_objects(cloud):
    evidence = cloud[0]["generation_evidence"]
    first = _check(cloud, evidence["trap_candidate_id"])
    second = _check(cloud, evidence["second_trap_candidate_id"])
    assert first.status == second.status == "BLOCK"
    assert first.closest().other_object_id == "DEB-2"
    assert second.closest().other_object_id == evidence["second_trap_blocked_by"]
    assert second.closest().other_object_id.startswith("FRG-")


def test_the_answer_clears_every_object_comfortably(cloud):
    document, policy = cloud
    answer = _check(cloud, document["generation_evidence"]["answer_candidate_id"])
    assert answer.status == "PASS"
    assert len(answer.evaluated_object_ids) == len(document["objects"]) - 1
    assert answer.closest().min_separation_m >= policy.min_separation_m * MARGINAL_CLEARANCE_RATIO
