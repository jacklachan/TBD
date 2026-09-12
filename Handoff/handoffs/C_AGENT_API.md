# Builder C — agent, API, storage and integration

Read [README.md](../README.md), [AGENTS.md](../AGENTS.md), [STATE.md](../STATE.md), [CONTRACTS.md](../CONTRACTS.md) and [IMPLEMENTATION.md](../IMPLEMENTATION.md) first. This file is your scope, sequence and acceptance checks. Nothing here is implemented yet.

## You own

```text
backend/config.py               Display name, model ID, runtime settings
backend/agent/llm.py            Single Gemini adapter
backend/agent/tools.py          Five flat declarations, validation, dispatch
backend/agent/planner.py        Bounded tool loop and proposal selection
backend/agent/reviewer.py       Separate evidence reviewer with a blocking verdict
backend/agent/memory.py         Small relevant-prior-case query
backend/api.py                  Endpoints, versions, run coordination
backend/store.py                SQLite transactions, events, approval, export
data/context/socrates_snapshot.csv      Once-fetched, committed
data/context/socrates_provenance.json   Timestamp, URL, hash
scripts/fetch_snapshots.py      Shared with A
scripts/demo_pipeline.py        Shared with A — Gate 2 CLI
tests/test_policy.py
tests/test_workflow.py
tests/test_verifier.py          Shared with A
```

You share `backend/domain/models.py` with A and B, and `contracts.ts` / `api.ts` with B. You own no numerical code and no frontend component.

## Hour 0–1 — contracts, then prove the runtime

- [ ] Sit with A and B, walk CONTRACTS.md, resolve field disagreements before anyone writes logic. You coordinate the integration.
- [ ] Co-write `backend/domain/models.py`.
- [ ] **Within the first thirty minutes**, complete one real Gemini round trip: request → model returns tool arguments → your local fake tool responds → model continues with the result. A text-only reply does **not** prove tool calling and does not clear this item.
- [ ] Record in this file: the exact model ID that worked, SDK and version, measured latency, and every attempt that failed. STATE.md currently says this is unverified — you are the one who changes that.
- [ ] Fetch the SOCRATES snapshot. A owns the TLE fetch. Do not both hit CelesTrak; see [DATA.md](../DATA.md) for why that matters.
- [ ] Secrets in environment configuration only. Never in Git, never in this packet.

> Write the five tool declarations **by hand as flat dicts**. Gemini's function-calling schema is an OpenAPI subset; generated JSON Schema commonly carries `$ref`, `anyOf` and `additionalProperties` that it rejects with unhelpful errors. Validate the arguments Gemini returns with the Pydantic models afterwards — that gives you both. Confirm the exact supported subset during the smoke test rather than assuming it.

## Hour 1–3 — API skeleton and storage

- [ ] FastAPI app, the endpoint set in CONTRACTS.md, typed error contract: 422 validation, 404 unknown ID, 409 stale version or blocked approval or reused idempotency key with different content.
- [ ] `store.py`: SQLite, `CaseEvent` append with monotonic `sequence`, evidence records addressable by ID.
- [ ] `llm.py`: one function behind the provider. `call(messages, tools) -> ToolCall | Text`. If Gemini disappoints at hour nine, swapping providers should be a contained change, not a rewrite.
- [ ] Long operations return a `run_id`; `GET /cases/{case_id}` returns the current snapshot. Bounded polling is fine for B initially.
- [ ] Every response wrapper carries the active version stamp so a late reply from a superseded run cannot overwrite newer UI state.

## Hour 3–5 — tools against evolving numerics

- [ ] Wire the five tools to A's interfaces as they stabilize. Expect signatures to move; keep the adapter thin.
- [ ] The backend binds case and versions from the active run. The model cannot select a different case or manufacture a version.
- [ ] Reject unknown tools and unknown IDs. Validate every returned argument against the domain models before dispatch.
- [ ] `GET /context/socrates` reads the committed snapshot from disk. **No runtime fetch, ever.** Budget thirty minutes for this endpoint and stop.

## Hour 5–7 — first full planner run

- [ ] `scripts/demo_pipeline.py` with A: scenario → options → provisional pick → secondary veto → verified alternative, printed on the command line. This is Gate 2 evidence and it needs no UI.
- [ ] Planner loop: briefing → evaluate → select → validate → reject and reselect, or propose.
- [ ] Bounds: at most three validation attempts, at most one `widen_search` per run, one overall timeout. **Log the actual call counts.** Do not claim a fixed turn count in any document — count what happened.
- [ ] A rejected candidate can never become an approved proposal. Enforce this in code, not in the prompt.

## Hour 7–11 — the agentic surface

This is the criterion the hackathon is named after. Four things, in priority order.

**1. Policy interpretation.** `POST /policy-preview` takes the judge's sentence. The model interprets it once into flat tool arguments — `budget_scale`, `max_delta_v_mps`, or `blocked_window_id`. The **backend computes the numbers**: "halve" supplies `budget_scale=0.5` and you compute half of the confirmed budget. Scale and absolute budget are mutually exclusive. An unknown window or an unsupported request returns `NEEDS_CLARIFICATION` — never a guessed value. `policy-confirm` applies the diff once, increments `policy_version`, invalidates pending proposals, starts a fresh run.

> A budget reduction is a change to the supported Δv envelope. It does not model a failed thruster, and nobody should say that it does.

**2. Reviewer with a real veto.** Separate call, reads validated evidence and policy only, returns `ALLOW` or `BLOCK` with reason codes. It can block; it cannot override a deterministic failure. **Do not manufacture a veto for the demo.** Build a test case with a genuine reviewer-policy violation and show the real verdict.

**3. Case memory.** Small SQLite retrieval by constraint tags and scenario family. Cite the prior case ID and *suggest* a constraint. Never silently apply another operator's historical limits.

**4. Evidence-bound output.** Numeric UI and report values come only from verified typed fields. Use evidence-linked templates with a short qualitative rationale from the model. A numeric-literal scanner over the rationale is a useful supplementary check — it is not a hallucination guarantee, so do not describe it as one.

**Gate 3 at hour ten:** a real judge sentence produces a confirmed diff, a new policy version, and an actual fresh computation. A replayed animation is not a pass. If latency misses the target, cut prompt size and optional calls, and report the measured number.

## Hour 11–14 — correctness under pressure

- [ ] Approval runs in a transaction: check active versions, check validation `PASS`, check reviewer `ALLOW`, write exactly one `ExecutionRecord`.
- [ ] Idempotency: a duplicate request returns the same record. The impulse is never applied twice.
- [ ] A committed execution stays in history when policy later changes.
- [ ] `POST /reset` mints a **new** case ID from the same frozen fixture and retains the historical case.
- [ ] Export: self-contained JSON and Markdown carrying provenance, versions, evidence and measured values. Re-running the export produces the same deterministic numbers.

## Hour 14–16 — the checks that catch real bugs

- [ ] Injected instructions inside scenario text change nothing about tool permissions or policy.
- [ ] Unknown candidate ID is rejected.
- [ ] Verifier disagreement blocks approval.
- [ ] Stale approval attempt returns 409.
- [ ] Duplicate approval returns the original record.
- [ ] Out-of-order frontend responses cannot overwrite newer state.
- [ ] Live API failure and malformed policy both surface as typed `ERROR` events. **Never return a successful empty result on tool failure.**
- [ ] Measure backend computation, model time and total user-visible time **separately**. Include repeated live runs and one fresh run with no stored answer.

## What blocks you, and what to do

| Problem | Action |
|---|---|
| Gemini rejects your tool schema | Flatten it. Remove `$ref`, `anyOf`, `additionalProperties`. Handwrite the declaration and validate with Pydantic after the call |
| Tool calling does not work at all in the first 30 minutes | Say so immediately — this is the highest-impact blocker in the build. Try the other available model tier before changing provider |
| Planner loops or stalls | Your bounds are the fix, not a longer prompt. Three validations, one expansion, one timeout |
| Latency over target | Shrink the briefing payload first; it is almost always the prompt size. Tool responses carry summaries and evidence IDs, never trajectory samples |
| A's signatures keep moving before hour 7 | Expected. Keep the adapter thin and do not mirror his internals |
| Tempted to let the model emit a distance | Don't. Every number comes from a typed field. This is the answer to the hardest question you will be asked |

## Update duties

After each work block, append to this file using [TEMPLATE.md](TEMPLATE.md): changed paths, commands run and their real output, checks that failed or were not run, contract changes, next concrete action. Put the working model ID, SDK version and measured latencies in STATE.md — that row is currently unverified and you own it.
