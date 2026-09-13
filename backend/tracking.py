"""Real-catalogue screening: a comms constellation against real debris.

Everything else in this project decides what to do about one close approach.
This finds them. It screens every satellite of the Iridium NEXT constellation
against every tracked fragment of the two events that seeded its shell -- the
2009 Iridium 33 / Cosmos 2251 collision and the 2007 Fengyun-1C test -- over
several days, from element sets fetched once and committed
(``scripts/fetch_snapshots.py --catalog``). Nothing is fetched at runtime.

Method, and why it is shaped this way:

* **SGP4 at absolute times.** Each object is propagated from its own element
  epoch to the same UTC instants, the way the catalogue is meant to be used.
  This is a different model from the two-body planner, on purpose: over days,
  drag and oblateness move a real object by tens of kilometres.
* **Coarse pass with a spatial index.** One-minute samples; at each, a KD-tree
  over the fragments returns everything within a radius wide enough that no
  pass closer than the report threshold can fall between two samples
  (threshold plus the largest LEO relative speed times half a step).
* **Linear closest approach, then exact refinement.** At each hit the relative
  position and velocity give a straight-line estimate of the miss; only
  estimates near the threshold are refined, by bounded minimisation of the SGP4
  separation itself.
* **An external check.** Pairs that CelesTrak's own SOCRATES report lists are
  recomputed here and compared, published figure against ours.

Limits, stated where the result is shown: element sets are roughly kilometre
accurate at epoch and degrade over days; no covariance is published with them,
so no probability is computed. A close approach found here is a reason to look,
not a prediction.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = REPO_ROOT / "data" / "catalog"
CATALOG_PROVENANCE = CATALOG_DIR / "catalog_provenance.json"
SOCRATES_CSV = REPO_ROOT / "data" / "context" / "socrates_snapshot.csv"

WINDOW_HOURS = 84.0
COARSE_STEP_S = 60.0
REPORT_KM = 10.0
# Floor for the capture bound. Head-on in LEO is about 15.5 km/s, so this holds
# for the committed catalogue -- but it is an assumption, and a screen that
# assumes its own capture radius cannot claim to have found everything. The
# bound actually used is derived from the element sets in hand
# (``_capture_speed_bound``) and only falls back to this when that comes out
# lower, so swapping in a catalogue with faster objects widens the radius
# instead of silently dropping passes.
MAX_RELATIVE_SPEED_KMS = 16.0
# SGP4 reports osculating velocity; the bound below is computed from mean
# elements. Short-period J2 terms separate the two by well under a tenth of a
# percent of orbital speed. A quarter of a km/s is two orders of magnitude more
# than that difference and costs a few kilometres of capture radius.
SPEED_BOUND_MARGIN_KMS = 0.25
EARTH_MU_KM3_S2 = 398600.4418
# A straight-line estimate from a sample up to half a step away is good to a
# few hundred metres for passes this close; refine anything that might be in.
LINEAR_MARGIN_KM = 10.0
# A pass this close is worth putting in front of an operator: it is the same
# distance at which the avoidance planner will list an option, so the queue
# below never holds a pass the planner would decline to discuss.
# ``test_the_triage_queue_matches_what_the_planner_will_act_on`` keeps the two
# from drifting apart.
TRIAGE_ATTENTION_KM = 5.0
REFINE_HALF_WINDOW_S = 15.0
CROSS_CHECK_HALF_WINDOW_S = 900.0
MAX_LISTED = 25

EVENT_LABELS = {
    "iridium-33-debris": "Iridium 33 (2009 collision)",
    "cosmos-2251-debris": "Cosmos 2251 (2009 collision)",
    "fengyun-1c-debris": "Fengyun-1C (2007 ASAT test)",
}


class TrackingError(RuntimeError):
    """The committed catalogue is missing or unreadable."""


@dataclass(frozen=True)
class CatalogObject:
    norad_id: int
    name: str
    group: str
    role: str
    line1: str
    line2: str
    epoch_utc: datetime


def _epoch(satrec) -> datetime:
    whole = datetime(1949, 12, 31, tzinfo=timezone.utc)
    return whole + timedelta(days=satrec.jdsatepoch - 2433281.5 + satrec.jdsatepochF)


def _jd(moment: datetime) -> tuple[float, float]:
    """Julian date split as (whole, fraction) to keep sub-second precision."""
    delta = moment - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    days = delta.total_seconds() / 86400.0 + 2451545.0
    whole = float(np.floor(days))
    return whole, days - whole


def _orbit_speed_bound_kms(satrec) -> float:
    """Fastest this object can be moving, from its own mean elements.

    Speed on a two-body orbit peaks at perigee, so ``sqrt(mu (1+e) / (a (1-e)))``
    bounds it everywhere -- no propagation, no sampling, and true for every
    instant of the window rather than only the instants we happened to look at.
    Mean motion gives the semi-major axis; ``no_kozai`` is in radians per minute.

    This bounds the *mean* orbit. SGP4 returns osculating state, whose speed
    rides slightly above it on the short-period J2 terms: across the committed
    catalogue the excess peaks at 5 m/s and sits at 1.3 m/s typical, measured
    over a full revolution of all 2744 objects. ``SPEED_BOUND_MARGIN_KMS``
    covers that fifty times over, and is added once in
    ``_capture_speed_bound`` -- so it is that function, not this one, that
    returns a figure safe to size a capture radius with.
    """
    n = satrec.no_kozai / 60.0
    if n <= 0.0:
        return float("inf")
    a = (EARTH_MU_KM3_S2 / (n * n)) ** (1.0 / 3.0)
    e = min(max(float(satrec.ecco), 0.0), 0.999)
    return float(np.sqrt(EARTH_MU_KM3_S2 * (1.0 + e) / (a * (1.0 - e))))


def _capture_speed_bound(sat_p: list, sat_d: list) -> dict:
    """The relative speed the capture radius has to survive, and where it came from.

    Two objects close head-on approach each other no faster than the sum of
    their individual speed bounds, so the fastest protected satellite plus the
    fastest fragment bounds every pair in the catalogue at once. That is looser
    than a per-pair bound and far cheaper: one number, computed before any
    propagation, that the whole coarse pass can be checked against.
    """
    fastest_p = max((_orbit_speed_bound_kms(s) for s in sat_p), default=0.0)
    fastest_d = max((_orbit_speed_bound_kms(s) for s in sat_d), default=0.0)
    derived = fastest_p + fastest_d + SPEED_BOUND_MARGIN_KMS
    return {
        "derived_kms": round(derived, 3),
        "floor_kms": MAX_RELATIVE_SPEED_KMS,
        "applied_kms": round(max(derived, MAX_RELATIVE_SPEED_KMS), 3),
        "source": "perigee_speed_sum_from_mean_elements",
        "fastest_protected_kms": round(fastest_p, 3),
        "fastest_debris_kms": round(fastest_d, 3),
        "margin_kms": SPEED_BOUND_MARGIN_KMS,
    }


def load_catalog() -> tuple[dict, list[CatalogObject]]:
    from sgp4.api import Satrec

    from backend.ingest import split_tle_text

    if not CATALOG_PROVENANCE.exists():
        raise TrackingError(
            "tracking catalogue not present; run scripts/fetch_snapshots.py --catalog once"
        )
    provenance = json.loads(CATALOG_PROVENANCE.read_text(encoding="utf-8"))
    objects: list[CatalogObject] = []
    seen: set[int] = set()
    for entry in provenance["files"]:
        text = (CATALOG_DIR / entry["file"]).read_text(encoding="utf-8")
        for name, line1, line2 in split_tle_text(text):
            norad = int(line1[2:7])
            if norad in seen:
                continue
            seen.add(norad)
            objects.append(CatalogObject(
                norad_id=norad, name=name.strip(), group=entry["group"], role=entry["role"],
                line1=line1, line2=line2, epoch_utc=_epoch(Satrec.twoline2rv(line1, line2)),
            ))
    return provenance, objects


def _sgp4_many(satrecs, start: datetime, offsets_s: np.ndarray):
    from sgp4.api import SatrecArray

    jd0, fr0 = _jd(start)
    fr = fr0 + offsets_s / 86400.0
    jd = np.full_like(fr, jd0)
    error, r, v = SatrecArray(satrecs).sgp4(jd, fr)
    bad = error != 0
    r[bad] = np.nan
    v[bad] = np.nan
    return r, v


def _fastest_sampled_kms(v: np.ndarray) -> float:
    """Largest speed actually seen in a block of propagated velocities.

    Propagation failures arrive as NaN and are ignored rather than poisoning the
    maximum; a block that is entirely failures contributes nothing.
    """
    speeds = np.linalg.norm(v, axis=-1)
    finite = speeds[np.isfinite(speeds)]
    return float(finite.max()) if finite.size else 0.0


def _pair_state(sat_a, sat_b, start: datetime, t_s: float):
    jd0, fr0 = _jd(start)
    fr = fr0 + t_s / 86400.0
    ea, ra, va = sat_a.sgp4(jd0, fr)
    eb, rb, vb = sat_b.sgp4(jd0, fr)
    if ea or eb:
        return None
    return np.subtract(rb, ra), np.subtract(vb, va)


def _refine(sat_a, sat_b, start: datetime, t_guess: float, half_window: float):
    """Exact SGP4 closest approach near ``t_guess``: (t_s, miss_km, speed_kms)."""
    lo, hi = t_guess - half_window, t_guess + half_window
    samples = np.linspace(lo, hi, int(2 * half_window) + 1)
    best_t, best_d = None, np.inf
    for t in samples:
        state = _pair_state(sat_a, sat_b, start, float(t))
        if state is None:
            continue
        d = float(np.linalg.norm(state[0]))
        if d < best_d:
            best_t, best_d = float(t), d
    if best_t is None:
        return None

    def squared(t):
        state = _pair_state(sat_a, sat_b, start, float(t))
        return np.inf if state is None else float(state[0] @ state[0])

    outcome = minimize_scalar(
        squared, bounds=(best_t - 1.0, best_t + 1.0), method="bounded", options={"xatol": 1e-4}
    )
    t_min = float(outcome.x) if np.isfinite(outcome.fun) and outcome.fun <= best_d**2 else best_t
    state = _pair_state(sat_a, sat_b, start, t_min)
    return t_min, float(np.linalg.norm(state[0])), float(np.linalg.norm(state[1]))


def _triage(lead_s: float, half_orbit_s: float) -> dict:
    """How much room is left to do anything about this pass.

    Sorting a screen by miss distance answers the wrong question. A 500 m pass
    three days out is a calendar entry; a 2 km pass forty minutes out is a
    decision, and the second one is the one that gets missed. What separates
    them is not how close the objects come, it is whether a burn can still be
    placed -- so the measure here is taken straight from the avoidance planner:
    it designs burns one, three, five and seven half-orbits ahead, and this
    counts how many of those placements are still in the future.

    Nothing here is a probability. There is no covariance on a public element
    set, so these fields order a queue; they do not score a risk.
    """
    from backend.avoidance import LEAD_HALF_ORBITS

    ladder = sorted(LEAD_HALF_ORBITS)
    open_slots = [k for k in ladder if k * half_orbit_s <= lead_s]
    if not open_slots:
        posture = "TOO_LATE"
    elif len(open_slots) == len(ladder):
        posture = "ACTIONABLE"
    else:
        posture = "NARROWING"
    latest = max(open_slots) if open_slots else 0
    return {
        "posture": posture,
        "lead_hours": round(lead_s / 3600.0, 2),
        # The deadline, which is not the approach. The last usable burn sits a
        # whole number of half-orbits ahead of TCA, and which one that is
        # differs per pass -- so a later approach can carry the earlier
        # deadline, and ordering on time-to-approach quietly buries it.
        "decide_in_hours": round((lead_s - latest * half_orbit_s) / 3600.0, 2) if open_slots else None,
        "burn_slots_open": len(open_slots),
        "burn_slots_total": len(ladder),
        "latest_burn_half_orbits": latest,
        "decide_by_utc": None,  # filled in by the caller, which holds the epoch
    }


def _cross_check(objects_by_id: dict, satrecs_by_id: dict, start: datetime, end: datetime) -> list[dict]:
    """Recompute the SOCRATES pairs whose objects are both in the catalogue."""
    if not SOCRATES_CSV.exists():
        return []
    checks = []
    with SOCRATES_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                a, b = int(row["NORAD_CAT_ID_1"]), int(row["NORAD_CAT_ID_2"])
            except ValueError:
                continue
            if a not in objects_by_id or b not in objects_by_id:
                continue
            published = datetime.strptime(row["TCA"], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            entry = {
                "object_1": {"norad_id": a, "name": objects_by_id[a].name},
                "object_2": {"norad_id": b, "name": objects_by_id[b].name},
                "published_tca_utc": published.isoformat(timespec="milliseconds"),
                "published_miss_km": float(row["TCA_RANGE_KM"]),
                "published_relative_speed_kms": float(row["TCA_RELATIVE_SPEED_KMS"]),
            }
            if not start <= published <= end:
                entry["status"] = "OUTSIDE_WINDOW"
                checks.append(entry)
                continue
            found = _refine(
                satrecs_by_id[a], satrecs_by_id[b], start,
                (published - start).total_seconds(), CROSS_CHECK_HALF_WINDOW_S,
            )
            if found is None:
                entry["status"] = "PROPAGATION_ERROR"
            else:
                t_s, miss, speed = found
                ours = start + timedelta(seconds=t_s)
                entry.update({
                    "status": "RECOMPUTED",
                    "our_tca_utc": ours.isoformat(timespec="milliseconds"),
                    "our_miss_km": round(miss, 3),
                    "our_relative_speed_kms": round(speed, 3),
                    "tca_difference_s": round((ours - published).total_seconds(), 1),
                })
            checks.append(entry)
    return checks


def screen(window_hours: float = WINDOW_HOURS, step_s: float = COARSE_STEP_S,
           report_km: float = REPORT_KM, include_all: bool = False) -> dict:
    """Screen every protected satellite against every debris object."""
    from sgp4.api import Satrec

    started = time.perf_counter()
    provenance, objects = load_catalog()
    retrieved = datetime.fromisoformat(provenance["retrieved_at_utc"])
    start = retrieved.replace(second=0, microsecond=0)
    end = start + timedelta(hours=window_hours)

    protected = [o for o in objects if o.role == "PROTECTED"]
    debris = [o for o in objects if o.role == "DEBRIS"]
    if not protected or not debris:
        raise TrackingError("catalogue needs both protected satellites and debris")
    sat_p = [Satrec.twoline2rv(o.line1, o.line2) for o in protected]
    sat_d = [Satrec.twoline2rv(o.line1, o.line2) for o in debris]

    offsets = np.arange(0.0, window_hours * 3600.0 + step_s / 2, step_s)
    bound = _capture_speed_bound(sat_p, sat_d)
    capture_km = report_km + bound["applied_kms"] * step_s / 2.0
    keep_km = report_km + LINEAR_MARGIN_KM
    candidates: dict[tuple[int, int], list[tuple[float, float]]] = {}
    observed_p = observed_d = 0.0
    far = 1e9

    chunk = 360
    for first in range(0, offsets.size, chunk):
        times = offsets[first:first + chunk]
        rp, vp = _sgp4_many(sat_p, start, times)
        rd, vd = _sgp4_many(sat_d, start, times)
        observed_p = max(observed_p, _fastest_sampled_kms(vp))
        observed_d = max(observed_d, _fastest_sampled_kms(vd))
        for k in range(times.size):
            points = np.where(np.isfinite(rd[:, k]), rd[:, k], far)
            tree = cKDTree(points)
            queries = np.where(np.isfinite(rp[:, k]), rp[:, k], -far)
            for i, hits in enumerate(tree.query_ball_point(queries, r=capture_km)):
                if not hits:
                    continue
                j = np.asarray(hits)
                rel_r = rd[j, k] - rp[i, k]
                rel_v = vd[j, k] - vp[i, k]
                vv = np.sum(rel_v * rel_v, axis=1)
                tau = -np.sum(rel_r * rel_v, axis=1) / vv
                near = np.abs(tau) <= step_s * 0.6
                miss = np.linalg.norm(rel_r + rel_v * tau[:, None], axis=1)
                take = near & (miss < keep_km)
                for jj, t_est, miss_est in zip(j[take], (times[k] + tau)[take], miss[take]):
                    candidates.setdefault((i, int(jj)), []).append((float(t_est), float(miss_est)))

    conjunctions = []
    worst_linear_error_km = 0.0
    for (i, j), estimates in candidates.items():
        estimates.sort()
        grouped: list[tuple[float, float]] = []
        for entry in estimates:
            if not grouped or entry[0] - grouped[-1][0] > 2 * step_s:
                grouped.append(entry)
        for t_est, miss_est in grouped:
            found = _refine(sat_p[i], sat_d[j], start, t_est, REFINE_HALF_WINDOW_S)
            if found is None:
                continue
            # How far the straight-line estimate that put this pair on the list
            # sat from the answer SGP4 actually gives. Measured on every
            # candidate, in or out, because it is the margin in LINEAR_MARGIN_KM
            # that decides what never gets refined at all.
            worst_linear_error_km = max(worst_linear_error_km, abs(miss_est - found[1]))
            if found[1] > report_km:
                continue
            t_s, miss, speed = found
            tca = start + timedelta(seconds=t_s)
            # pi/n is half a revolution: the unit the burn ladder is spaced in.
            half_orbit_s = float(np.pi / (sat_p[i].no_kozai / 60.0))
            triage = _triage(t_s, half_orbit_s)
            if triage["burn_slots_open"]:
                triage["decide_by_utc"] = (
                    tca - timedelta(seconds=triage["latest_burn_half_orbits"] * half_orbit_s)
                ).isoformat(timespec="seconds")
            else:
                triage.pop("decide_by_utc")
                triage.pop("decide_in_hours")
            conjunctions.append({
                "triage": triage,
                "protected": {"norad_id": protected[i].norad_id, "name": protected[i].name},
                "debris": {
                    "norad_id": debris[j].norad_id, "name": debris[j].name,
                    "event": EVENT_LABELS.get(debris[j].group, debris[j].group),
                },
                "tca_utc": tca.isoformat(timespec="milliseconds"),
                "miss_km": round(miss, 3),
                "relative_speed_kms": round(speed, 3),
                "element_age_days": {
                    "protected": round((tca - protected[i].epoch_utc).total_seconds() / 86400.0, 2),
                    "debris": round((tca - debris[j].epoch_utc).total_seconds() / 86400.0, 2),
                },
            })
    conjunctions.sort(key=lambda c: c["miss_km"])

    # The work queue, as opposed to the leaderboard. Closest-first is how you
    # write a report; soonest-decision-first is how you run a console, and a
    # pass whose last burn slot has already gone by is filed at the end because
    # there is no longer a decision attached to it.
    queue = [c for c in conjunctions if c["miss_km"] <= TRIAGE_ATTENTION_KM]
    queue.sort(key=lambda c: (
        0 if c["triage"]["burn_slots_open"] else 1,
        c["triage"].get("decide_in_hours") if c["triage"].get("decide_in_hours") is not None else 0.0,
        c["miss_km"],
    ))
    by_posture: dict[str, int] = {}
    for c in queue:
        posture = c["triage"]["posture"]
        by_posture[posture] = by_posture.get(posture, 0) + 1

    by_satellite: dict[int, dict] = {}
    by_event: dict[str, int] = {}
    for c in conjunctions:
        entry = by_satellite.setdefault(c["protected"]["norad_id"], {
            **c["protected"], "count": 0, "closest_km": c["miss_km"],
        })
        entry["count"] += 1
        by_event[c["debris"]["event"]] = by_event.get(c["debris"]["event"], 0) + 1

    objects_by_id = {o.norad_id: o for o in objects}
    satrecs_by_id = {o.norad_id: s for o, s in zip(protected + debris, sat_p + sat_d)}
    cross_check = _cross_check(objects_by_id, satrecs_by_id, start, end)

    # Two assumptions decide whether "nothing else was within the threshold" is
    # a finding or a hope: that no pair closes faster than the capture radius
    # allows for, and that the straight-line estimate never understates a miss
    # by more than the margin on the refine list. Both are now measured against
    # what the propagator actually produced, and both numbers ship with the
    # result so the claim can be checked instead of taken.
    observed_head_on = observed_p + observed_d
    speed_headroom = bound["applied_kms"] - observed_head_on
    linear_headroom = LINEAR_MARGIN_KM - worst_linear_error_km
    shortfall = []
    if speed_headroom < 0:
        shortfall.append(
            f"a pair closed at up to {observed_head_on:.3f} km/s, beyond the "
            f"{bound['applied_kms']:.3f} km/s the capture radius was sized for"
        )
    if linear_headroom < 0:
        shortfall.append(
            f"a straight-line estimate was off by {worst_linear_error_km:.3f} km, "
            f"beyond the {LINEAR_MARGIN_KM:.1f} km margin on the refine list"
        )
    completeness = {
        "status": "INCOMPLETE" if shortfall else "COMPLETE",
        "claim": (
            "No pass closer than the report threshold can fall between two coarse "
            "samples: the capture radius is the threshold plus the fastest "
            "relative closure the catalogue permits, times half a step."
        ),
        "capture_radius_km": round(capture_km, 3),
        "speed_bound": bound,
        "observed_head_on_kms": round(observed_head_on, 3),
        "speed_headroom_kms": round(speed_headroom, 3),
        "linear_margin_km": LINEAR_MARGIN_KM,
        "worst_linear_error_km": round(worst_linear_error_km, 4),
        "linear_headroom_km": round(linear_headroom, 4),
        "candidate_pairs_refined": len(candidates),
        **({"shortfall": shortfall} if shortfall else {}),
    }

    return {
        "mode": "SGP4_CATALOGUE_SCREEN",
        "window": {
            "start_utc": start.isoformat(timespec="seconds"),
            "end_utc": end.isoformat(timespec="seconds"),
            "hours": window_hours,
            "coarse_step_s": step_s,
        },
        "catalog": {
            "retrieved_at_utc": provenance["retrieved_at_utc"],
            "protected_count": len(protected),
            "debris_count": len(debris),
            "groups": [
                {"group": f["group"], "role": f["role"], "object_count": f["object_count"],
                 "label": EVENT_LABELS.get(f["group"], "Iridium NEXT constellation")}
                for f in provenance["files"]
            ],
        },
        "pairs_screened": len(protected) * len(debris),
        "report_threshold_km": report_km,
        "completeness": completeness,
        "triage": {
            "attention_km": TRIAGE_ATTENTION_KM,
            "queue_length": len(queue),
            "by_posture": by_posture,
            "basis": (
                "Ordered by when the decision has to be made, not by how close "
                "the pass is and not by when it happens. A burn is placeable one, "
                "three, five or seven half-orbits before the approach, so the "
                "deadline is the last of those still in the future -- which can "
                "fall earlier for a later approach. Once none is left there is "
                "nothing to decide and the pass is filed at the end. No "
                "probability is implied: public element sets carry no covariance."
            ),
            "queue": queue[:MAX_LISTED],
        },
        "conjunction_count": len(conjunctions),
        "conjunctions": conjunctions[:MAX_LISTED],
        "by_satellite": sorted(by_satellite.values(), key=lambda s: s["closest_km"])[:10],
        "by_event": by_event,
        "cross_check": cross_check,
        **({"all_conjunctions": conjunctions} if include_all else {}),
        "elapsed_s": round(time.perf_counter() - started, 2),
        "note": (
            "Real public element sets propagated with SGP4 to common UTC times. "
            "Element sets are roughly kilometre-accurate at epoch and degrade over "
            "days, and none carries covariance, so no probability is computed. A "
            "close approach found here is a reason to look, not a prediction."
        ),
    }


_CACHE: dict | None = None
_ALL: list[dict] = []
_CACHE_LOCK = threading.Lock()


def cached_screen() -> dict:
    """The committed catalogue never changes at runtime, so screen it once."""
    global _CACHE, _ALL
    with _CACHE_LOCK:
        if _CACHE is None:
            result = screen(include_all=True)
            _ALL = result.pop("all_conjunctions")
            _CACHE = result
        return _CACHE


def all_conjunctions() -> list[dict]:
    """Every pass under the report threshold, not only the listed closest."""
    cached_screen()
    return _ALL


