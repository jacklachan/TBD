/**
 * Typed client with stale-response protection.
 *
 * Two problems this solves for the UI.
 *
 * A late reply from a superseded run must never overwrite newer state. Every
 * response carries the versions it was computed under; `guard` drops anything
 * older than what the caller now holds. Fire two plans in quick succession and
 * the first one's answer is discarded, not rendered.
 *
 * A 409 is a normal outcome, not a crash. Stale versions, blocked approvals and
 * idempotency conflicts all arrive as `ApiError` with a machine-readable
 * `code`, so the UI can say something useful instead of showing a stack trace.
 */

import type {
  AvoidanceAssessment,
  Analysis,
  CaseSnapshot,
  CdmVerification,
  Health,
  PolicyDiff,
  RunRecord,
  SocratesContext,
  TrackingScreen,
  VersionStamp,
  VisualizationBundle,
} from "./contracts";

export const API_BASE =
  (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE ?? "";

// Operator credential lives in memory only. The model key never enters this client.
let accessToken = "";
export function setAccessToken(token: string) {
  accessToken = token.trim();
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    const record =
      detail && typeof detail === "object"
        ? (detail as Record<string, unknown>)
        : {};
    super(
      typeof record.message === "string"
        ? record.message
        : typeof detail === "string"
          ? detail
          : `Request failed with ${status}`,
    );
    this.name = "ApiError";
    this.status = status;
    this.code =
      typeof record.error === "string" ? record.error : `HTTP_${status}`;
    this.detail = detail;
  }

  /** The case moved on. Reload before acting. */
  get isStale(): boolean {
    return this.code === "STALE_VERSION" || this.code === "PROPOSAL_STALE";
  }

  /** Deterministic validation or the safety reviewer refused. */
  get isBlocked(): boolean {
    return this.code === "NOT_VALIDATED" || this.code === "REVIEWER_BLOCKED";
  }
}

/** Thrown when a response is older than what the caller already has. */
export class StaleResponse extends Error {
  constructor(
    readonly received: VersionStamp,
    readonly current: VersionStamp,
  ) {
    super("Discarded a response from a superseded version of the case");
    this.name = "StaleResponse";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    signal,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail: unknown = await response.text();
    try {
      const parsed = JSON.parse(detail as string);
      detail = parsed?.detail ?? parsed;
    } catch {
      /* keep the text body */
    }
    throw new ApiError(response.status, detail);
  }

  // Markdown reports and CCSDS records both come back as text, not JSON.
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("text/markdown") || contentType.includes("text/plain")) {
    return (await response.text()) as unknown as T;
  }
  return (await response.json()) as T;
}

/**
 * Reject a payload computed under an older version than the caller holds.
 *
 * Call this on anything that will be written into state after an await.
 */
export function guard<
  T extends { scenario_version: number; policy_version: number },
>(payload: T, current: VersionStamp): T {
  const received = {
    expected_scenario_version: payload.scenario_version,
    expected_policy_version: payload.policy_version,
  };
  if (
    payload.scenario_version < current.expected_scenario_version ||
    payload.policy_version < current.expected_policy_version
  ) {
    throw new StaleResponse(received, current);
  }
  return payload;
}

// --------------------------------------------------------------------------

export const api = {
  analysis(caseId: string, versions: VersionStamp): Promise<Analysis> {
    return request(`/cases/${caseId}/analysis`, {
      method: "POST",
      body: JSON.stringify(versions),
    });
  },

  manualPolicy(
    caseId: string,
    versions: VersionStamp,
    maxDeltaV: number,
  ): Promise<CaseSnapshot> {
    return request(`/cases/${caseId}/policy-manual`, {
      method: "POST",
      body: JSON.stringify({ ...versions, max_delta_v_mps: maxDeltaV }),
    });
  },
  createCase(scenarioId = "primary"): Promise<CaseSnapshot> {
    return request("/cases", {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId }),
    });
  },

  ingestTle(
    text: string,
    satelliteIndex = 0,
    horizonS = 21600,
  ): Promise<CaseSnapshot> {
    return request("/ingest/tle", {
      method: "POST",
      body: JSON.stringify({
        text,
        satellite_index: satelliteIndex,
        horizon_s: horizonS,
      }),
    });
  },

  getCase(caseId: string, signal?: AbortSignal): Promise<CaseSnapshot> {
    return request(`/cases/${caseId}`, {}, signal);
  },

  /** Returns immediately with a run_id; poll with `waitForRun`. */
  startPlan(
    caseId: string,
    versions: VersionStamp,
    instruction = "",
  ): Promise<{ run_id: string; status: string; case_id: string }> {
    return request(`/cases/${caseId}/plan`, {
      method: "POST",
      body: JSON.stringify({ ...versions, instruction }),
    });
  },

  getRun(runId: string, signal?: AbortSignal): Promise<RunRecord> {
    return request(`/runs/${runId}`, {}, signal);
  },

  /** The operator's sentence in, a diff to confirm out. Nothing changes yet. */
  policyPreview(
    caseId: string,
    versions: VersionStamp,
    text: string,
  ): Promise<{ diff: PolicyDiff; model_calls: number }> {
    return request(`/cases/${caseId}/policy-preview`, {
      method: "POST",
      body: JSON.stringify({ ...versions, text }),
    });
  },

  /** Applies once, bumps the policy version, stales pending proposals. */
  policyConfirm(
    caseId: string,
    versions: VersionStamp,
    diffId: string,
  ): Promise<{ policy_version: number; policy: Record<string, unknown> }> {
    return request(`/cases/${caseId}/policy-confirm`, {
      method: "POST",
      body: JSON.stringify({ ...versions, diff_id: diffId }),
    });
  },

  /** At most three variants. Baseline, rejected and recommended is the set to ask for. */
  visualization(
    caseId: string,
    versions: VersionStamp,
    candidateIds: string[],
    sampleStepS?: number,
    signal?: AbortSignal,
  ): Promise<VisualizationBundle> {
    const params = new URLSearchParams({
      candidate_ids: candidateIds.join(","),
      expected_scenario_version: String(versions.expected_scenario_version),
      expected_policy_version: String(versions.expected_policy_version),
    });
    if (sampleStepS !== undefined)
      params.set("sample_step_s", String(sampleStepS));
    return request(`/cases/${caseId}/visualization?${params}`, {}, signal);
  },

  /**
   * Simulated execution. Reuse the same idempotencyKey for a retry of the same
   * click so a double submit cannot apply the burn twice.
   */
  approve(
    caseId: string,
    versions: VersionStamp,
    proposalId: string,
    idempotencyKey: string,
  ): Promise<{ execution: Record<string, unknown>; created: boolean }> {
    return request(`/cases/${caseId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        ...versions,
        proposal_id: proposalId,
        idempotency_key: idempotencyKey,
      }),
    });
  },

  /** A new case from the same fixture. The old one keeps its history. */
  reset(caseId: string, versions: VersionStamp): Promise<CaseSnapshot> {
    return request(`/cases/${caseId}/reset`, {
      method: "POST",
      body: JSON.stringify(versions),
    });
  },

  exportJson(caseId: string): Promise<CaseSnapshot> {
    return request(`/cases/${caseId}/export?format=json`);
  },

  /** The case as a CCSDS-shaped record, carrying states so it can be rechecked. */
  exportCdm(caseId: string): Promise<string> {
    return request(`/cases/${caseId}/export?format=cdm`);
  },

  /** Recompute a record from another operator instead of believing it. */
  verifyCdm(text: string): Promise<CdmVerification> {
    return request("/interop/verify-cdm", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },

  exportMarkdown(caseId: string): Promise<string> {
    return request(`/cases/${caseId}/export?format=markdown`);
  },

  /** Computed once per server from the committed catalogue; can take seconds cold. */
  trackingScreen(): Promise<TrackingScreen> {
    return request("/tracking/screen");
  },

  trackingAssess(
    protectedNoradId: number,
    debrisNoradId: number,
    tcaUtc: string,
  ): Promise<AvoidanceAssessment> {
    return request("/tracking/assess", {
      method: "POST",
      body: JSON.stringify({
        protected_norad_id: protectedNoradId,
        debris_norad_id: debrisNoradId,
        tca_utc: tcaUtc,
      }),
    });
  },

  socrates(signal?: AbortSignal): Promise<SocratesContext> {
    return request("/context/socrates", {}, signal);
  },

  health(): Promise<Health> {
    return request("/health");
  },
};

/**
 * Poll a run to completion.
 *
 * A FAILED run is returned rather than thrown: the trace is still worth showing,
 * and "the run failed" is information the operator needs on screen.
 */
export async function waitForRun(
  runId: string,
  options: {
    intervalMs?: number;
    timeoutMs?: number;
    signal?: AbortSignal;
    onStep?: (step: string, done: number) => void;
  } = {},
): Promise<RunRecord> {
  // Longer than the planner's own deadline plus its reviewer call, so a run
  // that legitimately uses its whole budget is not reported here as a
  // client timeout. The server is the thing that bounds a run.
  const { intervalMs = 400, timeoutMs = 180_000, signal, onStep } = options;
  let reported = -1;
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    const run = await api.getRun(runId, signal);
    if (onStep && run.step && (run.steps_done ?? 0) > reported) {
      reported = run.steps_done ?? 0;
      onStep(run.step, reported);
    }
    if (run.status !== "RUNNING") return run;
    if (Date.now() > deadline) {
      throw new Error(`Run ${runId} did not finish within ${timeoutMs} ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

/** Stable key per approve click, so a retry is the same request. */
export function idempotencyKey(proposalId: string): string {
  return `approve:${proposalId}`;
}
