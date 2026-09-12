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
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from backend.agent import guards
from backend.agent.llm import LLMError, Message, Provider, ToolCall
from backend.agent.memory import CaseMemory
from backend.agent.reviewer import (
    DECISION_ALLOW,
    MARGINAL_CLEARANCE_RATIO,
    ReviewerVerdict,
    review,
)
from backend.agent.tools import (
    PHASE_PLANNING,
    PHASE_POLICY,
    TOOL_BRIEFING,
    TOOL_DESIGN,
    TOOL_EVALUATE,
    TOOL_PROPOSE_POLICY,
    TOOL_VALIDATE,
    CaseSession,
    ToolError,
    declarations_for_phase,
    dispatch,
)
from backend.planning.verifier import STATUS_PASS

# Tools whose result is an independent validation. Kept as a set because two
# different tools now produce one, and a hardcoded name in either the limit
# check or the reviewer hand-off would silently exempt the other.
VALIDATING_TOOLS = frozenset({TOOL_VALIDATE, TOOL_DESIGN})

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

If validation rejects your choice, read `blocked_by`: it names the object and how
far short of the floor the option fell. Options with a similar magnitude and burn
time move the satellite to a similar place, so they tend to fail the same way --
after a rejection, try one that differs materially in magnitude rather than the
next one along. You may widen the search once, and widening adds SMALLER
magnitudes, so it does not help when you were rejected for being too close to
something.

The grid is a menu, not a limit. If it brackets a workable answer without
containing one -- one option leaves too little margin, the next spends more fuel
than the job needs -- use design_maneuver to specify the burn you actually want:
any time, either direction, any magnitude within the budget. It is validated by
the same independent check, so designing a burn clears nothing on its own. Take
a grid option when one fits; design when the geometry asks for something the
grid does not offer, and say in your reply that you did.

A pass is not the same as a good answer. Every validation reports
`margin_above_floor_m`, the bar in `comfortable_margin_m`, and a `marginal`
flag. A marginal option will be refused by a separate safety reviewer, so
recommending one spends the run on something nobody can approve.

When a validation comes back marginal, design a better one before you conclude.
`budget_remaining_mps` says how much more you can spend. Two things buy margin:
burning earlier, because the displacement has longer to grow, and burning
harder. The grid's earliest burn is not the earliest one possible, and its
largest is not the largest one affordable. If a design improves the margin but
is still marginal, move further in the same direction rather than trying a
nearby variation.

When you are done, reply with two or three plain sentences: what you recommend,
what you rejected and why. Plain prose only -- no headings, no bullet lists, no
markdown. Refer to options by their ID. Do not state distances or times you were
not given by a tool, and do not compute anything yourself."""

PREFETCHED_NOTE = """The case briefing and the screening results are already below, computed by the
backend before this turn. Do not call get_case_briefing or evaluate_candidates
to fetch what you have already been given -- start by validating the option you
want to recommend. Both tools remain available if you widen the search or need
to re-read something."""

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
    max_model_calls: int = 12
    max_tool_calls: int = 18
    # Six rather than four because designing a burn now costs a validation, and
    # a run that finds a marginal answer and is then cut off before it can
    # improve on it has spent its budget reaching something the safety reviewer
    # will refuse.
    max_validations: int = 6
    deadline_s: float = 90.0


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
    """Accumulates the run's trace, and reports each step as it happens.

    The trace used to be readable only once the run had finished, which for a
    run that proves no option works is most of a minute of an unexplained
    spinner. ``on_event`` lets the caller watch. It is called on the worker
    thread, so whatever is passed must be cheap and must not raise -- a progress
    display is not worth failing a run over.
    """

    def __init__(self, on_event: Callable[[CaseEvent], None] | None = None) -> None:
        self.events: list[CaseEvent] = []
        self.on_event = on_event

    def add(self, event_type: str, summary: str, duration_ms: float, **details) -> CaseEvent:
        event = CaseEvent(
            sequence=len(self.events) + 1,
            event_type=event_type,
            summary=summary,
            duration_ms=duration_ms,
            details=details,
        )
        self.events.append(event)
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:  # noqa: BLE001 - progress must never fail a run
                pass
        return event


def _has_comfortable_margin(validation, policy) -> bool:
    """Whether an option clears the floor by more than a hair.

    Uses the safety reviewer's own definition of a thin margin. The two must
    agree on what counts as comfortable, because a ranking that prefers the
    cheapest passing option will otherwise keep proposing exactly the options
    the reviewer refuses -- which is a run spent reaching an answer nobody can
    approve. The reviewer still decides; this only stops us putting a known
    refusal in front of it.
    """
    closest = validation.closest()
    if closest is None:
        return False
    return closest.min_separation_m >= policy.min_separation_m * MARGINAL_CLEARANCE_RATIO


def _winning_validation(session: CaseSession, passed: list[tuple]) -> tuple:
    """Pick among the options that passed, by the policy's own ranking.

    Comfortable margin first, then least fuel, then the most clearance, then
    the earliest burn, then the ID. Taking whichever happened to be validated
    last made the recommendation depend on the order the model explored in:
    validate a good option, then validate another good one out of curiosity,
    and the second silently became the proposal. Ranking is a rule that can be
    stated to an operator; "the last one it looked at" is not.

    Margin comes before fuel because the cheapest option that merely scrapes
    past the floor is not the best answer to a conjunction -- it is the answer
    most likely to be refused.

    Within the comfortable group the cheapest wins, which is the ordering the
    search already uses: once there is room to spare, spending more fuel buys
    nothing worth having. Within the marginal group the order flips and the
    roomiest wins, because when nothing clears comfortably the scarce thing is
    separation, not fuel. Saving propellant on a manoeuvre that leaves you
    eleven metres above the floor is a false economy.

    This still reads nothing from the model's opinion. It reads typed
    validation results and the candidate grid.
    """

    def rank_key(item: tuple) -> tuple:
        candidate_id, validation = item
        try:
            candidate = session.candidate_by_id(candidate_id)
        except ToolError:
            return (1, float("inf"), float("inf"), float("inf"), candidate_id)
        closest = validation.closest()
        separation = closest.min_separation_m if closest is not None else 0.0
        if _has_comfortable_margin(validation, session.policy):
            return (0, candidate.delta_v_mps, -separation, _burn_key(candidate), candidate_id)
        return (1, -separation, candidate.delta_v_mps, _burn_key(candidate), candidate_id)

    return min(passed, key=rank_key)


def _burn_key(candidate) -> float:
    """Earliest burn first; the baseline, which has no burn, sorts ahead of all."""
    return candidate.burn_t_s if candidate.burn_t_s is not None else -1.0


def _compact(payload: dict, limit: int = 4000) -> dict:
    """Tool results go back as summaries; guard against an oversized payload."""
    text = json.dumps(payload)
    if len(text) <= limit:
        return payload
    return {"truncated": True, "preview": text[:limit]}


def _prefetch_context(session: CaseSession, recorder: "_Recorder") -> str:
    """Run the two read-only tools up front and return them as prompt context.

    Both are deterministic, neither takes an argument the model chooses, and
    together they are always the first two turns of an investigation. Paying
    for them as two sequential model round trips buys nothing: the model asks,
    waits, reads, asks again. Computing them here removes two round trips from
    every plan, which on a five-call loop is the largest single latency saving
    available -- model time dominates, backend time does not.

    This grants the model nothing. It is the same data the same tools would
    have returned, and approvability still comes only from validation.
    """
    started = time.perf_counter()
    try:
        briefing = dispatch(session, TOOL_BRIEFING, {}, phase=PHASE_PLANNING)
        screening = dispatch(session, TOOL_EVALUATE, {}, phase=PHASE_PLANNING)
    except (ToolError, KeyError, ValueError) as exc:
        # Degrade to the tool-driven path rather than failing the run: the model
        # can still call both tools itself.
        recorder.add(
            "prefetch_skipped",
            f"Could not precompute the briefing and screening: {exc}",
            (time.perf_counter() - started) * 1000.0,
            error=str(exc),
        )
        return ""

    nothing = briefing.get("if_nothing_is_done", {})
    recorder.add(
        "prefetch",
        f"Precomputed the briefing and screened {screening.get('candidate_count')} "
        f"options before the first model call; doing nothing comes within "
        f"{nothing.get('closest_approach_m')} m of {nothing.get('object_id')}.",
        (time.perf_counter() - started) * 1000.0,
        candidate_count=screening.get("candidate_count"),
        qualified_count=screening.get("qualified_count"),
        from_cache=screening.get("from_cache"),
    )
    return (
        "\n\n"
        f"{TOOL_BRIEFING} result:\n{json.dumps(_compact(briefing), indent=2)}"
        "\n\n"
        f"{TOOL_EVALUATE} result:\n{json.dumps(_compact(screening), indent=2)}"
    )


def plan_case(
    provider: Provider,
    session: CaseSession,
    limits: PlannerLimits | None = None,
    memory: CaseMemory | None = None,
    reviewer_provider: Provider | None = None,
    instruction: str = "",
    prefetch_context: bool = True,
    on_event: Callable[[CaseEvent], None] | None = None,
) -> PlannerOutcome:
    """Run the loop until the model concludes or a bound is reached.

    ``prefetch_context`` computes the briefing and the screening before the
    first model call and hands them over as context. Pass False to make the
    model fetch both itself, which is the shape the scripted tests exercise.
    """
    limits = limits or PlannerLimits()
    recorder = _Recorder(on_event)
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
    system_prompt = SYSTEM_PROMPT
    context = _prefetch_context(session, recorder) if prefetch_context else ""
    if context:
        system_prompt = f"{SYSTEM_PROMPT}\n\n{PREFETCHED_NOTE}"

    messages: list[Message] = [Message(role="user", text=task + context)]
    tools = declarations_for_phase(PHASE_PLANNING)

    model_calls = 0
    tool_calls = 0
    validations_run = 0
    final_text = ""
    unresolved = ""

    # The reviewer reads one passing validation and nothing else, so it does not
    # have to wait for the model to finish writing. Starting it the moment a
    # validation passes overlaps it with the final turn instead of adding to it.
    review_pool = ThreadPoolExecutor(max_workers=1) if reviewer_provider else None
    review_future: Future | None = None
    reviewed_validation_id = ""

    while True:
        if time.perf_counter() - started > limits.deadline_s:
            unresolved = UNRESOLVED_DEADLINE
            break
        if model_calls >= limits.max_model_calls:
            unresolved = UNRESOLVED_MODEL_CALLS
            break

        call_started = time.perf_counter()
        try:
            response = provider.call(system_prompt, messages, tools)
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

        if call.name in VALIDATING_TOOLS and validations_run >= limits.max_validations:
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
            messages.append(
                Message(
                    role="tool", name=call.name, result=result, call_id=call.call_id
                )
            )
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

        if call.name in VALIDATING_TOOLS and not failed:
            validations_run += 1
            passing = session.validations.get(result.get("candidate_id", ""))
            if (
                review_pool is not None
                and passing is not None
                and passing.status == STATUS_PASS
                and passing.validation_id != reviewed_validation_id
            ):
                reviewed_validation_id = passing.validation_id
                try:
                    reviewed_candidate = session.candidate_by_id(passing.candidate_id)
                except ToolError:
                    reviewed_candidate = None
                review_future = review_pool.submit(
                    review,
                    reviewer_provider,
                    passing,
                    session.policy,
                    reviewed_candidate,
                )

        recorder.add(
            "tool_error" if failed else "tool_result",
            _tool_summary(call.name, result, failed),
            tool_ms,
            tool=call.name,
            arguments=call.arguments,
            result=_compact(result),
        )
        messages.append(
            Message(
                role="tool",
                name=call.name,
                result=_compact(result),
                call_id=call.call_id,
            )
        )

    if review_pool is not None:
        review_pool.shutdown(wait=False)

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

    candidate_id, validation = _winning_validation(session, passed)

    # The proposal is chosen from typed results, so the prose can in principle
    # recommend something else. Say so in the trace rather than letting the two
    # disagree quietly on screen.
    other_passing = [
        other_id for other_id, _ in passed if other_id != candidate_id and other_id in final_text
    ]
    if other_passing and candidate_id not in final_text:
        recorder.add(
            "rationale_mismatch",
            f"Rationale names {', '.join(other_passing)} but the ranked proposal "
            f"is {candidate_id}; the proposal follows the validation results.",
            0.0,
            proposed=candidate_id,
            named_in_rationale=other_passing,
        )

    # The rationale may quote anything the tools computed during this run, not
    # only the option that won. Explaining why an option was rejected requires
    # citing that option's numbers, so every validation in the session counts as
    # supporting evidence -- otherwise the guard punishes exactly the behaviour
    # we want.
    allowed_values = guards.values_from_policy(session.policy)
    for other_id, other_validation in session.validations.items():
        allowed_values |= guards.values_from_validation(other_validation)
        allowed_values |= guards.values_from_shortfalls(other_validation, session.policy)
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
        if review_future is not None and reviewed_validation_id == validation.validation_id:
            verdict = review_future.result()
        else:
            try:
                reviewed_candidate = session.candidate_by_id(validation.candidate_id)
            except ToolError:
                reviewed_candidate = None
            verdict = review(
                reviewer_provider, validation, session.policy, reviewed_candidate
            )
        recorder.add(
            "reviewer",
            f"Safety reviewer returned {verdict.decision}.",
            (time.perf_counter() - review_started) * 1000.0,
            decision=verdict.decision,
            reason_codes=list(verdict.reason_codes),
            rationale=verdict.rationale,
            overlapped=review_future is not None,
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
    if name == "design_maneuver":
        # The most interesting line in a run, so it says what was designed and
        # how it did rather than that a tool returned. "Marginal" is included
        # because a PASS that the reviewer will refuse is not the same news as
        # a PASS with room in it.
        margin = result.get("margin_above_floor_m")
        outcome = result.get("status")
        if outcome == STATUS_PASS and margin is not None:
            outcome = (
                f"clears by {margin:,.0f} m"
                + (" but is marginal" if result.get("marginal") else "")
            )
        return (
            f"Designed {result.get('delta_v_mps')} m/s "
            f"{str(result.get('direction', '')).lower()} at "
            f"T+{result.get('burn_t_s', 0):,.0f} s: {outcome}."
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
        messages.append(
            Message(role="tool", name=call.name, result=result, call_id=call.call_id)
        )

        if call.name == TOOL_PROPOSE_POLICY and not failed:
            diff_result = result
            break

    return diff_result, recorder.events, model_calls
