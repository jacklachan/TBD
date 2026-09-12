# Satellite Demo — engineering specification

Current scope: [plan.md](plan.md). Shared fields and APIs: [CONTRACTS.md](CONTRACTS.md). This document describes future implementation; it does not scaffold source files.

## Planned source layout and ownership

All paths below are relative to the future repository root. Build application code beside `Handoff/`, not inside it.

```text
backend/
  config.py                    C: display name, model ID, runtime settings
  domain/models.py             A+B+C: shared Pydantic contracts
  core/
    kepler.py                  A: Stumpff functions and vectorized propagation
    trajectory.py              A: immutable arcs and instantaneous impulses
    encounters.py              A: search-path scan and root refinement
  planning/
    candidates.py              A: stable candidate IDs and finite grids
    search.py                  A: primary screening, policy checks, ranking
    verifier.py                A: separate reconstruction and all-object screening
  agent/
    llm.py                     C: single Gemini adapter
    tools.py                   C: five flat declarations, validation, dispatch
    planner.py                 C: bounded tool loop and proposal selection
    reviewer.py                C: separate evidence reviewer with a blocking verdict
    memory.py                  C: small relevant-prior-case query
  api.py                       C: HTTP endpoints, versions, run coordination
  store.py                     C: SQLite transactions, events, approval, export
scenarios/
  gen.py                       A: seeded backward construction and assertions
  primary.json                 A: generated signature fixture
  variants/                    A: four additional asserted scenario fixtures
  seed_tle.txt                 A: once-fetched source, not present yet
  seed_provenance.json          A: real epoch, source, hash, conversion details
data/context/
  socrates_snapshot.csv         C: once-fetched raw source, not present yet
  socrates_provenance.json      C: snapshot timestamp, source URL, hash
scripts/
  fetch_snapshots.py            A+C: explicit manual acquisition; no runtime fetch
  demo_pipeline.py              A+C: Gate 2 command-line workflow
tests/
  test_kepler.py                A: four Gate 1 checks
  test_encounters.py            A: endpoints, burns, narrow and secondary encounters
  test_scenarios.py             A: generated scenarios and actual candidate results
  test_verifier.py              A+C: independent path, errors and disagreement
  test_policy.py                C: parsed limits, validation, confirmation
  test_workflow.py              C: versions, duplicates, reset, export, injection
frontend/
  src/
    config.ts                  B: temporary display name
    contracts.ts               B+C: transport types aligned with models.py
    api.ts                     B+C: typed HTTP client and stale-response protection
    Workbench.tsx              B: case state and component composition
    components/
      SeparationChart.tsx      B: evidence chart and encounter annotations
      OptionsTable.tsx         B: provisional/verified/rejected candidates
      ConstraintInput.tsx      B: sentence, policy preview, confirmation
      AgentTrace.tsx           B: real events and timings
      ContextPanel.tsx         B: dated SOCRATES snapshot
      DecisionActions.tsx      B: approve, reset, export
    scene/
      OrbitScene.tsx           B: Earth and moving objects
      SatelliteModel.tsx       B: procedural body, solar panels, optional GLB
      SimulationClock.ts       B: shared selected time and playback
      DistanceLine.tsx         B: selected-pair separation at one shared time
      TimeScrubber.tsx          B: playback and exact encounter jumps
  public/models/               B: optional licensed GLB and attribution
Handoff/                       All: current documentation and role updates
```

Use descriptive modules and short responsibility comments. Add package initialization and dependency files when implementation begins. Do not create empty modules now just to resemble this diagram.

## Task 1 — shared contracts and runtime proof (hour 0–1)

Owners: all three; C coordinates integration. Deliverables: `backend/domain/models.py`, matching fixture/transport shapes, one real Gemini tool round trip.

- [ ] Read CONTRACTS.md together and resolve any proposed field changes before splitting up.
- [ ] Implement strict finite-number, vector-length, time-window and version validation.
- [ ] Keep model output separate from simulation truth and from application commands.
- [ ] Confirm an available Gemini model and SDK with one handwritten flat tool declaration. Store secrets only in environment configuration.
- [ ] Record the exact successful model, SDK, latency, and any failed attempts in C's handoff.

## Task 2 — numerical core and Gate 1 (hour 1–3)

Owner: A. `core/` has no HTTP, LLM, policy, persistence, or provider dependencies. NumPy performs vector operations; SciPy provides reference integration and encounter refinement.

Use universal-variable Kepler propagation for a supported near-circular bound LEO, with positive and negative time offsets. Implement small-argument Stumpff series, explicit convergence tests, a bounded iteration count, and finite-result checks. Return an explicit numerical failure on nonconvergence or unsupported states.

Review the archived snippet rather than copying it unchanged: after the final Newton update, recompute the functions used in the final state; handle zero/empty time arrays; set explicit `rtol` and `atol` for invariants. A floating-point implementation is not exact merely because its underlying equations are analytic.

Trajectory arcs are immutable by behavior: copy input arrays, prevent mutation of stored states, return a new trajectory on a burn. A frozen dataclass alone does not make a NumPy array immutable. Position is continuous at the burn; velocity jumps by the applied vector. At the burn timestamp, select the post-burn arc for state queries.

Four checks for `tests/test_kepler.py`:

| Check | Required evidence |
|---|---|
| Independent reference | Compare against DOP853 solving Cartesian two-body ODEs on fixed supported orbits; maximum position norm error < 0.001 m. Tighten reference tolerances until reference change is comfortably below that threshold; record settings |
| Circular closure | After one computed period, position returns within 0.001 m |
| Conservation | Relative energy and angular-momentum-norm drift <= 1e-12 on sampled unforced arcs; report observed error |
| Impulse behavior | Zero burn agrees with baseline within explicit numerical tolerance; nonzero burn preserves position and changes velocity by the specified vector at the same time |

Include backward/forward consistency in the reference check because generation uses negative time. These assertions are acceptance criteria, not a promise of automatic success.

## Task 3 — encounter detection and scenario generation (hour 3–5)

Owner: A. Search path samples at five seconds, includes both horizon endpoints, partitions at every burn epoch, and separately evaluates burn-time separation. Identify local approach brackets and refine stationary points using relative-position dot relative-velocity sign changes. Validate bracket direction and compare the refined separation with endpoints. Flat or degenerate encounters must be handled explicitly.

A coarse grid is not a general proof that no encounters were missed. Exercise narrow encounters and boundary cases against a denser independently implemented check on the supported scenario family.

Generate debris backward from target encounters. Seed the satellite from DATA.md; target the first encounter around 16200 s. Validate debris bound orbit, eccentricity < 0.05 and perigee altitude > 200 km using the documented Earth radius. Reproduce the intended event on forward propagation within 1 m and 0.01 s for the generator's supported cases.

Determine the highest-ranked primary-qualified candidate first. Construct the second object near that candidate around 19800 s, then verify three facts over the full horizon: baseline clears the second object, the chosen candidate violates its floor, and another candidate satisfies both objects and policy. Use a fixed RNG seed and bounded retries, at most 200 attempts. Record actual results; fail generation if assertions do not hold. Never hardcode a candidate's verdict from its ID.

## Task 4 — search and separate verifier (hour 5–7; Gate 2 at six)

Owner: A. C supplies the CLI integration. Precompute unmodified debris samples within a scenario version; recompute the maneuvered satellite. Include baseline in every result.

Rank primary-qualified candidates by minimum delta-v, then greater primary minimum separation, then earlier burn, then stable candidate ID. These results are provisional. Only all-object validation can make an option approvable.

Verifier rules:

- Input is raw serialized scenario plus Candidate and active Policy; rebuild trajectories afresh.
- Do not import `planning.search`, reuse its candidate evaluator, use its cached results as evidence, or call `core.encounters` for the verifier's encounter search.
- Use a separate one-second scan, burn/horizon boundary checks, and bounded scalar minimization of squared distance in candidate minimum intervals.
- Screen the satellite against both debris objects over the full six hours, and independently check burn time, magnitude, and protected windows.
- Sharing the tested Kepler/trajectory primitives is permitted and disclosed. Gate 1 independently checks propagation; verifier independence is at the reconstruction/screening layer.
- Compare matching primary encounters with the search: <= 1 m separation difference and <= 0.1 s time difference. If minima are tied/flat, explicitly report ambiguity; do not invent a unique matching time.
- Any disagreement, numerical error, missing object, version mismatch, or constraint failure blocks approval.

Gate 2 evidence comes from `python scripts/demo_pipeline.py`: actual initial count, first provisional candidate, computed secondary veto, and an independently accepted alternative.

## Task 5 — bounded agent and complete workflow (hour 5–14)

Owner: C. Implement the five tools and policy phases in CONTRACTS.md. Use one available Gemini model initially. Keep prompts/results compact; tool responses contain summaries and evidence IDs, not every trajectory sample.

Planner: briefing → finite evaluation → candidate selection → validation → reject/reselect or propose. A rejected candidate cannot be approved. At most three validation attempts, one permitted grid expansion, and a configured overall timeout. Log actual tool and model calls rather than claiming an exact fixed turn count.

A separate reviewer reads validated evidence and policy and returns a typed allow/block decision with reason codes. It may block, but it cannot override deterministic failure. Do not manufacture a reviewer veto for the demo; exercise a real reviewer-policy violation in a test case and display actual results.

Natural language is interpreted into a structured proposed policy diff. The application computes relative changes such as halving; the operator confirms before mutation. Missing ground-pass times require a clarification or a named window already in the scenario. Budget reduction does not simulate a physically failed thruster.

Use small SQLite case-memory retrieval by applicable constraint tags and scenario family. Cite the prior case ID and show a suggested constraint; never silently apply a different operator's historical limits.

Only verified typed fields populate numerical UI/report values. Prefer evidence-linked explanation templates with a short qualitative model rationale. A numeric-literal scanner is a supplementary check, not a complete hallucination guarantee.

Version every proposal, result, and request. Confirmed policy changes invalidate pending proposals. Approval runs in a transaction, checks the active versions and all vetoes, and creates one simulated execution record. Duplicate requests return the same record; they must not apply the impulse twice. A committed historical execution remains history when later policy changes.

## Task 6 — chart and moving 3D product (hour 1–14)

Owner: B, joined by A after numerical stabilization. Follow DASHBOARD.md. Build the chart before the 3D renderer. Fixture data is acceptable during integration only when marked and excluded from claimed live runs.

Three.js/React Three Fiber renders the backend's positions. A procedural satellite and two debris markers are sufficient. The 3D model is appearance; backend trajectories are motion. No Blender-authored orbital animation, CSS circular motion, decorative evasive swerve, or separate frontend physics calculation.

Both global and close-approach camera views retain one consistent spatial scale within each view. Move the camera/coordinate origin to inspect the encounter; do not stretch the separation. Finish the stated playback, distance line, chart linking, and stale-response handling before custom asset polish.

## Task 7 — verification and freeze (hour 14–20)

Owners: all. Run the five scenarios and the relevant tests from the repository root once code exists: `python -m pytest tests/`. Record real commands and outputs; adjust startup/package commands to the created dependency configuration rather than pretending the project is runnable now.

Check chart/3D agreement, exact burn/encounter timestamps, numerical failures, live API failure, malformed policy, unknown IDs, injected scenario text, stale response rejection, duplicate approval, export provenance, reset, and reload. Repeat on a second machine. Record full live latency and any cache use.

Freeze at sixteen. The remaining four hours are for rehearsal, artifact capture, bug fixes, and submission. A diagram, demo recording, README claim, or passing unrelated test cannot substitute for a missing gate.
