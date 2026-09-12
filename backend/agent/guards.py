"""Checks on what the model says, separate from what the tools computed.

The structural rule is that the model never supplies a number: every figure the
UI or the report shows is read from a typed field. This module is the backstop
for prose -- if a rationale mentions a distance that does not appear in the
validated evidence, that is worth flagging.

It is a supplementary check, not a hallucination guarantee. It cannot catch a
wrong claim phrased without digits ("the manoeuvre clears every object"), and it
should never be described as if it could.
"""

from __future__ import annotations

import re
from typing import Iterable

# Numbers that are part of an identifier (t30_ret_100, DEB-1, gs_pass_1) are not
# claims about the world, so they are removed before scanning.
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+\b")
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.\-])(\d+(?:,\d{3})*(?:\.\d+)?)(?![A-Za-z0-9_])")

# Small whole numbers are counts, ranks and object indices rather than
# measurements. Kept deliberately narrow: allowing everything up to 100 would
# let an invented "50 m clearance" through unchallenged.
_ALWAYS_ALLOWED = {float(n) for n in range(0, 26)}


def numeric_literals(text: str) -> list[float]:
    """Numbers stated as measurements, with identifiers stripped out."""
    cleaned = _IDENTIFIER_RE.sub(" ", text or "")
    values: list[float] = []
    for match in _NUMBER_RE.finditer(cleaned):
        try:
            values.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return values


def supported_values(*sources: Iterable[float]) -> set[float]:
    """Collect the figures a rationale is allowed to quote."""
    allowed: set[float] = set()
    for source in sources:
        for value in source:
            if value is None:
                continue
            allowed.add(round(float(value), 6))
    return allowed


def unsupported_numbers(
    text: str,
    allowed: Iterable[float],
    relative_tolerance: float = 0.005,
) -> list[float]:
    """Numbers in ``text`` that match nothing in ``allowed``.

    A small tolerance absorbs ordinary rounding -- 523.2 for 523.17 is a
    thousandth of a percent. It is deliberately not generous: distances, times
    and speeds share one comparison set, so a loose tolerance lets an invented
    distance match an unrelated speed. Aggressive rounding such as "2.0 km" for
    2016.9 m will be flagged, which is the right trade when flagging is a note
    in the trace rather than a block.
    """
    reference = {round(float(v), 6) for v in allowed}
    scaled = {v / 1000.0 for v in reference} | {v * 1000.0 for v in reference}
    reference |= scaled

    flagged: list[float] = []
    for value in numeric_literals(text):
        if value.is_integer() and value in _ALWAYS_ALLOWED:
            continue
        if any(
            abs(value - candidate) <= max(relative_tolerance * abs(candidate), 1e-6)
            for candidate in reference
        ):
            continue
        flagged.append(value)
    return flagged


def values_from_validation(validation) -> set[float]:
    """Every figure a rationale may legitimately quote from one validation."""
    values: list[float] = []
    for encounter in validation.encounters:
        values.extend(
            [encounter.min_separation_m, encounter.tca_s, encounter.relative_speed_mps]
        )
    if validation.max_primary_distance_disagreement_m is not None:
        values.append(validation.max_primary_distance_disagreement_m)
    if validation.primary_time_disagreement_s is not None:
        values.append(validation.primary_time_disagreement_s)
    values.append(validation.horizon_s)
    values.append(validation.sample_step_s)
    return supported_values(values)


def values_from_shortfalls(validation, policy) -> set[float]:
    """How far each violating encounter fell below the floor.

    Surfaced to the planner in `blocked_by`, so a rationale that explains a
    rejection legitimately quotes it. Derived rather than stored, which is why
    it needs its own helper.
    """
    return supported_values(
        policy.min_separation_m - e.min_separation_m
        for e in validation.encounters
        if e.min_separation_m < policy.min_separation_m
    )


def values_from_policy(policy) -> set[float]:
    return supported_values(
        [policy.max_delta_v_mps, policy.min_separation_m]
        + [w.start_s for w in policy.blocked_windows]
        + [w.end_s for w in policy.blocked_windows]
    )


def values_from_candidate(candidate) -> set[float]:
    values = [candidate.delta_v_mps]
    if candidate.burn_t_s is not None:
        values.append(candidate.burn_t_s)
        values.append(candidate.burn_t_s / 60.0)
    return supported_values(values)
