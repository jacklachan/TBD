"""Encounter detection: constructed minima, boundaries, burn epochs, grid adequacy.

Each expected value is constructed rather than asserted from a previous run.
A debris object is built so that, at a chosen instant, its relative position is
exactly a chosen offset and its relative velocity is perpendicular to that
offset -- which makes the range rate exactly zero there, so the encounter time
and miss distance are known independently of the detector under test.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.core.encounters import (
    BOUNDARY_BURN,
    BOUNDARY_HORIZON,
    BOUNDARY_INTERIOR,
    closest_encounter,
    find_encounters,
    min_separation_series,
)
from backend.core.kepler import EARTH_RADIUS_M, MU_M3_S2, propagate
from backend.core.trajectory import Trajectory, impulse_vector

HORIZON_S = 21600.0
SEMI_MAJOR_M = EARTH_RADIUS_M + 400_000.0
INCLINATION_RAD = np.radians(51.6)


def satellite() -> Trajectory:
    speed = np.sqrt(MU_M3_S2 / SEMI_MAJOR_M)
    r0 = np.array([SEMI_MAJOR_M, 0.0, 0.0])
    v0 = np.array(
        [0.0, speed * np.cos(INCLINATION_RAD), speed * np.sin(INCLINATION_RAD)]
    )
    return Trajectory.from_state(r0, v0)


def debris_passing_at(
    target: Trajectory, t_ca_s: float, miss_m: float, relative_speed_mps: float
) -> Trajectory:
    """Debris whose closest approach to ``target`` is ``miss_m`` at ``t_ca_s``.

    Built forward at the encounter and propagated backward to the epoch, then
    queried forward again by the detector -- so the round trip is part of what
    the test exercises.
    """
    r_t, v_t = target.states_at(np.array([t_ca_s]))
    r_t, v_t = r_t[0], v_t[0]

    # Offset direction: radial component orthogonalised against velocity.
    offset_dir = r_t / np.linalg.norm(r_t)
    offset_dir = offset_dir - (offset_dir @ v_t) / (v_t @ v_t) * v_t
    offset_dir = offset_dir / np.linalg.norm(offset_dir)

    # Relative velocity perpendicular to the offset makes the range rate zero.
    rel_dir = np.cross(offset_dir, v_t)
    rel_dir = rel_dir / np.linalg.norm(rel_dir)

    r_d = r_t + offset_dir * miss_m
    v_d = v_t + rel_dir * relative_speed_mps

    r_epoch, v_epoch = propagate(r_d, v_d, np.array([-t_ca_s]))
    return Trajectory.from_state(r_epoch[0], v_epoch[0])


# --------------------------------------------------------------------------
# Constructed interior minimum
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "t_ca,miss_m,rel_speed",
    [
        (16200.0, 120.0, 150.0),
        (8000.0, 2500.0, 400.0),
        (19800.0, 45.0, 90.0),
    ],
)
def test_recovers_constructed_encounter(t_ca, miss_m, rel_speed):
    sat = satellite()
    deb = debris_passing_at(sat, t_ca, miss_m, rel_speed)

    encounters = find_encounters(sat, deb, "DEB-1", HORIZON_S, step_s=5.0)
    closest = closest_encounter(encounters)
    assert closest is not None

    time_error = abs(closest.tca_s - t_ca)
    distance_error = abs(closest.min_separation_m - miss_m)
    print(
        f"\n[constructed t_ca={t_ca:.0f}s miss={miss_m:.0f}m] "
        f"time error {time_error:.3e} s, distance error {distance_error:.3e} m, "
        f"relative speed {closest.relative_speed_mps:.1f} m/s"
    )

    assert closest.boundary_kind == BOUNDARY_INTERIOR
    assert not closest.ambiguous_time
    assert time_error < 0.01
    assert distance_error < 1.0
    assert closest.relative_speed_mps == pytest.approx(rel_speed, rel=1e-3)


# --------------------------------------------------------------------------
# Grid adequacy on the supported family
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rel_speed", [90.0, 400.0, 1500.0])
def test_coarse_grid_agrees_with_dense_grid(rel_speed):
    """The 5 s search grid must not change the answer on this scenario family.

    This validates the sampling choice where it is used. It is not a general
    completeness proof and must not be described as one.
    """
    sat = satellite()
    deb = debris_passing_at(sat, 16200.0, 300.0, rel_speed)

    coarse = closest_encounter(find_encounters(sat, deb, "DEB-1", HORIZON_S, step_s=5.0))
    dense = closest_encounter(find_encounters(sat, deb, "DEB-1", HORIZON_S, step_s=0.5))
    assert coarse is not None and dense is not None

    print(
        f"\n[grid rel_speed={rel_speed:.0f}] coarse {coarse.min_separation_m:.6f} m "
        f"@ {coarse.tca_s:.6f} s vs dense {dense.min_separation_m:.6f} m "
        f"@ {dense.tca_s:.6f} s"
    )
    assert abs(coarse.min_separation_m - dense.min_separation_m) < 1.0
    assert abs(coarse.tca_s - dense.tca_s) < 0.1


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------


def test_minimum_at_the_horizon_edge_is_reported_as_a_boundary():
    sat = satellite()
    deb = debris_passing_at(sat, HORIZON_S, 500.0, 200.0)

    encounters = find_encounters(sat, deb, "DEB-1", HORIZON_S, step_s=5.0)
    closest = closest_encounter(encounters)
    assert closest is not None

    print(
        f"\n[horizon edge] {closest.min_separation_m:.3f} m at {closest.tca_s:.3f} s, "
        f"kind {closest.boundary_kind}"
    )
    assert closest.boundary_kind == BOUNDARY_HORIZON
    assert closest.tca_s == pytest.approx(HORIZON_S, abs=1e-6)
    assert closest.min_separation_m == pytest.approx(500.0, abs=1.0)


def test_minimum_at_a_burn_epoch_is_reported_as_a_burn_boundary():
    """Velocity is discontinuous at a burn, so the minimum can be a kink.

    Without partitioning the scan at the burn, the bracket around this point
    spans the discontinuity and refinement lands somewhere else.
    """
    sat = satellite()
    burn_t = 1800.0
    dv = impulse_vector(sat, burn_t, "PROGRADE", 0.20)
    burned = sat.apply_impulse(burn_t, dv)

    deb = debris_passing_at(burned, burn_t, 800.0, 250.0)
    encounters = find_encounters(burned, deb, "DEB-1", HORIZON_S, step_s=5.0)

    at_burn = [e for e in encounters if abs(e.tca_s - burn_t) < 1e-3]
    assert at_burn, f"no encounter found at the burn epoch; got {encounters}"

    print(
        f"\n[burn epoch] {at_burn[0].min_separation_m:.3f} m at "
        f"{at_burn[0].tca_s:.3f} s, kind {at_burn[0].boundary_kind}"
    )
    assert at_burn[0].boundary_kind == BOUNDARY_BURN
    assert at_burn[0].min_separation_m == pytest.approx(800.0, abs=1.0)


def test_burn_epoch_is_not_reported_twice():
    """The epoch is the right edge of one segment and the left edge of the next."""
    sat = satellite()
    burned = sat.apply_impulse(3600.0, impulse_vector(sat, 3600.0, "PROGRADE", 0.10))
    deb = debris_passing_at(sat, 12000.0, 400.0, 300.0)

    encounters = find_encounters(burned, deb, "DEB-1", HORIZON_S, step_s=5.0)
    times = sorted(e.tca_s for e in encounters)
    gaps = np.diff(times) if len(times) > 1 else np.array([np.inf])
    assert np.all(gaps > 1e-6), f"duplicate encounter times: {times}"


# --------------------------------------------------------------------------
# The behaviour the signature demo depends on
# --------------------------------------------------------------------------


def test_burn_can_create_an_encounter_that_the_baseline_does_not_have():
    """A manoeuvre that is safe against one object can be unsafe against another.

    This is the mechanism behind the secondary conflict. Here it is exercised
    directly on the detector, independently of scenario generation.
    """
    sat = satellite()
    burn_t = 1800.0
    burned = sat.apply_impulse(burn_t, impulse_vector(sat, burn_t, "PROGRADE", 0.20))

    secondary_t = 19800.0
    deb = debris_passing_at(burned, secondary_t, 300.0, 200.0)

    against_burned = closest_encounter(
        find_encounters(burned, deb, "DEB-2", HORIZON_S, step_s=5.0)
    )
    against_baseline = closest_encounter(
        find_encounters(sat, deb, "DEB-2", HORIZON_S, step_s=5.0)
    )
    assert against_burned is not None and against_baseline is not None

    print(
        f"\n[secondary] burned trajectory {against_burned.min_separation_m:.1f} m "
        f"@ {against_burned.tca_s:.1f} s; baseline "
        f"{against_baseline.min_separation_m:.1f} m "
        f"@ {against_baseline.tca_s:.1f} s"
    )

    assert against_burned.min_separation_m == pytest.approx(300.0, abs=1.0)
    # The burn is what creates the conflict; the unburned path is far clear.
    assert against_baseline.min_separation_m > 10.0 * against_burned.min_separation_m


# --------------------------------------------------------------------------
# Visualization series
# --------------------------------------------------------------------------


def test_min_to_any_envelope_matches_the_per_pair_series():
    sat = satellite()
    deb_1 = debris_passing_at(sat, 16200.0, 120.0, 150.0)
    deb_2 = debris_passing_at(sat, 19800.0, 900.0, 300.0)

    times = np.arange(0.0, HORIZON_S + 1.0, 60.0)
    pair, envelope = min_separation_series(
        sat, {"DEB-1": deb_1, "DEB-2": deb_2}, times
    )

    assert set(pair) == {"DEB-1", "DEB-2"}
    assert all(series.shape == times.shape for series in pair.values())
    assert np.allclose(envelope, np.minimum(pair["DEB-1"], pair["DEB-2"]))
    assert float(np.min(envelope)) < 5000.0
