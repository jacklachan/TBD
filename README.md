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

**Temporary name.** "Satellite Demo" is a placeholder, not a brand.

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
python -m pytest tests/ -q    # 191 tests after frontend integration
```

```bash
python scripts/demo_pipeline.py       # the whole decision chain, no UI, no model
uvicorn backend.api:app --port 8000   # the API
python scripts/live_api_check.py      # 20 checks end to end against the live model
```

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
python -m pytest tests -q                    # 191 tests
npm --prefix frontend test                  # 7 unit tests
npm --prefix frontend run test:browser      # running API + Vite; Chrome installed
```

The browser suite includes four real numerical-workflow checks and an optional scripted-agent fixture. [Frontend verification and handoff](Handoff/FRONTEND.md) records how to run that fixture, screenshots, and the limits of the checks. [Asset attribution](frontend/ASSETS.md) records the supplied design, NASA imagery and library licenses.

## Verified

| | |
|---|---|
| Propagation vs an independent DOP853 reference | 1.155e-06 m over one orbit |
| Energy and angular-momentum drift over six hours | below 4.1e-14 relative |
| Independent verifier vs the search path | agree to 3.4e-08 m and 1.4e-08 s |
| Live planner | `PROPOSAL_READY` in 5 model calls, 14.6 s through the API |
| Live constraint change | "halve the fuel budget" → 0.2 to 0.1 m/s, computed by the backend |
| Whole decision chain, no model | 1.24 s for 25 options, five validations and a verified answer |

Full evidence, including what is still unverified, is in [Handoff/STATE.md](Handoff/STATE.md).

## How it is put together

```
backend/core/        propagation, trajectories, encounter detection — numpy only
backend/planning/    the 25-option grid, primary screening, independent verifier
backend/agent/       provider seam, five tools, bounded planner, reviewer, memory
backend/api.py       HTTP surface, version gating, approval, export
scenarios/           the generator and four asserted fixtures
```

Three rules shape most of the design:

**The search is not the verifier.** Screening covers the object that triggered the case; the verifier rebuilds from raw scenario data, scans at a different rate with a different method, and screens every object. A test parses the module and fails if anyone imports one into the other.

**The model never supplies a number.** Every figure on screen comes from a typed field the backend computed. A scanner flags any figure in the model's prose that appears nowhere in the evidence.

**The model cannot approve anything.** Approvability is read off validation results. A model that recommends an unvalidated or rejected option produces an unresolved case, not a proposal.

## Working on it

[Handoff/README.md](Handoff/README.md) is the entry point for the team: current state, contracts, and a file per builder. [Handoff/reference](Handoff/reference/README.md) preserves the original planning documents, superseded by the current package.
