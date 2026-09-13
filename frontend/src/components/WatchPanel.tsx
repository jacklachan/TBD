import { useState } from "react";
import { api, waitForRun } from "../api";
import type { WatchItem, WatchResult } from "../contracts";
import { missText, utcText } from "./TrackingPanel";

const STAGES = [
  { id: "DETECT", title: "Detect", body: "Screen 80 satellites against 2,664 real fragments" },
  { id: "TRIAGE", title: "Triage", body: "AI agent picks the passes that matter" },
  { id: "PLAN", title: "Plan", body: "Compute burns, re-check against every fragment" },
  { id: "REVIEW", title: "Review", body: "Separate AI safety reviewer can veto" },
  { id: "COORDINATE", title: "Coordinate", body: "Decide who has to move" },
  { id: "DECIDE", title: "You approve", body: "The only human step" },
];

// The backend reports progress as "Actor: what it did"; the actor says which
// stage of the chain is running.
const ACTOR_STAGE: Record<string, string> = {
  "Screening engine": "DETECT",
  "Triage agent (AI)": "TRIAGE",
  "Avoidance engine": "PLAN",
  "Safety reviewer (AI)": "REVIEW",
  "Coordination check": "COORDINATE",
  "Decision queue": "DECIDE",
};

const STATUS: Record<WatchItem["status"], [string, string]> = {
  AWAITING_APPROVAL: ["Ready for your approval", "good"],
  APPROVED: ["Approved (simulated)", "good"],
  BLOCKED_BY_REVIEWER: ["Stopped by the safety reviewer", "danger"],
  ESCALATE: ["No safe option found — escalate", "watch"],
  NO_ACTION: ["No action needed", "muted"],
};

function burnSentence(item: WatchItem) {
  const r = item.recommendation;
  if (!r) return null;
  const verb = r.direction === "PROGRADE" ? "Speed up" : "Slow down";
  if (r.minutes_before !== undefined) {
    const h = Math.floor(r.minutes_before / 60);
    const m = r.minutes_before % 60;
    return `${verb} by ${r.delta_v_mps.toFixed(2)} m/s, ${h ? `${h} h ${m} min` : `${m} min`} before the pass`;
  }
  return `${verb} by ${r.delta_v_mps.toFixed(2)} m/s`;
}

function DecisionCard({
  item,
  onApprove,
  busy,
}: {
  item: WatchItem;
  onApprove: () => void;
  busy: boolean;
}) {
  const [label, tone] = STATUS[item.status];
  const burn = burnSentence(item);
  return (
    <article className={`decision-card glass ${item.status === "AWAITING_APPROVAL" ? "selected" : ""}`}>
      <div className="decision-head">
        <span className={`status ${tone}`}>
          <i />
          {label}
        </span>
        <span className="decision-source">
          {item.source === "REAL" ? "Real public data" : "Simulated scenario"}
        </span>
      </div>
      <h4>
        {item.satellite} ↔ {item.threat}
      </h4>
      <p>
        {item.tca_utc ? `On ${utcText(item.tca_utc)} they` : "They"} pass{" "}
        <strong>{missText(item.miss_km)}</strong> apart
        {item.relative_speed_kms ? ` at ${item.relative_speed_kms.toFixed(1)} km/s` : ""}
        {item.threat_event ? ` — debris from the ${item.threat_event}` : ""}.
      </p>
      {burn && (
        <p>
          <span className="decision-label">Plan</span> {burn}.
          {item.rescreen_closest_km !== null && (
            <>
              {" "}
              Re-checked against{" "}
              {item.rescreen_fragments ? `all ${item.rescreen_fragments.toLocaleString()} fragments` : "every object"}:
              nearest approach becomes <strong>{missText(item.rescreen_closest_km)}</strong>.
            </>
          )}
        </p>
      )}
      {item.reviewer && (
        <p>
          <span className="decision-label">AI safety reviewer</span>{" "}
          {item.reviewer.decision === "ALLOW" ? "approved" : item.reviewer.decision === "BLOCK" ? "blocked" : "did not answer, so blocked"}
          {item.reviewer.rationale ? ` — “${item.reviewer.rationale}”` : "."}
        </p>
      )}
      <p>
        <span className="decision-label">Who moves</span>{" "}
        {item.coordination.needed
          ? `Both operators could move. Each plan works alone, but together they pass ${
              item.coordination.both_as_planned_m ?? "—"
            } m apart, so the shared rule picks: ${item.coordination.agreed_plan}.`
          : item.coordination.reason}
      </p>
      {item.status === "AWAITING_APPROVAL" && (
        <button className="approve-button" onClick={onApprove} disabled={busy}>
          Approve burn (simulated)
        </button>
      )}
      {item.status === "APPROVED" && <p className="caption">{item.approval_note}</p>}
    </article>
  );
}

export function WatchPanel({ modelAccess }: { modelAccess: boolean }) {
  const [runId, setRunId] = useState("");
  const [step, setStep] = useState("");
  const [result, setResult] = useState<WatchResult | null>(null);
  const [error, setError] = useState("");
  const [approving, setApproving] = useState("");

  const running = !!step;
  const activeStage = running ? ACTOR_STAGE[step.split(":")[0]] : undefined;
  const reached = result
    ? STAGES.length
    : Math.max(0, STAGES.findIndex((s) => s.id === activeStage));

  const start = async () => {
    setError("");
    setResult(null);
    setStep("Starting the watch");
    try {
      const run = await api.startWatch();
      setRunId(run.run_id);
      const finished = await waitForRun(run.run_id, {
        onStep: (text) => setStep(text),
        timeoutMs: 400_000,
      });
      if (finished.status === "FAILED") throw new Error(finished.error);
      setResult(finished.result as unknown as WatchResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The watch failed.");
    } finally {
      setStep("");
    }
  };

  const approve = async (item: WatchItem) => {
    setApproving(item.item_id);
    try {
      const { item: updated } = await api.approveWatchItem(runId, item.item_id);
      setResult((current) =>
        current
          ? { ...current, queue: current.queue.map((i) => (i.item_id === updated.item_id ? updated : i)) }
          : current,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Approval failed.");
    } finally {
      setApproving("");
    }
  };

  const waiting = result?.queue.filter((i) => i.status === "AWAITING_APPROVAL").length ?? 0;
  return (
    <>
      <p className="dialog-intro">
        One click starts a chain of agents over real data: they find the close
        approaches, decide which matter, work out and double-check a burn, have
        a second AI review it, and check whether anyone else needs to move. They
        stop at the one decision that stays human — approving the burn.
      </p>

      <ol className="watch-stages">
        {STAGES.map((stage, index) => {
          const state = result
            ? "done"
            : activeStage === stage.id
              ? "active"
              : running && index < reached
                ? "done"
                : "pending";
          return (
            <li key={stage.id} className={`watch-stage ${state}`}>
              <span className="watch-index">{index + 1}</span>
              <strong>{stage.title}</strong>
              <small>{stage.body}</small>
            </li>
          );
        })}
      </ol>

      <button className="primary-button" onClick={start} disabled={!modelAccess || running}>
        {running ? "Agents working…" : result ? "Run the watch again" : "Start autonomous watch"}
      </button>
      {!modelAccess && <p className="caption">Set HF_TOKEN on the server to enable the agents.</p>}
      {running && (
        <div className="loading-card glass">
          <span className="loading-orbit" />
          <p>{step}</p>
        </div>
      )}
      {error && <p className="exchange-error">{error}</p>}

      {result && (
        <>
          <h3>
            Decisions{" "}
            <span className="caption">
              {waiting} waiting for you · finished in {result.elapsed_s.toFixed(0)} s ·{" "}
              {result.model_calls} AI calls
            </span>
          </h3>
          <div className="decision-list-watch">
            {result.queue.map((item) => (
              <DecisionCard
                key={item.item_id}
                item={item}
                busy={approving === item.item_id}
                onApprove={() => approve(item)}
              />
            ))}
          </div>

          {result.brief && (
            <>
              <h3>What the triage agent told the operator</h3>
              <p className="triage-brief">{result.brief}</p>
              {!!result.flagged_numbers.length && (
                <p className="warning-text">
                  Figures in the brief not found in any tool result: {result.flagged_numbers.join(", ")}.
                </p>
              )}
            </>
          )}

          <details className="triage-trace" open>
            <summary>What each agent did, in order</summary>
            <ol className="watch-timeline">
              {result.timeline.map((entry) => (
                <li key={entry.sequence}>
                  <span className={`actor ${entry.actor.includes("(AI)") ? "ai" : ""}`}>{entry.actor}</span>
                  <p>{entry.summary}</p>
                  <small>{entry.t_s.toFixed(1)} s</small>
                </li>
              ))}
            </ol>
          </details>
          <p className="caption">{result.note}</p>
        </>
      )}
    </>
  );
}
