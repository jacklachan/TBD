# Handoff update template

Copy this block to the bottom of your role file after each work session. Keep entries dated and factual. Anything you did not personally observe is not evidence.

---

## [YYYY-MM-DD HH:MM] — <Builder A / B / C> — <short title>

**Changed paths**

- `path/to/file.py` — one line on what changed

**Commands run**

```
$ <exact command>
<real output, trimmed but not edited>
```

**Verified**

- What now demonstrably works, with the number or output that shows it.

**Not verified / failed / not run**

- What is untested, what failed, what you skipped and why. This section is more useful than the one above — do not leave it empty by default.

**Contract changes**

- None. *(Or: field/signature changed, the two other builders notified, CONTRACTS.md updated, `schema_version` incremented, fixtures regenerated.)*

**Next concrete action**

- One sentence. The specific next thing, not a category of work.

---

## Rules

- Record real command output. Do not paraphrase a result, reconstruct one from memory, or write output you expect a command to produce.
- A gate is complete only when its evidence is in STATE.md with actual measured values. A plan, a diagram, a snippet or an unrelated passing test is not gate evidence.
- If you reduced scope, say so here and in STATE.md. Silent reduction is the failure mode this packet exists to prevent.
- Inspect the current repository state before editing. Preserve teammates' changes.
- No API keys, credentials, `node_modules`, virtual environments or runtime databases in this packet or in Git.
- Preserve third-party attribution and licence notices for anything adapted or imported.
