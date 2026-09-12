# Satellite Demo — shared contracts

**Contract revision:** 1, proposed for the team's hour-zero agreement. These definitions specify future interfaces; no `models.py` exists yet.

All three builders agree on changes here before implementing their own modules. Once code exists, `backend/domain/models.py` defines serialization; this document explains its semantics. B and C keep `frontend/src/contracts.ts` aligned. One field name per concept, explicit units, no independently invented frontend physics types.

## Units, frame, time, identity

| Concept | Contract |
|---|---|
| Position, velocity, delta-v | Metres, metres/second, metres/second; finite float64 values in the backend |
| Vector | Exactly three finite numbers; serialized as an array |
| Time | `t_s`: seconds from `epoch_utc`; horizon inclusive `[0, 21600]`; epoch is timezone-aware UTC |
| Frame | `SIM_ECI_TEME_SEEDED`: fixed simulation axes initialized from the epoch TEME state; not a claimed GCRF conversion |
| Earth model | `mu_m3_s2 = 3.986004418e14`, `earth_radius_m = 6378137.0`; two-body, instantaneous single impulse |
| Policy floor | `min_separation_m = 1000.0` initially; demo policy |
| IDs | Opaque case/run/proposal/execution IDs; stable object/candidate IDs within their version |
| Version stamp | `case_id`, `scenario_version`, `policy_version`; every result and mutation carries the stamp |
| Units at display | Convert metres to kilometres once for labels; renderer scale never changes the authoritative data |

## Domain objects for models.py

Required means present and validated unless marked optional. Prohibit NaN/Infinity; reject unexpected mutation fields. Optional fields are omitted or explicitly nullable in internal transport types; Gemini tool declarations use only the supported flat subset selected in the smoke test.

| Model | Fields and meaning |
|---|---|
| `StateVector` | `r_m`, `v_mps`: three-element arrays |
| `ObjectState` | `object_id`, `name`, `kind` (`SATELLITE` or `DEBRIS`), `maneuverable`, `initial_state: StateVector` |
| `BurnWindow` | `window_id`, `label`, `start_s`, `end_s`; finite `0 <= start_s < end_s <= horizon_s`; protected interval is closed at both ends |
| `Provenance` | `source_kind`, `source_url`, `retrieved_at_utc`, `source_sha256`, `norad_id` (optional), `tle_epoch_utc` (optional), `frame`, `model_version`, `synthetic_conjunction: true` |
| `Scenario` | `schema_version`, `scenario_id`, `scenario_version`, `seed`, `epoch_utc`, `horizon_s`, exactly three `objects`, `satellite_id`, `primary_threat_id`, `known_windows: list[BurnWindow]`, `provenance`; all IDs resolve; exactly one object maneuverable |
| `Policy` | `policy_version`, `max_delta_v_mps`, `min_separation_m`, `blocked_windows: list[BurnWindow]`; nonnegative budget, positive floor |
| `Candidate` | `candidate_id`, `kind` (`NO_BURN` or `IMPULSE`), `burn_t_s` (optional for baseline), `direction` (`PROGRADE`, `RETROGRADE`, or omitted for baseline), `delta_v_mps`, `grid_revision`; baseline magnitude is zero |
| `Encounter` | `other_object_id`, `tca_s`, `min_separation_m`, `relative_speed_mps`, `method`, `boundary_kind` (`INTERIOR`, `HORIZON`, `BURN`), `ambiguous_time: bool` |
| `CandidateEvaluation` | version stamp, `candidate`, `primary_encounter`, `primary_qualified`, `reason_codes`, `rank` (optional for excluded rows). This is NOT all-object clearance |
| `SearchResult` | version stamp, `grid_revision`, `candidate_count`, `baseline`, `evaluations`, `status` (`OPTIONS_AVAILABLE` or `NO_PRIMARY_QUALIFIED_OPTION`) |
| `ValidationResult` | version stamp, `candidate_id`, `validation_id`, `status` (`PASS`, `BLOCK`, `ERROR`), `encounters` against BOTH debris objects, `reason_codes`, `max_primary_distance_disagreement_m`, `primary_time_disagreement_s`, `computed_at_utc`, `model_version` |
| `PolicyDiff` | `diff_id`, base version stamp, `source_text`, `before: Policy`, `after: Policy`, `changes`, `status` (`READY` or `NEEDS_CLARIFICATION`), `clarification` (optional) |
| `ReviewerVerdict` | version stamp, `candidate_id`, `validation_id`, `decision` (`ALLOW` or `BLOCK`), `reason_codes`, `evidence_ids` |
| `Proposal` | `proposal_id`, version stamp, `candidate_id`, `validation_id`, `reviewer_verdict`, `qualitative_rationale`, `evidence_ids`, `status` (`READY`, `BLOCKED`, `STALE`, `EXECUTED`) |
| `CaseEvent` | `event_id`, `run_id`, version stamp, `sequence`, `event_type`, `summary`, `evidence_ids`, `duration_ms`, `created_at_utc`, sanitized structured `details` |
| `ExecutionRecord` | `execution_id`, version stamp, `proposal_id`, `candidate_id`, `idempotency_key`, `executed_at_utc`, `mode: SIMULATION`; one record per executed proposal |
| `CaseSnapshot` | version stamp, `scenario`, `policy`, `run_status`, `search_result` (optional), `validations`, `proposal` (optional), `execution` (optional), `events` |

Keep trace explanations concise; do not store or expose hidden model reasoning. Events show actual tool actions, results, evidence, and short decision summaries.

## Pure numerical interfaces

Signatures below are the agreed design, not runnable code:

- `propagate(r0_m, v0_mps, dt_s_array) -> (r_m_array, v_mps_array)`: input shapes `(3,)`, `(3,)`, `(N,)`; output `(N,3)` each. Reject nonfinite inputs, return empty arrays for empty times, preserve the exact input state at zero time.
- `Trajectory.states_at(t_s_array) -> (r_m_array, v_mps_array)` and `Trajectory.apply_impulse(burn_t_s, dv_mps_vector) -> Trajectory`: an impulse returns a new object. At the burn instant state queries use the post-burn velocity.
- `find_encounters(satellite_trajectory, debris_trajectory, horizon_s, step_s=5) -> list[Encounter]`: search-path detection; includes boundaries and validated local minima.
- `generate_candidates(scenario, grid_revision=1) -> list[Candidate]`: stable baseline ID `baseline`; four times x two directions x three magnitudes + baseline = 25. Policy-excluded candidates remain visible with reasons.
- `evaluate_candidates(scenario, policy, candidates) -> SearchResult`: primary-threat scope only, explicitly provisional.
- `validate_candidate(raw_scenario_json, policy, candidate, expected_primary_encounter) -> ValidationResult`: independent reconstruction/detection; `expected_primary_encounter` is only a comparison target, never accepted as evidence.

Candidate direction is resolved at burn time from the unburned satellite velocity: prograde is its unit vector, retrograde its negative. Store the derived applied vector in evidence. Do not confuse an RTN component with an inertial vector.

Cache numerical results by `(scenario input hash, model_version, grid_revision, candidate_id)`. If caching eligibility or decisions, include policy version/hash as well. Verifier results must be produced by its independent path, not the search cache. API responses add the active case version stamp.

## Five flat model tools

The backend binds case and versions from the active run; the model cannot select a different case or manufacture versions. Validate returned arguments with the domain models. Unknown tools or IDs are rejected.

| Tool | Flat model-visible arguments | Behavior |
|---|---|---|
| `get_case_briefing` | None | Returns compact scenario/policy, baseline evidence and relevant memory IDs |
| `evaluate_candidates` | None | Evaluates the active grid under the confirmed policy; returns IDs, provisional ranks and reasons |
| `validate_proposal` | `candidate_id: string` | Recomputes all-object validation; rejects IDs outside the active grid |
| `propose_policy` | Optional `budget_scale: number`, `max_delta_v_mps: number`, `blocked_window_id: string` | Produces a proposed diff; never applies it. Scale and absolute budget are mutually exclusive; known window ID must resolve. At least one change required |
| `widen_search` | `dimension: string`, enum `SMALLER_MAGNITUDES` | Only after a rejection, once per run: add magnitude 0.025 m/s at the same four times/two directions; 8 new options, 33 total. Never relax policy |

This flat `propose_policy` signature intentionally replaces the archived `propose_policy(text)` nesting: the model interprets the sentence once; the tool computes and validates the proposed numbers. The source sentence is bound to the run by the API. “Halve” supplies `budget_scale=0.5`; the backend computes half of the confirmed budget. Unsupported requests or unspecified window times yield `NEEDS_CLARIFICATION`, not guessed values.

Tool availability depends on phase. Policy interpretation can propose a diff but cannot approve/execute. Planning can evaluate/validate but cannot mutate policy. The reviewer receives read-only evidence. Human confirmation and simulated execution are application endpoints, not model tools.

## API boundaries

`api.py` coordinates these endpoints. Long operations return a `run_id`; `GET /cases/{case_id}` provides current events/results. B may use simple bounded polling initially. Response wrappers carry versions so late responses from an old run cannot overwrite new UI state.

| Endpoint | Input and result |
|---|---|
| `POST /cases` | `scenario_id` -> fresh `CaseSnapshot` from a frozen fixture |
| `GET /cases/{case_id}` | -> `CaseSnapshot` |
| `POST /cases/{case_id}/plan` | expected scenario/policy versions -> starts run, returns `run_id` |
| `POST /cases/{case_id}/policy-preview` | `text`, expected versions -> policy interpretation run; stores `PolicyDiff` in event/result details |
| `POST /cases/{case_id}/policy-confirm` | `diff_id`, expected versions -> apply diff once, increment policy version, invalidate old proposals, start fresh run |
| `GET /cases/{case_id}/visualization` | candidate IDs (maximum 3), expected versions -> `VisualizationBundle` |
| `POST /cases/{case_id}/approve` | `proposal_id`, expected versions, `idempotency_key` -> `ExecutionRecord` after deterministic PASS + reviewer ALLOW |
| `POST /cases/{case_id}/reset` | expected versions -> NEW case ID from the same frozen fixture; retain historical case |
| `GET /cases/{case_id}/export` | `format=json` or `format=markdown` -> self-contained decision evidence with provenance |
| `GET /context/socrates` | -> up to 10 normalized rows and source/retrieval/report timestamps from disk |

Validation errors return 422 with typed reason; unknown IDs 404; stale versions, reused idempotency key for different content, or blocked approval 409. Runtime/numerical failures appear as `ERROR` events and cannot produce an approvable proposal. Do not send successful empty results on tool failure.

Simulated execution is recorded once; later policy changes do not erase historical burns. For the live replan demonstration, change policy before execution. After execution, use reset/new case to demonstrate another decision.

## VisualizationBundle — one numerical source for chart and 3D

Required fields: version stamp, `model_version`, `frame`, `epoch_utc`, `t_s: sorted unique array`, `variants`, `events`, `min_separation_m`, `sample_step_s`.

Each variant contains `candidate_id`, `positions_m` mapping each of the three object IDs to an `(N,3)` array, `pair_separations_m` mapping each debris ID to an `(N,)` array, and `min_to_any_m: (N,)`. Every array aligns with the SAME `t_s`. Backend distances equal Euclidean position differences for that sample. Include one-second samples, horizon boundaries, burn timestamps, and exact refined encounter timestamps in the shared time union. Return only baseline, rejected, and recommended variants requested by B; never send all 25 trajectories to the LLM.

Default playback/scrubbing selects a supplied sample; chart cursor, all moving markers and labels use that sample together. Exact-encounter buttons select the included refined time. This avoids an interpolated distance being displayed as an exact minimum. If smoother interpolation is added later, label it during motion, interpolate all objects consistently, and snap to authoritative samples for encounter inspection; interpolated points cannot change a verdict.

Rendering may change the camera and apply one common rigid coordinate transform/scale. It must not rescale pair separation independently or compute alternative trajectories. Enlarged model geometry is explicitly labeled and is excluded from the centre-to-centre separation calculation.

## Integration handoff rule

When a field or signature changes: update this document, notify the two other builders, change models/transport types together, increment `schema_version` if serialized fixtures break, and regenerate affected fixtures. Record the change in STATE.md and the relevant role handoff. Do not solve mismatches with silent defaults.
