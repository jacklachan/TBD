# Deploying to Hugging Face Spaces

Docker SDK, one container, port 7860.

## 1. Space README frontmatter

Spaces reads configuration from YAML frontmatter at the very top of `README.md`. Add this block before anything else, or the Space will not build:

```yaml
---
title: Satellite Demo
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

Secrets arrive as environment variables. `backend/config.py` reads the environment first and only falls back to `.env`, so a Space secret wins and no code changes.

Optional variables, if the model ID moves again:

| Name | Default |
|---|---|
| `PLANNER_MODEL` | `gemini-3.6-flash` |
| `REVIEWER_MODEL` | `gemini-3.6-flash` |
| `DESK_DB` | `:memory:` |

Check it landed: `GET /health` reports `"model_access": true` when a key is visible. If that is false, the Space will still build and serve, and every plan will end as an unresolved case — a symptom worth recognising quickly.

## 3. Three things about Spaces that affect this app

**The filesystem is ephemeral.** Anything written outside persistent storage disappears on restart or rebuild. `DESK_DB` therefore defaults to `:memory:`, which is honest about what you get. If you attach persistent storage, set `DESK_DB=/data/desk.sqlite`. Do not point it at a path in the image — it will look like it works until the first restart.

**One worker, deliberately.** Run state lives in memory in `AppState.runs`. A second worker would answer `GET /runs/{id}` for runs it has never seen, and the UI would poll forever. The `Dockerfile` pins `--workers 1`. If you ever need more, make runs durable first; do not just raise the number.

**Free CPU Spaces sleep** after inactivity and take some seconds to wake. The first request after a sleep is slow through no fault of the app. If you are demoing live, wake it a minute beforehand.

## 4. Frontend

If `frontend/dist/` exists in the image, the API serves it from the same origin — one container is the whole app, and CORS stops mattering. Build it before pushing, or add a build stage to the `Dockerfile`.

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

## Before this is public

- **Narrow CORS.** `create_app` currently allows every origin, which is right for a dev server and wrong for a deployment. If the frontend is served from the same Space, you can drop the middleware entirely.
- **There is no auth and no rate limiting.** Anyone with the URL can spend your Gemini quota. For a judged demo that is usually fine; know that it is true.
- Model calls dominate latency — around 15 s for a full plan. Stream events into the trace so the page is never blank.
