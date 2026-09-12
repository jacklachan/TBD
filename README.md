---
title: Orion West
emoji: 🛰️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Orion West

A satellite is predicted to pass too close to a piece of debris. This decides what to do about it, and shows its working.

The interesting part is what happens next. The cheapest manoeuvre that clears the original threat turns out to put the satellite **523 m from a second object** — so an independent check rejects it, and the planner finds one that clears both. Then an operator can halve the fuel budget in plain English, and the system re-solves and reports honestly that nothing is left that works.

## Against the problem statement

> *Space Tech & Orbital Sustainability: Build autonomous agents to track space debris, optimize satellite maneuver planning, or coordinate open-source orbital traffic management to protect global communication infrastructure.*

| Clause | Where it lives | How far it goes |
|---|---|---|
| **Autonomous agents** | `backend/agent/` | A bounded planner with six tools, a safety reviewer that can veto, case memory, and plain-English constraint interpretation. It can design a burn of its own rather than only pick one off the grid — and a designed burn passes through the identical independent check, so the freedom costs no safety. Approvability is read off typed results, so the model cannot approve anything — that is enforced in code, not in a prompt. |
| **Track space debris** | `data/context/`, the Real-world context panel | A frozen CelesTrak SOCRATES snapshot: 25 real predicted conjunctions with real object names, times and miss distances. It is displayed and dated, and it drives nothing. Separately, `POST /ingest/tle` screens element sets you paste — real orbits, evaluated at one shared epoch, screened by the same two paths. That is a screen you drive, not a catalogue-wide one we run. |
| **Optimize satellite manoeuvre planning** | `backend/planning/`, `backend/core/` | The core. 25 options screened against the primary threat, then independently re-verified against every object over the full horizon by a separate code path at a finer step. The two paths agree to 3.6e-08 m. The planner may also design a burn the grid does not contain; that burn is screened by both paths too, agreeing to 7.7e-10 m. |
| **Coordinate open-source orbital traffic management** | `backend/interop.py`, `?format=cdm`, `POST /interop/verify-cdm` | A decision leaves as a CCSDS-shaped Conjunction Data Message **carrying the state vectors and the manoeuvre, not just the conclusion** — and the receiving endpoint throws the conclusions away and recomputes the encounter from those states with the same verifier that gates our own proposals. The receiver does not have to trust the sender. `python scripts/interop_demo.py` shows the exchange, including a tampered record being caught. |
| **Protect global communication infrastructure** | The same SOCRATES snapshot | **19 of the 25 real conjunctions we ship involve a communications satellite** — Starlink, Iridium, Kinéis — mostly against Fengyun 1C and Cosmos break-up debris. The constellations carrying global connectivity share these shells with the debris. |

### What we did not build, and why

The statement offers three tracks joined by *or*. We went deep on manoeuvre planning rather than wide across all three, and the gaps are worth naming rather than glossing:

- **No catalogue screening.** You can paste up to twelve real objects and we will screen them; we do not screen eighteen thousand. And the caveat that keeps us from claiming more is unchanged: public element sets are roughly a kilometre accurate at epoch, the same order as the clearance floor we enforce, and our propagation from that epoch is two-body rather than SGP4. A pasted screen is a reason to look, not a prediction, and the UI says so.
- **No multi-operator negotiation.** One operator, one spacecraft, and no automated protocol between agents. Coordination here means a record another operator can independently *check* — which is the part that actually blocks trust — not a negotiation.
- **No collision probability, anywhere.** A conforming CDM carries a covariance for each object and public element sets do not have one. We report deterministic simulated separation and say what was screened. The CDM export states this in its own header.

### The argument connecting the slice to the whole

Orbital traffic management does not usually fail for want of a protocol. It fails because one operator cannot tell whether another operator's proposed manoeuvre is safe — and the expensive part of answering that is verification, not messaging.

This is the demonstration: the cheapest manoeuvre that fixes the original encounter puts the satellite 523 m from a second object, an independent check catches it, and the option that survives costs twice the fuel.

Then that decision leaves as a record another operator can verify for themselves — and if the record overstates its clearance, they find out by recomputing it, not by trusting it. A claim that can be checked is the unit of work traffic coordination is actually made of.

## What is real and what is not

| | |
|---|---|
| Satellite's starting orbit | **Real** — NOAA 20 (JPSS-1), NORAD 43013, from CelesTrak, parsed from the committed element set |
| Both debris objects, every close approach | **Synthetic**, constructed backward from an encounter and verified by forward propagation |
| "Real conjunctions this week" panel | **Real** — 25 published close approaches from CelesTrak SOCRATES Plus |

The orbit is realistic. The encounter is constructed. Those are different claims and the product never blurs them.

No collision probability is computed anywhere. Separations are deterministic values under a two-body model over a six-hour horizon. Execution is simulated; nothing is transmitted to any spacecraft.

## Running it

```bash
pip install -r requirements-dev.txt  # Python 3.12+
cp .env.example .env          # then put your GEMINI_API_KEY in it
python -m pytest tests/ -q    # 270 tests
```

```bash
python scripts/demo_pipeline.py       # the whole decision chain, no UI, no model
uvicorn backend.api:app --port 8000   # the API
python scripts/live_api_check.py      # 20 checks end to end against the live model
python scripts/diagnose.py            # pre-demo gate: data, numerics, build, tests
```

Two narrated terminal walkthroughs, for showing the argument without the UI:

```bash
python scripts/collision_demo.py --offline   # a strike, and the grid's poor answer
python scripts/collision_demo.py             # + the burn the agent designs instead
python scripts/interop_demo.py               # a record issued, checked, and tampered with
```

Export a decision as JSON, Markdown or a CCSDS-shaped CDM:
`GET /cases/{id}/export?format=cdm`.

Deployment to Hugging Face Spaces: [DEPLOY.md](DEPLOY.md).

## The interactive workspace

Use Node.js 24 and Python 3.12+. Build the frontend before starting the server:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The server serves both the API and the production frontend. For frontend development, keep the API on port 8000 and run `npm --prefix frontend run dev`; Vite opens port 5173 and proxies API requests.

The workspace includes a rotatable 3D globe, an inspectable procedural spacecraft, exact encounter jumps, shared-clock playback, a separation chart, a 25-option comparison table, manual budget changes, AI restriction preview/confirmation, reviewed simulated approval, reset and evidence export. The numerical comparison works without an API key and is labeled separately from AI runs. Set `GEMINI_API_KEY` on the backend to use the real planner. Remote access also requires `DESK_ACCESS_TOKEN`; the browser asks for the operator token and keeps it in memory only.

```bash
python -m pytest tests -q                    # 270 tests
npm --prefix frontend test                  # 7 unit tests
npm --prefix frontend run test:browser      # running API + Vite; Chrome installed
```

The browser suite includes four real numerical-workflow checks and an optional scripted-agent fixture. [Frontend verification and handoff](Handoff/FRONTEND.md) records how to run that fixture, screenshots, and the limits of the checks. [Asset attribution](frontend/ASSETS.md) records the supplied design, NASA imagery and library licenses.

## Verified

Every figure below is printed by a test or a script in this repository, not quoted from memory.

| | |
|---|---|
| Propagation vs an independent DOP853 reference | 1.155e-06 m over one orbit |
| Six hours backward then forward again | 8.2e-07 m from where it started |
| Energy and angular-momentum drift over six hours | below 4.1e-14 relative |
| Independent verifier vs the search path, 6 options | agree to 2.5e-08 m and 1.4e-08 s |
| The same check on a burn the planner designed | 1.5e-09 m and 5.2e-09 s |
| A conjunction record recomputed by its receiver | 2 claims, worst disagreement 1.1e-03 m |
| The same record with its clearance overstated | rejected: claims 9,999 m, recomputes to 2,491.9 m |
| Live planner, signature case | `PROPOSAL_READY` in 5 model calls, 14.6 s through the API |
| Live planner, collision case | designs past the grid's 11.4 m margin to 1,375–1,990 m, reviewer ALLOW, 22–45 s over five runs |
| Live constraint change | "halve the fuel budget" → 0.2 to 0.1 m/s, computed by the backend |
| Whole decision chain, no model | 1.24 s for 25 options, five validations and a verified answer |
| Ten people opening the workspace at once | every request served, nothing refused |

270 Python tests, 10 browser tests, 7 frontend unit tests. `python scripts/diagnose.py` runs the pre-demo gate and exits non-zero if anything is broken.

Full evidence, including what is still unverified, is in [Handoff/STATE.md](Handoff/STATE.md).

## How it is put together

```
backend/core/        propagation, trajectories, encounter detection — numpy only
backend/planning/    the 25-option grid, primary screening, independent verifier
backend/agent/       provider seam, six tools, bounded planner, reviewer, memory
backend/api.py       HTTP surface, version gating, approval, export
scenarios/           the generator and four asserted fixtures
```

Three rules shape most of the design:

**The search is not the verifier.** Screening covers the object that triggered the case; the verifier rebuilds from raw scenario data, scans at a different rate with a different method, and screens every object. A test parses the module and fails if anyone imports one into the other.

**The model never supplies a number.** Every figure on screen comes from a typed field the backend computed. A scanner flags any figure in the model's prose that appears nowhere in the evidence.

**The model cannot approve anything.** Approvability is read off validation results. A model that recommends an unvalidated or rejected option produces an unresolved case, not a proposal.

## Working on it

[Handoff/README.md](Handoff/README.md) is the entry point for the team: current state, contracts, and a file per builder. [Handoff/reference](Handoff/reference/README.md) preserves the original planning documents, superseded by the current package.
