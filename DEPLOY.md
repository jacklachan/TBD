# Deploy Orion West on Hugging Face

Target Space: https://huggingface.co/spaces/Auenchanters/TBH

Use **Docker / Blank**, **CPU Upgrade (8 vCPU / 32 GB RAM)**, port **7860**.
The Dockerfile builds the React/Three.js frontend and serves it through FastAPI,
with one Uvicorn worker. The AI runs remotely; no server GPU or model download
is needed. The judge's browser renders the 3D scene.

## Account and hardware

Creating a personal Docker Space currently requires PRO. Upgraded hardware
billing does not replace that account requirement. CPU Basic (2 vCPU / 16 GB)
is the minimum tier to evaluate; the user selected CPU Upgrade for this Space.
At the time of this session it is listed at $0.03/hour. These are sizing
recommendations, not deployed load-test results.

Check [hardware prices](https://huggingface.co/docs/hub/spaces-gpus) and
[Space creation requirements](https://huggingface.co/docs/hub/spaces-overview).

## Model and secrets

The user selected **zai-org/GLM-5.3-Flash:baseten** through the Hugging Face
Inference Providers router. Hugging Face authenticates/bills the calls and
Baseten serves the model. Both the planner and independent reviewer use it.
There is no Gemini fallback.

Add these in Space Settings -> Variables and secrets as **secrets**:

| Secret | Value |
|---|---|
| HF_TOKEN | Persistent fine-grained token with Inference -> Make calls to Inference Providers permission |
| DESK_ACCESS_TOKEN | Long random secret that gates the API. With sign-in on, judges never see or type it |
| DESK_ADMIN_USER | Sign-in name. Defaults to `Paan` |
| DESK_ADMIN_PASSWORD | Sign-in password. Defaults to `Banaras` |

Create the token at https://huggingface.co/settings/tokens. Repository write
permission is unnecessary for runtime inference. Deployment uses separate
Hub credentials. A temporary CLI OAuth access token is not a permanent Space
secret. Keep secrets out of Git, frontmatter, public variables and browser code.

Optional public **variables**:

| Variable | Value |
|---|---|
| PLANNER_MODEL | zai-org/GLM-5.3-Flash:baseten |
| REVIEWER_MODEL | zai-org/GLM-5.3-Flash:baseten |
| HF_BASE_URL | https://router.huggingface.co/v1 |
| ALLOWED_ORIGINS | https://auenchanters-tbh.hf.space |
| DESK_DB | :memory: |

The explicit application origin is required behind the Space's HTTPS proxy.
Using `none` rejected browser requests even though direct API calls succeeded.
The deployment helper reads the exact application host from the Hub API.

A dedicated HF Inference Endpoint is a separate product. If used instead, set
HF_BASE_URL to its HTTPS /v1 base and both model variables to its served model ID.
The app Space still needs CPU only; dedicated-model GPU sizing depends on the model.

GET /health reports credential presence, not quota or successful inference.
HTTP 402 means inference billing needs funding; 401/403 means credentials or
permissions need checking. These failures never create approval evidence.

## Build and publish

1. npm --prefix frontend ci
2. npm --prefix frontend run build
3. Run the backend/unit/browser checks recorded in the current Handoff session.
4. Configure the Space's secrets, then upload tracked application/build inputs.
5. Read build/runtime logs and verify the actual 3D and model workflows.

Do not upload the working folder wholesale. .dockerignore excludes secrets from
the image, but does not exclude them from a Hub upload. Exclude .env, databases,
Handoff archives, dependency folders, test output and Git metadata from uploads.
The deployment script prepares tracked inputs explicitly and checks for secrets.

After committing the verified source, publish with:

```bash
uv run --no-project --python 3.12 --with huggingface_hub python scripts/deploy_space.py --space Auenchanters/TBH
```

A teammate redeploying code should use `--code-only`, which uploads files and leaves every
Space secret and variable untouched (without it, a missing local DESK_ACCESS_TOKEN rotates the
operator password). Otherwise, without the inference token, add `--keep-space-hf-token`
and puts a write token for the Space's account in `.env` as `HF_DEPLOY_TOKEN`, never as `HF_TOKEN`.

The helper uploads with HF_DEPLOY_TOKEN (environment or the ignored local .env) when set, otherwise the CLI login; it copies HF_TOKEN into a Space
secret, and generates DESK_ACCESS_TOKEN in the ignored local `.env` if needed.
Use the latter value at the website's Operator access prompt.

Local model proof: python scripts/smoke_llm.py must request a real function and
consume its result. With the API running, use:

```bash
python scripts/live_api_check.py --base https://auenchanters-tbh.hf.space
```

The checker needs the same DESK_ACCESS_TOKEN in its environment or local ignored
.env. Record real plan/replan timings and failed attempts. Ten seconds is a
full-agent workflow target, not an established guarantee.

## Runtime limits

- Keep one worker: run progress lives in process memory.
- Default cases/memory disappear on restart. Export decisions before rebuilding.
  Durable SQLite requires suitable persistent storage, a separate setup decision.
- The case store is bounded; it retains simulated executions preferentially.
- Remote API requests require the operator token; assets and health are public.
  There is a concurrency cap, but no per-user billing allowance.
- Frozen datasets are bundled. There are no runtime CelesTrak calls.
- Docker/HF build results must be verified separately from local Python tests.


## Signing in

When `DESK_ACCESS_TOKEN` is set, the page shows a name and password instead of a
token field. Signing in mints a **separate** session token, so the Space secret
itself never reaches a browser, a screenshot or a screen share, and a session
expires after twelve hours.

Defaults are `Paan` / `Banaras`; override with `DESK_ADMIN_USER` and
`DESK_ADMIN_PASSWORD`.

**Be clear-eyed about what this is.** It is a convenience gate over a shared
demo login whose defaults are in this repository, so anyone who can read the
repository can sign in. It protects the *token*, not the *application*. What it
genuinely buys is that the secret stays on the server, sessions expire, and
failed attempts are rate limited so the endpoint is not a free password oracle.
For anything beyond a judged demo, replace it with an identity provider rather
than extending it.

With no token configured the form does not appear and the API is open, which is
the right behaviour for `localhost` and the wrong one for a public URL — so set
the token before deploying.
