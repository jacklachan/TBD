import { useEffect, useState } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { api, ApiError } from "../api";
import type { CaseSnapshot, PriorCase } from "../contracts";
import { clockText, distance } from "../workspace";

/** Read-only inspection. Opening history never replaces or recomputes the active case. */
export function PriorCaseEvidence({
  prior,
  onBack,
}: {
  prior: PriorCase;
  onBack: () => void;
}) {
  const [record, setRecord] = useState<CaseSnapshot | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setRecord(null);
    setError("");
    api
      .getCase(prior.case_id, controller.signal)
      .then((snapshot) => {
        if (!controller.signal.aborted) setRecord(snapshot);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof ApiError && reason.status === 404
            ? "This earlier case is no longer available on the server. Its advisory memory remains in the current trace."
            : reason instanceof Error
              ? reason.message
              : "The earlier case could not be loaded.",
        );
      });
    return () => controller.abort();
  }, [prior.case_id]);

  return (
    <section className="prior-detail">
      <button className="subtle-button" onClick={onBack} autoFocus>
        <ArrowLeft size={17} /> Back to current evidence
      </button>
      <p className="caption">
        Read-only · your current case, policy and selected trajectory remain in
        place.
      </p>
      <h3>{prior.case_id}</h3>
      <article className="evidence-item">
        <span className="caption">
          What the current run recalled · {prior.memory_id}
        </span>
        <p>{prior.summary}</p>
        {prior.suggestion && <p className="caption">{prior.suggestion}</p>}
      </article>
      {error && (
        <p role="alert" className="warning-text">
          {error}
        </p>
      )}
      {!record && !error && <p role="status">Loading stored evidence…</p>}
      {record && (
        <>
          <h3>Latest stored case snapshot</h3>
          <p className="caption">
            This case may have changed since the recalled run. Every check below
            names the policy version it used.
          </p>
          <div className="evidence-summary">
            <div>
              <span>Scenario</span>
              <strong>
                {record.scenario_id} · v{record.scenario_version}
              </strong>
            </div>
            <div>
              <span>Current stored policy</span>
              <strong>
                v{record.policy_version} ·{" "}
                {record.policy.max_delta_v_mps.toFixed(3)} m/s
              </strong>
            </div>
            <div>
              <span>Clearance floor</span>
              <strong>
                {record.policy.min_separation_m.toLocaleString()} m
              </strong>
            </div>
          </div>
          <p className="caption">
            Created {record.created_at_utc} ·{" "}
            {record.scenario.provenance.synthetic_conjunction
              ? "Synthetic conjunction"
              : "Catalogue-seeded simulation"}
          </p>
          {record.policy.blocked_windows.length > 0 && (
            <p>
              Protected windows:{" "}
              {record.policy.blocked_windows.map((w) => w.label).join(", ")}
            </p>
          )}
          <h3>Proposal and execution</h3>
          {record.proposal ? (
            <article className="evidence-item">
              <p>
                <strong>{record.proposal.candidate_id}</strong> ·{" "}
                {record.proposal.status} · policy v
                {record.proposal.policy_version}
              </p>
              <p>
                Safety review:{" "}
                {record.proposal.reviewer_verdict?.decision ?? "Not recorded"}
              </p>
              <p className="caption">
                {record.proposal.reviewer_verdict?.rationale}
              </p>
            </article>
          ) : (
            <p>No proposal stored.</p>
          )}
          <p>
            {record.execution
              ? `Simulated execution recorded: ${record.execution.candidate_id} · ${record.execution.executed_at_utc}`
              : "No simulated execution recorded."}
          </p>
          <h3>Independent validation records</h3>
          {!record.validations.length && (
            <p>No independent validation stored.</p>
          )}
          {record.validations.map((validation) => (
            <article className="evidence-item" key={validation.validation_id}>
              <p>
                <strong>{validation.candidate_id}</strong> · {validation.status}{" "}
                · policy v{validation.policy_version} · scenario v
                {validation.scenario_version}
              </p>
              {validation.encounters.map((encounter) => {
                const [value, unit] = distance(encounter.min_separation_m);
                return (
                  <p key={encounter.object_id}>
                    {encounter.object_id}: {value} {unit} at T+
                    {clockText(encounter.tca_s)}
                  </p>
                );
              })}
              <p className="caption">{validation.reason_codes.join(" · ")}</p>
            </article>
          ))}
        </>
      )}
    </section>
  );
}
