# Right of Way — standalone walkthrough

A single-page explainer of the decision this project makes: a satellite is on
course to pass 133.7 m from a tracked object, and something has to move.

It is deliberately **separate from the application**. Nothing here imports from
`backend/` or `frontend/`, and nothing in those directories imports from here.
Serving, building or deleting this folder has no effect on either.

## Running it

Any static server, or open `index.html` directly:

```
python -m http.server 8080 --directory demo
```

Two external resources load from a CDN — Three.js r128 and two Google fonts.
Without network access the page still works: WebGL is skipped with a visible
notice, the fonts fall back, and every number and chart still renders.

## Where the numbers come from

`data.js` is **generated**, not authored. It is one export of the same
computation the application performs: 761 samples across the six-hour horizon,
three candidate manoeuvres, and the validated encounter for each.

Regenerate it by running the search and the verifier over `scenarios/primary.json`
and serialising `t_s`, per-object positions, `pair_separations_m`,
`min_to_any_m` and each `ValidationResult`. Every encounter time in the export
is an exact member of the shared time grid, which is what lets the page report a
minimum rather than interpolate one.

## What is real and what is not

| | |
|---|---|
| The seed orbit | **Real** — NOAA 20 (JPSS-1), catalogue number 43013 |
| Debris population figures | **Real** — ESA Space Debris Office; ISS manoeuvre threshold from NASA conjunction assessment practice |
| Both debris objects, every encounter | **Simulated** — constructed backwards from a chosen encounter, verified by forward propagation |
| Every distance shown | **Computed** — two-body, instantaneous impulses, 6 h horizon |

No collision probability is computed anywhere, here or in the application: that
needs covariance data this model does not carry.
