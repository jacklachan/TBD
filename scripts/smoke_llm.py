"""Prove a real model round trip with a real tool call. Builder C's first task.

    export HF_TOKEN=...
    python scripts/smoke_llm.py
    python scripts/smoke_llm.py --model some-other-model

A text-only reply does NOT pass. The point is to prove the model returns
structured function-call arguments and then continues sensibly after being given
a result -- that is the mechanism the whole planner depends on.

Record the model ID that worked, the latency, and every attempt that failed in
Handoff/handoffs/C_AGENT_API.md. Model IDs go stale -- a retired one answers 404
-- so rerun this rather than trusting the default. Every agent test in the suite
runs against ScriptedProvider and proves only that the loop is correct.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.agent.llm import LLMError, Message  # noqa: E402
from backend.agent.huggingface import HuggingFaceProvider  # noqa: E402
from backend.config import planner_model  # noqa: E402
from backend.agent.tools import DECLARATIONS, TOOL_BRIEFING  # noqa: E402

SYSTEM = (
    "You help a satellite operator. Use the tools available to you. "
    "Call get_case_briefing first to read the case."
)


def main() -> int:
    # Provider prose can contain Unicode on Windows terminals using cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=None,
        help="defaults to PLANNER_MODEL, then the built-in default in backend/config.py",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()
    model = args.model or planner_model()

    try:
        provider = HuggingFaceProvider(model=model, temperature=args.temperature)
    except LLMError as exc:
        print(f"FAIL  {exc}")
        return 2

    tools = [DECLARATIONS[TOOL_BRIEFING]]
    print(f"model      {model}")
    print(f"tool       {TOOL_BRIEFING}")
    print(f"schema     {json.dumps(tools[0]['parameters'])}")
    print()

    # Step 1 -- does it ask for the tool?
    messages = [Message(role="user", text="What is the situation with this satellite?")]
    try:
        first = provider.call(SYSTEM, messages, tools)
    except LLMError as exc:
        print(f"FAIL  step 1 request rejected: {exc}")
        print("      A 400 here usually means an unsupported schema construct.")
        return 1

    print(f"step 1     {first.latency_ms:.0f} ms, usage {first.usage or '{}'}")
    if not first.wants_tool:
        print("FAIL  model replied with text instead of a function call:")
        print(f"      {first.text[:300]}")
        print("      A text-only reply does not prove tool calling.")
        return 1

    call = first.tool_calls[0]
    print(f"           requested {call.name}({json.dumps(call.arguments)})")
    if call.name != TOOL_BRIEFING:
        print(f"FAIL  expected {TOOL_BRIEFING}, got {call.name}")
        return 1

    # Step 2 -- does it use a result we hand back?
    fake_result = {
        "if_nothing_is_done": {
            "closest_approach_m": 133.7,
            "at_t_s": 16234.3,
            "object_id": "DEB-1",
            "acceptable": False,
        },
        "policy": {"max_delta_v_mps": 0.2, "min_separation_m": 1000.0},
    }
    messages.append(Message(role="model", text=first.text, tool_call=call))
    messages.append(
        Message(role="tool", name=call.name, result=fake_result, call_id=call.call_id)
    )

    try:
        second = provider.call(SYSTEM, messages, tools)
    except LLMError as exc:
        print(f"FAIL  step 2 continuation rejected: {exc}")
        return 1

    print(f"step 2     {second.latency_ms:.0f} ms, usage {second.usage or '{}'}")
    reply = second.text or (
        f"[requested {second.tool_calls[0].name}]" if second.wants_tool else ""
    )
    print(f"           {reply[:300]}")

    if not reply:
        print("FAIL  no usable continuation after the tool result")
        return 1

    total = first.latency_ms + second.latency_ms
    print()
    print(f"PASS  request -> function call -> result -> continuation, {total:.0f} ms total")
    print(f"      Record model={model}, latency={total:.0f} ms in C_AGENT_API.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
