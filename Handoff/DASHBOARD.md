# Satellite Demo — chart, moving 3D scene and operator workflow

Current specification. Supersedes [reference/DASHBOARD.md](reference/DASHBOARD.md), which recommended cutting 3D. **3D is required.** The chart still ships first, and 3D never blocks a physics gate.

Written for a judge with no orbital mechanics background who will look at the screen for twenty seconds before deciding whether to engage.

This is a content and behaviour spec. Component ownership and sequence are in [handoffs/B_PRODUCT.md](handoffs/B_PRODUCT.md); field definitions are in [CONTRACTS.md](CONTRACTS.md).

## Division of labour between the two views

**The chart is the evidence. The 3D scene is the explanation.**

A distance-over-time line is legible to everyone and is what a verdict rests on. A 3D scene makes the situation *understandable* — where things are, how fast, what the encounter looks like — which a chart cannot do.

The failure mode to design against: **two orbit paths that cross on screen may never be at the crossing point at the same moment.** Nobody eyeballs proximity from orbit geometry correctly. So the 3D scene must never be the thing that answers "are they close?"

The fix is structural, not cosmetic. Render both objects as markers on **one shared clock**, and draw a **line between them carrying the computed separation as a label**. What the viewer sees is then literally what was calculated. Add a scrubber so the encounter can be inspected directly.

## The rule that governs the whole frontend

**The backend is the only source of motion and distance.** The frontend renders `VisualizationBundle` and computes no physics of any kind.

Prohibited without exception:

- Any frontend trajectory or separation calculation
- CSS or spring animation driving orbital motion
- A decorative evasive swerve absent from the returned positions
- Stretching pair separation to dramatize avoidance
- Rescaling one object's distance independently of the others

Model geometry **must** be enlarged — a real satellite is sub-pixel at true scale. Label the exaggeration on screen and exclude enlarged geometry from the centre-to-centre separation behind any displayed distance.

## 1. Hero chart — "Closest approach to any tracked object"

One chart, large, above the fold. This carries the verdict.

- **X:** hours from scenario start, 0 → 6. Not seconds, not epochs.
- **Y:** kilometres, linear, clipped with the ceiling explicitly labelled. Everything that matters lives between 0 and about 10 km; a log axis shows more and communicates less.
- **Danger band:** shaded red from 0 to `min_separation_m`, labelled as the clearance floor. Most important element on the page.
- **Series:** `min_to_any_m` — closest approach to *any* object at each sample. Correct safety metric and the one a non-expert already understands. Per-pair breakdown behind an expand.

Three variants, requested from `GET /cases/{id}/visualization` (maximum three; never fetch all 25):

| Variant | Style | What a judge sees |
|---|---|---|
| Baseline | grey, dashed | dips through the floor near the primary encounter |
| Rejected | amber | clears the primary, then dips again later against the second object |
| Recommended | blue, solid | stays above the floor across the horizon |

Annotate each dip with the responsible object and the time, taken from the bundle's `events`. The amber line is the signature: "the obvious fix creates a new problem," understood in about two seconds with no narration.

Distances and times are generator targets until numerically reproduced. Render what the backend returns; never hardcode an expected value into a label.

## 2. 3D scene — required

- Earth, the satellite, and two debris markers, positioned from `positions_m`.
- Procedural satellite body and panels are sufficient. A licensed GLB is optional and later, with its attribution committed alongside.
- **One `SimulationClock`.** Chart cursor, every marker, the distance line and all labels read the same selected `t_s`. There is exactly one clock in the application.
- **Distance line** between the selected pair, labelled with that sample's separation.
- **Scrubber** with playback and jump-to-exact-encounter buttons.
- **Approach camera:** a button that frames the encounter under inspection.

**Sampling rule.** The bundle ships a shared `t_s` array already containing one-second samples, both horizon boundaries, every burn timestamp, and the exact refined encounter times. Playback and scrubbing **select a supplied sample**; encounter buttons select the included refined time. An interpolated value must never be displayed as an exact minimum. If smoothing is added later: label it during motion, interpolate all objects consistently, snap to authoritative samples for inspection, and never let an interpolated point change a verdict.

**Camera rule.** Global and close-approach views each hold one consistent spatial scale within the view. Move the camera or the coordinate origin to inspect an encounter — do not stretch the separation.

**Loading rule.** 3D assets must never hold up the numerical result. The answer appears first; the scene fills in.

## 3. Status chip

One chip, large, colour **and** text — never colour alone:

- 🟢 **SAFE** — no action needed
- 🟠 **ACTION NEEDED** — close approach predicted, options available
- 🔴 **NO SAFE OPTION** — nothing in the searched set clears every constraint

The red state is a legitimate result, not an error screen.

## 4. Options table

- **Columns:** Option · When · Fuel · Closest approach · Verdict
- **Fuel as a filled bar against the budget**, not a number. `0.10 m/s` means nothing to a judge; a bar two-fifths full means everything. Numeric Δv in a tooltip.
- **The rejection reason belongs in the table**, in colour. It is the most interesting fact on the page and must not be buried in the trace.
- Policy-excluded options stay visible with their reason codes. Do not drop rows.
- The displayed option count must equal the count actually evaluated — 25 initially, 33 after one `widen_search`. Never state a count the backend did not report.

Δv is a simulated fuel proxy. No kilograms, no thruster capability, no lifetime claims anywhere in the UI.

## 5. Constraint input

Plain text box, above the fold, never inside a settings panel. This is the interaction a judge should physically touch.

Flow: judge types → `POST /policy-preview` → render the returned `PolicyDiff` as a **before/after pair** → explicit confirm → `POST /policy-confirm` → watch it replan.

- A `NEEDS_CLARIFICATION` diff renders as a question, not an error.
- On confirmation, the previous proposal must **visibly** go stale. An approved badge that silently persists is a correctness bug.

## 6. Agent trace

Where the agentic criterion is scored, so it must be readable rather than a JSON dump.

One plain-language line per `CaseEvent` with its `duration_ms`, expandable to the real tool call and result. Non-experts read the summaries; technical judges expand. Show the timings — they demonstrate the run is live.

Show actual tool actions, results, evidence and short decision summaries. Do not display or store hidden model reasoning.

## 7. Context panel

Up to ten rows from the committed SOCRATES snapshot, with the snapshot date visible and clear visual separation from the simulation. Display-only, from disk, no runtime fetch. It answers "is this a real problem?" before a judge has to ask.

## 8. Provenance line

Small, always visible, populated from `seed_provenance.json` — never a literal typed into the frontend:

> Orbit seeded from NORAD `<parsed id>`, epoch `<parsed epoch>` (real) · Conjunction geometry synthetic · Two-body model

See [DATA.md](DATA.md). A data sheet reads as rigour; a red SYNTHETIC banner reads as an apology.

## 9. Vocabulary

| Never show | Show instead |
|---|---|
| Conjunction | Close approach |
| Minimum separation / miss distance | Closest approach |
| Delta-v / Δv | Fuel used (bar); `Δv` in tooltip |
| Manoeuvre candidate | Option |
| Infeasible | Not allowed by your limits |
| `NO_PRIMARY_QUALIFIED_OPTION` | **No safe option found** (technical phrasing small, underneath) |
| Epoch / TCA | Time, in hours from start |
| Prograde / retrograde | Speed up / slow down |
| Secondary conjunction | Creates a new close approach |

Keep every technical term available on hover or expand. Lead with the plain word.

## 10. Do not put on screen

- Orbit ellipses offered as proximity evidence
- TLE strings, orbital elements, Julian dates or frame identifiers in the main view
- Raw JSON anywhere a judge lands first
- Metres where kilometres read better
- **Collision probability, or anything implying it.** It is not computed. A percentage invites the one question this product cannot answer.

## 11. Layout

Above the fold: status chip · hero chart · constraint box · options table.

Below: 3D scene · agent trace · context panel · approve / reset / export · provenance line.

Place the 3D scene where a judge reaches it immediately after the verdict, and keep the chart visible while narrating it.

## 12. Required states

Every panel needs loading, empty, error and infeasible states. Specifically:

- Stale-response protection — a late reply from a superseded run must never overwrite newer state. Test by firing two plans in quick succession.
- Approve disabled unless validation is `PASS` and the reviewer verdict is `ALLOW`.
- Reset produces a new case and retains history.
- Reload restores the case.

## The twenty-second test

Sit someone who knows nothing about satellites in front of it, say nothing, and time them. They should be able to tell you:

1. Something is going to come dangerously close
2. There are options, and one is recommended
3. One option was rejected because it caused a *new* problem

If they cannot get all three from the screen alone, fix the chart — not the explanation.
