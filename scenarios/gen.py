"""Seeded backward construction of the scenario fixtures.

The satellite starts from the committed real TLE. Both debris objects are
synthetic and built backward from an encounter we specify, then checked by
propagating forward again -- so the expected values are derived, never asserted
from a previous run.

The signature case needs three facts to hold at once, and they are *searched
for*, not hand-tuned: the baseline must clear the second object, the
highest-ranked option against the primary threat must violate the floor against
the second object, and some other option must clear both. If the search cannot
satisfy all three it fails loudly rather than emitting a fixture that only
looks right.

    python scenarios/gen.py            # write scenarios/primary.json + variants
    python scenarios/gen.py --check    # regenerate and verify, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.encounters import closest_encounter, find_encounters  # noqa: E402
from backend.core.kepler import (  # noqa: E402
    EARTH_RADIUS_M,
    MU_M3_S2,
    propagate,
)
from backend.core.trajectory import Trajectory  # noqa: E402
from backend.planning.search import (  # noqa: E402
    BurnWindow,
    Policy,
    apply_candidate,
    evaluate_candidates,
)

SCHEMA_VERSION = 1
HORIZON_S = 21600.0
FRAME = "SIM_ECI_TEME_SEEDED"
MODEL_VERSION = "two-body-universal-variable-1"

PRIMARY_TCA_TARGET_S = 16200.0
SECONDARY_TCA_TARGET_S = 19800.0

TLE_PATH = REPO_ROOT / "scenarios" / "seed_tle.txt"
TLE_PROVENANCE_PATH = REPO_ROOT / "scenarios" / "seed_provenance.json"
OUTPUT_DIR = REPO_ROOT / "scenarios"

MAX_ATTEMPTS = 200
REPRODUCTION_TOLERANCE_M = 1.0

# The baseline must be comfortably clear of the second object, not marginally
# clear, so that the secondary conflict is unambiguously caused by the burn.
SECONDARY_CLEAR_MARGIN = 3.0
REPRODUCTION_TOLERANCE_S = 0.01

# A named window the operator can block, overlapping one grid burn epoch so the
# constraint actually excludes options rather than being decorative.
GROUND_STATION_WINDOW = BurnWindow(
    window_id="gs_pass_1",
    label="Ground station pass",
    start_s=1700.0,
    end_s=1900.0,
)


class GenerationError(RuntimeError):
    """Raised when a fixture cannot be built to satisfy its own assertions."""


# --------------------------------------------------------------------------
# Seed state from the committed TLE
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedState:
    norad_id: int
    object_name: str
    epoch_utc: datetime
    r_m: np.ndarray
    v_mps: np.ndarray
    tle_sha256: str


def load_seed_state() -> SeedState:
    """Read the committed TLE and evaluate SGP4 once, at the TLE's own epoch.

    Identity and epoch come out of the file. Nothing downstream hardcodes them;
    replacing the snapshot changes the scenario without a code edit.
    """
    from sgp4.api import Satrec  # imported here so core/ stays dependency-free

    if not TLE_PATH.exists():
        raise GenerationError(
            f"{TLE_PATH.relative_to(REPO_ROOT)} missing -- run "
            "`python scripts/fetch_snapshots.py --tle` once and commit it"
        )

    text = TLE_PATH.read_text(encoding="utf-8")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) != 3:
        raise GenerationError(f"expected 3 TLE lines, found {len(lines)}")

    name, line1, line2 = lines
    satrec = Satrec.twoline2rv(line1, line2)
    error, r_km, v_kms = satrec.sgp4(satrec.jdsatepoch, satrec.jdsatepochF)
    if error != 0:
        raise GenerationError(f"SGP4 returned error code {error} at the TLE epoch")

    # Julian date -> UTC. The TLE epoch is the scenario epoch.
    jd_total = satrec.jdsatepoch + satrec.jdsatepochF
    epoch = datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(
        days=jd_total - 2400000.5
    )

    return SeedState(
        norad_id=int(line1[2:7]),
        object_name=name.strip(),
        epoch_utc=epoch,
        r_m=np.array(r_km, dtype=np.float64) * 1000.0,
        v_mps=np.array(v_kms, dtype=np.float64) * 1000.0,
        tle_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


# --------------------------------------------------------------------------
# Backward construction
# --------------------------------------------------------------------------


def _rotate(vector: np.ndarray, axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rodrigues rotation of ``vector`` about a unit ``axis``."""
    axis = axis / np.linalg.norm(axis)
    return (
        vector * np.cos(angle_rad)
        + np.cross(axis, vector) * np.sin(angle_rad)
        + axis * (axis @ vector) * (1.0 - np.cos(angle_rad))
    )


def orbit_elements(r_m: np.ndarray, v_mps: np.ndarray) -> dict[str, float]:
    r_norm = float(np.linalg.norm(r_m))
    alpha = 2.0 / r_norm - float(v_mps @ v_mps) / MU_M3_S2
    h = np.cross(r_m, v_mps)
    e_vec = np.cross(v_mps, h) / MU_M3_S2 - r_m / r_norm
    eccentricity = float(np.linalg.norm(e_vec))
    semi_major = float("inf") if abs(alpha) < 1e-15 else 1.0 / alpha
    return {
        "semi_major_axis_m": semi_major,
        "eccentricity": eccentricity,
        "perigee_altitude_m": semi_major * (1.0 - eccentricity) - EARTH_RADIUS_M,
        "inclination_deg": float(
            np.degrees(np.arccos(np.clip(h[2] / np.linalg.norm(h), -1.0, 1.0)))
        ),
    }


def is_supported_orbit(r_m: np.ndarray, v_mps: np.ndarray) -> bool:
    """Bound, near-circular, comfortably above the atmosphere."""
    elements = orbit_elements(r_m, v_mps)
    return (
        np.isfinite(elements["semi_major_axis_m"])
        and elements["semi_major_axis_m"] > 0.0
        and elements["eccentricity"] < 0.05
        and elements["perigee_altitude_m"] > 200_000.0
    )


def construct_debris(
    target: Trajectory,
    t_ca_s: float,
    miss_m: float,
    relative_speed_mps: float,
    roll_rad: float,
) -> Trajectory:
    """Debris whose closest approach to ``target`` is ``miss_m`` at ``t_ca_s``.

    The debris velocity is the target velocity *rotated*, not the target
    velocity plus a perpendicular kick. Rotating preserves speed, so the debris
    stays bound and near-circular even at realistic crossing speeds of several
    kilometres per second; adding a perpendicular component would push it past
    escape velocity long before then.

    Rotating about the offset direction also puts the relative velocity in the
    plane perpendicular to that offset, which makes the range rate exactly zero
    at ``t_ca_s`` -- so the encounter time and miss distance are known
    independently of the detector.
    """
    r_t, v_t = target.states_at(np.array([t_ca_s]))
    r_t, v_t = r_t[0], v_t[0]

    speed = float(np.linalg.norm(v_t))
    if relative_speed_mps >= 2.0 * speed:
        raise GenerationError(
            f"relative speed {relative_speed_mps:.0f} m/s is unreachable from a "
            f"co-altitude orbit at {speed:.0f} m/s"
        )

    # Rotate about the radial direction, which is a pure plane change: the
    # velocity stays perpendicular to radial, so no radial speed is introduced
    # and the debris eccentricity stays close to the satellite's. Rotating
    # about the orbit normal instead would add |v|*sin(theta) of radial
    # velocity and produce a wildly eccentric orbit at realistic crossing
    # angles.
    radial = r_t / np.linalg.norm(r_t)
    radial = radial - (radial @ v_t) / (v_t @ v_t) * v_t
    radial = radial / np.linalg.norm(radial)

    # |v_rel| = 2 * v * sin(theta / 2) for a pure rotation through theta.
    theta = 2.0 * np.arcsin(relative_speed_mps / (2.0 * speed))
    v_d = _rotate(v_t, radial, theta)

    relative_velocity = v_d - v_t
    rel_norm = float(np.linalg.norm(relative_velocity))
    if rel_norm <= 0.0:
        raise GenerationError("degenerate relative velocity")

    # Any direction in the plane spanned by these two is perpendicular to the
    # relative velocity, which is what makes the range rate exactly zero here.
    # The roll picks one, for geometric variety across attempts.
    lateral = np.cross(relative_velocity / rel_norm, radial)
    lateral = lateral / np.linalg.norm(lateral)
    offset_dir = np.cos(roll_rad) * radial + np.sin(roll_rad) * lateral
    offset_dir = offset_dir / np.linalg.norm(offset_dir)

    r_d = r_t + offset_dir * miss_m

    if not is_supported_orbit(r_d, v_d):
        raise GenerationError("constructed debris orbit is outside the supported family")

    r_epoch, v_epoch = propagate(r_d, v_d, np.array([-t_ca_s]))
    return Trajectory.from_state(r_epoch[0], v_epoch[0])


def verify_construction(
    target: Trajectory,
    debris: Trajectory,
    debris_id: str,
    t_ca_s: float,
    miss_m: float,
) -> tuple[bool, str]:
    """Forward-propagate and confirm the intended encounter actually reproduces."""
    encounters = find_encounters(target, debris, debris_id, HORIZON_S, step_s=5.0)
    closest = closest_encounter(encounters)
    if closest is None:
        return False, "no encounter found on forward propagation"

    time_error = abs(closest.tca_s - t_ca_s)
    distance_error = abs(closest.min_separation_m - miss_m)
    if time_error > REPRODUCTION_TOLERANCE_S:
        return False, f"encounter time off by {time_error:.4f} s"
    if distance_error > REPRODUCTION_TOLERANCE_M:
        return False, f"miss distance off by {distance_error:.4f} m"
    return True, (
        f"reproduced at {closest.tca_s:.3f} s, {closest.min_separation_m:.3f} m, "
        f"relative speed {closest.relative_speed_mps:.0f} m/s"
    )


# --------------------------------------------------------------------------
# The signature case: three facts, searched for rather than hand-tuned
# --------------------------------------------------------------------------


@dataclass
class BuiltScenario:
    scenario_id: str
    description: str
    seed: int
    satellite: Trajectory
    debris: dict[str, Trajectory]
    primary_threat_id: str
    evidence: dict


def _closest(a: Trajectory, b: Trajectory, object_id: str):
    return closest_encounter(find_encounters(a, b, object_id, HORIZON_S, step_s=5.0))


def build_signature_case(seed_state: SeedState, seed: int, policy: Policy) -> BuiltScenario:
    """Primary conflict where the best-looking fix creates a second conflict.

    Every attempt is fully evaluated before it is accepted. The trap is whatever
    the search itself ranks first, so the rejection the demo shows is discovered
    by our own ranking rather than chosen for effect.
    """
    rng = np.random.default_rng(seed)
    satellite = Trajectory.from_state(seed_state.r_m, seed_state.v_mps)
    rejected: list[str] = []

    for attempt in range(MAX_ATTEMPTS):
        try:
            tca_1 = PRIMARY_TCA_TARGET_S + float(rng.uniform(-600.0, 600.0))
            miss_1 = float(rng.uniform(80.0, 250.0))
            debris_1 = construct_debris(
                satellite,
                tca_1,
                miss_1,
                float(rng.uniform(6000.0, 12000.0)),
                float(rng.uniform(0.0, 2.0 * np.pi)),
            )
        except GenerationError as exc:
            rejected.append(f"attempt {attempt}: primary construction -- {exc}")
            continue

        ok, detail = verify_construction(satellite, debris_1, "DEB-1", tca_1, miss_1)
        if not ok:
            rejected.append(f"attempt {attempt}: primary did not reproduce -- {detail}")
            continue

        search = evaluate_candidates(satellite, debris_1, "DEB-1", policy, HORIZON_S)
        if search.baseline.primary_qualified:
            rejected.append(f"attempt {attempt}: baseline already clears the primary threat")
            continue

        trap = search.best
        if trap is None or trap.candidate.is_baseline:
            rejected.append(f"attempt {attempt}: no manoeuvre qualifies against the primary")
            continue

        trap_trajectory = apply_candidate(satellite, trap.candidate)

        try:
            tca_2 = SECONDARY_TCA_TARGET_S + float(rng.uniform(-600.0, 600.0))
            miss_2 = float(rng.uniform(150.0, 600.0))
            debris_2 = construct_debris(
                trap_trajectory,
                tca_2,
                miss_2,
                float(rng.uniform(6000.0, 12000.0)),
                float(rng.uniform(0.0, 2.0 * np.pi)),
            )
        except GenerationError as exc:
            rejected.append(f"attempt {attempt}: secondary construction -- {exc}")
            continue

        ok, detail = verify_construction(trap_trajectory, debris_2, "DEB-2", tca_2, miss_2)
        if not ok:
            rejected.append(f"attempt {attempt}: secondary did not reproduce -- {detail}")
            continue

        # Fact 1 -- doing nothing is safe with respect to the second object, so
        # the secondary conflict is created by the manoeuvre, not pre-existing.
        # Require real margin, not a hair above the floor: a baseline sitting at
        # 1.1x the floor would make "the manoeuvre caused this" a weak claim.
        baseline_vs_2 = _closest(satellite, debris_2, "DEB-2")
        if (
            baseline_vs_2 is None
            or baseline_vs_2.min_separation_m < SECONDARY_CLEAR_MARGIN * policy.min_separation_m
        ):
            rejected.append(f"attempt {attempt}: baseline is not clearly safe from the second object")
            continue

        # Fact 2 -- the highest-ranked option really does violate the floor.
        trap_vs_2 = _closest(trap_trajectory, debris_2, "DEB-2")
        if trap_vs_2 is None or trap_vs_2.min_separation_m >= policy.min_separation_m:
            rejected.append(f"attempt {attempt}: top option does not violate the floor")
            continue

        # Fact 3 -- a different option clears both, so the case has an answer.
        rescue = None
        for evaluation in search.qualified:
            if evaluation.candidate.candidate_id == trap.candidate.candidate_id:
                continue
            if evaluation.candidate.is_baseline:
                continue
            candidate_vs_2 = _closest(
                apply_candidate(satellite, evaluation.candidate), debris_2, "DEB-2"
            )
            if (
                candidate_vs_2 is not None
                and candidate_vs_2.min_separation_m >= policy.min_separation_m
            ):
                rescue = (evaluation, candidate_vs_2)
                break

        if rescue is None:
            rejected.append(f"attempt {attempt}: no option clears both objects")
            continue

        rescue_evaluation, rescue_vs_2 = rescue
        return BuiltScenario(
            scenario_id="primary",
            description=(
                "Primary close approach with a secondary conflict created by the "
                "highest-ranked option."
            ),
            seed=seed,
            satellite=satellite,
            debris={"DEB-1": debris_1, "DEB-2": debris_2},
            primary_threat_id="DEB-1",
            evidence={
                "attempts_used": attempt + 1,
                "baseline_vs_primary_m": search.baseline.primary_encounter.min_separation_m,
                "baseline_vs_primary_tca_s": search.baseline.primary_encounter.tca_s,
                "baseline_vs_secondary_m": baseline_vs_2.min_separation_m,
                "trap_candidate_id": trap.candidate.candidate_id,
                "trap_vs_primary_m": trap.primary_encounter.min_separation_m,
                "trap_vs_secondary_m": trap_vs_2.min_separation_m,
                "trap_vs_secondary_tca_s": trap_vs_2.tca_s,
                "rescue_candidate_id": rescue_evaluation.candidate.candidate_id,
                "rescue_vs_primary_m": rescue_evaluation.primary_encounter.min_separation_m,
                "rescue_vs_secondary_m": rescue_vs_2.min_separation_m,
                "qualified_against_primary": len(search.qualified),
                "candidate_count": search.candidate_count,
                "rejected_attempts": rejected[-5:],
            },
        )

    raise GenerationError(
        f"no signature case satisfied all three facts in {MAX_ATTEMPTS} attempts. "
        f"Last reasons: {rejected[-5:]}"
    )


def build_variant(
    seed_state: SeedState,
    seed: int,
    policy: Policy,
    scenario_id: str,
    description: str,
    primary_tca_s: float,
    primary_miss_m: float,
    require: str,
) -> BuiltScenario:
    """A simpler fixture with one required outcome against the primary threat.

    ``require`` is BASELINE_SAFE, MANOEUVRE_AVAILABLE or NO_QUALIFIED_OPTION.
    The second object is placed far away so it never drives the outcome.
    """
    rng = np.random.default_rng(seed)
    satellite = Trajectory.from_state(seed_state.r_m, seed_state.v_mps)
    rejected: list[str] = []

    for attempt in range(MAX_ATTEMPTS):
        try:
            tca_1 = primary_tca_s + float(rng.uniform(-300.0, 300.0))
            debris_1 = construct_debris(
                satellite,
                tca_1,
                primary_miss_m,
                float(rng.uniform(6000.0, 12000.0)),
                float(rng.uniform(0.0, 2.0 * np.pi)),
            )
            debris_2 = construct_debris(
                satellite,
                float(rng.uniform(6000.0, 9000.0)),
                float(rng.uniform(40_000.0, 90_000.0)),
                float(rng.uniform(6000.0, 12000.0)),
                float(rng.uniform(0.0, 2.0 * np.pi)),
            )
        except GenerationError as exc:
            rejected.append(f"attempt {attempt}: construction -- {exc}")
            continue

        ok, detail = verify_construction(satellite, debris_1, "DEB-1", tca_1, primary_miss_m)
        if not ok:
            rejected.append(f"attempt {attempt}: primary did not reproduce -- {detail}")
            continue

        search = evaluate_candidates(satellite, debris_1, "DEB-1", policy, HORIZON_S)
        baseline_vs_2 = _closest(satellite, debris_2, "DEB-2")
        if baseline_vs_2 is None or baseline_vs_2.min_separation_m < policy.min_separation_m:
            rejected.append(f"attempt {attempt}: distractor object is too close")
            continue

        burns_qualified = [e for e in search.qualified if not e.candidate.is_baseline]

        if require == "BASELINE_SAFE" and not search.baseline.primary_qualified:
            rejected.append(f"attempt {attempt}: baseline is not clear")
            continue
        if require == "MANOEUVRE_AVAILABLE" and (
            search.baseline.primary_qualified or not burns_qualified
        ):
            rejected.append(f"attempt {attempt}: wanted an unsafe baseline with a fix")
            continue
        if require == "NO_QUALIFIED_OPTION" and (
            search.baseline.primary_qualified or burns_qualified
        ):
            rejected.append(f"attempt {attempt}: an option still qualifies")
            continue

        return BuiltScenario(
            scenario_id=scenario_id,
            description=description,
            seed=seed,
            satellite=satellite,
            debris={"DEB-1": debris_1, "DEB-2": debris_2},
            primary_threat_id="DEB-1",
            evidence={
                "attempts_used": attempt + 1,
                "requirement": require,
                "baseline_vs_primary_m": search.baseline.primary_encounter.min_separation_m,
                "baseline_vs_primary_tca_s": search.baseline.primary_encounter.tca_s,
                "baseline_vs_secondary_m": baseline_vs_2.min_separation_m,
                "qualified_manoeuvres": len(burns_qualified),
                "search_status": search.status,
                "candidate_count": search.candidate_count,
                "rejected_attempts": rejected[-5:],
            },
        )

    raise GenerationError(
        f"variant {scenario_id!r} not satisfiable in {MAX_ATTEMPTS} attempts. "
        f"Last reasons: {rejected[-5:]}"
    )


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------


def _object_entry(
    object_id: str, name: str, kind: str, maneuverable: bool, trajectory: Trajectory
) -> dict:
    arc = trajectory.arcs[0]
    return {
        "object_id": object_id,
        "name": name,
        "kind": kind,
        "maneuverable": maneuverable,
        "initial_state": {
            "r_m": [float(x) for x in arc.r0_m],
            "v_mps": [float(x) for x in arc.v0_mps],
        },
    }


def scenario_document(built: BuiltScenario, seed_state: SeedState, policy: Policy) -> dict:
    """Serialize to the Scenario shape in Handoff/CONTRACTS.md.

    ``generation_evidence`` records what the generator measured while building
    the fixture. It is provenance, not input: the application recomputes every
    one of these values and must never read a verdict from here.
    """
    objects = [
        _object_entry(
            "SAT-1",
            f"{seed_state.object_name} (seed orbit)",
            "SATELLITE",
            True,
            built.satellite,
        ),
        _object_entry("DEB-1", "Synthetic debris 1", "DEBRIS", False, built.debris["DEB-1"]),
        _object_entry("DEB-2", "Synthetic debris 2", "DEBRIS", False, built.debris["DEB-2"]),
    ]

    document = {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": built.scenario_id,
        "scenario_version": 1,
        "seed": built.seed,
        "description": built.description,
        "epoch_utc": seed_state.epoch_utc.isoformat(timespec="milliseconds"),
        "horizon_s": HORIZON_S,
        "objects": objects,
        "satellite_id": "SAT-1",
        "primary_threat_id": built.primary_threat_id,
        "known_windows": [
            {
                "window_id": GROUND_STATION_WINDOW.window_id,
                "label": GROUND_STATION_WINDOW.label,
                "start_s": GROUND_STATION_WINDOW.start_s,
                "end_s": GROUND_STATION_WINDOW.end_s,
            }
        ],
        "default_policy": {
            "policy_version": policy.policy_version,
            "max_delta_v_mps": policy.max_delta_v_mps,
            "min_separation_m": policy.min_separation_m,
            "blocked_windows": [],
        },
        "provenance": {
            "source_kind": "CELESTRAK_GP_TLE",
            "source_url": (
                "https://celestrak.org/NORAD/elements/gp.php"
                f"?CATNR={seed_state.norad_id}&FORMAT=TLE"
            ),
            "source_sha256": seed_state.tle_sha256,
            "norad_id": seed_state.norad_id,
            "object_name": seed_state.object_name,
            "tle_epoch_utc": seed_state.epoch_utc.isoformat(timespec="milliseconds"),
            "frame": FRAME,
            "model_version": MODEL_VERSION,
            "synthetic_conjunction": True,
            "note": (
                "Satellite initial state derived from a real catalogue TLE at its "
                "own epoch. Both debris objects and every close approach are "
                "synthetic. The orbit is realistic; no conjunction here is real."
            ),
        },
        "generation_evidence": built.evidence,
    }

    payload = json.dumps(document, sort_keys=True).encode("utf-8")
    document["input_hash"] = hashlib.sha256(payload).hexdigest()
    return document


VARIANTS = [
    {
        "scenario_id": "no_encounter",
        "description": "No actionable close approach; doing nothing is correct.",
        "seed": 2001,
        "primary_tca_s": 16200.0,
        "primary_miss_m": 9500.0,
        "require": "BASELINE_SAFE",
    },
    {
        "scenario_id": "simple_conflict",
        "description": "One close approach with a straightforward feasible manoeuvre.",
        "seed": 2002,
        "primary_tca_s": 16200.0,
        "primary_miss_m": 200.0,
        "require": "MANOEUVRE_AVAILABLE",
    },
    {
        "scenario_id": "no_feasible",
        "description": (
            "Close approach too early for the supported burn grid to fix; no "
            "option qualifies."
        ),
        "seed": 2003,
        "primary_tca_s": 1300.0,
        "primary_miss_m": 150.0,
        "require": "NO_QUALIFIED_OPTION",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1001, help="seed for the signature case")
    parser.add_argument("--check", action="store_true", help="build and verify, write nothing")
    args = parser.parse_args()

    seed_state = load_seed_state()
    policy = Policy()

    print(
        f"seed: {seed_state.object_name} (NORAD {seed_state.norad_id}) "
        f"@ {seed_state.epoch_utc.isoformat(timespec='seconds')}"
    )
    elements = orbit_elements(seed_state.r_m, seed_state.v_mps)
    print(
        f"       a={elements['semi_major_axis_m'] / 1000:.1f} km  "
        f"e={elements['eccentricity']:.6f}  "
        f"i={elements['inclination_deg']:.2f} deg  "
        f"perigee alt={elements['perigee_altitude_m'] / 1000:.1f} km"
    )

    built_all = [build_signature_case(seed_state, args.seed, policy)]
    for spec in VARIANTS:
        built_all.append(
            build_variant(
                seed_state,
                spec["seed"],
                policy,
                spec["scenario_id"],
                spec["description"],
                spec["primary_tca_s"],
                spec["primary_miss_m"],
                spec["require"],
            )
        )

    for built in built_all:
        document = scenario_document(built, seed_state, policy)
        evidence = built.evidence
        print(f"\n{built.scenario_id}  (seed {built.seed}, {evidence['attempts_used']} attempt(s))")
        print(f"  {built.description}")
        for key, value in evidence.items():
            if key in ("attempts_used", "rejected_attempts"):
                continue
            if isinstance(value, float):
                print(f"  {key:32s} {value:,.3f}")
            else:
                print(f"  {key:32s} {value}")

        if not args.check:
            if built.scenario_id == "primary":
                path = OUTPUT_DIR / "primary.json"
            else:
                path = OUTPUT_DIR / "variants" / f"{built.scenario_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            print(f"  written -> {path.relative_to(REPO_ROOT)}")

    if args.check:
        print("\n--check: all fixtures built and verified; nothing written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
