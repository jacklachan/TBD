# HF deployment and continuation of the audit — 12–13 September 2026

Started at teammate commit `11b4cff18d8ac08ba587fc679e24c405b1d43f8e`.
The original checkout has unrelated uncommitted documentation edits; those were
preserved. Work is in `C:/Users/Utkarsh/Desktop/Project/TBD-refinements`, branch
`codex/handoff-refinements`. Git author/committer remains Auenchanters.

## Changes

- `backend/agent/huggingface.py`, `backend/config.py`, `backend/api.py`: HF REST
  chat completions, matching tool-call IDs, serial tool requests, explicit
  malformed/incomplete response errors, bearer-token secrets, bounded retries.
  The user selected `zai-org/GLM-5.3-Flash:baseten` for planner and reviewer.
  No Gemini runtime fallback. The older Gemini adapter remains for historical tests.
- `backend/agent/planner.py`: an early model conclusion after some vetoes is
  unresolved unless every primary-qualified grid option has independent BLOCK
  evidence. Final elapsed time includes safety review.
- `backend/api.py`: if a model concludes without an answer after a partial
  investigation, the existing numerical comparison completes the finite grid.
  It can establish NO_APPROVABLE_OPTION, but never creates a proposal or reviewer
  ALLOW. A `grid_audit` event preserves the unresolved model outcome, actual
  additional checks and the audit verdict. `validations_run` remains the count
  of model-requested checks; audit checks are named separately in the trace.
- `backend/api.py`: memory no longer invents a widened search or a binding
  constraint. `backend/agent/llm.py`: legacy transport timing includes retries.
- The rationale guard recognizes the exact comfortable-clearance threshold
  and clearance margin already reported by the validation tool, plus remaining
  delta-v. Invented distances remain flagged. Planner instructions explicitly
  limit rejection claims to checked options; prose is still not a proof.
- `frontend/src/components/PriorCaseEvidence.tsx`, `frontend/src/App.tsx`,
  `frontend/src/styles.css`: read-only earlier-case inspection with policy,
  proposal, reviewer, execution and versioned numerical evidence. Missing cases
  are recoverable; latest snapshot is distinguished from the recalled run.
  Active-case export is hidden during history inspection to avoid exporting a
  different case from the one displayed. Regression and screenshot verified.
- `scripts/smoke_llm.py`, `scripts/live_api_check.py`, `scripts/diagnose.py`:
  active HF adapter/config, UTF-8 console output, local operator-token loading.
- `scripts/deploy_space.py`: deploy only allowlisted committed Git blobs to an
  explicitly named existing Docker Space, with secrets set separately.
- `.env.example`, `README.md`, `DEPLOY.md`, `Handoff/CONTRACTS.md`: HF/GLM setup
  and Docker deployment requirements. HF_TOKEN needs fine-grained Inference
  Providers permission; it does not need repository write permission.
- `tests/test_huggingface_provider.py`, `tests/test_handoff_refinements.py`,
  `tests/test_agent.py`, `tests/test_config.py`, `frontend/e2e/history.spec.ts`,
  `frontend/e2e/scripted_server.py`: new regressions and updated test fixtures.

## Verification so far

- Final backend suite: **322 tests passed, 93% coverage, 131.94 s**, including
  the hosted-workflow regressions. Two upstream Starlette/anyio deprecation warnings.
- Frontend: 7 unit tests and strict TypeScript / production build passed.
- 10 browser workflows passed against built FastAPI, 52.5 s; two scripted history
  workflows passed, 22.1 s, and passed again after the history-export fix;
  scripted planning/approval/reset/constraint workflow
  passed, 8.1 s. Scripted tests make no external model call.
- `pip check`: no broken requirements. `npm audit`: no known vulnerabilities.
- Bandit reports one medium B608 warning at `backend/store.py:272`. Reviewed:
  table names come only from a fixed literal tuple; placeholder count is generated
  from internal selected rows and values are parameter-bound. No user-controlled
  SQL interpolation was found. It was not suppressed or claimed as a clean scan.
- `git diff --check` passed. Screenshots are under `Handoff/evidence/`.

## Live attempts and limitations

1. Before the user's provider change, Gemini 3.6 Flash tool round trip passed
   in 9.859 s. Its HTTP workflow passed: plan 16.8 s / replan 47.0 s. Historical
   only; this provider is no longer used by the application.
2. HF CLI's old cached credential was invalid. Device OAuth login succeeded as
   Auenchanters. Listing dedicated Endpoints was denied: OAuth lacked
   `inference.endpoints.read`; no claim that the account had no Endpoints.
3. Initial HF gpt-oss candidate request returned HTTP 402 (billing). The user
   subsequently selected GLM, supplied a persistent inference token, and created
   Auenchanters/TBH on CPU Upgrade.
4. First GLM round trip returned a tool call and continuation, but smoke output
   failed on an emoji under Windows cp1252. The script now explicitly uses UTF-8.
5. GLM smoke rerun passed: 1.320 s + 2.720 s = **4.040 s**.
6. First GLM HTTP workflow: initial reviewed plan passed in **10.8 s**, restriction
   preview 4.0 s; reduced-budget run ended UNRESOLVED after six model-requested
   validations (58.0 s). The checker correctly failed its infeasibility check.
   This led to the separately logged bounded grid-completion audit, not relaxed
   approval criteria. Approval/idempotency/export/reset passed in that attempt.
7. First hosted workflow on `6d4134b`: initial reviewed plan **5.3 s**, preview
   2.0 s, replan 21.5 s. Two checks failed: the guard flagged the tool-provided
   1,250 m comfort threshold, and the model stopped before reaching its validation
   allowance. Added regressions and corrected both paths. The audit now handles
   early NO_CONCLUSION as well as NO_CONCLUSION after the validation cap.
8. Hosted Docker build succeeded. Browser-origin create initially returned 403
   behind the HF proxy; explicitly allowing only the application HTTPS origin
   fixed it (201). The deployment helper now reads that host from the Hub API.
   Hosted Chrome checks passed: operator login, 3D playback, close-approach line
   at 523.2 m, clear alternative at 2.492 km, dark/light themes, mobile width,
   and no page errors. Screenshots: `Handoff/evidence/hf-deployed-*.png`.
   Hosted boundary checks also passed: missing/wrong token 401, untrusted Origin
   403, oversized request 413, and no configured secret exposed at `/.env`.

The ten-second complete-agent target is not established. No provider ranking or
quality comparison was measured. Secret values are never in this packet.

## Deployment

- Application source: GitHub `4d7c6639e4f18b79db389d09e19817668d68076b`.
- Space revision: `b63a69ff03c8908ccce7c3c101f30a45032db25f`, observed RUNNING
  on CPU Upgrade, one replica. Docker dependencies and frontend build succeeded.
- App: https://auenchanters-tbh.hf.space
- HF_TOKEN and DESK_ACCESS_TOKEN are Space secrets. The local ignored `.env`
  stores the operator password under DESK_ACCESS_TOKEN (line 29 in this checkout).
- The first attempt on this revision encountered HF HTTP 429 before the first
  model reply. The API returned unresolved with no proposal. The live checker
  now reports that cleanly rather than dereferencing a missing proposal.
- After a pause the provider recovered. Initial plan took 7.2 s, but exposed
  another guard false positive on the reported 1,491.9 m margin; regression
  reproduced and fixed. Later model replies were incomplete/filtered and remained
  unresolved. Response allowance increased from 2,048 to 8,192 tokens, preserving
  GLM's default reasoning setting; incomplete replies remain errors and now report
  finish_reason. GLM has built-in thinking (see its official model card at
  https://huggingface.co/zai-org/GLM-5.3-Flash); token truncation was a suspected
  cause, not established from the earlier combined error message.
- After these transport/guard edits: 106 affected agent, HF-provider and
  refinement tests passed in 14.71 s. The earlier full 322-test suite passed.

## Contract / next action

No HTTP field was removed or renamed. Updated status/timing semantics and the
read-only history behavior are recorded in CONTRACTS.md. Grid audit distinguishes
model steps from automatic numerical checks; it cannot promote a passing option
to a proposal. Next: finish final checks, commit/push as Auenchanters, deploy the
committed application to TBH, and verify the real hosted workflow.
