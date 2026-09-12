# Satellite Demo — current state and decisions

Revision 3, 12 September 2026. Revisions 1-2 recorded documentation decisions only. This revision adds the first measured numerical results.

## Current state

| Item | State |
|---|---|
| Team and duration | Confirmed: three builders, twenty hours |
| Placeholder name | Satellite Demo; repository name remains TBD |
| Current package | Complete. Entry files, plan, engineering spec, contracts, updated data and dashboard specs, and all three role handoffs are written. Nothing further is required before implementation begins |
| Application source, dependencies, deployment | `backend/core/`, `backend/planning/` (candidates, search), `scenarios/`, `scripts/` and `pyproject.toml` exist. `planning/verifier.py`, `agent/`, `api.py`, `store.py` and `frontend/` do not. Nothing is deployed |
| Numerical tests and generated scenarios | Gate 1 and Gate 2 passing. Candidate grid, primary search and four fixtures exist and are tested from disk. **Verifier not written** -- nothing is approvable yet |
| Gemini key, model availability, tool call | Not verified in this project |
| TLE and SOCRATES data snapshots | Both downloaded and committed. Seed: NOAA 20 (JPSS-1), NORAD 43013, epoch 2026-09-11T21:51:16Z. Context: 25 real conjunctions from SOCRATES Plus |
| Numerical accuracy and runtime latency | Acceptance targets only |
| 3D model and animation | Specified, not built |
| GitHub destination | jacklachan/TBD; documentation commit requested under Auenchanters |

The three supplied specifications and earlier plan/research are preserved under `reference/`. Current files in this folder supersede their build instructions.

## Decisions reconciled in this revision

| Issue in prior material | Current decision |
|---|---|
| Optional or removed 3D | Required synchronized moving 3D scene; chart ships first; 3D never blocks physics gates |
| Blender versus web rendering | Three.js with React Three Fiber; procedural satellite first; optional licensed GLB later |
| Existing OrbitGuard / Conjunction Decision Desk name | Our placeholder is Satellite Demo; preserve external repository names in research |
| Mixed model providers and model names | Gemini runtime behind one adapter; exact available model selected by a real early tool-call test |
| 25 burns versus the supplied 24-burn grid | 25 initial options means 24 burns plus do nothing; UI must count honestly |
| 36-hour scope or 20-hour optional cuts | Latest user schedule and gates are authoritative; physics target hour seven |
| Search verifier reusing the same evaluation | Separate reconstruction and encounter screening; shared tested propagation is disclosed |
| Exact propagation, automatic test success, 1000x speed | Two-body analytic method implemented in floating point; correctness and speed require tests and measurements |
| Code sample as ready-to-copy core | Reference only: review convergence, recompute final coefficients, explicit tolerances, supported inputs |
| Universal claims about never missing encounters | Sampling must be validated on the supported scenarios; no blanket completeness guarantee |
| Hardcoded satellite ID and example epoch | Parse them from the saved TLE; use its actual epoch for the seed state |
| Real orbit described as precise operational prediction | Real catalog seed; subsequent trajectories are a simplified simulation; no claimed real collision probability |
| Fuel quantity | Delta-v budget is the simulated fuel proxy; no kilograms or actual thruster capability is modeled |
| Fixed model/tool turn count and zero-temperature determinism | Count actual calls; bounded loop; repeated live timing measurements; no claim of deterministic LLM output |
| Pydantic schema generation claimed to always fail | Handwritten flat tool declarations are a simplification choice; validate against the selected SDK/API |

## Added in revision 2

Documentation only. No code was written, no command was run, no dataset was downloaded, and no gate evidence exists.

| File | Content |
|---|---|
| `DATA.md` | Current acquisition spec. Supersedes `reference/DATA.md`. Catalogue number and epoch are now parsed from the committed TLE rather than hardcoded; fetch ownership split (A takes the TLE, C takes SOCRATES); frame reasoning stated as reasoning rather than a measured bound; low temperature no longer described as producing deterministic model output |
| `DASHBOARD.md` | Current interface spec. Supersedes `reference/DASHBOARD.md`, which recommended cutting 3D. 3D is required; chart ships first; one shared clock; shared-sample rule; enlarged geometry labelled and excluded from separation arithmetic |
| `handoffs/A_PHYSICS.md` | Scope, hour sequence, Gate 1 and Gate 2 acceptance checks, blocking-issue table |
| `handoffs/B_PRODUCT.md` | Scope, hour sequence, chart-then-3D order, required states, blocking-issue table |
| `handoffs/C_AGENT_API.md` | Scope, hour sequence, first-thirty-minutes tool-call proof, Gate 3, blocking-issue table |
| `handoffs/TEMPLATE.md` | Update format for role files |

Two items carried into the role files as explicit warnings because they are the likeliest correctness bugs: recomputing the Stumpff and radius terms after the final Newton update before forming the Lagrange coefficients, and partitioning encounter detection at every burn epoch because velocity is discontinuous there.

## First action once implementation is requested

All three builders agree on CONTRACTS.md and create `backend/domain/models.py` together. C verifies one real Gemini tool call during the first thirty minutes. A then starts Gate 1; B starts the chart on explicitly marked fixture data.

## Evidence to add during the build

- ~~Gate 1: command, reference method/tolerances, actual maximum position error, test result.~~ **Recorded below.**
- ~~Gate 2: scenario seed/hash, actual candidate count, original threat result, secondary veto, verified alternative.~~ **Recorded below.**
- Gate 3: original policy, judge sentence, confirmed diff, changed policy version, new result, measured latency.
- Final: five-scenario results, stale/injection/idempotency checks, second-machine result, demo URL, repository commit.

Use [handoffs/TEMPLATE.md](handoffs/TEMPLATE.md) for factual updates.

## Gate 1 — passed 12 September 2026

```
$ python -m pytest tests/ -q
29 passed in 1.43s
```

Threshold 0.001 m. Reference is DOP853 on the Cartesian two-body ODE at `rtol=1e-13`, `atol=1e-9`, 400 samples over one period; the looser `rtol=1e-12` reference differs from it by more than the propagator does, so the tight reference is what the comparison is against.

| Check | Observed |
|---|---|
| Reference, circular / eccentric e=0.01 | 1.155e-06 m / 1.474e-06 m |
| Reference convergence spread, rtol 1e-12 vs 1e-13 | 1.361e-05 m / 1.751e-05 m |
| Backward 6 h then forward | 8.158e-07 m |
| Circular closure after one period | 6.975e-09 m |
| Energy drift over 6 h, relative | 4.080e-14 / 3.776e-14 |
| Angular-momentum drift over 6 h, relative | 2.011e-14 / 1.879e-14 |
| Zero impulse vs baseline | 3.084e-07 m |
| Non-zero impulse, position jump at burn | exactly 0.0 m |
| Non-zero impulse, applied delta-v error | 3.918e-13 m/s |

Encounter detection: constructed encounters recovered to ≤ 3.5e-10 s and ≤ 4.3e-08 m; the 5 s search grid matches a 0.5 s grid to printed precision at relative speeds 90 / 400 / 1500 m/s **on this scenario family**, which is a validated sampling choice and not a general completeness claim; horizon and burn-epoch boundaries classified correctly; a burn was shown to create a 300 m encounter where the baseline is 10114.3 m.

Gates 2 and 3 remain unmet. Detail and the untested surface are in [handoffs/A_PHYSICS.md](handoffs/A_PHYSICS.md).

## Gate 2 — signature case verified 12 September 2026

```
$ python scenarios/gen.py
primary  (seed 1001, 57 attempts)

$ python -m pytest tests/ -q
44 passed in 64.80s
```

Seed orbit: NOAA 20 (JPSS-1), NORAD 43013, epoch 2026-09-11T21:51:16Z, a = 7211.2 km, e = 0.001276, i = 98.78 deg. Parsed from `scenarios/seed_tle.txt`; nothing hardcodes it.

25 options evaluated (24 burns plus the baseline), 12 qualify against the primary threat.

| Fact | Value |
|---|---|
| Baseline vs DEB-1 | 133.7 m at 16234 s — below the 1000 m floor |
| Baseline vs DEB-2 | 3704.4 m — clear |
| Top-ranked option `t30_ret_100` vs DEB-1 | 2016.9 m — clears |
| Top-ranked option vs DEB-2 | **523.2 m at 20313 s — violates** |
| `t30_ret_200` vs DEB-1 / DEB-2 | 2491.9 m / 2569.0 m — clears both |

`tests/test_scenarios.py` rebuilds the trajectories from the serialized JSON and recomputes all three facts, so the fixture is checked independently of the generator that wrote it.

`no_feasible` variant: 0 of 25 options qualify, and 0 of 33 after grid widening — the agent's one permitted expansion cannot manufacture an answer.

**Update, same day:** `backend/planning/verifier.py` now exists, and the veto comes from it rather than from the generator and the tests.

It rebuilds from raw scenario JSON, scans at 1 s against the search's 5 s, refines by bounded minimisation of squared distance against the search's root-finding on range rate, and screens every debris object rather than only the primary threat. It shares the tested Kepler primitives, which is disclosed; independence is at the reconstruction and screening layer. A test parses the module with `ast` and fails if anyone imports the search path into it.

Measured agreement across six candidates: worst disagreement **3.559e-08 m** and **1.328e-08 s**, against tolerances of 1 m and 0.1 s.

`t30_ret_100` — ranked first, clears the primary threat at 2016.9 m — is returned `BLOCK` because DEB-2 sits at 523.2 m at 20313 s. `t30_ret_200` returns `PASS`.

A strong burn can be limited by an encounter it cannot affect: `t30_ret_200` and `t45_ret_200` report identical separations because the binding crossing at 999 s precedes both burns. The metric is correct; the chart must label the dip actually found.

Gate 3 is still untouched, and `scripts/demo_pipeline.py` does not exist, so Gate 2 has no single end-to-end command yet.
