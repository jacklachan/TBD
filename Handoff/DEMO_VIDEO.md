# Demo video — shot list and script

Target length about three minutes; check the submission limit and cut section 6
first if you are over. Every number below is one the app shows on screen at that
moment. If the screen says something different on the day, say what the screen
says.

## Before you record

- [ ] **The Space runs `b132826` or later.** The latest commit message on
  https://huggingface.co/spaces/Auenchanters/TBH/tree/main should read
  "Deploy verified application from b132826" (deployed 13 Sep). Older builds
  lack the Tracking and Coordinate tabs.
- [ ] `python scripts/live_api_check.py --base https://auenchanters-tbh.hf.space`
  ends with every check passing. Write down the replan time it prints; you say
  it in section 6.
- [ ] Warm the Space: open it, enter the operator token, run the AI planner once,
  then **Reset case**. The first model call after idle is the slowest.
- [ ] Desktop browser, 1920×1080, zoom 100 %, dark theme, bookmarks bar hidden,
  notifications off, one tab.
- [ ] Enter the operator token **before** you start recording, or cut that part.

If a take goes wrong — HTTP 429, "reviewer unavailable", an unresolved run —
wait a minute, **Reset case**, and retake that section. Do not keep a failed take.

## Which scenario

Record on **"Through a breakup debris stream"** (scenario dropdown, second
entry): the same satellite and first trap, plus 11 fragments from a simulated
breakup and a second trap. Its numbers differ from "The second encounter" in
sections 2–3; the differences are listed inline below as **[stream]**.

**Rehearse the AI planner on it once before recording.** Its live model
behaviour has not been measured — the scenario was added after the last live
run. If the planner does not reach "AI proposal ready" within about a minute on
two tries, record sections 3–6 on "The second encounter" instead; every number
in those sections without a **[stream]** note is from that scenario.

## 0 · Real debris around a real network — 0:00–0:30

**Screen:** Click **Tracking**. Let the three figures land: 213,120 pairs
screened, 1,151 passes under 10 km, closest 105 m. Scroll to **Checked against
CelesTrak SOCRATES**, then to the top row of **Closest passes** and click
**Assess avoidance**: "0.25 m/s slow down, 342 min before · estimated 2.49 km ·
after re-screen closest 2.49 km". Close the panel.

**Say:** "Iridium NEXT carries satellite phone traffic worldwide. We screened
all eighty of its satellites against every tracked fragment from the 2009
Iridium–Cosmos collision and the Fengyun-1C missile test — real element sets,
three and a half days. The closest pass is 105 metres, and CelesTrak's own
published screening lists the same pass to within three hundredths of a
second. The avoidance burn is checked against all 2,664 fragments before it's
offered."

If the Tracking panel is still loading on a freshly started Space, it takes
about fifteen seconds once; open it before recording.

**Optional, if the model is responding well in rehearsal:** click **Run triage
agent** before the passes table and let the brief and triage table appear. Say:
"An agent does the triage — it picks which passes to assess and briefs the
operator; every number in that table comes from the assessment tool." Measured
live on 13 Sep: brief ready in 13.5 s, five passes assessed, no unsupported
figures. Still rehearse once; skip it if a run is slow or unresolved.

## 0b · Two operators, one pass — 15–20 s, optional

**Screen:** Scenario dropdown → **Another operator's satellite** → **Coordinate**
tab. Point at the red line: each plan alone clears it by about 1.47 km, both
together 561.7 m. Then the **Agreed** row: only Orion West burns.

**Say:** "When the other object is someone else's satellite, both operators
dodging can be worse than one. Each plan is safe on its own; together they pass
at 562 metres. Both plans are checked together, and a rule both sides can apply
decides who moves."

## 1 · The problem — 0:30–0:55

**Screen:** Overview, scenario "The second encounter", globe turning. Click the
**Close approach** view: the line between NOAA 20 and DEB-1 reads 133.7 m.

**Say:** "This is NOAA 20, a real weather satellite, seeded from its published
orbit. In the next six hours it passes 133 metres from a piece of debris. Our
floor is a kilometre. The debris is synthetic; the orbit and the geometry are
real physics."

## 2 · The obvious fix is wrong — 0:25–1:00

**Screen:** Click **The hidden conflict** card. Closest approach changes to
523.2 m, status "Verifier rejected". Point at the chart callout
"DEB-2 · 523 m · T+05:38". Click **Close approach** — the line now goes to DEB-2.

**Say:** "The cheapest burn clears that debris by two kilometres. But screening
only checked the object that raised the alarm. An independent verifier rebuilds
the trajectory and screens everything — and the fix now takes us 523 metres from
a second object, five and a half hours later."

**Screen:** Click **The clear alternative**. "Verified clear", closest approach
2.492 km. Switch back to the **Orbit** view.

**Say:** "Twice the fuel clears both."

**[stream]** The clear alternative is instead **0.20 m/s · Prograde · T+30 min**,
closest approach 2.21 km. Before clicking it, open **Maneuvers**: the
0.200 m/s retrograde row `t30_ret_200` reads "Verifier rejected · FRG-09:
477.3 m". Say: "Doubling the burn doesn't save it either — it flies into a
fragment from the breakup. Eleven fragments, every one screened for every
option. The answer is to burn the other way."

## 3 · The agent does the investigation — 1:00–1:30

**Screen:** Click **Run AI planner**. Let the step readout play (≈5 s). The
notice reads "AI proposal ready · … model calls · … s" and the card shows
"AI proposal · reviewer allowed". Open **Evidence** and scroll to the event list:
the model validating `t30_ret_100` → BLOCK, `t30_ret_200` → PASS, then
"Safety reviewer returned ALLOW". Close the panel. **[stream]** `t30_ret_200`
is BLOCK here too; read whatever the trace actually shows — the model's path
varies run to run.

**Say:** "The planner is a language model working through tools. It validated
the cheap option, read why it failed, and moved to one that works. It never
supplies a number and it cannot approve anything — approval is read off the
verifier's result, and a second model reviews the evidence and can veto."

## 4 · Approve, and hand over a record anyone can check — 1:30–2:10

**Screen:** **Inspect proposed trajectory** → **Approve simulated maneuver** →
"Recorded in simulation". Open **Evidence** → **Issue record** →
**Hand it to the other operator** → **Recompute it**: "Its numbers hold".

**Say:** "The decision leaves as a conjunction record carrying the state
vectors, not just the conclusion. The receiving operator recomputes it."

**Screen:** Click in the received record, Ctrl+F `MISS_DISTANCE`, change the
first `2491.888` to `9999`, **Recompute it**: "Its numbers do not hold — the
record claims 9,999.0 m; recomputing from its own state vectors gives
2,491.9 m."

**Say:** "Overstate the clearance and the receiver catches it. Coordination
doesn't need trust if the claim can be checked."

## 5 · Change the rules in plain English — 2:10–2:35

**Screen:** Close the panel. **Reset case**. Type
"We lost a thruster. Halve the fuel budget." → **Preview restriction**. The
dialog shows the budget 0.2 → 0.1. **Confirm & recompute**. The left panel now
reads "Nothing here clears the floor."

**Say:** "An operator changes the brief in plain English. The model only
interprets the sentence; the backend computes the new budget, and nothing
changes until a human confirms."

## 6 · It says so when nothing works — 2:35–3:00

**Screen:** **Run AI planner**. Speed this section up in the edit and put the
real elapsed time on screen (measured live on 13 Sep: 27.9 s — use your own
number). It ends "AI outcome: no approvable option". Open **Evidence**: the last
event is "The independent completion check ruled out every option in this grid."

**Say:** "Under half the budget, every option in the grid is either
unaffordable or unsafe. The agent tries, including designing burns of its own,
and then the verifier checks the whole grid. It reports that nothing works
instead of inventing an answer. That replan took" — *say your number* —
"most of it model thinking time."

**Close on:** the workspace, with the line "Orion West · every number
recomputed, nothing taken on trust."

With section 0 the cut runs to about 3:30. If the limit is three minutes, drop
section 6 and end on the record check in section 4.

## Do not say

- "In under ten seconds" — the replan is not.
- "Collision probability" — none is computed anywhere.
- "Real debris" or "a real conjunction" **about the scenarios** — their debris
  is synthetic. In the Tracking tab the fragments and passes are real public
  data; say "a pass found in public element sets", not "a predicted collision".
- "Iridium will manoeuvre" — the burn is our assessment, not the operator's.
- "SGP4 conjunction analysis" — propagation is two-body from the seed epoch.

## If the Space cannot be redeployed in time

Record locally instead: put an inference-enabled `HF_TOKEN` in `TBD/.env`, then

```bash
npm --prefix frontend run build
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

and open http://127.0.0.1:8000. No operator token is needed on localhost.
