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
from scipy.optimize import brentq

from backend.core.kepler import PropagationError
from backend.core.trajectory import Trajectory

BOUNDARY_INTERIOR = "INTERIOR"
BOUNDARY_HORIZON = "HORIZON"
BOUNDARY_BURN = "BURN"

METHOD_REFINED = "brentq_range_rate"
METHOD_BOUNDARY = "segment_boundary"
METHOD_UNREFINED = "grid_sample_unrefined"

_TIME_DEDUPE_S = 1e-6
_BRENTQ_XTOL_S = 1e-6


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


def _range_rate(sat: Trajectory, deb: Trajectory, t: float) -> float:
    """d/dt of half the squared separation: dr . dv. Zero at a stationary point."""
    times = np.array([t], dtype=np.float64)
    r_s, v_s = sat.states_at(times)
    r_d, v_d = deb.states_at(times)
    return float((r_s[0] - r_d[0]) @ (v_s[0] - v_d[0]))


def _separation(sat: Trajectory, deb: Trajectory, t: float) -> tuple[float, float]:
    """(separation, relative speed) at one time."""
    times = np.array([t], dtype=np.float64)
    r_s, v_s = sat.states_at(times)
    r_d, v_d = deb.states_at(times)
    return (
        float(np.linalg.norm(r_s[0] - r_d[0])),
        float(np.linalg.norm(v_s[0] - v_d[0])),
    )


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

        n = times.size

        # Interior local minima, refined on the range-rate sign change.
        for i in range(1, n - 1):
            if not (d2[i] <= d2[i - 1] and d2[i] <= d2[i + 1]):
                continue

            t_lo, t_hi = float(times[i - 1]), float(times[i + 1])
            g_lo = float(dr[i - 1] @ dv[i - 1])
            g_hi = float(dr[i + 1] @ dv[i + 1])

            if g_lo < 0.0 < g_hi:
                t_min = float(
                    brentq(
                        lambda t: _range_rate(
                            satellite_trajectory, debris_trajectory, t
                        ),
                        t_lo,
                        t_hi,
                        xtol=_BRENTQ_XTOL_S,
                    )
                )
                sep, rel_speed = _separation(
                    satellite_trajectory, debris_trajectory, t_min
                )
                # A refined minimum must sit below the bracket it came from.
                # If it does not, the bracket held something other than a
                # simple minimum and the time is not trustworthy.
                if sep <= np.sqrt(d2[i - 1]) and sep <= np.sqrt(d2[i + 1]):
                    found.append(
                        Encounter(
                            other_object_id=debris_object_id,
                            tca_s=t_min,
                            min_separation_m=sep,
                            relative_speed_mps=rel_speed,
                            method=METHOD_REFINED,
                            boundary_kind=BOUNDARY_INTERIOR,
                            ambiguous_time=False,
                        )
                    )
                    continue

            # Flat or degenerate: report the sample, flag the time as unreliable.
            found.append(
                Encounter(
                    other_object_id=debris_object_id,
                    tca_s=float(times[i]),
                    min_separation_m=float(np.sqrt(d2[i])),
                    relative_speed_mps=float(np.linalg.norm(dv[i])),
                    method=METHOD_UNREFINED,
                    boundary_kind=BOUNDARY_INTERIOR,
                    ambiguous_time=True,
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
