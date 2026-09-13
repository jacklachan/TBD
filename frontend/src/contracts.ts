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
  /**
   * True for the generated fixtures, where the orbit is real and the encounter
   * is constructed. False for pasted catalogue elements, where the encounter is
   * whatever the elements say -- usually nothing.
   */
  synthetic_conjunction: boolean;
  note: string;
  /** Present only for pasted elements: one entry per object, with its own
   * element epoch before everything was moved to a shared one. */
  objects?: {
    object_id: string;
    norad_id: number;
    name: string;
    tle_epoch_utc: string;
    altitude_km: number;
  }[];
}

export interface ScenarioSummary {
  description: string;
  horizon_s: number;
  epoch_utc: string;
  satellite_id: string;
  primary_threat_id: string;
  objects: {
    object_id: string;
    name: string;
    kind: string;
    maneuverable?: boolean;
    operator?: string | null;
  }[];
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
  /** The step the planner is on, while it is still running. */
  step?: string;
  steps_done?: number;
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

/** A prior case on the same scenario that the last run consulted. */
export interface PriorCase {
  case_id: string;
  memory_id: string;
  outcome: PlannerStatus | string;
  tags: string[];
  summary: string;
  /** What it suggests. Advisory only — it never changed this case's policy. */
  suggestion: string;
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
  prior_cases: PriorCase[];
  runs: RunRecord[];
  /** Present only on the response that created a case from pasted elements. */
  ingest?: {
    objects: {
      object_id: string;
      norad_id: number;
      name: string;
      tle_epoch_utc: string;
      altitude_km: number;
    }[];
    epoch_spread_s: number;
    note: string;
  };
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

export interface TrackedConjunction {
  protected: { norad_id: number; name: string };
  debris: { norad_id: number; name: string; event: string };
  tca_utc: string;
  miss_km: number;
  relative_speed_kms: number;
  element_age_days: { protected: number; debris: number };
  triage: TrackedTriage;
}

/**
 * How much room is left to act on a pass.
 *
 * A burn is placeable a whole number of half-orbits before closest approach,
 * so the deadline is the last such slot still in the future. Which slot that is
 * differs per pass, which is why `decide_in_hours` does not run in the same
 * order as `lead_hours`. Nothing here is a probability.
 */
export interface TrackedTriage {
  posture: "ACTIONABLE" | "NARROWING" | "TOO_LATE";
  lead_hours: number;
  /** Absent once no burn slot is left. */
  decide_in_hours?: number | null;
  decide_by_utc?: string;
  burn_slots_open: number;
  burn_slots_total: number;
  latest_burn_half_orbits: number;
}

/**
 * What the screen can substantiate about the passes it did *not* report.
 *
 * The capture radius is the report threshold plus the fastest closure the
 * catalogue permits times half a coarse step; `status` is INCOMPLETE when the
 * run could not stand behind that, and `shortfall` says why.
 */
export interface TrackingCompleteness {
  status: "COMPLETE" | "INCOMPLETE";
  claim: string;
  capture_radius_km: number;
  speed_bound: {
    derived_kms: number;
    floor_kms: number;
    applied_kms: number;
    source: string;
    fastest_protected_kms: number;
    fastest_debris_kms: number;
    margin_kms: number;
  };
  observed_head_on_kms: number;
  speed_headroom_kms: number;
  linear_margin_km: number;
  worst_linear_error_km: number;
  linear_headroom_km: number;
  candidate_pairs_refined: number;
  shortfall?: string[];
}

export interface TrackingCrossCheck {
  object_1: { norad_id: number; name: string };
  object_2: { norad_id: number; name: string };
  published_tca_utc: string;
  published_miss_km: number;
  published_relative_speed_kms: number;
  status: "RECOMPUTED" | "OUTSIDE_WINDOW" | "PROPAGATION_ERROR";
  our_tca_utc?: string;
  our_miss_km?: number;
  our_relative_speed_kms?: number;
  tca_difference_s?: number;
}

/** GET /tracking/screen: real constellation against real debris, SGP4. */
export interface TrackingScreen {
  mode: "SGP4_CATALOGUE_SCREEN";
  window: { start_utc: string; end_utc: string; hours: number; coarse_step_s: number };
  catalog: {
    retrieved_at_utc: string;
    protected_count: number;
    debris_count: number;
    groups: { group: string; role: string; object_count: number; label: string }[];
  };
  pairs_screened: number;
  report_threshold_km: number;
  conjunction_count: number;
  conjunctions: TrackedConjunction[];
  completeness: TrackingCompleteness;
  triage: {
    attention_km: number;
    queue_length: number;
    by_posture: Partial<Record<TrackedTriage["posture"], number>>;
    basis: string;
    queue: TrackedConjunction[];
  };
  by_satellite: { norad_id: number; name: string; count: number; closest_km: number }[];
  by_event: Record<string, number>;
  cross_check: TrackingCrossCheck[];
  elapsed_s: number;
  note: string;
}

export interface WatchItem {
  item_id: string;
  source: "REAL" | "SIMULATED";
  satellite: string;
  threat: string;
  threat_event?: string;
  threat_can_move: boolean;
  tca_utc: string | null;
  miss_km: number;
  relative_speed_kms?: number;
  status: "AWAITING_APPROVAL" | "APPROVED" | "BLOCKED_BY_REVIEWER" | "ESCALATE" | "NO_ACTION";
  recommendation: {
    direction: string;
    delta_v_mps: number;
    minutes_before?: number;
    burn_t_s?: number;
  } | null;
  estimated_miss_km: number | null;
  rescreen_closest_km: number | null;
  rescreen_fragments?: number;
  reviewer: { decision: string; reason_codes: string[]; rationale: string } | null;
  coordination: {
    needed: boolean;
    reason?: string;
    both_as_planned_m?: number | null;
    agreed_plan?: string | null;
    movers?: string[];
    rule?: string;
  };
  approved_at_utc?: string;
  approval_note?: string;
}

/** The result of POST /watch, read from GET /runs/{id}. */
export interface WatchResult {
  status: "QUEUE_READY" | "PARTIAL";
  triage_status: string;
  unresolved_reason: string;
  brief: string;
  flagged_numbers: number[];
  queue: WatchItem[];
  timeline: { sequence: number; t_s: number; stage: string; actor: string; summary: string }[];
  model_calls: number;
  elapsed_s: number;
  note: string;
}

export interface TriageItem {
  pass_id: string;
  satellite: string;
  fragment_norad_id: number;
  event: string;
  tca_utc: string;
  miss_km: number;
  relative_speed_kms: number;
  status: "NEEDS_BURN" | "CLEAR" | "NO_OPTION";
  recommendation: string | null;
  estimated_miss_km: number | null;
  rescreen_closest_km: number | null;
}

/** The result of POST /tracking/agent, read from GET /runs/{id}. */
export interface TriageResult {
  status: "BRIEF_READY" | "UNRESOLVED";
  unresolved_reason: string;
  brief: string;
  triage: TriageItem[];
  model_calls: number;
  tool_calls: number;
  assessments: number;
  flagged_numbers: number[];
  events: { sequence: number; event_type: string; summary: string; duration_ms: number }[];
  elapsed_s: number;
  note: string;
}

export interface JointPlan {
  plan_id: string;
  label: string;
  movers: string[];
  total_delta_v_mps: number;
  closest_m: number | null;
  status: "PASS" | "BLOCK";
  comfortable: boolean;
  burns: Record<
    string,
    { candidate_id: string; burn_t_s: number; direction: string; delta_v_mps: number } | null
  >;
  pairs: { objects: string[]; min_separation_m: number; tca_s: number }[];
}

/** GET /cases/{id}/coordination */
export interface Coordination {
  mode: "OPERATOR_COORDINATION";
  case_id: string;
  operators: { object_id: string; label: string; role: "OURS" | "PARTNER" }[];
  floor_m: number;
  comfortable_m: number;
  if_nobody_moves: JointPlan;
  independent_plans: {
    operator: string;
    candidate_id: string | null;
    burn_t_s: number | null;
    direction: string | null;
    delta_v_mps: number | null;
    solo_closest_m: number | null;
  }[];
  plans: JointPlan[];
  rule: string;
  agreed_plan_id: string | null;
  agreement_sha256: string;
}

export interface AvoidanceOption {
  option_id: string;
  lead_minutes: number;
  direction: "PROGRADE" | "RETROGRADE" | null;
  delta_v_mps: number;
  displacement_km: number;
  predicted_miss_km: number;
  qualifies: boolean;
  verdict?: "PASS" | "BLOCK";
  rescreen_closest_km?: number | null;
  rescreen_assessed_miss_km?: number;
  blocked_by?: { debris: { norad_id: number; name: string; event: string }; tca_utc: string; miss_km: number };
}

/** POST /tracking/assess: burn options for one real pass, re-screened. */
export interface AvoidanceAssessment {
  mode: "SGP4_CW_ASSESSMENT";
  /**
   * The avoidance assessment identifies the pass but does not re-derive the
   * screen's element ages or its decision deadline, so neither is present.
   */
  conjunction: Omit<TrackedConjunction, "element_age_days" | "triage">;
  orbital_period_minutes: number;
  floor_km: number;
  comfortable_km: number;
  option_count: number;
  options: AvoidanceOption[];
  recommended_option_id: string | null;
  rescreen: { hours_after_burn: number; fragments: number; step_s: number };
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
  /** True when the planner specified this burn itself rather than taking it
   * off the grid. Screened identically either way. */
  designed?: boolean;
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
  /** Server has a token AND accepts a name/password in place of it. */
  sign_in_enabled: boolean;
}

/**
 * The result of recomputing a conjunction record received from someone else.
 *
 * `checks` is the comparison that matters: what the sender claimed against what
 * we computed from the state vectors they sent. A record whose numbers cannot be
 * reproduced comes back DISAGREES with the difference spelled out.
 */
export interface CdmCheck {
  object_id: string;
  agrees: boolean;
  claimed_miss_distance_m: number;
  recomputed_miss_distance_m: number | null;
  distance_delta_m?: number;
  claimed_tca_s?: number;
  recomputed_tca_s?: number;
  time_delta_s?: number;
  reason: string;
}

export interface CdmVerification {
  originator: string;
  message_id: string;
  created_at: string;
  frame: string;
  epoch_utc: string;
  objects: { object_id: string; name: string; maneuverable: boolean }[];
  manoeuvre: {
    candidate_id: string;
    burn_t_s: number | null;
    direction: string;
    delta_v_mps: number;
  } | null;
  independent_result: {
    status: ValidationStatus;
    reason_codes: string[];
    screened_objects: string[];
    sample_step_s: number;
    method: string;
    encounters: {
      object_id: string;
      min_separation_m: number;
      tca_s: number;
      relative_speed_mps: number;
    }[];
  };
  checks: CdmCheck[];
  verdict: "AGREES" | "DISAGREES" | "NO_CLAIMS";
  note: string;
}

/** What signing in returns. The token is a session, not the server's own. */
export interface SignIn {
  token: string;
  user: string;
  expires_in_s: number;
}
