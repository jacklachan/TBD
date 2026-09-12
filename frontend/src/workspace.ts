/** Display operations only. All positions, minima and maneuver results come from the API. */
import type { Analysis, OptionRow, VisualizationBundle } from "./contracts";

export function nearestSample(times: number[], time: number): number {
  let low = 0,
    high = times.length - 1;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (times[middle] < time) low = middle + 1;
    else high = middle;
  }
  return low > 0 &&
    Math.abs(times[low - 1] - time) < Math.abs(times[low] - time)
    ? low - 1
    : low;
}

export function minimum(values: number[]) {
  let index = 0;
  for (let i = 1; i < values.length; i++)
    if (values[i] < values[index]) index = i;
  return { value: values[index], index };
}

export function currentVariant(
  bundle: VisualizationBundle | null,
  selected: string,
) {
  return bundle?.variants.find((v) => v.candidate_id === selected);
}

export function comparisonIds(analysis: Analysis): string[] {
  const baseline = analysis.options.find(
    (o) => o.kind === "NO_BURN",
  )?.candidate_id;
  const veto = [...analysis.options]
    .sort((a, b) => (a.rank ?? 100) - (b.rank ?? 100))
    .find(
      (o) => o.primary_qualified && o.validation?.status === "BLOCK",
    )?.candidate_id;
  return [
    ...new Set(
      [baseline, veto, analysis.recommended_id].filter((id): id is string =>
        Boolean(id),
      ),
    ),
  ];
}

export function clockText(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

export function distance(metres: number | undefined): [string, string] {
  if (metres === undefined || !Number.isFinite(metres)) return ["—", "m"];
  return metres < 1000
    ? [metres.toFixed(1), "m"]
    : [
        (metres / 1000).toLocaleString("en-US", {
          maximumFractionDigits: metres >= 100_000 ? 1 : 3,
        }),
        "km",
      ];
}

export function optionName(
  option: Pick<OptionRow, "kind" | "burn_t_s" | "direction">,
) {
  return option.kind === "NO_BURN"
    ? "Continue current orbit"
    : `${option.direction === "RETROGRADE" ? "Retrograde" : "Prograde"} · T+${Math.round((option.burn_t_s ?? 0) / 60)} min`;
}

export function optionStatus(option: OptionRow): {
  label: string;
  tone: string;
} {
  if (option.validation?.status === "PASS")
    return { label: "Verified clear", tone: "good" };
  if (option.validation?.status === "ERROR")
    return { label: "Verification error", tone: "danger" };
  if (option.validation?.status === "BLOCK")
    return { label: "Verifier rejected", tone: "danger" };
  if (option.reason_codes.includes("OVER_BUDGET"))
    return { label: "Over budget", tone: "muted" };
  if (option.reason_codes.includes("BURN_IN_BLOCKED_WINDOW"))
    return { label: "Window blocked", tone: "muted" };
  return { label: "Below clearance", tone: "watch" };
}

export function download(
  name: string,
  content: string,
  mime = "application/json",
) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
