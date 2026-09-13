# Satellite Demo — start here

**Temporary display name:** Orion West, carried forward from the teammate's build. Keep module and file names descriptive when renaming it.

**Package revision:** 6 — 13 September 2026. **Status:** deployed on Auenchanters/TBH; HF/GLM workflow and interactive 3D verified. Initial plan 4.7 s, replan 86.3 s: the ten-second replan target is not met. Start with STATE.md and [the current refinement session](handoffs/2026-09-12-hf-refinements.md) for verification and deployment results. Older dated entries are historical evidence.

**Repository:** [jacklachan/orionwest](https://github.com/jacklachan/orionwest). Three builders, twenty hours, one satellite, two synthetic debris objects, six simulated hours.

The product compares maneuver options, discovers that a promising burn creates a second close approach, rejects it, and replans. A judge can change constraints in plain English. The target is a fresh verified decision in under ten seconds. A chart provides the numerical evidence; a synchronized moving 3D satellite scene makes the encounter understandable.

## Reading order

1. [AGENTS.md](AGENTS.md) — shared instructions for any teammate's AI.
2. [STATE.md](STATE.md) — what exists, what is unverified, and decisions that supersede older documents.
3. [plan.md](plan.md) — scope, schedule, gates, demo, and judging criteria.
4. [CONTRACTS.md](CONTRACTS.md) — types, units, ownership, tools, and API boundaries.
5. Read your role: [A: physics](handoffs/A_PHYSICS.md), [B: product and 3D](handoffs/B_PRODUCT.md), or [C: agent and API](handoffs/C_AGENT_API.md).
6. Open the relevant detailed specifications: [IMPLEMENTATION.md](IMPLEMENTATION.md), [DATA.md](DATA.md), [DASHBOARD.md](DASHBOARD.md).

Read [research.md](research.md) for GitHub reuse and hackathon evidence. The [reference folder](reference/README.md) preserves earlier documents; it is historical context, not the current build specification.

## Package layout

```text
Handoff/
  README.md                 Entry point and sharing instructions
  AGENTS.md                 One shared set of AI instructions
  CLAUDE.md                 Claude entry point; points to AGENTS.md
  GEMINI.md                 Gemini entry point; points to AGENTS.md
  STATE.md                  Current status, decisions, evidence, next action
  plan.md                   Current product plan and 20-hour schedule
  CONTRACTS.md              Shared domain and integration contract
  IMPLEMENTATION.md         Planned code layout and engineering tasks
  DATA.md                   Snapshot acquisition and provenance rules
  DASHBOARD.md              Chart, moving 3D scene, and operator workflow
  research.md               Research navigation and current reuse decision
  handoffs/
    A_PHYSICS.md             Builder A's scope and acceptance checks
    B_PRODUCT.md             Builder B's scope and acceptance checks
    C_AGENT_API.md           Builder C's scope and acceptance checks
    TEMPLATE.md              Reusable handoff update format
  reference/
    README.md               Archive boundary and known outdated claims
    plan.md                 Original product plan, preserved
    research.md             Original cited research, preserved
    IMPLEMENTATION.md       Original supplied spec, preserved
    DATA.md                 Original supplied spec, preserved
    DASHBOARD.md            Original supplied spec, preserved
```

The implemented source is in `backend/` and `frontend/src/`. [IMPLEMENTATION.md](IMPLEMENTATION.md) retains the original build plan; current contracts and the refinement session identify the implemented paths.

## Share and resume

Send this entire `Handoff` directory, or zip it. Its active links are relative and work after moving it to another machine. Nothing needed to understand the plan lives outside this directory.

The implementation transfer is in [updates/README.md](updates/README.md): a portable archive of changed source files, assets and dependency locks, plus its base commit, source commit and hashes. This avoids sending dependency folders or the entire repository. Screenshots and the supplied design are included separately in this packet.

Give a teammate's AI this message, replacing the role:

> Read README.md, AGENTS.md, STATE.md, CONTRACTS.md, and handoffs/A_PHYSICS.md in this Handoff folder. Explain the current state and your assigned boundaries. Follow my current request; the task checklists are plans, not permission to execute every step. Do not assume that any planned file, API key, dataset, or test already exists.

Keep current documents here as the single source of truth. After a work session, update `STATE.md` and the relevant file in `handoffs/`; use `TEMPLATE.md` for additional dated notes. Do not create recursive `Handoff/Handoff` copies. A later transfer of implemented code must also identify the repository commit; a documentation packet alone is not a runnable application.
