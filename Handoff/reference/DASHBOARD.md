# Dashboard specification — information design

Written for a judge with **no orbital mechanics background** who will look at the screen for twenty seconds before deciding whether to engage.

This is a content and layout spec, not an implementation. Build it however you like.

---

## The governing principle

**Distance-over-time is universally legible. 3D orbit views are not — and they actively mislead.**

Two orbit ellipses that cross on screen may never be at the crossing point at the same moment. Every non-expert who looks at a 3D orbit view draws the wrong conclusion about proximity. Your own plan already says *"do not use distances between drawn orbit lines as encounter evidence"* — that is the same insight, and it is the argument for what the hero element should be.

Everyone, without exception, understands **a line dipping toward a red zone.**

---

## 1. The hero: "Closest approach to any tracked object"

One chart. Big. Top of the page. This chart is the entire product.

**Axes**
- X: time, 0 → 6 hours from scenario start. Label in hours, not seconds, not epochs.
- Y: distance in **kilometres**, linear, **clipped at 50 km** with the ceiling labelled `50+ km — clear`. Everything interesting happens between 0 and 10 km; a log axis shows more and communicates less.

**The danger band:** shaded red from 0 to 1 km, labelled **`Safety floor — 1 km`**. This is the single most important visual element on the page.

**The metric:** minimum separation to *any* object in the scenario at each instant — the envelope, not one pair. This is both what a non-expert intuitively wants and the correct safety metric. Per-object breakdown lives behind an expand.

**Three lines, and they tell the whole story without a word of narration:**

| Line | Style | Behaviour |
|---|---|---|
| Do nothing | grey, dashed | dips to **0.12 km at 4.5 h** — deep in the red band |
| Rejected option | amber | clears 4.5 h, then **plunges to 0.3 km at 5.5 h** — red again |
| Recommended | blue, solid | stays above the band for the full horizon |

Annotate both dips with a callout naming the object responsible: *"0.12 km from Object 2"*, *"0.3 km from Object 3 — created by this manoeuvre."*

That amber line is your signature. A judge sees "the obvious fix creates a new problem" in about two seconds, with no explanation required. Do not bury it in a log.

---

## 2. Status chip — above the chart

One chip, large, colour plus text (never colour alone):

- 🟢 **SAFE** — no action needed
- 🟠 **ACTION NEEDED** — conjunction predicted, options available
- 🔴 **NO SAFE OPTION** — nothing in the search set clears all constraints

Judges orient off this in one second. It is also the honest headline when your infeasible scenario runs.

---

## 3. Options table

Where a non-expert actually makes the comparison. Four columns, plain words.

| Option | When | Fuel used | Closest approach | Verdict |
|---|---|---|---|---|
| Do nothing | — | ▁▁▁▁▁ | **0.12 km** | ❌ Unsafe |
| Small burn | 30 min | ▓▓▁▁▁ | 4.1 km → **0.3 km** | ❌ **Creates a new close approach** |
| Larger burn | 15 min | ▓▓▓▓▁ | 6.8 km | ✅ **Recommended** |

**Fuel as a filled bar against the budget, not a number.** `0.10 m/s` means nothing to a judge. A bar two-fifths full against a budget bar means everything, instantly. Put the numeric value in a tooltip for the technical judge.

The rejection reason belongs **in the table**, in colour, not in a trace. It is the most interesting fact on the page.

---

## 4. Constraint box — above the fold, not in settings

A plain text input, prominent, with live placeholder text:

> *e.g. "we lost a thruster — halve the fuel budget and no burns during the ground station pass"*

Judge types → agent returns a **before/after chip pair** showing the parsed change → judge confirms → system re-solves visibly.

This is the interaction you want a judge to physically touch. Hiding it in a settings panel wastes the best thing you built. When it re-solves, the prior approval must visibly invalidate — show the approved badge going stale.

---

## 5. Agent activity trace

This is where **Agentic AI Implementation** gets scored, so it must be readable, not a JSON dump.

Each step renders as a single plain-language line, expandable:

```
✓ Reviewed the situation — 3 objects, 6-hour window, 1 close approach found     0.4 s
✓ Compared 25 options against your fuel budget and no-burn windows              1.2 s
✗ Top option rejected — independent check found a new 0.3 km approach            0.8 s
↻ Widened the search after the rejection                                         0.9 s
✓ Verified the new choice against all 3 objects — agreed to within 1 m           1.1 s
🛡 Safety reviewer: APPROVED                                                     0.6 s
```

Non-experts read the summaries. Technical judges click to expand the real tool call and result. Both audiences served by one component. Show the per-step timing — it proves the run is live, and your sub-10-second total is worth displaying.

---

## 6. Provenance line

Small, always visible, phrased as a data sheet rather than a disclaimer:

> Orbit seeded from NORAD 43013, epoch 2026-09-12 12:00 UTC (real) · Conjunction geometry synthetic · Two-body model

See `DATA.md`. A large red SYNTHETIC banner reads as apology; this reads as rigour.

---

## 7. Real-world context panel

A small side panel from the committed SOCRATES CSV:

> **Real conjunctions predicted this week** — 10 rows, real satellite names, real TCA, real miss distance.

Clearly separated from the simulation, no computation. It answers "does this problem actually exist?" before the judge has to ask.

---

## 8. Vocabulary — translate everything

| Never show | Show instead |
|---|---|
| Conjunction | Close approach |
| Minimum separation / miss distance | Closest approach |
| Delta-v / Δv | Fuel used (bar), `Δv` in tooltip |
| Manoeuvre candidate | Option |
| Infeasible | Not allowed by your limits |
| "No feasible candidate in the supported search set" | **No safe option found** (technical phrasing underneath, small) |
| Epoch / TCA | Time, in hours from start |
| Prograde / retrograde | Speed up / slow down |
| Secondary conjunction | Creates a new close approach |

Keep every technical term available on hover or expand. Lead with the plain word.

---

## 9. Do not put on screen

- 3D globes or orbit ellipses as the primary view — misleading, expensive, and your chart is better
- TLE strings, orbital elements, Julian dates, frame names in the main view
- Raw JSON anywhere a judge lands first
- Metres where kilometres read better
- **Collision probability, or anything that implies it.** You are not computing it. A percentage on screen invites the one question you cannot answer.

---

## 10. Layout

**Above the fold, in this order:**
1. Status chip
2. Hero separation chart
3. Constraint text box
4. Options table

**Below:**
5. Agent trace
6. Real-world context panel
7. Approve / reset / export
8. Provenance line

---

## The twenty-second test

Sit someone who knows nothing about satellites in front of it, say nothing, and time them. They should be able to tell you:

1. Something is going to come dangerously close
2. There are options, and one is recommended
3. One option was rejected because it caused a *new* problem

If they cannot get all three from the screen alone with no narration, the chart is wrong — not the explanation.
