/**
 * Launch-broadcast telemetry, built from values the backend already computed.
 *
 * The parts map onto this product rather than being borrowed wholesale: the
 * gauges read separation and clearance instead of speed and altitude, the event
 * track carries the real burn and encounter times out of the visualization
 * bundle, and the engine grid becomes the option grid — twenty-five dots, one
 * per manoeuvre, coloured by what the verifier actually returned.
 *
 * Nothing here computes physics. Every figure is a supplied value formatted for
 * display, or a ratio of two supplied values.
 */

import type { Analysis, Policy, VisualizationBundle } from "../contracts";
import type { VisualizationVariant } from "../contracts";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  const h = String(Math.floor(whole / 3600)).padStart(2, "0");
  const m = String(Math.floor((whole % 3600) / 60)).padStart(2, "0");
  const s = String(whole % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

/** Arc gauge. `fill` is 0–1 of the sweep; beyond 1 it simply pins full. */
export function Gauge({
  label,
  value,
  unit,
  fill,
  tone = "normal",
}: {
  label: string;
  value: string;
  unit: string;
  fill: number;
  tone?: "normal" | "danger" | "chrome";
}) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  // Three quarters of the circle, opened at the bottom like a broadcast dial.
  const sweep = circumference * 0.75;
  const shown = Math.max(0, Math.min(1, fill)) * sweep;

  return (
    <div className={`gauge gauge-${tone}`}>
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <circle
          className="gauge-track"
          cx="32"
          cy="32"
          r={radius}
          strokeDasharray={`${sweep} ${circumference}`}
        />
        <circle
          className="gauge-fill"
          cx="32"
          cy="32"
          r={radius}
          strokeDasharray={`${shown} ${circumference}`}
        />
      </svg>
      <div className="gauge-readout">
        <strong>{value}</strong>
        <span>{unit}</span>
      </div>
      <p className="gauge-label">{label}</p>
    </div>
  );
}

/**
 * The mission event track: start, the burn, every encounter, the horizon end.
 * Times come from the bundle, so the marks sit where the numbers say and move
 * when the selected option changes.
 */
export function EventTrack({
  bundle,
  variant,
  time,
}: {
  bundle: VisualizationBundle;
  variant: VisualizationVariant | null | undefined;
  time: number;
}) {
  const horizon = bundle.horizon_s || 1;
  const marks: { at: number; label: string; tone: string }[] = [
    { at: 0, label: "Start", tone: "plain" },
  ];

  if (variant?.burn_t_s != null) {
    marks.push({ at: variant.burn_t_s, label: "Burn", tone: "chrome" });
  }
  for (const encounter of variant?.encounters ?? []) {
    marks.push({
      at: encounter.tca_s,
      label: encounter.object_id,
      tone: encounter.below_floor ? "danger" : "plain",
    });
  }
  marks.push({ at: horizon, label: "End", tone: "plain" });

  // Two encounters can land close together at this width; keep the earlier
  // label and drop the collision rather than overprinting them.
  const spaced = marks
    .sort((a, b) => a.at - b.at)
    .filter((mark, index, all) =>
      index === 0 ? true : (mark.at - all[index - 1].at) / horizon > 0.055,
    );

  return (
    <div className="event-track">
      <div className="event-rail" />
      <div
        className="event-progress"
        style={{ width: `${Math.min(100, (time / horizon) * 100)}%` }}
      />
      {spaced.map((mark) => (
        <div
          key={`${mark.label}-${mark.at}`}
          className={`event-mark event-${mark.tone} ${time >= mark.at ? "passed" : ""}`}
          style={{ left: `${(mark.at / horizon) * 100}%` }}
        >
          <i />
          <span>{mark.label}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Every option at once, the way a launch broadcast shows every engine: one dot
 * per manoeuvre, filled by what the verifier returned. Crimson is a breach,
 * paper is verified clear, hollow is excluded before verification.
 */
export function OptionGrid({
  analysis,
  selected,
  onSelect,
}: {
  analysis: Analysis | null;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const options = analysis?.options ?? [];
  const clear = options.filter((o) => o.validation?.status === "PASS").length;
  const rejected = options.filter(
    (o) => o.validation?.status === "BLOCK" || o.validation?.status === "ERROR",
  ).length;

  return (
    <div className="option-grid">
      <div className="option-dots" role="list">
        {options.map((option) => {
          const state =
            option.validation?.status === "PASS"
              ? "clear"
              : option.validation?.status === "BLOCK" ||
                  option.validation?.status === "ERROR"
                ? "rejected"
                : option.primary_qualified
                  ? "screened"
                  : "excluded";
          return (
            <button
              key={option.candidate_id}
              role="listitem"
              type="button"
              className={`option-dot dot-${state} ${option.candidate_id === selected ? "current" : ""}`}
              onClick={() => onSelect(option.candidate_id)}
              title={`${option.candidate_id} · ${option.delta_v_mps.toFixed(3)} m/s`}
              aria-label={`Option ${option.candidate_id}, ${state}`}
            />
          );
        })}
      </div>
      <p className="gauge-label">
        {options.length ? `${clear} clear · ${rejected} rejected` : "Options"}
      </p>
    </div>
  );
}

/** Mission clock and scenario name, set like a broadcast counter. */
export function MissionClock({
  time,
  scenario,
}: {
  time: number;
  scenario: string;
}) {
  return (
    <div className="mission-clock">
      <time data-testid="simulation-clock">
        <span>T+</span>
        {clock(time)}
      </time>
      <p>{scenario}</p>
    </div>
  );
}

export function separationGauge(
  variant: VisualizationVariant | null | undefined,
  sample: number,
  policy: Policy | undefined,
) {
  const metres = variant?.min_to_any_m?.[sample];
  const floor = policy?.min_separation_m ?? 1000;
  if (metres == null) {
    return { value: "—", unit: "km", fill: 0, tone: "normal" as const, ratio: 0 };
  }
  const ratio = metres / floor;
  return {
    value: metres >= 1000 ? (metres / 1000).toFixed(2) : Math.round(metres).toString(),
    unit: metres >= 1000 ? "km" : "m",
    // Full sweep at five times the floor; anything past that is simply clear.
    fill: Math.min(1, metres / (floor * 5)),
    tone: ratio < 1 ? ("danger" as const) : ("normal" as const),
    ratio,
  };
}
