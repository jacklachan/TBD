# Deploying to Hugging Face Spaces

Docker SDK, one container, port 7860.

## 1. Space README frontmatter

Spaces reads configuration from YAML frontmatter at the very top of `README.md`. Add this block before anything else, or the Space will not build:

```yaml
---
title: Orion West
emoji: 🛰️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---
```

## 2. The API key

**Never commit it.** In the Space, go to *Settings → Variables and secrets → New secret*:

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | your key |
| `DESK_ACCESS_TOKEN` | a long random operator token; required for remote API access |

Secrets arrive as environment variables. `backend/config.py` reads the environment first and only falls back to `.env`, so a Space secret wins and no code changes.

Optional variables, if the model ID moves again:

| Name | Default |
|---|---|
| `PLANNER_MODEL` | `gemini-3.6-flash` |
| `REVIEWER_MODEL` | `gemini-3.6-flash` |
| `DESK_DB` | `:memory:` |
| `ALLOWED_ORIGINS` | local dev servers; set to `none` for a single container |

Check it landed: `GET /health` reports `"model_access": true` when a key is visible. If that is false, the Space will still build and serve, and every plan will end as an unresolved case — a symptom worth recognising quickly.

## 3. Three things about Spaces that affect this app

**The filesystem is ephemeral.** Anything written outside persistent storage disappears on restart or rebuild. `DESK_DB` therefore defaults to `:memory:`, which is honest about what you get. If you attach persistent storage, set `DESK_DB=/data/desk.sqlite`. Do not point it at a path in the image — it will look like it works until the first restart.

**The case store is bounded and self-clearing.** Every page load opens a case, so the store would otherwise grow without limit or stop accepting new ones. At its cap it retires the oldest cases nobody acted on; a case with an execution is the record of a simulated decision and is kept regardless of age. Nothing here is a durable record, so this costs nothing and stops the workspace dying after a few hundred visits.

**One worker, deliberately.** Run state lives in memory in `AppState.runs`. A second worker would answer `GET /runs/{id}` for runs it has never seen, and the UI would poll forever. The `Dockerfile` pins `--workers 1`. If you ever need more, make runs durable first; do not just raise the number.

**Free CPU Spaces sleep** after inactivity and take some seconds to wake. The first request after a sleep is slow through no fault of the app. If you are demoing live, wake it a minute beforehand.

## 4. Frontend

The Dockerfile builds `frontend/dist/` with Node 24 and `npm ci`, then copies it into the Python image. The API serves it from the same origin. `.dockerignore` excludes credentials, local environments, databases, dependencies, test output and the handoff packet. The final container needs only Python at runtime.

`/assets` is mounted for the built bundle and every unmatched path returns `index.html`, so a client-side router works. The catch-all is registered after the API routes, so it cannot shadow them.

## 5. Push

```bash
git remote add space https://huggingface.co/spaces/<user>/<space-name>
git push space main
```

Data files are committed and needed at runtime: `scenarios/*.json`, `scenarios/seed_tle.txt`, `data/context/socrates_snapshot.csv`. The app never fetches CelesTrak at runtime, so the Space needs no outbound access to it — only to the Gemini endpoint.

## 6. Check the deployment

```bash
python scripts/live_api_check.py --base https://<user>-<space-name>.hf.space
```

Twenty checks covering create, plan, visualization, a plain-English constraint change, confirm, replan, approve twice, export and context. It exercises the live model, so expect it to take a minute or two.

For protected deployments, set `DESK_ACCESS_TOKEN` in the checker's environment too. It is sent in the Authorization header and is not printed or added to the URL. This session verified the built frontend served by FastAPI locally; a Docker image build was not run because the local Docker daemon was unavailable.

## Before this is public

- **CORS is already narrowed.** Unset, it permits local dev servers only. Serving the frontend from the same Space? Set `ALLOWED_ORIGINS=none` and no CORS headers are sent at all. Calling from somewhere else? Name that origin explicitly. There is no wildcard option, on purpose: this API spends a paid model quota.
- **API access uses `Authorization: Bearer <DESK_ACCESS_TOKEN>`.** Remote API requests fail closed when no token is configured. Health and static assets remain public. Use TLS; share the operator token only with your team. Model operations are capped at four concurrent requests, one plan per case, and request bodies at 16 KiB. These bounds are not a per-user quota or a time-based rate limiter.
- Model calls dominate latency — around 15 s for a full plan. Stream events into the trace so the page is never blank.
