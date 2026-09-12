"""The bounded planning loop.

The model investigates with tools and then explains its choice. It does not
decide what is approvable: the application reads that off the typed validation
results. So the loop cannot produce an approved proposal for an option that was
never validated, or that was validated and blocked -- not because the prompt
discourages it, but because nothing in this module looks at the model's opinion
when deciding.

Every limit here is a real bound, and exhausting one produces a specific
unresolved status rather than a best guess. Call counts are recorded as they
happen; no fixed turn count is claimed anywhere.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.agent import guards
from backend.agent.llm import LLMError, LLMResponse, Message, Provider, ToolCall
from backend.agent.memory import CaseMemory
from backend.agent.reviewer import (
    DECISION_ALLOW,
    ReviewerVerdict,
    review,
)
from backend.agent.tools import (
    PHASE_PLANNING,
    PHASE_POLICY,
    TOOL_PROPOSE_POLICY,
    CaseSession,
    ToolError,
    declarations_for_phase,
    dispatch,
)
from backend.planning.verifier import STATUS_PASS

STATUS_PROPOSAL_READY = "PROPOSAL_READY"
STATUS_NO_APPROVABLE_OPTION = "NO_APPROVABLE_OPTION"
STATUS_UNRESOLVED = "UNRESOLVED"

UNRESOLVED_MODEL_CALLS = "MODEL_CALL_LIMIT"
UNRESOLVED_TOOL_CALLS = "TOOL_CALL_LIMIT"
UNRESOLVED_DEADLINE = "DEADLINE"
UNRESOLVED_PROVIDER = "PROVIDER_ERROR"
UNRESOLVED_NO_CONCLUSION = "NO_CONCLUSION"

SYSTEM_PROMPT = """You help a satellite operator decide how to respond to a predicted close approach.

Work through the tools. A reasonable order is: read the case, screen the
options, then independently validate the one you want to recommend. Screening
results cover only the object that triggered the case, so an option that looks
good there can still be unsafe against something else -- validation is what
settles it.

If validation rejects your choice, read why, then pick a different option and
validate that. You may widen the search once, after a rejection.

When you are done, reply with a short plain-language explanation of what you
recommend and why, mentioning any option you rejected and the reason. Refer to
options by their ID. Do not state distances or times you were not given by a
tool, and do not compute anything yourself."""

POLICY_SYSTEM_PROMPT = """You turn an operator's instruction into a proposed constraint change.

Read the case first so you know which windows exist. Then call propose_policy
once with the arguments that match the instruction. Use budget_scale for a
relative change such as halving; use max_delta_v_mps for an absolute limit; use
blocked_window_id only for a window listed in the briefing.

If the instruction does not map onto those, call propose_policy with no
arguments so the operator is asked for clarification. Never guess a number or a
time window."""


@dataclass
class PlannerLimits:
    max_model_calls: int = 8
    max_tool_calls: int = 12
    max_validations: int = 3
    deadline_s: float = 60.0


@dataclass
class CaseEvent:
    sequence: int
    event_type: str
    summary: str
    duration_ms: float
    details: dict = field(default_factory=dict)
    created_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    )


@dataclass
class Proposal:
    proposal_id: str
    case_id: str
    scenario_version: int
    policy_version: int
    candidate_id: str
    validation_id: str
    reviewer_verdict: ReviewerVerdict | None
    qualitative_rationale: str
    evidence_ids: tuple[str, ...]
    status: str

    @property
    def approvable(self) -> bool:
        return self.status == "READY"


@dataclass
class PlannerOutcome:
    status: str
    session: CaseSession
    events: list[CaseEvent]
    proposal: Proposal | None = None
    unresolved_reason: str = ""
    model_calls: int = 0
    tool_calls: int = 0
    validations_run: int = 0
    elapsed_s: float = 0.0
    flagged_numbers: tuple[float, ...] = ()

    def trace(self) -> list[str]:
        return [f"{e.event_type}: {e.summary} ({e.duration_ms:.0f} ms)" for e in self.events]


class _Recorder:
    def __init__(self) -> None:
        self.events: list[CaseEvent] = []

    def add(self, event_type: str, summary: str, duration_ms: float, **details) -> CaseEvent:
        event = CaseEvent(
            sequence=len(self.events) + 1,
            event_type=event_type,
            summary=summary,
            duration_ms=duration_ms,
            details=details,
        )
        self.events.append(event)
        return event


def _compact(payload: dict, limit: int = 4000) -> dict:
    """Tool results go back as summaries; guard against an oversized payload."""
    text = json.dumps(payload)
    if len(text) <= limit:
        return payload
    return {"truncated": True, "preview": text[:limit]}


def plan_case(
    provider: Provider,
    session: CaseSession,
    limits: PlannerLimits | None = None,
    memory: CaseMemory | None = None,
    reviewer_provider: Provider | None = None,
    instruction: str = "",
) -> PlannerOutcome:
    """Run the loop until the model concludes or a bound is reached."""
    limits = limits or PlannerLimits()
    recorder = _Recorder()
    started = time.perf_counter()

    if memory is not None:
        hits = memory.relevant(
            scenario_family=str(session.document["scenario_id"]),
            exclude_case_id=session.case_id,
        )
        session.memory_hits = [h.as_hit() for h in hits]
        if hits:
            recorder.add(
                "memory",
                f"Found {len(hits)} relevant prior case(s): "
                + ", ".join(h.case_id for h in hits),
                0.0,
                memory_ids=[h.memory_id for h in hits],
            )

    task = instruction or (
        "A close approach has been predicted. Investigate and recommend what to do."
    )
    messages: list[Message] = [Message(role="user", text=task)]
    tools = declarations_for_phase(PHASE_PLANNING)

    model_calls = 0
    tool_calls = 0
    validations_run = 0
    final_text = ""
    unresolved = ""

    while True:
        if time.perf_counter() - started > limits.deadline_s:
            unresolved = UNRESOLVED_DEADLINE
            break
        if model_calls >= limits.max_model_calls:
            unresolved = UNRESOLVED_MODEL_CALLS
            break

        call_started = time.perf_counter()
        try:
            response = provider.call(SYSTEM_PROMPT, messages, tools)
        except LLMError as exc:
            recorder.add(
                "model_error",
                f"Model call failed: {exc}",
                (time.perf_counter() - call_started) * 1000.0,
                error=str(exc),
            )
            unresolved = UNRESOLVED_PROVIDER
            break

        model_calls += 1
        elapsed_ms = (time.perf_counter() - call_started) * 1000.0

        if not response.wants_tool:
            final_text = response.text
            recorder.add(
                "model_conclusion",
                "Model finished investigating and gave its recommendation.",
                elapsed_ms,
                characters=len(final_text),
            )
            break

        call: ToolCall = response.tool_calls[0]
        recorder.add(
            "model_tool_request",
            f"Model asked for {call.name}.",
            elapsed_ms,
            tool=call.name,
            arguments=call.arguments,
        )
        messages.append(Message(role="model", text=response.text, tool_call=call))

        if tool_calls >= limits.max_tool_calls:
            unresolved = UNRESOLVED_TOOL_CALLS
            break

        if call.name == "validate_proposal" and validations_run >= limits.max_validations:
            result = {
                "error": (
                    f"validation limit of {limits.max_validations} reached in this run"
                )
            }
            recorder.add(
                "tool_refused",
                f"Refused {call.name}: validation limit reached.",
                0.0,
                tool=call.name,
            )
            messages.append(Message(role="tool", name=call.name, result=result))
            tool_calls += 1
            continue

        tool_started = time.perf_counter()
        try:
            result = dispatch(session, call.name, call.arguments, phase=PHASE_PLANNING)
            failed = False
        except ToolError as exc:
            result = {"error": str(exc)}
            failed = True
        tool_ms = (time.perf_counter() - tool_started) * 1000.0
        tool_calls += 1

        if call.name == "validate_proposal" and not failed:
            validations_run += 1

        recorder.add(
            "tool_error" if failed else "tool_result",
            _tool_summary(call.name, result, failed),
            tool_ms,
            tool=call.name,
            arguments=call.arguments,
            result=_compact(result),
        )
        messages.append(Message(role="tool", name=call.name, result=_compact(result)))

    elapsed = time.perf_counter() - started

    passed = [
        (candidate_id, validation)
        for candidate_id, validation in session.validations.items()
        if validation.status == STATUS_PASS
    ]

    if unresolved:
        return PlannerOutcome(
            status=STATUS_UNRESOLVED,
            session=session,
            events=recorder.events,
            unresolved_reason=unresolved,
            model_calls=model_calls,
            tool_calls=tool_calls,
            validations_run=validations_run,
            elapsed_s=elapsed,
        )

    if not passed:
        # Either nothing qualified, or the model stopped without validating
        # anything. These are different situations and are reported differently.
        exhausted = (
            session.search_result is not None
            and not [
                e for e in session.search_result.qualified if not e.candidate.is_baseline
            ]
        )
        if exhausted or session.rejected_candidate_ids:
            recorder.add(
                "no_option",
                "No option passed full validation in the supported search set.",
                0.0,
                rejected=session.rejected_candidate_ids,
            )
            return PlannerOutcome(
                status=STATUS_NO_APPROVABLE_OPTION,
                session=session,
                events=recorder.events,
                model_calls=model_calls,
                tool_calls=tool_calls,
                validations_run=validations_run,
                elapsed_s=elapsed,
            )
        return PlannerOutcome(
            status=STATUS_UNRESOLVED,
            session=session,
            events=recorder.events,
            unresolved_reason=UNRESOLVED_NO_CONCLUSION,
            model_calls=model_calls,
            tool_calls=tool_calls,
            validations_run=validations_run,
            elapsed_s=elapsed,
        )

    candidate_id, validation = passed[-1]
    candidate = session.candidate_by_id(candidate_id)

    # The rationale may quote anything the tools computed during this run, not
    # only the option that won. Explaining why an option was rejected requires
    # citing that option's numbers, so every validation in the session counts as
    # supporting evidence -- otherwise the guard punishes exactly the behaviour
    # we want.
    allowed_values = guards.values_from_policy(session.policy)
    for other_id, other_validation in session.validations.items():
        allowed_values |= guards.values_from_validation(other_validation)
        try:
            allowed_values |= guards.values_from_candidate(
                session.candidate_by_id(other_id)
            )
        except ToolError:
            continue
    if session.search_result is not None:
        allowed_values |= guards.supported_values(
            e.primary_encounter.min_separation_m
            for e in session.search_result.evaluations
            if e.primary_encounter is not None
        )

    flagged = guards.unsupported_numbers(final_text, allowed_values)
    if flagged:
        recorder.add(
            "guard_flag",
            f"Rationale mentions {len(flagged)} figure(s) absent from the evidence: {flagged}.",
            0.0,
            flagged=flagged,
        )

    verdict: ReviewerVerdict | None = None
    if reviewer_provider is not None:
        review_started = time.perf_counter()
        verdict = review(reviewer_provider, validation, session.policy)
        recorder.add(
            "reviewer",
            f"Safety reviewer returned {verdict.decision}.",
            (time.perf_counter() - review_started) * 1000.0,
            decision=verdict.decision,
            reason_codes=list(verdict.reason_codes),
            rationale=verdict.rationale,
        )

    # Approvability is read off typed results. The model's text is attached as
    # explanation and has no bearing on this decision.
    blocked_by_reviewer = verdict is not None and verdict.decision != DECISION_ALLOW
    status = "BLOCKED" if blocked_by_reviewer else "READY"

    proposal = Proposal(
        proposal_id=f"prop_{uuid.uuid4().hex[:10]}",
        case_id=session.case_id,
        scenario_version=session.scenario_version,
        policy_version=session.policy.policy_version,
        candidate_id=candidate_id,
        validation_id=validation.validation_id,
        reviewer_verdict=verdict,
        qualitative_rationale=final_text,
        evidence_ids=(validation.validation_id,),
        status=status,
    )

    return PlannerOutcome(
        status=STATUS_PROPOSAL_READY,
        session=session,
        events=recorder.events,
        proposal=proposal,
        model_calls=model_calls,
        tool_calls=tool_calls,
        validations_run=validations_run,
        elapsed_s=elapsed,
        flagged_numbers=tuple(flagged),
    )


def _tool_summary(name: str, result: dict, failed: bool) -> str:
    if failed:
        return f"{name} rejected: {result.get('error', 'unknown error')}"
    if name == "get_case_briefing":
        nothing = result.get("if_nothing_is_done", {})
        return (
            f"Read the case: doing nothing comes within "
            f"{nothing.get('closest_approach_m')} m of {nothing.get('object_id')}."
        )
    if name == "evaluate_candidates":
        return (
            f"Screened {result.get('candidate_count')} options against the primary "
            f"threat; {result.get('qualified_count')} qualify."
        )
    if name == "validate_proposal":
        objects = ", ".join(result.get("screened_objects", []))
        return (
            f"Validated {result.get('candidate_id')} against {objects}: "
            f"{result.get('status')}."
        )
    if name == "widen_search":
        return (
            f"Widened the grid from {result.get('option_count_before')} to "
            f"{result.get('option_count_after')} options."
        )
    if name == "propose_policy":
        return f"Proposed a policy change: {result.get('status')}."
    return f"{name} completed."


def interpret_instruction(
    provider: Provider,
    session: CaseSession,
    instruction: str,
    limits: PlannerLimits | None = None,
) -> tuple[dict | None, list[CaseEvent], int]:
    """Turn an operator sentence into a proposed policy diff.

    Runs in the policy phase, where planning and validation tools are not
    offered, so this path cannot approve or execute anything.
    """
    limits = limits or PlannerLimits(max_model_calls=3, max_tool_calls=3)
    recorder = _Recorder()
    tools = declarations_for_phase(PHASE_POLICY)
    messages = [Message(role="user", text=instruction)]

    model_calls = 0
    diff_result: dict | None = None

    while model_calls < limits.max_model_calls:
        started = time.perf_counter()
        try:
            response = provider.call(POLICY_SYSTEM_PROMPT, messages, tools)
        except LLMError as exc:
            recorder.add("model_error", f"Model call failed: {exc}", 0.0, error=str(exc))
            break
        model_calls += 1
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        if not response.wants_tool:
            recorder.add(
                "model_conclusion", "Model replied without proposing a change.", elapsed_ms
            )
            break

        call = response.tool_calls[0]
        messages.append(Message(role="model", text=response.text, tool_call=call))
        recorder.add(
            "model_tool_request", f"Model asked for {call.name}.", elapsed_ms, tool=call.name
        )

        try:
            result = dispatch(
                session, call.name, call.arguments, phase=PHASE_POLICY, source_text=instruction
            )
            failed = False
        except ToolError as exc:
            result = {"error": str(exc)}
            failed = True

        recorder.add(
            "tool_error" if failed else "tool_result",
            _tool_summary(call.name, result, failed),
            0.0,
            tool=call.name,
            arguments=call.arguments,
            result=result,
        )
        messages.append(Message(role="tool", name=call.name, result=result))

        if call.name == TOOL_PROPOSE_POLICY and not failed:
            diff_result = result
            break

    return diff_result, recorder.events, model_calls
