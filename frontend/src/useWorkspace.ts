import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  guard,
  idempotencyKey,
  setAccessToken,
  waitForRun,
} from "./api";
import type {
  Analysis,
  CaseSnapshot,
  Health,
  PolicyDiff,
  SocratesContext,
  VisualizationBundle,
} from "./contracts";
import { versionsOf } from "./contracts";
import { comparisonIds, download, nearestSample } from "./workspace";

export function useWorkspace() {
  const [snapshot, setSnapshot] = useState<CaseSnapshot | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [bundle, setBundle] = useState<VisualizationBundle | null>(null);
  const [selected, setSelected] = useState("");
  const [time, setTime] = useState(0);
  const [health, setHealth] = useState<Health | null>(null);
  const [context, setContext] = useState<SocratesContext | null>(null);
  const [busy, setBusy] = useState("Connecting to the numerical engine");
  const [error, setError] = useState("");
  const [accessRequired, setAccessRequired] = useState(false);
  const [diff, setDiff] = useState<PolicyDiff | null>(null);
  const [notice, setNotice] = useState("");
  const generation = useRef(0),
    current = useRef<CaseSnapshot | null>(null),
    inFlight = useRef(false);

  function handleError(reason: unknown) {
    setError(
      reason instanceof Error
        ? reason.message
        : "The request could not be completed.",
    );
    if (
      reason instanceof ApiError &&
      (reason.status === 401 || reason.code === "ACCESS_NOT_CONFIGURED")
    )
      setAccessRequired(true);
  }

  async function refresh(next: CaseSnapshot, keepSelected = false) {
    const ticket = ++generation.current;
    current.current = next;
    setSnapshot(next);
    setAnalysis(null);
    setBundle(null);
    setDiff(null);
    setBusy("Comparing maneuvers and independently checking both objects");
    const computed = await api.analysis(next.case_id, versionsOf(next));
    if (ticket !== generation.current) return;
    guard(computed, versionsOf(current.current!));
    const ids = comparisonIds(computed);
    const chosen =
      keepSelected && computed.options.some((o) => o.candidate_id === selected)
        ? selected
        : ids[0];
    const wanted = [...new Set([ids[0], chosen, ...ids.slice(1)])].slice(0, 3);
    const trajectories = await api.visualization(
      next.case_id,
      versionsOf(next),
      wanted,
    );
    if (
      ticket !== generation.current ||
      trajectories.case_id !== current.current?.case_id
    )
      return;
    guard(trajectories, versionsOf(current.current));
    setAnalysis(computed);
    setBundle(trajectories);
    setSelected(chosen);
  }

  async function action(label: string, task: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (reason) {
      handleError(reason);
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  }

  async function connect(token?: string) {
    if (token !== undefined) setAccessToken(token);
    await action("Loading the frozen scenario", async () => {
      const status = await api.health();
      setHealth(status);
      if (status.access_token_required && token === undefined) {
        setAccessRequired(true);
        return;
      }
      const next = await api.createCase("primary");
      setAccessRequired(false);
      await refresh(next);
      setTime(0);
      try {
        setContext(await api.socrates());
      } catch {
        setNotice(
          "The orbital case is ready. The reference snapshot could not be loaded.",
        );
      }
    });
  }
  useEffect(() => {
    void connect();
  }, []);

  const choose = (id: string) =>
    action("Loading the selected trajectory", async () => {
      if (!snapshot || !analysis) return;
      if (!bundle?.variants.some((v) => v.candidate_id === id)) {
        const ticket = generation.current;
        const ids = [
          ...new Set(
            [comparisonIds(analysis)[0], id, analysis.recommended_id].filter(
              (s): s is string => Boolean(s),
            ),
          ),
        ].slice(0, 3);
        const next = await api.visualization(
          snapshot.case_id,
          versionsOf(snapshot),
          ids,
        );
        if (
          ticket !== generation.current ||
          next.case_id !== current.current?.case_id
        )
          return;
        guard(next, versionsOf(current.current));
        setBundle(next);
      }
      setSelected(id);
    });

  const runPlanner = () =>
    action("AI planner is evaluating evidence", async () => {
      if (!snapshot) return;
      const run = await api.startPlan(snapshot.case_id, versionsOf(snapshot));
      const result = await waitForRun(run.run_id);
      const next = await api.getCase(snapshot.case_id);
      if (next.case_id !== current.current?.case_id) return;
      current.current = next;
      setSnapshot(next);
      if (result.status === "FAILED") throw new Error(result.error);
      // A planner may widen the grid. Refresh the comparison and trajectories
      // before exposing a proposal from that grid for operator inspection.
      await refresh(next, true);
      setNotice(
        result.result.status === "PROPOSAL_READY"
          ? `AI proposal ready · ${result.result.model_calls} model calls · ${result.result.elapsed_s?.toFixed(1)} s`
          : `AI outcome: ${result.result.status?.replaceAll("_", " ").toLowerCase()}. ${result.result.unresolved_reason || ""}`,
      );
    });

  return {
    snapshot,
    analysis,
    bundle,
    selected,
    time,
    setTime,
    health,
    context,
    busy,
    error,
    notice,
    diff,
    accessRequired,
    connect,
    choose,
    sample: bundle ? nearestSample(bundle.t_s, time) : 0,
    openScenario: (id: string) =>
      action("Opening scenario", async () => {
        await refresh(await api.createCase(id));
        setTime(0);
      }),
    retry: () =>
      snapshot
        ? action("Refreshing case", async () => {
            await refresh(await api.getCase(snapshot.case_id), true);
          })
        : connect(),
    setBudget: (value: number) =>
      action("Applying the operator budget", async () => {
        if (snapshot) {
          await refresh(
            await api.manualPolicy(
              snapshot.case_id,
              versionsOf(snapshot),
              value,
            ),
            true,
          );
          setNotice(
            "Budget applied. Every displayed result uses the new policy.",
          );
        }
      }),
    preview: (text: string) =>
      action("Interpreting your restriction", async () => {
        if (!snapshot) return;
        const result = await api.policyPreview(
          snapshot.case_id,
          versionsOf(snapshot),
          text,
        );
        setDiff(result.diff);
      }),
    confirm: () =>
      action("Confirming the restriction", async () => {
        if (!snapshot || !diff) return;
        await api.policyConfirm(
          snapshot.case_id,
          versionsOf(snapshot),
          diff.diff_id,
        );
        await refresh(await api.getCase(snapshot.case_id), true);
        setNotice(
          "Restriction confirmed and numerical comparison refreshed. Run the AI planner for a new reviewed proposal.",
        );
      }),
    dismissDiff: () => setDiff(null),
    runPlanner,
    approve: () =>
      action("Recording simulated execution", async () => {
        if (!snapshot?.proposal) return;
        await api.approve(
          snapshot.case_id,
          versionsOf(snapshot),
          snapshot.proposal.proposal_id,
          idempotencyKey(snapshot.proposal.proposal_id),
        );
        const next = await api.getCase(snapshot.case_id);
        current.current = next;
        setSnapshot(next);
        setNotice(
          "Maneuver recorded in simulation. No spacecraft command was sent.",
        );
      }),
    reset: () =>
      action("Creating a fresh simulation", async () => {
        if (snapshot) {
          await refresh(
            await api.reset(snapshot.case_id, versionsOf(snapshot)),
          );
          setTime(0);
        }
      }),
    exportEvidence: () =>
      action("Preparing the evidence bundle", async () => {
        if (!snapshot) return;
        const report = await api.exportJson(snapshot.case_id);
        if (
          report.policy_version !== analysis?.policy_version ||
          report.scenario_version !== analysis.scenario_version ||
          report.case_id !== bundle?.case_id
        ) {
          throw new Error(
            "The case changed before export. Refresh the evidence and export again.",
          );
        }
        download(
          `satellite-demo-${snapshot.case_id}.json`,
          JSON.stringify(
            {
              ...report,
              numerical_analysis: analysis,
              displayed_trajectories: bundle,
            },
            null,
            2,
          ),
        );
        setNotice(
          "Evidence exported with provenance, versions, numerical comparison and displayed trajectories.",
        );
      }),
  };
}
