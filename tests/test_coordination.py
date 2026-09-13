"""Two operators on one pass, recomputed from the committed fixture."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.coordination import CoordinationError, coordinate
from backend.planning.policy import policy_from_document
from backend.store import Store

FIXTURE = Path(__file__).resolve().parents[1] / "scenarios" / "variants" / "two_operators.json"


@pytest.fixture(scope="module")
def result():
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return coordinate(document, policy_from_document(document))


def test_each_operator_has_a_plan_that_works_alone(result):
    for plan in result["independent_plans"]:
        assert plan["candidate_id"] is not None
        assert plan["solo_closest_m"] >= result["comfortable_m"]


def test_executing_both_independent_plans_is_unsafe(result):
    both = next(p for p in result["plans"] if p["plan_id"] == "both_as_planned")
    assert both["status"] == "BLOCK"
    assert both["closest_m"] < result["floor_m"]
    assert set(both["movers"]) == {"SAT-1", "OPS-B"}


def test_the_agreed_plan_follows_the_published_rule(result):
    acceptable = [p for p in result["plans"] if p["comfortable"]]
    agreed = next(p for p in result["plans"] if p["plan_id"] == result["agreed_plan_id"])
    assert agreed in acceptable
    assert agreed["total_delta_v_mps"] == min(p["total_delta_v_mps"] for p in acceptable)
    assert len(agreed["movers"]) == 1
    assert len(result["agreement_sha256"]) == 64


def test_a_single_operator_scenario_has_nobody_to_coordinate_with():
    document = json.loads((FIXTURE.parents[1] / "primary.json").read_text(encoding="utf-8"))
    with pytest.raises(CoordinationError):
        coordinate(document, policy_from_document(document))


def test_the_endpoint_serves_the_same_answer(result):
    client = TestClient(create_app(store=Store(":memory:")))
    case = client.post("/cases", json={"scenario_id": "two_operators"}).json()
    assert [o["maneuverable"] for o in case["scenario"]["objects"]].count(True) == 2
    served = client.get(f"/cases/{case['case_id']}/coordination").json()
    assert served["agreed_plan_id"] == result["agreed_plan_id"]
    assert served["agreement_sha256"] == result["agreement_sha256"]
