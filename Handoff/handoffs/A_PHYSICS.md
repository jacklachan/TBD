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

---

## [2026-09-12] — Builder A — snapshots, candidate grid, search, scenario generator

**Changed paths**

- `scripts/fetch_snapshots.py` — once-only acquisition with overwrite guard, SHA-256 provenance, `--parse-only`
- `scenarios/seed_tle.txt`, `scenarios/seed_provenance.json` — NOAA 20 (JPSS-1), NORAD 43013
- `data/context/socrates_raw.html`, `socrates_snapshot.csv`, `socrates_provenance.json` — 25 real conjunctions
- `backend/planning/candidates.py` — 25-option grid, stable IDs, revision-2 expansion to 33
- `backend/planning/search.py` — primary screening, policy reasons, ranking, `Policy`/`BurnWindow`
- `scenarios/gen.py` — backward construction, three-fact trap search, four fixtures
- `scenarios/primary.json`, `scenarios/variants/*.json`
- `tests/test_scenarios.py` — 15 tests

**Commands run**

```
$ python scripts/fetch_snapshots.py --tle --socrates
  NOAA 20 (JPSS-1) (NORAD 43013)
  25 conjunctions -> data/context/socrates_snapshot.csv

$ python scenarios/gen.py
  primary  (seed 1001, 57 attempts)

$ python -m pytest tests/ -q
44 passed in 64.80s
```

**Seed orbit, parsed from the TLE**

NOAA 20 (JPSS-1), NORAD 43013, epoch 2026-09-11T21:51:16Z. a = 7211.2 km, e = 0.001276, i = 98.78 deg, perigee altitude 823.9 km. Inside the supported family.

**Gate 2 — signature case, recomputed from the serialized fixture**

| Fact | Value |
|---|---|
| Baseline vs DEB-1 | **133.7 m** at 16234 s — below the 1000 m floor |
| Baseline vs DEB-2 | 3704.4 m — clear, 3.7x the floor |
| Top-ranked option | `t30_ret_100` (0.10 m/s retrograde at 30 min) |
| That option vs DEB-1 | 2016.9 m — clears |
| That option vs DEB-2 | **523.2 m** at 20313 s — violates |
| Option that clears both | `t30_ret_200` (0.20 m/s retrograde, same epoch) |
| Options clearing both | 8 of the 12 that qualify against the primary |
| Attempts to find the case | 57 of 200 |

The trade-off is legible: same burn time, same direction, twice the fuel to be actually safe. The trap is whatever the ranking puts first, not a candidate chosen for effect.

**Construction note — a real bug found and fixed**

The debris velocity is the target velocity *rotated about the radial direction*, which is a pure plane change: speed is preserved, no radial velocity is introduced, and eccentricity stays near the satellite's. The first implementation rolled the rotation axis toward the orbit normal, which injects `|v|*sin(theta)` of radial velocity — every attempt failed the `e < 0.05` check. Rotating about radial also puts the relative velocity in the plane perpendicular to it, so the range rate is exactly zero at the encounter and the miss distance is known independently of the detector.

**Variants**

- `no_encounter` — baseline clears at 9500 m.
- `simple_conflict` — baseline 200 m, 15 manoeuvres qualify.
- `no_feasible` — encounter at 1177 s, before most of the grid can act. 0 of 25 qualify, and **0 of 33 after widening**, so the agent's one permitted expansion cannot manufacture an answer.

**Not verified / not run**

- **`backend/planning/verifier.py` does not exist.** Nothing is approvable yet; `search.py` screens the primary threat only. This is the next and most important piece.
- No `domain/models.py`, no API, no agent, no frontend. Gate 3 untouched.
- `scenarios/variants/` holds three files; the fourth plan scenario (budget halved) is a runtime policy change against `primary.json`, not a separate fixture.
- Suite runtime is 64.8 s, dominated by the determinism test rebuilding the signature case. Acceptable now; revisit if it slows the loop.

**Contract changes**

`Policy` and `BurnWindow` live in `planning/search.py` as frozen dataclasses with CONTRACTS field names, same pattern as `Encounter`. They move to `domain/models.py` when the three of you write it. Scenario JSON adds two fields beyond CONTRACTS: `default_policy` and `generation_evidence`. The latter is provenance, not input — `tests/test_scenarios.py::test_recorded_evidence_matches_recomputation` fails if code and record disagree.

**Next concrete action**

`backend/planning/verifier.py`: rebuild from raw scenario JSON, own 1 s scan, screen both debris objects, compare against the search within 1 m / 0.1 s, block on any disagreement.

---

## [2026-09-12] — Builder A — independent verifier

**Changed paths**

- `backend/planning/policy.py` — `Policy`, `BurnWindow`, `policy_from_document` moved here
- `backend/planning/search.py` — re-exports them; no behaviour change
- `backend/planning/verifier.py` — reconstruction, independent screening, `ValidationResult`
- `tests/test_verifier.py` — 22 tests

**Commands run**

```
$ python -m pytest tests/ -q
66 passed in 36.22s
```

**Why `policy.py` exists**

`Policy` and `BurnWindow` previously lived in `search.py`. The verifier needs the active policy but must not import the search path, so the shared types moved to a neutral module. `search.py` re-exports them, so nothing else changed.

**How the verifier is independent**

| | Search | Verifier |
|---|---|---|
| Input | live `Trajectory` objects | raw scenario JSON, rebuilt here |
| Scan | 5 s | 1 s |
| Refinement | `brentq` on the range rate | bounded minimisation of squared distance |
| Scope | primary threat only | every debris object |
| Detection code | `core/encounters.py` | its own, in `verifier.py` |

Shared and disclosed: the Kepler propagator and trajectory primitives in `core/`. Writing the physics twice would test nothing useful — Gate 1 already checks the propagator against an independent integrator, and independence here is at the reconstruction and screening layer. `test_verifier_does_not_import_the_search_path` parses the module with `ast` and fails if anyone wires them together later.

**Agreement — measured**

Six candidates, both methods, against tolerances of 1 m and 0.1 s:

| Candidate | Search (m) | Verifier (m) | Δ distance | Δ time |
|---|---|---|---|---|
| `t30_ret_100` | 2016.926285 | 2016.926285 | 3.559e-08 m | 3.369e-09 s |
| `t15_ret_100` | 1982.268976 | 1982.268976 | 8.937e-09 m | 4.013e-09 s |
| `t45_ret_100` | 1852.899645 | 1852.899645 | 1.900e-08 m | 5.635e-09 s |
| `t60_ret_100` | 1448.447776 | 1448.447776 | 2.018e-08 m | 1.328e-08 s |
| `t30_ret_200` | 2491.888034 | 2491.888034 | 1.264e-09 m | 4.857e-09 s |

Roughly seven orders of margin inside the tolerance.

**The veto now happens in the right place**

`t30_ret_100` is ranked first by the search and clears the primary threat at 2016.9 m. The verifier screens `['DEB-1', 'DEB-2']`, finds DEB-2 at **523.2 m at 20313 s**, and returns `BLOCK`. `t30_ret_200` returns `PASS` with its closest approach to any object at 2491.9 m. Previously this rejection came from the generator and the tests; it now comes from the path that actually gates approval.

**A finding worth keeping**

`t30_ret_200` and `t45_ret_200` report *identical* separations. That looked wrong and is not: for a 0.20 m/s burn the constructed 16234 s conjunction is pushed far enough away that an earlier crossing at **t = 999 s** becomes the closest approach over the horizon — and 999 s precedes both burns, on the arc every candidate shares with the baseline. No manoeuvre can change it, so both candidates report the same number.

Two consequences:

- The metric is right. "Closest approach to this object over the horizon" is what matters, and it is correct for a strong burn to be limited by something the burn cannot affect.
- **For B:** the annotated dip is not always the headline conjunction. Label it with the time and object actually found, never with an assumed one.

`test_a_strong_burn_can_make_a_pre_burn_encounter_the_binding_one` pins this down so nobody "fixes" it later.

**Also verified**

- `no_feasible` variant: 0 approvable options across the full widened 33-option grid.
- Over-budget, blocked-window, beyond-horizon and malformed candidates all rejected, with the policy re-checked here rather than trusted from the search.
- Six malformed-scenario mutations (missing objects, unknown IDs, negative horizon, short vector, NaN velocity) all return `ERROR`, never `PASS`.
- A fabricated search result (claiming 99000 m where the verifier measures 2016.9 m) is caught as `SEARCH_DISAGREEMENT`.
- Stale `scenario_version` blocks.
- `ERROR` vs `BLOCK` is a real distinction: `ERROR` means the candidate could not be evaluated, `BLOCK` means it was evaluated and rejected. The UI should show these differently.

**Not verified / not run**

- No `domain/models.py`, no API, no agent, no frontend. Gate 3 untouched.
- `scripts/demo_pipeline.py` does not exist yet, so Gate 2 has no single command that prints the chain end to end.
- No caching anywhere. A 25-option search plus one validation is comfortable now; revisit if the agent loop makes it hot.
- The verifier's own 1 s scan is validated against a 4 s scan on this fixture family only, same caveat as the search grid.

**Next concrete action**

`scripts/demo_pipeline.py`: scenario → 25 options → top-ranked provisional pick → verifier veto → verified alternative, printed on stdout as the Gate 2 artifact.
