"""Numerical workspace comparison. No LLM, proposal, approval or execution."""

from dataclasses import asdict
from time import perf_counter

from backend.planning.candidates import DESIGNED_PREFIX
from backend.agent.tools import CaseSession, evaluate_all, validate_one


def analyze(session: CaseSession) -> dict:
    started = perf_counter()
    evaluate_all(session)
    search = session.search_result
    assert search is not None
    checks = {}
    recommended = None
    # Verify the baseline too: it is the right answer for a clear scenario.
    for evaluation in search.qualified:
        candidate_id = evaluation.candidate.candidate_id
        checks[candidate_id] = validate_one(session, candidate_id)
        if recommended is None and checks[candidate_id]["status"] == "PASS":
            recommended = candidate_id
    options = []
    for evaluation in search.evaluations:
        options.append({
            **asdict(evaluation.candidate),
            "primary_qualified": evaluation.primary_qualified,
            "primary_encounter": asdict(evaluation.primary_encounter) if evaluation.primary_encounter else None,
            "reason_codes": list(evaluation.reason_codes),
            "rank": evaluation.rank,
            "validation": checks.get(evaluation.candidate.candidate_id),
            # Whether this burn came off the grid or the planner designed it.
            # Worth showing: an operator comparing options should be able to see
            # which one no enumeration would have offered them.
            "designed": evaluation.candidate.candidate_id.startswith(
                DESIGNED_PREFIX
            ),
        })
    return {
        **session.version_stamp(),
        "mode": "NUMERICAL_ANALYSIS",
        "status": "VERIFIED_OPTION" if recommended else "NO_VERIFIED_OPTION",
        "candidate_count": search.candidate_count,
        "qualified_count": len(search.qualified),
        "recommended_id": recommended,
        "options": options,
        "elapsed_s": round(perf_counter() - started, 3),
        "note": "Deterministic comparison of this grid only. No model calls or approval. The AI planner and reviewer run separately.",
    }
