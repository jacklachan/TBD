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

## Commit and deployment

- Committed and pushed to GitHub `main` as `360e89d` (fast-forward from
  `717fdb4`). Full suite 326 passed with the operator token still in `.env`;
  7 frontend tests passed; production build succeeded.
- **Deploy not done.** `deploy_space.py --dry-run` listed 66 committed files and
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
