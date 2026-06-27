from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from .config import AppConfig
from .engine import AgentLoopEngine
from .events import EventBroker
from .memory import ObsidianMemory
from .model_client import OpenAICompatibleModel
from .persistence import RunStore
from .profile_adaptation import compact_adaptation_review
from .replay import build_replay_bundle
from .schemas import (
    AutonomyDecisionReport,
    ActionReadinessReport,
    ActionReadinessDecisionReport,
    CompletionAuditReport,
    CompletionVerificationPolicy,
    CreateRunRequest,
    GoalEvolutionReport,
    GoalProposalRequest,
    ModelProfileAdaptationReviewRequest,
    OperatorActionDispatchRequest,
    OperatorActionDispatchResult,
    OperatorActionQueueReport,
    OrnithLaunchChecklistReport,
    OrnithPreflightActionLedgerReport,
    OperatorDispatchLedgerReport,
    OperatorDispatchRestartSmokeLedgerReport,
    OperatorDispatchRestartSmokeReport,
    ObjectiveReadinessReport,
    PolicySimulationReport,
    PromoteWorkspaceRequest,
    ReadinessCompletionReport,
    ReadinessRehearsalLedgerReport,
    ReadinessRehearsalReport,
    RecoveryDecisionReport,
    ReportIntegrityReport,
    ResumeDecisionReport,
    RunHealthReport,
    RunProgressReport,
    SourceEvidencePreviewReport,
    SteerRunRequest,
    VerificationOutcomeReport,
)


config = AppConfig.from_env()
store = RunStore(config.sqlite_path)
memory = ObsidianMemory(config.obsidian_vault_path)
model = OpenAICompatibleModel(config)
broker = EventBroker()
engine = AgentLoopEngine(config, store, memory, model, broker)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await engine.recover_stale_runs()
    yield


app = FastAPI(title="AgentOrinth", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.cors_origins),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "config": config.public_dict()}


@app.get("/api/config")
async def get_config() -> dict:
    return config.public_dict()


@app.get("/api/supervisor")
async def get_supervisor() -> dict:
    return engine.get_supervisor_report()


@app.get("/api/operator-actions")
async def get_operator_actions(limit: int = 12) -> dict:
    return OperatorActionQueueReport.model_validate(engine.get_operator_action_queue(limit=limit)).model_dump()


@app.post("/api/operator-actions/dispatch")
async def dispatch_operator_action(payload: OperatorActionDispatchRequest) -> dict:
    return OperatorActionDispatchResult.model_validate(await engine.dispatch_operator_action(payload)).model_dump()


@app.get("/api/operator-actions/dispatches")
async def get_operator_dispatches(limit: int = 20) -> dict:
    return OperatorDispatchLedgerReport.model_validate(engine.get_operator_dispatches(limit=limit)).model_dump()


@app.post("/api/rehearsals/operator-dispatch-restart")
async def run_operator_dispatch_restart_smoke() -> dict:
    report = await engine.run_operator_dispatch_restart_smoke()
    return report.model_dump()


@app.get("/api/rehearsals/operator-dispatch-restart")
async def get_operator_dispatch_restart_smoke_ledger(limit: int = 10) -> dict:
    return OperatorDispatchRestartSmokeLedgerReport.model_validate(
        engine.get_operator_dispatch_restart_smoke_ledger(limit=limit)
    ).model_dump()


@app.post("/api/supervisor/recover")
async def recover_supervisor() -> dict:
    return await engine.recover_stale_runs()


@app.post("/api/rehearsals/readiness-claim")
async def run_readiness_rehearsal() -> dict:
    report = await engine.run_readiness_rehearsal()
    return report.model_dump()


@app.get("/api/rehearsals/readiness-claim")
async def get_readiness_rehearsal_ledger(limit: int = 10) -> dict:
    return ReadinessRehearsalLedgerReport.model_validate(
        engine.get_readiness_rehearsal_ledger(limit=limit)
    ).model_dump()


@app.get("/api/runs")
async def list_runs() -> list[dict]:
    return [run.model_dump() for run in store.list_runs()]


@app.post("/api/runs")
async def create_run(payload: CreateRunRequest) -> dict:
    run = await engine.create_run(
        goal=payload.goal,
        title=payload.title,
        workspace_path=payload.workspace_path,
        acceptance_criteria=payload.acceptance_criteria,
        tool_profile=payload.tool_profile,
        web_enabled=payload.web_enabled,
        browser_enabled=payload.browser_enabled,
        desktop_enabled=payload.desktop_enabled,
        wall_clock_limit_minutes=payload.wall_clock_limit_minutes,
        checkpoint_every_steps=payload.checkpoint_every_steps,
    )
    return run.model_dump()


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    try:
        return store.get_run(run_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/events")
async def list_events(run_id: str, limit: int = 250) -> list[dict]:
    return store.list_events(run_id, limit=limit)


@app.get("/api/runs/{run_id}/approvals")
async def list_approvals(run_id: str) -> list[dict]:
    return store.list_approvals(run_id)


@app.get("/api/tools")
async def get_tool_policy() -> dict:
    return engine.get_tool_policy()


@app.get("/api/completion-policy")
async def get_completion_policy() -> dict:
    return CompletionVerificationPolicy.model_validate(engine.get_completion_policy()).model_dump()


@app.get("/api/model-profile")
async def get_model_profile() -> dict:
    return engine.get_model_profile()


@app.get("/api/ornith/preflight")
async def get_ornith_launch_preflight() -> dict:
    return OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist()).model_dump()


@app.get("/api/runs/{run_id}/ornith-preflight")
async def get_run_ornith_preflight(run_id: str) -> dict:
    try:
        return OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist(run_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/ornith-preflight-actions")
async def get_run_ornith_preflight_actions(run_id: str, limit: int = 20) -> dict:
    try:
        return OrnithPreflightActionLedgerReport.model_validate(
            engine.get_ornith_preflight_actions(run_id, limit=limit)
        ).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/model-profile/eval")
async def get_model_eval() -> dict:
    return engine.get_model_eval()


@app.get("/api/model-profile/quality")
async def get_model_quality_report() -> dict:
    return engine.get_model_quality_report()


@app.get("/api/model-profile/adaptation")
async def get_model_adaptation_proposal() -> dict:
    return engine.get_model_adaptation_proposal()


@app.get("/api/model-profile/adaptation/reviews")
async def list_model_adaptation_reviews(limit: int = 50) -> list[dict]:
    return [review.model_dump() for review in store.list_model_adaptation_reviews(limit=limit)]


@app.post("/api/model-profile/adaptation/reviews")
async def create_model_adaptation_review(payload: ModelProfileAdaptationReviewRequest) -> dict:
    return store.create_model_adaptation_review(
        payload.proposal,
        payload.decision,
        payload.reviewer_note,
    ).model_dump()


@app.get("/api/runs/{run_id}/notes")
async def get_notes(run_id: str) -> dict:
    return {"run_id": run_id, "note": memory.read_run_note(run_id)}


@app.get("/api/runs/{run_id}/sources")
async def get_sources(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {"run_id": run_id, "sources": [source.model_dump() for source in run.state.web_sources]}


@app.get("/api/runs/{run_id}/desktop-snapshots")
async def get_desktop_snapshots(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {"run_id": run_id, "snapshots": [snapshot.model_dump() for snapshot in run.state.desktop_snapshots]}


@app.get("/api/runs/{run_id}/source-evidence")
async def get_source_evidence(run_id: str, limit: int = 20) -> dict:
    try:
        return SourceEvidencePreviewReport.model_validate(
            engine.get_source_evidence(run_id, limit=limit)
        ).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc

@app.get("/api/runs/{run_id}/desktop-snapshots/{snapshot_id}")
async def get_desktop_snapshot_file(run_id: str, snapshot_id: str) -> FileResponse:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    snapshot = next((item for item in run.state.desktop_snapshots if item.id == snapshot_id), None)
    if not snapshot or not snapshot.path:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(snapshot.path)


@app.get("/api/runs/{run_id}/handoff")
async def get_handoff(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    completion_audit = CompletionAuditReport.model_validate(engine.get_completion_audit(run_id))
    run_health = RunHealthReport.model_validate(engine.get_run_health(run_id))
    policy_simulation = PolicySimulationReport.model_validate(engine.get_policy_simulation(run_id))
    resume_decisions = ResumeDecisionReport.model_validate(engine.get_resume_decisions(run_id))
    run_progress = RunProgressReport.model_validate(engine.get_run_progress(run_id))
    ornith_preflight = OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist(run_id))
    run.state.ornith_preflight = ornith_preflight
    run.state.handoff_summary.ornith_preflight = ornith_preflight
    report_integrity = ReportIntegrityReport.model_validate(engine.get_report_integrity(run_id))
    objective_readiness = ObjectiveReadinessReport.model_validate(engine.get_objective_readiness(run_id))
    readiness_completion = ReadinessCompletionReport.model_validate(engine.get_readiness_completion(run_id))
    readiness_rehearsal = ReadinessRehearsalReport.model_validate(engine.get_readiness_rehearsal(run_id))
    action_readiness = ActionReadinessReport.model_validate(engine.get_action_readiness(run_id))
    action_readiness_decisions = ActionReadinessDecisionReport.model_validate(engine.get_action_readiness_decisions(run_id))
    autonomy_decisions = AutonomyDecisionReport.model_validate(engine.get_autonomy_decisions(run_id))
    recovery_decisions = RecoveryDecisionReport.model_validate(engine.get_recovery_decisions(run_id))
    verification_outcomes = VerificationOutcomeReport.model_validate(engine.get_verification_outcomes(run_id))
    goal_evolution = GoalEvolutionReport.model_validate(engine.get_goal_evolution(run_id))
    operator_dispatches = OperatorDispatchLedgerReport.model_validate(engine.get_operator_dispatches(run_id, limit=20))
    ornith_preflight_actions = OrnithPreflightActionLedgerReport.model_validate(engine.get_ornith_preflight_actions(run_id, limit=20))
    source_evidence = SourceEvidencePreviewReport.model_validate(engine.get_source_evidence(run_id, limit=20))
    handoff = run.state.handoff_summary.model_copy(
        update={
            "model_profile_adaptation_reviews": [
                compact_adaptation_review(review)
                for review in store.list_model_adaptation_reviews(limit=5)
            ],
            "completion_audit": completion_audit,
            "run_health": run_health,
            "policy_simulation": policy_simulation,
            "resume_decisions": resume_decisions,
            "run_progress": run_progress,
            "report_integrity": report_integrity,
            "objective_readiness": objective_readiness,
            "readiness_completion": readiness_completion,
            "readiness_rehearsal": readiness_rehearsal,
            "action_readiness": action_readiness,
            "action_readiness_decisions": action_readiness_decisions,
            "autonomy_decisions": autonomy_decisions,
            "recovery_decisions": recovery_decisions,
            "verification_outcomes": verification_outcomes,
            "goal_evolution": goal_evolution,
            "post_action_retries": run.state.post_action_retries,
            "operator_dispatches": operator_dispatches,
            "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke,
            "ornith_preflight": ornith_preflight,
            "ornith_preflight_actions": ornith_preflight_actions,
            "source_evidence": source_evidence,
        }
    )
    return handoff.model_dump()


@app.get("/api/runs/{run_id}/completion-audit")
async def get_completion_audit(run_id: str) -> dict:
    try:
        return engine.get_completion_audit(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/health")
async def get_run_health(run_id: str) -> dict:
    try:
        return engine.get_run_health(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/progress")
async def get_run_progress(run_id: str) -> dict:
    try:
        return engine.get_run_progress(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/report-integrity")
async def get_report_integrity(run_id: str) -> dict:
    try:
        return engine.get_report_integrity(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/objective-readiness")
async def get_objective_readiness(run_id: str) -> dict:
    try:
        return engine.get_objective_readiness(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/readiness-completion")
async def get_readiness_completion(run_id: str) -> dict:
    try:
        return engine.get_readiness_completion(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/readiness-rehearsal")
async def get_readiness_rehearsal(run_id: str) -> dict:
    try:
        return engine.get_readiness_rehearsal(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/policy-simulation")
async def get_policy_simulation(run_id: str) -> dict:
    try:
        return engine.get_policy_simulation(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/resume-decisions")
async def get_resume_decisions(run_id: str) -> dict:
    try:
        return engine.get_resume_decisions(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/action-readiness")
async def get_action_readiness(run_id: str) -> dict:
    try:
        return engine.get_action_readiness(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/action-readiness-decisions")
async def get_action_readiness_decisions(run_id: str) -> dict:
    try:
        return engine.get_action_readiness_decisions(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/autonomy-decisions")
async def get_autonomy_decisions(run_id: str) -> dict:
    try:
        return engine.get_autonomy_decisions(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/recovery-decisions")
async def get_recovery_decisions(run_id: str) -> dict:
    try:
        return engine.get_recovery_decisions(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/verification-outcomes")
async def get_verification_outcomes(run_id: str) -> dict:
    try:
        return engine.get_verification_outcomes(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/operator-dispatches")
async def get_run_operator_dispatches(run_id: str, limit: int = 20) -> dict:
    try:
        store.get_run(run_id)
        return OperatorDispatchLedgerReport.model_validate(engine.get_operator_dispatches(run_id, limit=limit)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/operator-dispatch-restart-smoke")
async def get_run_operator_dispatch_restart_smoke(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
        return OperatorDispatchRestartSmokeReport.model_validate(run.state.operator_dispatch_restart_smoke).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/timeline")
async def get_timeline(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    adaptation_reviews = [
        compact_adaptation_review(review)
        for review in store.list_model_adaptation_reviews(limit=10)
    ]
    completion_audit = engine.get_completion_audit(run_id)
    run_health = RunHealthReport.model_validate(engine.get_run_health(run_id))
    policy_simulation = PolicySimulationReport.model_validate(engine.get_policy_simulation(run_id))
    resume_decisions = ResumeDecisionReport.model_validate(engine.get_resume_decisions(run_id))
    run_progress = RunProgressReport.model_validate(engine.get_run_progress(run_id))
    ornith_preflight = OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist(run_id))
    run.state.ornith_preflight = ornith_preflight
    run.state.handoff_summary.ornith_preflight = ornith_preflight
    report_integrity = ReportIntegrityReport.model_validate(engine.get_report_integrity(run_id))
    objective_readiness = ObjectiveReadinessReport.model_validate(engine.get_objective_readiness(run_id))
    readiness_completion = ReadinessCompletionReport.model_validate(engine.get_readiness_completion(run_id))
    readiness_rehearsal = ReadinessRehearsalReport.model_validate(engine.get_readiness_rehearsal(run_id))
    action_readiness = ActionReadinessReport.model_validate(engine.get_action_readiness(run_id))
    action_readiness_decisions = ActionReadinessDecisionReport.model_validate(engine.get_action_readiness_decisions(run_id))
    autonomy_decisions = AutonomyDecisionReport.model_validate(engine.get_autonomy_decisions(run_id))
    recovery_decisions = RecoveryDecisionReport.model_validate(engine.get_recovery_decisions(run_id))
    verification_outcomes = VerificationOutcomeReport.model_validate(engine.get_verification_outcomes(run_id))
    goal_evolution = GoalEvolutionReport.model_validate(engine.get_goal_evolution(run_id))
    operator_dispatches = OperatorDispatchLedgerReport.model_validate(engine.get_operator_dispatches(run_id, limit=20))
    ornith_preflight_actions = OrnithPreflightActionLedgerReport.model_validate(engine.get_ornith_preflight_actions(run_id, limit=20))
    source_evidence = SourceEvidencePreviewReport.model_validate(engine.get_source_evidence(run_id, limit=20))
    completion_audit_model = CompletionAuditReport.model_validate(completion_audit)
    handoff = run.state.handoff_summary.model_copy(
        update={
            "model_profile_adaptation_reviews": adaptation_reviews[:5],
            "completion_audit": completion_audit_model,
            "run_health": run_health,
            "policy_simulation": policy_simulation,
            "resume_decisions": resume_decisions,
            "run_progress": run_progress,
            "report_integrity": report_integrity,
            "objective_readiness": objective_readiness,
            "readiness_completion": readiness_completion,
            "readiness_rehearsal": readiness_rehearsal,
            "action_readiness": action_readiness,
            "action_readiness_decisions": action_readiness_decisions,
            "autonomy_decisions": autonomy_decisions,
            "recovery_decisions": recovery_decisions,
            "verification_outcomes": verification_outcomes,
            "goal_evolution": goal_evolution,
            "post_action_retries": run.state.post_action_retries,
            "operator_dispatches": operator_dispatches,
            "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke,
            "ornith_preflight": ornith_preflight,
            "ornith_preflight_actions": ornith_preflight_actions,
            "source_evidence": source_evidence,
        }
    )
    return {
        "run_id": run_id,
        "events": store.list_events(run_id, limit=300),
        "approvals": store.list_approvals(run_id),
        "acceptance_evidence": [item.model_dump() for item in run.state.acceptance_evidence],
        "acceptance_recommendations": [item.model_dump() for item in run.state.acceptance_recommendations],
        "acceptance_recommendation_traces": [
            item.model_dump()
            for item in run.state.acceptance_recommendation_traces
        ],
        "completion_audit": completion_audit,
        "run_health": run_health.model_dump(),
        "policy_simulation": policy_simulation.model_dump(),
        "resume_decisions": resume_decisions.model_dump(),
        "run_progress": run_progress.model_dump(),
        "report_integrity": report_integrity.model_dump(),
        "objective_readiness": objective_readiness.model_dump(),
        "readiness_completion": readiness_completion.model_dump(),
        "readiness_rehearsal": readiness_rehearsal.model_dump(),
        "action_readiness": action_readiness.model_dump(),
        "action_readiness_decisions": action_readiness_decisions.model_dump(),
        "autonomy_decisions": autonomy_decisions.model_dump(),
        "recovery_decisions": recovery_decisions.model_dump(),
        "verification_outcomes": verification_outcomes.model_dump(),
        "goal_evolution": goal_evolution.model_dump(),
        "post_action_retries": run.state.post_action_retries.model_dump(),
        "operator_dispatches": operator_dispatches.model_dump(),
        "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke.model_dump(),
        "ornith_preflight": ornith_preflight.model_dump(),
        "ornith_preflight_actions": ornith_preflight_actions.model_dump(),
        "source_evidence": source_evidence.model_dump(),
        "tool_calls": [call.model_dump() for call in run.state.tool_calls],
        "model_interactions": [interaction.model_dump() for interaction in run.state.model_interactions],
        "task_graph": [task.model_dump() for task in run.state.task_graph],
        "workspace_isolation": run.state.workspace_isolation.model_dump(),
        "workspace_diff": run.state.workspace_diff.model_dump(),
        "workspace_promotions": [promotion.model_dump() for promotion in run.state.workspace_promotions],
        "patch_proposals": [proposal.model_dump() for proposal in run.state.patch_proposals],
        "patch_applications": [application.model_dump() for application in run.state.patch_applications],
        "failure_records": [record.model_dump() for record in run.state.failure_records],
        "recovery_plan": run.state.recovery_plan.model_dump(),
        "recovery_history": [plan.model_dump() for plan in run.state.recovery_history],
        "model_profile_adaptation_reviews": [review.model_dump() for review in adaptation_reviews],
        "repo_map": run.state.repo_map.model_dump(),
        "handoff": handoff.model_dump(),
    }


@app.get("/api/runs/{run_id}/replay")
async def get_replay(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    ornith_preflight = OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist(run_id))
    run.state.ornith_preflight = ornith_preflight
    run.state.handoff_summary.ornith_preflight = ornith_preflight
    bundle = build_replay_bundle(
        run,
        events=store.list_events(run_id, limit=500),
        approvals=store.list_approvals(run_id),
        model_adaptation_reviews=store.list_model_adaptation_reviews(limit=10),
        strict_stale_evidence=config.completion_strict_stale_evidence,
        stale_edit_tools=set(config.completion_stale_edit_tools),
    )
    return bundle.model_dump()


@app.get("/api/runs/{run_id}/replay.md")
async def get_replay_markdown(run_id: str) -> PlainTextResponse:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    ornith_preflight = OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist(run_id))
    run.state.ornith_preflight = ornith_preflight
    run.state.handoff_summary.ornith_preflight = ornith_preflight
    bundle = build_replay_bundle(
        run,
        events=store.list_events(run_id, limit=500),
        approvals=store.list_approvals(run_id),
        model_adaptation_reviews=store.list_model_adaptation_reviews(limit=10),
        strict_stale_evidence=config.completion_strict_stale_evidence,
        stale_edit_tools=set(config.completion_stale_edit_tools),
    )
    return PlainTextResponse(bundle.markdown, media_type="text/markdown")


@app.get("/api/runs/{run_id}/workspace")
async def get_workspace(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {
        "run_id": run_id,
        "workspace_path": run.workspace_path,
        "workspace_isolation": run.state.workspace_isolation.model_dump(),
        "workspace_diff": run.state.workspace_diff.model_dump(),
        "workspace_promotions": [promotion.model_dump() for promotion in run.state.workspace_promotions],
        "repo_map": run.state.repo_map.model_dump(),
    }


@app.get("/api/runs/{run_id}/workspace/diff")
async def get_workspace_diff(run_id: str) -> dict:
    try:
        run = await engine.refresh_workspace_diff(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {
        "run_id": run_id,
        "workspace_diff": run.state.workspace_diff.model_dump(),
    }


@app.post("/api/runs/{run_id}/workspace/promote")
async def promote_workspace(run_id: str, payload: PromoteWorkspaceRequest) -> dict:
    try:
        run = await engine.request_workspace_promotion(
            run_id,
            files=payload.files,
            include_deletions=payload.include_deletions,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return run.model_dump()


@app.get("/api/runs/{run_id}/patches")
async def get_patches(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {
        "run_id": run_id,
        "patch_proposals": [proposal.model_dump() for proposal in run.state.patch_proposals],
        "patch_applications": [application.model_dump() for application in run.state.patch_applications],
    }


@app.get("/api/runs/{run_id}/goal")
async def get_goal(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return {
        "original_goal": run.goal,
        "active_goal": run.state.goal,
        "proposed_goal": run.state.proposed_goal,
        "goal_revision_reason": run.state.goal_revision_reason,
        "goal_evolution": GoalEvolutionReport.model_validate(engine.get_goal_evolution(run_id)).model_dump(),
    }


@app.get("/api/runs/{run_id}/goal/evolution")
async def get_goal_evolution(run_id: str) -> dict:
    try:
        return GoalEvolutionReport.model_validate(engine.get_goal_evolution(run_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/api/runs/{run_id}/goal")
async def propose_goal(run_id: str, payload: GoalProposalRequest) -> dict:
    return (await engine.propose_goal(run_id, payload.proposed_goal, payload.reason)).model_dump()


@app.post("/api/runs/{run_id}/goal/review")
async def review_goal(run_id: str) -> dict:
    return (await engine.review_goal(run_id)).model_dump()


@app.post("/api/runs/{run_id}/pause")
async def pause_run(run_id: str) -> dict:
    return (await engine.pause_run(run_id)).model_dump()


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str) -> dict:
    return (await engine.resume_run(run_id)).model_dump()


@app.post("/api/runs/{run_id}/recovery/resume")
async def resume_recovery(run_id: str) -> dict:
    return (await engine.resume_recovery(run_id)).model_dump()


@app.post("/api/runs/{run_id}/recovery/replan")
async def replan_recovery(run_id: str) -> dict:
    return (await engine.replan_recovery(run_id)).model_dump()


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    return (await engine.cancel_run(run_id)).model_dump()


@app.post("/api/runs/{run_id}/steer")
async def steer_run(run_id: str, payload: SteerRunRequest) -> dict:
    return (await engine.steer_run(run_id, payload.message)).model_dump()


@app.post("/api/runs/{run_id}/approvals/{approval_id}/approve")
async def approve_action(run_id: str, approval_id: int) -> dict:
    return (await engine.approve_action(run_id, approval_id)).model_dump()


@app.post("/api/runs/{run_id}/approvals/{approval_id}/reject")
async def reject_action(run_id: str, approval_id: int) -> dict:
    return (await engine.reject_action(run_id, approval_id)).model_dump()


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    return StreamingResponse(broker.stream(run_id), media_type="text/event-stream")




