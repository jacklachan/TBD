"""Avoidance options for real passes from the committed catalogue.

Checks the physics against itself rather than against a stored answer: the
encounter-plane estimate must agree with the full re-screen of the same burn,
and a pass already clear must not be sent a burn.
"""

import pytest
from fastapi.testclient import TestClient

from backend import avoidance, tracking
from backend.api import create_app
from backend.store import Store


@pytest.fixture(scope="module")
def screen():
    return tracking.cached_screen()


def test_cw_displacement_matches_the_closed_form():
    n = 0.00107
    radial, along = avoidance._cw(0.001, [3.1416 / n], n)
    assert radial[0] == pytest.approx(4 * 0.001 / n, rel=1e-4)
    assert along[0] == pytest.approx(-3 * 0.001 * 3.1416 / n, rel=1e-3)


def test_the_closest_real_pass_gets_a_burn_that_survives_the_rescreen(screen):
    top = screen["conjunctions"][0]
    result = avoidance.assess(top["protected"]["norad_id"], top["debris"]["norad_id"], top["tca_utc"])
    assert result["conjunction"]["miss_km"] < result["comfortable_km"]
    chosen = next(o for o in result["options"] if o["option_id"] == result["recommended_option_id"])
    assert chosen["direction"] is not None and chosen["verdict"] == "PASS"
    # The straight-line estimate and the full re-screen describe the same pass.
    assert chosen["rescreen_assessed_miss_km"] == pytest.approx(chosen["predicted_miss_km"], abs=0.05)
    assert chosen["rescreen_closest_km"] is None or chosen["rescreen_closest_km"] >= result["comfortable_km"]


def test_a_pass_already_clear_is_not_sent_a_burn(screen):
    clear = next(c for c in screen["cross_check"] if c["status"] == "RECOMPUTED" and c["our_miss_km"] >= avoidance.COMFORTABLE_KM)
    result = avoidance.assess(clear["object_1"]["norad_id"], clear["object_2"]["norad_id"], clear["our_tca_utc"])
    assert result["recommended_option_id"] == "no_burn"


def test_assess_rejects_an_object_that_is_not_protected():
    client = TestClient(create_app(store=Store(":memory:")))
    response = client.post("/tracking/assess", json={
        "protected_norad_id": 30232, "debris_norad_id": 43930, "tca_utc": "2026-09-16T02:02:50+00:00",
    })
    assert response.status_code == 422
