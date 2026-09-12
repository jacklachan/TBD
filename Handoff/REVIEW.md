# Merge, security and reliability review — 12 September 2026

Scope: source-assisted testing of our local API, agent boundaries, store and numerical pipeline. This is a bounded review, not a certification or a test of external services.

## Merge

`main` was fast-forwarded to `origin/main` (`65ab3d1`), then to `origin/claude/focused-brown-5r09go` (`c6b6cd3`). No conflicts. Existing authorship is preserved; new commits use Auenchanters.

## Defects reproduced and corrected

| Finding | Correction and regression evidence |
|---|---|
| Very small or non-finite visualization steps could request excessive allocation | Finite 1–600 second steps and a horizon/sample cap, enforced before propagation |
| A new idempotency key allowed the same case to execute again | Transactional, case-wide execution guard; repeats return the original execution |
| Approval could race a policy change or use evidence from another candidate | Version, candidate, case, PASS result and reviewer ALLOW rechecked inside the SQLite write transaction |
| A pending diff could overwrite a newer policy | Base-version check plus atomic compare-and-update |
| Non-finite interpreted budgets could enter policy | Finite numeric validation |
| Paid model endpoints had no access protection | Optional bearer token locally; required for non-loopback deployment; constant-time comparison; no reliance on spoofable Host headers |
| Cross-origin mutation and oversized/chunked bodies were insufficiently bounded | Origin checks and an incremental 16 KiB body limit before parsing |
| Duplicate plans and unlimited concurrent preview requests consumed resources | One active plan per case, four combined model operations, bounded run and case registries |
| A completed case could be replanned without reset; late runs could replace current evidence | Reset required after execution; stale proposal/grid persistence guarded by policy version |
| Runtime requirements were unpinned; local pip had published advisories | Tested runtime pins, separate dev requirements, upgraded local pip |

Tests live in `tests/test_security_review.py` (18 cases). They were run against the uncorrected behavior first; failures were reproduced before fixes. The merged branch already fixes path traversal, concurrent event loss, the API key in a query string and other issues recorded in STATE.md.

## Verification

- Python 3.12.11, Windows; `python -m pytest tests -q --cov=backend --cov-report=term-missing`: **186 passed**, 91% statement coverage, 50.98 seconds. Two upstream TestClient deprecation warnings remain.
- `python scenarios/gen.py --check`: all four fixtures rebuilt and checked, no files written.
- `python scripts/demo_pipeline.py`: 25 options, secondary conflicts rejected, `t30_ret_200` verified; **0.60 seconds** total on this machine. This excludes model latency.
- `python -m bandit -r backend -q -ll`: no medium/high findings.
- `python -m pip_audit --local`: no known vulnerabilities in the installed environment after upgrading pip.
- `python -m pip check`: no broken requirements.

## Limits and remaining work

No live Gemini key is available in this checkout, so this review did not repeat live model tests. Earlier live results in STATE.md are historical evidence, not fresh measurements. The under-ten-second model target remains unverified. Four scenarios exist; a fifth distinct scenario and a physical second-machine check remain outstanding.

The bearer token is a shared operator credential, not per-user authentication. Concurrency and size caps are not a time-based rate limiter. A public production service still needs quota enforcement, durable jobs, per-user authorization and deployment-specific assessment. Keep one API worker because run state is process-local. Frontend and browser checks follow in the next phase.
