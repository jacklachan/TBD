"""The verifier must be independent, must agree, and must block.

The important test here is not that the verifier passes good candidates -- it is
that it independently rejects the option the search ranks first, using its own
reconstruction and its own detection method.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from backend.planning.candidates import (
    KIND_IMPULSE,
    Candidate,
    baseline_candidate,
    generate_candidates,
)
from backend.planning.policy import BurnWindow, Policy, policy_from_document
from backend.planning.search import apply_candidate, evaluate_candidates
from backend.planning.verifier import (
    AGREEMENT_DISTANCE_TOL_M,
    AGREEMENT_TIME_TOL_S,
    REASON_BELOW_CLEARANCE_FLOOR,
    REASON_BURN_IN_BLOCKED_WINDOW,
    REASON_BURN_OUTSIDE_HORIZON,
    REASON_CANDIDATE_INVALID,
    REASON_OVER_BUDGET,
    REASON_SCENARIO_INVALID,
    REASON_SEARCH_DISAGREEMENT,
    REASON_VERSION_MISMATCH,
    STATUS_BLOCK,
    STATUS_ERROR,
    STATUS_PASS,
    reconstruct,
    screen_pair,
    validate_candidate,
)
from backend.core.trajectory import Trajectory

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = REPO_ROOT / "scenarios" / "primary.json"
VARIANTS_DIR = REPO_ROOT / "scenarios" / "variants"
VERIFIER_SOURCE = REPO_ROOT / "backend" / "planning" / "verifier.py"

pytestmark = pytest.mark.skipif(
    not PRIMARY_PATH.exists(),
    reason="fixtures not generated; run `python scenarios/gen.py`",
)


@pytest.fixture(scope="module")
def primary_document() -> dict:
    return json.loads(PRIMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def primary_policy(primary_document) -> Policy:
    return policy_from_document(primary_document)


@pytest.fixture(scope="module")
def primary_search(primary_document, primary_policy):
    scenario = reconstruct(primary_document)
    return scenario, evaluate_candidates(
        scenario.satellite,
        scenario.debris[scenario.primary_threat_id],
        scenario.primary_threat_id,
        primary_policy,
        scenario.horizon_s,
    )


# --------------------------------------------------------------------------
# Independence, checked structurally rather than asserted in prose
# --------------------------------------------------------------------------


def test_verifier_does_not_import_the_search_path():
    """A future refactor that quietly wires these together fails here."""
    tree = ast.parse(VERIFIER_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "backend.planning.search" not in imported, (
        "verifier imports the search path; its result would no longer be independent"
    )
    assert "backend.core.encounters" not in imported, (
        "verifier imports the search encounter detector; it must implement its own"
    )
    # The shared physics primitives are permitted and disclosed.
    assert "backend.core.trajectory" in imported


def test_verifier_and_search_agree_on_the_primary_encounter(primary_document, primary_policy, primary_search):
    """Two sampling rates, two numerical methods, one answer."""
    scenario, search = primary_search
    checked = 0
    worst_distance = 0.0
    worst_time = 0.0

    for evaluation in list(search.qualified)[:6]:
        result = validate_candidate(
            primary_document,
            primary_policy,
            evaluation.candidate,
            expected_primary_encounter={
                "min_separation_m": evaluation.primary_encounter.min_separation_m,
                "tca_s": evaluation.primary_encounter.tca_s,
            },
        )
        assert REASON_SEARCH_DISAGREEMENT not in result.reason_codes, result.detail
        worst_distance = max(worst_distance, result.max_primary_distance_disagreement_m)
        worst_time = max(worst_time, result.primary_time_disagreement_s)
        checked += 1

    print(
        f"\n[agreement] {checked} candidates, 5 s Newton-on-range-rate vs 1 s "
        f"bounded-minimisation: worst distance disagreement {worst_distance:.3e} m "
        f"(tol {AGREEMENT_DISTANCE_TOL_M}), worst time {worst_time:.3e} s "
        f"(tol {AGREEMENT_TIME_TOL_S})"
    )
    assert worst_distance <= AGREEMENT_DISTANCE_TOL_M
    assert worst_time <= AGREEMENT_TIME_TOL_S


# --------------------------------------------------------------------------
# The behaviour the whole product exists for
# --------------------------------------------------------------------------


def test_top_ranked_option_passes_the_search_but_is_blocked_by_the_verifier(
    primary_document, primary_policy, primary_search
):
    scenario, search = primary_search
    trap = search.best
    assert trap is not None and trap.primary_qualified

    result = validate_candidate(primary_document, primary_policy, trap.candidate)

    secondary = [
        e for e in result.encounters if e.other_object_id != scenario.primary_threat_id
    ]
    print(
        f"\n[veto] search ranks {trap.candidate.candidate_id} first "
        f"({trap.primary_encounter.min_separation_m:.1f} m vs "
        f"{scenario.primary_threat_id}); verifier screened "
        f"{list(result.evaluated_object_ids)} and returned {result.status} "
        f"-- {secondary[0].other_object_id} at {secondary[0].min_separation_m:.1f} m "
        f"@ {secondary[0].tca_s:.0f} s"
    )

    assert result.status == STATUS_BLOCK
    assert REASON_BELOW_CLEARANCE_FLOOR in result.reason_codes
    assert not result.approvable
    assert len(result.evaluated_object_ids) == len(scenario.debris)
    assert result.detail["violating_objects"][0]["object_id"] != scenario.primary_threat_id


def test_an_alternative_option_passes_full_validation(
    primary_document, primary_policy, primary_search
):
    scenario, search = primary_search
    trap_id = search.best.candidate.candidate_id

    passed = []
    for evaluation in search.qualified:
        if evaluation.candidate.candidate_id == trap_id or evaluation.candidate.is_baseline:
            continue
        result = validate_candidate(primary_document, primary_policy, evaluation.candidate)
        if result.status == STATUS_PASS:
            passed.append((evaluation.candidate.candidate_id, result))
        if len(passed) >= 1:
            break

    assert passed, "no option cleared full validation; the case has no answer"
    candidate_id, result = passed[0]
    closest = result.closest()
    print(
        f"\n[approvable] {candidate_id} PASSES -- closest of any object "
        f"{closest.min_separation_m:.1f} m ({closest.other_object_id})"
    )
    assert result.approvable
    assert closest.min_separation_m >= primary_policy.min_separation_m


def test_baseline_is_blocked_in_the_signature_case(primary_document, primary_policy):
    result = validate_candidate(primary_document, primary_policy, baseline_candidate())
    assert result.status == STATUS_BLOCK
    assert REASON_BELOW_CLEARANCE_FLOOR in result.reason_codes


def test_baseline_passes_when_there_is_no_actionable_encounter(primary_policy):
    document = json.loads((VARIANTS_DIR / "no_encounter.json").read_text(encoding="utf-8"))
    result = validate_candidate(document, policy_from_document(document), baseline_candidate())
    print(f"\n[no_encounter] baseline -> {result.status}, closest {result.closest().min_separation_m:.0f} m")
    assert result.status == STATUS_PASS


def test_no_option_passes_validation_in_the_infeasible_variant():
    document = json.loads((VARIANTS_DIR / "no_feasible.json").read_text(encoding="utf-8"))
    policy = policy_from_document(document)

    approvable = [
        c.candidate_id
        for c in generate_candidates(2)
        if validate_candidate(document, policy, c).status == STATUS_PASS
    ]
    print(f"\n[no_feasible] approvable options across the widened grid: {len(approvable)}")
    assert not approvable


# --------------------------------------------------------------------------
# Policy is re-checked, not trusted
# --------------------------------------------------------------------------


def test_over_budget_candidate_is_blocked(primary_document):
    tight = Policy(policy_version=2, max_delta_v_mps=0.05, min_separation_m=1000.0)
    candidate = Candidate(
        candidate_id="t30_ret_200",
        kind=KIND_IMPULSE,
        delta_v_mps=0.20,
        grid_revision=1,
        burn_t_s=1800.0,
        direction="RETROGRADE",
    )
    result = validate_candidate(primary_document, tight, candidate)
    assert result.status == STATUS_BLOCK
    assert REASON_OVER_BUDGET in result.reason_codes


def test_burn_inside_a_blocked_window_is_blocked(primary_document):
    policy = Policy(
        policy_version=3,
        max_delta_v_mps=0.20,
        min_separation_m=1000.0,
        blocked_windows=(BurnWindow("gs_pass_1", "Ground station pass", 1700.0, 1900.0),),
    )
    candidate = Candidate(
        candidate_id="t30_ret_100",
        kind=KIND_IMPULSE,
        delta_v_mps=0.10,
        grid_revision=1,
        burn_t_s=1800.0,
        direction="RETROGRADE",
    )
    result = validate_candidate(primary_document, policy, candidate)
    assert result.status == STATUS_BLOCK
    assert REASON_BURN_IN_BLOCKED_WINDOW in result.reason_codes


def test_burn_beyond_the_horizon_is_rejected(primary_document, primary_policy):
    candidate = Candidate(
        candidate_id="t999_pro_100",
        kind=KIND_IMPULSE,
        delta_v_mps=0.10,
        grid_revision=1,
        burn_t_s=99_999.0,
        direction="PROGRADE",
    )
    result = validate_candidate(primary_document, primary_policy, candidate)
    assert result.status == STATUS_ERROR
    assert REASON_BURN_OUTSIDE_HORIZON in result.reason_codes


def test_malformed_candidate_is_rejected(primary_document, primary_policy):
    """An impulse with no burn fields cannot be silently treated as a baseline."""
    candidate = Candidate(
        candidate_id="broken", kind=KIND_IMPULSE, delta_v_mps=0.10, grid_revision=1
    )
    result = validate_candidate(primary_document, primary_policy, candidate)
    assert result.status == STATUS_ERROR
    assert REASON_CANDIDATE_INVALID in result.reason_codes


# --------------------------------------------------------------------------
# Stale versions, bad input, and injected agreement
# --------------------------------------------------------------------------


def test_stale_scenario_version_blocks(primary_document, primary_policy):
    result = validate_candidate(
        primary_document,
        primary_policy,
        baseline_candidate(),
        expected_scenario_version=primary_document["scenario_version"] + 1,
    )
    assert result.status == STATUS_BLOCK
    assert REASON_VERSION_MISMATCH in result.reason_codes


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d.pop("objects"), id="no_objects"),
        pytest.param(lambda d: d.update(satellite_id="MISSING"), id="unknown_satellite"),
        pytest.param(lambda d: d.update(primary_threat_id="MISSING"), id="unknown_threat"),
        pytest.param(lambda d: d.update(horizon_s=-1.0), id="negative_horizon"),
        pytest.param(
            lambda d: d["objects"][0]["initial_state"].update(r_m=[1.0, 2.0]),
            id="short_vector",
        ),
        pytest.param(
            lambda d: d["objects"][1]["initial_state"].update(v_mps=[0.0, float("nan"), 0.0]),
            id="nan_velocity",
        ),
    ],
)
def test_malformed_scenario_is_an_error_not_a_pass(primary_document, primary_policy, mutate):
    document = json.loads(json.dumps(primary_document))
    mutate(document)
    result = validate_candidate(document, primary_policy, baseline_candidate())
    assert result.status == STATUS_ERROR
    assert REASON_SCENARIO_INVALID in result.reason_codes
    assert not result.approvable


def test_a_fabricated_search_result_is_caught(primary_document, primary_policy, primary_search):
    """The verifier compares against the search; it never adopts its numbers."""
    _, search = primary_search
    result = validate_candidate(
        primary_document,
        primary_policy,
        search.best.candidate,
        expected_primary_encounter={"min_separation_m": 99_000.0, "tca_s": 100.0},
    )
    assert REASON_SEARCH_DISAGREEMENT in result.reason_codes
    assert result.status == STATUS_BLOCK
    assert result.max_primary_distance_disagreement_m > AGREEMENT_DISTANCE_TOL_M
    print(
        f"\n[fabricated] claimed 99000.0 m, verifier measured "
        f"{99_000.0 - result.max_primary_distance_disagreement_m:.1f} m -> BLOCK"
    )


# --------------------------------------------------------------------------
# Screening internals
# --------------------------------------------------------------------------


def test_screen_pair_finds_the_same_minimum_at_two_sampling_rates(primary_document):
    scenario = reconstruct(primary_document)
    debris_id = scenario.primary_threat_id
    fine = screen_pair(
        scenario.satellite, scenario.debris[debris_id], debris_id, scenario.horizon_s, step_s=1.0
    )
    coarse = screen_pair(
        scenario.satellite, scenario.debris[debris_id], debris_id, scenario.horizon_s, step_s=4.0
    )
    print(
        f"\n[screen] 1 s {fine.min_separation_m:.6f} m @ {fine.tca_s:.6f} s vs "
        f"4 s {coarse.min_separation_m:.6f} m @ {coarse.tca_s:.6f} s "
        f"(delta {abs(fine.min_separation_m - coarse.min_separation_m):.3e} m, "
        f"{abs(fine.tca_s - coarse.tca_s):.3e} s)"
    )
    assert abs(fine.min_separation_m - coarse.min_separation_m) < AGREEMENT_DISTANCE_TOL_M
    assert abs(fine.tca_s - coarse.tca_s) < AGREEMENT_TIME_TOL_S


def test_validation_result_carries_its_version_stamp_and_method(primary_document, primary_policy):
    result = validate_candidate(primary_document, primary_policy, baseline_candidate())
    assert result.scenario_id == primary_document["scenario_id"]
    assert result.scenario_version == primary_document["scenario_version"]
    assert result.policy_version == primary_policy.policy_version
    assert result.validation_id.startswith("val_")
    assert result.sample_step_s == 1.0
    assert result.method == "scan_1s_bounded_min_squared_distance"
    assert result.computed_at_utc.endswith("+00:00")


def test_a_strong_burn_can_make_a_pre_burn_encounter_the_binding_one(
    primary_document, primary_policy, primary_search
):
    """Two candidates reporting the same separation is correct, not a bug.

    The reported figure is the closest approach over the whole horizon. A large
    burn pushes the constructed conjunction far enough away that some earlier
    crossing -- on the arc before the burn, which every candidate shares with
    the baseline -- becomes the binding one. Candidates with different burn
    times then report identical values, because the encounter that limits them
    happens before either burn and no manoeuvre can change it.

    This matters for the chart: the annotated dip is not always the headline
    conjunction, so the label must name the time and object it actually found.
    """
    scenario, search = primary_search
    strong = [
        e
        for e in search.qualified
        if not e.candidate.is_baseline and e.candidate.delta_v_mps >= 0.20
    ]
    if len(strong) < 2:
        pytest.skip("fixture has fewer than two maximum-magnitude qualified options")

    first, second = strong[0], strong[1]
    assert first.candidate.burn_t_s != second.candidate.burn_t_s

    binding_t = first.primary_encounter.tca_s
    print(
        f"\n[binding] {first.candidate.candidate_id} (burn "
        f"{first.candidate.burn_t_s:.0f} s) and {second.candidate.candidate_id} "
        f"(burn {second.candidate.burn_t_s:.0f} s) both report "
        f"{first.primary_encounter.min_separation_m:.4f} m @ {binding_t:.1f} s"
    )

    # The binding encounter precedes both burns, which is why the values match.
    assert binding_t < first.candidate.burn_t_s
    assert binding_t < second.candidate.burn_t_s
    assert first.primary_encounter.min_separation_m == pytest.approx(
        second.primary_encounter.min_separation_m, abs=1e-6
    )

    # And it is the same encounter the untouched baseline sees on that arc.
    baseline_at_same_time = screen_pair(
        scenario.satellite,
        scenario.debris[scenario.primary_threat_id],
        scenario.primary_threat_id,
        binding_t + 1.0,
    )
    assert baseline_at_same_time.tca_s == pytest.approx(binding_t, abs=1e-3)
    assert baseline_at_same_time.min_separation_m == pytest.approx(
        first.primary_encounter.min_separation_m, abs=AGREEMENT_DISTANCE_TOL_M
    )

    # The verifier independently reproduces it.
    result = validate_candidate(primary_document, primary_policy, first.candidate)
    primary = next(
        e for e in result.encounters if e.other_object_id == scenario.primary_threat_id
    )
    assert primary.tca_s == pytest.approx(binding_t, abs=AGREEMENT_TIME_TOL_S)


def test_screening_partitions_at_every_burn_epoch_not_only_the_satellite_s():
    """Velocity is discontinuous at any burn, whichever object performs it.

    Debris is ballistic in every current scenario, so this is a latent case --
    but the module documents that it partitions at every impulse epoch, and a
    bracket straddling one refines against a velocity that changes mid-interval.
    """
    from backend.core.trajectory import impulse_vector
    from backend.planning.verifier import _segment_edges

    document = json.loads(PRIMARY_PATH.read_text(encoding="utf-8"))
    scenario = reconstruct(document)
    horizon = scenario.horizon_s

    satellite = scenario.satellite.apply_impulse(
        1800.0, impulse_vector(scenario.satellite, 1800.0, "RETROGRADE", 0.10)
    )
    debris = scenario.debris[scenario.primary_threat_id]
    manoeuvring_debris = debris.apply_impulse(
        9000.0, impulse_vector(debris, 9000.0, "PROGRADE", 0.10)
    )

    edges = _segment_edges((satellite, manoeuvring_debris), horizon)
    assert edges == [0.0, 1800.0, 9000.0, horizon]

    # And the screen still returns a usable result across the extra partition.
    found = screen_pair(satellite, manoeuvring_debris, "DEB-1", horizon)
    assert found is not None and found.min_separation_m > 0.0
