import { useEffect, useState } from "react";
import { api } from "../api";
import type { Coordination, JointPlan } from "../contracts";
import { clockText, distance } from "../workspace";

function metres(value: number | null) {
  return value === null ? "—" : distance(value).join(" ");
}

function burnText(burn: JointPlan["burns"][string]) {
  if (!burn) return "holds";
  const verb = burn.direction === "PROGRADE" ? "speed up" : "slow down";
  return `${burn.delta_v_mps.toFixed(2)} m/s ${verb} at T+${clockText(burn.burn_t_s).slice(0, 5)}`;
}

export function CoordinationPanel({ caseId }: { caseId: string }) {
  const [result, setResult] = useState<Coordination | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api
      .coordination(caseId)
      .then((r) => live && setResult(r))
      .catch(
        (reason) =>
          live &&
          setError(reason instanceof Error ? reason.message : "Coordination failed."),
      );
    return () => {
      live = false;
    };
  }, [caseId]);

  if (error) return <p className="exchange-error">{error}</p>;
  if (!result)
    return (
      <div className="loading-card glass">
        <span className="loading-orbit" />
        <p>Checking both operators&rsquo; plans, alone and together.</p>
      </div>
    );

  const label = Object.fromEntries(result.operators.map((o) => [o.object_id, o.label]));
  const [ours, partner] = result.operators;
  const agreed = result.plans.find((p) => p.plan_id === result.agreed_plan_id);
  const naive = result.plans.find((p) => p.plan_id === "both_as_planned");

  return (
    <>
      <p className="dialog-intro">
        The close approach is with {partner.label}&rsquo;s satellite, and both
        operators can move. If nobody does, they pass{" "}
        {metres(result.if_nobody_moves.closest_m)} apart.
      </p>

      <h3>Each operator, planning alone</h3>
      <div className="evidence-summary">
        {result.independent_plans.map((plan) => (
          <div key={plan.operator}>
            <span>{label[plan.operator]}</span>
            <strong>
              {plan.candidate_id
                ? `${plan.delta_v_mps!.toFixed(2)} m/s ${plan.direction === "PROGRADE" ? "speed up" : "slow down"} at T+${clockText(plan.burn_t_s!).slice(0, 5)}`
                : "no plan"}
            </strong>
            <small>
              {plan.solo_closest_m !== null
                ? `alone: closest ${metres(plan.solo_closest_m)}`
                : ""}
            </small>
          </div>
        ))}
      </div>

      {naive && (
        <p className={naive.comfortable ? "caption" : "exchange-error"}>
          If both execute their own plan: the satellites pass{" "}
          {metres(naive.closest_m)} apart
          {naive.status === "BLOCK"
            ? ` — below the ${metres(result.floor_m)} floor. Each plan is safe alone; together they are not.`
            : "."}
        </p>
      )}

      <h3>Joint plans, checked together</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Plan</th>
              <th>{ours.label}</th>
              <th>{partner.label}</th>
              <th>Total delta-v</th>
              <th>Closest</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {result.plans.map((plan) => (
              <tr
                key={plan.plan_id}
                className={plan.plan_id === result.agreed_plan_id ? "selected" : ""}
              >
                <td>{plan.label}</td>
                <td>{burnText(plan.burns[ours.object_id] ?? null)}</td>
                <td>{burnText(plan.burns[partner.object_id] ?? null)}</td>
                <td>{plan.total_delta_v_mps.toFixed(2)} m/s</td>
                <td>{metres(plan.closest_m)}</td>
                <td>
                  <span
                    className={`status ${plan.comfortable ? "good" : plan.status === "PASS" ? "watch" : "danger"}`}
                  >
                    <i />
                    {plan.comfortable ? "Clear" : plan.status === "PASS" ? "Marginal" : "Unsafe"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Agreed</h3>
      {agreed ? (
        <p>
          <span className="status good">
            <i />
            {agreed.label}
          </span>{" "}
          — {agreed.total_delta_v_mps.toFixed(2)} m/s in total, closest{" "}
          {metres(agreed.closest_m)} across every pair screened.
        </p>
      ) : (
        <p className="exchange-error">No joint plan clears every pair.</p>
      )}
      <p className="caption">Rule both operators apply: {result.rule}</p>
      <p className="caption">
        Agreement fingerprint <span className="mono">{result.agreement_sha256.slice(0, 16)}</span>{" "}
        — computed from the scenario states, the rule and the agreed burns, so
        either operator can recompute it and get the same value.
      </p>
    </>
  );
}
