"""Universal-variable two-body propagation.

Pure NumPy/SciPy. No HTTP, LLM, policy, or persistence dependencies (see
Handoff/AGENTS.md). Analytic in formulation, floating point in practice: the
tests in tests/test_kepler.py measure the actual error rather than assuming it.

Frame is SIM_ECI_TEME_SEEDED per Handoff/CONTRACTS.md. Units are metres,
seconds, metres/second throughout.
"""

from __future__ import annotations

import numpy as np

MU_M3_S2 = 3.986004418e14
EARTH_RADIUS_M = 6378137.0

# Below this |psi| the closed-form Stumpff expressions lose significance to
# cancellation, so the series is used instead. At |psi| = 0.1 the first omitted
# series term is ~1e-17 relative, and the closed form has lost only ~1.3
# digits, so the two agree to machine precision across the switch.
_PSI_SERIES_LIMIT = 0.1

_MAX_NEWTON_ITER = 60
_NEWTON_REL_TOL = 1e-12

# Tolerance for the Lagrange identity f*gd - g*fd == 1. This is a correctness
# guard, not a physics claim; it catches a mis-formed coefficient set.
_LAGRANGE_RTOL = 1e-8
_LAGRANGE_ATOL = 1e-8


class PropagationError(RuntimeError):
    """Raised for non-finite input, an unsupported state, or non-convergence.

    Callers must treat this as an explicit numerical failure. It must never be
    swallowed into a silently wrong trajectory.
    """


def stumpff(psi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Stumpff functions C(psi) and S(psi), elementwise.

    Uses the series near zero and the closed forms elsewhere. Handles psi of
    either sign; only the elliptic branch is exercised by the supported orbit
    family, but the hyperbolic branch is correct and kept for generality.
    """
    psi = np.asarray(psi, dtype=np.float64)
    c2 = np.empty_like(psi)
    c3 = np.empty_like(psi)

    small = np.abs(psi) < _PSI_SERIES_LIMIT
    pos = (~small) & (psi > 0.0)
    neg = (~small) & (psi < 0.0)

    if np.any(pos):
        s = np.sqrt(psi[pos])
        c2[pos] = (1.0 - np.cos(s)) / psi[pos]
        c3[pos] = (s - np.sin(s)) / (s * s * s)

    if np.any(neg):
        s = np.sqrt(-psi[neg])
        # (1 - cosh(s)) / psi == (cosh(s) - 1) / s**2 for psi = -s**2
        c2[neg] = (1.0 - np.cosh(s)) / psi[neg]
        c3[neg] = (np.sinh(s) - s) / (s * s * s)

    if np.any(small):
        p = psi[small]
        c2[small] = (
            1.0 / 2.0
            - p / 24.0
            + p**2 / 720.0
            - p**3 / 40320.0
            + p**4 / 3628800.0
            - p**5 / 479001600.0
        )
        c3[small] = (
            1.0 / 6.0
            - p / 120.0
            + p**2 / 5040.0
            - p**3 / 362880.0
            + p**4 / 39916800.0
            - p**5 / 6227020800.0
        )

    return c2, c3


def _as_state_vector(value: np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3,):
        raise PropagationError(f"{name} must have shape (3,), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise PropagationError(f"{name} contains non-finite values")
    return arr


def propagate(
    r0_m: np.ndarray,
    v0_mps: np.ndarray,
    dt_s: np.ndarray,
    mu: float = MU_M3_S2,
) -> tuple[np.ndarray, np.ndarray]:
    """Propagate one anchor state to many time offsets.

    Args:
        r0_m: anchor position, shape (3,).
        v0_mps: anchor velocity, shape (3,).
        dt_s: time offsets from the anchor, shape (N,). May be negative;
            backward propagation is used by the scenario generator.

    Returns:
        (r_m, v_mps), each shape (N, 3).

    Raises:
        PropagationError: non-finite input, unbound or unsupported state, or
            Newton non-convergence.

    A zero offset returns the anchor state exactly, which is what makes burn
    continuity in trajectory.py exact rather than approximate.
    """
    r0 = _as_state_vector(r0_m, "r0_m")
    v0 = _as_state_vector(v0_mps, "v0_mps")

    dt = np.atleast_1d(np.asarray(dt_s, dtype=np.float64))
    if dt.ndim != 1:
        raise PropagationError(f"dt_s must be one-dimensional, got shape {dt.shape}")
    if dt.size == 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    if not np.all(np.isfinite(dt)):
        raise PropagationError("dt_s contains non-finite values")

    sqrt_mu = np.sqrt(mu)
    r0n = float(np.linalg.norm(r0))
    if r0n <= 0.0:
        raise PropagationError("anchor position has zero magnitude")

    rdv = float(r0 @ v0)
    alpha = 2.0 / r0n - float(v0 @ v0) / mu  # reciprocal semi-major axis

    # The supported family is bound near-circular LEO. Parabolic and hyperbolic
    # states need a different initial guess and are rejected rather than
    # silently propagated with an elliptic assumption.
    if alpha <= 1e-12:
        raise PropagationError(
            f"unsupported state: reciprocal semi-major axis {alpha:.6e} <= 0 "
            "(only bound orbits are supported)"
        )

    # For a circular orbit chi = sqrt(mu) * dt / a exactly, so this guess is
    # essentially exact for the supported family and Newton converges in a
    # small number of steps even across several revolutions.
    chi = sqrt_mu * dt * alpha

    converged = False
    for _ in range(_MAX_NEWTON_ITER):
        psi = chi * chi * alpha
        c2, c3 = stumpff(psi)
        r = (
            chi * chi * c2
            + (rdv / sqrt_mu) * chi * (1.0 - psi * c3)
            + r0n * (1.0 - psi * c2)
        )
        if not np.all(np.isfinite(r)) or np.any(r == 0.0):
            raise PropagationError("Newton iteration produced a degenerate radius")

        residual = sqrt_mu * dt - (
            chi**3 * c3
            + (rdv / sqrt_mu) * chi * chi * c2
            + r0n * chi * (1.0 - psi * c3)
        )
        dchi = residual / r
        chi = chi + dchi

        if np.max(np.abs(dchi)) <= _NEWTON_REL_TOL * max(
            1.0, float(np.max(np.abs(chi)))
        ):
            converged = True
            break

    if not converged:
        raise PropagationError(
            f"universal Kepler iteration did not converge in {_MAX_NEWTON_ITER} steps"
        )

    # Recompute every psi-dependent quantity with the final chi. Reusing the
    # values from inside the loop would evaluate the Lagrange coefficients one
    # Newton step stale; the result stays plausible, which is what makes that
    # mistake expensive to find later.
    psi = chi * chi * alpha
    c2, c3 = stumpff(psi)
    r = (
        chi * chi * c2
        + (rdv / sqrt_mu) * chi * (1.0 - psi * c3)
        + r0n * (1.0 - psi * c2)
    )
    if not np.all(np.isfinite(r)) or np.any(r == 0.0):
        raise PropagationError("final radius is degenerate")

    f = 1.0 - chi * chi * c2 / r0n
    g = dt - chi**3 * c3 / sqrt_mu
    gd = 1.0 - chi * chi * c2 / r
    fd = (sqrt_mu / (r * r0n)) * chi * (psi * c3 - 1.0)

    identity = f * gd - g * fd
    if not np.allclose(identity, 1.0, rtol=_LAGRANGE_RTOL, atol=_LAGRANGE_ATOL):
        worst = float(np.max(np.abs(identity - 1.0)))
        raise PropagationError(
            f"Lagrange identity f*gd - g*fd deviates from 1 by {worst:.3e}"
        )

    r_out = f[:, None] * r0 + g[:, None] * v0
    v_out = fd[:, None] * r0 + gd[:, None] * v0

    if not (np.all(np.isfinite(r_out)) and np.all(np.isfinite(v_out))):
        raise PropagationError("propagation produced non-finite output")

    return r_out, v_out


def specific_energy(r_m: np.ndarray, v_mps: np.ndarray, mu: float = MU_M3_S2) -> np.ndarray:
    """Specific orbital energy, J/kg. Conserved on unforced two-body arcs."""
    r = np.atleast_2d(np.asarray(r_m, dtype=np.float64))
    v = np.atleast_2d(np.asarray(v_mps, dtype=np.float64))
    return 0.5 * np.sum(v * v, axis=1) - mu / np.linalg.norm(r, axis=1)


def specific_angular_momentum(r_m: np.ndarray, v_mps: np.ndarray) -> np.ndarray:
    """Specific angular momentum vector, m^2/s. Conserved on unforced arcs."""
    r = np.atleast_2d(np.asarray(r_m, dtype=np.float64))
    v = np.atleast_2d(np.asarray(v_mps, dtype=np.float64))
    return np.cross(r, v)


def orbital_period_s(r_m: np.ndarray, v_mps: np.ndarray, mu: float = MU_M3_S2) -> float:
    """Keplerian period of the osculating orbit through this state."""
    r = _as_state_vector(r_m, "r_m")
    v = _as_state_vector(v_mps, "v_mps")
    rn = float(np.linalg.norm(r))
    alpha = 2.0 / rn - float(v @ v) / mu
    if alpha <= 1e-12:
        raise PropagationError("period is undefined for an unbound state")
    a = 1.0 / alpha
    return float(2.0 * np.pi * np.sqrt(a**3 / mu))
