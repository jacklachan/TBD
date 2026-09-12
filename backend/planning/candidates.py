"""The finite manoeuvre grid.

Twenty-four burns plus a no-burn baseline is twenty-five options, not
twenty-five burns; the count the UI shows must be the count that was evaluated.
One bounded expansion adds smaller magnitudes at the same times and directions,
taking the total to thirty-three. Expansion never relaxes policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

KIND_NO_BURN = "NO_BURN"
KIND_IMPULSE = "IMPULSE"

DIRECTION_PROGRADE = "PROGRADE"
DIRECTION_RETROGRADE = "RETROGRADE"

BASELINE_ID = "baseline"

BURN_TIMES_S: tuple[float, ...] = (900.0, 1800.0, 2700.0, 3600.0)
DIRECTIONS: tuple[str, ...] = (DIRECTION_PROGRADE, DIRECTION_RETROGRADE)
BASE_MAGNITUDES_MPS: tuple[float, ...] = (0.05, 0.10, 0.20)
EXPANSION_MAGNITUDES_MPS: tuple[float, ...] = (0.025,)

GRID_REVISION_BASE = 1
GRID_REVISION_EXPANDED = 2

_DIRECTION_SLUG = {DIRECTION_PROGRADE: "pro", DIRECTION_RETROGRADE: "ret"}


@dataclass(frozen=True)
class Candidate:
    """One option. Field names mirror Handoff/CONTRACTS.md."""

    candidate_id: str
    kind: str
    delta_v_mps: float
    grid_revision: int
    burn_t_s: float | None = None
    direction: str | None = None

    @property
    def is_baseline(self) -> bool:
        return self.kind == KIND_NO_BURN


def candidate_id_for(burn_t_s: float, direction: str, delta_v_mps: float) -> str:
    """Stable ID: burn minute, direction, magnitude in millimetres per second.

    Stability matters because IDs appear in evidence, in the agent's tool
    arguments and in exported reports. Changing this format invalidates stored
    cases.
    """
    minutes = int(round(burn_t_s / 60.0))
    milli = int(round(delta_v_mps * 1000.0))
    return f"t{minutes:02d}_{_DIRECTION_SLUG[direction]}_{milli:03d}"


def baseline_candidate(grid_revision: int = GRID_REVISION_BASE) -> Candidate:
    return Candidate(
        candidate_id=BASELINE_ID,
        kind=KIND_NO_BURN,
        delta_v_mps=0.0,
        grid_revision=grid_revision,
    )


def generate_candidates(grid_revision: int = GRID_REVISION_BASE) -> list[Candidate]:
    """The option set for a grid revision, baseline first.

    Revision 1 is 25 options. Revision 2 adds the smaller magnitudes for 33.
    """
    if grid_revision not in (GRID_REVISION_BASE, GRID_REVISION_EXPANDED):
        raise ValueError(f"unsupported grid_revision {grid_revision}")

    magnitudes = list(BASE_MAGNITUDES_MPS)
    if grid_revision == GRID_REVISION_EXPANDED:
        magnitudes.extend(EXPANSION_MAGNITUDES_MPS)

    options = [baseline_candidate(grid_revision)]
    for burn_t_s in BURN_TIMES_S:
        for direction in DIRECTIONS:
            for delta_v_mps in magnitudes:
                options.append(
                    Candidate(
                        candidate_id=candidate_id_for(burn_t_s, direction, delta_v_mps),
                        kind=KIND_IMPULSE,
                        delta_v_mps=delta_v_mps,
                        grid_revision=grid_revision,
                        burn_t_s=burn_t_s,
                        direction=direction,
                    )
                )
    return options


def expansion_candidates() -> list[Candidate]:
    """Only the options revision 2 adds, for reporting what widening produced."""
    base_ids = {c.candidate_id for c in generate_candidates(GRID_REVISION_BASE)}
    return [
        c
        for c in generate_candidates(GRID_REVISION_EXPANDED)
        if c.candidate_id not in base_ids
    ]


# --------------------------------------------------------------------------
# Designed burns
#
# A burn the planner specified itself is not in any grid, so it cannot be found
# by enumeration. Its ID carries the whole design instead -- time in seconds,
# direction, magnitude in millimetres per second -- which is what lets the API
# reconstruct one for visualisation without a schema change and without the
# request being trusted to describe it.
# --------------------------------------------------------------------------

DESIGNED_PREFIX = "free_"
_DESIGNED_ID = re.compile(
    rf"^{DESIGNED_PREFIX}t(?P<seconds>\d{{1,7}})s_(?P<slug>pro|ret)_(?P<milli>\d{{1,6}})$"
)
_SLUG_DIRECTION = {slug: name for name, slug in _DIRECTION_SLUG.items()}


def designed_candidate_id(burn_t_s: float, direction: str, delta_v_mps: float) -> str:
    return (
        f"{DESIGNED_PREFIX}t{int(round(burn_t_s))}s_"
        f"{_DIRECTION_SLUG[direction]}_{int(round(delta_v_mps * 1000.0)):03d}"
    )


def candidate_from_id(candidate_id: str, grid_revision: int) -> Candidate | None:
    """Resolve an option ID, from the grid or from a designed burn.

    Returns None for anything that is neither, so callers keep reporting an
    unknown ID as unknown rather than propagating whatever was asked for.
    """
    for candidate in generate_candidates(grid_revision):
        if candidate.candidate_id == candidate_id:
            return candidate

    match = _DESIGNED_ID.match(candidate_id or "")
    if match is None:
        return None
    return Candidate(
        candidate_id=candidate_id,
        kind=KIND_IMPULSE,
        delta_v_mps=int(match.group("milli")) / 1000.0,
        grid_revision=grid_revision,
        burn_t_s=float(match.group("seconds")),
        direction=_SLUG_DIRECTION[match.group("slug")],
    )
