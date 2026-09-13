import { useEffect, useRef, useState } from "react";
import { api, waitForRun } from "../api";
import type {
  AvoidanceAssessment,
  AvoidanceOption,
  TrackedConjunction,
  TrackingScreen,
  TriageResult,
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

/** "6 min", "2.4 h", "3 days" -- whichever reads at the size the number is. */
function spanText(hours: number) {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${hours.toFixed(1)} h`;
  return `${(hours / 24).toFixed(1)} days`;
}

// What is true about the burn ladder, which is not the same as how urgent the
// pass is: every slot can still be open while the widest one expires in six
// minutes. Urgency is the deadline, and it gets its own signal below.
const POSTURE_LABEL: Record<string, string> = {
  ACTIONABLE: "All burns open",
  NARROWING: "Options closing",
  TOO_LATE: "Past last burn",
};

/** Red inside the hour. Colouring the posture instead would contradict the
 *  ordering -- a pass with every slot open can still be the next one due. */
function deadlineTone(hours: number) {
  return hours < 1 ? "danger" : "watch";
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

const TRIAGE_LABEL = {
  NEEDS_BURN: ["Needs a burn", "danger"],
  NO_OPTION: ["No option clears it", "watch"],
  CLEAR: ["Clear", "good"],
} as const;

function TriageAgent({ modelAccess }: { modelAccess: boolean }) {
  const [running, setRunning] = useState("");
  const [result, setResult] = useState<TriageResult | null>(null);
  const [error, setError] = useState("");

  const start = async () => {
    setError("");
    setResult(null);
    setRunning("Starting the triage agent");
    try {
      const run = await api.startTriage();
      const finished = await waitForRun(run.run_id, {
        onStep: (step, done) => setRunning(`${done}. ${step}`),
      });
      if (finished.status === "FAILED") throw new Error(finished.error);
      setResult(finished.result as unknown as TriageResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The triage agent failed.");
    } finally {
      setRunning("");
    }
  };

  return (
    <section className="triage-agent">
      <div className="section-heading">
        <h3>Triage agent</h3>
        <button className="primary-button" onClick={start} disabled={!modelAccess || !!running}>
          {running ? "Agent running…" : result ? "Run again" : "Run triage agent"}
        </button>
      </div>
      <p className="caption">
        A model works through this screen with three tools — summary, list
        passes, assess a pass — and briefs the operator. It recommends; nothing
        here can execute a burn. The table below the brief is built from the
        assessment tool&rsquo;s results, not from the model&rsquo;s prose.
        {!modelAccess && " Set HF_TOKEN on the server to enable it."}
      </p>
      {running && (
        <div className="loading-card glass">
          <span className="loading-orbit" />
          <p>{running}</p>
        </div>
      )}
      {error && <p className="exchange-error">{error}</p>}
      {result && (
        <>
          {result.brief && <p className="triage-brief">{result.brief}</p>}
          <p className="caption">
            {result.status === "BRIEF_READY" ? "Brief ready" : `Unresolved: ${result.unresolved_reason}`}{" "}
            · {result.assessments} passes assessed · {result.model_calls} model calls ·{" "}
            {result.elapsed_s.toFixed(1)} s
          </p>
          {!!result.flagged_numbers.length && (
            <p className="warning-text">
              Figures in the brief not found in any tool result:{" "}
              {result.flagged_numbers.join(", ")}. Use the table.
            </p>
          )}
          {!!result.triage.length && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Satellite</th>
                    <th>Pass</th>
                    <th>Miss</th>
                    <th>Triage</th>
                    <th>Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {result.triage.map((item) => {
                    const [text, tone] = TRIAGE_LABEL[item.status];
                    return (
                      <tr key={item.pass_id}>
                        <td>
                          {item.satellite}
                          <small>{item.pass_id}</small>
                        </td>
                        <td>
                          {utcText(item.tca_utc + "Z")}
                          <small>fragment {item.fragment_norad_id} · {item.event}</small>
                        </td>
                        <td>{missText(item.miss_km)}</td>
                        <td>
                          <span className={`status ${tone}`}>
                            <i />
                            {text}
                          </span>
                        </td>
                        <td>
                          {item.recommendation ?? "—"}
                          {item.estimated_miss_km !== null && item.status === "NEEDS_BURN" && (
                            <small>
                              estimated {missText(item.estimated_miss_km)}
                              {item.rescreen_closest_km !== null &&
                                ` · re-screen closest ${missText(item.rescreen_closest_km)}`}
                            </small>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <details className="triage-trace">
            <summary>Agent trace · {result.events.length} steps</summary>
            <ol className="event-list">
              {result.events.map((event) => (
                <li key={event.sequence}>
                  <span>{event.event_type.replaceAll("_", " ")}</span>
                  <p>{event.summary}</p>
                  <small>{event.duration_ms.toFixed(0)} ms</small>
                </li>
              ))}
            </ol>
          </details>
        </>
      )}
    </section>
  );
}

export function TrackingPanel({ modelAccess = false }: { modelAccess?: boolean }) {
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
  // The head of each ordering. They are usually different rows, which is the
  // point the intro paragraph makes; when they are not, it still reads true.
  const first = screen.triage.queue[0];
  const closest = screen.conjunctions[0];
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
          <span>Decide first</span>
          <strong>
            {first?.triage.decide_in_hours != null
              ? spanText(first.triage.decide_in_hours)
              : "—"}
          </strong>
        </div>
      </div>

      {first && (
        <p className="dialog-intro">
          Sorted by miss distance the top of this screen is{" "}
          <strong>{missText(closest!.miss_km)}</strong>, and it is{" "}
          {spanText(closest!.triage.lead_hours)} away — there is no hurry. The
          pass that actually needs an answer is{" "}
          <strong>{first.protected.name}</strong> against{" "}
          {first.debris.name} at <strong>{missText(first.miss_km)}</strong>:{" "}
          {spanText(first.triage.lead_hours)} to closest approach, but only{" "}
          <strong>{spanText(first.triage.decide_in_hours!)}</strong> before the
          last burn that can still be placed. Closest is not the same as
          soonest, and neither is the same as most urgent.
        </p>
      )}

      <h3>
        Decide first{" "}
        <span className="caption">
          {screen.triage.queue_length.toLocaleString()} passes under{" "}
          {screen.triage.attention_km} km, ordered by when the decision is due
        </span>
      </h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Satellite</th>
              <th>Fragment</th>
              <th>Decide by</th>
              <th>Miss</th>
              <th>Closest approach</th>
              <th>Burns left</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {screen.triage.queue.map((c) => (
              <tr key={`q-${c.protected.norad_id}-${c.debris.norad_id}-${c.tca_utc}`}>
                <td>
                  {c.protected.name}
                  <small>NORAD {c.protected.norad_id}</small>
                </td>
                <td>
                  {c.debris.name} {c.debris.norad_id}
                  <small>{c.debris.event}</small>
                </td>
                <td>
                  {c.triage.decide_in_hours != null ? (
                    <>
                      <span className={`status ${deadlineTone(c.triage.decide_in_hours)}`}>
                        <i />
                        {spanText(c.triage.decide_in_hours)}
                      </span>
                      <small>{utcText(c.triage.decide_by_utc!)}</small>
                    </>
                  ) : (
                    <small>{POSTURE_LABEL[c.triage.posture]}</small>
                  )}
                </td>
                <td>{missText(c.miss_km)}</td>
                <td>
                  {spanText(c.triage.lead_hours)}
                  <small>{utcText(c.tca_utc)}</small>
                </td>
                <td>
                  {c.triage.burn_slots_open}/{c.triage.burn_slots_total}
                  <small>{POSTURE_LABEL[c.triage.posture]}</small>
                </td>
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
      <p className="caption">{screen.triage.basis}</p>

      <TriageAgent modelAccess={modelAccess} />

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

      <h3>
        Why the passes that are <em>not</em> listed are not listed{" "}
        <span className="caption">
          the part of a screen nobody checks
        </span>
      </h3>
      <p className="caption">{screen.completeness.claim}</p>
      <div className="evidence-summary">
        <div>
          <span>Capture radius</span>
          <strong>{screen.completeness.capture_radius_km.toFixed(0)} km</strong>
        </div>
        <div>
          <span>Fastest closure allowed for</span>
          <strong>{screen.completeness.speed_bound.applied_kms.toFixed(2)} km/s</strong>
        </div>
        <div>
          <span>Fastest actually seen</span>
          <strong>{screen.completeness.observed_head_on_kms.toFixed(2)} km/s</strong>
        </div>
        <div>
          <span>Refine-list margin used</span>
          <strong>
            {missText(screen.completeness.worst_linear_error_km)} of{" "}
            {screen.completeness.linear_margin_km} km
          </strong>
        </div>
      </div>
      <p className="caption">
        {screen.completeness.status === "COMPLETE" ? (
          <>
            The capture radius is sized from the element sets in hand — perigee
            speed of the fastest satellite plus the fastest fragment,{" "}
            {screen.completeness.speed_bound.derived_kms.toFixed(2)} km/s — not
            from a constant, so a faster catalogue widens it rather than
            dropping passes between samples. Nothing in this run closed faster
            than that, with{" "}
            {screen.completeness.speed_headroom_kms.toFixed(2)} km/s to spare
            across {screen.completeness.candidate_pairs_refined.toLocaleString()}{" "}
            refined candidates.
          </>
        ) : (
          <>
            This run could not substantiate that claim:{" "}
            {screen.completeness.shortfall?.join("; ")}. Treat the list as
            partial.
          </>
        )}
      </p>

      <h3>
        Closest passes in the window{" "}
        <span className="caption">the leaderboard, not the work queue</span>
      </h3>
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
