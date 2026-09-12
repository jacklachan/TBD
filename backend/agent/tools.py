"""The five tools the model may call, their declarations, and their dispatch.

Three rules hold everywhere in this module.

*The backend binds the case.* No tool takes a case ID, a scenario version or a
policy version. The model cannot point itself at a different case or invent a
version stamp; it can only act on the run it was started for.

*Declarations are handwritten flat dictionaries.* Only ``type``, ``properties``,
``required``, ``description`` and ``enum`` appear -- the OpenAPI subset function
calling accepts. Arguments are validated against the domain types after they
come back.

*Tool results are summaries and identifiers.* Never trajectory samples, never
all 25 evaluations in full. The evidence lives in the case; the model gets
enough to decide and a handle to cite.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from backend.planning.candidates import (
    GRID_REVISION_BASE,
    GRID_REVISION_EXPANDED,
    Candidate,
    generate_candidates,
)
from backend.planning.policy import (
    STATUS_NEEDS_CLARIFICATION,
    STATUS_READY,
    BurnWindow,
    Policy,
    PolicyChange,
    PolicyDiff,
    policy_from_document,
)
from backend.planning.search import SearchResult, evaluate_candidates
from backend.planning.verifier import (
    STATUS_PASS,
    ValidationResult,
    reconstruct,
    validate_candidate,
)

PHASE_PLANNING = "PLANNING"
PHASE_POLICY = "POLICY"

TOOL_BRIEFING = "get_case_briefing"
TOOL_EVALUATE = "evaluate_candidates"
TOOL_VALIDATE = "validate_proposal"
TOOL_PROPOSE_POLICY = "propose_policy"
TOOL_WIDEN = "widen_search"

DIMENSION_SMALLER_MAGNITUDES = "SMALLER_MAGNITUDES"

MAX_LISTED_OPTIONS = 8

# Screening 25 options takes about half a second, and it is deterministic for a
# given scenario, policy and grid. Reset mints a new case ID from the same
# fixture, so without this every demo reset pays that cost again. Keyed on
# content, never on case ID.
#
# The verifier is deliberately NOT cached here. Its whole value is recomputing
# independently, and serving it from the search's memo would defeat that.
#
# Runs execute on a worker pool, so the map and its eviction are guarded. An
# unsynchronised `pop(next(iter(...)))` raises once two threads evict together.
_SEARCH_CACHE: dict[tuple, SearchResult] = {}
_SEARCH_CACHE_LIMIT = 32
_SEARCH_CACHE_LOCK = threading.Lock()


def _search_cache_key(session: "CaseSession") -> tuple:
    """Everything a screening result depends on, and nothing else.

    ``scenario_id`` is in the key alongside the content hash so that a document
    reaching this without a hash cannot collide with a different scenario that
    happens to share a policy.
    """
    policy = session.policy
    return (
        str(session.document.get("scenario_id", "")),
        session.document.get("input_hash", ""),
        session.scenario_version,
        policy.max_delta_v_mps,
        policy.min_separation_m,
        tuple(sorted(w.window_id for w in policy.blocked_windows)),
        session.grid_revision,
    )


def _cache_get(key: tuple) -> SearchResult | None:
    with _SEARCH_CACHE_LOCK:
        return _SEARCH_CACHE.get(key)


def _cache_put(key: tuple, result: SearchResult) -> None:
    with _SEARCH_CACHE_LOCK:
        _SEARCH_CACHE[key] = result
        while len(_SEARCH_CACHE) > _SEARCH_CACHE_LIMIT:
            _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))


class ToolError(Exception):
    """A tool call that cannot be honoured. Returned to the model as an error
    result so it can recover, never as a silent empty success."""


# --------------------------------------------------------------------------
# Session state -- owned by the application, not the model
# --------------------------------------------------------------------------


@dataclass
class CaseSession:
    case_id: str
    document: dict
    policy: Policy
    grid_revision: int = GRID_REVISION_BASE
    search_result: SearchResult | None = None
    validations: dict[str, ValidationResult] = field(default_factory=dict)
    rejected_candidate_ids: list[str] = field(default_factory=list)
    pending_diff: PolicyDiff | None = None
    widen_used: bool = False
    tool_log: list[dict] = field(default_factory=list)
    memory_hits: list[dict] = field(default_factory=list)

    @classmethod
    def from_document(cls, document: dict, case_id: str | None = None) -> "CaseSession":
        return cls(
            case_id=case_id or f"case_{uuid.uuid4().hex[:10]}",
            document=document,
            policy=policy_from_document(document),
        )

    @property
    def scenario_version(self) -> int:
        return int(self.document["scenario_version"])

    @property
    def horizon_s(self) -> float:
        return float(self.document["horizon_s"])

    def known_windows(self) -> dict[str, BurnWindow]:
        return {
            w["window_id"]: BurnWindow(
                window_id=w["window_id"],
                label=w["label"],
                start_s=float(w["start_s"]),
                end_s=float(w["end_s"]),
            )
            for w in self.document.get("known_windows", ())
        }

    def candidates(self) -> list[Candidate]:
        return generate_candidates(self.grid_revision)

    def candidate_by_id(self, candidate_id: str) -> Candidate:
        for candidate in self.candidates():
            if candidate.candidate_id == candidate_id:
                return candidate
        raise ToolError(
            f"unknown candidate_id {candidate_id!r}; it is not in the active grid "
            f"(revision {self.grid_revision})"
        )

    def version_stamp(self) -> dict:
        return {
            "case_id": self.case_id,
            "scenario_version": self.scenario_version,
            "policy_version": self.policy.policy_version,
            "grid_revision": self.grid_revision,
        }


# --------------------------------------------------------------------------
# Declarations -- flat, OpenAPI subset only
# --------------------------------------------------------------------------

DECLARATIONS: dict[str, dict] = {
    TOOL_BRIEFING: {
        "name": TOOL_BRIEFING,
        "description": (
            "Read the case: the scenario, the active policy, what happens if "
            "nothing is done, and any relevant prior cases. Call this first."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    TOOL_EVALUATE: {
        "name": TOOL_EVALUATE,
        "description": (
            "Screen every option in the active grid against the primary threat "
            "and the active policy. Results are provisional: they cover the "
            "primary threat only and cannot be approved without validation."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    TOOL_VALIDATE: {
        "name": TOOL_VALIDATE,
        "description": (
            "Independently recompute one option against every object in the "
            "scenario over the full horizon. This is the only check that can "
            "clear an option for approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_id": {
                    "type": "string",
                    "description": "An option ID from evaluate_candidates.",
                }
            },
            "required": ["candidate_id"],
        },
    },
    TOOL_PROPOSE_POLICY: {
        "name": TOOL_PROPOSE_POLICY,
        "description": (
            "Turn an operator instruction into a proposed constraint change for "
            "them to confirm. Never applies the change. Give budget_scale for a "
            "relative change such as halving, or max_delta_v_mps for an absolute "
            "limit, but not both. Give blocked_window_id to prohibit burns during "
            "a window named in the scenario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "budget_scale": {
                    "type": "number",
                    "description": (
                        "Multiply the current fuel budget by this factor. Use 0.5 "
                        "for 'halve the budget'. The backend computes the result."
                    ),
                },
                "max_delta_v_mps": {
                    "type": "number",
                    "description": "Absolute fuel budget in metres per second.",
                },
                "blocked_window_id": {
                    "type": "string",
                    "description": (
                        "ID of a window listed in the case briefing. Do not invent "
                        "one; if the operator names a period that is not listed, "
                        "call this with no arguments to request clarification."
                    ),
                },
            },
        },
    },
    TOOL_WIDEN: {
        "name": TOOL_WIDEN,
        "description": (
            "Add smaller-magnitude options to the grid. Available only after an "
            "option has been rejected, once per run. Never relaxes the policy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "enum": [DIMENSION_SMALLER_MAGNITUDES],
                    "description": "The only supported expansion.",
                }
            },
            "required": ["dimension"],
        },
    },
}

_PHASE_TOOLS = {
    PHASE_PLANNING: (TOOL_BRIEFING, TOOL_EVALUATE, TOOL_VALIDATE, TOOL_WIDEN),
    PHASE_POLICY: (TOOL_BRIEFING, TOOL_PROPOSE_POLICY),
}


def declarations_for_phase(phase: str) -> list[dict]:
    """Planning cannot mutate policy; policy interpretation cannot approve."""
    if phase not in _PHASE_TOOLS:
        raise ToolError(f"unknown phase {phase!r}")
    return [DECLARATIONS[name] for name in _PHASE_TOOLS[phase]]


def _assert_flat(schema: dict, path: str = "") -> None:
    """Guard against a generated schema sneaking in later."""
    forbidden = {"$ref", "anyOf", "oneOf", "allOf", "additionalProperties", "$defs"}
    present = forbidden.intersection(schema)
    if present:
        raise ToolError(f"tool schema at {path or '<root>'} uses unsupported keys {sorted(present)}")
    for name, prop in (schema.get("properties") or {}).items():
        _assert_flat(prop, f"{path}.{name}" if path else name)


for _name, _declaration in DECLARATIONS.items():
    _assert_flat(_declaration["parameters"], _name)


# --------------------------------------------------------------------------
# Implementations
# --------------------------------------------------------------------------


def _summarize_encounter(encounter) -> dict:
    return {
        "object_id": encounter.other_object_id,
        "min_separation_m": round(encounter.min_separation_m, 1),
        "tca_s": round(encounter.tca_s, 1),
    }


def get_case_briefing(session: CaseSession) -> dict:
    scenario = reconstruct(session.document)
    baseline_search = evaluate_candidates(
        scenario.satellite,
        scenario.debris[scenario.primary_threat_id],
        scenario.primary_threat_id,
        session.policy,
        scenario.horizon_s,
        candidates=[c for c in session.candidates() if c.is_baseline],
    )
    baseline = baseline_search.baseline

    return {
        **session.version_stamp(),
        "objects": {
            "satellite": scenario.satellite_id,
            "primary_threat": scenario.primary_threat_id,
            "all_debris": sorted(scenario.debris),
        },
        "horizon_s": scenario.horizon_s,
        "policy": {
            "max_delta_v_mps": session.policy.max_delta_v_mps,
            "min_separation_m": session.policy.min_separation_m,
            "blocked_window_ids": [w.window_id for w in session.policy.blocked_windows],
        },
        "known_windows": [
            {"window_id": w.window_id, "label": w.label, "start_s": w.start_s, "end_s": w.end_s}
            for w in session.known_windows().values()
        ],
        "if_nothing_is_done": {
            "closest_approach_m": round(baseline.primary_encounter.min_separation_m, 1),
            "at_t_s": round(baseline.primary_encounter.tca_s, 1),
            "object_id": scenario.primary_threat_id,
            "acceptable": baseline.primary_qualified,
            "reason_codes": list(baseline.reason_codes),
        },
        "option_count_available": len(session.candidates()),
        "relevant_prior_cases": session.memory_hits,
        "note": (
            "Separations are simulated under a two-body model with synthetic "
            "conjunction geometry. No collision probability is computed."
        ),
    }


def evaluate_all(session: CaseSession) -> dict:
    key = _search_cache_key(session)
    result = _cache_get(key)
    cached = result is not None

    if result is None:
        scenario = reconstruct(session.document)
        result = evaluate_candidates(
            scenario.satellite,
            scenario.debris[scenario.primary_threat_id],
            scenario.primary_threat_id,
            session.policy,
            scenario.horizon_s,
            candidates=session.candidates(),
        )
        _cache_put(key, result)

    session.search_result = result

    ranked = [
        {
            "candidate_id": e.candidate.candidate_id,
            "rank": e.rank,
            "delta_v_mps": e.candidate.delta_v_mps,
            "burn_t_s": e.candidate.burn_t_s,
            "direction": e.candidate.direction,
            "primary_separation_m": round(e.primary_encounter.min_separation_m, 1),
        }
        for e in result.qualified
        if not e.candidate.is_baseline
    ][:MAX_LISTED_OPTIONS]

    excluded: dict[str, int] = {}
    for evaluation in result.evaluations:
        if evaluation.primary_qualified:
            continue
        for code in evaluation.reason_codes:
            excluded[code] = excluded.get(code, 0) + 1

    return {
        **session.version_stamp(),
        "status": result.status,
        "candidate_count": result.candidate_count,
        "qualified_count": len([e for e in result.qualified if not e.candidate.is_baseline]),
        "top_options": ranked,
        "excluded_reason_counts": excluded,
        "already_rejected": [
            {
                "candidate_id": e.candidate.candidate_id,
                "delta_v_mps": e.candidate.delta_v_mps,
                "burn_t_s": e.candidate.burn_t_s,
            }
            for e in result.evaluations
            if e.candidate.candidate_id in session.rejected_candidate_ids
        ],
        "from_cache": cached,
        "note": (
            "Provisional: screened against the primary threat only. Call "
            "validate_proposal before treating any option as safe."
        ),
    }


def validate_one(session: CaseSession, candidate_id: str) -> dict:
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ToolError("candidate_id must be a non-empty string")

    candidate = session.candidate_by_id(candidate_id.strip())

    expected = None
    if session.search_result is not None:
        try:
            evaluation = session.search_result.by_id(candidate.candidate_id)
        except KeyError:
            evaluation = None
        if evaluation is not None and evaluation.primary_encounter is not None:
            expected = {
                "min_separation_m": evaluation.primary_encounter.min_separation_m,
                "tca_s": evaluation.primary_encounter.tca_s,
            }

    result = validate_candidate(
        session.document,
        session.policy,
        candidate,
        expected_primary_encounter=expected,
        expected_scenario_version=session.scenario_version,
    )
    session.validations[candidate.candidate_id] = result
    if result.status != STATUS_PASS and candidate.candidate_id not in session.rejected_candidate_ids:
        session.rejected_candidate_ids.append(candidate.candidate_id)

    # Naming the object and the shortfall turns "rejected" into something the
    # planner can act on: it is the difference between knowing an option failed
    # and knowing how much more displacement is needed.
    blocked_by = [
        {
            "object_id": e.other_object_id,
            "min_separation_m": round(e.min_separation_m, 1),
            "shortfall_m": round(session.policy.min_separation_m - e.min_separation_m, 1),
            "tca_s": round(e.tca_s, 1),
        }
        for e in result.encounters
        if e.min_separation_m < session.policy.min_separation_m
    ]

    return {
        **session.version_stamp(),
        "candidate_id": result.candidate_id,
        "validation_id": result.validation_id,
        "status": result.status,
        "reason_codes": list(result.reason_codes),
        "screened_objects": list(result.evaluated_object_ids),
        "encounters": [_summarize_encounter(e) for e in result.encounters],
        "blocked_by": blocked_by,
        "delta_v_mps": candidate.delta_v_mps,
        "burn_t_s": candidate.burn_t_s,
        "approvable": result.approvable,
        "note": (
            "Independent recomputation against every object over the full "
            "horizon, at a finer sample step than the screening pass."
        ),
    }


def propose_policy_change(
    session: CaseSession,
    budget_scale: float | None = None,
    max_delta_v_mps: float | None = None,
    blocked_window_id: str | None = None,
    source_text: str = "",
) -> dict:
    before = session.policy
    changes: list[PolicyChange] = []
    clarification = ""

    if budget_scale is not None and max_delta_v_mps is not None:
        clarification = (
            "Give a relative change (budget_scale) or an absolute limit "
            "(max_delta_v_mps), not both."
        )

    new_budget = before.max_delta_v_mps
    if not clarification and budget_scale is not None:
        try:
            scale = float(budget_scale)
        except (TypeError, ValueError):
            scale = float("nan")
        if not (scale == scale) or scale <= 0.0 or scale > 10.0:
            clarification = f"budget_scale must be a positive number no greater than 10; got {budget_scale!r}."
        else:
            new_budget = round(before.max_delta_v_mps * scale, 6)
            changes.append(
                PolicyChange(
                    field="max_delta_v_mps",
                    before=before.max_delta_v_mps,
                    after=new_budget,
                    note=f"scaled by {scale}",
                )
            )

    if not clarification and max_delta_v_mps is not None:
        try:
            absolute = float(max_delta_v_mps)
        except (TypeError, ValueError):
            absolute = float("nan")
        if not (absolute == absolute) or absolute < 0.0:
            clarification = f"max_delta_v_mps must be a non-negative number; got {max_delta_v_mps!r}."
        else:
            new_budget = round(absolute, 6)
            changes.append(
                PolicyChange(
                    field="max_delta_v_mps", before=before.max_delta_v_mps, after=new_budget
                )
            )

    new_windows = before.blocked_windows
    if not clarification and blocked_window_id is not None:
        known = session.known_windows()
        window = known.get(str(blocked_window_id))
        if window is None:
            clarification = (
                f"No window named {blocked_window_id!r} in this scenario. Known "
                f"windows: {sorted(known) or 'none'}. Ask the operator for the "
                "start and end times rather than guessing."
            )
        elif any(w.window_id == window.window_id for w in before.blocked_windows):
            clarification = f"Window {window.window_id!r} is already blocked."
        else:
            new_windows = before.blocked_windows + (window,)
            changes.append(
                PolicyChange(
                    field="blocked_windows",
                    before=[w.window_id for w in before.blocked_windows],
                    after=[w.window_id for w in new_windows],
                    note=f"{window.label} ({window.start_s:.0f}-{window.end_s:.0f} s)",
                )
            )

    if not clarification and not changes:
        clarification = (
            "No supported change was requested. This tool can scale or set the "
            "fuel budget, or block a window named in the scenario."
        )

    status = STATUS_NEEDS_CLARIFICATION if clarification else STATUS_READY
    after = (
        before
        if clarification
        else Policy(
            policy_version=before.policy_version + 1,
            max_delta_v_mps=new_budget,
            min_separation_m=before.min_separation_m,
            blocked_windows=new_windows,
        )
    )

    diff = PolicyDiff(
        diff_id=f"diff_{uuid.uuid4().hex[:10]}",
        base_policy_version=before.policy_version,
        before=before,
        after=after,
        changes=tuple(changes),
        status=status,
        source_text=source_text,
        clarification=clarification,
    )
    session.pending_diff = diff

    return {
        **session.version_stamp(),
        "diff_id": diff.diff_id,
        "status": diff.status,
        "clarification": diff.clarification,
        "changes": [
            {"field": c.field, "before": c.before, "after": c.after, "note": c.note}
            for c in diff.changes
        ],
        "note": (
            "Proposed only. The operator confirms before anything changes, and "
            "confirming invalidates any pending proposal."
        ),
    }


def widen(session: CaseSession, dimension: str) -> dict:
    if dimension != DIMENSION_SMALLER_MAGNITUDES:
        raise ToolError(
            f"unsupported dimension {dimension!r}; only "
            f"{DIMENSION_SMALLER_MAGNITUDES} is available"
        )
    if not session.rejected_candidate_ids:
        raise ToolError(
            "widen_search is available only after an option has been rejected"
        )
    if session.widen_used:
        raise ToolError("widen_search has already been used once in this run")

    before = len(session.candidates())
    session.grid_revision = GRID_REVISION_EXPANDED
    session.widen_used = True
    after = len(session.candidates())

    return {
        **session.version_stamp(),
        "dimension": dimension,
        "option_count_before": before,
        "option_count_after": after,
        "note": (
            "Grid expanded. The policy is unchanged; widening adds options, it "
            "does not relax a constraint."
        ),
    }


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------


def dispatch(
    session: CaseSession,
    name: str,
    arguments: dict,
    phase: str = PHASE_PLANNING,
    source_text: str = "",
) -> dict:
    """Run one tool call. Unknown tools and bad arguments raise ToolError.

    The caller turns a ToolError into an error result for the model rather than
    an exception, so a recoverable mistake stays recoverable -- but it is never
    reported as a success.
    """
    allowed = _PHASE_TOOLS.get(phase, ())
    if name not in DECLARATIONS:
        raise ToolError(f"unknown tool {name!r}")
    if name not in allowed:
        raise ToolError(f"tool {name!r} is not available during the {phase} phase")

    if not isinstance(arguments, dict):
        raise ToolError(f"arguments for {name!r} must be an object")

    declared = set((DECLARATIONS[name]["parameters"].get("properties") or {}))
    unexpected = set(arguments) - declared
    if unexpected:
        raise ToolError(f"{name!r} received unexpected arguments {sorted(unexpected)}")

    if name == TOOL_BRIEFING:
        return get_case_briefing(session)
    if name == TOOL_EVALUATE:
        return evaluate_all(session)
    if name == TOOL_VALIDATE:
        return validate_one(session, arguments.get("candidate_id", ""))
    if name == TOOL_PROPOSE_POLICY:
        return propose_policy_change(
            session,
            budget_scale=arguments.get("budget_scale"),
            max_delta_v_mps=arguments.get("max_delta_v_mps"),
            blocked_window_id=arguments.get("blocked_window_id"),
            source_text=source_text,
        )
    if name == TOOL_WIDEN:
        return widen(session, arguments.get("dimension", ""))

    raise ToolError(f"tool {name!r} has no implementation")


def apply_diff(session: CaseSession, diff_id: str) -> Policy:
    """Confirm a pending diff. Human-gated; not reachable from any model tool.

    Applying invalidates prior validations, because they were computed under the
    old policy.
    """
    diff = session.pending_diff
    if diff is None or diff.diff_id != diff_id:
        raise ToolError(f"no pending policy change with id {diff_id!r}")
    if diff.status != STATUS_READY:
        raise ToolError(f"policy change {diff_id!r} is {diff.status}, not {STATUS_READY}")
    if diff.base_policy_version != session.policy.policy_version:
        raise ToolError(
            f"policy change {diff_id!r} was built against version "
            f"{diff.base_policy_version}, current is {session.policy.policy_version}"
        )

    session.policy = diff.after
    session.pending_diff = None
    session.search_result = None
    session.validations.clear()
    session.rejected_candidate_ids.clear()
    return session.policy
