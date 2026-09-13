# Satellite Demo — product and implementation plan

**Goal:** deliver one complete simulated satellite close-approach decision workflow for three builders in twenty hours.

**Architecture:** a small Python two-body engine computes the trajectories. A Gemini planner calls bounded tools; a separate deterministic screening path and a reviewer can block proposals. A React frontend presents numerical evidence and a synchronized moving 3D scene.

**Stack:** Python, NumPy, SciPy, Pydantic, FastAPI, SQLite; React, TypeScript, a familiar chart library, Three.js and React Three Fiber. Use SGP4 only to derive the initial state from a cached real TLE. Select compatible dependency versions during setup and record them.

> **Historical plan.** Written before any code existed. The application is now implemented and deployed; [STATE.md](STATE.md) and the latest session record are current. Where this file says Gemini or `backend/domain/models.py`, read GLM via Hugging Face and the owning modules under `backend/`.

**Specifications:** [CONTRACTS.md](CONTRACTS.md), [IMPLEMENTATION.md](IMPLEMENTATION.md), [DATA.md](DATA.md), [DASHBOARD.md](DASHBOARD.md).

## Product promise and boundaries

A satellite receives a close-approach warning. The app compares 25 initial options, rejects an otherwise promising option because it creates another close approach, and verifies an alternative. A judge enters a restriction such as “halve the fuel budget.” The app shows a structured policy change for confirmation and recomputes the decision.

- One maneuverable satellite, two synthetic debris objects, six hours: `horizon_s = 21600`.
- Initial options: four burn times at 15/30/45/60 minutes, two directions, three magnitudes at 0.05/0.10/0.20 m/s, plus do nothing. This is 24 burns + one baseline, not 25 burns.
- Initial clearance floor: 1000 m. It is a demo policy, not a universal operational safety standard.
- Real catalog seed and epoch; synthetic conjunctions; explicitly simplified two-body model.
- Required chart, moving 3D satellite, scrubber, same-clock distance line, options table, real tool trace, policy changes, veto/replanning, small case memory, simulated approval, reset, persistence, and JSON/Markdown export.
- Frozen SOCRATES context panel, up to ten real rows, entirely separate from the simulation.
- Under ten seconds is the measured latency target, not a guaranteed benchmark.

No global screening, real collision probability, real thruster control, model training, debris-removal robot, or multi-operator negotiation. Actual fuel mass and failed-thruster dynamics are outside the model; the example sentence changes the supported delta-v budget.

## Signature demo

1. Load the generated signature case. Do nothing violates the clearance floor near the primary encounter.
2. Rank the initial options against the primary threat and policy. Show the highest-ranked primary-qualified option as provisional.
3. The verifier rebuilds that candidate and screens the entire horizon against both debris objects. It discovers a secondary conflict, records the evidence, and blocks the proposal.
4. The planner selects and verifies an alternative. It can use a bounded grid expansion after a rejection if needed; the displayed count must then increase.
5. Show the rejected and recommended trajectories in the chart. In 3D, scrub the same clock to each computed encounter; markers, line endpoints, and distance labels agree.
6. A judge enters a new constraint. Show the proposed diff, confirm it, invalidate the old proposal, and replan. Return a newly verified choice or honest infeasibility.
7. Approve the simulated burn once, export its evidence, reload, then reset to a new case instance.

Target primary and secondary encounter times are approximately 4.5 and 5.5 hours. Distances and exact times are generator targets until numerically reproduced; never hardcode them as results.

## Three-person schedule

| Hours | A — physics | B — product and 3D | C — agent and API |
|---|---|---|---|
| 0–1 | All three agree on CONTRACTS.md and write `backend/domain/models.py`; A acquires/validates the seed snapshot | Agree fixture contract; help freeze shared types | Real Gemini tool round trip within first 30 minutes; data fetch ownership coordinated |
| 1–3 | Kepler propagation, impulses, four Gate 1 tests | Chart on explicitly marked fixture data | FastAPI, handwritten tool declarations, adapter, event storage |
| 3–5 | Encounter finder and backward scenario generator | Procedural satellite, 3D scene, shared clock and scrubber | Wire tools to evolving numerical interfaces; load cached context panel within 30-minute budget |
| 5–7 | Search and separate verifier; command-line chain by hour six; stabilize by seven | Real trajectories and verdicts in chart/3D | First full planner run with actual secondary rejection |
| 7–11 | Joins B after physics gate evidence exists | Options, trace, approach camera, plain-English controls | Policy diff/confirmation, reviewer veto, case memory; live constraint change by ten |
| 11–14 | Help approval/reset/export UI | Complete loading, failure, stale and infeasible states | Version checks, idempotent approval, export and reload |
| 14–16 | Run five scenarios and numerical checks | Second-machine check and 3D/chart agreement | Injection, stale, idempotency and live latency measurements |
| 16–20 | Feature freeze; rehearse, record, prepare submission, leave buffer | Same | Same |

Physics finishing around hour seven and roughly 400 lines are scope targets, excluding tests. Do not sacrifice validation or readable error handling to meet a line count.

## Gates and cuts

**Hour three — Gate 1:** `pytest` succeeds on the four specified numerical checks, including less than one millimetre position discrepancy against an independently converged reference on supported test orbits. If missed, A and C focus on the core; cut asset polishing, grid expansion, and extra memory behavior first. B continues the chart with marked fixtures; no invented passing result.

**Hour six — Gate 2:** command-line scenario → 25 options → secondary conflict rejected → alternative verified. Hour seven is stabilization and A's handoff, not a later Gate 2 deadline. If the trap fails, simplify its generation before adding UI effects; stop claiming the signature until it passes.

**Hour ten — Gate 3:** a real judge sentence yields a confirmed policy change and an actual new computation with new versions. A reused animation is not a pass. If latency misses the target, reduce prompt size and optional calls, and report the measured time.

**Hour sixteen:** freeze features. Keep basic synchronized 3D; cut custom Blender work, textures, cinematic transitions, and decorative effects. Any reduction of required scope is recorded in STATE.md and the pitch, rather than silently marked complete.

## First sixty minutes once build work is authorized

- [ ] Agree units, frame, field names, sample format, statuses, and ownership in CONTRACTS.md.
- [ ] Create the shared models together; keep the first fixture consistent with them.
- [ ] Complete one real Gemini request → tool arguments → local fake tool → tool response → model continuation. A text-only response does not prove tool calling.
- [ ] A fetches one satellite TLE; C obtains one SOCRATES CSV snapshot. No other teammate independently fetches the same data.
- [ ] Record provenance and commit usable snapshots; no keys in Git. If a source fails, stop automatic retries and record the missing snapshot.
- [ ] A begins Kepler tests; B begins the chart; C begins the API/tool integration.

## Five scenarios and release evidence

1. No actionable encounter: baseline is valid.
2. Primary conflict: a feasible maneuver exists.
3. Signature case: highest-ranked primary-qualified candidate creates a secondary conflict; a different candidate passes.
4. Budget halved mid-case: old proposal becomes stale; fresh solve changes the result or reports infeasibility.
5. No feasible candidate within the supported search: no approval is possible.

Each scenario records seed, schema/model version, input hash, actual assertion results, and derived distances. Also check malformed input, missing API access, injected instructions in scenario text, unknown candidate, verifier disagreement, stale approval, duplicate approval, and out-of-order frontend responses.

Measure backend computation, model time, and total user-visible time separately. Record repeated live runs, including a fresh run without a stored answer. Measure text submission to policy preview, confirmation to verified result, and total machine processing; exclude human decision time only when explicitly labeled. Loading 3D assets must not hold up the result.

## Evidence for judging

| Criterion | What the judges can inspect |
|---|---|
| Problem understanding and impact | Real catalog seed, dated real-world context, explicit operator workflow and simulation boundary |
| Innovation and creativity | Computed secondary-conflict rejection and live constraint change; no claim to invent collision avoidance |
| Agentic AI | Actual tool calls, changed plan, reviewer veto, relevant prior-case retrieval, bounded actions |
| Technical implementation | Numerical reference comparison, distinct verifier path, version checks, deterministic evidence |
| Effectiveness and usability | One complete case through approval/export, legible infeasibility, same-clock 3D and chart |
| Demo and presentation | A judge can find both close approaches, edit a restriction, and inspect the fresh result |

The first minute explains the original risk and the failed obvious fix. The second demonstrates replanning and the moving 3D scene. The third invites the judge's restriction and ends with the evidence report. Keep the chart visible while narrating the 3D.

## Team tools

A may use one Claude Pro seat, B the second, and C ChatGPT Plus; assign by human expertise. These are development assistants. This plan assumes neither a working Gemini key nor funded runtime access until the early tool test proves it. Use one available Gemini model first; a second tier/provider is not a prerequisite.
