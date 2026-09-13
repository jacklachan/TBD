# Demo video — shot list and script

Target length about three minutes; check the submission limit and cut section 6
first if you are over. Every number below is one the app shows on screen at that
moment. If the screen says something different on the day, say what the screen
says.

## Before you record

- [ ] **The Space runs commit `360e89d` or later.** Check the latest commit message
  on https://huggingface.co/spaces/Auenchanters/TBH/tree/main reads
  "Deploy verified application from 360e89d". The older build has the
  unreadable log chart, zooms the globe when you scroll, and its replan
  can end "unresolved" — do not record on it.
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

## 1 · The problem — 0:00–0:25

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

## 3 · The agent does the investigation — 1:00–1:30

**Screen:** Click **Run AI planner**. Let the step readout play (≈5 s). The
notice reads "AI proposal ready · … model calls · … s" and the card shows
"AI proposal · reviewer allowed". Open **Evidence** and scroll to the event list:
the model validating `t30_ret_100` → BLOCK, `t30_ret_200` → PASS, then
"Safety reviewer returned ALLOW". Close the panel.

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
real elapsed time on screen ("real time: 1 min 30 s" — use your measured
number). It ends "AI outcome: no approvable option". Open **Evidence**: the last
event is "The independent completion check ruled out every option in this grid."

**Say:** "Under half the budget, every option in the grid is either
unaffordable or unsafe. The agent tries, including designing burns of its own,
and then the verifier checks the whole grid. It reports that nothing works
instead of inventing an answer. That replan took" — *say your number* —
"most of it model thinking time."

**Close on:** the workspace, with the line "Orion West · every number
recomputed, nothing taken on trust."

## Do not say

- "In under ten seconds" — the replan is not.
- "Collision probability" — none is computed anywhere.
- "Real debris" or "a real conjunction" — both debris objects are synthetic.
- "SGP4 conjunction analysis" — propagation is two-body from the seed epoch.

## If the Space cannot be redeployed in time

Record locally instead: put an inference-enabled `HF_TOKEN` in `TBD/.env`, then

```bash
npm --prefix frontend run build
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

and open http://127.0.0.1:8000. No operator token is needed on localhost.
