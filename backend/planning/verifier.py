"""Independent validation. The only path that can clear a proposal.

Independence is structural, not a naming convention:

* Input is the raw serialized scenario plus a candidate and the active policy.
  Trajectories are rebuilt here from the stored initial states; no object built
  by the search is accepted.
* This module must not import ``backend.planning.search``, reuse its evaluator,
  or read its cache.
* Encounter detection is implemented here and does not call
  ``backend.core.encounters``. It uses a 1 s scan and bounded minimization of
  squared distance, where the search uses a 5 s scan and root-finding on the
  range rate -- different sampling and a different numerical method.
* Screening covers every debris object over the whole horizon, where the search
  covers only the primary threat.

What is deliberately shared: the tested Kepler propagator and trajectory
primitives in ``backend.core``. Reimplementing the physics twice would test
nothing useful; Gate 1 checks the propagator against an independent integrator,
and independence here is at the reconstruction and screening layer. Say this
plainly rather than implying two independent physics models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import minimize_scalar

from backend.core.kepler import PropagationError
from backend.core.trajectory import Trajectory, impulse_vector
from backend.planning.candidates import KIND_IMPULSE, KIND_NO_BURN, Candidate
from backend.planning.policy import Policy

MODEL_VERSION = "two-body-universal-variable-1"
VERIFIER_METHOD = "scan_1s_bounded_min_squared_distance"

STATUS_PASS = "PASS"
STATUS_BLOCK = "BLOCK"
STATUS_ERROR = "ERROR"

REASON_OK = "OK"
REASON_OVER_BUDGET = "OVER_BUDGET"
REASON_BURN_IN_BLOCKED_WINDOW = "BURN_IN_BLOCKED_WINDOW"
REASON_BURN_OUTSIDE_HORIZON = "BURN_OUTSIDE_HORIZON"
REASON_BELOW_CLEARANCE_FLOOR = "BELOW_CLEARANCE_FLOOR"
REASON_SEARCH_DISAGREEMENT = "SEARCH_DISAGREEMENT"
REASON_AMBIGUOUS_MINIMUM = "AMBIGUOUS_MINIMUM"
REASON_NO_ENCOUNTER_FOUND = "NO_ENCOUNTER_FOUND"
REASON_SCENARIO_INVALID = "SCENARIO_INVALID"
REASON_CANDIDATE_INVALID = "CANDIDATE_INVALID"
REASON_VERSION_MISMATCH = "VERSION_MISMATCH"
REASON_NUMERICAL_ERROR = "NUMERICAL_ERROR"

VERIFIER_STEP_S = 1.0
AGREEMENT_DISTANCE_TOL_M = 1.0
AGREEMENT_TIME_TOL_S = 0.1

_FLAT_MINIMUM_TOL_M = 1e-6
_MINIMIZE_XATOL_S = 1e-7


class ScenarioError(ValueError):
    """The scenario document is malformed or internally inconsistent."""


@dataclass(frozen=True)
class VerifiedEncounter:
    other_object_id: str
    tca_s: float
    min_separation_m: float
    relative_speed_mps: float
    boundary_kind: str
    ambiguous_time: bool


@dataclass(frozen=True)
class ValidationResult:
    scenario_id: str
    scenario_version: int
    policy_version: int
    candidate_id: str
    validation_id: str
    status: str
    encounters: tuple[VerifiedEncounter, ...]
    reason_codes: tuple[str, ...]
    evaluated_object_ids: tuple[str, ...]
    horizon_s: float
    sample_step_s: float
    method: str
    model_version: str
    computed_at_utc: str
    max_primary_distance_disagreement_m: float | None = None
    primary_time_disagreement_s: float | None = None
    detail: dict = field(default_factory=dict)

    @property
    def approvable(self) -> bool:
        return self.status == STATUS_PASS

    def closest(self) -> VerifiedEncounter | None:
        if not self.encounters:
            return None
        return min(self.encounters, key=lambda e: e.min_separation_m)


# --------------------------------------------------------------------------
# Reconstruction from raw scenario data
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconstructedScenario:
    scenario_id: str
    scenario_version: int
    horizon_s: float
    satellite_id: str
    primary_threat_id: str
    satellite: Trajectory
    debris: dict[str, Trajectory]


def reconstruct(document: dict) -> ReconstructedScenario:
    """Rebuild trajectories from the serialized scenario. Nothing is imported."""
    try:
        scenario_id = str(document["scenario_id"])
        scenario_version = int(document["scenario_version"])
        horizon_s = float(document["horizon_s"])
        satellite_id = str(document["satellite_id"])
        primary_threat_id = str(document["primary_threat_id"])
        entries = document["objects"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ScenarioError(f"scenario is missing required fields: {exc}") from exc

    if not np.isfinite(horizon_s) or horizon_s <= 0.0:
        raise ScenarioError(f"horizon_s must be finite and positive, got {horizon_s}")
    if not isinstance(entries, list) or len(entries) < 2:
        raise ScenarioError("scenario must contain at least a satellite and one debris object")

    satellite: Trajectory | None = None
    debris: dict[str, Trajectory] = {}

    for entry in entries:
        try:
            object_id = str(entry["object_id"])
            state = entry["initial_state"]
            r = np.asarray(state["r_m"], dtype=np.float64)
            v = np.asarray(state["v_mps"], dtype=np.float64)
        except (KeyError, TypeError, ValueError) as exc:
            raise ScenarioError(f"malformed object entry: {exc}") from exc

        if r.shape != (3,) or v.shape != (3,):
            raise ScenarioError(f"object {object_id} state must be two 3-vectors")
        if not (np.all(np.isfinite(r)) and np.all(np.isfinite(v))):
            raise ScenarioError(f"object {object_id} state contains non-finite values")

        try:
            trajectory = Trajectory.from_state(r, v)
        except PropagationError as exc:
            raise ScenarioError(f"object {object_id} state rejected: {exc}") from exc

        if object_id == satellite_id:
            satellite = trajectory
        else:
            debris[object_id] = trajectory

    if satellite is None:
        raise ScenarioError(f"satellite_id {satellite_id!r} not present among objects")
    if primary_threat_id not in debris:
        raise ScenarioError(f"primary_threat_id {primary_threat_id!r} not present among objects")

    return ReconstructedScenario(
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        horizon_s=horizon_s,
        satellite_id=satellite_id,
        primary_threat_id=primary_threat_id,
        satellite=satellite,
        debris=debris,
    )


# --------------------------------------------------------------------------
# Independent encounter screening
# --------------------------------------------------------------------------


def _segment_edges(trajectory: Trajectory, horizon_s: float) -> list[float]:
    edges = {0.0, float(horizon_s)}
    for t_burn in trajectory.burn_times_s:
        if 0.0 < t_burn < horizon_s:
            edges.add(float(t_burn))
    return sorted(edges)


def screen_pair(
    satellite: Trajectory,
    debris: Trajectory,
    debris_id: str,
    horizon_s: float,
    step_s: float = VERIFIER_STEP_S,
) -> VerifiedEncounter | None:
    """Closest approach over the horizon, by this module's own method.

    Scans at 1 s, partitions at every burn epoch because velocity is
    discontinuous there, and refines each interior minimum by bounded
    minimization of the squared separation. The search path instead root-finds
    on the range rate at 5 s; agreement between the two is what the caller
    checks.
    """
    best: VerifiedEncounter | None = None
    edges = _segment_edges(satellite, horizon_s)

    for seg_start, seg_end in zip(edges[:-1], edges[1:]):
        span = seg_end - seg_start
        count = max(int(np.ceil(span / step_s)), 1) + 1
        times = np.linspace(seg_start, seg_end, count, dtype=np.float64)

        r_s, v_s = satellite.states_at(times)
        r_d, v_d = debris.states_at(times)
        separation = np.linalg.norm(r_s - r_d, axis=1)
        relative_speed = np.linalg.norm(v_s - v_d, axis=1)

        def squared_at(t: float) -> float:
            query = np.array([t], dtype=np.float64)
            a, _ = satellite.states_at(query)
            b, _ = debris.states_at(query)
            delta = a[0] - b[0]
            return float(delta @ delta)

        n = times.size
        for index in range(n):
            is_left_edge = index == 0
            is_right_edge = index == n - 1

            if is_left_edge or is_right_edge:
                neighbour = 1 if is_left_edge else n - 2
                if n > 1 and separation[index] > separation[neighbour]:
                    continue
                boundary_kind = (
                    "HORIZON"
                    if float(times[index]) in (0.0, float(horizon_s))
                    else "BURN"
                )
                candidate = VerifiedEncounter(
                    other_object_id=debris_id,
                    tca_s=float(times[index]),
                    min_separation_m=float(separation[index]),
                    relative_speed_mps=float(relative_speed[index]),
                    boundary_kind=boundary_kind,
                    ambiguous_time=False,
                )
            else:
                if not (
                    separation[index] <= separation[index - 1]
                    and separation[index] <= separation[index + 1]
                ):
                    continue

                lo, hi = float(times[index - 1]), float(times[index + 1])
                outcome = minimize_scalar(
                    squared_at,
                    bounds=(lo, hi),
                    method="bounded",
                    options={"xatol": _MINIMIZE_XATOL_S},
                )
                refined_t = float(outcome.x)
                refined_separation = float(np.sqrt(max(outcome.fun, 0.0)))

                # A refined minimum that is no better than the samples around it
                # means the curve is flat here; report the value but do not claim
                # the time is determined.
                bracket_low = float(min(separation[index - 1], separation[index + 1]))
                ambiguous = (bracket_low - refined_separation) < _FLAT_MINIMUM_TOL_M

                if refined_separation > separation[index]:
                    refined_t = float(times[index])
                    refined_separation = float(separation[index])
                    ambiguous = True

                query = np.array([refined_t], dtype=np.float64)
                _, sat_v = satellite.states_at(query)
                _, deb_v = debris.states_at(query)

                candidate = VerifiedEncounter(
                    other_object_id=debris_id,
                    tca_s=refined_t,
                    min_separation_m=refined_separation,
                    relative_speed_mps=float(np.linalg.norm(sat_v[0] - deb_v[0])),
                    boundary_kind="INTERIOR",
                    ambiguous_time=ambiguous,
                )

            if best is None or candidate.min_separation_m < best.min_separation_m:
                best = candidate

    return best


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def _rebuild_candidate_trajectory(
    satellite: Trajectory, candidate: Candidate, horizon_s: float
) -> tuple[Trajectory, list[str], dict]:
    """Re-derive the manoeuvred trajectory and re-check the candidate itself.

    The applied vector is recomputed here from the unburned velocity rather than
    read from anything the search produced.
    """
    reasons: list[str] = []
    detail: dict = {}

    if candidate.kind == KIND_NO_BURN:
        if candidate.delta_v_mps != 0.0 or candidate.burn_t_s is not None:
            reasons.append(REASON_CANDIDATE_INVALID)
        return satellite, reasons, detail

    if candidate.kind != KIND_IMPULSE:
        return satellite, [REASON_CANDIDATE_INVALID], detail

    if candidate.burn_t_s is None or candidate.direction is None:
        return satellite, [REASON_CANDIDATE_INVALID], detail

    burn_t = float(candidate.burn_t_s)
    if not np.isfinite(burn_t) or burn_t < 0.0 or burn_t > horizon_s:
        return satellite, [REASON_BURN_OUTSIDE_HORIZON], detail

    try:
        dv = impulse_vector(satellite, burn_t, candidate.direction, candidate.delta_v_mps)
        trajectory = satellite.apply_impulse(burn_t, dv)
    except PropagationError as exc:
        detail["numerical_error"] = str(exc)
        return satellite, [REASON_NUMERICAL_ERROR], detail

    detail["applied_delta_v_mps"] = [float(x) for x in dv]
    detail["applied_magnitude_mps"] = float(np.linalg.norm(dv))
    return trajectory, reasons, detail


def validate_candidate(
    raw_scenario: dict,
    policy: Policy,
    candidate: Candidate,
    expected_primary_encounter: dict | None = None,
    expected_scenario_version: int | None = None,
) -> ValidationResult:
    """Recompute one option against the whole scenario and the active policy.

    ``expected_primary_encounter`` is a comparison target only -- a mapping with
    ``min_separation_m`` and ``tca_s`` from the search. It is never accepted as
    evidence; disagreement beyond tolerance blocks the proposal.
    """
    validation_id = f"val_{uuid.uuid4().hex[:12]}"
    computed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def result(
        status: str,
        reasons: list[str],
        *,
        scenario: ReconstructedScenario | None = None,
        encounters: tuple[VerifiedEncounter, ...] = (),
        distance_disagreement: float | None = None,
        time_disagreement: float | None = None,
        detail: dict | None = None,
    ) -> ValidationResult:
        return ValidationResult(
            scenario_id=scenario.scenario_id if scenario else "",
            scenario_version=scenario.scenario_version if scenario else -1,
            policy_version=policy.policy_version,
            candidate_id=candidate.candidate_id,
            validation_id=validation_id,
            status=status,
            encounters=encounters,
            reason_codes=tuple(reasons) if reasons else (REASON_OK,),
            evaluated_object_ids=tuple(sorted(scenario.debris)) if scenario else (),
            horizon_s=scenario.horizon_s if scenario else 0.0,
            sample_step_s=VERIFIER_STEP_S,
            method=VERIFIER_METHOD,
            model_version=MODEL_VERSION,
            computed_at_utc=computed_at,
            max_primary_distance_disagreement_m=distance_disagreement,
            primary_time_disagreement_s=time_disagreement,
            detail=detail or {},
        )

    try:
        scenario = reconstruct(raw_scenario)
    except ScenarioError as exc:
        return result(STATUS_ERROR, [REASON_SCENARIO_INVALID], detail={"error": str(exc)})

    if (
        expected_scenario_version is not None
        and expected_scenario_version != scenario.scenario_version
    ):
        return result(
            STATUS_BLOCK,
            [REASON_VERSION_MISMATCH],
            scenario=scenario,
            detail={
                "expected_scenario_version": expected_scenario_version,
                "actual_scenario_version": scenario.scenario_version,
            },
        )

    reasons: list[str] = []

    # Policy is re-checked here rather than trusted from the search.
    if candidate.delta_v_mps > policy.max_delta_v_mps + 1e-12:
        reasons.append(REASON_OVER_BUDGET)
    if candidate.burn_t_s is not None:
        for window in policy.blocked_windows:
            if window.contains(float(candidate.burn_t_s)):
                reasons.append(REASON_BURN_IN_BLOCKED_WINDOW)
                break

    trajectory, candidate_reasons, detail = _rebuild_candidate_trajectory(
        scenario.satellite, candidate, scenario.horizon_s
    )
    reasons.extend(candidate_reasons)

    # These mean the candidate could not be evaluated at all, which is a
    # different thing from evaluating it and saying no. The UI shows an error
    # state for the first and a rejected option for the second.
    unevaluatable = {
        REASON_NUMERICAL_ERROR,
        REASON_CANDIDATE_INVALID,
        REASON_BURN_OUTSIDE_HORIZON,
    }
    if unevaluatable.intersection(reasons):
        return result(STATUS_ERROR, reasons, scenario=scenario, detail=detail)

    # Every debris object, whole horizon -- not only the primary threat.
    encounters: list[VerifiedEncounter] = []
    try:
        for debris_id in sorted(scenario.debris):
            found = screen_pair(
                trajectory, scenario.debris[debris_id], debris_id, scenario.horizon_s
            )
            if found is None:
                reasons.append(REASON_NO_ENCOUNTER_FOUND)
            else:
                encounters.append(found)
    except PropagationError as exc:
        detail["numerical_error"] = str(exc)
        return result(STATUS_ERROR, [REASON_NUMERICAL_ERROR], scenario=scenario, detail=detail)

    for encounter in encounters:
        if encounter.min_separation_m < policy.min_separation_m:
            reasons.append(REASON_BELOW_CLEARANCE_FLOOR)
            detail.setdefault("violating_objects", []).append(
                {
                    "object_id": encounter.other_object_id,
                    "min_separation_m": encounter.min_separation_m,
                    "tca_s": encounter.tca_s,
                }
            )
        if encounter.ambiguous_time:
            reasons.append(REASON_AMBIGUOUS_MINIMUM)

    distance_disagreement: float | None = None
    time_disagreement: float | None = None

    if expected_primary_encounter is not None:
        primary = next(
            (e for e in encounters if e.other_object_id == scenario.primary_threat_id), None
        )
        if primary is None:
            reasons.append(REASON_SEARCH_DISAGREEMENT)
            detail["disagreement"] = "verifier found no encounter with the primary threat"
        else:
            distance_disagreement = abs(
                primary.min_separation_m - float(expected_primary_encounter["min_separation_m"])
            )
            time_disagreement = abs(
                primary.tca_s - float(expected_primary_encounter["tca_s"])
            )
            if (
                distance_disagreement > AGREEMENT_DISTANCE_TOL_M
                or time_disagreement > AGREEMENT_TIME_TOL_S
            ):
                reasons.append(REASON_SEARCH_DISAGREEMENT)
                detail["disagreement"] = {
                    "search_min_separation_m": float(
                        expected_primary_encounter["min_separation_m"]
                    ),
                    "verifier_min_separation_m": primary.min_separation_m,
                    "search_tca_s": float(expected_primary_encounter["tca_s"]),
                    "verifier_tca_s": primary.tca_s,
                    "distance_tolerance_m": AGREEMENT_DISTANCE_TOL_M,
                    "time_tolerance_s": AGREEMENT_TIME_TOL_S,
                }

    deduped = tuple(dict.fromkeys(reasons))
    status = STATUS_PASS if not deduped else STATUS_BLOCK

    return result(
        status,
        list(deduped),
        scenario=scenario,
        encounters=tuple(encounters),
        distance_disagreement=distance_disagreement,
        time_disagreement=time_disagreement,
        detail=detail,
    )
