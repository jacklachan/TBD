"""Local adversarial API checks. Never contact a live model or external target."""

from dataclasses import replace
import threading

import pytest
from fastapi.testclient import TestClient

from backend.agent.llm import ScriptedProvider, text_reply
from backend.agent.tools import CaseSession, propose_policy_change
from backend.api import create_app
from backend.planning.policy import Policy
from backend.store import Store, StoreError
from test_api import ALLOW, RESCUE, approve, investigation, make_client, new_case, run_plan


def versions(case):
    return {"expected_scenario_version": case["scenario_version"],
            "expected_policy_version": case["policy_version"]}


@pytest.mark.parametrize("step", ["0.000000001", "nan", "inf"])
def test_visualization_rejects_unbounded_sampling_before_allocation(monkeypatch, step):
    client = make_client()
    case = new_case(client)
    # Do not allocate the enormous grid an attacker is asking for.
    called = []
    monkeypatch.setattr("backend.api.build_bundle", lambda **kw: called.append(kw) or {})
    result = client.get(f"/cases/{case['case_id']}/visualization", params={
        "candidate_ids": "baseline", "sample_step_s": step, **versions(case)})
    assert result.status_code == 422
    assert not called


def test_new_idempotency_key_cannot_execute_the_same_proposal_twice():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    first = approve(client, case["case_id"], snapshot, key="first-click")
    second = approve(client, case["case_id"], snapshot, key="retried-with-new-key")
    assert first.status_code == second.status_code == 200
    assert second.json()["created"] is False
    assert first.json()["execution"]["execution_id"] == second.json()["execution"]["execution_id"]


def test_transaction_rejects_proposal_after_policy_changes():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    state = client.app.state.desk
    proposal = state.store.latest_proposal(case["case_id"])
    state.store.update_policy(case["case_id"], Policy(policy_version=2, max_delta_v_mps=0.1))
    # Simulates the policy changing after endpoint checks and before the write.
    with pytest.raises(StoreError):
        state.store.record_execution(case["case_id"], proposal["proposal_id"], RESCUE, "racing")
    assert state.store.execution_for_case(case["case_id"]) is None


def test_stale_diff_cannot_overwrite_a_new_policy():
    client = make_client()
    case = new_case(client)
    state = client.app.state.desk
    state.store.update_policy(case["case_id"], Policy(policy_version=2, max_delta_v_mps=0.1))
    state.store.set_pending_diff(case["case_id"], {
        "diff_id": "late-v1", "base_policy_version": 1, "status": "READY",
        "after": {"max_delta_v_mps": 0.2, "min_separation_m": 1000, "blocked_windows": []}})
    result = client.post(f"/cases/{case['case_id']}/policy-confirm", json={
        "diff_id": "late-v1", "expected_scenario_version": 1, "expected_policy_version": 2})
    assert result.status_code == 409
    assert state.store.get_case(case["case_id"]).policy.max_delta_v_mps == 0.1


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_policy_output_never_becomes_a_ready_diff(value):
    client = make_client()
    case = new_case(client)
    row = client.app.state.desk.store.get_case(case["case_id"])
    session = CaseSession.from_document(row.document, case_id=row.case_id)
    result = propose_policy_change(session, max_delta_v_mps=value)
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert session.pending_diff.after.max_delta_v_mps == 0.2


def test_configured_access_token_protects_api_and_keeps_health_public(monkeypatch):
    monkeypatch.setenv("DESK_ACCESS_TOKEN", "review-only-test-token")
    with TestClient(create_app(store=Store(":memory:"))) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/cases", json={"scenario_id": "primary"}).status_code == 401
        assert client.post("/cases", json={"scenario_id": "primary"},
                           headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.post("/cases", json={"scenario_id": "primary"},
                           headers={"Authorization": "Bearer review-only-test-token"}).status_code == 201


def test_untrusted_browser_origin_is_rejected_on_mutation():
    client = make_client()
    response = client.post("/cases", json={"scenario_id": "primary"},
                           headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403


def test_oversized_plan_instruction_is_rejected_before_spending_model_quota():
    client = make_client()
    case = new_case(client)
    response = client.post(f"/cases/{case['case_id']}/plan", json={
        **versions(case), "instruction": "x" * 2001})
    assert response.status_code == 422
    assert client.app.state.desk.runs_for(case["case_id"]) == []


def test_duplicate_active_plan_is_not_queued():
    entered, release = threading.Event(), threading.Event()
    class PausedProvider:
        name = "test:paused"
        def __init__(self):
            self.delegate = investigation()
        def call(self, *args, **kwargs):
            entered.set()
            release.wait(10)
            return self.delegate.call(*args, **kwargs)
    client = TestClient(create_app(store=Store(":memory:"), provider_factory=PausedProvider,
        reviewer_factory=lambda: ScriptedProvider([text_reply(ALLOW)])))
    case = new_case(client)
    first = client.post(f"/cases/{case['case_id']}/plan", json=versions(case))
    try:
        assert first.status_code == 202
        assert entered.wait(5)
        second = client.post(f"/cases/{case['case_id']}/plan", json=versions(case))
        assert second.status_code == 409
    finally:
        release.set()


def test_approval_rejects_pass_evidence_for_a_different_candidate():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    state = client.app.state.desk
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    proposal = snapshot["proposal"]
    validation = state.store.get_validation(proposal["validation_id"])
    state.store.save_validation(case["case_id"], replace(validation, candidate_id="baseline"))
    assert approve(client, case["case_id"], snapshot).status_code == 409
    assert state.store.execution_for_case(case["case_id"]) is None


def test_public_request_cannot_bypass_access_setup_with_a_localhost_host_header():
    client = TestClient(create_app(store=Store(":memory:"), require_remote_token=True),
                        client=("198.51.100.10", 4567))
    response = client.post("/cases", json={"scenario_id": "primary"}, headers={"host": "localhost"})
    assert response.status_code == 503


def test_chunked_body_is_bounded_without_trusting_content_length():
    client = make_client()
    response = client.post("/cases", content=iter([b" " * 9000, b" " * 9000]),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_a_completed_simulation_requires_reset_before_planning_again():
    client = make_client()
    case = new_case(client)
    run_plan(client, case)
    snapshot = client.get(f"/cases/{case['case_id']}").json()
    assert approve(client, case["case_id"], snapshot).status_code == 200
    response = client.post(f"/cases/{case['case_id']}/plan", json=versions(case))
    assert response.status_code == 409


def test_case_creation_is_bounded(monkeypatch):
    monkeypatch.setattr("backend.api.MAX_CASES", 2, raising=False)
    client = make_client()
    new_case(client)
    new_case(client)
    assert client.post("/cases", json={"scenario_id": "primary"}).status_code == 429


def test_every_endpoint_that_costs_something_is_behind_the_guard():
    """The guard's prefix list is the whole boundary, so omissions are silent.

    An endpoint added outside it is unauthenticated, unbounded and cross-origin
    by omission rather than by decision. This enumerates the routes that cost
    case storage, model quota or the CPU of a propagation and asserts each one
    is covered, so adding the next one without listing it fails here.
    """
    from backend.security import PROTECTED_PREFIXES

    costly = [
        "/cases",
        "/runs/run_x",
        "/context/socrates",
        "/ingest/tle",
        "/interop/verify-cdm",
    ]
    for path in costly:
        assert any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in PROTECTED_PREFIXES
        ), f"{path} is not behind the guard"

    # /health stays public so a deployment can be checked without a token.
    assert not any(
        "/health" == prefix or "/health".startswith(prefix + "/")
        for prefix in PROTECTED_PREFIXES
    )


def test_an_untrusted_origin_cannot_spend_cpu_on_the_new_endpoints():
    client = make_client()
    for path, payload in (
        ("/ingest/tle", {"text": "irrelevant"}),
        ("/interop/verify-cdm", {"text": "irrelevant"}),
    ):
        response = client.post(
            path, json=payload, headers={"Origin": "https://untrusted.example"}
        )
        assert response.status_code == 403, path


def test_several_viewers_opening_the_page_at_once_are_not_refused():
    """The comparison is the first thing the workspace asks for.

    It makes no model calls, so rationing it against the paid model quota turned
    a handful of people opening the link together into a handful of people
    seeing a capacity error. Refusing a model call under load is honest;
    refusing arithmetic is not.
    """
    import concurrent.futures as futures

    client = make_client()
    cases = [new_case(client) for _ in range(8)]

    def compare(case):
        return client.post(
            f"/cases/{case['case_id']}/analysis", json=versions(case)
        ).status_code

    with futures.ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(compare, cases))

    assert codes == [200] * len(cases), codes


def test_the_model_quota_is_still_rationed_separately():
    """Separating CPU from quota must not have widened the quota."""
    client = make_client()
    state = client.app.state.desk
    assert state.compute_slots is not state.model_slots
    # Exhaust the model quota and confirm a plan is refused rather than queued.
    acquired = []
    while state.model_slots.acquire(blocking=False):
        acquired.append(True)
    try:
        case = new_case(client)
        response = client.post(f"/cases/{case['case_id']}/plan", json=versions(case))
        assert response.status_code == 429
        assert response.json()["detail"]["error"] == "CAPACITY"
        # The comparison is unaffected by the model being busy.
        assert (
            client.post(
                f"/cases/{case['case_id']}/analysis", json=versions(case)
            ).status_code
            == 200
        )
    finally:
        for _ in acquired:
            state.model_slots.release()
