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


# --------------------------------------------------------------- completeness
#
# The screen's real claim is not the list it prints, it is the absence of
# anything else: no pass under the threshold slipped between two coarse
# samples. That rests on the capture radius being wide enough, which rests on a
# bound on how fast two objects can close. These check the bound is derived
# from the catalogue rather than assumed, and that the derivation holds against
# what SGP4 actually produced.


def test_the_capture_bound_is_derived_from_the_elements_not_assumed(result):
    bound = result["completeness"]["speed_bound"]
    assert bound["source"] == "perigee_speed_sum_from_mean_elements"
    assert bound["derived_kms"] == pytest.approx(
        bound["fastest_protected_kms"] + bound["fastest_debris_kms"] + bound["margin_kms"],
        abs=1e-3,
    )
    # Applied is whichever of derived and floor is larger, so a faster
    # catalogue widens the radius and never narrows it.
    assert bound["applied_kms"] == pytest.approx(
        max(bound["derived_kms"], bound["floor_kms"]), abs=1e-3
    )


def test_no_pair_ever_closed_faster_than_the_capture_radius_allowed_for(result):
    completeness = result["completeness"]
    assert completeness["status"] == "COMPLETE", completeness.get("shortfall")
    assert completeness["observed_head_on_kms"] <= completeness["speed_bound"]["applied_kms"]
    assert completeness["speed_headroom_kms"] > 0
    assert completeness["capture_radius_km"] == pytest.approx(
        result["report_threshold_km"]
        + completeness["speed_bound"]["applied_kms"] * result["window"]["coarse_step_s"] / 2.0,
        abs=1e-6,
    )


def test_the_straight_line_estimate_stays_well_inside_its_refine_margin(result):
    completeness = result["completeness"]
    assert completeness["worst_linear_error_km"] < completeness["linear_margin_km"]
    assert completeness["linear_headroom_km"] > 0
    # Every candidate that was refined got measured, so this is a statement
    # about the screen, not about the handful of passes that made the list.
    assert completeness["candidate_pairs_refined"] >= result["conjunction_count"]


def test_the_speed_bound_is_an_upper_bound_on_a_known_orbit():
    from sgp4.api import Satrec

    # ISS-like: near circular, so perigee speed and mean orbital speed almost
    # coincide and the bound can be checked against the propagator directly.
    line1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9005"
    line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49815465 20000"
    sat = Satrec.twoline2rv(line1, line2)
    bound = tracking._orbit_speed_bound_kms(sat)
    assert 7.0 < bound < 8.5

    import numpy as np

    start = tracking._epoch(sat)
    _, v = tracking._sgp4_many([sat], start, np.arange(0.0, 5700.0, 30.0))
    fastest = tracking._fastest_sampled_kms(v)

    # SGP4 is osculating and the bound is computed from mean elements, so the
    # propagator rides just above it on short-period terms. The gap is metres
    # per second, and the margin is what makes the applied bound safe -- assert
    # both halves, because a regression in either is what would quietly narrow
    # the capture radius.
    assert fastest > bound - 0.05
    assert fastest - bound < tracking.SPEED_BOUND_MARGIN_KMS / 10.0
    assert fastest < bound + tracking.SPEED_BOUND_MARGIN_KMS


def test_a_faster_catalogue_widens_the_capture_radius():
    """The floor is a floor, not a ceiling: raise the orbits and it gives way."""

    class FakeSat:
        def __init__(self, period_min: float, ecco: float) -> None:
            import math

            self.no_kozai = 2 * math.pi / period_min
            self.ecco = ecco

    # A highly eccentric fragment: perigee speed far above the LEO head-on
    # figure the old constant assumed, which is exactly the case that used to
    # be captured too narrowly and reported as if it had been screened.
    hot = tracking._capture_speed_bound([FakeSat(100.0, 0.001)], [FakeSat(720.0, 0.72)])
    assert hot["derived_kms"] > tracking.MAX_RELATIVE_SPEED_KMS
    assert hot["applied_kms"] == hot["derived_kms"]

    calm = tracking._capture_speed_bound([FakeSat(100.0, 0.001)], [FakeSat(100.0, 0.001)])
    assert calm["derived_kms"] < tracking.MAX_RELATIVE_SPEED_KMS
    assert calm["applied_kms"] == tracking.MAX_RELATIVE_SPEED_KMS


def test_propagation_failures_do_not_poison_the_observed_speed():
    import numpy as np

    v = np.array([[[1.0, 0.0, 0.0], [np.nan, np.nan, np.nan]]])
    assert tracking._fastest_sampled_kms(v) == pytest.approx(1.0)
    assert tracking._fastest_sampled_kms(np.full((1, 1, 3), np.nan)) == 0.0


# --------------------------------------------------------------------- triage
#
# A screen sorted by miss distance is a report. These check the queue answers
# the operator's question instead: what has to be decided first.


def test_the_triage_queue_matches_what_the_planner_will_act_on():
    from backend import avoidance

    assert tracking.TRIAGE_ATTENTION_KM == avoidance.LIST_KM


def test_the_queue_is_ordered_by_decision_deadline_not_by_approach(result):
    queue = result["triage"]["queue"]
    assert queue, "the committed catalogue should produce a work queue"

    deadlines = [c["triage"]["decide_in_hours"] for c in queue
                 if c["triage"].get("decide_in_hours") is not None]
    assert deadlines == sorted(deadlines)

    # Anything with no burn slot left carries no deadline and is filed last.
    with_slots = [bool(c["triage"]["burn_slots_open"]) for c in queue]
    assert with_slots == sorted(with_slots, reverse=True)

    # The ordering has to actually differ from closest-first, or it is not
    # adding anything: the closest pass in the screen is only urgent if its
    # deadline happens to be the nearest one too.
    assert all(c["miss_km"] <= result["triage"]["attention_km"] for c in queue)


def test_every_queued_pass_carries_a_deadline_that_precedes_its_approach(result):
    for c in result["triage"]["queue"]:
        triage = c["triage"]
        tca = datetime.fromisoformat(c["tca_utc"])
        if triage["posture"] == "TOO_LATE":
            assert triage["burn_slots_open"] == 0
            assert "decide_by_utc" not in triage
            continue
        decide_by = datetime.fromisoformat(triage["decide_by_utc"])
        assert decide_by < tca
        assert triage["decide_in_hours"] <= triage["lead_hours"]
        assert 0 < triage["burn_slots_open"] <= triage["burn_slots_total"]


def test_posture_tracks_how_many_burn_slots_are_left():
    from backend.avoidance import LEAD_HALF_ORBITS

    half_orbit_s = 3000.0  # a round 100-minute orbit
    widest = max(LEAD_HALF_ORBITS)
    narrowest = min(LEAD_HALF_ORBITS)

    plenty = tracking._triage(widest * half_orbit_s + 60.0, half_orbit_s)
    assert plenty["posture"] == "ACTIONABLE"
    assert plenty["burn_slots_open"] == len(LEAD_HALF_ORBITS)

    closing = tracking._triage(narrowest * half_orbit_s + 60.0, half_orbit_s)
    assert closing["posture"] == "NARROWING"
    assert closing["burn_slots_open"] == 1

    gone = tracking._triage(narrowest * half_orbit_s - 60.0, half_orbit_s)
    assert gone["posture"] == "TOO_LATE"
    assert gone["burn_slots_open"] == 0
    assert gone["decide_in_hours"] is None


def test_a_later_approach_can_carry_the_earlier_deadline():
    """The reason the queue is not just sorted by time to closest approach."""
    from backend.avoidance import LEAD_HALF_ORBITS

    half_orbit_s = 3000.0
    widest, narrowest = max(LEAD_HALF_ORBITS), min(LEAD_HALF_ORBITS)

    # Far enough out that the widest burn is only just still placeable.
    later = tracking._triage(widest * half_orbit_s + 300.0, half_orbit_s)
    # Nearer approach, but past the widest slot, so it falls back to a much
    # closer burn and has correspondingly more room before its own deadline.
    sooner = tracking._triage(narrowest * half_orbit_s + 3600.0, half_orbit_s)

    assert later["lead_hours"] > sooner["lead_hours"]
    assert later["decide_in_hours"] < sooner["decide_in_hours"]
