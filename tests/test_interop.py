"""The CDM round trip: written here, read back, and recomputed independently.

The point of these tests is not that the file parses. It is that a record
carries enough for someone else to disagree with it — so the tampering cases
matter more than the happy path.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agent.llm import ScriptedProvider, text_reply, tool_call
from backend.api import create_app
from backend.interop import (
    CdmError,
    parse_cdm,
    scenario_from_cdm,
    verify_cdm,
    write_cdm,
)
from backend.store import Store

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = REPO_ROOT / "scenarios" / "primary.json"

pytestmark = pytest.mark.skipif(
    not PRIMARY_PATH.exists(), reason="fixtures not generated; run scenarios/gen.py"
)

TRAP = "t30_ret_100"
RESCUE = "t30_ret_200"


def investigation():
    return ScriptedProvider(
        [
            tool_call("get_case_briefing"),
            tool_call("evaluate_candidates"),
            tool_call("validate_proposal", candidate_id=TRAP),
            tool_call("validate_proposal", candidate_id=RESCUE),
            text_reply(f"Recommend {RESCUE}."),
        ]
    )


@pytest.fixture(scope="module")
def issued_cdm() -> str:
    """A record produced the way the application actually produces one."""
    client = TestClient(
        create_app(store=Store(":memory:"), provider_factory=investigation)
    )
    case = client.post("/cases", json={"scenario_id": "primary"}).json()
    run = client.post(
        f"/cases/{case['case_id']}/plan",
        json={"expected_scenario_version": 1, "expected_policy_version": 1},
    ).json()
    for _ in range(300):
        if client.get(f"/runs/{run['run_id']}").json()["status"] != "RUNNING":
            break
        time.sleep(0.05)
    return client.get(
        f"/cases/{case['case_id']}/export", params={"format": "cdm"}
    ).text


# --------------------------------------------------------------------- write


def test_the_record_carries_state_vectors_not_just_conclusions(issued_cdm):
    """Without these the receiver can read the claim but not check it."""
    for key in ("X =", "Y =", "Z =", "X_DOT =", "Y_DOT =", "Z_DOT ="):
        assert key in issued_cdm, key
    assert "[km]" in issued_cdm and "[km/s]" in issued_cdm


def test_the_record_carries_the_manoeuvre(issued_cdm):
    assert "ORION_WEST_BURN_T_S" in issued_cdm
    assert "ORION_WEST_BURN_DIRECTION" in issued_cdm
    assert "ORION_WEST_DELTA_V_MPS" in issued_cdm


# ---------------------------------------------------------------------- read


def test_parsing_recovers_objects_states_and_the_burn(issued_cdm):
    parsed = parse_cdm(issued_cdm)
    assert len(parsed.objects) >= 2
    assert parsed.satellite_designator == "SAT-1"
    assert parsed.candidate_id == RESCUE
    assert parsed.burn_t_s == 1800.0
    assert parsed.burn_direction == "RETROGRADE"
    assert parsed.delta_v_mps == pytest.approx(0.20)

    satellite = next(o for o in parsed.objects if o.designator == "SAT-1")
    # Kilometres on the wire, metres in memory.
    assert 6.0e6 < sum(c * c for c in satellite.r_m) ** 0.5 < 8.0e6
    assert 6.0e3 < sum(c * c for c in satellite.v_mps) ** 0.5 < 9.0e3


def test_the_scenario_is_rebuilt_from_the_message_alone(issued_cdm):
    """Nothing may be looked up locally, or the record proves nothing."""
    document = scenario_from_cdm(parse_cdm(issued_cdm))
    assert document["provenance"]["source_kind"] == "IMPORTED_CDM"
    assert document["scenario_id"].startswith("imported:")
    assert len(document["objects"]) >= 2
    assert sum(o["maneuverable"] for o in document["objects"]) == 1


# -------------------------------------------------------------------- verify


def test_a_genuine_record_verifies(issued_cdm):
    result = verify_cdm(issued_cdm)
    assert result["verdict"] == "AGREES", result["checks"]
    assert result["independent_result"]["status"] == "PASS"

    worst_distance = max(c["distance_delta_m"] for c in result["checks"])
    worst_time = max(c["time_delta_s"] for c in result["checks"])
    print(
        f"\n[round trip] {len(result['checks'])} claims rechecked — worst "
        f"disagreement {worst_distance:.3e} m, {worst_time:.3e} s"
    )
    assert worst_distance < 1.0
    assert worst_time < 0.1


def test_an_overstated_clearance_is_caught(issued_cdm):
    """The case this feature exists for: a record that claims too much."""
    tampered = issued_cdm.replace(
        "MISS_DISTANCE = 2491.888", "MISS_DISTANCE = 9999.000"
    )
    assert tampered != issued_cdm, "the fixture changed; update the tampered value"

    result = verify_cdm(tampered)
    assert result["verdict"] == "DISAGREES"
    bad = [c for c in result["checks"] if not c["agrees"]]
    assert bad
    assert bad[0]["claimed_miss_distance_m"] == 9999.0
    assert bad[0]["recomputed_miss_distance_m"] == pytest.approx(2491.888, abs=1.0)
    print(f"\n[tampered] {bad[0]['reason']}")


def test_a_moved_state_vector_is_caught(issued_cdm):
    """Changing the geometry changes our answer, not theirs — so they diverge."""
    parsed = parse_cdm(issued_cdm)
    debris = next(o for o in parsed.objects if o.designator != "SAT-1")
    original = f"{debris.r_m[0] / 1000.0:.6f}"
    moved = f"{debris.r_m[0] / 1000.0 + 40.0:.6f}"
    tampered = issued_cdm.replace(f"X = {original} [km]", f"X = {moved} [km]", 1)
    assert tampered != issued_cdm

    result = verify_cdm(tampered)
    assert result["verdict"] == "DISAGREES"


def test_a_record_without_state_vectors_is_refused():
    """Readable is not the same as verifiable, and the difference is the point."""
    stateless = (
        "CCSDS_CDM_VERS = 1.0\n"
        "ORIGINATOR = SOMEONE ELSE\n"
        "TCA = 2026-01-01T00:00:00.000+00:00 + 100.0 [s]\n"
        "MISS_DISTANCE = 250.000 [m]\n"
        "OBJECT = OBJECT1\n"
        "OBJECT_DESIGNATOR = THEIRS\n"
        "OBJECT = OBJECT2\n"
        "OBJECT_DESIGNATOR = OURS\n"
    )
    with pytest.raises(CdmError, match="nothing to recompute"):
        verify_cdm(stateless)


@pytest.mark.parametrize(
    "text,fragment",
    [
        ("", "empty"),
        ("hello world", "not a CDM"),
        ("{\"json\": true}", "not a CDM"),
    ],
)
def test_rubbish_is_refused_with_a_reason(text, fragment):
    with pytest.raises(CdmError, match=fragment):
        verify_cdm(text)


# ------------------------------------------------------------------ endpoint


def test_the_endpoint_verifies_and_reports(issued_cdm):
    client = TestClient(create_app(store=Store(":memory:")))
    response = client.post("/interop/verify-cdm", json={"text": issued_cdm})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "AGREES"
    assert body["originator"] == "ORION WEST"
    assert body["independent_result"]["method"].startswith("scan_1s")
    assert body["manoeuvre"]["delta_v_mps"] == pytest.approx(0.20)


def test_the_endpoint_refuses_rubbish_with_a_typed_error():
    client = TestClient(create_app(store=Store(":memory:")))
    response = client.post("/interop/verify-cdm", json={"text": "not a message"})
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "CDM_UNREADABLE"


def test_the_endpoint_needs_no_case_of_its_own(issued_cdm):
    """A received record is screened on its own terms, not against our fixtures."""
    client = TestClient(create_app(store=Store(":memory:")))
    body = client.post("/interop/verify-cdm", json={"text": issued_cdm}).json()
    assert body["independent_result"]["screened_objects"]
    assert client.get("/cases/case_missing").status_code == 404
