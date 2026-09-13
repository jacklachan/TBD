"""The real-catalogue screen, run on the committed element sets.

The cross-check tolerances are what public element sets can support, not what
this run happened to produce: timing of a pass is well determined, the miss
distance moves by kilometres between element-set updates.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend import tracking
from backend.api import create_app
from backend.store import Store


@pytest.fixture(scope="module")
def result():
    return tracking.screen()


def test_the_whole_constellation_is_screened_against_every_fragment(result):
    provenance, objects = tracking.load_catalog()
    protected = sum(o.role == "PROTECTED" for o in objects)
    debris = sum(o.role == "DEBRIS" for o in objects)
    assert result["catalog"]["protected_count"] == protected >= 60
    assert result["catalog"]["debris_count"] == debris >= 2000
    assert result["pairs_screened"] == protected * debris


def test_reported_passes_are_inside_the_window_and_threshold(result):
    start = datetime.fromisoformat(result["window"]["start_utc"])
    end = datetime.fromisoformat(result["window"]["end_utc"])
    misses = [c["miss_km"] for c in result["conjunctions"]]
    assert misses == sorted(misses)
    for c in result["conjunctions"]:
        assert c["miss_km"] <= result["report_threshold_km"]
        assert start <= datetime.fromisoformat(c["tca_utc"]) <= end


def test_published_socrates_passes_are_found_independently(result):
    checks = [c for c in result["cross_check"] if c["status"] == "RECOMPUTED"]
    assert len(checks) >= 2
    for c in checks:
        assert abs(c["tca_difference_s"]) < 5.0
        assert c["our_relative_speed_kms"] == pytest.approx(c["published_relative_speed_kms"], abs=0.05)
        assert c["our_miss_km"] < 5.0


def test_a_published_pass_is_also_in_our_own_ranking(result):
    published = {
        (c["object_1"]["norad_id"], c["object_2"]["norad_id"]) for c in result["cross_check"]
    }
    ours = {(c["protected"]["norad_id"], c["debris"]["norad_id"]) for c in result["conjunctions"]}
    assert published & ours


def test_the_tracking_endpoint_is_behind_the_access_guard():
    client = TestClient(
        create_app(store=Store(":memory:"), require_remote_token=True),
        client=("198.51.100.10", 4567),
    )
    assert client.get("/tracking/screen").status_code == 503
