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

export function SeparationChart({ bundle, selected, sample, onSeek }: Props) {
  const [zoom, setZoom] = useState(false);
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
    top = 15,
    bottom = 125;
  const x = (t: number) =>
    left + ((t - start) / (end - start)) * (right - left);
  const low = Math.min(100, Math.max(1, min.value / 2));
  const visible = bundle.t_s
    .map((time, i) => (time >= start && time <= end ? i : -1))
    .filter((i) => i >= 0);
  let high = bundle.min_separation_m * 3;
  for (const v of bundle.variants)
    for (const i of visible) high = Math.max(high, v.min_to_any_m[i]);
  high = 10 ** Math.ceil(Math.log10(high));
  const y = (d: number) =>
    bottom -
    ((Math.log10(Math.max(d, low)) - Math.log10(low)) /
      (Math.log10(high) - Math.log10(low))) *
      (bottom - top);
  const levels = [];
  for (let value = 10 ** Math.ceil(Math.log10(low)); value <= high; value *= 10)
    levels.push(value);
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
          <h2>Distance is the evidence.</h2>
          <p className="caption">
            Closest object at each instant · logarithmic distance scale
          </p>
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
              {level / 1000} km
            </text>
          </g>
        ))}
        <line
          x1={left}
          x2={right}
          y1={y(bundle.min_separation_m)}
          y2={y(bundle.min_separation_m)}
          className="floor-line"
        />
        <text
          x={right - 4}
          y={y(bundle.min_separation_m) - 7}
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
        <circle
          cx={x(criticalTime)}
          cy={y(min.value)}
          r="4"
          className="minimum-dot"
        />
        {(width < 500 ? [0, 2, 4, 6] : [0, 1, 2, 3, 4, 5, 6]).map((i) => {
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
