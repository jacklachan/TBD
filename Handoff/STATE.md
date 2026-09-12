# Satellite Demo — current state and decisions

Revision 2, 12 September 2026. This records documentation decisions, not measured application performance.

## Current state

| Item | State |
|---|---|
| Team and duration | Confirmed: three builders, twenty hours |
| Placeholder name | Satellite Demo; repository name remains TBD |
| Current package | Complete. Entry files, plan, engineering spec, contracts, updated data and dashboard specs, and all three role handoffs are written. Nothing further is required before implementation begins |
| Application source, dependencies, deployment | Not created or installed |
| Numerical tests and generated scenarios | Not implemented or run |
| Gemini key, model availability, tool call | Not verified in this project |
| TLE and SOCRATES data snapshots | Not downloaded; acquisition is a future build task |
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

- Gate 1: command, reference method/tolerances, actual maximum position error, test result.
- Gate 2: scenario seed/hash, actual candidate count, original threat result, secondary veto, verified alternative.
- Gate 3: original policy, judge sentence, confirmed diff, changed policy version, new result, measured latency.
- Final: five-scenario results, stale/injection/idempotency checks, second-machine result, demo URL, repository commit.

No entries above are evidence of passing gates yet. Use [handoffs/TEMPLATE.md](handoffs/TEMPLATE.md) for factual updates.
