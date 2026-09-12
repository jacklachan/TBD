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
| 8 | Prior cases were invisible unless the Evidence tab was already open | `frontend/src/App.tsx` |

Three of these fail silently, which is why none had a test: a lost trace reads
as a failed run, an unparsed key reads as a missing key, and an inert memory
reads as a scenario with no history.

(8) was found while testing (7). The Evidence panel is not mounted until its tab
is selected, so a run could retrieve history and the operator would never know
unless they happened to click through. The tab now carries the count in the same
`nav-count` mark the Maneuvers tab uses, with screen-reader text saying what it
counts. Verified in the browser *before* opening the tab: `Evidence 2 earlier
cases on this scenario`.

Two other things cost a retry while testing and are **not** defects, recorded so
nobody re-investigates them:

- The AI planner button is disabled without a key. That is correct, and the
  panel already says why: *"Set GEMINI_API_KEY on the server to enable AI.
  Numerical controls remain available."* The browser probe borrows
  `frontend/e2e/scripted_server.py`'s trick of reporting model access in
  `/health`; the planner underneath stays scripted.
- This stylesheet defines `--divider`, `--muted`, `--text` and sizes in px. It
  has no `--space-*`, `--rule` or `--ink-*` tokens. Check what the file defines
  before adding a block; a token that does not exist fails silently as a zero
  gap.

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

## What needs doing now

In order. The first is the only thing standing between this build and a complete
demo.

### 1. Prove the live model path — needs an API key

**No live model call has been made in this checkout.** There is no key here, so
`scripts/smoke_llm.py` and `scripts/live_api_check.py` were **not run** and no
live result is claimed anywhere in this packet. Everything in the agent layer is
proven against `ScriptedProvider`, which proves the loop and proves nothing about
any model.

```bash
cd <repo>
echo 'GEMINI_API_KEY=your-key-here' > .env     # `export KEY=...` also works now

python scripts/smoke_llm.py                    # request -> function call -> result -> continuation
python scripts/live_api_check.py               # 20 checks end to end
```

`smoke_llm.py` deliberately **fails on a text-only reply**: a model that answers
in prose has not proven tool calling, which is the mechanism the whole planner
depends on. Record the model ID that worked, the latency, and every attempt that
failed in `C_AGENT_API.md`. Model IDs go stale — `gemini-2.5-flash` is already
retired and answers 404 — so rerun this rather than trusting the default in
`backend/config.py`.

If it fails, the two failures already seen are written up in `C_AGENT_API.md`: a
retired model ID, and a replayed `functionCall` arriving without its
`thoughtSignature`. The second is now unit-tested, so a wire-format regression
should surface before a live call does.

### 2. Build the frontend before demoing

```bash
npm --prefix frontend ci && npm --prefix frontend run build
python -m uvicorn backend.api:app --port 8000
```

`frontend/dist` is a build artefact and is gitignored on purpose. A fresh clone
has no bundle, and `scripts/diagnose.py` will say so — that is correct, not a
defect. Run `diagnose.py` before any demo; it is the single check that covers
fixtures, physics, ingest, interop, the build and the test suites.

### 3. Re-time the loop and replace the predicted figure

`Handoff/STATE.md` carries a *predicted* latency saving from prefetching the
briefing and screening — arithmetic on an earlier measurement, not a new one.
With a key, time a real run and replace it. **Do not put a predicted number on a
slide.** The last measured figure is 16.6 s, of which ~15.4 s was model time.

### 4. Smaller, genuinely optional

- Docker image execution is unverified; no daemon was available here.
- The memory cap (500 rows) is covered by a unit test, not by a long-running
  server.
- `prior_cases` renders the case ID as text. If an operator should be able to
  *open* the earlier case, the workspace needs a route to it — the data is
  already there.
