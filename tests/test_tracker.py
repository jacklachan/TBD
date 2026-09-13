"""The triage agent's loop, bounds and evidence rules, with a scripted model.

A scripted pass proves the loop is correct, not that any model triages well.
The screen and the assessments are small stand-ins so these run in
milliseconds; the real ones are covered by test_tracking and test_avoidance.
"""

import time

import pytest
from fastapi.testclient import TestClient

from backend.agent.llm import LLMResponse, ScriptedProvider, ToolCall, text_reply, tool_call
from backend.agent.tracker import TriageLimits, pass_id, triage


def _pass(sat, norad, debris, miss, tca="2026-09-16T02:02:50.433+00:00"):
    return {
        "protected": {"norad_id": norad, "name": sat},
        "debris": {"norad_id": debris, "name": "FENGYUN 1C DEB", "event": "Fengyun-1C (2007 ASAT test)"},
        "tca_utc": tca, "miss_km": miss, "relative_speed_kms": 14.879,
        "element_age_days": {"protected": 3.9, "debris": 4.0},
    }


PASSES = [
    _pass("IRIDIUM 170", 43930, 30232, 0.105),
    _pass("IRIDIUM 131", 43571, 36273, 0.453, "2026-09-13T23:44:40.038+00:00"),
    _pass("IRIDIUM 117", 42808, 31024, 1.496, "2026-09-16T02:53:35.920+00:00"),
]
SCREEN = {
    "window": {"start_utc": "2026-09-13T01:20:00+00:00", "end_utc": "2026-09-16T13:20:00+00:00", "hours": 84.0, "coarse_step_s": 60.0},
    "catalog": {"protected_count": 80, "debris_count": 2664},
    "conjunction_count": 3, "report_threshold_km": 10.0,
    "by_event": {"Fengyun-1C (2007 ASAT test)": 3},
    "cross_check": [],
}


def fake_assess(protected, debris, tca):
    miss = next(p["miss_km"] for p in PASSES if p["protected"]["norad_id"] == protected)
    burn = miss < 1.25
    chosen = {
        "option_id": "l342_ret_250" if burn else "no_burn", "lead_minutes": 342 if burn else 0,
        "direction": "RETROGRADE" if burn else None, "delta_v_mps": 0.25 if burn else 0.0,
        "predicted_miss_km": 2.492 if burn else miss, "rescreen_closest_km": 2.487 if burn else miss,
        "verdict": "PASS",
    }
    return {"conjunction": {"miss_km": miss}, "options": [chosen], "recommended_option_id": chosen["option_id"],
            "option_count": 25, "rescreen": {"hours_after_burn": 12.0}}


def run(provider, **kwargs):
    return triage(provider, SCREEN, PASSES, fake_assess, **kwargs)


def test_passes_below_the_margin_are_assessed_and_triaged_from_tool_results():
    first, second = pass_id(PASSES[0]), pass_id(PASSES[1])
    result = run(ScriptedProvider([
        tool_call("assess_pass", pass_id=first),
        tool_call("assess_pass", pass_id=second),
        text_reply(f"IRIDIUM 170 pass {first} needs a burn: 0.25 m/s slow down, estimated 2.492 km."),
    ]))
    assert result["status"] == "BRIEF_READY"
    assert [i["status"] for i in result["triage"]] == ["NEEDS_BURN", "NEEDS_BURN"]
    assert result["triage"][0]["recommendation"] == "0.25 m/s slow down, 342 min before"
    assert result["flagged_numbers"] == []


def test_a_pass_already_clear_is_triaged_clear():
    clear = pass_id(PASSES[2])
    result = run(ScriptedProvider([tool_call("assess_pass", pass_id=clear), text_reply("Nothing to do.")]))
    assert result["triage"][0]["status"] == "CLEAR"


def test_an_invented_figure_in_the_brief_is_flagged():
    result = run(ScriptedProvider([text_reply("The worst pass is 37.5 m away.")]))
    assert result["flagged_numbers"] == [37.5]


def test_an_unknown_pass_is_an_error_the_model_can_recover_from():
    result = run(ScriptedProvider([
        tool_call("assess_pass", pass_id="P1_2_20260101T0000"),
        tool_call("assess_pass", pass_id=pass_id(PASSES[0])),
        text_reply("Done."),
    ]))
    assert any(e["event_type"] == "tool_error" for e in result["events"])
    assert result["assessments"] == 1


def test_the_assessment_limit_is_enforced():
    ids = [pass_id(p) for p in PASSES]
    result = run(ScriptedProvider([tool_call("assess_pass", pass_id=i) for i in ids] + [text_reply("Done.")]),
                 limits=TriageLimits(max_assessments=2))
    assert result["assessments"] == 2


def test_several_calls_in_one_turn_are_all_answered():
    ids = [pass_id(p) for p in PASSES[:2]]
    provider = ScriptedProvider([
        LLMResponse(tool_calls=tuple(ToolCall(name="assess_pass", arguments={"pass_id": i}, call_id=f"c{n}")
                                     for n, i in enumerate(ids))),
        text_reply("Two passes need burns."),
    ])
    result = run(provider)
    assert result["assessments"] == 2
    assert [m.call_id for m in provider.calls[1]["messages"][2:4]] == ["c0", "c1"]


def test_a_provider_failure_ends_the_run_unresolved():
    from backend.agent.llm import LLMError
    result = run(ScriptedProvider([LLMError("HTTP 429")]))
    assert result["status"] == "UNRESOLVED" and result["unresolved_reason"] == "PROVIDER_ERROR"


def test_the_endpoint_runs_the_agent_in_the_background(monkeypatch):
    from backend import avoidance, tracking
    from backend.api import create_app
    from backend.store import Store

    monkeypatch.setattr(tracking, "cached_screen", lambda: SCREEN)
    monkeypatch.setattr(tracking, "all_conjunctions", lambda: PASSES)
    monkeypatch.setattr(avoidance, "cached_assess", fake_assess)
    provider = lambda: ScriptedProvider([tool_call("assess_pass", pass_id=pass_id(PASSES[0])), text_reply("One burn.")])
    client = TestClient(create_app(store=Store(":memory:"), provider_factory=provider))
    run_id = client.post("/tracking/agent").json()["run_id"]
    deadline = time.monotonic() + 15
    while (run := client.get(f"/runs/{run_id}").json())["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert run["status"] == "DONE", run
    assert run["result"]["triage"][0]["status"] == "NEEDS_BURN"
