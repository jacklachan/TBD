"""The browser can inspect real computed evidence without impersonating an agent."""

import pytest

from test_api import make_client, new_case


def stamp(case):
    return {"expected_scenario_version": case["scenario_version"], "expected_policy_version": case["policy_version"]}


def test_analysis_computes_the_secondary_veto_without_creating_an_ai_proposal():
    with make_client() as client:
        case = new_case(client)
        response = client.post(f"/cases/{case['case_id']}/analysis", json=stamp(case))
        assert response.status_code == 200
        result = response.json()
        assert result["mode"] == "NUMERICAL_ANALYSIS"
        assert result["candidate_count"] == 25
        assert result["recommended_id"] == "t30_ret_200"
        trap = next(o for o in result["options"] if o["candidate_id"] == "t30_ret_100")
        assert trap["primary_qualified"]
        assert trap["validation"]["status"] == "BLOCK"
        assert trap["validation"]["blocked_by"][0]["object_id"] == "DEB-2"
        current = client.get(f"/cases/{case['case_id']}").json()
        assert current["proposal"] is None
        assert current["runs"] == []


def test_manual_budget_changes_versions_and_recomputes_infeasibility():
    with make_client() as client:
        case = new_case(client)
        url = f"/cases/{case['case_id']}"
        changed = client.post(url + "/policy-manual", json={**stamp(case), "max_delta_v_mps": .1})
        assert changed.status_code == 200
        updated = changed.json()
        assert updated["policy_version"] == 2
        assert client.post(url + "/analysis", json=stamp(case)).status_code == 409
        analysis = client.post(url + "/analysis", json=stamp(updated)).json()
        assert analysis["recommended_id"] is None
        assert analysis["status"] == "NO_VERIFIED_OPTION"


@pytest.mark.parametrize("value", [-1, 1.01, "Infinity"])
def test_manual_budget_is_bounded(value):
    with make_client() as client:
        case = new_case(client)
        response = client.post(f"/cases/{case['case_id']}/policy-manual", json={**stamp(case), "max_delta_v_mps": value})
        assert response.status_code == 422
