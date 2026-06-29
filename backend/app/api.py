from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from .checkpoint_quality_resume import build_checkpoint_quality_resume_report
from .config import AppConfig
from .desktop_effect_proof import build_desktop_effect_proof_repairs
from .engine import AgentLoopEngine
from .events import EventBroker
from .memory import ObsidianMemory
from .model_client import OpenAICompatibleModel
from .persistence import RunStore
from .profile_adaptation import compact_adaptation_review
from .replay import build_readiness_proof_history, build_replay_bundle
from .report_integrity import build_report_integrity_refreshes
from .self_scaffold import build_self_scaffold_review_report, build_self_scaffold_rollback_intent_report
from .schemas import (
    AutonomyDecisionReport,
    ActionReadinessReport,
    ActionReadinessDecisionReport,
    ApprovalReviewRecord,
    CheckpointQualityReport,
    CheckpointQualityResumeReport,
    CompletionAuditReport,
    CompletionVerificationPolicy,
    CreateRunRequest,
    DesktopEffectProofReport,
    DesktopEffectProofRepairReport,
    GitCheckpointReport,
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
    PromotionAuditReport,
    PromotionRepairReport,
    PromotionVerificationReport,
    PromoteWorkspaceRequest,
    ReadinessCompletionReport,
    ReadinessProofHistoryReport,
    ReadinessSourceRefPreviewReport,
    ReadinessRehearsalLedgerReport,
    ReadinessRehearsalReport,
    RecoveryDecisionReport,
    ReportIntegrityReport,
    ResumeDecisionReport,
    ResumeHandoffDiffReport,
    ResumePromptQualityReport,
    RunHealthReport,
    RunProgressReport,
    SourceEvidencePreviewReport,
    SelfScaffoldReviewReport,
    SelfScaffoldRollbackIntentReport,
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
    recovery_task = asyncio.create_task(_recover_stale_runs_on_startup())
    yield
    if not recovery_task.done():
        recovery_task.cancel()


async def _recover_stale_runs_on_startup() -> None:
    try:
        await asyncio.sleep(2)
        await asyncio.wait_for(engine.recover_stale_runs(), timeout=20)
    except asyncio.TimeoutError:
        print("AgentOrinth startup recovery timed out; API is serving and supervisor can be refreshed manually.")
    except Exception as exc:  # pragma: no cover - startup guardrail
        print(f"AgentOrinth startup recovery failed: {exc}")


app = FastAPI(title="AgentOrinth", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.cors_origins),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _checkpoint_quality_resume_material(report: CheckpointQualityResumeReport) -> dict:
    return report.model_dump(exclude={"generated_at"})


def _persist_checkpoint_quality_resumes(run_id: str, report: CheckpointQualityResumeReport) -> None:
    if not report.run_id:
        return
    current = store.get_run(run_id)
    state = current.state
    material = _checkpoint_quality_resume_material(report)
    state_material = _checkpoint_quality_resume_material(state.checkpoint_quality_resumes)
    handoff_material = _checkpoint_quality_resume_material(state.handoff_summary.checkpoint_quality_resumes)
    if material == state_material and material == handoff_material:
        return
    state.checkpoint_quality_resumes = report
    state.handoff_summary.checkpoint_quality_resumes = report
    store.update_run(run_id, state=state)


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
async def get_operator_actions(limit: int = 12, filter: str = "all") -> dict:
    if filter not in {"all", "promotion_approvals", "proof_reviews"}:
        raise HTTPException(
            status_code=400,
            detail="operator action filter must be all, promotion_approvals, or proof_reviews",
        )
    return OperatorActionQueueReport.model_validate(
        engine.get_operator_action_queue(limit=limit, queue_filter=filter)
    ).model_dump()


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
    runs = []
    for run in store.list_runs():
        promotion_repair = PromotionRepairReport.model_validate(engine.get_promotion_repair(run.id))
        run.state.promotion_repair = promotion_repair
        run.state.handoff_summary.promotion_repair = promotion_repair
        runs.append(run.model_dump())
    return runs


@app.post("/api/runs")
async def create_run(payload: CreateRunRequest) -> dict:
    run = await engine.create_run(
        goal=payload.goal,
        title=payload.title,
        workspace_path=payload.workspace_path,
        acceptance_criteria=payload.acceptance_criteria,
        tool_profile=payload.tool_profile,
        approval_mode=payload.approval_mode,
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


@app.get("/api/runs/{run_id}/approval-reviews")
async def list_approval_reviews(run_id: str, status: str | None = None) -> list[dict]:
    try:
        return [ApprovalReviewRecord.model_validate(item).model_dump() for item in engine.get_approval_reviews(run_id, status=status)]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/tools")
async def get_tool_policy() -> dict:
    return engine.get_tool_policy()


@app.get("/api/completion-policy")
async def get_completion_policy() -> dict:
    return CompletionVerificationPolicy.model_validate(engine.get_completion_policy()).model_dump()


@app.get("/api/model-profile")
async def get_model_profile() -> dict:
    return engine.get_model_profile()


@app.get("/api/model-profile/health")
async def get_model_connection_health() -> dict:
    return await model.health_check(timeout_seconds=float(config.model_health_timeout_seconds))


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


@app.get("/api/runs/{run_id}/desktop-effect-proof")
async def get_desktop_effect_proof(run_id: str, limit: int = 5) -> dict:
    try:
        return DesktopEffectProofReport.model_validate(
            engine.get_desktop_effect_proof_preview(run_id, limit=limit)
        ).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


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
    resume_prompt_quality = ResumePromptQualityReport.model_validate(engine.get_resume_prompt_quality(run_id))
    resume_handoff_diff = ResumeHandoffDiffReport.model_validate(engine.get_resume_handoff_diff(run_id))
    promotion_audit = PromotionAuditReport.model_validate(engine.get_promotion_audit(run_id))
    promotion_verification = PromotionVerificationReport.model_validate(engine.get_promotion_verification(run_id))
    promotion_repair = PromotionRepairReport.model_validate(engine.get_promotion_repair(run_id))
    run_progress = RunProgressReport.model_validate(engine.get_run_progress(run_id))
    ornith_preflight = OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist(run_id))
    run.state.ornith_preflight = ornith_preflight
    run.state.handoff_summary.ornith_preflight = ornith_preflight
    report_integrity = ReportIntegrityReport.model_validate(engine.get_report_integrity(run_id))
    checkpoint_quality = CheckpointQualityReport.model_validate(engine.get_checkpoint_quality(run_id))
    objective_readiness = ObjectiveReadinessReport.model_validate(engine.get_objective_readiness(run_id))
    readiness_completion = ReadinessCompletionReport.model_validate(engine.get_readiness_completion(run_id))
    readiness_rehearsal = ReadinessRehearsalReport.model_validate(engine.get_readiness_rehearsal(run_id))
    action_readiness = ActionReadinessReport.model_validate(engine.get_action_readiness(run_id))
    action_readiness_decisions = ActionReadinessDecisionReport.model_validate(engine.get_action_readiness_decisions(run_id))
    autonomy_decisions = AutonomyDecisionReport.model_validate(engine.get_autonomy_decisions(run_id))
    recovery_decisions = RecoveryDecisionReport.model_validate(engine.get_recovery_decisions(run_id))
    verification_outcomes = VerificationOutcomeReport.model_validate(engine.get_verification_outcomes(run_id))
    goal_evolution = GoalEvolutionReport.model_validate(engine.get_goal_evolution(run_id))
    git_checkpoint = GitCheckpointReport.model_validate(engine.get_git_checkpoint(run_id))
    operator_dispatches = OperatorDispatchLedgerReport.model_validate(engine.get_operator_dispatches(run_id, limit=20))
    ornith_preflight_actions = OrnithPreflightActionLedgerReport.model_validate(engine.get_ornith_preflight_actions(run_id, limit=20))
    source_evidence = SourceEvidencePreviewReport.model_validate(engine.get_source_evidence(run_id, limit=20))
    desktop_effect_proof = DesktopEffectProofReport.model_validate(engine.get_desktop_effect_proof_preview(run_id, limit=8))
    events = store.list_events(run_id, limit=300)
    self_scaffold_reviews = SelfScaffoldReviewReport.model_validate(
        build_self_scaffold_review_report(run, events, limit=8)
    )
    self_scaffold_rollback_intents = SelfScaffoldRollbackIntentReport.model_validate(
        build_self_scaffold_rollback_intent_report(
            run,
            events,
            self_scaffold=run.state.self_scaffold if run.state.self_scaffold.generated_at else None,
            reviews=self_scaffold_reviews,
            limit=8,
        )
    )
    desktop_effect_proof_repairs = DesktopEffectProofRepairReport.model_validate(
        build_desktop_effect_proof_repairs(run, events, limit=8)
    )
    report_integrity_refreshes = build_report_integrity_refreshes(events, limit=8)
    checkpoint_quality_resumes = CheckpointQualityResumeReport.model_validate(
        build_checkpoint_quality_resume_report(run, events, checkpoint_quality=checkpoint_quality, limit=8)
    )
    readiness_proof_history = ReadinessProofHistoryReport.model_validate(
        build_readiness_proof_history(run, events, readiness_rehearsal, run.state.self_scaffold, source_evidence, limit=20)
    )
    readiness_source_ref_preview = ReadinessSourceRefPreviewReport.model_validate(
        engine.get_readiness_source_ref_preview(run_id, limit=20)
    )
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
            "resume_prompt_quality": resume_prompt_quality,
            "resume_handoff_diff": resume_handoff_diff,
            "promotion_audit": promotion_audit,
            "promotion_verification": promotion_verification,
            "promotion_repair": promotion_repair,
            "run_progress": run_progress,
            "report_integrity": report_integrity,
            "checkpoint_quality": checkpoint_quality,
            "checkpoint_quality_resumes": checkpoint_quality_resumes,
            "report_integrity_refreshes": report_integrity_refreshes,
            "objective_readiness": objective_readiness,
            "readiness_completion": readiness_completion,
            "readiness_rehearsal": readiness_rehearsal,
            "readiness_proof_history": readiness_proof_history,
            "readiness_source_ref_preview": readiness_source_ref_preview,
            "action_readiness": action_readiness,
            "action_readiness_decisions": action_readiness_decisions,
            "autonomy_decisions": autonomy_decisions,
            "recovery_decisions": recovery_decisions,
            "verification_outcomes": verification_outcomes,
            "goal_evolution": goal_evolution,
            "git_checkpoint": git_checkpoint,
            "post_action_retries": run.state.post_action_retries,
            "operator_dispatches": operator_dispatches,
            "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke,
            "ornith_preflight": ornith_preflight,
            "ornith_preflight_actions": ornith_preflight_actions,
            "source_evidence": source_evidence,
            "desktop_effect_proof": desktop_effect_proof,
            "desktop_effect_proof_repairs": desktop_effect_proof_repairs,
            "self_scaffold_reviews": self_scaffold_reviews,
            "self_scaffold_rollback_intents": self_scaffold_rollback_intents,
            "failure_records": run.state.failure_records[-20:],
        }
    )
    _persist_checkpoint_quality_resumes(run_id, checkpoint_quality_resumes)
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


@app.get("/api/runs/{run_id}/checkpoint-quality")
async def get_checkpoint_quality(run_id: str) -> dict:
    try:
        return engine.get_checkpoint_quality(run_id)
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


@app.get("/api/runs/{run_id}/readiness-source-refs")
async def get_readiness_source_refs(run_id: str, limit: int = 12) -> dict:
    try:
        return ReadinessSourceRefPreviewReport.model_validate(
            engine.get_readiness_source_ref_preview(run_id, limit=limit)
        ).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc

@app.post("/api/runs/{run_id}/readiness-source-refs/refresh")
async def refresh_readiness_source_refs(run_id: str) -> dict:
    try:
        updated = await engine.refresh_readiness_source_refs(run_id)
        return updated.model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/api/runs/{run_id}/desktop-effect/verify")
async def verify_desktop_effect(run_id: str) -> dict:
    try:
        updated = await engine.run_desktop_effect_proof(run_id)
        return updated.model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/self-scaffold-reviews")
async def get_self_scaffold_reviews(run_id: str, limit: int = 8) -> dict:
    try:
        run = store.get_run(run_id)
        return SelfScaffoldReviewReport.model_validate(
            build_self_scaffold_review_report(run, store.list_events(run_id, limit=300), limit=limit)
        ).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc



@app.get("/api/runs/{run_id}/self-scaffold-rollback-intents")
async def get_self_scaffold_rollback_intents(run_id: str, limit: int = 8) -> dict:
    try:
        run = store.get_run(run_id)
        events = store.list_events(run_id, limit=300)
        reviews = build_self_scaffold_review_report(run, events, limit=limit)
        return SelfScaffoldRollbackIntentReport.model_validate(
            build_self_scaffold_rollback_intent_report(
                run,
                events,
                self_scaffold=run.state.self_scaffold if run.state.self_scaffold.generated_at else None,
                reviews=reviews,
                limit=limit,
            )
        ).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc

@app.get("/api/runs/{run_id}/readiness-proof-history")
async def get_readiness_proof_history(run_id: str, limit: int = 20) -> dict:
    try:
        run = store.get_run(run_id)
        events = store.list_events(run_id, limit=300)
        source_evidence = SourceEvidencePreviewReport.model_validate(engine.get_source_evidence(run_id, limit=limit))
        return ReadinessProofHistoryReport.model_validate(
            build_readiness_proof_history(run, events, run.state.readiness_rehearsal, run.state.self_scaffold, source_evidence, limit=limit)
        ).model_dump()
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


@app.get("/api/runs/{run_id}/resume-quality")
async def get_resume_prompt_quality(run_id: str) -> dict:
    try:
        return ResumePromptQualityReport.model_validate(engine.get_resume_prompt_quality(run_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/resume-handoff-diff")
async def get_resume_handoff_diff(run_id: str) -> dict:
    try:
        return ResumeHandoffDiffReport.model_validate(engine.get_resume_handoff_diff(run_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/promotion-audit")
async def get_promotion_audit(run_id: str) -> dict:
    try:
        return PromotionAuditReport.model_validate(engine.get_promotion_audit(run_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/promotion-verification")
async def get_promotion_verification(run_id: str) -> dict:
    try:
        return PromotionVerificationReport.model_validate(engine.get_promotion_verification(run_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/promotion-repair")
async def get_promotion_repair(run_id: str) -> dict:
    try:
        return PromotionRepairReport.model_validate(engine.get_promotion_repair(run_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/api/runs/{run_id}/promotion-audit/verify")
async def verify_promotion_audit(run_id: str) -> dict:
    try:
        run = await engine.run_promotion_audit_verification(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return run.model_dump()


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
    resume_prompt_quality = ResumePromptQualityReport.model_validate(engine.get_resume_prompt_quality(run_id))
    resume_handoff_diff = ResumeHandoffDiffReport.model_validate(engine.get_resume_handoff_diff(run_id))
    promotion_audit = PromotionAuditReport.model_validate(engine.get_promotion_audit(run_id))
    promotion_verification = PromotionVerificationReport.model_validate(engine.get_promotion_verification(run_id))
    promotion_repair = PromotionRepairReport.model_validate(engine.get_promotion_repair(run_id))
    run_progress = RunProgressReport.model_validate(engine.get_run_progress(run_id))
    ornith_preflight = OrnithLaunchChecklistReport.model_validate(engine.get_ornith_launch_checklist(run_id))
    run.state.ornith_preflight = ornith_preflight
    run.state.handoff_summary.ornith_preflight = ornith_preflight
    report_integrity = ReportIntegrityReport.model_validate(engine.get_report_integrity(run_id))
    checkpoint_quality = CheckpointQualityReport.model_validate(engine.get_checkpoint_quality(run_id))
    objective_readiness = ObjectiveReadinessReport.model_validate(engine.get_objective_readiness(run_id))
    readiness_completion = ReadinessCompletionReport.model_validate(engine.get_readiness_completion(run_id))
    readiness_rehearsal = ReadinessRehearsalReport.model_validate(engine.get_readiness_rehearsal(run_id))
    action_readiness = ActionReadinessReport.model_validate(engine.get_action_readiness(run_id))
    action_readiness_decisions = ActionReadinessDecisionReport.model_validate(engine.get_action_readiness_decisions(run_id))
    autonomy_decisions = AutonomyDecisionReport.model_validate(engine.get_autonomy_decisions(run_id))
    recovery_decisions = RecoveryDecisionReport.model_validate(engine.get_recovery_decisions(run_id))
    verification_outcomes = VerificationOutcomeReport.model_validate(engine.get_verification_outcomes(run_id))
    goal_evolution = GoalEvolutionReport.model_validate(engine.get_goal_evolution(run_id))
    git_checkpoint = GitCheckpointReport.model_validate(engine.get_git_checkpoint(run_id))
    operator_dispatches = OperatorDispatchLedgerReport.model_validate(engine.get_operator_dispatches(run_id, limit=20))
    ornith_preflight_actions = OrnithPreflightActionLedgerReport.model_validate(engine.get_ornith_preflight_actions(run_id, limit=20))
    source_evidence = SourceEvidencePreviewReport.model_validate(engine.get_source_evidence(run_id, limit=20))
    desktop_effect_proof = DesktopEffectProofReport.model_validate(engine.get_desktop_effect_proof_preview(run_id, limit=8))
    events = store.list_events(run_id, limit=300)
    self_scaffold_reviews = SelfScaffoldReviewReport.model_validate(
        build_self_scaffold_review_report(run, events, limit=8)
    )
    self_scaffold_rollback_intents = SelfScaffoldRollbackIntentReport.model_validate(
        build_self_scaffold_rollback_intent_report(
            run,
            events,
            self_scaffold=run.state.self_scaffold if run.state.self_scaffold.generated_at else None,
            reviews=self_scaffold_reviews,
            limit=8,
        )
    )
    desktop_effect_proof_repairs = DesktopEffectProofRepairReport.model_validate(
        build_desktop_effect_proof_repairs(run, events, limit=8)
    )
    report_integrity_refreshes = build_report_integrity_refreshes(events, limit=8)
    checkpoint_quality_resumes = CheckpointQualityResumeReport.model_validate(
        build_checkpoint_quality_resume_report(run, events, checkpoint_quality=checkpoint_quality, limit=8)
    )
    readiness_proof_history = ReadinessProofHistoryReport.model_validate(
        build_readiness_proof_history(run, events, readiness_rehearsal, run.state.self_scaffold, source_evidence, limit=20)
    )
    readiness_source_ref_preview = ReadinessSourceRefPreviewReport.model_validate(
        engine.get_readiness_source_ref_preview(run_id, limit=20)
    )
    completion_audit_model = CompletionAuditReport.model_validate(completion_audit)
    handoff = run.state.handoff_summary.model_copy(
        update={
            "model_profile_adaptation_reviews": adaptation_reviews[:5],
            "completion_audit": completion_audit_model,
            "run_health": run_health,
            "policy_simulation": policy_simulation,
            "resume_decisions": resume_decisions,
            "resume_prompt_quality": resume_prompt_quality,
            "resume_handoff_diff": resume_handoff_diff,
            "promotion_audit": promotion_audit,
            "promotion_verification": promotion_verification,
            "promotion_repair": promotion_repair,
            "run_progress": run_progress,
            "report_integrity": report_integrity,
            "checkpoint_quality": checkpoint_quality,
            "checkpoint_quality_resumes": checkpoint_quality_resumes,
            "report_integrity_refreshes": report_integrity_refreshes,
            "objective_readiness": objective_readiness,
            "readiness_completion": readiness_completion,
            "readiness_rehearsal": readiness_rehearsal,
            "readiness_proof_history": readiness_proof_history,
            "readiness_source_ref_preview": readiness_source_ref_preview,
            "action_readiness": action_readiness,
            "action_readiness_decisions": action_readiness_decisions,
            "autonomy_decisions": autonomy_decisions,
            "recovery_decisions": recovery_decisions,
            "verification_outcomes": verification_outcomes,
            "goal_evolution": goal_evolution,
            "git_checkpoint": git_checkpoint,
            "post_action_retries": run.state.post_action_retries,
            "operator_dispatches": operator_dispatches,
            "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke,
            "ornith_preflight": ornith_preflight,
            "ornith_preflight_actions": ornith_preflight_actions,
            "source_evidence": source_evidence,
            "desktop_effect_proof": desktop_effect_proof,
            "desktop_effect_proof_repairs": desktop_effect_proof_repairs,
            "self_scaffold_reviews": self_scaffold_reviews,
            "self_scaffold_rollback_intents": self_scaffold_rollback_intents,
            "failure_records": run.state.failure_records[-20:],
        }
    )
    _persist_checkpoint_quality_resumes(run_id, checkpoint_quality_resumes)
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
        "resume_prompt_quality": resume_prompt_quality.model_dump(),
        "resume_handoff_diff": resume_handoff_diff.model_dump(),
        "promotion_audit": promotion_audit.model_dump(),
        "promotion_verification": promotion_verification.model_dump(),
        "promotion_repair": promotion_repair.model_dump(),
        "run_progress": run_progress.model_dump(),
        "report_integrity": report_integrity.model_dump(),
        "checkpoint_quality": checkpoint_quality.model_dump(),
        "checkpoint_quality_resumes": checkpoint_quality_resumes.model_dump(),
        "report_integrity_refreshes": [item.model_dump() for item in report_integrity_refreshes],
        "objective_readiness": objective_readiness.model_dump(),
        "readiness_completion": readiness_completion.model_dump(),
        "readiness_source_ref_preview": readiness_source_ref_preview.model_dump(),
        "readiness_rehearsal": readiness_rehearsal.model_dump(),
        "action_readiness": action_readiness.model_dump(),
        "action_readiness_decisions": action_readiness_decisions.model_dump(),
        "autonomy_decisions": autonomy_decisions.model_dump(),
        "recovery_decisions": recovery_decisions.model_dump(),
        "verification_outcomes": verification_outcomes.model_dump(),
        "goal_evolution": goal_evolution.model_dump(),
        "git_checkpoint": git_checkpoint.model_dump(),
        "post_action_retries": run.state.post_action_retries.model_dump(),
        "operator_dispatches": operator_dispatches.model_dump(),
        "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke.model_dump(),
        "ornith_preflight": ornith_preflight.model_dump(),
        "ornith_preflight_actions": ornith_preflight_actions.model_dump(),
        "source_evidence": source_evidence.model_dump(),
        "desktop_effect_proof": desktop_effect_proof.model_dump(),
        "desktop_effect_proof_repairs": desktop_effect_proof_repairs.model_dump(),
        "self_scaffold_reviews": self_scaffold_reviews.model_dump(),
        "self_scaffold_rollback_intents": self_scaffold_rollback_intents.model_dump(),
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
    _persist_checkpoint_quality_resumes(run_id, bundle.checkpoint_quality_resumes)
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



@app.post("/api/runs/{run_id}/patches/{patch_id}/apply")
async def request_patch_apply(run_id: str, patch_id: str) -> dict:
    try:
        run = await engine.request_patch_apply_approval(run_id, patch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run.model_dump()



@app.post("/api/runs/{run_id}/patches/{patch_id}/rollback")
async def request_patch_rollback(run_id: str, patch_id: str) -> dict:
    try:
        run = await engine.request_patch_rollback_approval(run_id, patch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run.model_dump()

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



@app.get("/api/runs/{run_id}/git-checkpoint")
async def get_git_checkpoint(run_id: str) -> dict:
    try:
        return GitCheckpointReport.model_validate(engine.get_git_checkpoint(run_id)).model_dump()
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

