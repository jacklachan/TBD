"""Gate 1 -- the four numerical checks from Handoff/handoffs/A_PHYSICS.md.

These are acceptance criteria, not a prediction. The propagator is analytic in
formulation and floating point in practice, so each test reports the observed
error rather than only asserting a bound.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from backend.core.kepler import (
    EARTH_RADIUS_M,
    MU_M3_S2,
    PropagationError,
    orbital_period_s,
    propagate,
    specific_angular_momentum,
    specific_energy,
)
from backend.core.trajectory import Trajectory, impulse_vector

# Supported family: bound, near-circular LEO.
ALTITUDE_M = 400_000.0
SEMI_MAJOR_M = EARTH_RADIUS_M + ALTITUDE_M
INCLINATION_RAD = np.radians(51.6)

POSITION_TOLERANCE_M = 1e-3
CONSERVATION_TOLERANCE = 1e-12


def circular_state() -> tuple[np.ndarray, np.ndarray]:
    speed = np.sqrt(MU_M3_S2 / SEMI_MAJOR_M)
    r0 = np.array([SEMI_MAJOR_M, 0.0, 0.0])
    v0 = np.array(
        [0.0, speed * np.cos(INCLINATION_RAD), speed * np.sin(INCLINATION_RAD)]
    )
    return r0, v0


def eccentric_state(eccentricity: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """Perigee state of a slightly eccentric orbit with the same semi-major axis.

    A purely circular orbit is the one case where the universal-variable initial
    guess is exact, so Newton converges in a single step. This orbit keeps the
    iteration honest.
    """
    r_p = SEMI_MAJOR_M * (1.0 - eccentricity)
    v_p = np.sqrt(MU_M3_S2 * (1.0 + eccentricity) / r_p)
    r0 = np.array([r_p, 0.0, 0.0])
    v0 = np.array([0.0, v_p * np.cos(INCLINATION_RAD), v_p * np.sin(INCLINATION_RAD)])
    return r0, v0


def _two_body_rhs(_t: float, y: np.ndarray) -> np.ndarray:
    r = y[:3]
    v = y[3:]
    r_norm = np.linalg.norm(r)
    return np.concatenate([v, -MU_M3_S2 * r / r_norm**3])


def reference_positions(
    r0: np.ndarray, v0: np.ndarray, times: np.ndarray, rtol: float, atol: float
) -> np.ndarray:
    """Independent DOP853 solution of the Cartesian two-body ODE."""
    solution = solve_ivp(
        _two_body_rhs,
        (float(times[0]), float(times[-1])),
        np.concatenate([r0, v0]),
        method="DOP853",
        t_eval=times,
        rtol=rtol,
        atol=atol,
    )
    assert solution.success, solution.message
    return solution.y[:3].T


# --------------------------------------------------------------------------
# Check 1 -- independent reference
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state_fn,label", [(circular_state, "circular"), (eccentric_state, "eccentric")]
)
def test_matches_independent_dop853_reference(state_fn, label, capsys):
    r0, v0 = state_fn()
    period = orbital_period_s(r0, v0)
    times = np.linspace(0.0, period, 400)

    # Tighten the reference until further tightening moves it far below the
    # threshold we are about to apply. Without this, a loose reference could be
    # what we are actually measuring.
    loose = reference_positions(r0, v0, times, rtol=1e-12, atol=1e-6)
    tight = reference_positions(r0, v0, times, rtol=1e-13, atol=1e-9)
    reference_spread = float(np.max(np.linalg.norm(loose - tight, axis=1)))
    assert reference_spread < 0.1 * POSITION_TOLERANCE_M, (
        f"reference not converged: rtol 1e-12 vs 1e-13 differ by "
        f"{reference_spread:.3e} m"
    )

    r_kepler, _ = propagate(r0, v0, times)
    error = float(np.max(np.linalg.norm(r_kepler - tight, axis=1)))

    with capsys.disabled():
        print(
            f"\n[check 1/{label}] reference spread {reference_spread:.3e} m, "
            f"max |kepler - DOP853| {error:.3e} m over one period"
        )

    assert error < POSITION_TOLERANCE_M


def test_backward_then_forward_round_trip():
    """Generation propagates backward, so negative offsets are load bearing."""
    r0, v0 = eccentric_state()
    span = 6.0 * 3600.0

    r_back, v_back = propagate(r0, v0, np.array([-span]))
    r_fwd, _ = propagate(r_back[0], v_back[0], np.array([span]))

    error = float(np.linalg.norm(r_fwd[0] - r0))
    print(f"\n[check 1/round-trip] 6 h backward then forward: {error:.3e} m")
    assert error < POSITION_TOLERANCE_M


# --------------------------------------------------------------------------
# Check 2 -- circular closure
# --------------------------------------------------------------------------


def test_circular_orbit_closes_after_one_period():
    r0, v0 = circular_state()
    period = orbital_period_s(r0, v0)

    r_end, v_end = propagate(r0, v0, np.array([period]))
    position_error = float(np.linalg.norm(r_end[0] - r0))
    velocity_error = float(np.linalg.norm(v_end[0] - v0))

    print(
        f"\n[check 2] closure after one period: position {position_error:.3e} m, "
        f"velocity {velocity_error:.3e} m/s"
    )
    assert position_error < POSITION_TOLERANCE_M


# --------------------------------------------------------------------------
# Check 3 -- conservation on unforced arcs
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state_fn,label", [(circular_state, "circular"), (eccentric_state, "eccentric")]
)
def test_energy_and_angular_momentum_conserved(state_fn, label):
    r0, v0 = state_fn()
    times = np.linspace(0.0, 6.0 * 3600.0, 2000)
    r, v = propagate(r0, v0, times)

    energy = specific_energy(r, v)
    momentum = np.linalg.norm(specific_angular_momentum(r, v), axis=1)

    energy_drift = float(np.max(np.abs(energy - energy[0])) / abs(energy[0]))
    momentum_drift = float(np.max(np.abs(momentum - momentum[0])) / momentum[0])

    print(
        f"\n[check 3/{label}] relative drift over 6 h -- "
        f"energy {energy_drift:.3e}, angular momentum {momentum_drift:.3e}"
    )
    assert energy_drift <= CONSERVATION_TOLERANCE
    assert momentum_drift <= CONSERVATION_TOLERANCE


# --------------------------------------------------------------------------
# Check 4 -- impulse behaviour
# --------------------------------------------------------------------------


def test_zero_impulse_reproduces_baseline():
    r0, v0 = circular_state()
    baseline = Trajectory.from_state(r0, v0)
    burned = baseline.apply_impulse(1800.0, np.zeros(3))

    times = np.linspace(0.0, 6.0 * 3600.0, 1000)
    r_base, v_base = baseline.states_at(times)
    r_burn, v_burn = burned.states_at(times)

    position_error = float(np.max(np.linalg.norm(r_base - r_burn, axis=1)))
    velocity_error = float(np.max(np.linalg.norm(v_base - v_burn, axis=1)))

    print(
        f"\n[check 4/zero] max divergence from re-anchoring: "
        f"{position_error:.3e} m, {velocity_error:.3e} m/s"
    )
    # Not bitwise identical: the burned trajectory re-anchors at the burn and
    # propagates a shorter offset, so the two paths differ at rounding level.
    assert position_error < POSITION_TOLERANCE_M


def test_nonzero_impulse_is_continuous_in_position_and_exact_in_velocity():
    r0, v0 = circular_state()
    baseline = Trajectory.from_state(r0, v0)

    burn_t = 1800.0
    dv = impulse_vector(baseline, burn_t, "PROGRADE", 0.10)
    burned = baseline.apply_impulse(burn_t, dv)

    at_burn = np.array([burn_t])
    r_before, v_before = baseline.states_at(at_burn)
    r_after, v_after = burned.states_at(at_burn)

    position_jump = float(np.linalg.norm(r_after[0] - r_before[0]))
    velocity_delta = v_after[0] - v_before[0]
    velocity_error = float(np.linalg.norm(velocity_delta - dv))

    print(
        f"\n[check 4/nonzero] position jump at burn {position_jump:.3e} m, "
        f"applied delta-v error {velocity_error:.3e} m/s"
    )
    assert position_jump == 0.0
    assert velocity_error < 1e-12
    assert burned.total_delta_v_mps == pytest.approx(0.10, abs=1e-12)


def test_retrograde_is_exactly_opposed_to_prograde():
    r0, v0 = circular_state()
    baseline = Trajectory.from_state(r0, v0)
    forward = impulse_vector(baseline, 900.0, "PROGRADE", 0.05)
    backward = impulse_vector(baseline, 900.0, "RETROGRADE", 0.05)
    assert np.allclose(forward, -backward, rtol=0.0, atol=0.0)


# --------------------------------------------------------------------------
# Input handling -- explicit failures, never a silently wrong array
# --------------------------------------------------------------------------


def test_zero_offset_returns_the_anchor_state_exactly():
    """Burn continuity in trajectory.py depends on this being exact."""
    r0, v0 = eccentric_state()
    r, v = propagate(r0, v0, np.array([0.0]))
    assert np.array_equal(r[0], r0)
    assert np.array_equal(v[0], v0)


def test_empty_time_array_returns_empty_arrays():
    r0, v0 = circular_state()
    r, v = propagate(r0, v0, np.array([]))
    assert r.shape == (0, 3)
    assert v.shape == (0, 3)


@pytest.mark.parametrize(
    "r0,v0,dt",
    [
        (np.array([np.nan, 0.0, 0.0]), np.array([0.0, 7.0e3, 0.0]), np.array([1.0])),
        (np.array([7.0e6, 0.0, 0.0]), np.array([0.0, np.inf, 0.0]), np.array([1.0])),
        (np.array([7.0e6, 0.0, 0.0]), np.array([0.0, 7.0e3, 0.0]), np.array([np.nan])),
        (np.array([7.0e6, 0.0]), np.array([0.0, 7.0e3, 0.0]), np.array([1.0])),
    ],
)
def test_rejects_malformed_input(r0, v0, dt):
    with pytest.raises(PropagationError):
        propagate(r0, v0, dt)


def test_rejects_unbound_state():
    """Escape velocity is outside the supported family and must be refused."""
    r0 = np.array([SEMI_MAJOR_M, 0.0, 0.0])
    escape = np.sqrt(2.0 * MU_M3_S2 / SEMI_MAJOR_M)
    v0 = np.array([0.0, escape * 1.05, 0.0])
    with pytest.raises(PropagationError, match="unsupported state"):
        propagate(r0, v0, np.array([60.0]))


def test_arc_state_arrays_are_not_writeable():
    r0, v0 = circular_state()
    trajectory = Trajectory.from_state(r0, v0)
    with pytest.raises(ValueError):
        trajectory.arcs[0].r0_m[0] = 0.0


def test_impulses_must_be_applied_in_time_order():
    r0, v0 = circular_state()
    trajectory = Trajectory.from_state(r0, v0).apply_impulse(1800.0, np.zeros(3))
    with pytest.raises(PropagationError, match="increasing time order"):
        trajectory.apply_impulse(900.0, np.zeros(3))
