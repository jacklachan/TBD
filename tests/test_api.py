"""API and store: versions gate, approval is not the model's to give, once means once."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agent.llm import LLMError, ScriptedProvider, text_reply, tool_call
from backend.agent.memory import CaseMemory
from backend.api import create_app
from backend.store import IdempotencyConflict, Store

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = REPO_ROOT / "scenarios" / "primary.json"

pytestmark = pytest.mark.skipif(
    not PRIMARY_PATH.exists(), reason="fixtures not generated; run `python scenarios/gen.py`"
)

TRAP = "t30_ret_100"
RESCUE = "t30_ret_200"

ALLOW = '{"decision":"ALLOW","reason_codes":["OK"],"rationale":"Both objects clear."}'
BLOCK = '{"decision":"BLOCK","reason_codes":["MARGINAL"],"rationale":"Too tight."}'


def investigation():
    return ScriptedProvider(
        [
            tool_call("get_case_briefing"),
            tool_call("evaluate_candidates"),
            tool_call("validate_proposal", candidate_id=TRAP),
            tool_call("validate_proposal", candidate_id=RESCUE),
            text_reply(f"Recommend {RESCUE}; {TRAP} was rejected for a second close approach."),
        ]
    )


def make_client(
    reviewer_text: str | None = ALLOW,
    memory: CaseMemory | None = None,
    provider_factory=investigation,
):
    app = create_app(
        store=Store(":memory:"),
        provider_factory=provider_factory,
        reviewer_factory=(lambda: ScriptedProvider([text_reply(reviewer_text)]))
        if reviewer_text
        else None,
        memory=memory,
    )
    return TestClient(app)


def wait_for_run(client: TestClient, run_id: str, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")


def new_case(client: TestClient, scenario_id: str = "primary") -> dict:
    response = client.post("/cases", json={"scenario_id": scenario_id})
    assert response.status_code == 201, response.text
    return response.json()


def run_plan(client: TestClient, case: dict) -> dict:
    response = client.post(
        f"/cases/{case['case_id']}/plan",
        json={
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
    )
    assert response.status_code == 202, response.text
    return wait_for_run(client, response.json()["run_id"])


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------


def test_create_case_returns_a_snapshot_with_provenance():
    client = make_client()
    case = new_case(client)
    assert case["scenario_id"] == "primary"
    assert case["policy_version"] == 1
    assert case["scenario"]["provenance"]["synthetic_conjunction"] is True
    assert case["scenario"]["provenance"]["norad_id"] > 0
    assert case["execution"] is None and case["proposal"] is None


def test_unknown_scenario_and_unknown_case_are_404():
    client = make_client()
    assert client.post("/cases", json={"scenario_id": "nope"}).status_code == 404
    assert client.get("/cases/case_missing").status_code == 404


def test_health_reports_the_model_version():
    assert make_client().get("/health").json()["model_version"]


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def test_plan_run_persists_evidence_and_a_proposal():
    client = make_client()
    case = new_case(client)
    run = run_plan(client, case)

    assert run["status"] == "DONE"
    assert run["result"]["status"] == "PROPOSAL_READY"

    snapshot = client.get(f"/cases/{case['case_id']}").json()
    statuses = {v["candidate_id"]: v["status"] for v in snapshot["validations"]}
    assert statuses[TRAP] == "BLOCK"
    assert statuses[RESCUE] == "PASS"
    assert snapshot["proposal"]["candidate_id"] == RESCUE
    assert snapshot["proposal"]["status"] == "READY"

    sequences = [e["sequence"] for e in snapshot["events"]]
    assert sequences == sorted(sequences) == list(range(1, len(sequences) + 1))
    print(f"\n[api] {len(snapshot['events'])} events, {run['result']['elapsed_s']:.2f} s")


def test_plan_with_a_stale_version_is_rejected():
    client = make_client()
    case = new_case(client)
    response = client.post(
        f"/cases/{case['case_id']}/plan",
        json={"expected_scenario_version": 99, "expected_policy_version": 1},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "STALE_VERSION"


def test_provider_failure_is_a_failed_run_not_a_silent_success():
    app = create_app(
        store=Store(":memory:"),
        provider_factory=lambda: ScriptedProvider([LLMError("503 overloaded")]),
    )
    client = TestClient(app)
    case = new_case(client)
    run = run_plan(client, case)
    assert run["status"] == "DONE"
    assert run["result"]["status"] == "UNRESOLVED"
    assert run["result"]["unresolved_reason"] == "PROVIDER_ERROR"

    snapshot = client.get(f"/cases/{case['case_id']}").json()
    assert snapshot["proposal"] is None


# --------------------------------------------------------------------------
# Approval
# --------------------------------------------------------------------------


def approve(client, case_id, snapshot, key="key-1", proposal_id=None):
    return client.post(
        f"/cases/{case_id}/approve",
        json={
            "proposal_id": proposal_id or snapshot["proposal"]["proposal_id"],
            "expected_scenario_version": snapshot["scenario_version"],
            "expected_policy_version": snapshot["policy_version"],
            "idempotency_key": key,
        },
    )


def test_approval_applies_once_and_repeats_return_the_same_record():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()

    first = approve(client, case["case_id"], snapshot)
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    execution_id = first.json()["execution"]["execution_id"]

    second = approve(client, case["case_id"], snapshot)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["execution"]["execution_id"] == execution_id

    after = client.get(f"/cases/{case['case_id']}").json()
    assert after["execution"]["execution_id"] == execution_id
    assert after["proposal"]["status"] == "EXECUTED"


def test_reusing_an_idempotency_key_for_another_proposal_is_a_conflict():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    store = client.app.state.desk.store
    proposal = store.latest_proposal(case["case_id"])
    store.record_execution(case["case_id"], proposal["proposal_id"], RESCUE, "same-key")
    with pytest.raises(IdempotencyConflict):
        store.record_execution(case["case_id"], "prop_b", TRAP, "same-key")


def test_a_reviewer_block_prevents_approval():
    client = make_client(reviewer_text=BLOCK)
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()

    assert snapshot["proposal"]["status"] == "BLOCKED"
    response = approve(client, case["case_id"], snapshot)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "REVIEWER_BLOCKED"
    assert client.get(f"/cases/{case['case_id']}").json()["execution"] is None


def test_an_unreadable_reviewer_reply_also_prevents_approval():
    client = make_client(reviewer_text="looks fine to me")
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    response = approve(client, case["case_id"], snapshot)
    assert response.status_code == 409
    assert response.json()["detail"]["decision"] == "UNAVAILABLE"


def test_approval_rechecks_the_stored_validation_not_the_proposal_row():
    """Corrupt the proposal's status and approval must still refuse."""
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()

    state = client.app.state.desk
    proposal = state.store.get_proposal(snapshot["proposal"]["proposal_id"])
    blocked = state.store.get_validation(
        [v["validation_id"] for v in snapshot["validations"] if v["candidate_id"] == TRAP][0]
    )
    # Point the proposal at the BLOCKED validation, as a tampered row would.
    proposal["validation_id"] = blocked.validation_id
    state.store._connection.execute(
        "UPDATE proposals SET payload_json = ?, validation_id = ? WHERE proposal_id = ?",
        (json.dumps(proposal), blocked.validation_id, proposal["proposal_id"]),
    )
    state.store._connection.commit()

    response = approve(client, case["case_id"], snapshot)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "NOT_VALIDATED"


def test_approving_an_unknown_proposal_is_404():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    assert approve(client, case["case_id"], snapshot, proposal_id="prop_nope").status_code == 404


# --------------------------------------------------------------------------
# Policy change
# --------------------------------------------------------------------------


def policy_client():
    """Planner first, then a policy interpretation, then a fresh plan."""
    providers = iter(
        [
            investigation(),
            ScriptedProvider(
                [tool_call("get_case_briefing"), tool_call("propose_policy", budget_scale=0.5)]
            ),
            investigation(),
        ]
    )
    app = create_app(
        store=Store(":memory:"),
        provider_factory=lambda: next(providers),
        reviewer_factory=lambda: ScriptedProvider([text_reply(ALLOW)]),
    )
    return TestClient(app)


def test_policy_change_bumps_the_version_and_stales_the_old_proposal():
    client = policy_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    assert snapshot["proposal"]["status"] == "READY"

    preview = client.post(
        f"/cases/{case['case_id']}/policy-preview",
        json={
            "text": "we lost a thruster, halve the fuel budget",
            "expected_scenario_version": snapshot["scenario_version"],
            "expected_policy_version": snapshot["policy_version"],
        },
    )
    assert preview.status_code == 200, preview.text
    diff = preview.json()["diff"]
    assert diff["status"] == "READY"
    assert diff["changes"][0]["after"] == 0.1

    confirm = client.post(
        f"/cases/{case['case_id']}/policy-confirm",
        json={
            "diff_id": diff["diff_id"],
            "expected_scenario_version": snapshot["scenario_version"],
            "expected_policy_version": snapshot["policy_version"],
        },
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["policy_version"] == 2
    assert confirm.json()["policy"]["max_delta_v_mps"] == 0.1

    after = client.get(f"/cases/{case['case_id']}").json()
    assert after["policy_version"] == 2
    assert after["proposal"]["status"] == "STALE"

    # And the stale proposal cannot be approved.
    response = approve(client, case["case_id"], after, proposal_id=after["proposal"]["proposal_id"])
    assert response.status_code == 409
    print(f"\n[api] policy v1 -> v2, prior proposal {after['proposal']['status']}")


def test_confirming_with_a_stale_version_is_rejected():
    client = policy_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    preview = client.post(
        f"/cases/{case['case_id']}/policy-preview",
        json={
            "text": "halve the budget",
            "expected_scenario_version": snapshot["scenario_version"],
            "expected_policy_version": snapshot["policy_version"],
        },
    ).json()

    response = client.post(
        f"/cases/{case['case_id']}/policy-confirm",
        json={
            "diff_id": preview["diff"]["diff_id"],
            "expected_scenario_version": snapshot["scenario_version"],
            "expected_policy_version": 99,
        },
    )
    assert response.status_code == 409


# --------------------------------------------------------------------------
# Visualization
# --------------------------------------------------------------------------


def test_visualization_shares_one_time_grid_and_includes_encounter_times():
    client = make_client()
    case = new_case(client)
    bundle = client.get(
        f"/cases/{case['case_id']}/visualization",
        params={
            "candidate_ids": f"baseline,{TRAP},{RESCUE}",
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
    ).json()

    times = bundle["t_s"]
    assert times == sorted(times) and len(times) == len(set(times))
    assert times[0] == 0.0 and times[-1] == bundle["horizon_s"]

    for variant in bundle["variants"]:
        assert len(variant["min_to_any_m"]) == len(times)
        for series in variant["pair_separations_m"].values():
            assert len(series) == len(times)
        for positions in variant["positions_m"].values():
            assert len(positions) == len(times) and len(positions[0]) == 3

        # Every encounter time must be an actual sample, so an exact minimum is
        # never interpolated.
        for encounter in variant["encounters"]:
            assert any(abs(t - encounter["tca_s"]) < 1e-6 for t in times), encounter

    # Burn epochs are sampled too.
    trap = next(v for v in bundle["variants"] if v["candidate_id"] == TRAP)
    assert any(abs(t - trap["burn_t_s"]) < 1e-6 for t in times)
    print(f"\n[api] bundle {len(times)} samples, {len(bundle['variants'])} variants")


def test_visualization_separations_match_the_positions_it_ships():
    import numpy as np

    client = make_client()
    case = new_case(client)
    bundle = client.get(
        f"/cases/{case['case_id']}/visualization",
        params={
            "candidate_ids": RESCUE,
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
    ).json()

    variant = bundle["variants"][0]
    satellite = np.array(variant["positions_m"][bundle["satellite_id"]])
    for debris_id, series in variant["pair_separations_m"].items():
        debris = np.array(variant["positions_m"][debris_id])
        computed = np.linalg.norm(satellite - debris, axis=1)
        assert np.allclose(computed, series, atol=0.05)


def test_visualization_rejects_too_many_variants_and_unknown_ids():
    client = make_client()
    case = new_case(client)
    params = {
        "expected_scenario_version": case["scenario_version"],
        "expected_policy_version": case["policy_version"],
    }
    too_many = client.get(
        f"/cases/{case['case_id']}/visualization",
        params={**params, "candidate_ids": "baseline,t15_ret_100,t30_ret_100,t45_ret_100"},
    )
    assert too_many.status_code == 422
    unknown = client.get(
        f"/cases/{case['case_id']}/visualization",
        params={**params, "candidate_ids": "t99_pro_999"},
    )
    assert unknown.status_code == 404


# --------------------------------------------------------------------------
# Reset, export, context
# --------------------------------------------------------------------------


def test_reset_creates_a_new_case_and_keeps_the_old_one():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    approve(client, case["case_id"], snapshot)

    fresh = client.post(
        f"/cases/{case['case_id']}/reset",
        json={
            "expected_scenario_version": snapshot["scenario_version"],
            "expected_policy_version": snapshot["policy_version"],
        },
    ).json()

    assert fresh["case_id"] != case["case_id"]
    assert fresh["parent_case_id"] == case["case_id"]
    assert fresh["execution"] is None and fresh["proposal"] is None

    # History survives.
    old = client.get(f"/cases/{case['case_id']}").json()
    assert old["execution"] is not None


def test_export_json_and_markdown_are_self_contained():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    approve(client, case["case_id"], snapshot)

    as_json = client.get(f"/cases/{case['case_id']}/export", params={"format": "json"}).json()
    assert as_json["scenario"]["provenance"]["synthetic_conjunction"] is True
    assert as_json["execution"] is not None

    markdown = client.get(
        f"/cases/{case['case_id']}/export", params={"format": "markdown"}
    ).text
    for expected in (
        "Decision record",
        "synthetic",
        "No collision probability is computed",
        "Simulated only",
        "Limitations",
        RESCUE,
    ):
        assert expected in markdown, expected
    print(f"\n[api] markdown export {len(markdown)} chars")


def test_export_is_deterministic_apart_from_its_timestamp():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    first = client.get(f"/cases/{case['case_id']}/export").json()
    second = client.get(f"/cases/{case['case_id']}/export").json()
    first.pop("runs"), second.pop("runs")
    assert first == second


def test_socrates_context_is_served_from_disk_with_provenance():
    client = make_client()
    response = client.get("/context/socrates")
    if response.status_code == 404:
        pytest.skip("SOCRATES snapshot not present")
    payload = response.json()
    assert 0 < payload["row_count"] <= 10
    assert payload["retrieved_at_utc"]
    assert "NORAD_CAT_ID_1" in payload["rows"][0]
    print(
        f"\n[api] SOCRATES {payload['row_count']} real conjunctions, "
        f"closest {payload['rows'][0]['TCA_RANGE_KM']} km"
    )


def test_memory_from_an_earlier_case_reaches_the_briefing():
    memory = CaseMemory(":memory:")
    memory.record(
        case_id="case_earlier",
        scenario_id="primary",
        outcome="OPERATOR_REJECTED",
        summary="Operator rejected a burn during the ground station pass.",
        detail={"suggestion": "Consider blocking gs_pass_1."},
    )
    client = make_client(memory=memory)
    case = new_case(client)
    run = run_plan(client, case)
    assert run["status"] == "DONE"

    events = client.get(f"/cases/{case['case_id']}").json()["events"]
    assert any(e["event_type"] == "memory" for e in events)
    memory.close()


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------


def test_cors_allows_a_named_dev_origin_but_not_an_arbitrary_one(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    client = make_client()

    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    # An origin nobody named gets no grant. Starlette answers the request; the
    # browser is what refuses to hand the response to the calling page.
    stranger = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in stranger.headers


def test_cors_never_answers_with_a_wildcard(monkeypatch):
    """A wildcard would let any page the operator has open spend the quota."""
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    client = make_client()
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") != "*"


def test_same_origin_deployment_sends_no_cors_headers(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "none")
    client = make_client()
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_explicitly_named_origin_is_honoured(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://user-space.hf.space")
    client = make_client()
    response = client.get("/health", headers={"Origin": "https://user-space.hf.space"})
    assert response.headers.get("access-control-allow-origin") == "https://user-space.hf.space"
    blocked = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in blocked.headers


def test_health_reports_whether_a_key_is_visible():
    payload = make_client().get("/health").json()
    assert "model_access" in payload
    assert payload["planner_model"]


# --------------------------------------------------------------------------
# A scenario ID is a filesystem path component
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario_id",
    [
        "../data/anything",
        "../../etc/hostname",
        "variants/../../README",
        "primary/../primary",
        "/etc/hostname",
        "primary.json",
        "",
        "PRIMARY",
    ],
)
def test_a_scenario_id_that_is_not_a_fixture_name_is_refused(scenario_id, tmp_path):
    """The ID is interpolated into a path, so anything but a fixture name is a 404.

    Without this a request could name a traversal sequence and have any JSON
    file on disk loaded and served as a scenario.
    """
    planted = tmp_path / "data"
    planted.mkdir()
    (planted / "anything.json").write_text(
        PRIMARY_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )

    client = make_client()
    response = client.post("/cases", json={"scenario_id": scenario_id})
    assert response.status_code == 404, response.text


def test_the_real_fixture_names_still_resolve():
    client = make_client()
    for scenario_id in ("primary", "no_encounter", "simple_conflict", "no_feasible"):
        assert new_case(client, scenario_id)["scenario_id"] == scenario_id


# --------------------------------------------------------------------------
# Concurrency on the shared store
# --------------------------------------------------------------------------


def test_concurrent_event_appends_do_not_lose_a_trace():
    """Runs execute on a worker pool and share one connection.

    ``append_events`` reads the last sequence number and then inserts. Without
    serialisation two runs on one case read the same number, and the loser's
    whole trace is rejected by the UNIQUE constraint -- the events vanish and
    the run is reported FAILED for a reason that has nothing to do with it.
    """
    import threading

    from backend.agent.planner import CaseEvent
    from backend.planning.policy import policy_from_document

    document = json.loads(PRIMARY_PATH.read_text(encoding="utf-8"))
    store = Store(":memory:")
    case = store.create_case(document, policy_from_document(document))

    writers, failures = 8, []
    per_writer = 20

    def append(index: int) -> None:
        try:
            store.append_events(
                case.case_id,
                f"run_{index}",
                [
                    CaseEvent(sequence=n, event_type="t", summary="s", duration_ms=0.0)
                    for n in range(per_writer)
                ],
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=append, args=(i,)) for i in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures, failures
    sequences = [event["sequence"] for event in store.events(case.case_id)]
    assert len(sequences) == writers * per_writer
    assert sequences == list(range(1, writers * per_writer + 1))


def test_the_run_reason_is_readable_the_moment_the_run_reads_failed():
    """A poller that sees FAILED must see why in the same response."""
    def exploding():
        raise RuntimeError("provider construction blew up")

    app = create_app(store=Store(":memory:"), provider_factory=exploding)
    client = TestClient(app)
    case = new_case(client)
    run = run_plan(client, case)

    assert run["status"] == "FAILED"
    assert "provider construction blew up" in run["error"]


# --------------------------------------------------------------------------
# CDM export — interoperability
# --------------------------------------------------------------------------


def test_cdm_export_is_shaped_for_another_operator():
    """Coordinating traffic means the result has to mean something elsewhere."""
    client = make_client()
    case = new_case(client)
    run_plan(client, case)

    text = client.get(
        f"/cases/{case['case_id']}/export", params={"format": "cdm"}
    ).text

    for field in (
        "CCSDS_CDM_VERS",
        "CREATION_DATE",
        "ORIGINATOR",
        "TCA",
        "MISS_DISTANCE",
        "RELATIVE_SPEED",
        "OBJECT = OBJECT1",
        "OBJECT = OBJECT2",
        "REF_FRAME",
    ):
        assert field in text, field

    # Both screened objects appear, not just the one that triggered the case.
    assert "DEB-1" in text and "DEB-2" in text


def test_cdm_export_refuses_to_imply_a_probability():
    """A conforming CDM carries covariance; public element sets do not have one.
    Saying so is the difference between interoperable and misleading."""
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    text = client.get(
        f"/cases/{case['case_id']}/export", params={"format": "cdm"}
    ).text

    assert "NOT a conforming CDM" in text
    assert "no covariance" in text
    assert "COVARIANCE_METHOD = NONE" in text
    assert "synthetic" in text.lower()
    # No probability FIELD anywhere. Disclaimers live in COMMENT lines and are
    # allowed to use the word; a keyword-value line carrying one would not be.
    fields = [
        line
        for line in text.splitlines()
        if "=" in line and not line.strip().startswith("COMMENT")
    ]
    assert not any("prob" in line.lower() for line in fields), fields


def test_cdm_export_before_any_screening_claims_nothing_but_carries_the_geometry():
    """Saying "we have not looked yet" is not worth sending. The states are."""
    client = make_client()
    case = new_case(client)
    text = client.get(
        f"/cases/{case['case_id']}/export", params={"format": "cdm"}
    ).text
    assert "No screening has been run" in text
    assert "MISS_DISTANCE" not in text
    assert "TCA =" not in text
    assert text.count("X_DOT =") >= 2, "the receiver must be able to screen it"


def test_export_rejects_an_unknown_format():
    client = make_client()
    case = new_case(client)
    assert (
        client.get(
            f"/cases/{case['case_id']}/export", params={"format": "pdf"}
        ).status_code
        == 422
    )


def test_a_designed_burn_can_be_visualised_like_any_other_option():
    """An operator cannot approve what the workspace refuses to draw."""
    client = make_client()
    case = new_case(client)
    response = client.get(
        f"/cases/{case['case_id']}/visualization",
        params={
            "candidate_ids": "baseline,free_t1500s_ret_150",
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
    )
    assert response.status_code == 200, response.text
    variants = {v["candidate_id"] for v in response.json()["variants"]}
    assert variants == {"baseline", "free_t1500s_ret_150"}


def test_a_designed_burn_outside_the_horizon_is_refused_not_drawn():
    client = make_client()
    case = new_case(client)
    response = client.get(
        f"/cases/{case['case_id']}/visualization",
        params={
            "candidate_ids": "free_t9999999s_ret_150",
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
    )
    assert response.status_code == 422


def test_a_designed_burn_survives_into_the_comparison_a_later_request_builds():
    """An operator cannot approve what the workspace will not show them.

    A designed burn lives in the planner's session and nowhere else, so a later
    request building a fresh session would not know about it -- including the
    analysis call that feeds the comparison and the trajectory the operator
    inspects before approving. It is recovered from the stored validations,
    which were already being kept as evidence.
    """
    from backend.agent.llm import ScriptedProvider, text_reply, tool_call

    designed_burn = {
        "burn_t_s": 1500.0,
        "direction": "RETROGRADE",
        "delta_v_mps": 0.15,
    }

    def designing():
        return ScriptedProvider(
            [
                tool_call("design_maneuver", **designed_burn),
                text_reply("Recommend the designed burn."),
            ]
        )

    client = make_client(provider_factory=designing)
    case = new_case(client)
    case_id = case["case_id"]

    run = client.post(
        f"/cases/{case_id}/plan",
        json={"expected_scenario_version": 1, "expected_policy_version": 1},
    ).json()
    wait_for_run(client, run["run_id"])

    proposed = client.get(f"/cases/{case_id}").json()["proposal"]["candidate_id"]
    assert proposed.startswith("free_"), proposed

    analysis = client.post(
        f"/cases/{case_id}/analysis",
        json={"expected_scenario_version": 1, "expected_policy_version": 1},
    ).json()
    row = next(
        (o for o in analysis["options"] if o["candidate_id"] == proposed), None
    )
    assert row is not None, "the proposed burn is missing from the comparison"
    assert row["designed"] is True
    assert row["delta_v_mps"] == pytest.approx(designed_burn["delta_v_mps"])

    # And it can be drawn, which is what "inspect before approving" requires.
    variants = client.get(
        f"/cases/{case_id}/visualization",
        params={
            "candidate_ids": f"baseline,{proposed}",
            "expected_scenario_version": 1,
            "expected_policy_version": 1,
        },
    ).json()["variants"]
    assert proposed in {v["candidate_id"] for v in variants}


def test_a_record_exported_after_the_comparison_states_what_the_screen_shows():
    """The workspace says "Verified clear"; the record must not say otherwise.

    The numerical comparison verifies options with the same verifier the planner
    uses. Discarding those results meant a record exported from a case the
    operator had been looking at claimed nothing had been screened.
    """
    client = make_client()
    case = new_case(client)
    case_id = case["case_id"]

    before = client.get(f"/cases/{case_id}/export", params={"format": "cdm"}).text
    assert "No screening has been run" in before

    analysis = client.post(
        f"/cases/{case_id}/analysis",
        json={"expected_scenario_version": 1, "expected_policy_version": 1},
    ).json()
    assert analysis["recommended_id"], "the comparison verified something"

    after = client.get(f"/cases/{case_id}/export", params={"format": "cdm"}).text
    assert "No screening has been run" not in after
    assert "MISS_DISTANCE" in after
    assert "Screening result:" in after

    # And it still holds up when someone else recomputes it.
    verdict = client.post("/interop/verify-cdm", json={"text": after}).json()
    assert verdict["verdict"] == "AGREES", verdict["checks"]


def test_the_comparison_still_creates_nothing_that_could_be_approved():
    """Storing what it verified must not open an approval path."""
    client = make_client()
    case = new_case(client)
    case_id = case["case_id"]
    client.post(
        f"/cases/{case_id}/analysis",
        json={"expected_scenario_version": 1, "expected_policy_version": 1},
    )
    snapshot = client.get(f"/cases/{case_id}").json()
    assert snapshot["proposal"] is None
    assert snapshot["execution"] is None


def test_a_running_plan_reports_its_progress_over_http():
    """The spinner has something to say, and it comes from the run itself."""
    client = make_client()
    case = new_case(client)
    run = client.post(
        f"/cases/{case['case_id']}/plan",
        json={
            "expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"],
        },
    ).json()

    steps: list[tuple[int, str]] = []
    for _ in range(600):
        state = client.get(f"/runs/{run['run_id']}").json()
        entry = (state.get("steps_done", 0), state.get("step", ""))
        if entry[1] and entry not in steps:
            steps.append(entry)
        if state["status"] != "RUNNING":
            break
        time.sleep(0.02)

    assert state["status"] == "DONE", state
    assert steps, "the run never reported a step"
    assert steps == sorted(steps), "step numbers went backwards"
    assert all(summary.strip() for _, summary in steps), steps

    # A poller sees the latest step, not every one -- a fast run finishes
    # several between polls, which is fine for a progress readout. The complete
    # trace is the persisted one, and that must miss nothing.
    events = client.get(f"/cases/{case['case_id']}").json()["events"]
    summaries = [e["summary"] for e in events]
    assert any("Validated" in summary for summary in summaries), summaries
    assert steps[-1][0] <= len(events)


# --------------------------------------------------------------------------
# Case memory has to be written, not only read
# --------------------------------------------------------------------------


def test_a_finished_run_files_what_it_concluded():
    """The planner reads this table at the top of every run.

    Nothing was ever writing to it, so `relevant()` could only ever return
    nothing — the feature was inert rather than absent, which is why no test
    caught it. This asserts the round trip, not just the read.
    """
    from backend.agent.memory import CaseMemory

    memory = CaseMemory()
    client = make_client(memory=memory)
    case = new_case(client)
    run = run_plan(client, case)
    assert run["status"] == "DONE", run

    filed = memory.all_records()
    assert filed, "a completed run filed nothing to case memory"
    entry = filed[0]
    assert entry.case_id == case["case_id"]
    assert entry.scenario_family == case["scenario_id"]
    assert entry.outcome == run["result"]["status"]
    # The summary quotes a measured clearance, so it must name the option it measured.
    assert entry.candidate_id and entry.candidate_id in entry.summary


def test_a_later_case_on_the_same_scenario_sees_the_earlier_one():
    from backend.agent.memory import CaseMemory

    memory = CaseMemory()
    client = make_client(memory=memory)

    first = new_case(client)
    run_plan(client, first)

    second = new_case(client)
    hits = memory.relevant(scenario_family=second["scenario_id"], exclude_case_id=second["case_id"])
    assert hits, "the second case saw no prior case on the same scenario"
    assert first["case_id"] in {h.case_id for h in hits}
    # Memory suggests; it never applies. The new case starts on the base policy.
    assert second["policy_version"] == 1
    assert second["grid_revision"] == 1


def test_a_memory_failure_never_fails_a_completed_run():
    """A bookkeeping write is not allowed to turn a good run into a FAILED one."""
    from backend.agent.memory import CaseMemory

    class Breaks(CaseMemory):
        def record(self, *a, **k):
            raise RuntimeError("disk went away")

    client = make_client(memory=Breaks())
    case = new_case(client)
    run = run_plan(client, case)
    assert run["status"] == "DONE", run
    assert run["result"]["status"] == "PROPOSAL_READY"


def test_the_memory_hit_reaches_the_operator_trace():
    """The prior case has to be visible, not merely stored.

    The planner emits a `memory` event when retrieval returns hits, and the
    workspace renders every event's type and summary. Before a run filed
    anything there were never any hits, so that event could never fire and the
    trace never mentioned a prior case. This asserts the whole path: record,
    retrieve, event, persisted snapshot.
    """
    from backend.agent.memory import CaseMemory

    client = make_client(memory=CaseMemory())

    first = new_case(client)
    run_plan(client, first)

    second = new_case(client)
    run_plan(client, second)

    events = client.get(f"/cases/{second['case_id']}").json()["events"]
    memory_events = [e for e in events if e["event_type"] == "memory"]
    assert memory_events, "the second run's trace never mentioned the earlier case"
    assert first["case_id"] in memory_events[0]["summary"]
    assert memory_events[0]["details"]["memory_ids"]
