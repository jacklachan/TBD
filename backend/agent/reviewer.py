"""A second model that can stop a proposal, reading only validated evidence.

Two properties make this more than decoration.

It can actually block, and blocking is the default when anything goes wrong:
an unparseable reply, a missing decision, or a transport failure all return a
verdict that prevents approval. A reviewer that can only agree is theatre.

It cannot override a deterministic failure. If validation did not pass, this is
not consulted at all -- there is nothing for a second opinion to add to a
computed constraint violation, and letting a model "approve" past one would be
the worst possible design.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from backend.agent.llm import LLMError, Message, Provider
from backend.planning.candidates import DESIGNED_PREFIX, Candidate
from backend.planning.verifier import STATUS_PASS, ValidationResult
from backend.planning.policy import Policy

DECISION_ALLOW = "ALLOW"
DECISION_BLOCK = "BLOCK"
DECISION_UNAVAILABLE = "UNAVAILABLE"

REASON_OK = "OK"
REASON_REVIEWER_UNPARSEABLE = "REVIEWER_UNPARSEABLE"
REASON_REVIEWER_ERROR = "REVIEWER_ERROR"
REASON_NOT_VALIDATED = "NOT_VALIDATED"

SYSTEM_PROMPT = """You are a safety reviewer for satellite collision-avoidance proposals.

You receive computed evidence for one manoeuvre that has already passed automatic
validation. Your job is to decide whether anything about it should still stop it
from being carried out.

`candidate_id` is an opaque label. Do not read a burn time or a magnitude out
of it, and never call the evidence inconsistent because the label does not
match the numbers. The `manoeuvre` object is the burn under review and is the
only description of it.

Block if the evidence is internally inconsistent, if a clearance is only
marginally above the floor, if a reported minimum is flagged as ambiguous, or if
required evidence is missing. Allow if the evidence supports the manoeuvre.

Reply with JSON only, no prose outside it:
{"decision": "ALLOW" or "BLOCK", "reason_codes": ["..."], "rationale": "one or two sentences"}

Do not restate numbers you were not given. Do not compute anything."""

MARGINAL_CLEARANCE_RATIO = 1.25


@dataclass(frozen=True)
class ReviewerVerdict:
    decision: str
    reason_codes: tuple[str, ...]
    rationale: str = ""
    evidence_ids: tuple[str, ...] = ()
    model: str = ""
    latency_ms: float = 0.0
    detail: dict = field(default_factory=dict)

    @property
    def allows(self) -> bool:
        return self.decision == DECISION_ALLOW


def build_evidence(
    validation: ValidationResult,
    policy: Policy,
    candidate: Candidate | None = None,
) -> dict:
    """Read-only evidence. No trajectories, no candidate list, no tools.

    ``candidate`` is the burn under review. It is optional only because a
    reviewer that is handed no manoeuvre should say so rather than crash --
    "required evidence is missing" is a correct verdict on an incomplete
    bundle. It should be supplied. Grid IDs happen to describe their own burn,
    which is why its absence went unnoticed until the planner started designing
    manoeuvres whose IDs the reviewer had never seen.
    """
    manoeuvre: dict | None = None
    if candidate is not None:
        manoeuvre = {
            "kind": candidate.kind,
            "delta_v_mps": candidate.delta_v_mps,
            "burn_t_s": candidate.burn_t_s,
            "direction": candidate.direction,
            "within_budget": candidate.delta_v_mps <= policy.max_delta_v_mps + 1e-12,
            "source": (
                "DESIGNED"
                if candidate.candidate_id.startswith(DESIGNED_PREFIX)
                else "GRID"
            ),
        }

    return {
        "candidate_id": validation.candidate_id,
        "manoeuvre": manoeuvre,
        "validation_id": validation.validation_id,
        "validation_status": validation.status,
        "clearance_floor_m": policy.min_separation_m,
        "fuel_budget_mps": policy.max_delta_v_mps,
        "screened_objects": list(validation.evaluated_object_ids),
        "horizon_s": validation.horizon_s,
        "sample_step_s": validation.sample_step_s,
        "encounters": [
            {
                "object_id": e.other_object_id,
                "min_separation_m": round(e.min_separation_m, 1),
                "tca_s": round(e.tca_s, 1),
                "relative_speed_mps": round(e.relative_speed_mps, 0),
                "boundary_kind": e.boundary_kind,
                "ambiguous_time": e.ambiguous_time,
            }
            for e in validation.encounters
        ],
        "search_agreement": {
            "distance_m": validation.max_primary_distance_disagreement_m,
            "time_s": validation.primary_time_disagreement_s,
        },
    }


def _parse(text: str) -> dict | None:
    """Accept bare JSON or JSON inside a fenced block; reject anything else."""
    if not text:
        return None
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1)
    else:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            return None
        stripped = stripped[start : end + 1]
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def review(
    provider: Provider,
    validation: ValidationResult,
    policy: Policy,
    candidate: Candidate | None = None,
) -> ReviewerVerdict:
    """Second opinion on an already-validated proposal.

    Never called for a validation that did not pass; if one is passed anyway it
    is refused rather than reviewed.
    """
    if validation.status != STATUS_PASS:
        return ReviewerVerdict(
            decision=DECISION_BLOCK,
            reason_codes=(REASON_NOT_VALIDATED,),
            rationale=(
                "Deterministic validation did not pass, so there is nothing to "
                "review. A reviewer cannot clear a computed constraint violation."
            ),
            evidence_ids=(validation.validation_id,),
        )

    evidence = build_evidence(validation, policy, candidate)
    started = time.perf_counter()

    try:
        response = provider.call(
            SYSTEM_PROMPT,
            [Message(role="user", text=json.dumps(evidence, indent=2))],
            tools=[],
        )
    except LLMError as exc:
        return ReviewerVerdict(
            decision=DECISION_UNAVAILABLE,
            reason_codes=(REASON_REVIEWER_ERROR,),
            rationale=f"Reviewer could not be reached: {exc}",
            evidence_ids=(validation.validation_id,),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            detail={"error": str(exc)},
        )

    latency_ms = (time.perf_counter() - started) * 1000.0
    parsed = _parse(response.text)

    if parsed is None or parsed.get("decision") not in (DECISION_ALLOW, DECISION_BLOCK):
        # Fail closed, and say which kind of failure this is: a reviewer that
        # did not answer is not the same as a reviewer that found a problem.
        return ReviewerVerdict(
            decision=DECISION_UNAVAILABLE,
            reason_codes=(REASON_REVIEWER_UNPARSEABLE,),
            rationale="Reviewer reply could not be read as a decision.",
            evidence_ids=(validation.validation_id,),
            model=response.model or provider.name,
            latency_ms=latency_ms,
            detail={"raw": response.text[:500]},
        )

    codes = parsed.get("reason_codes") or []
    if not isinstance(codes, list):
        codes = [str(codes)]

    return ReviewerVerdict(
        decision=parsed["decision"],
        reason_codes=tuple(str(c) for c in codes) or (REASON_OK,),
        rationale=str(parsed.get("rationale", ""))[:600],
        evidence_ids=(validation.validation_id,),
        model=response.model or provider.name,
        latency_ms=latency_ms,
    )


