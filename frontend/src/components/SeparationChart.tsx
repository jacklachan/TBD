import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowsOutSimple, MagnifyingGlassPlus } from "@phosphor-icons/react";
import type { VisualizationBundle } from "../contracts";
import {
  clockText,
  currentVariant,
  minimum,
  nearestSample,
} from "../workspace";

interface Props {
  bundle: VisualizationBundle;
  selected: string;
  sample: number;
  onSeek: (time: number) => void;
}

// Linear axis, clipped. Everything that decides a verdict lives between zero
// and a few kilometres; a log axis spanning 0.1 km to 10,000 km rendered every
// dip as the same dot on the bottom line and the three variants as one curve.
// The ceiling is the smallest of these that leaves the closest approach of
// every plotted variant inside the frame with room above it.
// [ceiling, gridline step], both in metres.
const CEILINGS_M: [number, number][] = [
  [2_000, 500],
  [5_000, 1_000],
  [10_000, 2_000],
  [20_000, 5_000],
  [50_000, 10_000],
  [100_000, 20_000],
  [200_000, 50_000],
  [500_000, 100_000],
  [1_000_000, 200_000],
];

function ceilingFor(
  bundle: VisualizationBundle,
  visible: number[],
): [number, number] {
  let needed = bundle.min_separation_m * 3;
  for (const v of bundle.variants) {
    let low = Infinity;
    for (const i of visible) low = Math.min(low, v.min_to_any_m[i]);
    if (Number.isFinite(low)) needed = Math.max(needed, low * 2);
  }
  return (
    CEILINGS_M.find(([c]) => c >= needed) ?? CEILINGS_M[CEILINGS_M.length - 1]
  );
}

function km(metres: number): string {
  return metres >= 1000
    ? `${(metres / 1000).toLocaleString("en-US", { maximumFractionDigits: 1 })} km`
    : `${metres.toFixed(0)} m`;
}

/**
 * What the chart is actually showing, said before the physics.
 *
 * The interesting thing on this screen is not that separation was computed, it
 * is that a burn the search ranked first was thrown out for coming 523 m from
 * something -- and that a different burn holds. That is the whole argument, so
 * it goes in the heading rather than three scrolls down in a table.
 *
 * The verdict is read off the verifier's own `below_floor` flag on each
 * encounter, never re-derived from the plotted series: the chart is allowed to
 * clip, smooth and resample, and a heading that disagreed with the validation
 * would be worse than no heading at all.
 */
/** Quote the floor in whatever unit the breach is in: "523 m ... 1 km" makes
 *  the reader do the conversion the sentence exists to spare them. */
function sameUnitAs(value: number, reference: number) {
  return reference < 1000
    ? `${Math.round(value).toLocaleString("en-US")} m`
    : km(value);
}

function verdict(bundle: VisualizationBundle) {
  const floor = bundle.min_separation_m;
  const burns = bundle.variants.filter((v) => v.kind === "IMPULSE");
  const vetoed = burns.find((v) => v.encounters.some((e) => e.below_floor));
  if (!vetoed) return null;

  const breach = vetoed.encounters
    .filter((e) => e.below_floor)
    .reduce((a, b) => (a.min_separation_m <= b.min_separation_m ? a : b));
  const clear = burns.find(
    (v) => v !== vetoed && !v.encounters.some((e) => e.below_floor),
  );
  return {
    breach_m: breach.min_separation_m,
    floor_m: floor,
    clear_m: clear ? minimum(clear.min_to_any_m).value : null,
  };
}

export function SeparationChart({ bundle, selected, sample, onSeek }: Props) {
  const [zoom, setZoom] = useState(false);
  const call = useMemo(() => verdict(bundle), [bundle]);
  const element = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(1100);
  useEffect(() => {
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(280, entries[0].contentRect.width)),
    );
    observer.observe(element.current!);
    return () => observer.disconnect();
  }, []);
  const variant = currentVariant(bundle, selected)!;
  const min = useMemo(() => minimum(variant.min_to_any_m), [variant]);
  const criticalTime = bundle.t_s[min.index];
  const start = zoom ? Math.max(0, criticalTime - 180) : 0;
  const end = zoom
    ? Math.min(bundle.horizon_s, criticalTime + 180)
    : bundle.horizon_s;
  const left = 62,
    right = width - 18,
    top = 18,
    bottom = 125;
  const x = (t: number) =>
    left + ((t - start) / (end - start)) * (right - left);
  const visible = bundle.t_s
    .map((time, i) => (time >= start && time <= end ? i : -1))
    .filter((i) => i >= 0);
  const [high, step] = ceilingFor(bundle, visible);
  const y = (d: number) =>
    bottom - (Math.min(d, high) / high) * (bottom - top);
  const levels: number[] = [];
  for (let level = step; level <= high; level += step) levels.push(level);
  const narrow = width < 500;

  // Annotate the selected variant only: every dip through the floor, plus its
  // closest approach. Other variants stay as unlabelled context so the frame
  // reads as one story rather than a cloud of captions.
  const callouts = variant.encounters
    .filter(
      (e) =>
        e.tca_s >= start &&
        e.tca_s <= end &&
        (e.below_floor || e.tca_s === criticalTime) &&
        e.min_separation_m < high,
    )
    .sort((a, b) => a.min_separation_m - b.min_separation_m)
    .slice(0, narrow ? 1 : 3);

  const click = (event: React.PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - bounds.left) / bounds.width) * width;
    onSeek(
      Math.max(
        start,
        Math.min(end, start + ((svgX - left) / (right - left)) * (end - start)),
      ),
    );
  };
  return (
    <section className="chart-section" aria-label="Separation evidence">
      <div className="section-heading">
        <div>
          {call ? (
            <>
              <h2>
                Vetoed: the ranked-first burn came {km(call.breach_m)} from
                another object.
              </h2>
              <p className="caption">
                The floor is {sameUnitAs(call.floor_m, call.breach_m)}.{" "}
                {call.clear_m !== null
                  ? `A different burn holds ${km(call.clear_m)} and is what gets proposed.`
                  : "No burn on the grid clears it, which is a real answer."}{" "}
                · Closest object at each instant · clipped at {km(high)}
              </p>
            </>
          ) : (
            <>
              <h2>Distance is the evidence.</h2>
              <p className="caption">
                Closest object at each instant · clipped at {km(high)}
              </p>
            </>
          )}
        </div>
        <button
          className="subtle-button"
          onClick={() => setZoom(!zoom)}
          aria-pressed={zoom}
        >
          {zoom ? <ArrowsOutSimple /> : <MagnifyingGlassPlus />}
          {zoom ? "Full 6 hours" : "Inspect minimum"}
        </button>
      </div>
      <svg
        ref={element}
        className="separation-chart"
        viewBox={`0 0 ${width} 157`}
        role="img"
        aria-label={`Minimum separation ${min.value.toFixed(1)} metres at ${clockText(criticalTime)}. Click to scrub time.`}
        onPointerDown={click}
      >
        <rect
          x={left}
          y={y(bundle.min_separation_m)}
          width={right - left}
          height={bottom - y(bundle.min_separation_m)}
          className="floor-band"
        />
        {levels.map((level) => (
          <g key={level}>
            <line
              x1={left}
              x2={right}
              y1={y(level)}
              y2={y(level)}
              className="chart-grid"
            />
            <text x={left - 10} y={y(level) + 4} textAnchor="end">
              {level === high ? `≥ ${km(level)}` : km(level)}
            </text>
          </g>
        ))}
        <text x={left - 10} y={bottom + 4} textAnchor="end">
          0
        </text>
        <line
          x1={left}
          x2={right}
          y1={y(bundle.min_separation_m)}
          y2={y(bundle.min_separation_m)}
          className="floor-line"
        />
        <text
          x={right - 4}
          y={y(bundle.min_separation_m) + 11}
          textAnchor="end"
          className="floor-label"
        >
          {bundle.min_separation_m.toLocaleString()} m clearance floor
        </text>
        {[...bundle.variants]
          .sort(
            (a, b) =>
              Number(a.candidate_id === selected) -
              Number(b.candidate_id === selected),
          )
          .map((v) => {
            const points = visible
              .map(
                (i) =>
                  `${x(bundle.t_s[i]).toFixed(2)},${y(v.min_to_any_m[i]).toFixed(2)}`,
              )
              .join(" ");
            return (
              <polyline
                key={v.candidate_id}
                points={points}
                fill="none"
                className={`chart-trace ${v.kind === "NO_BURN" ? "baseline" : v.encounters.some((e) => e.below_floor) ? "rejected" : "clear"} ${v.candidate_id === selected ? "active" : ""}`}
              />
            );
          })}
        {bundle.t_s[sample] >= start && bundle.t_s[sample] <= end && (
          <g>
            <line
              x1={x(bundle.t_s[sample])}
              x2={x(bundle.t_s[sample])}
              y1={top}
              y2={bottom}
              className="cursor-line"
            />
            <circle
              cx={x(bundle.t_s[sample])}
              cy={y(variant.min_to_any_m[sample])}
              r="4"
              className="cursor-dot"
            />
          </g>
        )}
        {callouts.map((e, i) => {
          const cx = x(e.tca_s);
          const cy = y(e.min_separation_m);
          // Alternate label sides near the frame edges so text stays inside.
          const anchor =
            cx > right - 120 ? "end" : cx < left + 120 ? "start" : "middle";
          const dx = anchor === "end" ? -8 : anchor === "start" ? 8 : 0;
          return (
            <g
              key={`${e.object_id}-${e.tca_s}`}
              className={`callout ${e.below_floor ? "violation" : ""}`}
            >
              <line x1={cx} x2={cx} y1={cy - 6} y2={cy - 22 - i * 12} />
              <circle cx={cx} cy={cy} r="4" />
              <text x={cx + dx} y={cy - 26 - i * 12} textAnchor={anchor}>
                {e.object_id} · {km(e.min_separation_m)} · T+
                {clockText(e.tca_s).slice(0, 5)}
              </text>
            </g>
          );
        })}
        {(narrow ? [0, 2, 4, 6] : [0, 1, 2, 3, 4, 5, 6]).map((i) => {
          const time = start + ((end - start) * i) / 6;
          return (
            <text key={i} x={x(time)} y={151} textAnchor="middle">
              {zoom ? clockText(time) : `${i}h`}
            </text>
          );
        })}
      </svg>
      <div className="chart-legend">
        <span>
          <i className="swatch baseline" />
          Current orbit
        </span>
        <span>
          <i className="swatch rejected" />
          Rejected burn
        </span>
        <span>
          <i className="swatch clear" />
          Clear alternative
        </span>
        <button
          onClick={() =>
            onSeek(bundle.t_s[nearestSample(bundle.t_s, criticalTime)])
          }
        >
          Jump to minimum ↗
        </button>
      </div>
    </section>
  );
}
