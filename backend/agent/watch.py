"""The autonomous watch: detect, triage, plan, review, coordinate -- then ask.

One call runs the whole chain with no operator input until the single step that
must stay human, authorising a burn:

1. **Detect.** The committed catalogue screen: every Iridium NEXT satellite
   against every catalogued fragment.
2. **Triage (AI).** The triage agent decides which passes matter and assesses
   them with its tools.
3. **Plan and verify.** Each assessment estimates avoidance burns and re-screens
   the best against every fragment -- deterministic, not the model.
4. **Safety review (AI).** A separate reviewer reads each recommended burn's
   evidence and can block it. A reviewer that does not answer blocks too.
5. **Coordinate.** A pass against a debris fragment needs no negotiation: the
   fragment cannot move. The simulated two-operator case is checked with both
   plans together and the published who-moves rule.
6. **Decide.** Everything lands in one queue. Only an operator can approve, and
   approval is recorded as simulated -- nothing is transmitted.

Every step is written to a timeline with who did it, so a reader can see which
parts were the agents and which were deterministic checks.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from backend.agent.llm import LLMError, Message, Provider
from backend.agent.reviewer import (
    DECISION_ALLOW,
    DECISION_BLOCK,
    DECISION_UNAVAILABLE,
    _parse,
)
from backend.agent.tracker import COMFORTABLE_KM, TriageLimits, triage

REPO_ROOT = Path(__file__).resolve().parents[2]
PARTNER_FIXTURE = REPO_ROOT / "scenarios" / "variants" / "two_operators.json"

ESTIMATE_AGREEMENT_KM = 0.1

REVIEW_PROMPT = """You are the safety reviewer for an avoidance burn recommended for a real close
approach between an Iridium NEXT communications satellite and a catalogued
debris fragment. The burn was estimated and then re-screened against every
catalogued fragment by deterministic code; you read that evidence and decide
whether anything should still stop it.

Block if the re-screened closest approach is below the comfortable margin, if
the estimate and the re-screen of this pass disagree by more than the stated
tolerance, if the burn is marked as creating a new close approach, or if
evidence is missing. Allow if the evidence supports the burn.

Reply with JSON only:
{"decision": "ALLOW" or "BLOCK", "reason_codes": ["..."], "rationale": "one sentence"}

Do not restate numbers you were not given. Do not compute anything."""

ACTOR_SCREEN = "Screening engine"
ACTOR_TRIAGE = "Triage agent (AI)"
ACTOR_ASSESS = "Avoidance engine"
ACTOR_REVIEW = "Safety reviewer (AI)"
ACTOR_COORDINATE = "Coordination check"
ACTOR_QUEUE = "Decision queue"


class Timeline:
    def __init__(self, on_step: Callable[[str, str, str, int], None] | None) -> None:
        self.started = time.perf_counter()
        self.entries: list[dict] = []
        self.on_step = on_step

    def add(self, stage: str, actor: str, summary: str) -> None:
        entry = {
            "sequence": len(self.entries) + 1,
            "t_s": round(time.perf_counter() - self.started, 1),
            "stage": stage,
            "actor": actor,
            "summary": summary,
        }
        self.entries.append(entry)
        if self.on_step is not None:
            try:
                self.on_step(stage, actor, summary, entry["sequence"])
            except Exception:  # noqa: BLE001 - progress must never fail the run
                pass


def _recommended(assessment: dict) -> dict | None:
    return next(
        (o for o in assessment["options"] if o["option_id"] == assessment["recommended_option_id"]),
        None,
    )


def review_burn(provider: Provider | None, assessment: dict) -> dict:
    """The AI reviewer's verdict on one recommended burn. Fails closed."""
    chosen = _recommended(assessment)
    if chosen is None or chosen["direction"] is None:
        return {"decision": DECISION_BLOCK, "reason_codes": ["NO_BURN_TO_REVIEW"], "rationale": ""}
    evidence = {
        "pass": assessment["conjunction"],
        "burn": {
            "direction": chosen["direction"],
            "delta_v_mps": chosen["delta_v_mps"],
            "minutes_before_pass": chosen["lead_minutes"],
        },
        "estimated_miss_km": chosen["predicted_miss_km"],
        "rescreen_this_pass_km": chosen.get("rescreen_assessed_miss_km"),
        "rescreen_closest_any_fragment_km": chosen.get("rescreen_closest_km"),
        "rescreen_fragments": assessment["rescreen"]["fragments"],
        "rescreen_hours_after_burn": assessment["rescreen"]["hours_after_burn"],
        "creates_new_close_approach": chosen.get("verdict") == "BLOCK",
        "comfortable_margin_km": assessment["comfortable_km"],
        "estimate_agreement_tolerance_km": ESTIMATE_AGREEMENT_KM,
        "method": "SGP4 geometry, Clohessy-Wiltshire burn displacement, re-screen against every fragment",
    }
    if provider is None:
        return {"decision": DECISION_UNAVAILABLE, "reason_codes": ["NO_REVIEWER"],
                "rationale": "No reviewer model is configured, so the burn cannot be allowed."}
    try:
        response = provider.call(REVIEW_PROMPT, [Message(role="user", text=json.dumps(evidence, indent=1))], tools=[])
    except LLMError as exc:
        return {"decision": DECISION_UNAVAILABLE, "reason_codes": ["REVIEWER_ERROR"],
                "rationale": f"Reviewer could not be reached: {str(exc)[:200]}"}
    parsed = _parse(response.text)
    if parsed is None or parsed.get("decision") not in (DECISION_ALLOW, DECISION_BLOCK):
        return {"decision": DECISION_UNAVAILABLE, "reason_codes": ["REVIEWER_UNPARSEABLE"],
                "rationale": "Reviewer reply could not be read as a decision."}
    codes = parsed.get("reason_codes") or []
    return {
        "decision": parsed["decision"],
        "reason_codes": [str(c) for c in (codes if isinstance(codes, list) else [codes])],
        "rationale": str(parsed.get("rationale", ""))[:400],
    }


def _partner_item(timeline: Timeline) -> dict | None:
    """The simulated two-operator case, checked the same way every run."""
    from backend.coordination import coordinate
    from backend.planning.policy import policy_from_document

    if not PARTNER_FIXTURE.exists():
        return None
    document = json.loads(PARTNER_FIXTURE.read_text(encoding="utf-8"))
    result = coordinate(document, policy_from_document(document))
    plans = {p["plan_id"]: p for p in result["plans"]}
    agreed = plans.get(result["agreed_plan_id"])
    both = plans.get("both_as_planned")
    ours = result["operators"][0]
    burn = agreed["burns"].get(ours["object_id"]) if agreed else None
    timeline.add(
        "COORDINATE", ACTOR_COORDINATE,
        f"Simulated partner satellite: each operator's own burn works alone, both together pass "
        f"{both['closest_m']} m apart; the rule picks: {agreed['label'] if agreed else 'no safe joint plan'}.",
    )
    return {
        "item_id": "simulated-two-operators",
        "source": "SIMULATED",
        "satellite": "NOAA 20 (simulated case)",
        "threat": "Partner operator's satellite (simulated)",
        "threat_can_move": True,
        "tca_utc": None,
        "miss_km": round(result["if_nobody_moves"]["closest_m"] / 1000.0, 4),
        "status": "AWAITING_APPROVAL" if agreed else "ESCALATE",
        "recommendation": {
            "direction": burn["direction"], "delta_v_mps": burn["delta_v_mps"],
            "burn_t_s": burn["burn_t_s"],
        } if burn else None,
        "estimated_miss_km": round(agreed["closest_m"] / 1000.0, 4) if agreed else None,
        "rescreen_closest_km": round(agreed["closest_m"] / 1000.0, 4) if agreed else None,
        "reviewer": None,
        "coordination": {
            "needed": True,
            "both_as_planned_m": both["closest_m"] if both else None,
            "agreed_plan": agreed["label"] if agreed else None,
            "movers": agreed["movers"] if agreed else [],
            "rule": result["rule"],
        },
    }


def run_watch(
    provider_factory: Callable[[], Provider],
    reviewer_factory: Callable[[], Provider] | None,
    screen: dict,
    conjunctions: list[dict],
    assess_fn: Callable,
    on_step: Callable[[str, str, str, int], None] | None = None,
    limits: TriageLimits | None = None,
    include_partner_case: bool = True,
) -> dict:
    timeline = Timeline(on_step)
    catalog = screen["catalog"]
    timeline.add(
        "DETECT", ACTOR_SCREEN,
        f"Screened {catalog['protected_count']} Iridium NEXT satellites against "
        f"{catalog['debris_count']:,} catalogued fragments: {screen['conjunction_count']:,} passes under "
        f"{screen['report_threshold_km']:g} km, "
        f"{sum(c['miss_km'] < COMFORTABLE_KM for c in conjunctions)} under {COMFORTABLE_KM} km.",
    )

    def forward(event) -> None:
        if event.event_type in ("tool_result", "tool_error", "model_conclusion", "guard_flag", "model_error"):
            stage = "PLAN" if "Assessed" in event.summary else "TRIAGE"
            actor = ACTOR_ASSESS if stage == "PLAN" else ACTOR_TRIAGE
            timeline.add(stage, actor, event.summary)

    timeline.add("TRIAGE", ACTOR_TRIAGE, "Deciding which passes need attention.")
    outcome = triage(provider_factory(), screen, conjunctions, assess_fn, limits=limits, on_event=forward)

    items: list[dict] = []
    burns = [i for i in outcome["triage"] if i["status"] == "NEEDS_BURN"]
    assessments = {
        i["pass_id"]: assess_fn(*_ids(conjunctions, i["pass_id"]))
        for i in burns
    }

    if burns:
        timeline.add("REVIEW", ACTOR_REVIEW, f"Reviewing {len(burns)} recommended burn(s) independently.")
        with ThreadPoolExecutor(max_workers=3) as pool:
            verdicts = dict(zip(
                [i["pass_id"] for i in burns],
                pool.map(lambda i: review_burn(reviewer_factory() if reviewer_factory else None,
                                               assessments[i["pass_id"]]), burns),
            ))
    else:
        verdicts = {}

    for item in outcome["triage"]:
        conjunction = next(c for c in conjunctions if _pass_key(c) == item["pass_id"])
        verdict = verdicts.get(item["pass_id"])
        if item["status"] == "NEEDS_BURN":
            allowed = verdict is not None and verdict["decision"] == DECISION_ALLOW
            status = "AWAITING_APPROVAL" if allowed else "BLOCKED_BY_REVIEWER"
            timeline.add(
                "REVIEW", ACTOR_REVIEW,
                f"{item['satellite']}: {verdict['decision'] if verdict else 'no verdict'}"
                + (f" - {verdict['rationale']}" if verdict and verdict.get("rationale") else ""),
            )
            chosen = _recommended(assessments[item["pass_id"]])
            recommendation = {
                "direction": chosen["direction"], "delta_v_mps": chosen["delta_v_mps"],
                "minutes_before": chosen["lead_minutes"],
            } if chosen else None
        else:
            status = "NO_ACTION" if item["status"] == "CLEAR" else "ESCALATE"
            recommendation = None
        items.append({
            "item_id": item["pass_id"],
            "source": "REAL",
            "satellite": item["satellite"],
            "threat": f"{conjunction['debris']['name']} {conjunction['debris']['norad_id']}",
            "threat_event": conjunction["debris"]["event"],
            "threat_can_move": False,
            "tca_utc": conjunction["tca_utc"],
            "miss_km": item["miss_km"],
            "relative_speed_kms": item["relative_speed_kms"],
            "status": status,
            "recommendation": recommendation,
            "estimated_miss_km": item["estimated_miss_km"],
            "rescreen_closest_km": item["rescreen_closest_km"],
            "rescreen_fragments": catalog["debris_count"],
            "reviewer": verdict,
            "coordination": {"needed": False, "reason": "The other object is a debris fragment and cannot manoeuvre."},
        })

    real_needing = [i for i in items if i["status"] in ("AWAITING_APPROVAL", "BLOCKED_BY_REVIEWER")]
    timeline.add(
        "COORDINATE", ACTOR_COORDINATE,
        f"{len(real_needing)} real pass(es) are against debris, which cannot move: no negotiation needed.",
    )
    if include_partner_case:
        partner = _partner_item(timeline)
        if partner is not None:
            items.append(partner)

    order = {"AWAITING_APPROVAL": 0, "BLOCKED_BY_REVIEWER": 1, "ESCALATE": 2, "NO_ACTION": 3}
    items.sort(key=lambda i: (order[i["status"]], i["source"] != "REAL", i["miss_km"]))
    waiting = sum(i["status"] == "AWAITING_APPROVAL" for i in items)
    timeline.add("DECIDE", ACTOR_QUEUE, f"{waiting} decision(s) waiting for an operator to approve.")

    return {
        "status": "QUEUE_READY" if outcome["status"] == "BRIEF_READY" else "PARTIAL",
        "triage_status": outcome["status"],
        "unresolved_reason": outcome["unresolved_reason"],
        "brief": outcome["brief"],
        "flagged_numbers": outcome["flagged_numbers"],
        "queue": items,
        "timeline": timeline.entries,
        "model_calls": outcome["model_calls"] + len(burns),
        "elapsed_s": round(time.perf_counter() - timeline.started, 1),
        "note": (
            "Agents detected, triaged, planned, reviewed and checked coordination without "
            "operator input. Approval is the operator's and is simulated: nothing is transmitted."
        ),
    }


def _pass_key(conjunction: dict) -> str:
    from backend.agent.tracker import pass_id

    return pass_id(conjunction)


def _ids(conjunctions: list[dict], key: str) -> tuple[int, int, str]:
    conjunction = next(c for c in conjunctions if _pass_key(c) == key)
    return conjunction["protected"]["norad_id"], conjunction["debris"]["norad_id"], conjunction["tca_utc"]
