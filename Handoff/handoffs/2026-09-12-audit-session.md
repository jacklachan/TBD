# Session note — 12 September 2026 — audit, dead code, case memory

Format per [TEMPLATE.md](TEMPLATE.md). Role-file detail is in
[C_AGENT_API.md](C_AGENT_API.md) and [A_PHYSICS.md](A_PHYSICS.md); this is the
one-page view of a single session so the next reader does not have to reassemble
it from five appended sections.

## What changed, in the order it was found

| # | Finding | Where |
|---|---|---|
| 1 | `scenario_id` was interpolated into a filesystem path unchecked | `backend/api.py` |
| 2 | Concurrent runs on one case lost their entire trace | `backend/store.py` |
| 3 | The Gemini API key travelled in the query string | `backend/agent/llm.py` |
| 4 | Case memory was never written — the feature was inert | `backend/api.py` |
| 5 | `export GEMINI_API_KEY=...` in `.env` was silently ignored | `backend/config.py` |
| 6 | The Gemini wire format had no test at all | `backend/agent/llm.py` |
| 7 | The prior case reached the operator only as a sentence | snapshot + workspace |

Three of these fail silently, which is why none had a test: a lost trace reads
as a failed run, an unparsed key reads as a missing key, and an inert memory
reads as a scenario with no history.

## Commands run

```
$ python -m pytest tests/ -q
302 passed, 2 warnings in 82.28s          # 270 at the start of the session

$ npm --prefix frontend ci && npm --prefix frontend run build
added 62 packages / ✓ built in 1.23s

$ npm --prefix frontend test
Test Files  1 passed (1)      Tests  7 passed (7)

$ python scenarios/gen.py --check
--check: all fixtures built and verified; nothing written.

$ python scripts/demo_pipeline.py
OUTCOME    verified option t30_ret_200        0.70 s total

$ python scripts/diagnose.py
No failures. Demo is safe to show.
```

## Verified

- Every committed fixture still rebuilds to the same numbers. 133.698 m baseline,
  2,016.9 / 523.2 m for the rejected burn, 2,491.9 / 2,569.0 m for the verified
  one. The numerical work in this session is a speed and correctness change, not
  a change of answers.
- Search 1.109 s → 0.595 s; whole Gate 2 chain 1.885 s → 0.70 s.
- Constructed-encounter time error improved 3.5e-10 → 2.5e-10 s; verifier versus
  search agreement 3.559e-08 → 3.376e-08 m.
- `backend/agent/llm.py` coverage 81% → 96%; whole backend 92%.
- The built frontend driven in Chromium against `uvicorn backend.api:app` at
  1440×960 and 390×844: two canvases, real figures, **no console errors and no
  horizontal overflow at either width**.
- `prior_cases` renders in the workspace after a real planner run, not only in
  the JSON.

## Not verified / failed / not run

- **No live model call.** There is no API key in this checkout — no `.env`,
  nothing in the environment — so `scripts/smoke_llm.py` and
  `scripts/live_api_check.py` were **not run** and no live result is claimed
  anywhere in this session's notes. Every agent test uses `ScriptedProvider`.
- The retry path is tested against a fake `requests.post`, not a real endpoint.
- The `export` parsing fix is exercised through `load_env` and
  `gemini_api_key()`, not through a real deployment.
- Docker image execution remains unverified; no daemon here.
- `frontend/dist` is a build artefact and stays gitignored. `diagnose.py` asking
  a fresh checkout to build it is correct behaviour, not a defect.

## Corrections to earlier notes in this packet

Two claims written earlier in this session were wrong and have been withdrawn
where they were made:

- That the workspace never shows the operator a prior case. It did — `App.tsx`
  renders every event's type and summary. What was missing was that retrieval
  had nothing to report.
- That `frontend/dist` being unbuilt was an open failure. It is a build step.

## Contract changes

`CaseSnapshot` gains `prior_cases: PriorCase[]`. Additive; an older client that
ignores it is unaffected. `frontend/src/contracts.ts` was updated in the same
commit, per the integration rule in AGENTS.md. Nothing else changed shape.

## Next concrete action

Run `scripts/smoke_llm.py` with a real key, then `scripts/live_api_check.py`.
That is the only unexercised path left in the agent layer, and the `export` fix
means a pasted key will now actually be found.
