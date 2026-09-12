"""Regressions found while continuing the September 12 audit handoff.

Scripted models and a controlled clock: these prove bookkeeping, not live latency.
"""
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent.llm import GeminiProvider, ScriptedProvider, text_reply, tool_call
from backend.agent.planner import plan_case
from backend.agent.tools import CaseSession, PHASE_PLANNING, dispatch
from backend.agent.memory import CaseMemory
from backend.api import _record_memory
from backend.store import Store


@pytest.fixture
def session():
    path = Path(__file__).resolve().parents[1] / "scenarios/primary.json"
    return CaseSession.from_document(json.loads(path.read_text()), case_id="case_audit")


def test_a_partial_investigation_does_not_claim_no_option(session):
    outcome = plan_case(ScriptedProvider([
        tool_call("validate_proposal", candidate_id="t30_ret_100"),
        text_reply("No maneuver is possible."),
    ]), session)
    assert outcome.status == "UNRESOLVED"
    assert outcome.unresolved_reason == "NO_CONCLUSION"
    assert not any(e.event_type == "no_option" for e in outcome.events)


def test_a_fully_screened_grid_can_report_no_option(session):
    from dataclasses import replace
    session.policy = replace(session.policy, max_delta_v_mps=0.0)
    outcome = plan_case(ScriptedProvider([text_reply("No option in this grid.")]), session)
    assert outcome.status == "NO_APPROVABLE_OPTION"
    assert outcome.proposal is None


def test_elapsed_time_includes_the_final_safety_review(session, monkeypatch):
    # A previously cached passing validation takes the non-overlapped review path.
    dispatch(session, "validate_proposal", {"candidate_id": "t30_ret_200"}, PHASE_PLANNING)
    clock = [100.0]
    monkeypatch.setattr("backend.agent.planner.time.perf_counter", lambda: clock[0])

    class Reviewer:
        name = "scripted-reviewer"

        def call(self, *args, **kwargs):
            clock[0] += 7.0
            return text_reply('{"decision":"ALLOW","reason_codes":["OK"],"rationale":"Evidence passes."}')

    outcome = plan_case(
        ScriptedProvider([text_reply("Recommend the verified alternative.")]),
        session, reviewer_provider=Reviewer(), prefetch_context=False,
    )
    assert outcome.proposal.reviewer_verdict.decision == "ALLOW"
    assert outcome.elapsed_s == pytest.approx(7.0)


def test_provider_latency_includes_failed_attempt_and_backoff(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("backend.agent.llm.time.perf_counter", lambda: clock[0])
    monkeypatch.setattr("backend.agent.llm.time.sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    replies = [429, 200]

    def post(*args, **kwargs):
        clock[0] += 2.0
        return SimpleNamespace(
            status_code=replies.pop(0), headers={"Retry-After": "0.75"},
            text="busy", elapsed=timedelta(milliseconds=20),
            json=lambda: {"candidates": [{"content": {"parts": [{"text": "ready"}]}}]},
        )

    monkeypatch.setattr("backend.agent.llm.requests.post", post)
    response = GeminiProvider(api_key="unit-test-only").call("", [], [])
    assert response.latency_ms == pytest.approx(4750.0)


def test_memory_does_not_invent_a_widened_search_or_binding_constraint(session):
    from dataclasses import replace
    session.policy = replace(session.policy, max_delta_v_mps=0.0)
    outcome = plan_case(ScriptedProvider([text_reply("No grid option qualifies.")]), session)
    store = Store()
    row = store.create_case(session.document, session.policy)
    memory = CaseMemory()
    _record_memory(SimpleNamespace(memory=memory), row, session, outcome)
    record = memory.all_records()[0]
    assert "Widening" not in record.detail["suggestion"]
    assert "binding constraint" not in record.detail["suggestion"]
    assert "evaluated grid" in record.summary


@pytest.mark.parametrize("scenario,expected", [("primary", "UNRESOLVED"), ("no_feasible", "NO_APPROVABLE_OPTION")])
def test_grid_completion_cannot_mint_a_proposal(scenario, expected):
    from fastapi.testclient import TestClient
    from backend.api import create_app
    from backend.agent.planner import PlannerLimits
    import time
    provider = lambda: ScriptedProvider([
        tool_call("validate_proposal", candidate_id="t30_ret_100"),
        text_reply("I have reached the validation limit."),
    ])
    with TestClient(create_app(store=Store(), provider_factory=provider,
                              limits=PlannerLimits(max_validations=1))) as client:
        case = client.post("/cases", json={"scenario_id": "primary"}).json()
        if scenario == "no_feasible":
            case = client.post(f"/cases/{case['case_id']}/policy-manual", json={
                "expected_scenario_version": 1, "expected_policy_version": 1,
                "max_delta_v_mps": 0.1,
            }).json()
        run_id = client.post(f"/cases/{case['case_id']}/plan", json={
            "expected_scenario_version": case["scenario_version"], "expected_policy_version": case["policy_version"],
        }).json()["run_id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = client.get(f"/runs/{run_id}").json()
            if run["status"] != "RUNNING":
                break
            time.sleep(.02)
        assert run["status"] == "DONE", run
        assert run["result"]["status"] == expected
        snapshot = client.get(f"/cases/{case['case_id']}").json()
        assert snapshot["proposal"] is None
        assert snapshot["execution"] is None
        audits = [e for e in snapshot["events"] if e["event_type"] == "grid_audit"]
        assert len(audits) == 1
        assert audits[0]["details"]["model_outcome"] == "UNRESOLVED"
