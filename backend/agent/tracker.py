"""The conjunction triage agent: a model working through the real screen.

The catalogue screen finds hundreds of passes; an operator needs to know which
few matter and what to do about them. This agent does that triage with three
bounded tools over the committed data -- summarise the screen, list passes,
assess one pass -- and writes a short brief.

The same rules as the planner hold, for the same reasons:

* **The model never supplies a number.** The structured triage the operator
  acts on is assembled from the assessment tool's results, not from the prose.
  Figures in the brief that appear in no tool result are flagged.
* **Every bound is real.** Model calls, tool calls, assessments and a deadline
  each end the run with a named reason rather than a best guess.
* **It can recommend, not act.** There is no execution path from here; a burn
  recommendation is the deterministic assessment's, and it is labelled as a
  linearised estimate on public element sets.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable

from backend.agent import guards
from backend.agent.llm import LLMError, Message, Provider
from backend.agent.planner import CaseEvent, _Recorder

TOOL_SUMMARY = "get_screen_summary"
TOOL_LIST = "list_passes"
TOOL_ASSESS = "assess_pass"

COMFORTABLE_KM = 1.25
MAX_LIST = 15

SYSTEM_PROMPT = """You are the conjunction triage agent for the operator of the Iridium NEXT
communications constellation. A screen of all its satellites against catalogued
debris has already run; its summary and the closest passes are below.

Decide which passes need attention and assess them with assess_pass, most urgent
first. An assessment estimates avoidance burns for that pass and re-screens the
best against every catalogued fragment. You may list more passes with
list_passes, for example for one satellite.

Then write a brief of three to five plain sentences for the operator: which
satellites need a burn and what the assessment recommends, which assessed passes
turned out not to need one, and anything left unassessed or unresolved. Plain
prose only -- no headings, no lists, no markdown. Name passes by satellite and
pass ID. State only figures a tool gave you and do not compute anything. These
are public element sets accurate to about a kilometre: never call a pass a
predicted collision."""

DECLARATIONS = {
    TOOL_SUMMARY: {
        "name": TOOL_SUMMARY,
        "description": "Counts, window, source events and the published cross-check for the whole screen.",
        "parameters": {"type": "object", "properties": {}},
    },
    TOOL_LIST: {
        "name": TOOL_LIST,
        "description": "Passes from the screen, closest first.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_miss_km": {"type": "number", "description": "Only passes closer than this. Default 1.25."},
                "satellite": {"type": "string", "description": "Only this satellite: a name such as IRIDIUM 170, or a NORAD ID."},
                "limit": {"type": "number", "description": f"At most this many rows, up to {MAX_LIST}. Default 10."},
            },
        },
    },
    TOOL_ASSESS: {
        "name": TOOL_ASSESS,
        "description": (
            "Estimate avoidance burns for one pass and re-screen the best against every "
            "catalogued fragment. Returns the recommendation and the evidence."
        ),
        "parameters": {
            "type": "object",
            "properties": {"pass_id": {"type": "string", "description": "A pass_id from the list."}},
            "required": ["pass_id"],
        },
    },
}


class TriageToolError(Exception):
    """Returned to the model as an error result so it can recover."""


@dataclass
class TriageLimits:
    max_model_calls: int = 10
    max_tool_calls: int = 14
    max_assessments: int = 5
    deadline_s: float = 150.0


def pass_id(conjunction: dict) -> str:
    """Starts with a letter so the prose guard reads it as an identifier."""
    moment = datetime.fromisoformat(conjunction["tca_utc"]).strftime("%Y%m%dT%H%M")
    return f"P{conjunction['protected']['norad_id']}_{conjunction['debris']['norad_id']}_{moment}"


def _row(conjunction: dict) -> dict:
    return {
        "pass_id": pass_id(conjunction),
        "satellite": conjunction["protected"]["name"],
        "fragment_norad_id": conjunction["debris"]["norad_id"],
        "event": conjunction["debris"]["event"],
        "tca_utc": conjunction["tca_utc"][:19],
        "miss_km": conjunction["miss_km"],
        "relative_speed_kms": conjunction["relative_speed_kms"],
    }


def _burn_text(option: dict | None) -> str | None:
    if option is None:
        return None
    if option["direction"] is None:
        return "no burn"
    verb = "speed up" if option["direction"] == "PROGRADE" else "slow down"
    return f"{option['delta_v_mps']:.2f} m/s {verb}, {option['lead_minutes']} min before"


class TriageSession:
    def __init__(self, screen: dict, conjunctions: list[dict], assess_fn: Callable) -> None:
        self.screen = screen
        self.conjunctions = conjunctions
        self.by_id = {pass_id(c): c for c in conjunctions}
        self.assess_fn = assess_fn
        self.assessments: dict[str, dict] = {}

    def summary(self) -> dict:
        s = self.screen
        return {
            "window": s["window"],
            "satellites": s["catalog"]["protected_count"],
            "fragments": s["catalog"]["debris_count"],
            "passes_under_report_threshold": s["conjunction_count"],
            "report_threshold_km": s["report_threshold_km"],
            "passes_under_comfortable_margin": sum(c["miss_km"] < COMFORTABLE_KM for c in self.conjunctions),
            "comfortable_margin_km": COMFORTABLE_KM,
            "by_event": s["by_event"],
            "published_cross_check": [
                {
                    "pair": f"{c['object_1']['name']} x {c['object_2']['name']} {c['object_2']['norad_id']}",
                    "published_miss_km": c["published_miss_km"],
                    "our_miss_km": c.get("our_miss_km"),
                    "tca_difference_s": c.get("tca_difference_s"),
                }
                for c in s["cross_check"]
            ],
        }

    def list_passes(self, max_miss_km=None, satellite=None, limit=None) -> dict:
        try:
            ceiling = COMFORTABLE_KM if max_miss_km is None else float(max_miss_km)
            count = 10 if limit is None else int(limit)
        except (TypeError, ValueError) as exc:
            raise TriageToolError(f"max_miss_km and limit must be numbers: {exc}") from None
        count = max(1, min(count, MAX_LIST))
        rows = [c for c in self.conjunctions if c["miss_km"] < ceiling]
        if satellite:
            wanted = str(satellite).strip().upper()
            rows = [c for c in rows if wanted in (c["protected"]["name"].upper(), str(c["protected"]["norad_id"]))]
        return {"total_matching": len(rows), "passes": [_row(c) for c in rows[:count]]}

    def assess(self, pass_id_value) -> dict:
        key = str(pass_id_value or "").strip()
        conjunction = self.by_id.get(key)
        if conjunction is None:
            raise TriageToolError(f"unknown pass_id {key!r}; use a pass_id from list_passes")
        result = self.assess_fn(conjunction["protected"]["norad_id"], conjunction["debris"]["norad_id"], conjunction["tca_utc"])
        self.assessments[key] = result
        chosen = next((o for o in result["options"] if o["option_id"] == result["recommended_option_id"]), None)
        blocked = [
            {"option": _burn_text(o), "blocked_by_norad_id": o["blocked_by"]["debris"]["norad_id"],
             "blocked_miss_km": o["blocked_by"]["miss_km"]}
            for o in result["options"] if o.get("verdict") == "BLOCK" and o.get("blocked_by")
        ]
        return {
            "pass_id": key,
            "satellite": conjunction["protected"]["name"],
            "miss_km": result["conjunction"]["miss_km"],
            "recommendation": _burn_text(chosen),
            "estimated_miss_km": chosen["predicted_miss_km"] if chosen else None,
            "rescreen_closest_km": chosen.get("rescreen_closest_km") if chosen else None,
            "rescreen_hours_after_burn": result["rescreen"]["hours_after_burn"],
            "options_estimated": result["option_count"],
            "options_blocked_by_new_close_approach": blocked,
        }

    def triage_items(self) -> list[dict]:
        items = []
        for key, result in self.assessments.items():
            chosen = next((o for o in result["options"] if o["option_id"] == result["recommended_option_id"]), None)
            if chosen is None:
                status = "NO_OPTION"
            elif chosen["direction"] is None:
                status = "CLEAR"
            else:
                status = "NEEDS_BURN"
            items.append({
                "pass_id": key,
                **{k: v for k, v in _row(self.by_id[key]).items() if k != "pass_id"},
                "status": status,
                "recommendation": _burn_text(chosen),
                "estimated_miss_km": chosen["predicted_miss_km"] if chosen else None,
                "rescreen_closest_km": chosen.get("rescreen_closest_km") if chosen else None,
            })
        order = {"NEEDS_BURN": 0, "NO_OPTION": 1, "CLEAR": 2}
        return sorted(items, key=lambda i: (order[i["status"]], i["miss_km"]))


def _dispatch(session: TriageSession, name: str, arguments: dict) -> dict:
    if name not in DECLARATIONS:
        raise TriageToolError(f"unknown tool {name!r}")
    if not isinstance(arguments, dict):
        raise TriageToolError("arguments must be an object")
    unexpected = set(arguments) - set(DECLARATIONS[name]["parameters"]["properties"])
    if unexpected:
        raise TriageToolError(f"{name!r} received unexpected arguments {sorted(unexpected)}")
    if name == TOOL_SUMMARY:
        return session.summary()
    if name == TOOL_LIST:
        return session.list_passes(arguments.get("max_miss_km"), arguments.get("satellite"), arguments.get("limit"))
    return session.assess(arguments.get("pass_id"))


def _numbers_in(payload) -> list[float]:
    """Every figure a tool returned, including those inside strings."""
    found: list[float] = []
    if isinstance(payload, dict):
        for value in payload.values():
            found.extend(_numbers_in(value))
    elif isinstance(payload, list):
        for value in payload:
            found.extend(_numbers_in(value))
    elif isinstance(payload, bool) or payload is None:
        pass
    elif isinstance(payload, (int, float)):
        found.append(float(payload))
    elif isinstance(payload, str):
        found.extend(guards.numeric_literals(payload))
    return found


def triage(
    provider: Provider,
    screen: dict,
    conjunctions: list[dict],
    assess_fn: Callable,
    limits: TriageLimits | None = None,
    on_event: Callable[[CaseEvent], None] | None = None,
) -> dict:
    limits = limits or TriageLimits()
    session = TriageSession(screen, conjunctions, assess_fn)
    recorder = _Recorder(on_event)
    started = time.perf_counter()
    evidence: list = []

    summary = session.summary()
    listed = session.list_passes()
    evidence.extend([summary, listed])
    recorder.add(
        "prefetch",
        f"Read the screen: {summary['passes_under_comfortable_margin']} passes under "
        f"{COMFORTABLE_KM} km among {summary['passes_under_report_threshold']} under "
        f"{summary['report_threshold_km']} km.",
        0.0,
    )
    messages = [Message(role="user", text=(
        "Triage the screen and brief the operator.\n\n"
        f"{TOOL_SUMMARY} result:\n{json.dumps(summary, indent=1)}\n\n"
        f"{TOOL_LIST} result (passes under {COMFORTABLE_KM} km):\n{json.dumps(listed, indent=1)}"
    ))]
    tools = list(DECLARATIONS.values())

    model_calls = tool_calls = 0
    unresolved = ""
    final_text = ""
    while True:
        if time.perf_counter() - started > limits.deadline_s:
            unresolved = "DEADLINE"
            break
        if model_calls >= limits.max_model_calls:
            unresolved = "MODEL_CALL_LIMIT"
            break
        call_started = time.perf_counter()
        try:
            response = provider.call(SYSTEM_PROMPT, messages, tools)
        except LLMError as exc:
            recorder.add("model_error", f"Model call failed: {exc}", (time.perf_counter() - call_started) * 1000.0)
            unresolved = "PROVIDER_ERROR"
            break
        model_calls += 1
        elapsed_ms = (time.perf_counter() - call_started) * 1000.0
        if not response.wants_tool:
            final_text = response.text
            recorder.add("model_conclusion", "Model wrote the brief.", elapsed_ms)
            break

        requested = response.tool_calls
        messages.append(Message(role="model", text=response.text, tool_call=requested[0],
                                tool_calls=requested if len(requested) > 1 else ()))
        for call in requested:
            recorder.add("model_tool_request", f"Model asked for {call.name}.", elapsed_ms if call is requested[0] else 0.0,
                         tool=call.name, arguments=call.arguments)
        for call in requested:
            if tool_calls >= limits.max_tool_calls:
                unresolved = "TOOL_CALL_LIMIT"
                break
            tool_calls += 1
            tool_started = time.perf_counter()
            try:
                if call.name == TOOL_ASSESS and len(session.assessments) >= limits.max_assessments \
                        and str(call.arguments.get("pass_id", "")).strip() not in session.assessments:
                    raise TriageToolError(f"assessment limit of {limits.max_assessments} reached; write the brief")
                result = _dispatch(session, call.name, call.arguments)
                failed = False
                evidence.append(result)
            except TriageToolError as exc:
                result, failed = {"error": str(exc)}, True
            summary_line = (
                f"{call.name} rejected: {result['error']}" if failed else
                f"Assessed {result['satellite']} pass {result['pass_id']}: "
                f"{result['recommendation'] or 'no option clears it'}." if call.name == TOOL_ASSESS else
                f"Listed {len(result.get('passes', []))} of {result.get('total_matching')} passes." if call.name == TOOL_LIST else
                "Read the screen summary."
            )
            recorder.add("tool_error" if failed else "tool_result", summary_line,
                         (time.perf_counter() - tool_started) * 1000.0, tool=call.name)
            messages.append(Message(role="tool", name=call.name, result=result, call_id=call.call_id))
        if unresolved:
            break

    allowed = guards.supported_values(_numbers_in(evidence) + [COMFORTABLE_KM])
    flagged = guards.unsupported_numbers(final_text, allowed)
    if flagged:
        recorder.add("guard_flag", f"Brief mentions {len(flagged)} figure(s) absent from the tool results: {flagged}.", 0.0)

    return {
        "status": "UNRESOLVED" if unresolved else "BRIEF_READY",
        "unresolved_reason": unresolved,
        "brief": final_text,
        "triage": session.triage_items(),
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "assessments": len(session.assessments),
        "flagged_numbers": flagged,
        "events": [asdict(e) for e in recorder.events],
        "elapsed_s": round(time.perf_counter() - started, 2),
        "note": (
            "The triage table is built from the assessment tool's results; the brief is "
            "the model's summary of them. Linearised estimates on public element sets."
        ),
    }
