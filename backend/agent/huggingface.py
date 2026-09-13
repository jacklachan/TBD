"""Hugging Face chat completions for the existing tool loop.

The default routes through HF Inference Providers. HF_BASE_URL can instead point
to a dedicated HF endpoint's HTTPS /v1 API. No model weights or GPU are needed
in the application Space. Provider reasoning fields are never stored or shown.
"""
from __future__ import annotations

import json
import time
from urllib.parse import urlsplit

import requests

from backend.agent.llm import LLMError, LLMResponse, Message, ToolCall, RETRYABLE_STATUS
from backend.config import hf_api_token, hf_base_url, planner_model


class HuggingFaceProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, temperature: float = 0.0,
                 timeout_s: float = 75.0, max_attempts: int = 3):
        # GLM-5.3-Flash thinks before it answers, and a long tool-loop turn has
        # been observed past 30 s; a transport timeout there surfaced as an
        # UNRESOLVED run rather than a slow one. Three attempts absorb the
        # provider's occasional 429 without spending a whole run on it.
        self.model = model or planner_model()
        self.name = f"huggingface:{self.model}"
        self._token = api_key or hf_api_token()
        self.base_url = (base_url or hf_base_url()).rstrip("/")
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.max_attempts = max(1, max_attempts)
        parsed = urlsplit(self.base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise LLMError("HF_BASE_URL must be an HTTPS API base URL without credentials or query parameters.")
        if not self._token:
            raise LLMError("HF_TOKEN is not set. Add a Hugging Face token with Inference Providers permission as a server secret.")

    @staticmethod
    def _messages(system: str, messages: list[Message]) -> list[dict]:
        result = [{"role": "system", "content": system}] if system else []
        for message in messages:
            if message.role == "user":
                result.append({"role": "user", "content": message.text})
            elif message.role == "model":
                item: dict = {"role": "assistant", "content": message.text or None}
                calls = message.all_tool_calls
                if calls:
                    item["tool_calls"] = [{"id": call.call_id, "type": "function", "function": {
                        "name": call.name, "arguments": json.dumps(call.arguments, allow_nan=False),
                    }} for call in calls]
                result.append(item)
            elif message.role == "tool":
                result.append({"role": "tool", "tool_call_id": message.call_id,
                               "content": json.dumps(message.result or {}, allow_nan=False)})
            else:
                raise LLMError(f"unsupported message role {message.role!r}")
        return result

    def call(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        started = time.perf_counter()
        body = {"model": self.model, "messages": self._messages(system, messages),
                "temperature": self.temperature, "max_tokens": 8192, "stream": False}
        # This model supports low/medium/high. Other model families keep their
        # own defaults rather than receiving a model-specific parameter.
        if "gpt-oss" in self.model:
            body["reasoning_effort"] = "low"
        if tools:
            body.update(tools=[{"type": "function", "function": tool} for tool in tools],
                        tool_choice="auto", parallel_tool_calls=False)
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        error = "Hugging Face request failed"
        for attempt in range(self.max_attempts):
            delay = 0.75 * (2 ** attempt)
            try:
                response = requests.post(f"{self.base_url}/chat/completions", headers=headers,
                                         json=body, timeout=self.timeout_s)
            except requests.RequestException as exc:
                error = f"Hugging Face transport error: {exc}".replace(self._token, "[redacted]")
            else:
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise LLMError("Hugging Face returned non-JSON data") from exc
                    return self._parse(payload, (time.perf_counter() - started) * 1000)
                error = f"Hugging Face HTTP {response.status_code}: {response.text[:600]}".replace(self._token, "[redacted]")
                if response.status_code not in RETRYABLE_STATUS:
                    raise LLMError(error)
                try:
                    delay = min(max(float(response.headers.get("Retry-After", delay)), 0), 8)
                except (ValueError, TypeError):
                    pass
            if attempt + 1 < self.max_attempts:
                time.sleep(delay)
        raise LLMError(error)

    def _parse(self, payload: dict, elapsed_ms: float) -> LLMResponse:
        try:
            choice = payload["choices"][0]
            if choice.get("finish_reason") not in {"stop", "tool_calls"}:
                raise ValueError(f"incomplete or filtered reply (finish_reason={choice.get('finish_reason')!r})")
            message = choice["message"]
            text = message.get("content") or ""
            if not isinstance(text, str):
                raise ValueError("content must be text")
            raw_calls = message.get("tool_calls") or []
            # GLM through the router has been observed returning two calls in
            # one turn despite parallel_tool_calls=false. Treating that as a
            # fatal reply ended a live replan UNRESOLVED after 100 s. Every call
            # is returned; the planner runs them in order and answers each, so
            # the replayed history stays complete.
            calls = []
            for raw in raw_calls:
                function = raw["function"]
                arguments = json.loads(function["arguments"])
                if not isinstance(arguments, dict) or not raw.get("id") or not function.get("name"):
                    raise ValueError("tool call needs an id, name and JSON object arguments")
                calls.append(ToolCall(name=function["name"], arguments=arguments, call_id=raw["id"]))
            if not text.strip() and not calls:
                raise ValueError("empty reply")
            return LLMResponse(text=text.strip(), tool_calls=tuple(calls), model=self.name,
                               latency_ms=elapsed_ms, usage=payload.get("usage") or {})
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise LLMError(f"Unusable Hugging Face reply: {exc}") from exc
