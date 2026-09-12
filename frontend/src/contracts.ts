/**
 * Transport types, mirroring backend/planning and backend/api.py.
 *
 * One field name per concept, matching the backend exactly. Do not add
 * frontend-only physics types: if a number is needed on screen and is not here,
 * ask C for a backend field rather than deriving it. Every figure the UI shows
 * comes from a typed value the backend computed.
 *
 * Keep this in step with Handoff/CONTRACTS.md. When a field changes, both sides
 * change together.
 */

export type ValidationStatus = "PASS" | "BLOCK" | "ERROR";
export type ProposalStatus = "READY" | "BLOCKED" | "STALE" | "EXECUTED";
export type ReviewerDecision = "ALLOW" | "BLOCK" | "UNAVAILABLE";
export type BoundaryKind = "INTERIOR" | "HORIZON" | "BURN";
export type RunStatus = "RUNNING" | "DONE" | "FAILED";
export type CandidateKind = "NO_BURN" | "IMPULSE";
export type BurnDirection = "PROGRADE" | "RETROGRADE";

/** Planner outcomes. NO_APPROVABLE_OPTION is a real answer, not an error. */
export type PlannerStatus =
  "PROPOSAL_READY" | "NO_APPROVABLE_OPTION" | "UNRESOLVED";

export interface BurnWindow {
  window_id: string;
  label: string;
  start_s: number;
  end_s: number;
}

export interface Provenance {
  source_kind: string;
  source_url: string;
  source_sha256: string;
  norad_id: number;
  object_name: string;
  tle_epoch_utc: string;
  frame: string;
  model_version: string;
  /** Always true. The orbit is real; the encounter is constructed. */
  synthetic_conjunction: boolean;
  note: string;
}

export interface ScenarioSummary {
  description: string;
  horizon_s: number;
  epoch_utc: string;
  satellite_id: string;
  primary_threat_id: string;
  objects: { object_id: string; name: string; kind: string }[];
  known_windows: BurnWindow[];
  provenance: Provenance;
  input_hash: string;
}

export interface Policy {
  policy_version: number;
  max_delta_v_mps: number;
  min_separation_m: number;
  blocked_windows: BurnWindow[];
}

export interface Encounter {
  object_id: string;
  min_separation_m: number;
  tca_s: number;
  relative_speed_mps: number;
  boundary_kind: BoundaryKind;
  /** Flat or degenerate minimum: show the distance, not an exact time. */
  ambiguous_time: boolean;
}

export interface Validation {
  scenario_version: number;
  policy_version: number;
  validation_id: string;
  candidate_id: string;
  status: ValidationStatus;
  reason_codes: string[];
  screened_objects: string[];
  encounters: Encounter[];
  max_primary_distance_disagreement_m: number | null;
  primary_time_disagreement_s: number | null;
  sample_step_s: number;
  method: string;
}

export interface ReviewerVerdict {
  decision: ReviewerDecision;
  reason_codes: string[];
  rationale: string;
  evidence_ids: string[];
  model: string;
  latency_ms: number;
}

export interface Proposal {
  proposal_id: string;
  case_id: string;
  scenario_version: number;
  policy_version: number;
  candidate_id: string;
  validation_id: string;
  reviewer_verdict: ReviewerVerdict | null;
  qualitative_rationale: string;
  evidence_ids: string[];
  status: ProposalStatus;
}

export interface ExecutionRecord {
  execution_id: string;
  case_id: string;
  proposal_id: string;
  candidate_id: string;
  idempotency_key: string;
  mode: "SIMULATION";
  executed_at_utc: string;
}

export interface CaseEvent {
  event_id: string;
  run_id: string | null;
  sequence: number;
  event_type: string;
  summary: string;
  duration_ms: number;
  details: Record<string, unknown>;
  created_at_utc: string;
}

export interface PolicyChange {
  field: string;
  before: unknown;
  after: unknown;
  note: string;
}

export interface PolicyDiff {
  diff_id: string;
  status: "READY" | "NEEDS_CLARIFICATION";
  /** Render as a question, not an error, when NEEDS_CLARIFICATION. */
  clarification: string;
  changes: PolicyChange[];
  case_id: string;
  scenario_version: number;
  policy_version: number;
  grid_revision: number;
}

export interface RunRecord {
  run_id: string;
  case_id: string;
  kind: string;
  status: RunStatus;
  started_at_utc: string;
  finished_at_utc: string;
  error: string;
  result: {
    status?: PlannerStatus;
    unresolved_reason?: string;
    proposal_id?: string | null;
    model_calls?: number;
    tool_calls?: number;
    validations_run?: number;
    elapsed_s?: number;
    /** Figures in the model's prose absent from the evidence. Surface these. */
    flagged_numbers?: number[];
  };
}

export interface CaseSnapshot {
  case_id: string;
  parent_case_id: string | null;
  scenario_id: string;
  scenario_version: number;
  policy_version: number;
  grid_revision: number;
  created_at_utc: string;
  scenario: ScenarioSummary;
  policy: Policy;
  pending_diff: (PolicyDiff & { after: Policy; source_text: string }) | null;
  validations: Validation[];
  proposal: Proposal | null;
  execution: ExecutionRecord | null;
  events: CaseEvent[];
  runs: RunRecord[];
}

/**
 * One numerical source for the chart and the 3D scene.
 *
 * Every array aligns with `t_s`. The grid already contains both horizon ends,
 * every burn epoch and the exact time of every encounter, so playback and
 * scrubbing must SELECT a supplied sample rather than interpolate. An
 * interpolated value must never be shown as an exact minimum.
 */
export interface VisualizationVariant {
  candidate_id: string;
  kind: CandidateKind;
  delta_v_mps: number;
  burn_t_s: number | null;
  direction: BurnDirection | null;
  /** object_id -> [N][3] metres, aligned with t_s. */
  positions_m: Record<string, number[][]>;
  /** debris_id -> [N] metres, aligned with t_s. */
  pair_separations_m: Record<string, number[]>;
  /** Closest approach to ANY object at each sample. The chart's headline series. */
  min_to_any_m: number[];
  encounters: (Omit<Encounter, "relative_speed_mps"> & {
    below_floor: boolean;
  })[];
}

export interface VisualizationBundle {
  case_id: string;
  scenario_id: string;
  scenario_version: number;
  policy_version: number;
  model_version: string;
  frame: string;
  epoch_utc: string;
  horizon_s: number;
  sample_step_s: number;
  min_separation_m: number;
  satellite_id: string;
  primary_threat_id: string;
  object_ids: string[];
  t_s: number[];
  variants: VisualizationVariant[];
  note: string;
}

export interface SocratesContext {
  rows: Record<string, string>[];
  row_count: number;
  source_url: string;
  retrieved_at_utc: string;
  source_sha256: string;
  note: string;
}

/** Every mutating request states the versions it was composed against. */
export interface VersionStamp {
  expected_scenario_version: number;
  expected_policy_version: number;
}

export function versionsOf(snapshot: CaseSnapshot): VersionStamp {
  return {
    expected_scenario_version: snapshot.scenario_version,
    expected_policy_version: snapshot.policy_version,
  };
}

/** True when this option can actually be approved. */
export function isApprovable(snapshot: CaseSnapshot): boolean {
  const proposal = snapshot.proposal;
  if (!proposal || proposal.status !== "READY" || snapshot.execution)
    return false;
  if (
    proposal.case_id !== snapshot.case_id ||
    proposal.scenario_version !== snapshot.scenario_version ||
    proposal.policy_version !== snapshot.policy_version
  )
    return false;
  const validation = snapshot.validations.find(
    (v) => v.validation_id === proposal.validation_id,
  );
  if (
    !validation ||
    validation.status !== "PASS" ||
    validation.candidate_id !== proposal.candidate_id ||
    validation.scenario_version !== snapshot.scenario_version ||
    validation.policy_version !== snapshot.policy_version
  )
    return false;
  const verdict = proposal.reviewer_verdict;
  return verdict?.decision === "ALLOW";
}

export interface OptionRow {
  candidate_id: string;
  kind: CandidateKind;
  delta_v_mps: number;
  burn_t_s: number | null;
  direction: BurnDirection | null;
  primary_qualified: boolean;
  primary_encounter: { min_separation_m: number; tca_s: number } | null;
  reason_codes: string[];
  rank: number | null;
  validation: {
    status: ValidationStatus;
    validation_id: string;
    reason_codes: string[];
    encounters: {
      object_id: string;
      min_separation_m: number;
      tca_s: number;
    }[];
    blocked_by: {
      object_id: string;
      min_separation_m: number;
      shortfall_m: number;
      tca_s: number;
    }[];
  } | null;
}

export interface Analysis {
  case_id: string;
  scenario_version: number;
  policy_version: number;
  mode: "NUMERICAL_ANALYSIS";
  status: "VERIFIED_OPTION" | "NO_VERIFIED_OPTION";
  candidate_count: number;
  qualified_count: number;
  recommended_id: string | null;
  options: OptionRow[];
  elapsed_s: number;
  note: string;
}

export interface Health {
  status: string;
  model_version: string;
  planner_model: string;
  model_access: boolean;
  access_token_required: boolean;
}
