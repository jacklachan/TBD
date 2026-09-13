import { useEffect, useState } from "react";
import { api } from "../api";
import type { TrackedConjunction, TrackingScreen } from "../contracts";

/** "2026-09-16T02:02:50.433+00:00" -> "16 Sep 02:02:50 UTC" */
export function utcText(iso: string) {
  const date = new Date(iso);
  const month = date.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  return `${date.getUTCDate()} ${month} ${date.toISOString().slice(11, 19)} UTC`;
}

export function missText(km: number) {
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(2)} km`;
}

export function TrackingPanel({
  onAssess,
}: {
  onAssess?: (conjunction: TrackedConjunction) => void;
}) {
  const [screen, setScreen] = useState<TrackingScreen | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api
      .trackingScreen()
      .then((result) => live && setScreen(result))
      .catch(
        (reason) =>
          live &&
          setError(
            reason instanceof Error ? reason.message : "The screen could not be loaded.",
          ),
      );
    return () => {
      live = false;
    };
  }, []);

  if (error) return <p className="exchange-error">{error}</p>;
  if (!screen)
    return (
      <div className="loading-card glass">
        <span className="loading-orbit" />
        <p>
          Screening every Iridium NEXT satellite against every catalogued
          fragment with SGP4. The first load on a fresh server takes about
          fifteen seconds.
        </p>
      </div>
    );

  const constellation = screen.catalog.groups.find((g) => g.role === "PROTECTED");
  const retrieved = utcText(screen.catalog.retrieved_at_utc);
  return (
    <>
      <p className="dialog-intro">
        {screen.catalog.protected_count} {constellation?.label ?? "protected"}{" "}
        satellites — a communications network — screened against{" "}
        {screen.catalog.debris_count.toLocaleString()} real catalogued
        fragments over {screen.window.hours} hours from the {retrieved}{" "}
        element-set snapshot. SGP4, one-minute screen, exact refinement of
        every pass under {screen.report_threshold_km} km.
      </p>

      <div className="evidence-summary">
        <div>
          <span>Pairs screened</span>
          <strong>{screen.pairs_screened.toLocaleString()}</strong>
        </div>
        <div>
          <span>Passes under {screen.report_threshold_km} km</span>
          <strong>{screen.conjunction_count.toLocaleString()}</strong>
        </div>
        <div>
          <span>Closest</span>
          <strong>
            {screen.conjunctions[0] ? missText(screen.conjunctions[0].miss_km) : "—"}
          </strong>
        </div>
      </div>

      <h3>Where the fragments come from</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Source event</th>
              <th>Fragments tracked</th>
              <th>Passes under {screen.report_threshold_km} km</th>
            </tr>
          </thead>
          <tbody>
            {screen.catalog.groups
              .filter((g) => g.role === "DEBRIS")
              .map((g) => (
                <tr key={g.group}>
                  <td>{g.label}</td>
                  <td>{g.object_count.toLocaleString()}</td>
                  <td>{(screen.by_event[g.label] ?? 0).toLocaleString()}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {!!screen.cross_check.length && (
        <>
          <h3>
            Checked against CelesTrak SOCRATES{" "}
            <span className="caption">published independently, before this snapshot</span>
          </h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Published</th>
                  <th>Recomputed here</th>
                  <th>Time difference</th>
                </tr>
              </thead>
              <tbody>
                {screen.cross_check.map((c) => (
                  <tr key={`${c.object_1.norad_id}-${c.object_2.norad_id}`}>
                    <td>
                      {c.object_1.name} × {c.object_2.name}
                      <small>
                        {c.object_1.norad_id} / {c.object_2.norad_id}
                      </small>
                    </td>
                    <td>
                      {missText(c.published_miss_km)}
                      <small>{utcText(c.published_tca_utc)}</small>
                    </td>
                    <td>
                      {c.status === "RECOMPUTED" && c.our_miss_km !== undefined ? (
                        <>
                          {missText(c.our_miss_km)}
                          <small>{utcText(c.our_tca_utc!)}</small>
                        </>
                      ) : (
                        c.status.replaceAll("_", " ").toLowerCase()
                      )}
                    </td>
                    <td>
                      {c.tca_difference_s !== undefined
                        ? `${Math.abs(c.tca_difference_s).toFixed(1)} s`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="caption">
            Same pass, found independently from newer element sets. The timing
            agrees to a fraction of a second; the miss distance differs because
            the two element sets differ, which is the uncertainty any screen
            built on public data carries.
          </p>
        </>
      )}

      <h3>Closest passes in the window</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Satellite</th>
              <th>Fragment</th>
              <th>Closest approach</th>
              <th>Miss</th>
              <th>Relative speed</th>
              {onAssess && <th />}
            </tr>
          </thead>
          <tbody>
            {screen.conjunctions.map((c) => (
              <tr key={`${c.protected.norad_id}-${c.debris.norad_id}-${c.tca_utc}`}>
                <td>
                  {c.protected.name}
                  <small>NORAD {c.protected.norad_id}</small>
                </td>
                <td>
                  {c.debris.name} {c.debris.norad_id}
                  <small>{c.debris.event}</small>
                </td>
                <td>
                  {utcText(c.tca_utc)}
                  <small>
                    elements {c.element_age_days.protected} / {c.element_age_days.debris} days old
                  </small>
                </td>
                <td>
                  <span className={`status ${c.miss_km < 1 ? "danger" : "watch"}`}>
                    <i />
                    {missText(c.miss_km)}
                  </span>
                </td>
                <td>{c.relative_speed_kms.toFixed(1)} km/s</td>
                {onAssess && (
                  <td>
                    <button className="subtle-button" onClick={() => onAssess(c)}>
                      Assess avoidance
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">{screen.note}</p>
      <p className="caption">
        Computed in {screen.elapsed_s} s from committed data. Nothing is
        fetched at runtime.
      </p>
    </>
  );
}
