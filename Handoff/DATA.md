# Satellite Demo — data acquisition and provenance

Current specification. Supersedes [reference/DATA.md](reference/DATA.md), which contains a hardcoded catalogue number and example epoch that must not be copied.

**Status:** no snapshot has been downloaded. Acquisition is a build task with named owners.

## Decision

No public dataset provides propagatable state vectors at the fidelity this product needs. Synthetic conjunctions are the correct engineering choice here, not a fallback.

The build uses a **hybrid**: the satellite's initial state is derived from one real catalogue object; both debris objects and every conjunction are synthetic and generated backward with assertions. Real conjunctions appear only in a separate, display-only context panel.

## Snapshot rules

These apply to every external source without exception.

- **Fetch once, commit the file, never call the source again.** No fetch may exist in the runtime or demo path.
- One owner per source. **A fetches the TLE. C fetches the SOCRATES snapshot.** Two builders hitting CelesTrak independently is the likeliest way to get blocked.
- Every snapshot gets a provenance sidecar: source URL, retrieval timestamp UTC, SHA-256 of the file, and any parsed fields.
- If a source fails, stop and record the missing snapshot. Do not retry in a loop.

> CelesTrak refreshes roughly every two hours and enforces a one-download-per-update policy — repeat requests return HTTP 403. Around fifty HTTP errors within two hours triggers a firewall block. Verify the current terms on the documentation page when you fetch; the behaviour above is what was observed on 12 September 2026.

## Source 1 — CelesTrak GP, for the seed state (owner: A)

```
https://celestrak.org/NORAD/elements/gp.php?CATNR=<id>&FORMAT=TLE
```

Parameters: `CATNR`, `GROUP` (uppercase), `INTDES`, `NAME`, `SPECIAL`. Formats include `JSON`, `CSV`, `XML`, `KVN`, `TLE`, `2LE`.

Pick any bound near-circular LEO object inside the supported orbit family. Save the response to `scenarios/seed_tle.txt`, commit it, and stop.

**Parse the identity out of the saved file. Do not hardcode it.**

- NORAD ID comes from the TLE lines, not from a constant in the source.
- Epoch comes from the TLE epoch field, not from a chosen wall-clock time.
- The seed state is SGP4 evaluated **at that parsed epoch**.

Any catalogue number or date written in a specification document — including this one — is illustrative. The committed file is the only authority.

Write `scenarios/seed_provenance.json` with the source URL, retrieval timestamp, file hash, parsed NORAD ID, parsed TLE epoch, the SGP4 invocation used, and the resulting state vector. This populates the `Provenance` model in [CONTRACTS.md](CONTRACTS.md), with `synthetic_conjunction: true`.

`sgp4` is used exactly once, at scenario build time, and never in the request path.

### Frame

SGP4 outputs TEME. The simulation frame is `SIM_ECI_TEME_SEEDED`: fixed simulation axes initialized from that epoch TEME state. The TEME→GCRF transformation is deliberately not performed, because the TEME state is used only as the initial condition of a self-consistent simulation and is never mixed with another frame.

If asked why that is acceptable: TEME precesses on the order of 50 arcsec/year, so over a six-hour horizon the axes rotate roughly 0.034 arcsec — about a metre of absolute displacement at LEO radius — and that rotation is common-mode across all three objects, so it very largely cancels in the relative geometry, which is the only quantity computed. State this as the reasoning, not as a measured bound; if precision matters to a questioner, offer to compute it rather than asserting a figure.

### What the real seed does and does not buy

TLE accuracy is on the order of a kilometre at epoch. The defensible claim is **"the orbit is realistic."** The claim **"this conjunction is real"** is false and must never be made in the UI, the README, the export or the pitch. Subsequent trajectories are a simplified two-body simulation. No real collision probability is computed anywhere in this product.

## Source 2 — CelesTrak SOCRATES Plus, for context only (owner: C)

Real precomputed conjunction reports for the coming week: object names, catalogue numbers, TCA, minimum range, relative speed. RFC 4180 CSV, regenerated a few times daily.

Save to `data/context/socrates_snapshot.csv` with `socrates_provenance.json` alongside. `GET /context/socrates` serves up to ten normalized rows from disk with the source, retrieval and report timestamps.

This panel is **entirely separate from the simulation**. It performs no computation, shares no objects with the scenario, and never feeds the engine. It exists to show the problem class is real. Thirty-minute budget — if it costs more, ship without it.

## Source 3 — ESA Kelvins Collision Avoidance Challenge — evaluated, not used

Genuinely real data: roughly 162,000 CDMs across about 13,000 conjunction events, from US Space Surveillance Network data, released for a 2019 machine-learning competition.

Rejected for two reasons:

- **No absolute state vectors.** The set provides relative position and velocity at TCA, orbital elements and covariances — derived quantities. It cannot be propagated, and a Δv cannot be applied to it and recomputed. It is a probability-prediction dataset, not a simulation dataset.
- **Licensing is unclear.** ESA copyright with a competition-scoped release and no stated general licence. Unsuitable as a dependency for a judged submission.

Keep one sentence about this in the README. Showing that an option was evaluated and declined on stated grounds is worth more than silence.

## Source 4 — Space-Track.org — not viable

Authoritative catalogue and real CDMs, but account approval has unpredictable latency, a redistribution agreement applies, and CDMs are available only for satellites you operate. Out of scope for this event.

## Source 5 — ESA DISCOSweb — statistic only

Object metadata behind a free API token. The tracked-object count already cited in the research is all that is used. No integration.

## Provenance line in the UI

One small line, always visible, phrased as a data sheet rather than a disclaimer. Fields come from `seed_provenance.json` — including the parsed NORAD ID and parsed epoch, never a literal typed into the frontend:

> Orbit seeded from NORAD `<parsed id>`, epoch `<parsed TLE epoch>` (real) · Conjunction geometry synthetic · Two-body model, `SIM_ECI_TEME_SEEDED`

A large red SYNTHETIC banner reads as an apology. A precise provenance line reads as rigour, and it is the honest version.

## Runtime model access

Runtime inference is a separate matter from these data snapshots, and neither is verified yet.

Use the available Gemini key behind the single adapter in `backend/agent/llm.py`. Select the exact model during C's first-thirty-minutes tool-call test rather than committing to a model name in a document. Prefer the faster tier for the planner loop; reserve the stronger tier for policy interpretation if measurement shows it is needed.

Write the five tool declarations by hand as flat dictionaries, and validate returned arguments with the Pydantic models. Generated JSON Schema commonly emits `$ref`, `anyOf` and `additionalProperties`, which the function-calling subset may reject — confirm the supported subset in the smoke test rather than assuming a specific failure.

A low temperature reduces variation in the planner's wording. It does not make model output deterministic, and no document or slide should say that it does. Determinism in this product comes from the numerical path, which is where every displayed number originates.

## Sources

- [CelesTrak GP data formats and API](https://celestrak.org/NORAD/documentation/gp-data-formats.php)
- [CelesTrak SOCRATES Plus](https://celestrak.org/SOCRATES/)
- [ESA Kelvins Collision Avoidance Challenge — data](https://kelvins.esa.int/collision-avoidance-challenge/data/)
