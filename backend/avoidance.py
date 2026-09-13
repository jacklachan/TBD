"""Avoidance options for a real close approach found by the catalogue screen.

The two-body planner cannot take a real pass: replaying SGP4 geometry in pure
two-body mispredicts a pass by 7-22 km within hours, because it drops the
oblateness terms SGP4 carries. So this works on the SGP4 geometry directly.

* **Burn effect: Clohessy-Wiltshire.** An along-track impulse ``dv`` applied
  ``tau`` seconds before closest approach displaces the satellite by
  ``x = 2 dv/n (1 - cos n tau)`` radially and
  ``y = dv/n (4 sin n tau - 3 n tau)`` along track, in its own RTN frame. Small
  compared with the orbit radius for every burn offered here.
* **Predicted miss: the encounter plane.** At closest approach the relative
  motion is a straight line at kilometres per second, so the new miss is the
  component of the shifted relative position perpendicular to the relative
  velocity.
* **Then an independent re-screen.** Each option that clears the pass on that
  estimate has its manoeuvred trajectory -- SGP4 plus the CW displacement at
  every instant -- screened against every catalogued fragment for twelve hours
  after the burn. A burn that fixes one pass and creates another is blocked,
  the same rule the rest of the product applies.

Every figure is labelled as a linearised estimate on public element sets. No
covariance, no probability.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.spatial import cKDTree

from backend import tracking

MU_KM3_S2 = 398600.4418
FLOOR_KM = 1.0
COMFORTABLE_KM = 1.25
# Burns an odd number of half-orbits before the pass: an along-track impulse
# changes the radial position most there, and for a near head-on pass only the
# radial offset changes the miss -- along-track displacement mostly moves the
# time of closest approach.
LEAD_HALF_ORBITS = (1, 3, 5, 7)
MAGNITUDES_MPS = (0.10, 0.25, 0.50)
DIRECTIONS = ("PROGRADE", "RETROGRADE")
RESCREEN_HOURS = 12.0
STEP_S = 60.0
LIST_KM = 5.0


class AvoidanceError(ValueError):
    """The requested pass could not be assessed."""


def _rtn(r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rows are radial, along-track, normal unit vectors; works on (3,) or (N,3)."""
    r, v = np.atleast_2d(r), np.atleast_2d(v)
    radial = r / np.linalg.norm(r, axis=1, keepdims=True)
    normal = np.cross(r, v)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    along = np.cross(normal, radial)
    return np.stack([radial, along, normal], axis=1)


def _cw(dv_kms: float, tau_s: np.ndarray, n: float) -> tuple[np.ndarray, np.ndarray]:
    """Radial and along-track displacement (km) after an along-track impulse."""
    tau = np.maximum(np.asarray(tau_s, dtype=float), 0.0)
    radial = 2.0 * dv_kms / n * (1.0 - np.cos(n * tau))
    along = dv_kms / n * (4.0 * np.sin(n * tau) - 3.0 * n * tau)
    return radial, along


def _option_id(lead: int, direction: str, dv: float) -> str:
    return f"l{lead:03d}_{'pro' if direction == 'PROGRADE' else 'ret'}_{int(round(dv * 1000)):03d}"


def _displaced(sat, start, t_s: np.ndarray, burn_t_s: float, dv_kms: float, n: float):
    """SGP4 position of the satellite plus the CW displacement of one burn."""
    r, v = tracking._sgp4_many([sat], start, np.atleast_1d(t_s))
    r, v = r[0], v[0]
    radial, along = _cw(dv_kms, np.atleast_1d(t_s) - burn_t_s, n)
    frame = _rtn(r, v)
    return r + radial[:, None] * frame[:, 0] + along[:, None] * frame[:, 1], v


def assess(protected_norad: int, debris_norad: int, tca_utc: str) -> dict:
    from sgp4.api import Satrec

    provenance, objects = tracking.load_catalog()
    by_id = {o.norad_id: o for o in objects}
    if by_id.get(protected_norad, None) is None or by_id[protected_norad].role != "PROTECTED":
        raise AvoidanceError(f"{protected_norad} is not a protected satellite in the catalogue")
    if by_id.get(debris_norad, None) is None:
        raise AvoidanceError(f"{debris_norad} is not in the catalogue")

    try:
        tca_guess = datetime.fromisoformat(tca_utc)
    except ValueError as exc:
        raise AvoidanceError(f"tca_utc is not an ISO timestamp: {tca_utc!r}") from exc
    start = tca_guess - timedelta(hours=4)

    sat = Satrec.twoline2rv(by_id[protected_norad].line1, by_id[protected_norad].line2)
    target = Satrec.twoline2rv(by_id[debris_norad].line1, by_id[debris_norad].line2)
    found = tracking._refine(sat, target, start, 4 * 3600.0, 120.0)
    if found is None:
        raise AvoidanceError("SGP4 could not propagate this pair to the requested time")
    t_ca, miss_km, speed = found
    rel_r, rel_v = tracking._pair_state(sat, target, start, t_ca)
    unit = rel_v / np.linalg.norm(rel_v)
    r_sat, v_sat = tracking._sgp4_many([sat], start, np.array([t_ca]))
    frame = _rtn(r_sat[0, 0], v_sat[0, 0])[0]
    radius = float(np.linalg.norm(r_sat[0, 0]))
    a = 1.0 / (2.0 / radius - float(v_sat[0, 0] @ v_sat[0, 0]) / MU_KM3_S2)
    n = float(np.sqrt(MU_KM3_S2 / a**3))

    period_min = 2.0 * np.pi / n / 60.0
    leads = [int(round(h * period_min / 2.0)) for h in LEAD_HALF_ORBITS]

    # ---- every option, by the encounter-plane estimate ----------------------
    options = []
    for lead in leads:
        for direction in DIRECTIONS:
            for dv in MAGNITUDES_MPS:
                signed = dv / 1000.0 * (1.0 if direction == "PROGRADE" else -1.0)
                radial, along = _cw(signed, np.array([lead * 60.0]), n)
                shift = radial[0] * frame[0] + along[0] * frame[1]
                shifted = rel_r - shift
                predicted = float(np.linalg.norm(shifted - (shifted @ unit) * unit))
                options.append({
                    "option_id": _option_id(lead, direction, dv),
                    "lead_minutes": lead,
                    "direction": direction,
                    "delta_v_mps": dv,
                    "displacement_km": round(float(np.linalg.norm(shift)), 3),
                    "predicted_miss_km": round(predicted, 3),
                    "qualifies": predicted >= COMFORTABLE_KM,
                })
    options.sort(key=lambda o: (not o["qualifies"], o["delta_v_mps"], -o["predicted_miss_km"], o["lead_minutes"]))
    # Doing nothing goes first: a pass already clear of the comfortable margin
    # needs no burn, and recommending one would spend fuel to look busy.
    options.insert(0, {
        "option_id": "no_burn",
        "lead_minutes": 0,
        "direction": None,
        "delta_v_mps": 0.0,
        "displacement_km": 0.0,
        "predicted_miss_km": round(miss_km, 3),
        "qualifies": miss_km >= COMFORTABLE_KM,
    })

    # ---- independent re-screen of the qualifying options ---------------------
    earliest = t_ca - max(leads) * 60.0
    span_end = t_ca - min(leads) * 60.0 + RESCREEN_HOURS * 3600.0
    grid = np.arange(earliest, span_end + STEP_S / 2, STEP_S)
    debris = [o for o in objects if o.role == "DEBRIS"]
    debris_sats = [Satrec.twoline2rv(o.line1, o.line2) for o in debris]
    rd, vd = tracking._sgp4_many(debris_sats, start, grid)
    far = 1e9
    trees = [cKDTree(np.where(np.isfinite(rd[:, k]), rd[:, k], far)) for k in range(grid.size)]
    capture = LIST_KM + tracking.MAX_RELATIVE_SPEED_KMS * STEP_S / 2.0

    def rescreen(option: dict) -> list[dict]:
        signed = option["delta_v_mps"] / 1000.0 * (1.0 if option["direction"] == "PROGRADE" else -1.0)
        burn_t = earliest if option["direction"] is None else t_ca - option["lead_minutes"] * 60.0
        window = (grid >= burn_t) & (grid <= burn_t + RESCREEN_HOURS * 3600.0)
        rs, vs = _displaced(sat, start, grid, burn_t, signed, n)
        estimates: dict[int, list[float]] = {}
        for k in np.flatnonzero(window):
            hits = trees[k].query_ball_point(rs[k], r=capture)
            if not hits:
                continue
            j = np.asarray(hits)
            dr, dvel = rd[j, k] - rs[k], vd[j, k] - vs[k]
            tau = -np.sum(dr * dvel, axis=1) / np.sum(dvel * dvel, axis=1)
            miss = np.linalg.norm(dr + dvel * tau[:, None], axis=1)
            keep = (np.abs(tau) <= STEP_S * 0.6) & (miss < LIST_KM + tracking.LINEAR_MARGIN_KM)
            for jj, t_est in zip(j[keep], grid[k] + tau[keep]):
                estimates.setdefault(int(jj), []).append(float(t_est))
        passes = []
        for jj, times in estimates.items():
            times.sort()
            groups = [times[0]] + [t for p, t in zip(times, times[1:]) if t - p > 2 * STEP_S]
            for t_est in groups:
                def squared(t, jj=jj):
                    pos, _ = _displaced(sat, start, np.array([t]), burn_t, signed, n)
                    other, _ = tracking._sgp4_many([debris_sats[jj]], start, np.array([t]))
                    d = other[0, 0] - pos[0]
                    return float(d @ d) if np.all(np.isfinite(d)) else np.inf
                coarse = np.arange(t_est - 15.0, t_est + 15.5, 1.0)
                values = [squared(t) for t in coarse]
                best = float(coarse[int(np.argmin(values))])
                result = minimize_scalar(squared, bounds=(best - 1.0, best + 1.0), method="bounded",
                                         options={"xatol": 1e-3})
                t_min = float(result.x) if result.fun <= min(values) else best
                d_min = float(np.sqrt(min(result.fun, min(values))))
                if d_min > LIST_KM or t_min < burn_t:
                    continue
                passes.append({
                    "debris": {"norad_id": debris[jj].norad_id, "name": debris[jj].name,
                               "event": tracking.EVENT_LABELS.get(debris[jj].group, debris[jj].group)},
                    "tca_utc": (start + timedelta(seconds=t_min)).isoformat(timespec="milliseconds"),
                    "miss_km": round(d_min, 3),
                    "is_assessed_pass": debris[jj].norad_id == debris_norad and abs(t_min - t_ca) < 300.0,
                })
        return sorted(passes, key=lambda p: p["miss_km"])

    recommended = None
    for option in options:
        if not option["qualifies"]:
            continue
        passes = rescreen(option)
        option["rescreen"] = passes
        worst = passes[0]["miss_km"] if passes else None
        option["rescreen_closest_km"] = worst
        blocking = [p for p in passes if p["miss_km"] < COMFORTABLE_KM]
        option["verdict"] = "BLOCK" if blocking else "PASS"
        if blocking:
            option["blocked_by"] = blocking[0]
        assessed = next((p for p in passes if p["is_assessed_pass"]), None)
        if assessed is not None:
            option["rescreen_assessed_miss_km"] = assessed["miss_km"]
        if option["verdict"] == "PASS":
            recommended = option
            break

    return {
        "mode": "SGP4_CW_ASSESSMENT",
        "conjunction": {
            "protected": {"norad_id": protected_norad, "name": by_id[protected_norad].name},
            "debris": {"norad_id": debris_norad, "name": by_id[debris_norad].name,
                       "event": tracking.EVENT_LABELS.get(by_id[debris_norad].group, by_id[debris_norad].group)},
            "tca_utc": (start + timedelta(seconds=t_ca)).isoformat(timespec="milliseconds"),
            "miss_km": round(miss_km, 3),
            "relative_speed_kms": round(speed, 3),
        },
        "orbital_period_minutes": round(period_min, 1),
        "floor_km": FLOOR_KM,
        "comfortable_km": COMFORTABLE_KM,
        "option_count": len(options),
        "options": options,
        "recommended_option_id": recommended["option_id"] if recommended else None,
        "rescreen": {"hours_after_burn": RESCREEN_HOURS, "fragments": len(debris), "step_s": STEP_S},
        "note": (
            "Linearised estimate on public element sets: SGP4 geometry, "
            "Clohessy-Wiltshire displacement for an instantaneous along-track "
            "burn, and a re-screen of the manoeuvred trajectory against every "
            "catalogued fragment. No covariance, so no probability. A decision "
            "aid for where to look, not an operational manoeuvre plan."
        ),
    }


_CACHE: dict[tuple, dict] = {}
_LOCK = threading.Lock()


def cached_assess(protected_norad: int, debris_norad: int, tca_utc: str) -> dict:
    key = (protected_norad, debris_norad, tca_utc)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    result = assess(protected_norad, debris_norad, tca_utc)
    with _LOCK:
        if len(_CACHE) > 32:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = result
    return result
