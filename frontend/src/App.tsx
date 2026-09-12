import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  ArrowsClockwise,
  Check,
  Crosshair,
  DownloadSimple,
  GlobeHemisphereWest,
  Info,
  Moon,
  Pause,
  Play,
  ShieldCheck,
  SlidersHorizontal,
  Sparkle,
  Sun,
  WarningCircle,
} from "@phosphor-icons/react";
import { api } from "./api";
import type { CdmVerification } from "./contracts";
import { useWorkspace } from "./useWorkspace";
import {
  currentVariant,
  minimum,
  clockText,
  distance,
  optionName,
  optionStatus,
  comparisonIds,
} from "./workspace";
import { isApprovable } from "./contracts";
import { SeparationChart } from "./components/SeparationChart";
import { Dialog } from "./components/Dialog";
import type { ViewMode } from "./scene/OrbitalScene";

const OrbitalScene = lazy(() =>
  import("./scene/OrbitalScene").then((m) => ({ default: m.OrbitalScene })),
);
const SatellitePreview = lazy(() =>
  import("./scene/OrbitalScene").then((m) => ({ default: m.SatellitePreview })),
);
const scenarios = [
  { id: "primary", name: "The second encounter" },
  { id: "collision", name: "Impact if nothing changes" },
  { id: "simple_conflict", name: "A single close approach" },
  { id: "no_encounter", name: "A clear orbit" },
  { id: "no_feasible", name: "No feasible maneuver" },
];

function Status({
  tone = "muted",
  children,
}: {
  tone?: string;
  children: React.ReactNode;
}) {
  return (
    <span className={`status ${tone}`}>
      <i />
      {children}
    </span>
  );
}
function Metric({
  value,
  unit,
  className = "",
}: {
  value: string;
  unit: string;
  className?: string;
}) {
  return (
    <div className={`metric ${className}`}>
      {value}
      <span>{unit}</span>
    </div>
  );
}

export default function App() {
  const desk = useWorkspace();
  const { snapshot, analysis, bundle, selected, sample, busy } = desk;
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("satellite-demo-theme") === "light"
        ? "light"
        : "dark";
    } catch {
      return "dark";
    }
  });
  const [view, setView] = useState<ViewMode>("orbit");
  const [debrisId, setDebrisId] = useState("DEB-1");
  const [cameraReset, setCameraReset] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(180);
  const [panel, setPanel] = useState<
    "options" | "evidence" | "about" | "limits" | "elements" | null
  >(null);
  const [instruction, setInstruction] = useState("");
  const [token, setToken] = useState("");
  const [budget, setBudget] = useState("0.20");
  // Pasted catalogue elements, and the exchange panel's issued and received
  // records. Grouped because all three are someone else's data passing through
  // a dialog; none of them belongs in case state.
  const [elements, setElements] = useState("");
  const [elementsIndex, setElementsIndex] = useState(0);
  const [elementsError, setElementsError] = useState("");
  const [issued, setIssued] = useState("");
  const [received, setReceived] = useState("");
  const [checked, setChecked] = useState<CdmVerification | null>(null);
  const [exchangeError, setExchangeError] = useState("");
  const [exchangeBusy, setExchangeBusy] = useState("");
  const [filter, setFilter] = useState("all");
  const variant = currentVariant(bundle, selected);
  const option = analysis?.options.find((o) => o.candidate_id === selected);
  const worst = useMemo(
    () => (variant ? minimum(variant.min_to_any_m) : null),
    [variant],
  );
  // Names recognised in the pasted text, so the picker and the count respond as
  // you type. The server parses it again properly; this is only for the form.
  const elementNames = useMemo(() => {
    const lines = elements.split(/\r?\n/).map((l) => l.trimEnd());
    const names: string[] = [];
    let pending = "";
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      if (!line.trim()) continue;
      if (/^1 [ 0-9]{5}[A-Z] /.test(line)) {
        if (/^2 [ 0-9]{5} /.test(lines[i + 1] ?? "")) {
          names.push(pending || `OBJECT ${line.slice(2, 7).trim()}`);
          pending = "";
          i += 1;
        }
        continue;
      }
      if (/^2 [ 0-9]{5} /.test(line)) continue;
      pending = line.trim();
    }
    return names;
  }, [elements]);
  const [minValue, minUnit] = distance(worst?.value);
  // Both objects are metres across. Below this the centres are close enough
  // that the hardware occupies the same space -- a strike, not a near miss,
  // and the difference is worth saying out loud rather than leaving to whoever
  // is reading the number.
  const CONTACT_M = 25;
  const strike = worst != null && worst.value < CONTACT_M;
  const liveDistance = variant?.pair_separations_m[debrisId]?.[sample];
  const [liveValue, liveUnit] = distance(liveDistance);
  const policy = snapshot?.policy;
  const status = option
    ? optionStatus(option)
    : { label: "Awaiting analysis", tone: "muted" };
  const designedCount =
    analysis?.options.filter((o) => o.designed).length ?? 0;
  const comparison = analysis
    ? comparisonIds(analysis, snapshot?.proposal?.candidate_id)
        .map((id) => analysis.options.find((o) => o.candidate_id === id))
        .filter((o): o is NonNullable<typeof o> => Boolean(o))
    : [];

  useEffect(() => {
    if (!bundle) return;
    const others = bundle.object_ids.filter((id) => id !== bundle.satellite_id);
    if (others.length && !others.includes(debrisId)) {
      setDebrisId(bundle.primary_threat_id ?? others[0]);
    }
  }, [bundle, debrisId]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("satellite-demo-theme", theme);
    } catch {
      /* theme still works without storage */
    }
  }, [theme]);
  useEffect(() => {
    if (policy) setBudget(policy.max_delta_v_mps.toFixed(2));
  }, [policy]);
  useEffect(() => {
    setPlaying(false);
  }, [busy, selected]);
  useEffect(() => {
    if (!playing || !bundle) return;
    let previous = performance.now(),
      frame = 0;
    function tick(now: number) {
      const elapsed = Math.min((now - previous) / 1000, 0.1);
      previous = now;
      if (!document.hidden)
        desk.setTime((t) => {
          const next = t + elapsed * speed;
          if (next >= bundle!.horizon_s) {
            setPlaying(false);
            return bundle!.horizon_s;
          }
          return next;
        });
      frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, bundle]);

  const seek = (time: number) => {
    setPlaying(false);
    desk.setTime(time);
  };
  const issueRecord = async () => {
    if (!snapshot) return;
    setExchangeError("");
    setExchangeBusy("Issuing the record");
    try {
      setIssued(await api.exportCdm(snapshot.case_id));
    } catch (reason) {
      setExchangeError(
        reason instanceof Error ? reason.message : "The record could not be issued.",
      );
    } finally {
      setExchangeBusy("");
    }
  };

  const checkRecord = async () => {
    setExchangeError("");
    setChecked(null);
    setExchangeBusy("Recomputing the record");
    try {
      setChecked(await api.verifyCdm(received));
    } catch (reason) {
      setExchangeError(
        reason instanceof Error
          ? reason.message
          : "That record could not be read as a conjunction message.",
      );
    } finally {
      setExchangeBusy("");
    }
  };

  const jump = (objectId?: string) => {
    if (!variant) return;
    const encounters = variant.encounters.filter(
      (e) => !objectId || e.object_id === objectId,
    );
    const closest = encounters.reduce(
      (best, e) =>
        !best || e.min_separation_m < best.min_separation_m ? e : best,
      encounters[0],
    );
    if (closest) {
      setDebrisId(closest.object_id);
      seek(closest.tca_s);
      setView("approach");
      setCameraReset((n) => n + 1);
    }
  };
  const choose = async (id: string) => {
    setPlaying(false);
    await desk.choose(id);
    setCameraReset((n) => n + 1);
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#decision-controls">
        Skip to decision controls
      </a>
      <div className="space-field" aria-hidden="true" />
      {bundle && variant && (
        <Suspense
          fallback={
            <div className="scene-loading">Preparing the orbital scene…</div>
          }
        >
          <OrbitalScene
            bundle={bundle}
            selected={selected}
            sample={sample}
            theme={theme}
            view={view}
            debrisId={debrisId}
            cameraReset={cameraReset}
          />
        </Suspense>
      )}

      <header className="topbar glass">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPanel(null);
          }}
          aria-label="Orion West workspace"
        >
          <span className="brand-mark">
            <span />
            <span />
            <span />
          </span>
          <span>
            Orion West<small>ORBITAL DECISION WORKSPACE</small>
          </span>
        </a>
        <nav aria-label="Workspace">
          <button
            className={`pill ${panel === null ? "selected" : ""}`}
            onClick={() => setPanel(null)}
          >
            Overview
          </button>
          <button
            className={`pill ${panel === "options" ? "selected" : ""}`}
            onClick={() => setPanel("options")}
          >
            Maneuvers{" "}
            <span className="nav-count">
              {analysis?.candidate_count ?? "—"}
            </span>
          </button>
          <button
            className={`pill ${panel === "evidence" ? "selected" : ""}`}
            onClick={() => setPanel("evidence")}
          >
            Evidence
          </button>
        </nav>
        <div className="topbar-tools">
          <Status tone={desk.health ? "good" : "muted"}>
            {desk.health ? "Engine connected" : "Connecting"}
          </Status>
          <span className="divider" />
          <button
            className="icon-button"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? (
              <Sun size={24} weight="light" />
            ) : (
              <Moon size={24} weight="light" />
            )}
          </button>
          <button
            className="avatar"
            onClick={() => setPanel("about")}
            aria-label="About this simulation"
          >
            SD
          </button>
        </div>
      </header>

      {/* The case this view is showing. Exposed so a browser test can name it
          and so anyone inspecting the page can match what is on screen to a
          row in the store without opening the network panel. */}
      <main data-case-id={snapshot?.case_id ?? ""}>
        <div className="page-heading">
          <div>
            <div className="eyebrow">MISSION CONTROL / SIMULATION</div>
            <h1>A safer way around.</h1>
            <p>One orbit. Every consequence.</p>
          </div>
          <div className="provenance-tag">
            <span className="tiny-orbit" />
            Real orbit seed<span className="dot-separator">·</span>Synthetic
            encounters
            <button
              aria-label="Read data provenance"
              onClick={() => setPanel("about")}
            >
              <Info size={16} />
            </button>
          </div>
        </div>

        {(desk.error || desk.notice) && (
          <div
            className={`notice glass ${desk.error ? "danger" : ""}`}
            role={desk.error ? "alert" : "status"}
          >
            <Info size={18} />
            <span>{desk.error || desk.notice}</span>
            {desk.error && (
              <button onClick={desk.retry} disabled={!!busy}>
                Retry
              </button>
            )}
          </div>
        )}
        {desk.accessRequired && (
          <section className="access-card glass">
            <h2>Operator access</h2>
            <p>
              Enter the access token configured on this server. It stays in
              memory for this session.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void desk.connect(token);
              }}
            >
              <input
                aria-label="Operator access token"
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <button className="primary-button" disabled={!!busy || !token}>
                Connect <ArrowRight />
              </button>
            </form>
          </section>
        )}

        <div className="workspace-grid">
          <aside className="left-stack" id="decision-controls">
            <div className="scenario-switch glass">
              <span className="eyebrow">SCENARIO</span>
              <select
                aria-label="Scenario"
                disabled={!!busy}
                value={snapshot?.scenario_id ?? "primary"}
                onChange={(e) => {
                  setView("orbit");
                  void desk.openScenario(e.target.value);
                }}
              >
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
                {snapshot?.scenario?.provenance?.source_kind ===
                  "PASTED_TLE" && (
                  <option value={snapshot.scenario_id}>
                    Pasted catalogue elements
                  </option>
                )}
              </select>
              <button
                className="subtle-button compact"
                onClick={() => setPanel("elements")}
                disabled={!!busy}
              >
                Use real elements <ArrowUpRight size={15} />
              </button>
            </div>
            <section className="metric-card glass">
              <div className="section-heading">
                <h2>Closest approach</h2>
                <button
                  className="icon-button compact"
                  aria-label="Focus closest approach"
                  onClick={() => jump()}
                  disabled={!variant || !!busy}
                >
                  <ArrowUpRight size={20} />
                </button>
              </div>
              <Metric value={minValue} unit={minUnit} />
              <p className={strike ? "caption strike-note" : "caption"}>
                {strike
                  ? "The objects occupy the same space. On this trajectory they collide."
                  : "Minimum to either object · 6-hour horizon"}
              </p>
              <div className="clearance-meter">
                <div
                  style={{
                    width: `${Math.min(100, ((worst?.value ?? 0) / ((policy?.min_separation_m ?? 1000) * 3)) * 100)}%`,
                  }}
                  className={
                    worst && worst.value < (policy?.min_separation_m ?? 1000)
                      ? "warning-fill"
                      : "clear-fill"
                  }
                />
                <i />
              </div>
              <div className="metric-foot">
                <Status tone={status.tone}>{status.label}</Status>
                <span>
                  {policy?.min_separation_m.toLocaleString() ?? "1,000"} m floor
                </span>
              </div>
            </section>

            <section
              className="decision-list"
              aria-label="Key maneuver comparison"
            >
              <div className="small-heading">
                <span>THE DECISION</span>
                <button onClick={() => setPanel("options")}>
                  All {analysis?.candidate_count ?? "25"} options{" "}
                  <ArrowUpRight />
                </button>
              </div>
              {comparison.length ? (
                comparison.map((item, i) => {
                  const state = optionStatus(item);
                  const active = item.candidate_id === selected;
                  const proposed =
                    item.candidate_id === snapshot?.proposal?.candidate_id;
                  const title =
                    item.kind === "NO_BURN"
                      ? "Do nothing"
                      : item.designed
                        ? "Designed by the planner"
                        : item.candidate_id === analysis?.recommended_id
                          ? "The clear alternative"
                          : "The hidden conflict";
                  return (
                    <button
                      key={item.candidate_id}
                      className={`option-card glass ${active ? "selected" : ""}`}
                      aria-pressed={active}
                      disabled={!!busy}
                      onClick={() => choose(item.candidate_id)}
                    >
                      <div className={`option-glyph ${state.tone}`}>
                        {item.kind === "NO_BURN" ? (
                          <GlobeHemisphereWest size={25} weight="light" />
                        ) : state.tone === "good" ? (
                          <ShieldCheck size={25} weight="light" />
                        ) : (
                          <WarningCircle size={25} weight="light" />
                        )}
                      </div>
                      <div>
                        <span className="option-title">{title}</span>
                        <span className="option-description">
                          {item.kind === "NO_BURN"
                            ? "Original trajectory"
                            : `${item.delta_v_mps.toFixed(2)} m/s · ${optionName(item)}`}
                        </span>
                        <Status tone={state.tone}>{state.label}</Status>
                        {/* Said out loud because the claim it supports — that
                            the agent is not just picking from a menu — is only
                            credible if you can see which option is not on it. */}
                        {item.designed && (
                          <span className="option-note">
                            Not on the grid · screened the same way
                          </span>
                        )}
                        {proposed && !item.designed && (
                          <span className="option-note">AI proposal</span>
                        )}
                      </div>
                      <span className="option-index">0{i + 1}</span>
                    </button>
                  );
                })
              ) : (
                <div className="loading-card glass">
                  <span className="loading-orbit" />
                  <p>{busy || "Load a scenario to compare options."}</p>
                </div>
              )}
              {/* A case with no answer showed one bad option and nothing else,
                  which reads as a gap rather than as the result. Saying it
                  plainly is the whole point of the scenario. */}
              {analysis && !analysis.recommended_id && (
                <div className="no-option glass" role="status">
                  <WarningCircle size={19} weight="light" />
                  <div>
                    <strong>Nothing here clears the floor.</strong>
                    <span>
                      All {analysis.candidate_count} options were screened and
                      none reaches{" "}
                      {policy?.min_separation_m.toLocaleString() ?? "1,000"} m.
                      That is the answer, not a missing one. Each option carries
                      its own reason in the full list.
                    </span>
                  </div>
                </div>
              )}
            </section>

            <button
              className="limits-summary glass"
              aria-label="Edit mission limits"
              onClick={() => setPanel("limits")}
            >
              <SlidersHorizontal size={18} weight="light" />
              <span>Mission limits</span>
              <strong>{policy?.max_delta_v_mps.toFixed(2) ?? "—"} m/s</strong>
              <ArrowUpRight size={15} />
            </button>
          </aside>

          <section
            className="scene-workspace"
            aria-label="Orbital view controls"
          >
            <div className="view-switch glass">
              <button
                className={`pill ${view === "orbit" ? "selected" : ""}`}
                onClick={() => {
                  setView("orbit");
                  setCameraReset((n) => n + 1);
                }}
              >
                <GlobeHemisphereWest size={17} />
                Orbit
              </button>
              <button
                className={`pill ${view === "approach" ? "selected" : ""}`}
                disabled={!variant}
                onClick={() => jump()}
              >
                <Crosshair size={17} />
                Close approach
              </button>
            </div>
            <div className="scene-bottom">
              <div className="scene-caption">
                <span className="coordinate-mark">⊕</span>
                <span>
                  {view === "orbit"
                    ? "Earth-centered view"
                    : "Local encounter view"}
                  <small>Drag to orbit · Scroll to zoom</small>
                </span>
              </div>
              <button
                className="view-tool glass"
                onClick={() => setCameraReset((n) => n + 1)}
                aria-label="Reset camera"
              >
                <Crosshair size={23} weight="light" />
              </button>
            </div>
            <div className="scene-disclosure">
              Object models enlarged for visibility. Positions and distances are
              computed.
            </div>
          </section>

          <aside className="right-stack">
            <section className="inspector glass">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">TRACKED SPACECRAFT</span>
                  <h2>
                    {snapshot?.scenario.provenance.object_name ||
                      "NOAA 20 (JPSS-1)"}
                  </h2>
                </div>
                <Status tone="good">TLE</Status>
              </div>
              <Suspense fallback={<div className="satellite-preview" />}>
                <SatellitePreview />
              </Suspense>
              <div className="model-caption">
                Illustrative spacecraft · drag to inspect
              </div>
              <div className="inspector-meta">
                <span>
                  NORAD{" "}
                  <strong>
                    {snapshot?.scenario.provenance.norad_id ?? "—"}
                  </strong>
                </span>
                <span>
                  Horizon{" "}
                  <strong>
                    {snapshot ? snapshot.scenario.horizon_s / 3600 : "—"} hours
                  </strong>
                </span>
              </div>
              <div className="pair-selector">
                <label htmlFor="debris">Measure to</label>
                <select
                  id="debris"
                  value={debrisId}
                  onChange={(e) => {
                    setDebrisId(e.target.value);
                    setCameraReset((n) => n + 1);
                  }}
                  disabled={!bundle}
                >
                  {(
                    bundle?.object_ids.filter(
                      (id) => id !== bundle.satellite_id,
                    ) ?? ["DEB-1", "DEB-2"]
                  ).map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </div>
              <div className="live-reading">
                <div>
                  <Metric value={liveValue} unit={liveUnit} />
                  <span>Separation at the shared clock</span>
                </div>
                <button
                  className="icon-button"
                  aria-label="Jump to selected object's closest approach"
                  onClick={() => jump(debrisId)}
                  disabled={!variant || !!busy}
                >
                  <ArrowUpRight size={23} />
                </button>
              </div>
            </section>

            <section className="planner-card glass">
              <div className="section-heading">
                <h2>
                  <Sparkle size={19} weight="light" />
                  Change the brief
                </h2>
                <Status tone={desk.health?.model_access ? "good" : "muted"}>
                  {desk.health?.model_access ? "AI ready" : "AI offline"}
                </Status>
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void desk.preview(instruction);
                }}
              >
                <label className="sr-only" htmlFor="instruction">
                  New restriction in plain English
                </label>
                <textarea
                  id="instruction"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="We lost a thruster. Halve the fuel budget."
                  maxLength={2000}
                  disabled={!!busy || !!snapshot?.execution}
                />
                <button
                  className="subtle-button full"
                  disabled={
                    !instruction.trim() ||
                    !!busy ||
                    !desk.health?.model_access ||
                    !!snapshot?.execution
                  }
                >
                  Preview restriction <ArrowUpRight size={17} />
                </button>
              </form>
              {!desk.health?.model_access && (
                <p className="caption">
                  Set GEMINI_API_KEY on the server to enable AI. Numerical
                  controls remain available.
                </p>
              )}
              <button
                className="primary-button full"
                onClick={desk.runPlanner}
                disabled={
                  !snapshot ||
                  !!busy ||
                  !desk.health?.model_access ||
                  !!snapshot?.execution
                }
              >
                <Sparkle size={18} />
                {busy.includes("AI planner")
                  ? "Planner running…"
                  : snapshot?.proposal
                    ? "Re-run AI planner"
                    : "Run AI planner"}
                <ArrowRight size={17} />
              </button>
              {snapshot && isApprovable(snapshot) && (
                <div className="proposal-review">
                  <Status tone="good">AI proposal · reviewer allowed</Status>
                  <p>{snapshot.proposal!.candidate_id}</p>
                  <button
                    className="subtle-button full"
                    disabled={!!busy}
                    onClick={() => choose(snapshot.proposal!.candidate_id)}
                  >
                    Inspect proposed trajectory <ArrowUpRight size={16} />
                  </button>
                  {selected !== snapshot.proposal!.candidate_id && (
                    <p className="caption">
                      Inspect this proposal on the chart before approving.
                    </p>
                  )}
                  <button
                    className="approve-button full"
                    onClick={desk.approve}
                    disabled={
                      !!busy || selected !== snapshot.proposal!.candidate_id
                    }
                  >
                    <Check size={18} />
                    Approve simulated maneuver
                  </button>
                </div>
              )}
              {snapshot?.execution && (
                <p className="execution-note">
                  <Check size={16} />
                  Recorded in simulation
                </p>
              )}
            </section>
          </aside>
        </div>

        <section
          className="timeline-panel glass"
          aria-label="Simulation timeline"
        >
          <div className="playback-row">
            <div className="playback-controls">
              <button
                className="play-button"
                aria-label={playing ? "Pause simulation" : "Play simulation"}
                disabled={!bundle || !!busy}
                onClick={() => {
                  if (bundle && desk.time >= bundle.horizon_s) desk.setTime(0);
                  setPlaying(!playing);
                }}
              >
                {playing ? (
                  <Pause size={20} weight="fill" />
                ) : (
                  <Play size={20} weight="fill" />
                )}
              </button>
              <div className="time-readout">
                <span>SIMULATION CLOCK</span>
                <time data-testid="simulation-clock">
                  T+ {clockText(bundle?.t_s[sample] ?? 0)}
                </time>
              </div>
              <select
                className="speed-control"
                aria-label="Playback speed"
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
              >
                {[30, 180, 600].map((s) => (
                  <option value={s} key={s}>
                    {s}×
                  </option>
                ))}
              </select>
            </div>
            <div className="scrubber">
              <input
                aria-label="Simulation time"
                type="range"
                min="0"
                max={bundle?.horizon_s ?? 21600}
                step="1"
                value={desk.time}
                disabled={!bundle || !!busy}
                onChange={(e) => seek(Number(e.target.value))}
              />
              <span>00:00:00</span>
              <span>06:00:00</span>
            </div>
            <button
              className="subtle-button event-jump"
              onClick={() => jump()}
              disabled={!variant || !!busy}
            >
              Closest approach <ArrowDown size={16} />
            </button>
          </div>
          {bundle && variant ? (
            <SeparationChart
              bundle={bundle}
              selected={selected}
              sample={sample}
              onSeek={seek}
            />
          ) : (
            <div className="chart-placeholder">
              <span className="loading-orbit" />
              {busy || "Numerical evidence will appear here."}
            </div>
          )}
        </section>
        <footer className="workspace-footer">
          <span>
            <i />
            Two-body simulation <span className="dot-separator">/</span>{" "}
            {analysis
              ? `${analysis.candidate_count} options · ${analysis.elapsed_s.toFixed(2)} s numerical analysis`
              : "Awaiting computed evidence"}
          </span>
          <div>
            <button onClick={() => setPanel("about")}>
              Data & model notes
            </button>
            <button onClick={desk.reset} disabled={!snapshot || !!busy}>
              <ArrowsClockwise size={15} />
              Reset case
            </button>
            <button onClick={desk.exportEvidence} disabled={!bundle || !!busy}>
              <DownloadSimple size={15} />
              Export evidence
            </button>
          </div>
        </footer>
        {!!busy && (
          <div className="busy-indicator glass" role="status">
            <span className="loading-orbit" />
            {busy}
          </div>
        )}
      </main>

      {panel === "elements" && (
        <Dialog
          title="Screen real catalogue objects"
          onClose={() => setPanel(null)}
        >
          <p className="dialog-intro">
            Paste two-line element sets — a spacecraft and whatever you want it
            screened against. The same two independent paths run on those
            orbits instead of a generated fixture.
          </p>

          <div className="elements-panel">
            <label className="visually-hidden" htmlFor="pasted-elements">
              Two-line element sets
            </label>
            <textarea
              id="pasted-elements"
              className="record-input tall"
              rows={10}
              spellCheck={false}
              placeholder={
                "NOAA 20 (JPSS-1)\n" +
                "1 43013U 17073A   26254.91060846  .00000019  00000+0  30092-4 0  9999\n" +
                "2 43013  98.7810 193.6155 0001610  53.1622 306.9701 14.19525379456774\n" +
                "…and at least one more object"
              }
              value={elements}
              onChange={(e) => {
                setElements(e.target.value);
                setElementsError("");
              }}
            />

            <div className="elements-controls">
              <label>
                Which one can manoeuvre
                <select
                  value={elementsIndex}
                  onChange={(e) => setElementsIndex(Number(e.target.value))}
                >
                  {elementNames.map((name, index) => (
                    <option key={index} value={index}>
                      {index + 1}. {name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="primary-button"
                disabled={elementNames.length < 2 || !!busy}
                onClick={async () => {
                  setElementsError("");
                  try {
                    await desk.openPastedElements(elements, elementsIndex);
                    setPanel(null);
                    setView("orbit");
                  } catch (e) {
                    setElementsError(
                      e instanceof Error ? e.message : "Could not read those.",
                    );
                  }
                }}
              >
                Screen these objects <ArrowRight size={16} />
              </button>
            </div>

            {elements.trim() && (
              <p className="caption">
                {elementNames.length === 0
                  ? "No element sets recognised yet."
                  : `${elementNames.length} object${
                      elementNames.length === 1 ? "" : "s"
                    } recognised: ${elementNames.join(", ")}${
                      elementNames.length < 2
                        ? ". At least two are needed."
                        : "."
                    }`}
              </p>
            )}
            {elementsError && (
              <p className="exchange-error">
                <WarningCircle size={16} /> {elementsError}
              </p>
            )}
          </div>

          <h3>What this is, and what it is not</h3>
          <p className="caption">
            The orbits are real. Every state vector comes from the element sets
            you paste, evaluated with SGP4 at one shared epoch — element sets
            are published hours apart, and screening them at their own epochs
            would compare positions that never coexisted.
          </p>
          <p className="caption">
            Propagation from that epoch is two-body, so this is not an SGP4
            conjunction analysis; over six hours in low orbit the difference is
            kilometres. No element set carries covariance, so nothing here
            states a probability. Two catalogue objects usually have no close
            approach at all, and reporting that is the point — a screening tool
            that always finds something is not screening.
          </p>
          <p className="caption">
            Current element sets are at{" "}
            <span className="mono">celestrak.org/NORAD/elements/</span>.
          </p>
        </Dialog>
      )}

      {panel === "limits" && (
        <Dialog title="Mission limits" onClose={() => setPanel(null)}>
          <section className="budget-card">
            <p className="dialog-intro">
              Change the delta-v budget directly. Applying a limit creates a new
              policy version and recomputes every option; existing proposals
              become stale.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void desk.setBudget(Number(budget));
              }}
            >
              <label htmlFor="budget">
                Delta-v budget{" "}
                <span>Policy v{snapshot?.policy_version ?? "—"}</span>
              </label>
              <div className="input-row">
                <input
                  id="budget"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  required
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  disabled={!!busy || !!snapshot?.execution}
                />
                <span>m/s</span>
                <button
                  aria-label="Apply delta-v budget"
                  disabled={
                    !snapshot ||
                    !!busy ||
                    !!snapshot.execution ||
                    !budget ||
                    Number(budget) === policy?.max_delta_v_mps
                  }
                >
                  Apply <ArrowRight size={15} />
                </button>
              </div>
            </form>
            <p className="caption">
              Delta-v is a fuel proxy; no propellant mass is modeled. The
              clearance floor remains{" "}
              {policy?.min_separation_m.toLocaleString()} m.
            </p>
            {!!policy?.blocked_windows.length && (
              <p className="caption">
                Blocked windows:{" "}
                {policy.blocked_windows.map((w) => w.label).join(", ")}
              </p>
            )}
            {analysis && (
              <p className="limit-result">
                <Status tone={analysis.recommended_id ? "good" : "watch"}>
                  {analysis.recommended_id
                    ? "Verified alternative available"
                    : "No verified option in this grid"}
                </Status>
              </p>
            )}
          </section>
        </Dialog>
      )}

      {desk.diff && (
        <Dialog title="Review the new restriction" onClose={desk.dismissDiff}>
          <p className="dialog-intro">
            The current policy stays active until you confirm.
          </p>
          {desk.diff.status === "NEEDS_CLARIFICATION" ? (
            <p>{desk.diff.clarification}</p>
          ) : (
            <>
              <div className="policy-changes">
                {desk.diff.changes.map((change) => (
                  <div key={change.field}>
                    <span>
                      {change.field === "max_delta_v_mps"
                        ? "Delta-v budget (m/s)"
                        : "Blocked burn windows"}
                    </span>
                    <strong>
                      {JSON.stringify(change.before)} <ArrowRight />{" "}
                      {JSON.stringify(change.after)}
                    </strong>
                  </div>
                ))}
              </div>
              <button
                className="primary-button"
                onClick={desk.confirm}
                disabled={!!busy}
              >
                Confirm & recompute <ArrowRight />
              </button>
            </>
          )}
        </Dialog>
      )}

      {panel === "options" && (
        <Dialog
          title="Every maneuver. Every tradeoff."
          onClose={() => setPanel(null)}
        >
          <div className="dialog-intro">
            {analysis?.candidate_count ?? 25} options include the no-burn
            baseline. The first screen considers the primary threat; independent
            verification checks every object in the scenario.
            {designedCount > 0 && (
              <>
                {" "}
                {designedCount} of them {designedCount === 1 ? "was" : "were"}{" "}
                designed by the planner rather than taken from the grid, and{" "}
                {designedCount === 1 ? "was" : "were"} verified the same way.
              </>
            )}
          </div>
          <div className="table-tools">
            <div className="segmented">
              <button
                className={filter === "all" ? "selected" : ""}
                onClick={() => setFilter("all")}
              >
                All options
              </button>
              <button
                className={filter === "verified" ? "selected" : ""}
                onClick={() => setFilter("verified")}
              >
                Verified clear
              </button>
              <button
                className={filter === "rejected" ? "selected" : ""}
                onClick={() => setFilter("rejected")}
              >
                Rejected
              </button>
            </div>
            <Status tone={analysis?.recommended_id ? "good" : "watch"}>
              {analysis?.recommended_id
                ? "Alternative found"
                : "No verified option in this grid"}
            </Status>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Maneuver</th>
                  <th>Delta-v</th>
                  <th>Primary minimum</th>
                  <th>Independent check</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {analysis?.options
                  .filter(
                    (o) =>
                      filter === "all" ||
                      (filter === "verified"
                        ? o.validation?.status === "PASS"
                        : o.validation?.status === "BLOCK"),
                  )
                  .sort((a, b) => (a.rank ?? 100) - (b.rank ?? 100))
                  .map((o) => {
                    const s = optionStatus(o);
                    const d = distance(o.primary_encounter?.min_separation_m);
                    return (
                      <tr
                        key={o.candidate_id}
                        className={
                          o.candidate_id === selected ? "selected" : ""
                        }
                      >
                        <td>
                          {optionName(o)}
                          {/* This table is titled "every manoeuvre", so it has
                              to say which ones were never on the menu. */}
                          {o.designed && <em className="designed-tag">designed</em>}
                          <small>{o.candidate_id}</small>
                        </td>
                        <td>{o.delta_v_mps.toFixed(3)} m/s</td>
                        <td>{d.join(" ")}</td>
                        <td>
                          <Status tone={s.tone}>{s.label}</Status>
                          {o.validation?.blocked_by.map((b) => (
                            <small key={b.object_id}>
                              {b.object_id}: {b.min_separation_m.toFixed(1)} m
                            </small>
                          ))}
                        </td>
                        <td>
                          <button
                            className="subtle-button"
                            disabled={!!busy}
                            onClick={async () => {
                              await choose(o.candidate_id);
                              setPanel(null);
                            }}
                          >
                            Inspect <ArrowUpRight />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </Dialog>
      )}

      {panel === "evidence" && (
        <Dialog
          title="Evidence, with a paper trail."
          onClose={() => setPanel(null)}
        >
          <div className="evidence-summary">
            <div>
              <span>Case</span>
              <strong>{snapshot?.case_id ?? "—"}</strong>
            </div>
            <div>
              <span>Policy</span>
              <strong>v{snapshot?.policy_version ?? "—"}</strong>
            </div>
            <div>
              <span>Numerical outcome</span>
              <strong>
                {analysis?.recommended_id ?? "No verified option"}
              </strong>
            </div>
          </div>
          <h3>What the independent check found</h3>
          {comparison
            .filter((o) => o.validation)
            .map((o) => (
              <article className="evidence-item" key={o.candidate_id}>
                <Status tone={optionStatus(o).tone}>
                  {o.candidate_id} · {optionStatus(o).label}
                </Status>
                <p>
                  {o
                    .validation!.encounters.map(
                      (e) =>
                        `${e.object_id}: ${e.min_separation_m.toFixed(1)} m at T+${clockText(e.tca_s)}`,
                    )
                    .join(" · ")}
                </p>
              </article>
            ))}
          <p className="caption">
            Numerical comparison only. A separate AI proposal and reviewer ALLOW
            are required for simulated approval.
          </p>
          <h3>Agent & operator activity</h3>
          {snapshot?.runs.map((run) => (
            <article className="evidence-item" key={run.run_id}>
              <Status
                tone={
                  run.status === "FAILED"
                    ? "danger"
                    : run.status === "DONE"
                      ? "good"
                      : "watch"
                }
              >
                {run.kind} · {run.status}
              </Status>
              <p>
                {run.result.status}{" "}
                {run.result.elapsed_s !== undefined
                  ? `· ${run.result.elapsed_s.toFixed(1)} s · ${run.result.model_calls} model calls`
                  : ""}
              </p>
              {run.error && <p>{run.error}</p>}
              {!!run.result.flagged_numbers?.length && (
                <p className="warning-text">
                  Unsupported numbers detected in model prose:{" "}
                  {run.result.flagged_numbers.join(", ")}. Use the computed
                  evidence.
                </p>
              )}
            </article>
          ))}
          {!snapshot?.events.length && (
            <p className="empty-state">
              No AI run yet. The comparison above was computed by the numerical
              engine.
            </p>
          )}
          <ol className="event-list">
            {snapshot?.events.map((event) => (
              <li key={event.event_id}>
                <span>{event.event_type.replaceAll("_", " ")}</span>
                <p>{event.summary}</p>
                <small>{event.duration_ms.toFixed(0)} ms</small>
              </li>
            ))}
          </ol>
          <h3>
            Exchange with another operator{" "}
            <span className="caption">CCSDS-shaped record · recomputed, not trusted</span>
          </h3>
          <p className="caption">
            A record that only states a conclusion has to be taken on trust. This
            one carries the state vectors and the manoeuvre, so whoever receives
            it can recompute every figure in it — and disagree.
          </p>

          <div className="exchange">
            <div className="exchange-half">
              <h4>Issue this decision</h4>
              <button
                className="subtle-button"
                onClick={issueRecord}
                disabled={!snapshot || !!exchangeBusy}
              >
                {exchangeBusy === "Issuing the record"
                  ? "Issuing…"
                  : "Issue record"}{" "}
                <ArrowUpRight size={16} />
              </button>
              {issued && (
                <>
                  <p className="caption">
                    {issued.length.toLocaleString()} bytes ·{" "}
                    {issued.split("\n").filter((l) => l.startsWith("X_DOT")).length}{" "}
                    state vectors · no covariance, so no probability
                  </p>
                  <pre className="record" aria-label="Issued conjunction record">
                    {issued}
                  </pre>
                  <button
                    className="subtle-button"
                    onClick={() => {
                      setReceived(issued);
                      setChecked(null);
                    }}
                  >
                    Hand it to the other operator <ArrowRight size={16} />
                  </button>
                </>
              )}
            </div>

            <div className="exchange-half">
              <h4>Check a received record</h4>
              <label className="visually-hidden" htmlFor="received-record">
                Conjunction record received from another operator
              </label>
              <textarea
                id="received-record"
                className="record-input"
                rows={6}
                spellCheck={false}
                placeholder="Paste a CCSDS conjunction record here."
                value={received}
                onChange={(e) => {
                  setReceived(e.target.value);
                  setChecked(null);
                }}
              />
              <button
                className="primary-button"
                onClick={checkRecord}
                disabled={!received.trim() || !!exchangeBusy}
              >
                {exchangeBusy === "Recomputing the record"
                  ? "Recomputing…"
                  : "Recompute it"}{" "}
                <ArrowRight size={16} />
              </button>

              {exchangeError && (
                <p className="exchange-error">
                  <WarningCircle size={16} /> {exchangeError}
                </p>
              )}

              {checked && (
                <div className={`exchange-result verdict-${checked.verdict.toLowerCase()}`}>
                  <p className="exchange-verdict">
                    {checked.verdict === "AGREES" && (
                      <>
                        <Check size={16} /> Its numbers hold
                      </>
                    )}
                    {checked.verdict === "DISAGREES" && (
                      <>
                        <WarningCircle size={16} /> Its numbers do not hold
                      </>
                    )}
                    {checked.verdict === "NO_CLAIMS" && (
                      <>It claims nothing — so we screened it ourselves</>
                    )}
                    <span className="caption">
                      from {checked.originator} · recomputed at{" "}
                      {checked.independent_result.sample_step_s} s
                    </span>
                  </p>
                  {/* With no claims there is nothing to compare against, so the
                      table shows what we found rather than four empty columns. */}
                  <div className="table-scroll">
                    <table>
                      <thead>
                        {checked.verdict === "NO_CLAIMS" ? (
                          <tr>
                            <th>Object</th>
                            <th>Closest approach</th>
                            <th>At</th>
                            <th>Relative speed</th>
                          </tr>
                        ) : (
                          <tr>
                            <th>Object</th>
                            <th>Claimed</th>
                            <th>Recomputed</th>
                            <th>Difference</th>
                          </tr>
                        )}
                      </thead>
                      <tbody>
                        {checked.verdict === "NO_CLAIMS" &&
                          checked.independent_result.encounters.map((e) => (
                            <tr key={e.object_id}>
                              <td>{e.object_id}</td>
                              <td>
                                {e.min_separation_m.toLocaleString(undefined, {
                                  maximumFractionDigits: 1,
                                })}{" "}
                                m
                              </td>
                              <td>T+{clockText(e.tca_s)}</td>
                              <td>
                                {e.relative_speed_mps.toLocaleString(undefined, {
                                  maximumFractionDigits: 0,
                                })}{" "}
                                m/s
                              </td>
                            </tr>
                          ))}
                        {checked.checks.map((check) => (
                          <tr
                            key={check.object_id}
                            className={check.agrees ? "" : "row-disagrees"}
                          >
                            <td>{check.object_id}</td>
                            <td>
                              {check.claimed_miss_distance_m.toLocaleString(
                                undefined,
                                { maximumFractionDigits: 1 },
                              )}{" "}
                              m
                            </td>
                            <td>
                              {check.recomputed_miss_distance_m === null
                                ? "—"
                                : `${check.recomputed_miss_distance_m.toLocaleString(
                                    undefined,
                                    { maximumFractionDigits: 1 },
                                  )} m`}
                            </td>
                            <td>
                              {check.distance_delta_m === undefined
                                ? "—"
                                : `${check.distance_delta_m.toExponential(2)} m`}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {checked.checks
                    .filter((c) => !c.agrees)
                    .map((c) => (
                      <p className="exchange-error" key={c.object_id}>
                        {c.reason}
                      </p>
                    ))}
                  <p className="caption">{checked.note}</p>
                </div>
              )}
            </div>
          </div>

          <h3>
            Real-world context{" "}
            <span className="caption">
              Frozen SOCRATES snapshot · display only
            </span>
          </h3>
          {desk.context ? (
            <>
              <p className="caption">
                Retrieved {desk.context.retrieved_at_utc}. These records do not
                drive this simulation.
              </p>
              <p className="caption">
                Most of these involve a communications satellite —{" "}
                {
                  desk.context.rows.filter((row) =>
                    /STARLINK|ONEWEB|IRIDIUM|GLOBALSTAR|INTELSAT|KUIPER|KINEIS/i.test(
                      `${row.OBJECT_NAME_1} ${row.OBJECT_NAME_2}`,
                    ),
                  ).length
                }{" "}
                of {desk.context.rows.length} shown, against debris from the
                Fengyun 1C and Cosmos break-ups. The constellations that carry
                global connectivity share these shells with the debris, which is
                what makes one operator&rsquo;s manoeuvre everyone&rsquo;s
                problem.
              </p>
              <div className="table-scroll context-table">
                <table>
                  <thead>
                    <tr>
                      {Object.keys(desk.context.rows[0] ?? {}).map((key) => (
                        <th key={key}>{key.replaceAll("_", " ")}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {desk.context.rows.map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((value, j) => (
                          <td key={j}>{value}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="caption">Context snapshot unavailable.</p>
          )}
          <button
            className="primary-button"
            onClick={desk.exportEvidence}
            disabled={!bundle || !!busy}
          >
            <DownloadSimple />
            Export this evidence
          </button>
        </Dialog>
      )}

      {panel === "about" && (
        <Dialog
          title="A real orbit. An honest simulation."
          onClose={() => setPanel(null)}
        >
          <p className="dialog-intro">
            Orion West is a working name. One spacecraft, two
            synthetic debris objects, six simulated hours.
          </p>
          <dl className="provenance-list">
            <dt>Catalog seed</dt>
            <dd>
              {snapshot?.scenario.provenance.object_name} · NORAD{" "}
              {snapshot?.scenario.provenance.norad_id}
            </dd>
            <dt>Frozen TLE epoch</dt>
            <dd>{snapshot?.scenario.provenance.tle_epoch_utc}</dd>
            <dt>Reference frame</dt>
            <dd>{bundle?.frame || "SIM_ECI_TEME_SEEDED"}</dd>
            <dt>Propagation</dt>
            <dd>
              Two-body gravity and instantaneous impulses. No drag, J2,
              navigation uncertainty, or collision probability.
            </dd>
            <dt>Verification</dt>
            <dd>
              Fresh reconstruction, one-second sampling and independent
              encounter refinement. The tested Kepler propagator is shared.
            </dd>
            <dt>3D rendering</dt>
            <dd>
              Markers use the same sample as the chart. Models are enlarged;
              their apparent size and overlap do not describe risk. Earth
              orientation, light and spacecraft attitude are illustrative.
            </dd>
            <dt>Earth imagery</dt>
            <dd>
              <a
                href="https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/"
                target="_blank"
                rel="noreferrer"
              >
                NASA Earth Observatory · Blue Marble, September 2004 ↗
              </a>
            </dd>
            <dt>Visual system</dt>
            <dd>
              Adapted from the supplied design.md and its glass palette. Inter
              and Phosphor assets retain their licenses.
            </dd>
          </dl>
          <p className="empty-state">
            Execution stays inside the simulation. Nothing is transmitted to a
            satellite.
          </p>
        </Dialog>
      )}
    </div>
  );
}
