"""The committed fixtures must hold their claims when rebuilt from disk.

These tests deliberately do not call the generator to produce the states they
check. They load the serialized JSON, rebuild trajectories from the stored
initial states, and recompute everything -- so a fixture whose recorded
evidence has drifted away from its own numbers fails here.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from backend.core.encounters import closest_encounter, find_encounters
from backend.core.trajectory import Trajectory
from backend.planning.candidates import generate_candidates
from backend.planning.search import (
    STATUS_NO_PRIMARY_QUALIFIED_OPTION,
    Policy,
    apply_candidate,
    evaluate_candidates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = REPO_ROOT / "scenarios" / "primary.json"
VARIANTS_DIR = REPO_ROOT / "scenarios" / "variants"

pytestmark = pytest.mark.skipif(
    not PRIMARY_PATH.exists(),
    reason="fixtures not generated; run `python scenarios/gen.py`",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def trajectories(document: dict) -> tuple[Trajectory, dict[str, Trajectory]]:
    """Rebuild from the serialized initial states, not from the generator."""
    satellite = None
    debris: dict[str, Trajectory] = {}
    for entry in document["objects"]:
        state = entry["initial_state"]
        trajectory = Trajectory.from_state(
            np.array(state["r_m"], dtype=np.float64),
            np.array(state["v_mps"], dtype=np.float64),
        )
        if entry["object_id"] == document["satellite_id"]:
            satellite = trajectory
        else:
            debris[entry["object_id"]] = trajectory
    assert satellite is not None
    return satellite, debris


def policy_from(document: dict) -> Policy:
    spec = document["default_policy"]
    return Policy(
        policy_version=spec["policy_version"],
        max_delta_v_mps=spec["max_delta_v_mps"],
        min_separation_m=spec["min_separation_m"],
    )


def closest(a: Trajectory, b: Trajectory, object_id: str, horizon_s: float):
    return closest_encounter(find_encounters(a, b, object_id, horizon_s, step_s=5.0))


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def all_fixture_paths() -> list[Path]:
    return [PRIMARY_PATH, *sorted(VARIANTS_DIR.glob("*.json"))]


@pytest.mark.parametrize("path", all_fixture_paths(), ids=lambda p: p.stem)
def test_fixture_shape_matches_the_contract(path):
    document = load(path)

    for field in (
        "schema_version", "scenario_id", "scenario_version", "seed", "epoch_utc",
        "horizon_s", "objects", "satellite_id", "primary_threat_id",
        "known_windows", "provenance", "input_hash",
    ):
        assert field in document, f"{path.name} missing {field}"

    assert len(document["objects"]) == 3
    ids = [o["object_id"] for o in document["objects"]]
    assert len(set(ids)) == 3
    assert document["satellite_id"] in ids
    assert document["primary_threat_id"] in ids
    assert document["primary_threat_id"] != document["satellite_id"]
    assert sum(o["maneuverable"] for o in document["objects"]) == 1

    for entry in document["objects"]:
        state = entry["initial_state"]
        assert len(state["r_m"]) == 3 and len(state["v_mps"]) == 3
        assert all(np.isfinite(state["r_m"])) and all(np.isfinite(state["v_mps"]))

    for window in document["known_windows"]:
        assert 0.0 <= window["start_s"] < window["end_s"] <= document["horizon_s"]


@pytest.mark.parametrize("path", all_fixture_paths(), ids=lambda p: p.stem)
def test_provenance_is_honest_about_what_is_real(path):
    provenance = load(path)["provenance"]
    assert provenance["synthetic_conjunction"] is True
    assert provenance["norad_id"] > 0
    assert provenance["tle_epoch_utc"]
    assert provenance["source_sha256"]
    assert provenance["frame"] == "SIM_ECI_TEME_SEEDED"


def test_seed_state_matches_the_committed_tle():
    """The satellite state must come from the TLE on disk, not a constant."""
    from scenarios.gen import load_seed_state

    document = load(PRIMARY_PATH)
    seed = load_seed_state()

    assert document["provenance"]["norad_id"] == seed.norad_id
    assert document["provenance"]["source_sha256"] == seed.tle_sha256

    satellite = next(
        o for o in document["objects"] if o["object_id"] == document["satellite_id"]
    )
    assert np.allclose(satellite["initial_state"]["r_m"], seed.r_m, rtol=0, atol=1e-6)
    assert np.allclose(satellite["initial_state"]["v_mps"], seed.v_mps, rtol=0, atol=1e-9)


# --------------------------------------------------------------------------
# The three facts the signature case claims
# --------------------------------------------------------------------------


def test_signature_case_holds_all_three_facts_when_rebuilt_from_disk():
    document = load(PRIMARY_PATH)
    satellite, debris = trajectories(document)
    policy = policy_from(document)
    horizon = document["horizon_s"]
    primary_id = document["primary_threat_id"]
    secondary_id = next(k for k in debris if k != primary_id)

    search = evaluate_candidates(
        satellite, debris[primary_id], primary_id, policy, horizon
    )

    # The case needs to be a real problem.
    assert not search.baseline.primary_qualified
    baseline_primary = search.baseline.primary_encounter
    assert baseline_primary.min_separation_m < policy.min_separation_m

    trap = search.best
    assert trap is not None and not trap.candidate.is_baseline

    trap_trajectory = apply_candidate(satellite, trap.candidate)
    baseline_vs_secondary = closest(satellite, debris[secondary_id], secondary_id, horizon)
    trap_vs_secondary = closest(trap_trajectory, debris[secondary_id], secondary_id, horizon)

    print(
        f"\n[signature] baseline {baseline_primary.min_separation_m:.1f} m vs "
        f"{primary_id} @ {baseline_primary.tca_s:.0f} s | "
        f"top option {trap.candidate.candidate_id} clears {primary_id} at "
        f"{trap.primary_encounter.min_separation_m:.1f} m but hits {secondary_id} at "
        f"{trap_vs_secondary.min_separation_m:.1f} m @ {trap_vs_secondary.tca_s:.0f} s | "
        f"baseline vs {secondary_id} {baseline_vs_secondary.min_separation_m:.1f} m"
    )

    # Fact 1 -- the second conflict is caused by the burn, not pre-existing.
    assert baseline_vs_secondary.min_separation_m >= policy.min_separation_m
    # Fact 2 -- the top-ranked option really is unsafe against the second object.
    assert trap.primary_encounter.min_separation_m >= policy.min_separation_m
    assert trap_vs_secondary.min_separation_m < policy.min_separation_m

    # Fact 3 -- a different option clears both, so the case has an answer.
    rescues = []
    for evaluation in search.qualified:
        if evaluation.candidate.is_baseline:
            continue
        if evaluation.candidate.candidate_id == trap.candidate.candidate_id:
            continue
        vs_secondary = closest(
            apply_candidate(satellite, evaluation.candidate),
            debris[secondary_id],
            secondary_id,
            horizon,
        )
        if vs_secondary and vs_secondary.min_separation_m >= policy.min_separation_m:
            rescues.append((evaluation.candidate.candidate_id, vs_secondary.min_separation_m))

    assert rescues, "no option clears both objects; the case has no answer"
    print(f"[signature] {len(rescues)} option(s) clear both, first is {rescues[0][0]}")


def test_recorded_evidence_matches_recomputation():
    """Stored generation evidence is provenance; it must agree with the code."""
    document = load(PRIMARY_PATH)
    evidence = document["generation_evidence"]
    satellite, debris = trajectories(document)
    policy = policy_from(document)
    horizon = document["horizon_s"]
    primary_id = document["primary_threat_id"]
    secondary_id = next(k for k in debris if k != primary_id)

    search = evaluate_candidates(
        satellite, debris[primary_id], primary_id, policy, horizon
    )

    assert search.candidate_count == evidence["candidate_count"]
    assert search.best.candidate.candidate_id == evidence["trap_candidate_id"]
    assert search.baseline.primary_encounter.min_separation_m == pytest.approx(
        evidence["baseline_vs_primary_m"], abs=1e-3
    )

    trap_vs_secondary = closest(
        apply_candidate(satellite, search.best.candidate),
        debris[secondary_id],
        secondary_id,
        horizon,
    )
    assert trap_vs_secondary.min_separation_m == pytest.approx(
        evidence["trap_vs_secondary_m"], abs=1e-3
    )


# --------------------------------------------------------------------------
# Variants
# --------------------------------------------------------------------------


def test_no_encounter_variant_leaves_the_baseline_acceptable():
    document = load(VARIANTS_DIR / "no_encounter.json")
    satellite, debris = trajectories(document)
    primary_id = document["primary_threat_id"]

    search = evaluate_candidates(
        satellite, debris[primary_id], primary_id, policy_from(document), document["horizon_s"]
    )
    assert search.baseline.primary_qualified


def test_simple_conflict_variant_has_an_unsafe_baseline_and_a_fix():
    document = load(VARIANTS_DIR / "simple_conflict.json")
    satellite, debris = trajectories(document)
    primary_id = document["primary_threat_id"]

    search = evaluate_candidates(
        satellite, debris[primary_id], primary_id, policy_from(document), document["horizon_s"]
    )
    assert not search.baseline.primary_qualified
    assert any(e for e in search.qualified if not e.candidate.is_baseline)


def test_no_feasible_variant_really_has_no_qualifying_option():
    document = load(VARIANTS_DIR / "no_feasible.json")
    satellite, debris = trajectories(document)
    primary_id = document["primary_threat_id"]

    search = evaluate_candidates(
        satellite, debris[primary_id], primary_id, policy_from(document), document["horizon_s"]
    )
    assert not search.baseline.primary_qualified
    assert not [e for e in search.qualified if not e.candidate.is_baseline]
    assert search.status == STATUS_NO_PRIMARY_QUALIFIED_OPTION

    # Widening the grid must not manufacture an answer here either.
    widened = evaluate_candidates(
        satellite,
        debris[primary_id],
        primary_id,
        policy_from(document),
        document["horizon_s"],
        candidates=generate_candidates(2),
    )
    print(
        f"\n[no_feasible] {search.candidate_count} options -> none qualify; "
        f"after widening to {widened.candidate_count}: "
        f"{len([e for e in widened.qualified if not e.candidate.is_baseline])} qualify"
    )


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_regeneration_is_deterministic():
    """The same seed must rebuild the same states, or the fixture is not reproducible."""
    from scenarios.gen import Policy as GenPolicy
    from scenarios.gen import build_signature_case, load_seed_state

    document = load(PRIMARY_PATH)
    rebuilt = build_signature_case(load_seed_state(), document["seed"], GenPolicy())

    for entry in document["objects"]:
        if entry["object_id"] == document["satellite_id"]:
            continue
        arc = rebuilt.debris[entry["object_id"]].arcs[0]
        assert np.allclose(entry["initial_state"]["r_m"], arc.r0_m, rtol=0, atol=1e-6)
        assert np.allclose(entry["initial_state"]["v_mps"], arc.v0_mps, rtol=0, atol=1e-9)

    assert rebuilt.evidence["trap_candidate_id"] == document["generation_evidence"]["trap_candidate_id"]
