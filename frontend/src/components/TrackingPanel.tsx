import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type {
  AvoidanceAssessment,
  AvoidanceOption,
  TrackedConjunction,
  TrackingScreen,
} from "../contracts";

/** "2026-09-16T02:02:50.433+00:00" -> "16 Sep 02:02:50 UTC" */
export function utcText(iso: string) {
  const date = new Date(iso);
  const month = date.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  return `${date.getUTCDate()} ${month} ${date.toISOString().slice(11, 19)} UTC`;
}

export function missText(km: number) {
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(2)} km`;
}

function burnText(option: AvoidanceOption) {
  if (option.direction === null) return "No burn";
  const verb = option.direction === "PROGRADE" ? "speed up" : "slow down";
  return `${option.delta_v_mps.toFixed(2)} m/s ${verb}, ${option.lead_minutes} min before`;
}

function AvoidanceView({
  conjunction,
  onBack,
}: {
  conjunction: TrackedConjunction;
  onBack: () => void;
}) {
  const [result, setResult] = useState<AvoidanceAssessment | null>(null);
  const [error, setError] = useState("");
  const top = useRef<HTMLButtonElement>(null);
  // The dialog keeps its scroll position across the switch from the list, which
  // opened this view half-way down its own options table.
  useEffect(() => {
    top.current?.closest("dialog")?.scrollTo({ top: 0 });
  }, []);
  useEffect(() => {
    let live = true;
    api
      .trackingAssess(
        conjunction.protected.norad_id,
        conjunction.debris.norad_id,
        conjunction.tca_utc,
      )
      .then((r) => live && setResult(r))
      .catch(
        (reason) =>
          live &&
          setError(reason instanceof Error ? reason.message : "Assessment failed."),
      );
    return () => {
      live = false;
    };
  }, [conjunction]);

  const recommended = result?.options.find(
    (o) => o.option_id === result.recommended_option_id,
  );
  const checked = result?.options.filter((o) => o.verdict) ?? [];
  return (
    <>
      <button ref={top} className="subtle-button" onClick={onBack}>
        ← All passes
      </button>
      <h3>
        {conjunction.protected.name} × {conjunction.debris.name}{" "}
        {conjunction.debris.norad_id}
      </h3>
      <p className="dialog-intro">
        {missText(conjunction.miss_km)} at {utcText(conjunction.tca_utc)},{" "}
        {conjunction.relative_speed_kms.toFixed(1)} km/s ·{" "}
        {conjunction.debris.event}
      </p>
      {error && <p className="exchange-error">{error}</p>}
      {!result && !error && (
        <div className="loading-card glass">
          <span className="loading-orbit" />
          <p>
            Estimating every burn, then re-screening the best against every
            catalogued fragment.
          </p>
        </div>
      )}
      {result && (
        <>
          <div className="evidence-summary">
            <div>
              <span>Recommendation</span>
              <strong>
                {recommended ? burnText(recommended) : "Nothing offered clears it"}
              </strong>
            </div>
            <div>
              <span>Estimated miss</span>
              <strong>
                {recommended ? missText(recommended.predicted_miss_km) : "—"}
              </strong>
            </div>
            <div>
              <span>After re-screen</span>
              <strong>
                {recommended?.rescreen_closest_km != null
                  ? `closest ${missText(recommended.rescreen_closest_km)}`
                  : recommended
                    ? "nothing within 5 km"
                    : "—"}
              </strong>
            </div>
          </div>
          <p className="caption">
            The re-screen moves the satellite along its SGP4 path plus the
            displacement of the burn, and checks it against all{" "}
            {result.rescreen.fragments.toLocaleString()} fragments for{" "}
            {result.rescreen.hours_after_burn} hours after the burn. A burn that
            clears this pass but creates another under{" "}
            {missText(result.comfortable_km)} is rejected.
          </p>
          {!!checked.length && (
            <>
              <h3>Checked independently</h3>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Burn</th>
                      <th>Estimated miss</th>
                      <th>Re-screen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {checked.map((o) => (
                      <tr key={o.option_id}>
                        <td>
                          {burnText(o)}
                          <small>{o.option_id}</small>
                        </td>
                        <td>{missText(o.predicted_miss_km)}</td>
                        <td>
                          <span
                            className={`status ${o.verdict === "PASS" ? "good" : "danger"}`}
                          >
                            <i />
                            {o.verdict === "PASS" ? "Clear" : "Rejected"}
                          </span>
                          {o.blocked_by && (
                            <small>
                              {o.blocked_by.debris.name} {o.blocked_by.debris.norad_id}:{" "}
                              {missText(o.blocked_by.miss_km)}
                            </small>
                          )}
                          {o.rescreen_assessed_miss_km !== undefined && (
                            <small>
                              this pass: {missText(o.rescreen_assessed_miss_km)}
                            </small>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <h3>
            Every option{" "}
            <span className="caption">
              burns at half-orbit multiples before the pass · orbit{" "}
              {result.orbital_period_minutes} min
            </span>
          </h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Burn</th>
                  <th>Shift at the pass</th>
                  <th>Estimated miss</th>
                </tr>
              </thead>
              <tbody>
                {result.options.map((o) => (
                  <tr key={o.option_id}>
                    <td>{burnText(o)}</td>
                    <td>{o.displacement_km.toFixed(2)} km</td>
                    <td>
                      <span className={`status ${o.qualifies ? "good" : "watch"}`}>
                        <i />
                        {missText(o.predicted_miss_km)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="caption">{result.note}</p>
        </>
      )}
    </>
  );
}

export function TrackingPanel() {
  const [screen, setScreen] = useState<TrackingScreen | null>(null);
  const [error, setError] = useState("");
  const [assessing, setAssessing] = useState<TrackedConjunction | null>(null);

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
  if (assessing)
    return <AvoidanceView conjunction={assessing} onBack={() => setAssessing(null)} />;

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
              <th />
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
                    elements {c.element_age_days.protected} /{" "}
                    {c.element_age_days.debris} days old
                  </small>
                </td>
                <td>
                  <span className={`status ${c.miss_km < 1 ? "danger" : "watch"}`}>
                    <i />
                    {missText(c.miss_km)}
                  </span>
                </td>
                <td>{c.relative_speed_kms.toFixed(1)} km/s</td>
                <td>
                  <button className="subtle-button" onClick={() => setAssessing(c)}>
                    Assess avoidance
                  </button>
                </td>
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
