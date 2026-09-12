"""Immutable trajectories built from Keplerian arcs joined by instantaneous impulses.

Pure NumPy. A trajectory is a sequence of arcs; each arc has an anchor state and
a start time. Applying an impulse never mutates the receiver, so candidate
evaluation is a pure function of (trajectory, burn time, delta-v) and results are
safe to cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from backend.core.kepler import PropagationError, propagate


def _frozen_vector(value: np.ndarray, name: str) -> np.ndarray:
    """Copy to an owned, non-writeable float64 (3,) array.

    A frozen dataclass prevents rebinding the attribute; it does nothing about
    in-place mutation of the array it points at. The copy and the writeable flag
    are what actually make an arc immutable.
    """
    arr = np.array(value, dtype=np.float64, copy=True)
    if arr.shape != (3,):
        raise PropagationError(f"{name} must have shape (3,), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise PropagationError(f"{name} contains non-finite values")
    arr.flags.writeable = False
    return arr


@dataclass(frozen=True)
class Arc:
    """A single unforced Keplerian arc anchored at ``t0_s``."""

    t0_s: float
    r0_m: np.ndarray
    v0_mps: np.ndarray

    def __post_init__(self) -> None:
        if not np.isfinite(self.t0_s):
            raise PropagationError("arc start time must be finite")
        object.__setattr__(self, "r0_m", _frozen_vector(self.r0_m, "r0_m"))
        object.__setattr__(self, "v0_mps", _frozen_vector(self.v0_mps, "v0_mps"))


@dataclass(frozen=True)
class Impulse:
    """Record of an applied instantaneous velocity change."""

    t_s: float
    dv_mps: np.ndarray

    def __post_init__(self) -> None:
        if not np.isfinite(self.t_s):
            raise PropagationError("impulse time must be finite")
        object.__setattr__(self, "dv_mps", _frozen_vector(self.dv_mps, "dv_mps"))

    @property
    def magnitude_mps(self) -> float:
        return float(np.linalg.norm(self.dv_mps))


@dataclass(frozen=True)
class Trajectory:
    """An arc sequence queried on one shared simulation clock.

    ``arcs`` is ordered by start time; ``arcs[0].t0_s`` is the earliest queryable
    time. Queries at an impulse timestamp resolve to the post-burn arc.
    """

    arcs: tuple[Arc, ...]
    impulses: tuple[Impulse, ...] = field(default=())

    @classmethod
    def from_state(cls, r0_m: np.ndarray, v0_mps: np.ndarray, t0_s: float = 0.0) -> "Trajectory":
        return cls(arcs=(Arc(t0_s=float(t0_s), r0_m=r0_m, v0_mps=v0_mps),))

    @property
    def start_t_s(self) -> float:
        return self.arcs[0].t0_s

    @property
    def burn_times_s(self) -> tuple[float, ...]:
        return tuple(imp.t_s for imp in self.impulses)

    @property
    def total_delta_v_mps(self) -> float:
        return float(sum(imp.magnitude_mps for imp in self.impulses))

    def apply_impulse(self, burn_t_s: float, dv_mps: np.ndarray) -> "Trajectory":
        """Return a new trajectory with an instantaneous velocity change applied.

        Position is continuous across the burn and velocity changes by exactly
        ``dv_mps``. Both hold exactly rather than approximately, because
        ``propagate`` returns the anchor state unchanged at a zero offset.
        """
        burn_t_s = float(burn_t_s)
        if not np.isfinite(burn_t_s):
            raise PropagationError("burn time must be finite")

        last = self.arcs[-1]
        if burn_t_s < last.t0_s:
            raise PropagationError(
                f"burn time {burn_t_s} precedes the last arc start {last.t0_s}; "
                "impulses must be applied in increasing time order"
            )

        r_b, v_b = propagate(last.r0_m, last.v0_mps, np.array([burn_t_s - last.t0_s]))
        dv = _frozen_vector(dv_mps, "dv_mps")

        new_arc = Arc(t0_s=burn_t_s, r0_m=r_b[0], v0_mps=v_b[0] + dv)
        return Trajectory(
            arcs=self.arcs + (new_arc,),
            impulses=self.impulses + (Impulse(t_s=burn_t_s, dv_mps=dv),),
        )

    def states_at(self, t_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """States at arbitrary times, shape (N, 3) each.

        Times need not be sorted. A time exactly at an impulse resolves to the
        post-burn arc, so the returned velocity is the post-burn velocity.
        """
        t = np.atleast_1d(np.asarray(t_s, dtype=np.float64))
        if t.ndim != 1:
            raise PropagationError(f"t_s must be one-dimensional, got shape {t.shape}")
        if t.size == 0:
            return np.zeros((0, 3)), np.zeros((0, 3))
        if not np.all(np.isfinite(t)):
            raise PropagationError("t_s contains non-finite values")

        starts = np.array([arc.t0_s for arc in self.arcs], dtype=np.float64)
        if np.any(t < starts[0]):
            raise PropagationError(
                f"query time below trajectory start {starts[0]}"
            )

        # side='right' minus one selects the post-burn arc at an exact burn time.
        idx = np.searchsorted(starts, t, side="right") - 1

        r_out = np.empty((t.size, 3), dtype=np.float64)
        v_out = np.empty((t.size, 3), dtype=np.float64)

        for arc_index in np.unique(idx):
            arc = self.arcs[int(arc_index)]
            sel = idx == arc_index
            r_out[sel], v_out[sel] = propagate(
                arc.r0_m, arc.v0_mps, t[sel] - arc.t0_s
            )

        return r_out, v_out


def direction_unit_vector(
    trajectory: Trajectory, burn_t_s: float, direction: str
) -> np.ndarray:
    """Resolve PROGRADE/RETROGRADE against the *unburned* velocity at burn time.

    Call this on the trajectory before the impulse is applied, per
    Handoff/CONTRACTS.md. The returned vector is inertial; it is not an RTN
    component and must not be treated as one.
    """
    _, v = trajectory.states_at(np.array([float(burn_t_s)]))
    speed = float(np.linalg.norm(v[0]))
    if speed <= 0.0:
        raise PropagationError("cannot resolve burn direction from zero velocity")
    unit = v[0] / speed

    if direction == "PROGRADE":
        return unit
    if direction == "RETROGRADE":
        return -unit
    raise PropagationError(
        f"unsupported direction {direction!r}; expected PROGRADE or RETROGRADE"
    )


def impulse_vector(
    trajectory: Trajectory, burn_t_s: float, direction: str, delta_v_mps: float
) -> np.ndarray:
    """Applied inertial delta-v vector for a signed candidate.

    Store the result in candidate evidence rather than re-deriving it later.
    """
    delta_v_mps = float(delta_v_mps)
    if not np.isfinite(delta_v_mps) or delta_v_mps < 0.0:
        raise PropagationError(f"delta-v magnitude must be finite and non-negative, got {delta_v_mps}")
    return direction_unit_vector(trajectory, burn_t_s, direction) * delta_v_mps
