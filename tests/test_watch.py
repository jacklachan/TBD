"""The autonomous watch, end to end, with scripted models and small stand-ins.

Proves the chain and its rules: every stage runs without operator input, a
reviewer that blocks or does not answer keeps a burn out of the approvable
queue, and only an operator's approval changes a decision.
"""

import time

from fastapi.testclient import TestClient

from backend.agent.llm import LLMError, ScriptedProvider, text_reply, tool_call
from backend.agent.tracker import pass_id
from backend.agent.watch import run_watch
from test_tracker import PASSES, SCREEN, fake_assess

ALLOW = '{"decision": "ALLOW", "reason_codes": ["OK"], "rationale": "Re-screen is clear."}'
BLOCK = '{"decision": "BLOCK", "reason_codes": ["MARGIN"], "rationale": "Too close."}'


def _full_assess(protected, debris, tca):
    result = fake_assess(protected, debris, tca)
    result.update({"comfortable_km": 1.25, "rescreen": {"hours_after_burn": 12.0, "fragments": 2664}})
    return result


def _planner():
    return ScriptedProvider([
        tool_call("assess_pass", pass_id=pass_id(PASSES[0])),
        tool_call("assess_pass", pass_id=pass_id(PASSES[2])),
        text_reply("IRIDIUM 170 needs a burn; IRIDIUM 117 is clear."),
    ])


def _watch(reviewer_text, **kwargs):
    return run_watch(
        _planner,
        (lambda: ScriptedProvider([text_reply(reviewer_text)])) if reviewer_text else None,
        SCREEN, PASSES, _full_assess, **kwargs,
    )


def test_the_chain_runs_every_stage_without_operator_input():
    result = _watch(ALLOW)
    stages = [entry["stage"] for entry in result["timeline"]]
    for stage in ("DETECT", "TRIAGE", "PLAN", "REVIEW", "COORDINATE", "DECIDE"):
        assert stage in stages
    real = {i["satellite"]: i for i in result["queue"] if i["source"] == "REAL"}
    assert real["IRIDIUM 170"]["status"] == "AWAITING_APPROVAL"
    assert real["IRIDIUM 170"]["reviewer"]["decision"] == "ALLOW"
    assert real["IRIDIUM 117"]["status"] == "NO_ACTION"
    assert real["IRIDIUM 170"]["coordination"]["needed"] is False


def test_a_blocking_reviewer_keeps_the_burn_out_of_the_approvable_queue():
    result = _watch(BLOCK, include_partner_case=False)
    item = next(i for i in result["queue"] if i["satellite"] == "IRIDIUM 170")
    assert item["status"] == "BLOCKED_BY_REVIEWER"


def test_no_reviewer_means_nothing_can_be_approved():
    result = _watch(None, include_partner_case=False)
    assert not any(i["status"] == "AWAITING_APPROVAL" for i in result["queue"])


def test_the_simulated_partner_case_is_labelled_and_coordinated():
    result = _watch(ALLOW)
    partner = next(i for i in result["queue"] if i["source"] == "SIMULATED")
    assert partner["coordination"]["needed"] is True
    assert partner["coordination"]["both_as_planned_m"] < 1000.0
    assert len(partner["coordination"]["movers"]) == 1


def test_approval_is_the_only_human_step_and_is_idempotent(monkeypatch):
    from backend import avoidance, tracking
    from backend.api import create_app
    from backend.store import Store

    monkeypatch.setattr(tracking, "cached_screen", lambda: SCREEN)
    monkeypatch.setattr(tracking, "all_conjunctions", lambda: PASSES)
    monkeypatch.setattr(avoidance, "cached_assess", _full_assess)
    client = TestClient(create_app(
        store=Store(":memory:"), provider_factory=_planner,
        reviewer_factory=lambda: ScriptedProvider([text_reply(ALLOW)]),
    ))
    run_id = client.post("/watch").json()["run_id"]
    deadline = time.monotonic() + 30
    while (run := client.get(f"/runs/{run_id}").json())["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert run["status"] == "DONE", run
    queue = run["result"]["queue"]
    waiting = next(i for i in queue if i["status"] == "AWAITING_APPROVAL" and i["source"] == "REAL")
    clear = next(i for i in queue if i["status"] == "NO_ACTION")

    first = client.post(f"/watch/{run_id}/approve", json={"item_id": waiting["item_id"]})
    again = client.post(f"/watch/{run_id}/approve", json={"item_id": waiting["item_id"]})
    assert first.status_code == 200 and first.json()["created"] is True
    assert again.json()["created"] is False and again.json()["item"]["status"] == "APPROVED"
    assert client.post(f"/watch/{run_id}/approve", json={"item_id": clear["item_id"]}).status_code == 409


def test_a_reviewer_transport_failure_blocks():
    def failing():
        return ScriptedProvider([LLMError("HTTP 429")])

    result = run_watch(_planner, failing, SCREEN, PASSES, _full_assess, include_partner_case=False)
    item = next(i for i in result["queue"] if i["satellite"] == "IRIDIUM 170")
    assert item["status"] == "BLOCKED_BY_REVIEWER"
    assert item["reviewer"]["decision"] == "UNAVAILABLE"


def test_a_windowed_bundle_replays_the_strike_at_one_second_steps():
    from backend.api import create_app
    from backend.store import Store

    client = TestClient(create_app(store=Store(":memory:")))
    case = client.post("/cases", json={"scenario_id": "collision"}).json()
    bundle = client.get(f"/cases/{case['case_id']}/visualization", params={
        "candidate_ids": "baseline", "expected_scenario_version": 1, "expected_policy_version": 1,
        "sample_step_s": 1, "window_start_s": 16200, "window_end_s": 16360,
    }).json()
    assert bundle["window"] == {"start_s": 16200.0, "end_s": 16360.0}
    assert bundle["t_s"][0] == 16200.0 and bundle["t_s"][-1] == 16360.0
    strike = min(bundle["variants"][0]["encounters"], key=lambda e: e["min_separation_m"])
    assert strike["min_separation_m"] < 25.0
    assert strike["tca_s"] in bundle["t_s"]
