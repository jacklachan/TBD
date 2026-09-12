import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
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
import {
  EventTrack,
  Gauge,
  MissionClock,
  OptionGrid,
  separationGauge,
} from "./components/Telemetry";
import { countTo, revealWorkspace } from "./motion";
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
/**
 * The one line that says what is happening.
 *
 * The workspace showed a distance and left the reader to work out whether it
 * was bad, and showed nothing at all about what a manoeuvre changed. This
 * states the situation, and once an option is selected, states the before and
 * after as a single comparison.
 */
function Verdict({
  baselineMetres,
  currentMetres,
  floor,
  isBaseline,
  cleared,
  breachedObject,
  executed,
}: {
  baselineMetres?: number;
  currentMetres?: number;
  floor: number;
  isBaseline: boolean;
  cleared: boolean;
  breachedObject?: { object_id: string; min_separation_m: number };
  executed: boolean;
}) {
  if (baselineMetres === undefined || currentMetres === undefined) return null;
  const [baseValue, baseUnit] = distance(baselineMetres);
  const [nowValue, nowUnit] = distance(currentMetres);
  const atRisk = currentMetres < floor;
  const tone = atRisk ? "risk" : cleared ? "clear" : "watch";

  return (
    <div className={`verdict verdict-${tone} glass`}>
      <span className="verdict-state">
        {atRisk
          ? "Collision risk"
          : executed
            ? "Manoeuvre applied"
            : cleared
              ? "Cleared"
              : "Screened"}
      </span>
      {isBaseline ? (
        <p className="verdict-line">
          Doing nothing brings the satellite within{" "}
          <b>
            {baseValue} {baseUnit}
          </b>{" "}
          — inside the {floor.toLocaleString()} m floor.
        </p>
      ) : (
        <p className="verdict-line">
          <span className="verdict-change">
            <b className="was">
              {baseValue} {baseUnit}
            </b>
            <span aria-hidden="true">→</span>
            <b className="now">
              {nowValue} {nowUnit}
            </b>
          </span>
          {atRisk && breachedObject
            ? ` still inside the floor — ${breachedObject.object_id} at ${distance(breachedObject.min_separation_m)[0]} ${distance(breachedObject.min_separation_m)[1]}.`
            : " clear of every tracked object."}
        </p>
      )}
    </div>
  );
}

function Metric({
  value,
  unit,
  metres,
  className = "",
}: {
  value: string;
  unit: string;
  /** Raw metres. When supplied the figure counts to its new value instead of
      snapping, and is re-formatted every frame so the units stay honest. */
  metres?: number;
  className?: string;
}) {
  const figure = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (metres === undefined || !Number.isFinite(metres)) return;
    countTo(figure.current, metres, (n) => distance(n)[0]);
  }, [metres]);
  return (
    <div className={`metric ${className}`}>
      <span className="metric-figure" ref={figure}>
        {value}
      </span>
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
    "options" | "evidence" | "about" | "limits" | null
  >(null);
  const [instruction, setInstruction] = useState("");
  const [token, setToken] = useState("");
  const [budget, setBudget] = useState("0.20");
  const [filter, setFilter] = useState("all");
  const variant = currentVariant(bundle, selected);
  // One entrance, the first time there is something to show.
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    if (!bundle || revealed) return;
    setRevealed(true);
    requestAnimationFrame(() => revealWorkspace());
  }, [bundle, revealed]);
  const option = analysis?.options.find((o) => o.candidate_id === selected);
  const worst = useMemo(
    () => (variant ? minimum(variant.min_to_any_m) : null),
    [variant],
  );
  const [minValue, minUnit] = distance(worst?.value);
  const liveDistance = variant?.pair_separations_m[debrisId]?.[sample];
  const [liveValue, liveUnit] = distance(liveDistance);
  const baselineVariant = bundle?.variants.find((v) => v.kind === "NO_BURN");
  const baselineWorst = useMemo(
    () => (baselineVariant ? minimum(baselineVariant.min_to_any_m) : null),
    [baselineVariant],
  );
  const policy = snapshot?.policy;
  // Open on the encounter. At t+0 the objects are thousands of kilometres
  // apart and nothing looks wrong, so the case opened on its quietest moment.
  const [framed, setFramed] = useState(false);
  useEffect(() => {
    if (!bundle || !variant || framed) return;
    setFramed(true);
    setView("approach");
    const worstEncounter = variant.encounters.reduce(
      (best, e) =>
        !best || e.min_separation_m < best.min_separation_m ? e : best,
      variant.encounters[0],
    );
    if (worstEncounter) {
      setDebrisId(worstEncounter.object_id);
      desk.setTime(worstEncounter.tca_s);
    }
  }, [bundle, variant, framed, desk]);

  const status = option
    ? optionStatus(option)
    : { label: "Awaiting analysis", tone: "muted" };
  const comparison = analysis
    ? comparisonIds(analysis).map((id) =>
        analysis.options.find((o) => o.candidate_id === id)!,
      )
    : [];

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

      <main>
        <div className="page-heading">
          <div>
            <div className="eyebrow">MISSION CONTROL / SIMULATION</div>
            <h1>Every option, checked twice.</h1>
            <p>Two independent paths. One answer.</p>
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
            <Verdict
              baselineMetres={baselineWorst?.value}
              currentMetres={worst?.value}
              floor={policy?.min_separation_m ?? 1000}
              isBaseline={!variant || variant.kind === "NO_BURN"}
              cleared={option?.validation?.status === "PASS"}
              breachedObject={variant?.encounters.find((e) => e.below_floor)}
              executed={!!snapshot?.execution}
            />
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
              </select>
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
              <Metric value={minValue} unit={minUnit} metres={worst?.value} />
              <p className="caption">
                Minimum to either object · 6-hour horizon
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
                  const title =
                    item.kind === "NO_BURN"
                      ? "Do nothing"
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
                  <Metric value={liveValue} unit={liveUnit} metres={liveDistance} />
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
                  {baselineWorst && worst
                    ? `Applied in simulation. Closest approach ${distance(baselineWorst.value)[0]} ${distance(baselineWorst.value)[1]} → ${distance(worst.value)[0]} ${distance(worst.value)[1]}.`
                    : "Applied in simulation."}
                </p>
              )}
            </section>
          </aside>
        </div>

        <section
          className="timeline-panel glass"
          aria-label="Simulation timeline"
        >
          <div className="playback-row telemetry">
            <div className="telemetry-cluster left">
              {(() => {
                const sep = separationGauge(variant, sample, policy);
                return (
                  <>
                    <Gauge
                      label="Separation"
                      value={sep.value}
                      unit={sep.unit}
                      fill={sep.fill}
                      tone={sep.tone}
                    />
                    <Gauge
                      label="Clearance"
                      value={sep.ratio ? sep.ratio.toFixed(1) : "—"}
                      unit="× floor"
                      fill={Math.min(1, sep.ratio / 3)}
                      tone={sep.ratio && sep.ratio < 1 ? "danger" : "normal"}
                    />
                  </>
                );
              })()}
            </div>
            <div className="telemetry-centre">
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
            <MissionClock
              time={bundle?.t_s[sample] ?? 0}
              scenario={snapshot?.scenario_id ?? "—"}
            />
            {bundle && (
              <EventTrack
                bundle={bundle}
                variant={variant}
                time={bundle.t_s[sample] ?? 0}
              />
            )}
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
            <div className="telemetry-cluster right">
              <Gauge
                label="Delta-v"
                value={(variant?.delta_v_mps ?? 0).toFixed(3)}
                unit="m/s"
                fill={
                  policy?.max_delta_v_mps
                    ? (variant?.delta_v_mps ?? 0) / policy.max_delta_v_mps
                    : 0
                }
                tone="chrome"
              />
              <OptionGrid
                analysis={analysis}
                selected={selected}
                onSelect={choose}
              />
            </div>
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
            verification checks both objects.
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
