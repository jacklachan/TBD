# Strict review and pre-demo fixes — 13 September 2026

Started at `717fdb4` (origin/main). Local checkout `C:/gdg bit and build/TBD`,
Python 3.14, Node 24. Not yet committed or deployed at the time of writing.

## What was checked

- Full backend suite (322 passed, 90.8 s), 7 frontend unit tests, `gen.py --check`,
  `diagnose.py`, `demo_pipeline.py` (0.75 s): all pass at `717fdb4`.
- Every backend module under `backend/core`, `backend/planning`, `backend/agent`,
  `backend/api.py`, `backend/analysis.py`, `backend/security.py`,
  `backend/visualization.py` read in full. Frontend `App.tsx`, `useWorkspace.ts`,
  `api.ts`, `workspace.ts`, `SeparationChart.tsx`, `OrbitalScene.tsx`, `Dialog.tsx`.
- Local app driven in Chromium at desktop and 375 px widths: all five scenarios
  analyse in 0.4–2.8 s; trajectory bundle 922 KB / 2,201 samples in 0.16 s; no
  console errors.
- **Live workflow against the deployed Space** (`scripts/live_api_check.py --base
  https://auenchanters-tbh.hf.space`, operator token from local `.env`):
  initial reviewed plan **4.8 s** (3 model calls); restriction preview 1.8 s;
  stale-proposal rejection, approval idempotency, export and context all pass;
  **replan under the halved budget ended `UNRESOLVED / PROVIDER_ERROR` after
  103.6 s** — `Unusable Hugging Face reply: endpoint ignored
  parallel_tool_calls=false`. The model had spent 36.8 s, 20.9 s and 19.1 s
  thinking on three `design_maneuver` calls, all at T+1 s, before returning two
  calls in one turn. Case `case_bdaccbf963` on the Space holds the trace.

## Holes found and fixed

| # | Hole | Fix |
|---|---|---|
| 1 | Replan could end `UNRESOLVED` with no answer: the grid audit in `api.py` rescued only `NO_CONCLUSION`, and the 90 s deadline sat 4 s above the measured 86.3 s replan | Audit now runs for any `UNRESOLVED` outcome with a search result (`DEADLINE`, `PROVIDER_ERROR`, call limits); `unresolved_reason` recorded in the `grid_audit` event; `PlannerLimits.deadline_s` 90 → 150 (client waits 180) |
| 1b | GLM returns two tool calls in one turn despite `parallel_tool_calls=false`; the adapter raised and the run died | `HuggingFaceProvider._parse` returns every call; `Message.tool_calls` carries a multi-call turn; the planner runs each call in order under the same bounds and answers each, so the replayed history is complete |
| 2 | Chart used a log axis 0.1 km–10,000 km: all three variants overlapped into one line and the 133 m / 523 m dips were dots on the baseline | Linear axis clipped to a nice ceiling (5 km on the signature case), shaded floor band, per-dip callouts on the selected variant naming object, distance and time |
| 4 | Root README still said `GEMINI_API_KEY`, "270 tests", and quoted Gemini-era timings without naming the model; `plan.md` said no code exists | README updated (HF_TOKEN, 322 tests, deployed GLM timings including the 86.3 s miss); historical banner on `plan.md` |
| 5 | HF adapter: 30 s per-request timeout, 2 attempts | 75 s, 3 attempts |
| 6 | `policy-preview` / `policy-confirm` accepted an executed case; `<dialog>` could close in the DOM (Escape without user activation) while React kept it open | Both endpoints return 409 `CASE_EXECUTED`; `Dialog` listens to `close` as well as `cancel` |
| — | Memory briefing listed the same case twice when it had been planned twice | `relevant()` keeps the latest run per case |
| 3 | Wheel or one-finger swipe anywhere over the 3D scene zoomed/rotated the globe instead of scrolling the page | Capture-phase wheel gate on the scene host: plain wheel scrolls, Ctrl/Cmd + wheel (and trackpad pinch) zooms; canvas `touch-action: pan-y`. Verified in Chromium: wheel over the globe scrolled the page 0 → 334 px with the globe unchanged; Ctrl + wheel zoomed |
| — | `pytest` failed 70 API tests with 401 whenever the local `.env` held the Space's operator password | `tests/conftest.py` sets `DESK_ACCESS_TOKEN` and `HF_TOKEN` empty before the backend loads `.env`. Suite passes with the token still in `.env` (326 passed) |
| — | `deploy_space.py` refused to run without the inference token locally, and otherwise overwrote the Space's `HF_TOKEN` secret | `--keep-space-hf-token` leaves the Space secret untouched for a teammate redeploying code |

Five regressions added in `tests/test_handoff_refinements.py`; the
`test_huggingface_provider.py` case that pinned "two calls is fatal" removed.

## Still open (not fixed here)

- **Replan latency.** Still dominated by GLM thinking time (20–37 s on
  `design_maneuver` turns). Two untested levers: pass a thinking-disable
  parameter through the router if Baseten honours one for GLM; or prefetch the
  verifier result for every primary-qualified option after a policy change so
  the model's first turn already sees the vetoes. Neither was tried: no
  `HF_TOKEN` in this checkout.

## Debris-stream scenario (added later the same day, one-hour scope)

- `scenarios/cloud.py` → `scenarios/variants/debris_cloud.json`: 14 objects.
  Keeps `primary.json`'s satellite, DEB-1 and DEB-2 exactly (baseline 133.698 m,
  trap `t30_ret_100` blocked by DEB-2 at 523.170 m); adds a second trap FRG-09
  constructed on `t30_ret_200` (477.332 m) and 10 fragments from a simulated
  breakup, each kept only if ≥ 1.5 floors from every grid option. Verified
  answer `t30_pro_200`, closest 2,209.532 m (DEB-1); all four 0.20 m/s prograde
  options pass. Seed 3001, 12 attempts, 17 s to generate.
- `tests/test_debris_cloud.py` re-verifies those facts from the JSON; the
  fixture-shape test now allows ≥ 3 objects; CONTRACTS.md updated.
- 3D scene draws every tracked object (paths only for the spacecraft and the
  measured object). Captions count objects. GZip on responses ≥ 4 KB.
- Measured locally: analysis 5.6 s (was ~1.2 s on primary; verifier is still
  one pass per object), bundle 5.2 MB before compression, tool results ≤ 1.7 KB,
  CDM record 13.9 KB (limit 16 KB — a larger stream will exceed it).
- **Not measured:** live GLM planner behaviour on this scenario. Rehearse before
  recording (DEMO_VIDEO.md says how to fall back).
- Deferred: vectorised multi-object verifier (would bring analysis back near
  1 s and allow ~40+ fragments); a real-catalogue screen; two-operator
  coordination.

## Real debris tracking and avoidance (later still, same day)

User authorised a one-time CelesTrak download. `scripts/fetch_snapshots.py
--catalog` fetched, at 2026-09-13T01:20:44Z, four GP groups into
`data/catalog/` with `catalog_provenance.json`: iridium-NEXT (80),
iridium-33-debris (110), cosmos-2251-debris (585), fengyun-1c-debris (1,969).
**This reverses the AGENTS.md "no catalog scanner" scope line for one
constellation; tell the team.**

- `backend/tracking.py`, `GET /tracking/screen`: SGP4 at common UTC times over
  84 h, 60 s KD-tree pass, straight-line miss estimate, exact refinement.
  213,120 pairs, 1,151 passes under 10 km, ~15 s (warmed at server start).
- SOCRATES cross-check: IRIDIUM 170 × 30232 — published 48 m at
  02:02:50.465, ours 105 m at 02:02:50.433, same 14.879 km/s; IRIDIUM 117 ×
  31024 — published 28 m, ours 1.496 km, 0.2 s apart. The first is also our
  closest pass overall.
- Measured and rejected: handing a real pass to the two-body planner. Replaying
  the 105 m pass in two-body from 0.5–3 h before gives 7.5–22 km.
- `backend/avoidance.py`, `POST /tracking/assess`: burns at 1/3/5/7 half-orbits
  before the pass × speed up/slow down × 0.10/0.25/0.50 m/s plus no burn;
  Clohessy-Wiltshire displacement projected onto the encounter plane; options
  that clear 1.25 km re-screened (SGP4 + CW displacement) against all 2,664
  fragments for 12 h. 105 m pass → 0.25 m/s slow down 342 min before,
  estimated 2,492 m, re-screen 2,487 m, nothing else within 5 km. The 1.5 km
  IRIDIUM 117 pass → no burn. ~1.3 s per assessment.
- Tracking tab (`TrackingPanel.tsx`); `/tracking` added to the access guard;
  deploy script now uploads `data/catalog/`. Tests: `test_tracking.py` (5),
  `test_avoidance.py` (4).
- Superseded the same day by the two items below.

## Operator coordination and the triage agent

- `scenarios/coordination.py` → `scenarios/variants/two_operators.json`
  (seed 4001, 134 attempts, ~3 min): SAT-1, a synthetic partner satellite OPS-B
  (maneuverable, `operator: "Partner operator"`), one distant debris object.
  Nobody moves: 81.4 m. Our own plan `t15_ret_200`: 1,465.8 m alone. Partner's
  own plan `t15_pro_200`: 1,465.1 m alone. Both together: 561.7 m. Partner
  reversed with ours: 81.1 m. Agreed under the rule: only Orion West burns.
- `backend/coordination.py`, `GET /cases/{id}/coordination`: joint screening of
  every pair involving either satellite (verifier `screen_pair`), published rule
  (least total delta-v → fewer movers → larger clearance), agreement SHA-256.
  Coordinate tab appears when a case has two manoeuvrable objects; snapshot
  objects now include `maneuverable` and `operator`.
- `backend/agent/tracker.py`, `POST /tracking/agent` (background run, poll
  `/runs/{id}`): prefetched summary and passes under 1.25 km; tools
  `get_screen_summary`, `list_passes`, `assess_pass`; limits 10 model calls,
  14 tool calls, 5 assessments, 150 s; multi-call turns answered in order;
  triage table built from assessment results; prose guard over every tool
  figure. UI verified with a **scripted** model on the real data (2 passes
  assessed, 3 calls, 3.9 s). **Live GLM behaviour not measured** — no inference
  token on this machine.
- Tests: `test_coordination.py` (5), `test_tracker.py` (8).

## Commit and deployment

- Committed and pushed to GitHub `main` as `360e89d` (fast-forward from
  `717fdb4`). Full suite 326 passed with the operator token still in `.env`;
  7 frontend tests passed; production build succeeded.
- **Deployed later the same day** with the Space owner's write token:
  `deploy_space.py --space Auenchanters/TBH --code-only` from GitHub `b132826`
  → Space revision `2045f0c` (81 files), no secrets or variables changed.
  Started 02:01:09 UTC; `/health` 200 with `model_access: true`;
  `/tracking/screen` 401 without the operator token (route present, guarded);
  served frontend bundle hash matches the local build.
- **Live checks on `2045f0c`, 13 Sep**, operator token restored to `.env`:
  `scripts/live_api_check.py` **ALL CHECKS PASSED** — plan 4.8 s (3 model
  calls, reviewer ALLOW), restriction preview 2.2 s, **replan 27.9 s ending
  NO_APPROVABLE_OPTION** (was 86.3 s; the pre-fix run failed UNRESOLVED at
  103.6 s), stale approval refused, idempotent execution, export and context.
  New features: tracking screen 0.8 s (23.4 s compute at startup, warmed);
  avoidance for the top pass 3.0 s, same answer as local (2,492 m est, 2,487 m
  re-screen); debris stream analysis 7.8 s; coordination 2.9 s (both as
  planned 561.7 m BLOCK, agreed only_ours). **Triage agent on live GLM: brief
  ready in 13.5 s, 4 model calls, 5 assessments, no flagged figures** — all
  five triaged NEEDS_BURN (IRIDIUM 170, 131, 171, 100, 156). The brief opened
  with a "Brief for the operator:" line despite the no-headings instruction.
- Earlier attempt: `deploy_space.py --dry-run` listed 66 committed files and
  no secrets. The real run was refused: `403 Forbidden: You have read access but
  not the required permissions` on `/api/spaces/Auenchanters/TBH/secrets`. The
  cached HF login on this machine is `jacklachan` (write token, no orgs); the
  Space is on the personal account `Auenchanters`. It failed on the first write,
  so the Space is unchanged and still serves `ea758d5`.
- **Next action, for the Space owner:** `git pull`, then
  `uv run --no-project --python 3.12 --with huggingface_hub python scripts/deploy_space.py --space Auenchanters/TBH`
  (add `--keep-space-hf-token` if the local `.env` has no inference token), then
  `python scripts/live_api_check.py --base https://auenchanters-tbh.hf.space` and
  record the replan time here.
- Video shot list with verified on-screen numbers: [DEMO_VIDEO.md](../DEMO_VIDEO.md).
  The record-exchange tamper check was driven in the local UI: the untampered
  record "holds"; changing `MISS_DISTANCE` 2491.888 → 9999 gives "does not hold",
  recomputed 2,491.9 m.

## Autonomous watch and crash replay

- `backend/agent/watch.py`, `POST /watch` (background run) and
  `POST /watch/{run_id}/approve`: detect (catalogue screen) → triage agent →
  assessment per NEEDS_BURN pass → AI safety reviewer per burn (parallel, fails
  closed: BLOCK or UNAVAILABLE keeps it out of the approvable queue) →
  coordination (real passes are against debris, so none needed; the simulated
  two-operator case is added, labelled SIMULATED) → decision queue. Timeline
  records each step's actor. Approval is the only human step, simulated,
  idempotent, refused for anything not awaiting approval. `/watch` is behind
  the access guard.
- Windowed visualization bundles: `window_start_s` / `window_end_s` on
  `GET /cases/{id}/visualization` (≤ 1 h, encounter times inside the window
  stay exact samples).
- UI: *Autonomous watch* tab (six-stage strip, plain-English decision cards,
  approve, brief, actor timeline) and *Crash test* tab (collision scenario,
  baseline vs the first comfortable verified option — here only `t15_ret_200`
  passes, 1,011.4 m closest; two synchronized panes at 1 s samples, linear
  display interpolation between samples, slow-motion near the pass, illustrative
  explosion). Crash: 4.0 m at T+04:31:24, closing 7.7 km/s; burn variant 9.383 km
  at that instant.
- Verified in Chromium: crash replay plays through contact; watch with
  **scripted** models on real data (13 s, 4 decisions, approve works). Live GLM
  run of the watch not yet measured.
- Tests: `test_watch.py` (7).
