"""One seam between the planner and whichever model actually answers.

Everything above this module speaks in ``LLMResponse``; only the providers below
know about a wire format. Swapping Gemini for another provider is a new class
here, not a rewrite of the planner.

Tool declarations are handwritten flat dictionaries in ``tools.py`` rather than
generated from Pydantic. Gemini's function-calling schema is an OpenAPI subset;
generated JSON Schema carries ``$ref`` for nested models and ``anyOf`` for every
``Optional[X]``, which it rejects with unhelpful errors. Arguments coming back
are validated against the domain types after the call, so nothing is lost.

**Verified against a live endpoint** on ``gemini-3.6-flash`` over
``generateContent``: full request -> function call -> result -> continuation,
recorded in Handoff/handoffs/C_AGENT_API.md. ``scripts/smoke_llm.py`` reproves
it against any key, and fails on a text-only reply. Every test in the suite
still uses ``ScriptedProvider``, which proves the loop and not the model.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Protocol

import requests

from backend.config import gemini_api_key, planner_model

DEFAULT_TIMEOUT_S = 30
DEFAULT_TEMPERATURE = 0.0

# A single rate-limit or "model overloaded" reply used to end the run as an
# unresolved case. Those are exactly the failures that are transient and worth
# one more try; a 400 or a 403 is not, and retrying it only burns the deadline.
DEFAULT_MAX_ATTEMPTS = 3
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_RETRY_BASE_DELAY_S = 0.75
_RETRY_MAX_DELAY_S = 8.0

ROLE_USER = "user"
ROLE_MODEL = "model"
ROLE_TOOL = "tool"


class LLMError(RuntimeError):
    """Transport, authentication, quota, or malformed-response failure.

    Callers turn this into an explicit unresolved case. It must never become a
    successful empty result.
    """


@dataclass(frozen=True)
class ToolCall:
    """A tool the model asked for.

    ``call_id`` and ``thought_signature`` are provider bookkeeping that must be
    echoed back verbatim when the turn is replayed in conversation history.
    Gemini 3.x rejects a functionCall part that arrives without its signature.
    Both default to empty so scripted tests can construct a call by name alone.
    """

    name: str
    arguments: dict
    call_id: str = ""
    thought_signature: str = ""


@dataclass(frozen=True)
class LLMResponse:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    model: str = ""
    latency_ms: float = 0.0
    usage: dict = field(default_factory=dict)

    @property
    def wants_tool(self) -> bool:
        return bool(self.tool_calls)


@dataclass
class Message:
    """Provider-neutral turn.

    ``tool`` messages carry the result of a call the model asked for; ``name``
    is the tool it named.
    """

    role: str
    text: str = ""
    tool_call: ToolCall | None = None
    name: str = ""
    result: dict | None = None
    call_id: str = ""


class Provider(Protocol):
    name: str

    def call(
        self, system: str, messages: list[Message], tools: list[dict]
    ) -> LLMResponse: ...


# --------------------------------------------------------------------------
# Gemini over REST
# --------------------------------------------------------------------------


class GeminiProvider:
    """Gemini via the generateContent REST endpoint.

    REST rather than the SDK so the request body -- especially the flat tool
    schema -- stays visible and debuggable.

    Transient failures are retried with jittered backoff; a deterministic one
    (bad schema, bad key, blocked prompt) is raised on the first reply, because
    the second will say the same thing more slowly.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        model = model or planner_model()
        self.name = f"gemini:{model}"
        self.model = model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.max_attempts = max(1, int(max_attempts))
        self._api_key = api_key or gemini_api_key()
        if not self._api_key:
            raise LLMError(
                "GEMINI_API_KEY is not set. Put it in the .env file at the "
                "repository root (copy .env.example), or export it. Keys never "
                "belong in the repository."
            )

    @staticmethod
    def _to_contents(messages: list[Message]) -> list[dict]:
        contents: list[dict] = []
        for message in messages:
            if message.role == ROLE_USER:
                contents.append({"role": "user", "parts": [{"text": message.text}]})
            elif message.role == ROLE_MODEL:
                parts: list[dict] = []
                if message.text:
                    parts.append({"text": message.text})
                if message.tool_call is not None:
                    call: dict = {
                        "name": message.tool_call.name,
                        "args": message.tool_call.arguments,
                    }
                    if message.tool_call.call_id:
                        call["id"] = message.tool_call.call_id
                    part: dict = {"functionCall": call}
                    # Gemini 3.x requires the signature it issued to travel back
                    # with the call, as a sibling key on the same part. Omitting
                    # it is a 400, not a soft degradation.
                    if message.tool_call.thought_signature:
                        part["thoughtSignature"] = message.tool_call.thought_signature
                    parts.append(part)
                contents.append({"role": "model", "parts": parts})
            elif message.role == ROLE_TOOL:
                response: dict = {
                    "name": message.name,
                    "response": message.result or {},
                }
                if message.call_id:
                    response["id"] = message.call_id
                contents.append(
                    {"role": "user", "parts": [{"functionResponse": response}]}
                )
            else:
                raise LLMError(f"unsupported message role {message.role!r}")
        return contents

    @staticmethod
    def _retry_delay_s(attempt: int, response: requests.Response | None) -> float:
        """Backoff before the next attempt, honouring Retry-After when given.

        Jittered, because a retry storm from several clients that all backed off
        by the same amount is how a recovering endpoint gets knocked over again.
        """
        if response is not None:
            header = response.headers.get("Retry-After", "")
            try:
                return min(max(float(header), 0.0), _RETRY_MAX_DELAY_S)
            except (TypeError, ValueError):
                pass
        ceiling = min(_RETRY_BASE_DELAY_S * (2.0**attempt), _RETRY_MAX_DELAY_S)
        return random.uniform(0.5 * ceiling, ceiling)

    def call(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        started = time.perf_counter()
        body: dict = {
            "contents": self._to_contents(messages),
            "generationConfig": {"temperature": self.temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}]

        url = f"{self.BASE_URL}/{self.model}:generateContent"
        # In the header rather than the query string: a URL travels through
        # proxy logs, browser history and error reports, and a key in one is a
        # leaked key.
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}

        last_error = ""
        for attempt in range(self.max_attempts):
            response: requests.Response | None = None
            try:
                response = requests.post(
                    url, headers=headers, json=body, timeout=self.timeout_s
                )
            except requests.RequestException as exc:
                last_error = f"request to {self.model} failed: {exc}"
            else:
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except json.JSONDecodeError as exc:
                        raise LLMError(
                            f"{self.model} returned non-JSON: {response.text[:300]}"
                        ) from exc
                    # requests.Response.elapsed covers only the final HTTP
                    # attempt, excluding backoff and earlier failed attempts.
                    return self._parse(payload, (time.perf_counter() - started) * 1000.0)

                # The 400 you get for an unsupported schema construct is opaque,
                # so surface the body rather than just the status.
                last_error = (
                    f"{self.model} returned HTTP {response.status_code}: "
                    f"{response.text[:600]}"
                )
                if response.status_code not in RETRYABLE_STATUS:
                    raise LLMError(last_error)

            if attempt + 1 >= self.max_attempts:
                break
            time.sleep(self._retry_delay_s(attempt, response))

        raise LLMError(
            f"{last_error} (gave up after {self.max_attempts} attempt(s))"
        )

    def _parse(self, payload: dict, elapsed_ms: float) -> LLMResponse:
        candidates = payload.get("candidates") or []
        if not candidates:
            blocked = payload.get("promptFeedback", {}).get("blockReason")
            raise LLMError(
                f"{self.model} returned no candidates"
                + (f" (blockReason {blocked})" if blocked else "")
            )

        parts = candidates[0].get("content", {}).get("parts") or []
        text_chunks: list[str] = []
        calls: list[ToolCall] = []
        for part in parts:
            if "text" in part:
                text_chunks.append(part["text"])
            if "functionCall" in part:
                call = part["functionCall"]
                calls.append(
                    ToolCall(
                        name=call.get("name", ""),
                        arguments=call.get("args") or {},
                        call_id=call.get("id", ""),
                        # Sibling of functionCall on the same part, not inside it.
                        thought_signature=part.get("thoughtSignature", ""),
                    )
                )

        return LLMResponse(
            text="".join(text_chunks).strip(),
            tool_calls=tuple(calls),
            model=self.model,
            latency_ms=elapsed_ms,
            usage=payload.get("usageMetadata", {}),
        )


# --------------------------------------------------------------------------
# Deterministic provider for tests
# --------------------------------------------------------------------------


class ScriptedProvider:
    """Replays a fixed sequence of responses and records what it was asked.

    Lets the planner loop, its bounds, and its guards be tested without a key
    and without network flakiness. A scripted pass is evidence the loop is
    correct; it is not evidence that any model works.
    """

    def __init__(self, responses: list[LLMResponse | Exception], name: str = "scripted") -> None:
        self.name = name
        self._responses = list(responses)
        self.calls: list[dict] = []

    def call(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "messages": list(messages),
                "tool_names": [t["name"] for t in tools],
            }
        )
        if not self._responses:
            raise LLMError("ScriptedProvider ran out of scripted responses")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def tools_offered_on(self, index: int) -> list[str]:
        return self.calls[index]["tool_names"]


def tool_call(name: str, **arguments) -> LLMResponse:
    """Shorthand for scripting a single tool call."""
    return LLMResponse(tool_calls=(ToolCall(name=name, arguments=arguments),))


def text_reply(text: str) -> LLMResponse:
    return LLMResponse(text=text)
