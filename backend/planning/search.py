"""Primary-threat screening and ranking. Provisional results only.

This path answers one question: which options look acceptable against the
object that triggered the case. It deliberately does not screen the rest of the
catalogue, because the gap between "clears the primary threat" and "clears
everything" is the failure the verifier exists to catch.

Nothing here may be treated as approvable. Only
``backend/planning/verifier.py`` -- which rebuilds from raw scenario data and
runs its own detection -- can clear a proposal.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from backend.core.encounters import Encounter, closest_encounter, find_encounters
from backend.core.trajectory import Trajectory, impulse_vector
from backend.planning.candidates import (
    GRID_REVISION_BASE,
    Candidate,
    generate_candidates,
)

REASON_OK = "OK"
REASON_OVER_BUDGET = "OVER_BUDGET"
REASON_BURN_IN_BLOCKED_WINDOW = "BURN_IN_BLOCKED_WINDOW"
REASON_BELOW_CLEARANCE_FLOOR = "BELOW_CLEARANCE_FLOOR"
REASON_NO_ENCOUNTER_FOUND = "NO_ENCOUNTER_FOUND"

STATUS_OPTIONS_AVAILABLE = "OPTIONS_AVAILABLE"
STATUS_NO_PRIMARY_QUALIFIED_OPTION = "NO_PRIMARY_QUALIFIED_OPTION"


@dataclass(frozen=True)
class BurnWindow:
    """A closed interval during which burns are prohibited."""

    window_id: str
    label: str
    start_s: float
    end_s: float

    def contains(self, t_s: float) -> bool:
        return self.start_s <= t_s <= self.end_s


@dataclass(frozen=True)
class Policy:
    """Operator constraints. Mirrors Handoff/CONTRACTS.md."""

    policy_version: int = 1
    max_delta_v_mps: float = 0.20
    min_separation_m: float = 1000.0
    blocked_windows: tuple[BurnWindow, ...] = ()


@dataclass(frozen=True)
class CandidateEvaluation:
    """One option screened against the primary threat only.

    ``primary_qualified`` is not clearance. It means this option survived the
    primary screen and is worth validating.
    """

    candidate: Candidate
    primary_encounter: Encounter | None
    primary_qualified: bool
    reason_codes: tuple[str, ...]
    rank: int | None = None


@dataclass(frozen=True)
class SearchResult:
    grid_revision: int
    candidate_count: int
    baseline: CandidateEvaluation
    evaluations: tuple[CandidateEvaluation, ...]
    status: str

    @property
    def qualified(self) -> tuple[CandidateEvaluation, ...]:
        ranked = [e for e in self.evaluations if e.primary_qualified]
        return tuple(sorted(ranked, key=lambda e: e.rank if e.rank is not None else 1 << 30))

    @property
    def best(self) -> CandidateEvaluation | None:
        ranked = self.qualified
        return ranked[0] if ranked else None

    def by_id(self, candidate_id: str) -> CandidateEvaluation:
        for evaluation in self.evaluations:
            if evaluation.candidate.candidate_id == candidate_id:
                return evaluation
        raise KeyError(f"unknown candidate_id {candidate_id!r}")


def apply_candidate(satellite: Trajectory, candidate: Candidate) -> Trajectory:
    """The trajectory this option produces. Baseline returns the input unchanged.

    Direction resolves against the unburned velocity at the burn epoch, so this
    must be called on the pre-burn trajectory.
    """
    if candidate.is_baseline:
        return satellite
    if candidate.burn_t_s is None or candidate.direction is None:
        raise ValueError(f"impulse candidate {candidate.candidate_id} is missing burn fields")
    dv = impulse_vector(satellite, candidate.burn_t_s, candidate.direction, candidate.delta_v_mps)
    return satellite.apply_impulse(candidate.burn_t_s, dv)


def _policy_reasons(candidate: Candidate, policy: Policy) -> list[str]:
    reasons: list[str] = []
    if candidate.delta_v_mps > policy.max_delta_v_mps + 1e-12:
        reasons.append(REASON_OVER_BUDGET)
    if candidate.burn_t_s is not None:
        for window in policy.blocked_windows:
            if window.contains(candidate.burn_t_s):
                reasons.append(REASON_BURN_IN_BLOCKED_WINDOW)
                break
    return reasons


def evaluate_candidate(
    satellite: Trajectory,
    primary_threat: Trajectory,
    primary_threat_id: str,
    candidate: Candidate,
    policy: Policy,
    horizon_s: float,
    step_s: float = 5.0,
) -> CandidateEvaluation:
    """Screen one option against the primary threat and the policy."""
    reasons = _policy_reasons(candidate, policy)

    trajectory = apply_candidate(satellite, candidate)
    encounters = find_encounters(
        trajectory, primary_threat, primary_threat_id, horizon_s, step_s=step_s
    )
    primary = closest_encounter(encounters)

    if primary is None:
        reasons.append(REASON_NO_ENCOUNTER_FOUND)
    elif primary.min_separation_m < policy.min_separation_m:
        reasons.append(REASON_BELOW_CLEARANCE_FLOOR)

    qualified = not reasons
    return CandidateEvaluation(
        candidate=candidate,
        primary_encounter=primary,
        primary_qualified=qualified,
        reason_codes=tuple(reasons) if reasons else (REASON_OK,),
    )


def _rank_key(evaluation: CandidateEvaluation) -> tuple:
    """Least fuel, then most clearance, then earliest burn, then stable ID."""
    separation = (
        evaluation.primary_encounter.min_separation_m
        if evaluation.primary_encounter is not None
        else 0.0
    )
    burn_t = evaluation.candidate.burn_t_s
    return (
        evaluation.candidate.delta_v_mps,
        -separation,
        burn_t if burn_t is not None else -1.0,
        evaluation.candidate.candidate_id,
    )


def evaluate_candidates(
    satellite: Trajectory,
    primary_threat: Trajectory,
    primary_threat_id: str,
    policy: Policy,
    horizon_s: float,
    grid_revision: int = GRID_REVISION_BASE,
    step_s: float = 5.0,
    candidates: list[Candidate] | None = None,
) -> SearchResult:
    """Screen the whole grid. Excluded options stay visible with their reasons."""
    options = candidates if candidates is not None else generate_candidates(grid_revision)

    evaluations = [
        evaluate_candidate(
            satellite, primary_threat, primary_threat_id, candidate, policy, horizon_s, step_s
        )
        for candidate in options
    ]

    qualified = sorted(
        [e for e in evaluations if e.primary_qualified], key=_rank_key
    )
    ranks = {
        e.candidate.candidate_id: position for position, e in enumerate(qualified, start=1)
    }
    evaluations = [
        replace(e, rank=ranks.get(e.candidate.candidate_id)) for e in evaluations
    ]

    baseline = next(e for e in evaluations if e.candidate.is_baseline)

    # The baseline is a valid outcome when nothing needs doing, but it is not a
    # manoeuvre; "options available" means at least one burn qualified.
    burns_qualified = [e for e in evaluations if e.primary_qualified and not e.candidate.is_baseline]

    return SearchResult(
        grid_revision=grid_revision,
        candidate_count=len(options),
        baseline=baseline,
        evaluations=tuple(evaluations),
        status=(
            STATUS_OPTIONS_AVAILABLE
            if burns_qualified
            else STATUS_NO_PRIMARY_QUALIFIED_OPTION
        ),
    )
