"""One numerical source for the chart and the 3D scene.

Both views read the same ``t_s`` array and the same positions, so a distance
shown beside a marker is the distance the chart plots at that instant. Nothing
downstream recomputes geometry.

The time grid is a union: a regular step, both horizon ends, every burn epoch,
and the exact refined time of every encounter found. That last part is what lets
the scrubber jump to a close approach and display an authoritative minimum
rather than an interpolated one.

**Deviation from CONTRACTS.md, deliberate and worth knowing.** The contract asks
for one-second samples. Over a six-hour horizon that is 21,601 samples times
three objects times three coordinates times three variants -- roughly 583,000
floats, about 11 MB of JSON per request. The contract's actual requirement is
that an exact minimum is never interpolated, and the union above satisfies that
at any base step. The default is therefore 10 s (~700 KB) with the step reported
in the bundle, and callers may ask for finer. Raised with the team rather than
changed silently.
"""

from __future__ import annotations

import numpy as np

from backend.core.encounters import find_encounters, min_separation_series
from backend.core.trajectory import Trajectory
from backend.planning.candidates import Candidate
from backend.planning.search import apply_candidate
from backend.planning.verifier import ReconstructedScenario

DEFAULT_SAMPLE_STEP_S = 10.0
MIN_SAMPLE_STEP_S = 1.0
MAX_VARIANTS = 3
POSITION_DECIMALS = 2
# Encounter times and grid times must round identically, or a reported
# minimum will not land on a sample and the scrubber will interpolate it.
TIME_DECIMALS = 6
SEPARATION_DECIMALS = 2


def _time_grid(
    scenario: ReconstructedScenario,
    trajectories: dict[str, Trajectory],
    encounter_times: list[float],
    sample_step_s: float,
    window: tuple[float, float] | None = None,
) -> np.ndarray:
    start, end = window if window is not None else (0.0, scenario.horizon_s)
    base = np.arange(start, end + sample_step_s, sample_step_s)
    base = base[base <= end]

    extra = [start, end]
    for trajectory in trajectories.values():
        extra.extend(t for t in trajectory.burn_times_s if start <= t <= end)
    extra.extend(t for t in encounter_times if start <= t <= end)

    combined = np.concatenate([base, np.array(extra, dtype=np.float64)])
    # Round before uniquing so a burn epoch and its neighbouring sample do not
    # both survive as two points a microsecond apart.
    return np.unique(np.round(combined, TIME_DECIMALS))


def build_bundle(
    scenario: ReconstructedScenario,
    candidates: list[Candidate],
    case_id: str,
    policy_version: int,
    epoch_utc: str,
    model_version: str,
    min_separation_m: float,
    sample_step_s: float = DEFAULT_SAMPLE_STEP_S,
    window: tuple[float, float] | None = None,
) -> dict:
    """Positions and separations for up to three options on one shared clock.

    ``window`` restricts the samples to one stretch of the horizon, so a close
    approach can be replayed at one-second steps without shipping six hours of
    them. Encounters are still found over the whole horizon; only those inside
    the window are reported, and each of those is a sample, as always.
    """
    if not candidates:
        raise ValueError("at least one candidate is required")
    if len(candidates) > MAX_VARIANTS:
        raise ValueError(f"at most {MAX_VARIANTS} variants per bundle, got {len(candidates)}")
    if not np.isfinite(sample_step_s) or not MIN_SAMPLE_STEP_S <= sample_step_s <= 600.0:
        raise ValueError("sample_step_s must be finite and between 1 and 600 seconds")
    if window is not None:
        start, end = window
        if not (np.isfinite(start) and np.isfinite(end) and 0.0 <= start < end <= scenario.horizon_s):
            raise ValueError("window must lie inside the horizon with start before end")
        if end - start > 3600.0:
            raise ValueError("window may span at most one hour")
    span = (window[1] - window[0]) if window is not None else scenario.horizon_s
    if span / sample_step_s > 21600:
        raise ValueError("visualization exceeds the 21601-sample base-grid budget")

    trajectories = {
        candidate.candidate_id: apply_candidate(scenario.satellite, candidate)
        for candidate in candidates
    }

    encounter_times: list[float] = []
    encounters_by_variant: dict[str, list[dict]] = {}
    for candidate_id, trajectory in trajectories.items():
        found: list[dict] = []
        for debris_id, debris in scenario.debris.items():
            for encounter in find_encounters(
                trajectory, debris, debris_id, scenario.horizon_s, step_s=5.0
            ):
                encounter_times.append(encounter.tca_s)
                found.append(
                    {
                        "object_id": debris_id,
                        "tca_s": round(encounter.tca_s, TIME_DECIMALS),
                        "min_separation_m": round(encounter.min_separation_m, 2),
                        "boundary_kind": encounter.boundary_kind,
                        "ambiguous_time": encounter.ambiguous_time,
                        "below_floor": encounter.min_separation_m < min_separation_m,
                    }
                )
        found.sort(key=lambda e: e["tca_s"])
        encounters_by_variant[candidate_id] = found

    times = _time_grid(scenario, trajectories, encounter_times, sample_step_s, window)
    if window is not None:
        for candidate_id, found in encounters_by_variant.items():
            encounters_by_variant[candidate_id] = [
                e for e in found if window[0] <= e["tca_s"] <= window[1]
            ]

    debris_positions = {
        debris_id: debris.states_at(times)[0]
        for debris_id, debris in scenario.debris.items()
    }

    variants = []
    for candidate in candidates:
        trajectory = trajectories[candidate.candidate_id]
        satellite_positions, _ = trajectory.states_at(times)
        pair, envelope = min_separation_series(trajectory, scenario.debris, times)

        positions = {scenario.satellite_id: satellite_positions}
        positions.update(debris_positions)

        variants.append(
            {
                "candidate_id": candidate.candidate_id,
                "kind": candidate.kind,
                "delta_v_mps": candidate.delta_v_mps,
                "burn_t_s": candidate.burn_t_s,
                "direction": candidate.direction,
                "positions_m": {
                    object_id: np.round(array, POSITION_DECIMALS).tolist()
                    for object_id, array in positions.items()
                },
                "pair_separations_m": {
                    debris_id: np.round(series, SEPARATION_DECIMALS).tolist()
                    for debris_id, series in pair.items()
                },
                "min_to_any_m": np.round(envelope, SEPARATION_DECIMALS).tolist(),
                "encounters": encounters_by_variant[candidate.candidate_id],
            }
        )

    # The invariant the scrubber depends on: every reported encounter time is a
    # real sample, so jumping to a close approach shows a computed minimum and
    # never an interpolated one. Enforced here rather than left to the caller.
    sample_set = set(times.tolist())
    for variant in variants:
        for encounter in variant["encounters"]:
            if encounter["tca_s"] not in sample_set:
                raise ValueError(
                    f"encounter at {encounter['tca_s']} s for "
                    f"{variant['candidate_id']} is not in the time grid"
                )

    return {
        "case_id": case_id,
        "scenario_id": scenario.scenario_id,
        "scenario_version": scenario.scenario_version,
        "policy_version": policy_version,
        "model_version": model_version,
        "frame": "SIM_ECI_TEME_SEEDED",
        "epoch_utc": epoch_utc,
        "horizon_s": scenario.horizon_s,
        "sample_step_s": sample_step_s,
        "window": {"start_s": window[0], "end_s": window[1]} if window is not None else None,
        "min_separation_m": min_separation_m,
        "satellite_id": scenario.satellite_id,
        "primary_threat_id": scenario.primary_threat_id,
        "object_ids": [scenario.satellite_id, *sorted(scenario.debris)],
        "t_s": times.tolist(),
        "variants": variants,
        "note": (
            "Positions and separations share one time grid. The grid includes "
            "both horizon ends, every burn epoch and the exact refined time of "
            "every encounter, so an exact minimum is never interpolated. "
            "Enlarged model geometry is display only and is excluded from these "
            "centre-to-centre distances."
        ),
    }
