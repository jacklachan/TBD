"""Search-path close-approach detection between two trajectories.

Coarse scan, then root refinement on the sign change of the range rate. The
scan is partitioned at every impulse epoch, because velocity is discontinuous
there and an unpartitioned bracket refines to the wrong stationary point --
which is precisely the failure that would hide a post-burn secondary conflict.

This is the search path. The verifier implements its own detection with a finer
scan and bounded scalar minimization, and must not call into this module (see
Handoff/CONTRACTS.md and Handoff/handoffs/A_PHYSICS.md).

Coverage note: a discrete scan is not a general proof that no encounter was
missed. Completeness is validated on the supported scenario family in
tests/test_encounters.py, not claimed in general.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.core.kepler import MU_M3_S2, PropagationError
from backend.core.trajectory import Trajectory

BOUNDARY_INTERIOR = "INTERIOR"
BOUNDARY_HORIZON = "HORIZON"
BOUNDARY_BURN = "BURN"

METHOD_REFINED = "safeguarded_newton_range_rate"
METHOD_BOUNDARY = "segment_boundary"
METHOD_UNREFINED = "grid_sample_unrefined"

_TIME_DEDUPE_S = 1e-6

# Refinement tolerance on the time of closest approach. Every bracket is
# reduced to this width, which is three orders tighter than the 1e-3 s that
# anything downstream compares against, and cheap here because all brackets are
# solved together rather than one scalar solve at a time.
_REFINE_XTOL_S = 1e-9
_MAX_REFINE_ITER = 60


@dataclass(frozen=True)
class Encounter:
    """A local minimum of separation. Field names mirror Handoff/CONTRACTS.md.

    ``ambiguous_time`` is set when the minimum is flat or the bracket did not
    show a clean sign change, meaning the time is not uniquely determined. The
    separation is still reported; the time should not be treated as exact.
    """

    other_object_id: str
    tca_s: float
    min_separation_m: float
    relative_speed_mps: float
    method: str
    boundary_kind: str
    ambiguous_time: bool


def _segment_boundaries(
    trajectories: tuple[Trajectory, ...], start_s: float, horizon_s: float
) -> list[float]:
    """Segment edges: the horizon ends plus every impulse epoch inside them."""
    edges = {float(start_s), float(horizon_s)}
    for traj in trajectories:
        for t_burn in traj.burn_times_s:
            if start_s < t_burn < horizon_s:
                edges.add(float(t_burn))
    return sorted(edges)


def _segment_samples(a: float, b: float, step_s: float) -> np.ndarray:
    """Samples across [a, b] inclusive of both endpoints."""
    span = b - a
    if span <= 0.0:
        return np.array([a], dtype=np.float64)
    count = max(int(np.ceil(span / step_s)), 1) + 1
    return np.linspace(a, b, count, dtype=np.float64)


def _separations(
    sat: Trajectory, deb: Trajectory, times: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(separations, relative speeds) at many times, shape (N,) each."""
    r_s, v_s = sat.states_at(times)
    r_d, v_d = deb.states_at(times)
    return (
        np.linalg.norm(r_s - r_d, axis=1),
        np.linalg.norm(v_s - v_d, axis=1),
    )


def _range_rate_and_slope(
    sat: Trajectory, deb: Trajectory, times: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """g(t) = dr . dv and its exact derivative, elementwise.

    g' = |dv|^2 + dr . (a_sat - a_deb), where each acceleration is the two-body
    term the propagator itself integrates. Having the derivative in closed form
    is what lets the refinement below converge quadratically instead of
    bisecting, so a minimum costs a handful of batched evaluations.
    """
    r_s, v_s = sat.states_at(times)
    r_d, v_d = deb.states_at(times)
    dr = r_s - r_d
    dv = v_s - v_d

    a_s = -MU_M3_S2 * r_s / (np.linalg.norm(r_s, axis=1) ** 3)[:, None]
    a_d = -MU_M3_S2 * r_d / (np.linalg.norm(r_d, axis=1) ** 3)[:, None]

    return (
        np.sum(dr * dv, axis=1),
        np.sum(dv * dv, axis=1) + np.sum(dr * (a_s - a_d), axis=1),
    )


def _refine_minima(
    sat: Trajectory, deb: Trajectory, t_lo: np.ndarray, t_hi: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Solve g(t) = 0 inside every bracket at once. Returns (times, converged).

    Each bracket must satisfy g(t_lo) < 0 < g(t_hi), which is exactly the
    condition the caller screens for. A Newton step is taken when it lands
    strictly inside the live bracket and bisection otherwise, so convergence is
    guaranteed by the bracket and fast in the ordinary case.

    A root is frozen the moment it meets the tolerance and is dropped from the
    batch. That matters for reproducibility: a candidate's reported time must
    not depend on how many other minima happened to be solved alongside it.
    """
    lo = np.array(t_lo, dtype=np.float64, copy=True)
    hi = np.array(t_hi, dtype=np.float64, copy=True)
    t = 0.5 * (lo + hi)
    active = np.ones(t.shape, dtype=bool)

    for _ in range(_MAX_REFINE_ITER):
        index = np.flatnonzero(active)
        if index.size == 0:
            break

        current = t[index]
        g, slope = _range_rate_and_slope(sat, deb, current)

        # Keep the sign convention g(lo) < 0 < g(hi) as the bracket shrinks.
        negative = g < 0.0
        lo[index[negative]] = current[negative]
        hi[index[~negative]] = current[~negative]

        with np.errstate(divide="ignore", invalid="ignore"):
            newton = current - g / slope
        inside = (
            np.isfinite(newton)
            & (slope > 0.0)
            & (newton > lo[index])
            & (newton < hi[index])
        )
        step_to = np.where(inside, newton, 0.5 * (lo[index] + hi[index]))

        converged = ((hi[index] - lo[index]) <= _REFINE_XTOL_S) | (
            np.abs(step_to - current) <= _REFINE_XTOL_S
        )
        t[index] = step_to
        active[index] = ~converged

    return t, ~active


def find_encounters(
    satellite_trajectory: Trajectory,
    debris_trajectory: Trajectory,
    debris_object_id: str,
    horizon_s: float,
    step_s: float = 5.0,
    start_s: float = 0.0,
) -> list[Encounter]:
    """Local separation minima across [start_s, horizon_s], ascending in time.

    Every local minimum is returned; filtering against a clearance floor is the
    caller's job. Segment endpoints (the horizon ends and each impulse epoch)
    are evaluated as one-sided minima and reported with their boundary kind.
    """
    if not np.isfinite(horizon_s) or horizon_s <= start_s:
        raise PropagationError(
            f"horizon_s must be finite and greater than start_s, got {horizon_s}"
        )
    if not np.isfinite(step_s) or step_s <= 0.0:
        raise PropagationError(f"step_s must be finite and positive, got {step_s}")

    edges = _segment_boundaries(
        (satellite_trajectory, debris_trajectory), start_s, horizon_s
    )
    burn_times = set(satellite_trajectory.burn_times_s) | set(
        debris_trajectory.burn_times_s
    )

    found: list[Encounter] = []

    for seg_start, seg_end in zip(edges[:-1], edges[1:]):
        times = _segment_samples(seg_start, seg_end, step_s)

        r_s, v_s = satellite_trajectory.states_at(times)
        r_d, v_d = debris_trajectory.states_at(times)
        dr = r_s - r_d
        dv = v_s - v_d
        d2 = np.sum(dr * dr, axis=1)
        g = np.sum(dr * dv, axis=1)

        n = times.size

        # Interior local minima, located across the whole segment at once and
        # then refined in a single batch. Walking the samples one at a time and
        # running a scalar root solve per minimum costs one propagation call per
        # solver iteration; doing it this way costs one call per iteration for
        # every minimum in the segment together.
        interior = (
            np.flatnonzero((d2[1:-1] <= d2[:-2]) & (d2[1:-1] <= d2[2:])) + 1
            if n > 2
            else np.empty(0, dtype=np.intp)
        )

        if interior.size:
            tca = times[interior].astype(np.float64)
            separation = np.sqrt(d2[interior])
            speed = np.linalg.norm(dv[interior], axis=1)
            refined = np.zeros(interior.shape, dtype=bool)

            bracketed = (g[interior - 1] < 0.0) & (g[interior + 1] > 0.0)
            refine_at = interior[bracketed]

            if refine_at.size:
                root_t, converged = _refine_minima(
                    satellite_trajectory,
                    debris_trajectory,
                    times[refine_at - 1],
                    times[refine_at + 1],
                )
                root_sep, root_speed = _separations(
                    satellite_trajectory, debris_trajectory, root_t
                )
                # A refined minimum must sit below the bracket it came from. If
                # it does not, the bracket held something other than a simple
                # minimum and the time is not trustworthy.
                accepted = (
                    converged
                    & (root_sep <= np.sqrt(d2[refine_at - 1]))
                    & (root_sep <= np.sqrt(d2[refine_at + 1]))
                )
                slot = np.flatnonzero(bracketed)[accepted]
                tca[slot] = root_t[accepted]
                separation[slot] = root_sep[accepted]
                speed[slot] = root_speed[accepted]
                refined[slot] = True

            for position in range(interior.size):
                # Flat, degenerate or non-convergent: report the sample and flag
                # the time as unreliable rather than quoting a made-up instant.
                is_refined = bool(refined[position])
                found.append(
                    Encounter(
                        other_object_id=debris_object_id,
                        tca_s=float(tca[position]),
                        min_separation_m=float(separation[position]),
                        relative_speed_mps=float(speed[position]),
                        method=METHOD_REFINED if is_refined else METHOD_UNREFINED,
                        boundary_kind=BOUNDARY_INTERIOR,
                        ambiguous_time=not is_refined,
                    )
                )

        # Segment endpoints as one-sided minima.
        for edge_index, t_edge in ((0, seg_start), (n - 1, seg_end)):
            if n > 1:
                neighbour = 1 if edge_index == 0 else n - 2
                if d2[edge_index] > d2[neighbour]:
                    continue

            is_burn = any(abs(t_edge - tb) <= _TIME_DEDUPE_S for tb in burn_times)
            found.append(
                Encounter(
                    other_object_id=debris_object_id,
                    tca_s=float(t_edge),
                    min_separation_m=float(np.sqrt(d2[edge_index])),
                    relative_speed_mps=float(np.linalg.norm(dv[edge_index])),
                    method=METHOD_BOUNDARY,
                    boundary_kind=BOUNDARY_BURN if is_burn else BOUNDARY_HORIZON,
                    ambiguous_time=False,
                )
            )

    return _dedupe(found)


def _dedupe(encounters: list[Encounter]) -> list[Encounter]:
    """Drop duplicate times, keeping the closest approach at each.

    An impulse epoch is the right edge of one segment and the left edge of the
    next. Separation is continuous there, so both segments report it.
    """
    ordered = sorted(encounters, key=lambda e: (e.tca_s, e.min_separation_m))
    kept: list[Encounter] = []
    for enc in ordered:
        if kept and abs(enc.tca_s - kept[-1].tca_s) <= _TIME_DEDUPE_S:
            continue
        kept.append(enc)
    return kept


def closest_encounter(encounters: list[Encounter]) -> Encounter | None:
    """The smallest separation in the list, or None when empty."""
    if not encounters:
        return None
    return min(encounters, key=lambda e: e.min_separation_m)


def min_separation_series(
    satellite_trajectory: Trajectory,
    debris_trajectories: dict[str, Trajectory],
    t_s: np.ndarray,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Per-pair separations and the min-to-any envelope on a shared time grid.

    Feeds the VisualizationBundle. Every array aligns with the supplied ``t_s``
    so the chart, the 3D scene and any displayed distance read one sample.
    """
    times = np.atleast_1d(np.asarray(t_s, dtype=np.float64))
    r_s, _ = satellite_trajectory.states_at(times)

    pair: dict[str, np.ndarray] = {}
    for object_id, traj in debris_trajectories.items():
        r_d, _ = traj.states_at(times)
        pair[object_id] = np.linalg.norm(r_s - r_d, axis=1)

    if pair:
        envelope = np.min(np.stack(list(pair.values()), axis=0), axis=0)
    else:
        envelope = np.full(times.shape, np.inf)

    return pair, envelope
