# Frontend implementation plan and integration map

**Status: implemented, 12 September 2026.** The build sequence below records the approved direction; it is not an outstanding task list.

User-approved direction: adapt the supplied `design.md` and approved dark/light v2 references to a satellite decision workspace. Keep the temporary name Satellite Demo. Use the supplied optical glass, fine rims, Inter 300/400/500, neutral capsules and peripheral panels around meaningful continuous 3D content.

## Build order

1. Expose a bounded, versioned numerical comparison without model calls. This is explicitly numerical analysis, never an AI run or approvable proposal. Add a typed manual budget control for key-free exploration; natural-language preview/confirm remains the real model path.
2. Build a chart using backend samples and refined encounter times. Show the floor and the closest-to-any-object envelope; provide exact encounter jumps.
3. Place a Three.js globe and original procedural satellite around that same clock. Orbit/approach/spacecraft views change only the camera, never the physical separation. Enlarge marker geometry and disclose it. Keep authoritative distance labels in HTML.
4. Connect scenario selection, option comparison, time playback, AI planning, policy confirmation, approval, reset, evidence export and frozen SOCRATES context.
5. Verify TypeScript, meaningful state/clock tests, production build, browser interactions, both themes and mobile layout. Preserve numerical and API checks.

## New HTTP contract

- `POST /cases/{id}/analysis` takes the usual version stamp. Returns case/scenario/policy versions, `mode: NUMERICAL_ANALYSIS`, option count, ranked option rows, independent checks for primary-qualified options, a recommended ID or null, and measured numerical runtime. It creates no model trace, validation authorization or proposal.
- `POST /cases/{id}/policy-manual` takes the version stamp and finite `max_delta_v_mps` in [0,1]. This explicit operator action advances the policy version and invalidates pending proposals through the existing store transaction. The original floor and blocked windows are preserved. It returns a current case snapshot. Natural language still uses `/policy-preview` and `/policy-confirm`.
- Both endpoints inherit the API guard and resource limits. Browser requests carry the operator bearer token in a header, never a URL. The Gemini key stays on the backend.

## Files and responsibility

`frontend/src/api.ts` and `contracts.ts`: transport and approval guards. `workspace.ts`: formatting/sample selection only; no propagator in the browser. `components/SeparationChart.tsx`: numerical evidence. `scene/`: rendering, camera, original spacecraft geometry. `App.tsx`: operator workflow. `styles.css`: semantic light/dark tokens and responsive composition.

Visual references guide material and composition, not runtime content. No terrain image is presented as orbital data. Satellite geometry is illustrative, not an engineering model of NOAA 20. Earth imagery and lighting are visual context; object positions come from the frozen TLE-seeded simulation. Read ASSETS.md for attribution.

## What is working

- Both themes follow the supplied neutral glass palette, thin rim reflections, Inter weights and compact controls. Original NASA-textured globe and procedural spacecraft replace the reference terrain. `design/` preserves the supplied Markdown and token ledger; shipped font/icon/Three notices are preserved.
- The main scene is lazy-loaded. Chart data and all approval checks work if WebGL cannot start. Global and local encounter cameras never stretch physical separation. Positions map simulation XYZ to Three X,Z,-Y by a right-handed display rotation. Camera, Earth orientation and spacecraft attitude are illustrative.
- The clock selects a backend sample; it never interpolates an exact minimum. The chart retains all samples and exact refined events, uses a labeled logarithmic distance scale, and offers a local time window. The mobile chart has its own measured width rather than shrinking desktop labels.
- Scenario selection, selected-option geometry, both debris measurements, playback/speed, exact focus, camera reset, option filtering, manual budget changes, AI preview/confirmation, plan/run status, reviewer-gated approval, reset, context and versioned JSON export are wired to the API.
- New numerical endpoints do not create fake AI traces or proposals. The UI says AI offline when `/health` reports no key. Case runs and actual model/tool events appear in the Evidence panel; this API currently persists agent events at the end of a run, so the UI shows honest running state rather than a fabricated live trace.
- Approval identifies the actual proposed candidate and stays disabled while the operator is inspecting a different trajectory. The operator can load the proposed trajectory before approving. The browser regression reproduced and fixed the earlier ambiguity. After an AI run the comparison is refreshed, including an expanded grid if the planner used one.
- Runtime dependencies are pinned and npm lockfile committed. Docker has a frontend build stage and excludes local secrets/dependency directories.

## Verification and screenshots

- `python -m pytest tests -q --cov=backend --cov-report=term-missing`: **191 passed**, 91% statement coverage, 62.40 s. Two upstream TestClient deprecations remain.
- `npm --prefix frontend test`: **7 passed** (exact sample selection, narrow minima, missing selection, clock formatting, stale responses, approval evidence and computed comparison IDs).
- `npm --prefix frontend run build`: TypeScript and production build pass. Scene chunk is 571 kB minified / 143 kB gzip and lazy-loaded; Vite emits its default 500 kB chunk-size advisory. No chart/physics dependency on WebGL.
- `npm audit --audit-level=moderate`: **0 vulnerabilities**. Bandit: no medium/high findings. Pip check: no broken requirements.
- Playwright/Chrome: four scenarios cover the real numerical pipeline, both themes, 25-option table, shared playback, 523.2 m veto, 2.492 km alternative, budget infeasibility, export, scenario switching, mobile overflow/theme persistence and WebGL failure. Also exercised against the built frontend served by FastAPI.
- A separate, explicitly scripted provider test covers AI planning, reviewed approval, reset, a plain-English restriction, preview/confirm and policy recomputation through real HTTP. An initial test-fixture failure used the wrong tool name; importing `TOOL_PROPOSE_POLICY` fixed the fixture. This is not a live-model measurement.

Screenshots: [dark](evidence/frontend-dark.png), [light](evidence/frontend-light.png), [close approach](evidence/frontend-approach.png), [mobile](evidence/frontend-mobile.png), [mobile chart](evidence/frontend-mobile-chart.png).

To repeat the optional browser agent check, run these alongside API port 8000 and Vite port 5173:

```powershell
.venv/Scripts/python.exe frontend/e2e/scripted_server.py
# In another terminal, from frontend/:
$env:TEST_SCRIPTED_AGENT='1'
npx playwright test e2e/agent.spec.ts
```

`e2e/scripted_server.py` is a local test fixture on port 8001, not a production provider or app import. Do not expose it or use its timings as Gemini evidence.

## Practical limits

No live Gemini key was available, so the current change does not prove the under-ten-second target. There are four scenario fixtures, not five. Browser testing used Chrome on this Windows host and mobile emulation, not a second physical machine, Safari or every GPU. The Docker daemon was unavailable: the image definition is updated, but no Docker build/run is claimed. No public site was deployed.

The app is a single-operator demo with a shared bearer token, bounded requests and one process. It is not a production satellite command system. Camera views and model sizes are explicitly illustrative; deterministic geometry is authoritative.

## Update — later the same day

Two statements above have since been overtaken, and one of them undersells what
the product now does.

**The running state is a real live trace.** The note above says agent events are
persisted only at the end of a run, so the UI shows honest running state rather
than a live one. The planner now reports each step as it completes, the run
record carries the latest over HTTP, and the workspace shows it. It is the
planner's own trace, not a fabricated one: a poller sees the most recent step
rather than every one, because a fast run finishes several between polls, and
the complete trace is still the persisted one.

**Counts have moved.** 270 Python tests and 11 browser tests, with the browser
suite now also covering the record exchange, pasted catalogue elements, the
two-object case that used to crash the scene, recovery from a case the server
has forgotten, and a scenario where the honest answer is that nothing works.

Everything else in this handoff still holds, including the WebGL-failure path,
the no-interpolation rule for exact minima, and approval staying disabled while
the operator inspects a different trajectory.
