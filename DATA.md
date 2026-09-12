# Data sources — findings and decision

Checked 12 September 2026, event day.

## Verdict

**No public dataset gives you propagatable state vectors at the fidelity this product needs.** Synthetic is the correct engineering choice here, not a fallback you apologise for. But do a **hybrid**: seed the satellite's orbit from a real catalogue object, keep the conjunction geometry synthetic, and show real conjunctions in a separate context panel.

That buys you a real NORAD ID and a real epoch on screen — which is what a non-expert judge reads as legitimacy — without giving up the control you need for verifiable outcomes.

---

## What was checked

### 1. CelesTrak GP data — **USE THIS, ONCE**

Free, no auth, real orbital elements for the whole public catalogue.

```
https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE
https://celestrak.org/NORAD/elements/gp.php?GROUP=STATIONS&FORMAT=JSON
```

Parameters: `CATNR` (catalogue number), `GROUP` (uppercase), `INTDES`, `NAME`, `SPECIAL`. Formats: `JSON`, `JSON-PRETTY`, `CSV`, `XML`, `KVN`, `TLE`, `2LE`.

> **Rate limiting is harsh and it will bite you.** CelesTrak refreshes only every 2 hours and as of March 2026 enforces a one-download-per-update policy — repeat requests return **HTTP 403**. Roughly **50 HTTP errors within 2 hours triggers a firewall block.**

**Therefore: fetch once, write to disk, commit the file, never call it again.** A live fetch anywhere in your demo path is a way to get IP-blocked during judging.

```python
# scripts/fetch_seed.py — RUN ONCE. COMMIT scenarios/seed_tle.txt.
import requests

CATNR = 43013   # pick any real LEO smallsat
r = requests.get("https://celestrak.org/NORAD/elements/gp.php",
                 params={"CATNR": CATNR, "FORMAT": "TLE"}, timeout=20)
r.raise_for_status()
open("scenarios/seed_tle.txt", "w").write(r.text)
```

Then convert once to a state vector and hand it to your own propagator:

```python
from sgp4.api import Satrec, jday
name, l1, l2 = open("scenarios/seed_tle.txt").read().splitlines()[:3]
sat = Satrec.twoline2rv(l1, l2)
e, r_km, v_kms = sat.sgp4(*jday(2026, 9, 12, 12, 0, 0))
assert e == 0
r0 = np.array(r_km) * 1000.0     # m
v0 = np.array(v_kms) * 1000.0    # m/s
```

From here your two-body simulation owns everything. `sgp4` is used exactly once, at scenario build time.

**Frame question — and the answer that saves you two hours:** SGP4 outputs TEME, your propagator is a generic inertial frame. You do **not** need the TEME→GCRF transformation, because you use the TEME state only as the *initial condition of your own self-consistent simulation* and never mix frames.

If a judge presses on this, the rigorous answer is: TEME precesses at roughly 50 arcsec/year, so over a 6-hour horizon it rotates about 0.034 arcsec ≈ 1.1 m of absolute displacement at LEO radius — and that rotation is **common-mode across all objects, so it cancels almost entirely in relative geometry**, which is the only thing we compute. Label the frame "TEME-derived, treated as inertial over the simulation horizon."

**Be precise about what the real data buys you.** TLE accuracy is ~1 km at epoch. So the claim is *"the orbit is realistic"*, never *"this conjunction is real."* Say that on screen and you are unassailable.

### 2. CelesTrak SOCRATES Plus — **USE THIS as a context panel, 30 minutes**

Real precomputed conjunction reports for the coming week: object names, catalogue numbers, TCA, minimum range, relative speed, max probability. RFC 4180 CSV. Runs three times daily, seven-day look-ahead.

This is the highest-value 30 minutes on your data side. A panel headed **"Real conjunctions predicted this week"** listing ten actual close approaches with real satellite names, sitting *next to* your simulation, does more for Problem Understanding & Impact than any slide. Display-only — no computation, no coupling to your engine.

Same rule: fetch once, commit the CSV, serve from disk.

### 3. ESA Kelvins Collision Avoidance Challenge CDM dataset — **DO NOT USE**

Genuinely real: 162,634 CDMs across 13,154 conjunction events, US Space Surveillance Network data, released by ESA for a 2019 ML competition.

Two disqualifying problems:

- **No absolute state vectors.** It has relative position/velocity in RTN at TCA, orbital elements, and covariances — 103 numerical features, all *derived*. You cannot propagate it, and you certainly cannot apply a Δv to it and recompute. It's a probability-prediction dataset, not a simulation dataset.
- **Licence is unclear.** ESA copyright with a competition-scoped release agreement, no stated general licence. Bad dependency for a judged submission.

Worth one sentence in your README to show you evaluated it and why it doesn't fit. That reads as rigour.

### 4. Space-Track.org — **NO**

Authoritative catalogue and real CDMs, but requires account approval (unpredictable latency), has a redistribution agreement, and CDMs are only available for satellites you own. Not viable mid-event.

### 5. ESA DISCOSweb — **statistic only**

Object metadata (mass, dimensions, cross-section) behind a free API token. You already cite the ~46,780 tracked-object figure from DISCOS statistics; that's all you need from it.

---

## Provenance line for the UI

One small always-visible line. Not a warning banner — a credential:

> Orbit seeded from NORAD 43013, epoch 2026-09-12 12:00 UTC (real) · Conjunction geometry synthetic · Two-body model, TEME-derived inertial frame

Non-experts read "real." Experts read the honesty. A big red SYNTHETIC DATA banner reads as an apology; this reads as a data sheet.

---

## Model / API decision

**Use the Gemini key you already have. Buy nothing today.** Procurement at hour one of a twenty-hour event is pure loss, and the differences between providers do not matter for a tool-calling loop this small.

- **Flash tier** for the planner loop — latency is what you are optimising.
- **Pro tier** only for `propose_policy`, where natural-language quality actually matters.
- `temperature=0` on the planner. Determinism supports your reproducibility claim and makes the demo behave the same on every reset.

> **The trap that will cost you 45 minutes:** Gemini's function-calling schema is an OpenAPI 3.0 subset. It rejects `$ref`, `anyOf` in most positions, `additionalProperties`, and several `format` values. `pydantic.model_json_schema()` emits all of them — `$ref` for every nested model, `anyOf` for every `Optional[X]`. You will get opaque 400s.
>
> **Write your five tool schemas by hand as flat dicts.** Keep pydantic for internal domain types and use it to validate the *arguments* Gemini returns. Both benefits, no fight.

**Build the seam, not the backup.** Thirty lines in `agent/llm.py`:

```python
def call(messages: list[dict], tools: list[dict]) -> ToolCall | Text: ...
```

One function, provider behind it. If Gemini disappoints at hour 9, swapping to Groq (fastest for the loop) or DeepSeek is a 30-minute change instead of a rewrite. Do not spend money on a second key now — spend twenty minutes on the interface.

---

## Sources

- [CelesTrak GP data formats and API](https://celestrak.org/NORAD/documentation/gp-data-formats.php)
- [CelesTrak SOCRATES Plus](https://celestrak.org/SOCRATES/)
- [ESA Kelvins Collision Avoidance Challenge — data](https://kelvins.esa.int/collision-avoidance-challenge/data/)
- [Kelvins challenge overview](https://kelvins.esa.int/collision-avoidance-challenge/)
