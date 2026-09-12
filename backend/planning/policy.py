"""Operator constraints, in a module both the search and the verifier may import.

These types live here rather than in ``search.py`` so that ``verifier.py`` can
read the active policy without importing the search path it is supposed to be
independent of. Field names mirror Handoff/CONTRACTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    policy_version: int = 1
    max_delta_v_mps: float = 0.20
    min_separation_m: float = 1000.0
    blocked_windows: tuple[BurnWindow, ...] = ()


def policy_from_document(document: dict, policy_version: int | None = None) -> Policy:
    """Build the default policy carried by a scenario fixture."""
    spec = document["default_policy"]
    windows = tuple(
        BurnWindow(
            window_id=w["window_id"],
            label=w["label"],
            start_s=float(w["start_s"]),
            end_s=float(w["end_s"]),
        )
        for w in spec.get("blocked_windows", ())
    )
    return Policy(
        policy_version=policy_version if policy_version is not None else int(spec["policy_version"]),
        max_delta_v_mps=float(spec["max_delta_v_mps"]),
        min_separation_m=float(spec["min_separation_m"]),
        blocked_windows=windows,
    )
