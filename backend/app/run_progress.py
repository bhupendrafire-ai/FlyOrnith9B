from __future__ import annotations

from datetime import datetime, timezone

from .schemas import CompletionAuditReport, PolicySimulationReport, RunProgressReport, RunRecord


def build_run_progress(
    run: RunRecord,
    approvals: list[dict],
    completion_audit: CompletionAuditReport,
    policy_simulation: PolicySimulationReport,
) -> RunProgressReport:
    state = run.state
    task_total = len(state.task_graph)
    task_completed = sum(1 for task in state.task_graph if task.status == "completed")
    task_blocked = sum(1 for task in state.task_graph if task.status == "blocked")
    task_failed = sum(1 for task in state.task_graph if task.status == "failed")
    task_progress = _percent(task_completed, task_total)
    acceptance_coverage = _percent(completion_audit.acceptance_verified, completion_audit.acceptance_total)
    pending_approvals = [approval for approval in approvals if approval.get("status") == "pending"]
    latest_autonomy = state.autonomy_decisions.latest_decision
    latest_verification = state.verification_outcomes.latest_outcome
    status = _status(run, completion_audit, policy_simulation)
    next_actions = _next_actions(run, completion_audit, policy_simulation, status)
    evidence = _evidence(run, completion_audit, policy_simulation)

    return RunProgressReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status=status,
        summary=_summary(status, run, completion_audit, task_progress, acceptance_coverage),
        can_keep_running=status in {"on_track", "needs_verification", "near_completion"},
        should_pause=status in {"needs_recovery", "waiting", "blocked"},
        near_completion=status == "near_completion",
        task_total=task_total,
        task_completed=task_completed,
        task_blocked=task_blocked,
        task_failed=task_failed,
        task_progress_percent=task_progress,
        acceptance_total=completion_audit.acceptance_total,
        acceptance_verified=completion_audit.acceptance_verified,
        acceptance_open=completion_audit.acceptance_open,
        acceptance_failed=completion_audit.acceptance_failed,
        acceptance_blocked=completion_audit.acceptance_blocked,
        acceptance_coverage_percent=acceptance_coverage,
        workspace_change_count=run.state.workspace_diff.total_files,
        pending_patch_count=sum(1 for patch in run.state.patch_proposals if patch.status == "pending"),
        pending_approval_count=len(pending_approvals),
        latest_autonomy_decision=(
            f"{latest_autonomy.decision}:{latest_autonomy.source}" if latest_autonomy.id else ""
        ),
        latest_verification_outcome=(
            f"{latest_verification.outcome}:{latest_verification.tool}" if latest_verification.id else ""
        ),
        current_policy_action=policy_simulation.policy_action,
        next_actions=next_actions,
        evidence=evidence,
    )


def _status(
    run: RunRecord,
    completion_audit: CompletionAuditReport,
    policy_simulation: PolicySimulationReport,
) -> str:
    state = run.state
    if run.status in {"blocked", "error"} or state.blockers:
        return "blocked"
    if run.status in {"waiting_approval", "waiting_goal_confirmation"} or completion_audit.pending_approvals:
        return "waiting"
    if state.recovery_plan.status == "active" or policy_simulation.policy_action == "recover":
        return "needs_recovery"
    if completion_audit.can_finish or run.status == "completed":
        return "near_completion"
    if completion_audit.acceptance_open or completion_audit.stale_evidence_count or policy_simulation.policy_action == "verify":
        return "needs_verification"
    return "on_track"


def _next_actions(
    run: RunRecord,
    completion_audit: CompletionAuditReport,
    policy_simulation: PolicySimulationReport,
    status: str,
) -> list[str]:
    actions: list[str] = []
    if policy_simulation.next_action:
        actions.append(policy_simulation.next_action)
    actions.extend(completion_audit.next_actions)
    if status == "needs_recovery" and run.state.recovery_plan.next_action:
        actions.insert(0, run.state.recovery_plan.next_action)
    if status == "waiting":
        actions.append("Resolve pending approval or goal confirmation before resuming.")
    if status == "near_completion":
        actions.append("Write final memory and close the run if no fresh edits are pending.")
    if not actions:
        actions.append(run.state.next_step or "Continue with the next safe action.")
    return list(dict.fromkeys(actions))[:8]


def _evidence(
    run: RunRecord,
    completion_audit: CompletionAuditReport,
    policy_simulation: PolicySimulationReport,
) -> list[str]:
    state = run.state
    evidence = [
        f"run_status={run.status}",
        f"milestone={state.milestone}",
        f"policy={policy_simulation.policy_action}",
        f"health={policy_simulation.run_health.level}/{policy_simulation.run_health.recommended_action}/{policy_simulation.run_health.score}",
        f"acceptance={completion_audit.acceptance_verified}/{completion_audit.acceptance_total}",
        f"workspace_changes={state.workspace_diff.total_files}",
    ]
    if state.autonomy_decisions.latest_decision.id:
        latest = state.autonomy_decisions.latest_decision
        evidence.append(f"latest_autonomy={latest.decision}:{latest.source}:{latest.reason}")
    if state.verification_outcomes.latest_outcome.id:
        latest_outcome = state.verification_outcomes.latest_outcome
        evidence.append(f"latest_verification={latest_outcome.outcome}:{latest_outcome.tool}:{latest_outcome.summary}")
    return evidence[:10]


def _summary(
    status: str,
    run: RunRecord,
    completion_audit: CompletionAuditReport,
    task_progress: int,
    acceptance_coverage: int,
) -> str:
    if status == "near_completion":
        return f"Near completion: {completion_audit.acceptance_verified}/{completion_audit.acceptance_total} acceptance criteria verified."
    if status == "needs_recovery":
        return f"Needs recovery: {run.state.recovery_plan.summary or 'policy recommends recovery'}"
    if status == "waiting":
        return "Waiting for approval or goal confirmation before the loop can continue."
    if status == "blocked":
        blocker = run.state.blockers[-1] if run.state.blockers else "run is blocked"
        return f"Blocked: {blocker}"
    if status == "needs_verification":
        return (
            f"Needs verification: {completion_audit.acceptance_verified}/{completion_audit.acceptance_total} "
            f"criteria verified, task progress {task_progress}%."
        )
    return f"On track: task progress {task_progress}%, acceptance coverage {acceptance_coverage}%."


def _percent(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return min(100, max(0, round((value / total) * 100)))
