"""HTTP surface. Owns versions, run coordination, approval and export.

Three things this layer exists to enforce.

*Version gating.* Every mutating request states the scenario and policy version
it was composed against. A mismatch is a 409, so a late click from a superseded
view cannot act on stale evidence.

*Approval is not the model's to give.* The approve endpoint re-reads the stored
validation and the reviewer verdict and refuses unless the deterministic result
passed and the reviewer allowed. It does not consult the planner's text.

*Failures are typed.* A tool error, a provider outage or a numerical failure
becomes an explicit event and a non-2xx response. Nothing here returns a
successful empty result.
"""

from __future__ import annotations

import csv
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import store as store_module
from backend.agent.llm import GeminiProvider, LLMError, Provider
from backend.agent.memory import CaseMemory
from backend.agent.planner import (
    STATUS_PROPOSAL_READY,
    PlannerLimits,
    interpret_instruction,
    plan_case,
)
from backend.agent.tools import CaseSession, ToolError, apply_diff
from backend.planning.candidates import Candidate, generate_candidates
from backend.planning.policy import STATUS_READY as DIFF_READY
from backend.planning.policy import Policy, policy_from_document
from backend.planning.verifier import MODEL_VERSION, STATUS_PASS, reconstruct
from backend.store import IdempotencyConflict, Store, StoreError
from backend.visualization import DEFAULT_SAMPLE_STEP_S, build_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = REPO_ROOT / "scenarios"
SOCRATES_CSV = REPO_ROOT / "data" / "context" / "socrates_snapshot.csv"
SOCRATES_PROVENANCE = REPO_ROOT / "data" / "context" / "socrates_provenance.json"

SOCRATES_MAX_ROWS = 10

RUN_RUNNING = "RUNNING"
RUN_DONE = "DONE"
RUN_FAILED = "FAILED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------


class VersionedRequest(BaseModel):
    expected_scenario_version: int = Field(..., ge=0)
    expected_policy_version: int = Field(..., ge=0)


class CreateCaseRequest(BaseModel):
    scenario_id: str = "primary"


class PlanRequest(VersionedRequest):
    instruction: str = ""


class PolicyPreviewRequest(VersionedRequest):
    text: str = Field(..., min_length=1, max_length=2000)


class PolicyConfirmRequest(VersionedRequest):
    diff_id: str


class ApproveRequest(VersionedRequest):
    proposal_id: str
    idempotency_key: str = Field(..., min_length=1, max_length=200)


class ResetRequest(VersionedRequest):
    pass


# --------------------------------------------------------------------------
# Run registry
# --------------------------------------------------------------------------


@dataclass
class RunState:
    run_id: str
    case_id: str
    kind: str
    status: str = RUN_RUNNING
    started_at_utc: str = field(default_factory=_now)
    finished_at_utc: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class AppState:
    def __init__(
        self,
        store: Store,
        provider_factory: Callable[[], Provider],
        reviewer_factory: Callable[[], Provider] | None,
        memory: CaseMemory | None,
        scenarios_dir: Path,
        limits: PlannerLimits,
    ) -> None:
        self.store = store
        self.provider_factory = provider_factory
        self.reviewer_factory = reviewer_factory
        self.memory = memory
        self.scenarios_dir = scenarios_dir
        self.limits = limits
        self.runs: dict[str, RunState] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.lock = threading.Lock()

    def scenario_path(self, scenario_id: str) -> Path:
        direct = self.scenarios_dir / f"{scenario_id}.json"
        variant = self.scenarios_dir / "variants" / f"{scenario_id}.json"
        if direct.exists():
            return direct
        if variant.exists():
            return variant
        raise HTTPException(404, f"unknown scenario {scenario_id!r}")

    def runs_for(self, case_id: str) -> list[dict]:
        with self.lock:
            return [r.as_dict() for r in self.runs.values() if r.case_id == case_id]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _default_provider_factory() -> Provider:
    return GeminiProvider()


def _state(request: Request) -> AppState:
    return request.app.state.desk


def _case_or_404(state: AppState, case_id: str):
    try:
        return state.store.get_case(case_id)
    except StoreError as exc:
        raise HTTPException(404, str(exc)) from exc


def _check_versions(case_row, expected_scenario: int, expected_policy: int) -> None:
    if case_row.scenario_version != expected_scenario or case_row.policy_version != expected_policy:
        raise HTTPException(
            409,
            {
                "error": "STALE_VERSION",
                "message": (
                    "This request was composed against an older version of the case. "
                    "Reload before acting."
                ),
                "expected_scenario_version": expected_scenario,
                "actual_scenario_version": case_row.scenario_version,
                "expected_policy_version": expected_policy,
                "actual_policy_version": case_row.policy_version,
            },
        )


def _session_for(case_row) -> CaseSession:
    session = CaseSession.from_document(case_row.document, case_id=case_row.case_id)
    session.policy = case_row.policy
    session.grid_revision = case_row.grid_revision
    return session


def _persist_run(state: AppState, case_row, session: CaseSession, outcome, run_id: str) -> None:
    store = state.store
    store.append_events(case_row.case_id, run_id, outcome.events)
    for validation in session.validations.values():
        store.save_validation(case_row.case_id, validation)
    if outcome.proposal is not None:
        store.save_proposal(case_row.case_id, outcome.proposal)
    store.set_grid_revision(case_row.case_id, session.grid_revision)


def _snapshot(state: AppState, case_id: str) -> dict:
    store = state.store
    case_row = _case_or_404(state, case_id)
    document = case_row.document
    execution = store.execution_for_case(case_id)
    proposal = store.latest_proposal(case_id)

    return {
        "case_id": case_row.case_id,
        "parent_case_id": case_row.parent_case_id,
        "scenario_id": case_row.scenario_id,
        "scenario_version": case_row.scenario_version,
        "policy_version": case_row.policy_version,
        "grid_revision": case_row.grid_revision,
        "created_at_utc": case_row.created_at_utc,
        "scenario": {
            "description": document.get("description", ""),
            "horizon_s": document["horizon_s"],
            "epoch_utc": document["epoch_utc"],
            "satellite_id": document["satellite_id"],
            "primary_threat_id": document["primary_threat_id"],
            "objects": [
                {"object_id": o["object_id"], "name": o["name"], "kind": o["kind"]}
                for o in document["objects"]
            ],
            "known_windows": document.get("known_windows", []),
            "provenance": document["provenance"],
            "input_hash": document.get("input_hash", ""),
        },
        "policy": {
            "policy_version": case_row.policy.policy_version,
            "max_delta_v_mps": case_row.policy.max_delta_v_mps,
            "min_separation_m": case_row.policy.min_separation_m,
            "blocked_windows": [
                {"window_id": w.window_id, "label": w.label, "start_s": w.start_s, "end_s": w.end_s}
                for w in case_row.policy.blocked_windows
            ],
        },
        "pending_diff": case_row.pending_diff,
        "validations": [
            {
                "validation_id": v.validation_id,
                "candidate_id": v.candidate_id,
                "status": v.status,
                "reason_codes": list(v.reason_codes),
                "screened_objects": list(v.evaluated_object_ids),
                "encounters": [
                    {
                        "object_id": e.other_object_id,
                        "min_separation_m": e.min_separation_m,
                        "tca_s": e.tca_s,
                        "relative_speed_mps": e.relative_speed_mps,
                        "boundary_kind": e.boundary_kind,
                        "ambiguous_time": e.ambiguous_time,
                    }
                    for e in v.encounters
                ],
                "max_primary_distance_disagreement_m": v.max_primary_distance_disagreement_m,
                "primary_time_disagreement_s": v.primary_time_disagreement_s,
                "sample_step_s": v.sample_step_s,
                "method": v.method,
            }
            for v in store.validations(case_id)
        ],
        "proposal": proposal,
        "execution": asdict(execution) if execution else None,
        "events": store.events(case_id),
        "runs": state.runs_for(case_id),
    }


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------


def create_app(
    store: Store | None = None,
    provider_factory: Callable[[], Provider] | None = None,
    reviewer_factory: Callable[[], Provider] | None = None,
    memory: CaseMemory | None = None,
    scenarios_dir: Path | None = None,
    limits: PlannerLimits | None = None,
) -> FastAPI:
    app = FastAPI(title="Satellite Demo", version="0.1.0")

    # Open during the event so the Vite dev server can call this directly.
    # Narrow it before anything is exposed beyond a laptop.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.desk = AppState(
        store=store or Store(":memory:"),
        provider_factory=provider_factory or _default_provider_factory,
        reviewer_factory=reviewer_factory,
        memory=memory,
        scenarios_dir=scenarios_dir or SCENARIOS_DIR,
        limits=limits or PlannerLimits(),
    )

    # ---------------------------------------------------------------- cases

    @app.post("/cases", status_code=201)
    def create_case(payload: CreateCaseRequest, request: Request) -> dict:
        state = _state(request)
        path = state.scenario_path(payload.scenario_id)
        document = json.loads(path.read_text(encoding="utf-8"))
        case_row = state.store.create_case(document, policy_from_document(document))
        return _snapshot(state, case_row.case_id)

    @app.get("/cases/{case_id}")
    def get_case(case_id: str, request: Request) -> dict:
        return _snapshot(_state(request), case_id)

    # ----------------------------------------------------------------- plan

    @app.post("/cases/{case_id}/plan", status_code=202)
    def start_plan(case_id: str, payload: PlanRequest, request: Request) -> dict:
        state = _state(request)
        case_row = _case_or_404(state, case_id)
        _check_versions(case_row, payload.expected_scenario_version, payload.expected_policy_version)

        run = RunState(run_id=f"run_{uuid.uuid4().hex[:10]}", case_id=case_id, kind="plan")
        with state.lock:
            state.runs[run.run_id] = run

        def work() -> None:
            try:
                session = _session_for(case_row)
                provider = state.provider_factory()
                reviewer = state.reviewer_factory() if state.reviewer_factory else None
                outcome = plan_case(
                    provider,
                    session,
                    limits=state.limits,
                    memory=state.memory,
                    reviewer_provider=reviewer,
                    instruction=payload.instruction,
                )
                _persist_run(state, case_row, session, outcome, run.run_id)
                run.result = {
                    "status": outcome.status,
                    "unresolved_reason": outcome.unresolved_reason,
                    "proposal_id": outcome.proposal.proposal_id if outcome.proposal else None,
                    "model_calls": outcome.model_calls,
                    "tool_calls": outcome.tool_calls,
                    "validations_run": outcome.validations_run,
                    "elapsed_s": outcome.elapsed_s,
                    "flagged_numbers": list(outcome.flagged_numbers),
                }
                run.status = RUN_DONE
            except Exception as exc:  # noqa: BLE001
                # Deliberately broad. A worker that dies on an unanticipated
                # exception would leave the run RUNNING forever, and the UI
                # would poll a case that is never coming back. Every failure
                # has to become a visible FAILED run.
                run.status = RUN_FAILED
                run.error = f"{type(exc).__name__}: {exc}"
            finally:
                run.finished_at_utc = _now()

        state.executor.submit(work)
        return {"run_id": run.run_id, "status": run.status, "case_id": case_id}

    @app.get("/runs/{run_id}")
    def get_run(run_id: str, request: Request) -> dict:
        state = _state(request)
        with state.lock:
            run = state.runs.get(run_id)
        if run is None:
            raise HTTPException(404, f"unknown run {run_id!r}")
        return run.as_dict()

    # --------------------------------------------------------------- policy

    @app.post("/cases/{case_id}/policy-preview")
    def policy_preview(case_id: str, payload: PolicyPreviewRequest, request: Request) -> dict:
        state = _state(request)
        case_row = _case_or_404(state, case_id)
        _check_versions(case_row, payload.expected_scenario_version, payload.expected_policy_version)

        session = _session_for(case_row)
        try:
            diff, events, model_calls = interpret_instruction(
                state.provider_factory(), session, payload.text
            )
        except LLMError as exc:
            raise HTTPException(503, {"error": "PROVIDER_ERROR", "message": str(exc)}) from exc

        state.store.append_events(case_id, None, events)
        if session.pending_diff is not None:
            state.store.set_pending_diff(
                case_id,
                {
                    "diff_id": session.pending_diff.diff_id,
                    "status": session.pending_diff.status,
                    "clarification": session.pending_diff.clarification,
                    "source_text": session.pending_diff.source_text,
                    "base_policy_version": session.pending_diff.base_policy_version,
                    "changes": [
                        {"field": c.field, "before": c.before, "after": c.after, "note": c.note}
                        for c in session.pending_diff.changes
                    ],
                    "after": {
                        "policy_version": session.pending_diff.after.policy_version,
                        "max_delta_v_mps": session.pending_diff.after.max_delta_v_mps,
                        "min_separation_m": session.pending_diff.after.min_separation_m,
                        "blocked_windows": [
                            {
                                "window_id": w.window_id,
                                "label": w.label,
                                "start_s": w.start_s,
                                "end_s": w.end_s,
                            }
                            for w in session.pending_diff.after.blocked_windows
                        ],
                    },
                },
            )

        if diff is None:
            raise HTTPException(
                422,
                {
                    "error": "NO_CHANGE_PROPOSED",
                    "message": "The instruction did not map onto a supported constraint change.",
                    "model_calls": model_calls,
                },
            )
        return {"diff": diff, "model_calls": model_calls}

    @app.post("/cases/{case_id}/policy-confirm")
    def policy_confirm(case_id: str, payload: PolicyConfirmRequest, request: Request) -> dict:
        state = _state(request)
        case_row = _case_or_404(state, case_id)
        _check_versions(case_row, payload.expected_scenario_version, payload.expected_policy_version)

        pending = case_row.pending_diff
        if pending is None or pending["diff_id"] != payload.diff_id:
            raise HTTPException(404, f"no pending policy change with id {payload.diff_id!r}")
        if pending["status"] != DIFF_READY:
            raise HTTPException(
                409,
                {
                    "error": "DIFF_NOT_READY",
                    "message": pending.get("clarification", "The change needs clarification."),
                },
            )

        after = pending["after"]
        from backend.planning.policy import BurnWindow

        new_policy = Policy(
            policy_version=case_row.policy_version + 1,
            max_delta_v_mps=float(after["max_delta_v_mps"]),
            min_separation_m=float(after["min_separation_m"]),
            blocked_windows=tuple(
                BurnWindow(
                    window_id=w["window_id"],
                    label=w["label"],
                    start_s=float(w["start_s"]),
                    end_s=float(w["end_s"]),
                )
                for w in after.get("blocked_windows", ())
            ),
        )
        state.store.update_policy(case_id, new_policy)
        return {
            "case_id": case_id,
            "policy_version": new_policy.policy_version,
            "policy": {
                "max_delta_v_mps": new_policy.max_delta_v_mps,
                "min_separation_m": new_policy.min_separation_m,
                "blocked_windows": [w.window_id for w in new_policy.blocked_windows],
            },
            "invalidated_proposals": True,
            "note": (
                "Prior proposals are marked stale because they were computed under "
                "the previous policy. Plan again to get a fresh result."
            ),
        }

    # -------------------------------------------------------- visualization

    @app.get("/cases/{case_id}/visualization")
    def visualization(
        case_id: str,
        request: Request,
        candidate_ids: str = Query(..., description="Comma-separated, at most three"),
        expected_scenario_version: int = Query(...),
        expected_policy_version: int = Query(...),
        sample_step_s: float = Query(DEFAULT_SAMPLE_STEP_S, gt=0.0, le=600.0),
    ) -> dict:
        state = _state(request)
        case_row = _case_or_404(state, case_id)
        _check_versions(case_row, expected_scenario_version, expected_policy_version)

        wanted = [c.strip() for c in candidate_ids.split(",") if c.strip()]
        if not wanted:
            raise HTTPException(422, "candidate_ids must name at least one option")
        if len(wanted) > 3:
            raise HTTPException(422, "at most three variants per request")

        available = {c.candidate_id: c for c in generate_candidates(case_row.grid_revision)}
        selected: list[Candidate] = []
        for candidate_id in wanted:
            if candidate_id not in available:
                raise HTTPException(404, f"unknown candidate_id {candidate_id!r}")
            selected.append(available[candidate_id])

        scenario = reconstruct(case_row.document)
        return build_bundle(
            scenario=scenario,
            candidates=selected,
            case_id=case_id,
            policy_version=case_row.policy_version,
            epoch_utc=case_row.document["epoch_utc"],
            model_version=MODEL_VERSION,
            min_separation_m=case_row.policy.min_separation_m,
            sample_step_s=sample_step_s,
        )

    # -------------------------------------------------------------- approve

    @app.post("/cases/{case_id}/approve")
    def approve(case_id: str, payload: ApproveRequest, request: Request) -> dict:
        state = _state(request)
        case_row = _case_or_404(state, case_id)
        _check_versions(case_row, payload.expected_scenario_version, payload.expected_policy_version)

        try:
            proposal = state.store.get_proposal(payload.proposal_id)
        except StoreError as exc:
            raise HTTPException(404, str(exc)) from exc

        if proposal["case_id"] != case_id:
            raise HTTPException(404, "proposal does not belong to this case")

        if (
            proposal["scenario_version"] != case_row.scenario_version
            or proposal["policy_version"] != case_row.policy_version
        ):
            raise HTTPException(
                409,
                {
                    "error": "PROPOSAL_STALE",
                    "message": "The proposal was computed under a different version of the case.",
                },
            )
        if proposal.get("status") == store_module.PROPOSAL_STALE:
            raise HTTPException(409, {"error": "PROPOSAL_STALE", "message": "Proposal superseded."})

        # Re-read the deterministic result rather than trusting the proposal row.
        try:
            validation = state.store.get_validation(proposal["validation_id"])
        except StoreError as exc:
            raise HTTPException(409, {"error": "MISSING_EVIDENCE", "message": str(exc)}) from exc

        if validation.status != STATUS_PASS:
            raise HTTPException(
                409,
                {
                    "error": "NOT_VALIDATED",
                    "message": "Validation did not pass; this cannot be approved.",
                    "reason_codes": list(validation.reason_codes),
                },
            )

        verdict = proposal.get("reviewer_verdict")
        if verdict is not None and verdict.get("decision") != "ALLOW":
            raise HTTPException(
                409,
                {
                    "error": "REVIEWER_BLOCKED",
                    "message": "The safety reviewer did not allow this proposal.",
                    "decision": verdict.get("decision"),
                    "reason_codes": verdict.get("reason_codes", []),
                },
            )

        try:
            record, created = state.store.record_execution(
                case_id=case_id,
                proposal_id=payload.proposal_id,
                candidate_id=proposal["candidate_id"],
                idempotency_key=payload.idempotency_key,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(409, {"error": "IDEMPOTENCY_CONFLICT", "message": str(exc)}) from exc

        return {
            "execution": asdict(record),
            "created": created,
            "note": (
                "Simulated execution only. Nothing is transmitted to any spacecraft."
            ),
        }

    # ---------------------------------------------------------------- reset

    @app.post("/cases/{case_id}/reset", status_code=201)
    def reset(case_id: str, payload: ResetRequest, request: Request) -> dict:
        state = _state(request)
        case_row = _case_or_404(state, case_id)
        _check_versions(case_row, payload.expected_scenario_version, payload.expected_policy_version)

        document = json.loads(state.scenario_path(case_row.scenario_id).read_text(encoding="utf-8"))
        fresh = state.store.create_case(
            document, policy_from_document(document), parent_case_id=case_id
        )
        return _snapshot(state, fresh.case_id)

    # --------------------------------------------------------------- export

    @app.get("/cases/{case_id}/export")
    def export(case_id: str, request: Request, format: str = Query("json", pattern="^(json|markdown)$")):
        state = _state(request)
        snapshot = _snapshot(state, case_id)
        if format == "json":
            return snapshot
        return PlainTextResponse(
            _markdown_report(snapshot), media_type="text/markdown; charset=utf-8"
        )

    # -------------------------------------------------------------- context

    @app.get("/context/socrates")
    def socrates(request: Request) -> dict:
        if not SOCRATES_CSV.exists():
            raise HTTPException(404, "SOCRATES snapshot not present; run scripts/fetch_snapshots.py")

        with SOCRATES_CSV.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))[:SOCRATES_MAX_ROWS]

        provenance = (
            json.loads(SOCRATES_PROVENANCE.read_text(encoding="utf-8"))
            if SOCRATES_PROVENANCE.exists()
            else {}
        )
        return {
            "rows": rows,
            "row_count": len(rows),
            "source_url": provenance.get("source_url", ""),
            "retrieved_at_utc": provenance.get("retrieved_at_utc", ""),
            "source_sha256": provenance.get("raw_sha256", ""),
            "note": (
                "Real published close approaches, shown as context. Not related to "
                "the simulated scenario and not an input to any computation. Served "
                "from a committed snapshot; never fetched at runtime."
            ),
        }

    @app.get("/health")
    def health() -> dict:
        from backend.config import has_model_access, planner_model

        return {
            "status": "ok",
            "model_version": MODEL_VERSION,
            "planner_model": planner_model(),
            # Surfaced so a deployment without a key is obvious from /health
            # rather than only from the first failed run.
            "model_access": has_model_access(),
        }

    # A built frontend is served from the same origin when present, so one
    # container is the whole app. Mounted last so it cannot shadow an API route.
    dist = REPO_ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            """Serve the SPA, letting the client router own unknown paths."""
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


# --------------------------------------------------------------------------
# Markdown export
# --------------------------------------------------------------------------


def _markdown_report(snapshot: dict) -> str:
    scenario = snapshot["scenario"]
    provenance = scenario["provenance"]
    policy = snapshot["policy"]
    lines: list[str] = []

    lines.append(f"# Decision record — case {snapshot['case_id']}")
    lines.append("")
    lines.append(
        f"Scenario `{snapshot['scenario_id']}` v{snapshot['scenario_version']}, "
        f"policy v{snapshot['policy_version']}. Generated {_now()}."
    )
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(
        f"- Seed orbit: {provenance.get('object_name')} (NORAD {provenance.get('norad_id')}), "
        f"epoch {provenance.get('tle_epoch_utc')} — real catalogue element set"
    )
    lines.append(f"- Frame: `{provenance.get('frame')}`, model `{provenance.get('model_version')}`")
    lines.append(
        f"- Conjunction geometry: **synthetic** "
        f"(`synthetic_conjunction={provenance.get('synthetic_conjunction')}`)"
    )
    lines.append(f"- Scenario input hash: `{scenario.get('input_hash', '')[:32]}`")
    lines.append("")
    lines.append("No collision probability is computed anywhere in this record.")
    lines.append("")
    lines.append("## Constraints")
    lines.append("")
    lines.append(f"- Fuel budget: {policy['max_delta_v_mps']} m/s")
    lines.append(f"- Clearance floor: {policy['min_separation_m']:,.0f} m")
    blocked = ", ".join(w["window_id"] for w in policy["blocked_windows"]) or "none"
    lines.append(f"- Blocked windows: {blocked}")
    lines.append("")

    if snapshot["validations"]:
        lines.append("## Options validated")
        lines.append("")
        lines.append("| Option | Result | Closest approach | Object | Reason |")
        lines.append("|---|---|---|---|---|")
        for validation in snapshot["validations"]:
            closest = min(
                validation["encounters"], key=lambda e: e["min_separation_m"], default=None
            )
            lines.append(
                f"| `{validation['candidate_id']}` | {validation['status']} | "
                f"{closest['min_separation_m']:,.1f} m at {closest['tca_s']:,.0f} s | "
                f"{closest['object_id']} | {', '.join(validation['reason_codes'])} |"
                if closest
                else f"| `{validation['candidate_id']}` | {validation['status']} | — | — | "
                f"{', '.join(validation['reason_codes'])} |"
            )
        lines.append("")

    proposal = snapshot.get("proposal")
    if proposal:
        lines.append("## Recommendation")
        lines.append("")
        lines.append(f"- Option: `{proposal['candidate_id']}`")
        lines.append(f"- Status: {proposal['status']}")
        lines.append(f"- Evidence: `{proposal['validation_id']}`")
        verdict = proposal.get("reviewer_verdict")
        if verdict:
            lines.append(f"- Safety reviewer: {verdict['decision']} — {verdict.get('rationale', '')}")
        if proposal.get("qualitative_rationale"):
            lines.append("")
            lines.append("> " + proposal["qualitative_rationale"].replace("\n", " "))
        lines.append("")

    execution = snapshot.get("execution")
    if execution:
        lines.append("## Execution")
        lines.append("")
        lines.append(
            f"- `{execution['execution_id']}` applied `{execution['candidate_id']}` "
            f"at {execution['executed_at_utc']} in mode **{execution['mode']}**"
        )
        lines.append("- Simulated only. Nothing was transmitted to any spacecraft.")
        lines.append("")

    lines.append("## Activity")
    lines.append("")
    for event in snapshot["events"]:
        lines.append(
            f"{event['sequence']}. **{event['event_type']}** — {event['summary']} "
            f"({event['duration_ms']:.0f} ms)"
        )
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Two-body dynamics with instantaneous impulses over a six-hour horizon. "
        "No drag, no oblateness, no finite burn duration, no navigation uncertainty."
    )
    lines.append(
        "- Clearance is a deterministic simulated separation against the objects in "
        "this scenario, not a catalogue-wide screen and not a probability."
    )
    lines.append("- Delta-v is a fuel proxy. No propellant mass or lifetime is modelled.")
    lines.append("")
    return "\n".join(lines)


def _default_app() -> FastAPI:
    """Module-level app for `uvicorn backend.api:app`.

    Providers are constructed lazily per run, so importing this without a key is
    fine -- the failure surfaces on the first plan as an unresolved case rather
    than as an import error.

    The reviewer is wired only when a key is present. Wiring it without one would
    make every proposal UNAVAILABLE, which blocks approval and reads as a safety
    finding rather than a missing credential.
    """
    from backend.config import (
        database_path,
        has_model_access,
        planner_model,
        reviewer_model,
    )

    return create_app(
        store=Store(database_path()),
        provider_factory=lambda: GeminiProvider(model=planner_model()),
        reviewer_factory=(
            (lambda: GeminiProvider(model=reviewer_model())) if has_model_access() else None
        ),
        memory=CaseMemory(database_path()) if database_path() != ":memory:" else CaseMemory(),
    )


app = _default_app()
