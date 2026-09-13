# Tracking completeness, decision triage, and demo hardening

13 September 2026. Branch `claude/focused-brown-5r09go`, three commits on top of
`0f91958`. All work is in this checkout; **`origin` rejects the push with 403**
(see *Delivery* below), so the change ships as a patch.

**Result: 394 Python tests and 7 frontend tests pass. `scripts/diagnose.py`
reports no failures.** Test count went 383 → 394; the eleven new tests are all
in `tests/test_tracking.py`.

---

## 1. The screen could not substantiate its main claim

A screen's finding is not the list it prints. It is the **absence of everything
else** — the assertion that no pass under the report threshold slipped between
two one-minute samples. That assertion rested on two unchecked assumptions.

### The capture radius was sized from a guess

`MAX_RELATIVE_SPEED_KMS = 16.0` was a hardcoded constant with the comment
"head-on in LEO is about 15.5 km/s". The capture radius is
`report_km + MAX_RELATIVE_SPEED_KMS × step/2` = 490 km. If any pair could close
faster than 16 km/s, a conjunction would pass between two samples and simply
never be found — and the screen would report a clean list anyway.

For the committed catalogue the constant happens to hold. **It is not derived,
so nothing would have caught the case where it does not.** A fragment in a more
eccentric orbit has a higher perigee speed; a 300 × 20,000 km orbit reaches
~9.8 km/s, which head-on against a 7.7 km/s satellite is 17.5 km/s — past the
constant, and silently under-captured.

The bound is now computed from the element sets actually loaded
(`_capture_speed_bound`): perigee speed from mean elements
(`sqrt(mu(1+e)/(a(1-e)))`) for the fastest protected satellite and the fastest
fragment, summed, plus a margin.

| | |
|---|---|
| Fastest protected satellite | 7.544 km/s (IRIDIUM 178) |
| Fastest fragment | 7.951 km/s (FENGYUN 1C DEB, e = 0.138) |
| Derived bound + margin | **15.745 km/s** |
| Old constant, kept as a floor | 16.0 km/s |
| Applied | 16.0 km/s (the floor; radius unchanged for this catalogue) |

The old constant stays as a **floor**, so the radius can only ever widen. A
catalogue with faster objects now widens it automatically instead of dropping
passes.

**Why there is a margin.** The bound is computed from *mean* elements; SGP4
returns *osculating* state, whose speed rides slightly above it on short-period
J2 terms. Measured over a full revolution of all 2,744 catalogue objects that
excess peaks at **4.98 m/s** and sits at 1.3 m/s median. `SPEED_BOUND_MARGIN_KMS
= 0.25` covers it fifty times over. This was found by a test that asserted the
per-object function was an upper bound on SGP4 and failed by 5.3 m/s — the test
was wrong, not the code, and both were corrected to state the real property.

### Neither assumption was measured

Both are now measured against what the propagator actually produced, and both
ship in a `completeness` block on `GET /tracking/screen`:

| Check | Allowed for | Observed | Headroom |
|---|---|---|---|
| Head-on closure | 16.0 km/s | 15.486 km/s | 0.514 km/s |
| Straight-line estimate error | 10 km margin | **26 m** | 9.974 km |

The linear error is measured on **every** refined candidate (3,573 of them), in
or out, because it is that margin which decides what never gets refined at all.

A run that cannot substantiate either reports `status: "INCOMPLETE"` with a
`shortfall` naming which, rather than printing a clean list. It does not raise —
the screen still returns its findings, it just stops claiming they are all of
them.

> The 10 km margin was left at 10 km. Measured worst case is 26 m, so it could
> be tightened ~390× for a faster screen — but tightening a safety margin to fit
> the data it was measured on is exactly the mistake this whole section is about.
> 17.6 s for 213,120 pairs is acceptable.

---

## 2. The output answered the wrong question

Conjunctions were sorted by miss distance. That is how you write a report, not
how you run a console.

- Closest pass in the catalogue: **IRIDIUM 170 at 105 m** — and **72.7 hours
  away**. There is no hurry.
- Pass that actually needs an answer: **IRIDIUM 123 at 4.557 km** — **six
  minutes** before the last burn that can still be placed.

Sorted by miss, the second one is 40+ rows down.

What separates them is not how close the objects come, it is whether a burn can
still be placed. So the measure is taken from the avoidance planner itself:
`LEAD_HALF_ORBITS = (1, 3, 5, 7)` — it designs burns a whole number of
half-orbits ahead, and `_triage` counts how many of those placements are still
in the future.

Each conjunction now carries `posture` (ACTIONABLE / NARROWING / TOO_LATE),
`lead_hours`, `decide_in_hours`, `decide_by_utc`, and `burn_slots_open`.

**The queue orders on the deadline, not on the approach.** These are different
orderings, and the difference is the entire point: the last usable slot differs
per pass, so a *later* approach can carry an *earlier* deadline. IRIDIUM 123 is
6.0 h out with 4/4 slots open and 6 minutes to decide; IRIDIUM 166 is 3.2 h out
with 2/4 slots open and 40 minutes to decide. My first implementation sorted by
`lead_hours` and got this backwards; the test
`test_a_later_approach_can_carry_the_earlier_deadline` pins it.

Current catalogue: 307 passes under 5 km — 293 ACTIONABLE, 11 NARROWING, 3
already past their last burn.

**No probability is computed or implied anywhere.** Public element sets carry no
covariance. These fields order a queue; they do not score a risk. That
constraint is stated in the code, in the API payload's `basis` string, and on
screen.

---

## 3. Demo surface

**The separation chart led with the method, not the finding.** "Distance is the
evidence" → *"Vetoed: the ranked-first burn came 523 m from another object. The
floor is 1,000 m. A different burn holds 2.5 km and is what gets proposed."*

The verdict is read off the verifier's own `below_floor` flag, never re-derived
from the plotted series — the chart clips and resamples, and a heading that
disagreed with the validation would be worse than no heading. The floor is
quoted in the same unit as the breach; "523 m … 1 km" made the reader do the
conversion the sentence exists to spare them.

**The tracking panel** now opens with the closest-vs-soonest comparison in plain
words, then the decision queue, then a section on *why the passes that are not
listed are not listed* (capture radius, closure allowed for, closure observed,
margin used). The closest-first table is kept below, labelled as the leaderboard
it is.

Two signalling bugs found in my own first pass and fixed: the urgency dot
coloured `posture` rather than the deadline, so it showed red for an 8-minute
deadline and amber for a 6-minute one — contradicting the row order; and the
ACTIONABLE label read "Room to plan" directly beside "6 min". Now "All burns
open", with colour keyed to the deadline.

Verified in Chromium at 1440×960 and 390×844: `scrollWidth` equals viewport at
both, no console errors, both headings render from live data.

---

## 4. The walkthrough page could hang on a spinner

`demo/index.html` is the offline fallback. Two failures it could not take:

1. **An exception inside `buildGL` escaped to `boot()`**, which stopped before
   drawing anything — spinner up forever, no numbers, nothing. The trigger is
   not hypothetical: a captive portal answers a request for `three.min.js` with
   an HTML login page, and a partial download leaves a `THREE` object that is
   present but broken. The call is now wrapped; the globe is the optional half
   of the page and the content below renders regardless.
2. **The fallback blamed the browser** — "your browser could not start WebGL" —
   when the real cause was an unreachable CDN. Wrong diagnosis sends a judge to
   fix the wrong problem. The two causes are now distinguished.

Verified with `cdnjs.cloudflare.com` and both font hosts blocked: loader clears,
message accurate, 5,890 characters of content render. Verified again with a
deliberately broken `THREE`: same.

> **Not fixed:** `three.min.js` still comes from cdnjs. Vendoring it would make
> the page fully offline, but this sandbox's egress proxy returns 403 on cdnjs
> so I could not fetch the file. To do it yourself:
> ```
> curl -o demo/three.min.js https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
> # then in demo/index.html change the script src to "three.min.js"
> ```
> The page is safe without this — it just loses the globe offline.

---

## 5. What still needs doing — requires you, not this environment

### Run the live model check (blocking for the AI half of the demo)

`scripts/smoke_llm.py` and `scripts/live_api_check.py` **have never been run
against a live model in any session.** `/health` currently reports
`model_access: false`. Two independent reasons, both outside this sandbox:

- No `hf_` token is present.
- `router.huggingface.co` is blocked by the egress proxy (403 on CONNECT,
  confirmed directly).

```bash
export HF_TOKEN=hf_xxxxxxxxxxxx          # Inference Providers permission
python scripts/live_api_check.py         # reachability + auth
python scripts/smoke_llm.py              # one real planner turn end to end
```

Do this **before** the demo, not during it. Until it passes, treat the AI
planner as unverified. The numerical spine does not depend on it: the planner
button disables itself with "Set HF_TOKEN on the server to enable AI. Numerical
controls remain available", and the brief panel shows "AI offline".

### Rotate the pasted token

A token was pasted into chat in an earlier session. **Treat it as compromised
and rotate it.** It was never written to any file in this repository, and
nothing in this branch contains a credential.

### Rehearse the opening

The two strongest beats, in order:

1. **Tracking → "Decide first".** "The closest thing in this catalogue is 105
   metres away and it is three days out. The one that needs an answer is four
   and a half kilometres away and you have six minutes, because a burn is only
   placeable a whole number of half-orbits ahead and the last one is about to
   go by. Closest is not the same as soonest, and neither is the same as most
   urgent."
2. **The veto.** "The search ranked this burn first. The verifier rebuilt it
   from the raw scenario, independently, and threw it out: 523 metres from a
   second object, against a 1,000 metre floor. The model never supplied that
   number and cannot overrule it."

Then *"why the passes that are not listed are not listed"* if there is time —
that is the part no one else will have.

### First load takes 17.6 s

`cached_screen()` screens 213,120 pairs on first call. `warm_tracking=True` is
set on the module-level app, so `python -m uvicorn backend.api:app` absorbs it
in a startup thread. **Start the server well before demoing** and confirm
`curl localhost:8000/tracking/screen` returns 200 before you need it.

---

## Delivery

`git push` to `origin` returns **403 — "Claude doesn't have GitHub access to
jacklachan/orionwest for your organization"** (~10 attempts across sessions,
re-checked after the rename from `TBD` on 13 September; the rename does not
change it). The
three commits are delivered as patch files instead, verified to apply cleanly
against `origin/main` with `git apply --check` in a throwaway worktree.

```bash
git checkout -b claude/focused-brown-5r09go origin/main
git am 000*.patch
```

## Changed paths

```
backend/tracking.py                          derived capture bound, completeness, triage
tests/test_tracking.py                       +11 tests
frontend/src/contracts.ts                    TrackedTriage, TrackingCompleteness
frontend/src/components/TrackingPanel.tsx    decision queue, completeness section
frontend/src/components/SeparationChart.tsx  veto-first heading
demo/index.html                              boot guard, accurate fallback diagnosis
```

No contract was changed in a breaking direction: `completeness` and `triage` are
additions, and `triage` on `TrackedConjunction` is omitted from the avoidance
assessment's copy (which does not carry it) via
`Omit<TrackedConjunction, "element_age_days" | "triage">`.

## Commands run

| Command | Result |
|---|---|
| `python -m pytest -q` | **394 passed**, 138 s |
| `npm test` (frontend) | **7 passed** |
| `npx tsc --noEmit` | clean |
| `npm run build` | built, 1.15 s |
| `python scripts/diagnose.py` | no failures; 2 warnings (no HF_TOKEN, server not running) |
| Chromium 1440×960 / 390×844 | no overflow, no console errors |
| Chromium, all external hosts blocked | page renders, fallback accurate |
| `scripts/smoke_llm.py` | **not run — impossible here, see §5** |
