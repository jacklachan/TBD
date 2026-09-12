# Builder A — physics, scenarios, search and verifier

Read [README.md](../README.md), [AGENTS.md](../AGENTS.md), [STATE.md](../STATE.md), [CONTRACTS.md](../CONTRACTS.md) and [IMPLEMENTATION.md](../IMPLEMENTATION.md) first. This file is your scope, sequence and acceptance checks. Nothing here is implemented yet.

## You own

```text
backend/core/kepler.py          Stumpff functions, vectorized universal-variable propagation
backend/core/trajectory.py      Immutable arcs, instantaneous impulses, states_at
backend/core/encounters.py      Search-path scan and stationary-point refinement
backend/planning/candidates.py  Stable IDs, finite grids
backend/planning/search.py      Primary screening, policy checks, ranking
backend/planning/verifier.py    Separate reconstruction and all-object screening
scenarios/gen.py                Seeded backward construction with assertions
scenarios/primary.json          Signature fixture
scenarios/variants/             Four additional asserted fixtures
scenarios/seed_tle.txt          Once-fetched, committed
scenarios/seed_provenance.json  Real epoch, source, hash, conversion detail
tests/test_kepler.py            Gate 1
tests/test_encounters.py
tests/test_scenarios.py
tests/test_verifier.py          Shared with C
```

You share `backend/domain/models.py` with B and C. You do not own the API, the agent, storage, or any frontend file.

## Hard boundaries

- `backend/core/` imports NumPy and SciPy only. No HTTP, no LLM, no policy objects, no persistence, no provider SDK.
- SI units throughout: metres, seconds, metres/second. Convert to kilometres only at display, and that is B's job.
- Frame is `SIM_ECI_TEME_SEEDED` — fixed simulation axes initialized from the epoch TEME state. This is not a claimed GCRF conversion. Do not silently mix in another frame.
- Never hardcode a distance, a time of closest approach, or a candidate's verdict. Every number in a fixture is produced by your generator and re-derived by assertion.
- The verifier may share the tested Kepler and trajectory primitives. It may **not** import `planning.search`, reuse its evaluator, read its cache, or call `core.encounters`.

## Hour 0–1 — shared contracts

- [ ] Sit with B and C, walk CONTRACTS.md, resolve field disagreements **before** anyone writes logic.
- [ ] Co-write `backend/domain/models.py`. Strict validation: finite floats, three-element vectors, `0 <= start_s < end_s <= horizon_s`, version stamps present.
- [ ] Fetch **one** satellite TLE per [DATA.md](../DATA.md). You own this fetch; C owns the SOCRATES fetch. Do not both hit CelesTrak.
- [ ] Parse the NORAD ID and epoch **out of the saved TLE**. Do not hardcode either; the archived spec's example values are illustrative only.
- [ ] Write `scenarios/seed_provenance.json`: source URL, retrieval timestamp, SHA-256 of the file, parsed NORAD ID, parsed TLE epoch, the SGP4 call used, resulting state vector.

## Hour 1–3 — Gate 1

Universal-variable Kepler propagation for supported near-circular bound LEO, positive and negative `dt`.

- [ ] Small-argument Stumpff series; do not evaluate the trigonometric forms near ψ = 0.
- [ ] Bounded Newton iteration with an explicit convergence test. Return a typed numerical failure on nonconvergence or unsupported state — never a silently wrong array.
- [ ] **Recompute `c2`, `c3` and `r` after the final Newton update** before forming the Lagrange coefficients. Using the pre-update values is the most likely correctness bug in this module.
- [ ] Handle empty and zero time arrays; `dt = 0` returns the exact input state.
- [ ] Copy input arrays into arcs. A frozen dataclass does not make a NumPy array immutable — call `.copy()` and set `flags.writeable = False`.
- [ ] `apply_impulse` returns a new `Trajectory`. Position continuous at the burn, velocity jumps by exactly the applied vector, state queries at the burn timestamp use the post-burn arc.
- [ ] Resolve direction from the **unburned** satellite velocity at burn time: prograde is its unit vector, retrograde its negative. Store the derived inertial vector in evidence. An RTN component is not an inertial vector.

**Gate 1 — `pytest tests/test_kepler.py` green, four checks:**

| Check | Evidence to record |
|---|---|
| Independent reference | vs DOP853 on Cartesian two-body ODEs, supported orbits, max position-norm error < 0.001 m. Tighten reference tolerances until further tightening moves the result well below threshold; record the settings you used |
| Circular closure | After one computed period, position within 0.001 m |
| Conservation | Relative energy and \|r × v\| drift ≤ 1e-12 on unforced arcs; **report the observed value**, not just pass/fail |
| Impulse behaviour | Zero burn matches baseline within a stated tolerance; nonzero burn preserves position and changes velocity by exactly the applied vector |

Include backward-then-forward consistency in the reference check — generation relies on negative `dt`.

> These are acceptance criteria, not a prediction. The equations are analytic; the implementation is floating point. `f·ġ − g·ḟ = 1` is a useful invariant, but assert it with explicit `rtol`/`atol`, not exact equality.

Post the actual maximum error into STATE.md when it passes. Do not mark Gate 1 from a snippet or a plan.

## Hour 3–5 — encounters and scenario generation

**Detection (search path):**

- [ ] Sample at 5 s, include both horizon endpoints, **partition at every burn epoch**, and separately evaluate separation exactly at each burn timestamp. Velocity is discontinuous there, so `Δr·Δv` jumps and an unpartitioned bracket lands wrong.
- [ ] Bracket local approaches, refine the stationary point via the sign change of `Δr·Δv`.
- [ ] Validate bracket direction and confirm the refined separation is below both endpoints. Handle flat or degenerate minima explicitly and set `ambiguous_time`.
- [ ] Set `boundary_kind` honestly: `INTERIOR`, `HORIZON` or `BURN`.

> A 5 s grid is not a general proof that nothing was missed. Exercise narrow encounters and boundary cases against a denser, independently written check on the supported scenario family, and say in the README that completeness is validated on that family only.

**Generation (backward):**

- [ ] Seed the satellite from the committed TLE state.
- [ ] Target the primary encounter near `t = 16200 s`. Place debris relative to the satellite at that instant, choose relative velocity, back-propagate to `t = 0`.
- [ ] Validate the debris orbit: bound, `e < 0.05`, perigee altitude > 200 km using `earth_radius_m = 6378137.0`.
- [ ] Forward-propagate from `t = 0` and **assert** the intended event reproduces within 1 m and 0.01 s. Fail generation loudly otherwise.
- [ ] For the trap: first determine the highest-ranked primary-qualified candidate by running your own search. Then construct object 2 near that candidate's path around `t = 19800 s`.
- [ ] Assert three facts over the full horizon: baseline clears object 2; the top candidate violates the floor against object 2; at least one other candidate satisfies both objects and policy.
- [ ] Fixed RNG seed, at most 200 bounded retries. Record the seed. If the assertions never hold, simplify the geometry — do not hand-tune a fixture.

## Hour 5–7 — search and verifier

- [ ] Precompute the two unmodified debris sample sets **once per scenario version** and reuse across all candidates. Only the manoeuvred satellite is recomputed. This is the difference between a snappy loop and a slow one.
- [ ] Baseline appears in every `SearchResult`. `candidate_count` is 25 = 24 burns + baseline; after one `widen_search` it is 33. The count you report must be the count you evaluated.
- [ ] Rank primary-qualified candidates: minimum Δv, then greater primary separation, then earlier burn, then stable candidate ID. Results are **provisional** — only all-object validation makes an option approvable.
- [ ] Policy-excluded candidates stay visible with `reason_codes`. Do not drop rows.

**Verifier:**

- [ ] Input is raw serialized scenario JSON plus `Candidate` and active `Policy`. Rebuild trajectories from scratch.
- [ ] Own 1 s scan, own boundary handling, bounded scalar minimization of squared distance inside candidate intervals.
- [ ] Screen against **both** debris objects across the full horizon. Independently re-check burn time, magnitude and protected windows.
- [ ] Compare matching primary encounters with the search: ≤ 1 m and ≤ 0.1 s. Report `max_primary_distance_disagreement_m` and `primary_time_disagreement_s` as numbers, always.
- [ ] Ties or flat minima → report ambiguity. Do not invent a unique matching time.
- [ ] Any disagreement, numerical error, missing object, version mismatch or constraint failure sets `BLOCK` or `ERROR`. None of these can produce an approvable proposal.

**Gate 2 — `python scripts/demo_pipeline.py` prints:** actual option count, the first provisional candidate, the computed secondary veto with its distance and time, and an independently accepted alternative. Command line only. No UI needed.

## Hour 7 onward

Physics stabilizes at hour seven. Hand over to C with the CLI transcript, then join B on the frontend. Stay reachable for numerical questions; do not keep extending the core.

## Hour 14–16

- [ ] Run the five scenarios; record seed, input hash, actual assertions, derived distances for each.
- [ ] `python -m pytest tests/` from the repository root; paste real output.
- [ ] Investigate any verifier disagreement rather than widening the tolerance to make it pass.

## What blocks you, and what to do

| Problem | Action |
|---|---|
| Gate 1 misses 0.001 m | Tighten the reference first — it may be the reference that is loose. Then check the final-coefficient recomputation. Do not relax the threshold silently; if you change it, record why in STATE.md |
| Newton fails to converge | Check the elliptic initial guess and `alpha`; hyperbolic or near-parabolic states are out of the supported family — reject them explicitly |
| Trap generation never satisfies all three assertions | Move the secondary encounter later, or reduce the primary miss distance. Simplify before adding retries |
| Verifier and search disagree beyond tolerance | This is a real finding, not a nuisance. Most likely cause is burn-epoch partitioning in one path but not the other |
| You finish early | Join B. Do not add drag, J2, or a third debris object |

## Update duties

After each work block, append to this file using [TEMPLATE.md](TEMPLATE.md): changed paths, commands run and their real output, checks that failed or were not run, contract changes, next concrete action. Put gate evidence in STATE.md — actual numbers, not "passed".

---

## [2026-09-12] — Builder A — numerical core and Gate 1

**Changed paths**

- `pyproject.toml` — numpy/scipy deps, pytest `pythonpath`/`testpaths`
- `backend/core/kepler.py` — Stumpff, universal-variable `propagate`, energy/angular-momentum/period helpers, `PropagationError`
- `backend/core/trajectory.py` — `Arc`, `Impulse`, `Trajectory`, `direction_unit_vector`, `impulse_vector`
- `backend/core/encounters.py` — segmented scan, brentq refinement on range rate, `Encounter`, `min_separation_series`
- `tests/test_kepler.py` — Gate 1, 18 tests
- `tests/test_encounters.py` — 11 tests

**Commands run**

```
$ python -m pytest tests/ -q
29 passed in 1.43s
```

**Gate 1 — measured, threshold 0.001 m**

| Check | Observed |
|---|---|
| DOP853 reference, circular, one period | 1.155e-06 m |
| DOP853 reference, eccentric e=0.01, one period | 1.474e-06 m |
| Reference convergence, rtol 1e-12 vs 1e-13 | 1.361e-05 m / 1.751e-05 m |
| Backward 6 h then forward | 8.158e-07 m |
| Circular closure after one period | 6.975e-09 m position, 5.349e-12 m/s velocity |
| Energy drift over 6 h (circular / eccentric) | 4.080e-14 / 3.776e-14 relative |
| Angular-momentum drift over 6 h | 2.011e-14 / 1.879e-14 relative |
| Zero impulse vs baseline | 3.084e-07 m |
| Non-zero impulse, position jump at burn | exactly 0.0 m |
| Non-zero impulse, applied delta-v error | 3.918e-13 m/s |

Reference settings: DOP853, `rtol=1e-13`, `atol=1e-9`, 400 samples over one period. The looser `rtol=1e-12` reference differs from it by more than the propagator does, so the tight reference is what the comparison is against.

**Encounter detection — measured**

- Constructed encounters recovered at three times and miss distances (120 m, 2500 m, 45 m): time error ≤ 3.5e-10 s, distance error ≤ 4.3e-08 m.
- 5 s search grid vs 0.5 s grid, relative speeds 90 / 400 / 1500 m/s: identical to printed precision. This validates the grid **on this scenario family only** and is not a general completeness claim.
- Horizon-edge minimum → `HORIZON`. Minimum at a burn epoch → `BURN`, recovered to 1.0 m. Burn epoch not double-reported.
- Burn-creates-new-encounter mechanism exercised directly: burned trajectory 300.0 m at 19800 s where the baseline is 10114.3 m.

**Not verified / not run**

- No scenario generator, candidate grid, search, or verifier yet. Gate 2 is untouched.
- No seed TLE fetched; `scenarios/` does not exist. `core/` currently has no real-catalogue input.
- `backend/domain/models.py` deliberately not written — it is the hour-0 three-builder agreement. `core/` stays pure and returns a frozen `Encounter` dataclass whose field names match CONTRACTS.md exactly, so the Pydantic model maps one-to-one.
- Only the elliptic branch of `propagate` is exercised. Unbound states raise; the hyperbolic Stumpff branch is implemented but untested.

**Contract changes**

None. `find_encounters` gained a `debris_object_id` argument so it can populate `Encounter.other_object_id`, and a `start_s` default — both additive to the CONTRACTS.md signature.

**Performance note for search.py**

A 25-option sweep against both debris objects takes 0.816 s today because `find_encounters` re-samples the debris trajectory for every candidate. Precompute the two unmodified debris sample sets once per scenario version, as the role brief says; only the manoeuvred satellite needs recomputing.

**Next concrete action**

Fetch the seed TLE per DATA.md, write `scenarios/gen.py` backward construction with its assertions, and target the primary encounter at 16200 s.
