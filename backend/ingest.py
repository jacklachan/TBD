"""Real catalogue elements in, a screenable scenario out.

Everything else in this project screens a fixture. This is the door for actual
data: paste the two-line element sets for a spacecraft and the objects near it,
and the same two paths screen those instead.

Three things are worth being plain about, because a demo that overstates them
is worse than one that does not exist.

The elements are real and so are the orbits. The *conjunction* is whatever the
elements say it is -- which, for two objects pulled off a public catalogue, is
usually nothing. Finding no encounter is the honest answer and the code says so
rather than manufacturing one.

SGP4 is used once, to turn each element set into a state vector at a common
epoch, and then the ordinary two-body propagator takes over. That is the same
treatment the committed seed TLE gets. It is not an SGP4 conjunction analysis:
over a six-hour horizon in low Earth orbit, drag and the oblateness terms SGP4
carries and this propagator does not will move a real object by kilometres. The
scenario records that in its provenance and the UI repeats it.

And no covariance comes with a TLE, so nothing here states a probability.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

MODEL_VERSION = "two-body-universal-variable-1"
FRAME = "SIM_ECI_TEME_SEEDED"
SCHEMA_VERSION = 1

DEFAULT_HORIZON_S = 21_600.0
MAX_OBJECTS = 12
MIN_OBJECTS = 2

# Sampling for the coarse pass that picks the primary threat. Only the ordering
# matters here, so this is far cruder than anything the verifier uses.
COARSE_STEP_S = 30.0

# A TLE line is 69 characters and starts with its line number. Checking the
# shape before handing it to SGP4 turns a library exception into a message that
# names the offending line.
_LINE1 = re.compile(r"^1 [ 0-9]{5}[A-Z] ")
_LINE2 = re.compile(r"^2 [ 0-9]{5} ")


class IngestError(ValueError):
    """Input that cannot be turned into a scenario, with the reason."""


@dataclass(frozen=True)
class TleObject:
    name: str
    norad_id: int
    line1: str
    line2: str
    epoch_utc: datetime
    r_m: np.ndarray
    v_mps: np.ndarray

    @property
    def altitude_km(self) -> float:
        return float(np.linalg.norm(self.r_m)) / 1000.0 - 6378.137


def _epoch_from(satrec) -> datetime:
    jd = satrec.jdsatepoch + satrec.jdsatepochF
    return datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=jd - 2400000.5)


def split_tle_text(text: str) -> list[tuple[str, str, str]]:
    """Split pasted text into (name, line1, line2) triples.

    Accepts the two shapes people actually paste: three-line sets with a name
    above each pair, and bare two-line sets with no names at all. A file that
    mixes them works too, because the pairing is driven by the line numbers
    rather than by counting lines.
    """
    if not text or not text.strip():
        raise IngestError("nothing pasted")

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    sets: list[tuple[str, str, str]] = []
    pending_name = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        if _LINE1.match(line):
            if index + 1 >= len(lines) or not _LINE2.match(lines[index + 1]):
                raise IngestError(
                    f"line {index + 1} starts an element set but no line 2 follows it"
                )
            name = pending_name or f"OBJECT {line[2:7].strip()}"
            sets.append((name, line, lines[index + 1]))
            pending_name = ""
            index += 2
            continue
        if _LINE2.match(line):
            raise IngestError(f"line {index + 1} is a line 2 with no line 1 before it")
        # Anything else is a name for the set that follows.
        pending_name = line.strip()
        index += 1

    if not sets:
        raise IngestError(
            "no element sets found. A TLE line 1 looks like "
            "'1 25544U 98067A   24001.50000000  ...'"
        )
    return sets


def evaluate_tles(text: str) -> list[TleObject]:
    """Evaluate every element set at the epoch of the first one.

    A common epoch is required: state vectors taken at each object's own epoch
    describe different instants and screening them against each other compares
    positions that never coexisted. Public element sets are typically hours
    apart, so this matters.
    """
    try:
        from sgp4.api import Satrec
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise IngestError("sgp4 is not installed on the server") from exc

    sets = split_tle_text(text)
    if len(sets) > MAX_OBJECTS:
        raise IngestError(
            f"{len(sets)} objects pasted; this screens at most {MAX_OBJECTS}"
        )
    if len(sets) < MIN_OBJECTS:
        raise IngestError(
            "at least two objects are needed: the spacecraft and something to "
            "screen it against"
        )

    records = []
    for name, line1, line2 in sets:
        try:
            satrec = Satrec.twoline2rv(line1, line2)
        except Exception as exc:  # noqa: BLE001 - library raises bare exceptions
            raise IngestError(f"{name}: element set rejected by SGP4 ({exc})") from exc
        records.append((name, line1, line2, satrec))

    # Everything is evaluated at the first object's epoch.
    reference = records[0][3]
    jd, fr = reference.jdsatepoch, reference.jdsatepochF
    epoch = _epoch_from(reference)

    objects: list[TleObject] = []
    seen: set[int] = set()
    for name, line1, line2, satrec in records:
        error, r_km, v_kms = satrec.sgp4(jd, fr)
        if error != 0:
            raise IngestError(
                f"{name}: SGP4 error {error} at the shared epoch "
                f"{epoch.isoformat(timespec='seconds')}. Element sets far from "
                "that epoch cannot be propagated to it."
            )
        r_m = np.array(r_km, dtype=np.float64) * 1000.0
        v_mps = np.array(v_kms, dtype=np.float64) * 1000.0
        if not np.all(np.isfinite(r_m)) or not np.all(np.isfinite(v_mps)):
            raise IngestError(f"{name}: SGP4 returned a non-finite state")

        norad_id = int(line1[2:7])
        if norad_id in seen:
            raise IngestError(f"NORAD {norad_id} appears twice")
        seen.add(norad_id)

        objects.append(
            TleObject(
                name=name.strip() or f"OBJECT {norad_id}",
                norad_id=norad_id,
                line1=line1,
                line2=line2,
                epoch_utc=epoch,
                r_m=r_m,
                v_mps=v_mps,
            )
        )
    return objects


def closest_object(
    objects: list[TleObject], satellite_index: int, horizon_s: float
) -> str:
    """Which pasted object comes nearest the spacecraft over the horizon.

    The search path screens candidates against one named primary threat, and for
    a generated fixture that is the object the case was built around. A paste
    has no such object, and taking whichever happened to be typed first made the
    ranking meaningless: the search would rank burns against an object that was
    never close while the real approach sat unranked. Everything is still
    screened by the verifier either way; this only decides which one the search
    is ranking against.

    Deliberately coarse. It picks a name, it does not report a distance -- the
    verifier recomputes every figure properly later, and a number produced here
    would be a second, worse answer to a question already answered elsewhere.
    """
    from backend.core.trajectory import Trajectory

    satellite = objects[satellite_index]
    grid = np.arange(0.0, horizon_s + COARSE_STEP_S, COARSE_STEP_S)
    own, _ = Trajectory.from_state(satellite.r_m, satellite.v_mps).states_at(grid)

    nearest, best = "", float("inf")
    for index, other in enumerate(objects):
        if index == satellite_index:
            continue
        theirs, _ = Trajectory.from_state(other.r_m, other.v_mps).states_at(grid)
        separation = float(np.min(np.linalg.norm(theirs - own, axis=1)))
        if separation < best:
            nearest, best = f"NORAD-{other.norad_id}", separation
    return nearest


def scenario_from_tles(
    text: str,
    satellite_index: int = 0,
    horizon_s: float = DEFAULT_HORIZON_S,
    scenario_id: str | None = None,
) -> dict:
    """A scenario document built from pasted elements, ready to screen.

    ``satellite_index`` names which of the pasted objects is the one that can
    manoeuvre. Everything else is screened against it.
    """
    if not 60.0 <= horizon_s <= 172_800.0:
        raise IngestError("horizon must be between 1 minute and 48 hours")

    objects = evaluate_tles(text)
    if not 0 <= satellite_index < len(objects):
        raise IngestError(
            f"satellite_index {satellite_index} is outside the {len(objects)} "
            "objects pasted"
        )

    satellite = objects[satellite_index]
    others = [o for i, o in enumerate(objects) if i != satellite_index]

    entries = []
    for index, obj in enumerate(objects):
        is_satellite = index == satellite_index
        entries.append(
            {
                "object_id": f"NORAD-{obj.norad_id}",
                "name": obj.name,
                "kind": "SATELLITE" if is_satellite else "DEBRIS",
                "maneuverable": is_satellite,
                "initial_state": {
                    "r_m": [float(c) for c in obj.r_m],
                    "v_mps": [float(c) for c in obj.v_mps],
                },
            }
        )

    digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    document = {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": scenario_id or f"tle:{digest[:12]}",
        "scenario_version": 1,
        "seed": 0,
        "description": (
            f"{len(objects)} catalogue objects screened against "
            f"{satellite.name}, from pasted element sets."
        ),
        "epoch_utc": satellite.epoch_utc.isoformat(timespec="milliseconds"),
        "horizon_s": float(horizon_s),
        "objects": entries,
        "satellite_id": f"NORAD-{satellite.norad_id}",
        # Screening covers every object regardless; this only names which one
        # the search path treats as the case's primary threat.
        "primary_threat_id": closest_object(objects, satellite_index, horizon_s)
        or f"NORAD-{others[0].norad_id}",
        "known_windows": [],
        "default_policy": {
            "policy_version": 1,
            "max_delta_v_mps": 0.2,
            "min_separation_m": 1000.0,
            "blocked_windows": [],
        },
        "provenance": {
            "source_kind": "PASTED_TLE",
            "source_url": "",
            "source_sha256": digest,
            "norad_id": satellite.norad_id,
            "object_name": satellite.name,
            "tle_epoch_utc": satellite.epoch_utc.isoformat(timespec="milliseconds"),
            "frame": FRAME,
            "model_version": MODEL_VERSION,
            "synthetic_conjunction": False,
            "note": (
                "Orbits are real: every state vector here came from a catalogue "
                "element set, evaluated with SGP4 at a single shared epoch. "
                "Propagation from that epoch is two-body, so this is not an SGP4 "
                "conjunction analysis -- over hours in low Earth orbit the "
                "difference is kilometres. No element set carries covariance, so "
                "nothing here states a collision probability. Treat any close "
                "approach found as a reason to look, not as a prediction."
            ),
            "objects": [
                {
                    "object_id": f"NORAD-{o.norad_id}",
                    "norad_id": o.norad_id,
                    "name": o.name,
                    "tle_epoch_utc": _tle_epoch_iso(o),
                    "altitude_km": round(o.altitude_km, 1),
                }
                for o in objects
            ],
        },
    }

    payload = __import__("json").dumps(document, sort_keys=True).encode("utf-8")
    document["input_hash"] = hashlib.sha256(payload).hexdigest()
    return document


def _tle_epoch_iso(obj: TleObject) -> str:
    """Each object's own element epoch, before it was moved to the shared one.

    Recorded per object because the spread between them is the main reason a
    screening built this way can be wrong, and hiding it would be the easiest
    way to make the result look better than it is.
    """
    from sgp4.api import Satrec

    satrec = Satrec.twoline2rv(obj.line1, obj.line2)
    return _epoch_from(satrec).isoformat(timespec="milliseconds")


def epoch_spread_s(text: str) -> float:
    """Seconds between the earliest and latest element epoch in a paste."""
    from sgp4.api import Satrec

    epochs = [
        _epoch_from(Satrec.twoline2rv(line1, line2))
        for _, line1, line2 in split_tle_text(text)
    ]
    return (max(epochs) - min(epochs)).total_seconds()
