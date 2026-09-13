"""HF chat-completions transport: no network calls and no real token in tests."""
import json
from types import SimpleNamespace

import pytest

from backend.agent.llm import LLMError, Message, ToolCall


def test_hf_default_never_uses_a_gemini_key(monkeypatch):
    from backend.config import has_model_access, planner_model
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-test-key")
    assert not has_model_access()
    assert "gemini" not in planner_model()


def test_hf_tool_roundtrip_uses_bearer_auth_and_matching_call_ids(monkeypatch):
    from backend.agent.huggingface import HuggingFaceProvider
    seen = []
    payloads = [
        {"choices": [{"finish_reason": "tool_calls", "message": {
            "content": None, "reasoning": "private reasoning is not application output",
            "tool_calls": [{"id": "call_hf1", "type": "function", "function": {
                "name": "get_case_briefing", "arguments": "{}"}}],
        }}], "usage": {"total_tokens": 42}},
        {"choices": [{"finish_reason": "stop", "message": {"content": "Investigate the close approach."}}]},
    ]

    def post(url, **kwargs):
        seen.append((url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: payloads.pop(0))

    monkeypatch.setattr("backend.agent.huggingface.requests.post", post)
    provider = HuggingFaceProvider(api_key="hf_unit_test_only", model="test/model")
    tools = [{"name": "get_case_briefing", "description": "Read case", "parameters": {"type": "object", "properties": {}}}]
    first = provider.call("Use tools", [Message(role="user", text="Read case")], tools)
    assert first.text == ""
    assert first.tool_calls[0].arguments == {}
    second = provider.call("Use tools", [
        Message(role="user", text="Read case"),
        Message(role="model", tool_call=first.tool_calls[0]),
        Message(role="tool", name="get_case_briefing", call_id="call_hf1", result={"status": "ready"}),
    ], tools)
    assert second.text == "Investigate the close approach."
    url, request = seen[-1]
    assert url == "https://router.huggingface.co/v1/chat/completions"
    assert "hf_unit_test_only" not in url
    assert request["headers"]["Authorization"] == "Bearer hf_unit_test_only"
    assert request["json"]["tools"][0]["function"] == tools[0]
    assert request["json"]["parallel_tool_calls"] is False
    history = request["json"]["messages"]
    assert history[-2]["tool_calls"][0]["id"] == history[-1]["tool_call_id"] == "call_hf1"
    assert json.loads(history[-1]["content"]) == {"status": "ready"}
    assert "private reasoning" not in json.dumps(history)


@pytest.mark.parametrize("message,finish", [
    ({"content": None}, "stop"),
    ({"content": "unfinished"}, "length"),
    ({"tool_calls": [{"id": "c", "function": {"name": "x", "arguments": "bad json"}}]}, "tool_calls"),
    ({"tool_calls": [{"id": "c", "function": {"name": "x", "arguments": "[]"}}]}, "tool_calls"),
    ({"tool_calls": [{"function": {"name": "x", "arguments": "{}"}}]}, "tool_calls"),
    # Two calls in one turn is no longer an error: GLM does it despite
    # parallel_tool_calls=false, and the planner now runs them in order.
])
def test_hf_unusable_reply_is_an_explicit_error(message, finish):
    from backend.agent.huggingface import HuggingFaceProvider
    provider = HuggingFaceProvider(api_key="unit-test")
    with pytest.raises(LLMError):
        provider._parse({"choices": [{"message": message, "finish_reason": finish}]}, 1.0)


def test_hf_auth_failure_does_not_retry_or_expose_token(monkeypatch):
    from backend.agent.huggingface import HuggingFaceProvider
    calls = []
    def post(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(status_code=401, text="invalid hf_unit_test_only")
    monkeypatch.setattr("backend.agent.huggingface.requests.post", post)
    with pytest.raises(LLMError, match="401") as exc:
        HuggingFaceProvider(api_key="hf_unit_test_only").call("", [], [])
    assert "hf_unit_test_only" not in str(exc.value)
    assert len(calls) == 1


def test_hf_accepts_dedicated_https_endpoint_but_not_insecure_token_transport():
    from backend.agent.huggingface import HuggingFaceProvider
    assert HuggingFaceProvider(api_key="unit-test", base_url="https://example.endpoints.huggingface.cloud/v1").base_url.endswith("/v1")
    with pytest.raises(LLMError, match="HTTPS"):
        HuggingFaceProvider(api_key="unit-test", base_url="http://untrusted.example/v1")
