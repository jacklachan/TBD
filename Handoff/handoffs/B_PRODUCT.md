# Builder B — product, chart and moving 3D scene

**Current status, 12 September 2026:** the requested React/Three.js workspace is implemented. Read [FRONTEND.md](../FRONTEND.md) for actual files, contracts, commands, tests, screenshots and remaining limits. This file preserves the earlier ownership plan below; planned names such as Workbench.tsx were realized as App.tsx/useWorkspace.ts. Do not recreate the application from this older checklist.

## You own

```text
frontend/src/config.ts                     Temporary display name
frontend/src/contracts.ts                  Transport types, aligned with models.py (shared with C)
frontend/src/api.ts                        Typed client, stale-response protection (shared with C)
frontend/src/Workbench.tsx                 Case state and composition
frontend/src/components/
  SeparationChart.tsx                      Evidence chart and encounter annotations
  OptionsTable.tsx                         Provisional, verified and rejected options
  ConstraintInput.tsx                      Sentence, policy preview, confirmation
  AgentTrace.tsx                           Real events and timings
  ContextPanel.tsx                         Dated SOCRATES snapshot
  DecisionActions.tsx                      Approve, reset, export
frontend/src/scene/
  OrbitScene.tsx                           Earth and moving objects
  SatelliteModel.tsx                       Procedural body, panels, optional GLB
  SimulationClock.ts                       Shared selected time and playback
  DistanceLine.tsx                         Selected-pair separation at one shared time
  TimeScrubber.tsx                         Playback and exact-encounter jumps
frontend/public/models/                    Optional licensed GLB plus attribution
```

You share `backend/domain/models.py` with A and C. You own no backend file.

## The one rule that governs everything you build

**The backend is the only source of motion and distance.**

You render `VisualizationBundle`. You do not propagate, interpolate a verdict, compute a separation, or ease a marker along a path you invented. If a number appears on screen, it came from a typed backend field.

Concretely, all of these are prohibited:

- A separate frontend physics calculation of any kind
- CSS or spring animation driving orbital motion
- A decorative "evasive swerve" that is not in the returned positions
- Stretching pair separation to make avoidance look bigger
- Rescaling one object's distance independently of the others

Model geometry **may** be enlarged so a satellite is visible — that is required, since true scale is sub-pixel. Label it on screen, and exclude enlarged geometry from the centre-to-centre separation used for any displayed distance.

## Hour 0–1 — shared contracts

- [ ] Sit with A and C, walk CONTRACTS.md, resolve field disagreements before anyone writes logic.
- [ ] Co-write `backend/domain/models.py`, then mirror it in `contracts.ts`. One field name per concept. Do not invent frontend-only physics types.
- [ ] Agree the fixture shape with A so your first chart data is contract-valid from the start.

## Hour 1–3 — chart on marked fixtures

Build the chart before the renderer. The chart is the evidence; 3D is the explanation.

- [ ] `SeparationChart.tsx` on explicitly marked fixture data. A visible `FIXTURE DATA` badge that you remove when real results land — not a comment.
- [ ] X axis hours from scenario start, Y axis kilometres, linear, clipped with the ceiling labelled. Red band 0 → 1 km labelled as the clearance floor.
- [ ] Plot `min_to_any_m` — closest approach to **any** object — as the headline series. Per-pair breakdown behind an expand.
- [ ] Three variants: baseline, rejected, recommended. Annotate each dip with the object responsible and the time.

Fixture data is acceptable during integration only while marked, and it is excluded from any claimed live run.

## Hour 3–5 — 3D scene and shared clock

- [ ] `SimulationClock.ts` holds one selected `t_s`. Chart cursor, every marker, the distance line and all labels read from it. There is exactly one clock.
- [ ] `OrbitScene.tsx`: Earth plus three moving objects at positions taken from the bundle.
- [ ] `SatelliteModel.tsx`: procedural body and panels. A licensed GLB is optional and later; if you add one, commit its attribution alongside it.
- [ ] `DistanceLine.tsx`: a line between the selected pair with the current separation printed on it. This is what makes 3D honest — the line *is* the computed distance, so what a judge sees is what was calculated.
- [ ] `TimeScrubber.tsx`: playback plus jump-to-exact-encounter buttons.

**Sampling rule.** The bundle ships a shared `t_s` array that already includes one-second samples, both horizon boundaries, every burn timestamp, and the exact refined encounter times. Default playback and scrubbing **select a supplied sample**. Encounter buttons select the included refined time. Never display an interpolated value as an exact minimum. If you add smoothing later: label it during motion, interpolate every object consistently, snap to authoritative samples for inspection, and never let an interpolated point change a verdict.

**Camera rule.** Global and close-approach views each keep one consistent spatial scale within the view. Move the camera or the coordinate origin to inspect an encounter. Do not stretch the separation.

## Hour 5–7 — real data

- [ ] Swap fixtures for real `VisualizationBundle` responses. Remove the fixture badge.
- [ ] Request only the variants you display — baseline, rejected, recommended. Never fetch all 25.
- [ ] Verify chart and 3D agree: at a given `t_s`, the chart value and the 3D distance label are the same number.

## Hour 7–11 — the interaction judges touch

A joins you here.

- [ ] `OptionsTable.tsx`: option, when, fuel **as a filled bar against the budget**, closest approach, verdict. Numeric Δv in a tooltip. The rejection reason belongs in the table in colour — it is the most interesting fact on the page.
- [ ] `ConstraintInput.tsx`: plain text box, above the fold, never in a settings panel. Submit → show the returned `PolicyDiff` as a before/after pair → explicit confirm → watch it replan. A `NEEDS_CLARIFICATION` diff renders as a question, not an error.
- [ ] `AgentTrace.tsx`: one plain-language line per event with its `duration_ms`, expandable to the real tool call and result. Non-experts read the summaries; technical judges expand. Show timings — they prove the run is live.
- [ ] Approach camera: a button that frames the encounter under inspection.

## Hour 11–14 — the unglamorous half

This is where demos are actually won or lost.

- [ ] Loading, empty, error and infeasible states for every panel.
- [ ] `NO_PRIMARY_QUALIFIED_OPTION` renders as **"No safe option found"** with the technical phrasing small underneath. This is a legitimate result, not an error screen.
- [ ] Stale-response protection: every response carries a version stamp; a late reply from a superseded run must never overwrite newer state. Test it by firing two plans in quick succession.
- [ ] A stale proposal visibly goes stale when policy changes. The approved badge must not silently persist.
- [ ] `DecisionActions.tsx`: approve, reset, export. Approve disabled unless validation is `PASS` and the reviewer verdict is `ALLOW`.
- [ ] `ContextPanel.tsx`: up to ten SOCRATES rows from disk, with the snapshot date visible and clear separation from the simulation.
- [ ] Provenance line always visible. Phrase it as a data sheet, not a disclaimer.

## Hour 14–16

- [ ] Second machine, clean checkout, fresh browser. Confirm the demo path works with no local state.
- [ ] Confirm chart and 3D agree at every annotated encounter.
- [ ] Confirm 3D asset loading never blocks the numerical result appearing. The answer arrives first; the scene can fill in.

## Freeze at sixteen

Keep basic synchronized 3D. Cut, in this order, if time runs short: custom Blender work, textures, cinematic transitions, decorative effects. Any reduction of required scope goes into STATE.md and the pitch — never silently marked complete.

## What blocks you, and what to do

| Problem | Action |
|---|---|
| Backend not ready at hour 1 | Build on marked fixtures. This is expected and planned for |
| Chart and 3D disagree | One of them is not reading the shared clock, or one is interpolating. The bundle is authoritative; find which component left it |
| 3D is eating your hours | It is allowed to be plain. A procedural box with panels and a correct distance line beats a beautiful scene with wrong motion |
| Latency feels bad | Stream events into the trace as they arrive so something is always moving. Report measured time; do not hide it |
| Tempted to compute something client-side to fill a gap | Ask C for a backend field instead. Every exception to this rule becomes the question you cannot answer |

## Update duties

After each work block, append to this file using [TEMPLATE.md](TEMPLATE.md): changed paths, commands run and their real output, checks that failed or were not run, contract changes, next concrete action.
