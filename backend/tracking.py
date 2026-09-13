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
# Head-on in LEO is about 15.5 km/s; the margin keeps the capture radius honest.
MAX_RELATIVE_SPEED_KMS = 16.0
# A straight-line estimate from a sample up to half a step away is good to a
# few hundred metres for passes this close; refine anything that might be in.
LINEAR_MARGIN_KM = 10.0
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
    capture_km = report_km + MAX_RELATIVE_SPEED_KMS * step_s / 2.0
    keep_km = report_km + LINEAR_MARGIN_KM
    candidates: dict[tuple[int, int], list[float]] = {}
    far = 1e9

    chunk = 360
    for first in range(0, offsets.size, chunk):
        times = offsets[first:first + chunk]
        rp, vp = _sgp4_many(sat_p, start, times)
        rd, vd = _sgp4_many(sat_d, start, times)
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
                for jj, t_est in zip(j[near & (miss < keep_km)], (times[k] + tau)[near & (miss < keep_km)]):
                    candidates.setdefault((i, int(jj)), []).append(float(t_est))

    conjunctions = []
    for (i, j), estimates in candidates.items():
        estimates.sort()
        grouped: list[float] = []
        for t_est in estimates:
            if not grouped or t_est - grouped[-1] > 2 * step_s:
                grouped.append(t_est)
        for t_est in grouped:
            found = _refine(sat_p[i], sat_d[j], start, t_est, REFINE_HALF_WINDOW_S)
            if found is None or found[1] > report_km:
                continue
            t_s, miss, speed = found
            tca = start + timedelta(seconds=t_s)
            conjunctions.append({
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


def element_text(*norad_ids: int) -> str:
    """The committed element sets for the given objects, as TLE text."""
    _, objects = load_catalog()
    by_id = {o.norad_id: o for o in objects}
    missing = [n for n in norad_ids if n not in by_id]
    if missing:
        raise TrackingError(f"not in the committed catalogue: {missing}")
    return "\n".join(f"{by_id[n].name}\n{by_id[n].line1}\n{by_id[n].line2}" for n in norad_ids)
