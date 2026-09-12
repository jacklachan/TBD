"""Browser integration fixture only. Never imported by the production app.

Run from the repo: python frontend/e2e/scripted_server.py
No key, no remote model calls. Numeric search and verification remain real.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent.llm import ScriptedProvider, text_reply, tool_call
from backend.agent.tools import TOOL_PROPOSE_POLICY
from backend.api import create_app
from backend.store import Store
from fastapi import Request
import uvicorn


class BrowserProvider:
    def __init__(self):
        self.planner = ScriptedProvider([
            tool_call("validate_proposal", candidate_id="t30_ret_100"),
            tool_call("validate_proposal", candidate_id="t30_ret_200"),
            text_reply("Recommend the independently verified alternative."),
        ])

    def call(self, system, messages, tools):
        if any(t["name"] == TOOL_PROPOSE_POLICY for t in tools):
            return tool_call(TOOL_PROPOSE_POLICY, budget_scale=.5)
        return self.planner.call(system, messages, tools)


app = create_app(
    store=Store(), provider_factory=BrowserProvider,
    reviewer_factory=lambda: ScriptedProvider([text_reply('{"decision":"ALLOW","reason_codes":["OK"],"rationale":"Independent evidence passes."}')]),
)


@app.middleware("http")
async def mark_scripted_fixture(request: Request, call_next):
    if request.url.path == "/health":
        from fastapi.responses import JSONResponse
        return JSONResponse({"status": "ok", "model_version": "two-body-universal-variable-1", "planner_model": "SCRIPTED_BROWSER_TEST", "model_access": True, "access_token_required": False})
    return await call_next(request)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
