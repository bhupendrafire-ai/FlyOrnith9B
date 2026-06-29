from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .acceptance import infer_required_labels
from .artifact_verification import artifact_verification_command, expected_artifact_exists, expected_artifact_suffix
from .schemas import (
    AcceptanceEvidenceRecommendation,
    ActionReadinessIssue,
    ActionReadinessReport,
    ResumeDecisionReport,
    ResumeHandoffDiffReport,
    RunRecord,
    TaskNode,
)


def build_action_readiness(
    run: RunRecord,
    resume_decisions: ResumeDecisionReport,
    resume_handoff_diff: ResumeHandoffDiffReport | None = None,
) -> ActionReadinessReport:
    state = run.state
    task = _current_task(state.task_graph, state.current_task_id)
    issues: list[ActionReadinessIssue] = []
    suggested_tool = ""
    suggested_label = ""

    if run.status in {"completed", "canceled"}:
        issues.append(
            ActionReadinessIssue(
                id="terminal_status",
                severity="blocker",
                summary=f"Run is {run.status}; no action should be selected.",
            )
        )
        return _report(run, resume_decisions, task, "blocked", False, "Do not act on a terminal run.", "", "", issues)

    if run.status == "waiting_approval" or state.active_tool:
        issues.append(
            ActionReadinessIssue(
                id="active_tool_or_approval",
                severity="blocker",
                summary="A pending tool or approval must be resolved before acting.",
                evidence=[f"status={run.status}", f"active_tool={state.active_tool or 'none'}"],
            )
        )
        return _report(run, resume_decisions, task, "waiting_approval", False, "Resolve pending approval or active tool state.", "", "", issues)

    if (
        state.recovery_plan.status == "active"
        or state.run_health.recommended_action == "recover"
    ) and not _is_active_recovery_task(state, task):
        issues.append(
            ActionReadinessIssue(
                id="active_recovery",
                severity="blocker",
                summary="Recovery is active or recommended before the next action.",
                evidence=[state.recovery_plan.summary or state.run_health.summary],
            )
        )
        return _report(run, resume_decisions, task, "recover", False, state.recovery_plan.next_action or "Resume or replan recovery.", "", "", issues)

    if state.blockers or state.run_health.recommended_action == "ask_user":
        issues.append(
            ActionReadinessIssue(
                id="unresolved_blockers",
                severity="blocker",
                summary="User attention or blocker resolution is needed before acting.",
                evidence=state.blockers[-4:] or [state.run_health.summary],
            )
        )
        return _report(run, resume_decisions, task, "blocked", False, "Resolve blockers or ask the user before acting.", "", "", issues)

    latest_accepted = resume_decisions.latest_accepted
    if (
        resume_handoff_diff
        and resume_handoff_diff.latest_accepted_event_id
        and resume_handoff_diff.status in {"changed", "blocked"}
        and state.act_preflight_checked_decision_id != resume_handoff_diff.latest_accepted_event_id
    ):
        severity = "blocker" if resume_handoff_diff.status == "blocked" else "warning"
        issues.append(
            ActionReadinessIssue(
                id="resume_handoff_drift",
                severity=severity,  # type: ignore[arg-type]
                summary="Current handoff/context differs from the latest accepted resume preflight snapshot.",
                evidence=[resume_handoff_diff.summary, *[change.summary for change in resume_handoff_diff.changes[:3]]],
            )
        )
        return _report(run, resume_decisions, task, "reorient", False, resume_handoff_diff.recommended_action, "", "", issues)

    if (
        latest_accepted.id
        and not resume_decisions.current_matches_last_accepted
        and state.act_preflight_checked_decision_id != latest_accepted.id
    ):
        issues.append(
            ActionReadinessIssue(
                id="resume_policy_diverged",
                severity="warning",
                summary="Current policy simulation differs from the latest accepted resume snapshot.",
                evidence=[resume_decisions.comparison_summary],
            )
        )
        return _report(run, resume_decisions, task, "reorient", False, "Re-orient before selecting the next action.", "", "", issues)

    if state.run_health.recommended_action == "pause" or state.context_budget.pressure == "high":
        issues.append(
            ActionReadinessIssue(
                id="context_reorientation_needed",
                severity="warning",
                summary="Context or health policy recommends pausing/re-orienting before acting.",
                evidence=[state.run_health.summary, f"context={state.context_budget.pressure}"],
            )
        )
        return _report(run, resume_decisions, task, "reorient", False, "Checkpoint and re-orient before acting.", "", "", issues)

    if state.milestone != "act":
        issues.append(
            ActionReadinessIssue(
                id="not_act_milestone",
                severity="info",
                summary="The loop is not currently at the act milestone.",
                evidence=[f"milestone={state.milestone}"],
            )
        )
        return _report(run, resume_decisions, task, "needs_replan", False, "Advance through orient/plan before selecting a tool.", "", "", issues)

    if not task:
        issues.append(
            ActionReadinessIssue(
                id="missing_current_task",
                severity="warning",
                summary="No current task is selected for the action milestone.",
            )
        )
        return _report(run, resume_decisions, task, "needs_replan", False, "Rebuild or select a current task before acting.", "", "", issues)

    if task.status in {"blocked", "failed"}:
        issues.append(
            ActionReadinessIssue(
                id="task_not_actionable",
                severity="blocker",
                summary="The current task is blocked or failed.",
                evidence=[f"{task.id}:{task.status}:{task.title}"],
            )
        )
        return _report(run, resume_decisions, task, "needs_replan", False, "Replan around the blocked or failed task.", "", "", issues)

    if expected_artifact_suffix(run, state) and not expected_artifact_exists(run, state):
        issues.append(
            ActionReadinessIssue(
                id="artifact_missing_before_verification",
                severity="info",
                summary="The requested deliverable artifact does not exist yet.",
                evidence=[f"workspace={run.workspace_path}"],
            )
        )
        return _report(
            run,
            resume_decisions,
            task,
            "ready",
            True,
            "Create the requested artifact before running artifact verification.",
            "",
            "",
            issues,
        )

    if _readiness_source_ref_refresh_required(run):
        preview = state.readiness_source_ref_preview
        labels = ",".join(preview.missing_proof_ref_labels) or "unknown"
        endpoint = f"/api/runs/{run.id}/readiness-source-refs/refresh"
        action = (
            "Dispatch confirmed readiness source-ref refresh before asking Ornith for another model tool: "
            f"POST {endpoint}."
        )
        issues.append(
            ActionReadinessIssue(
                id="readiness_source_ref_refresh_required",
                severity="blocker",
                summary="Readiness source evidence exists, but proof-history source refs are stale or missing.",
                evidence=[
                    preview.summary,
                    f"missing_proof={labels}",
                    f"source={','.join(preview.source_evidence_labels) or 'none'}",
                    f"proof={','.join(preview.proof_ref_labels) or 'none'}",
                    f"endpoint={endpoint}",
                ],
            )
        )
        return _report(run, resume_decisions, task, "blocked", False, action, "ask_user", "readiness_source_refs", issues)

    ranked_recommendations = rank_acceptance_recommendations(run)
    recommendation = ranked_recommendations[0] if ranked_recommendations else _fallback_recommendation(run)
    if recommendation:
        suggested_tool = recommendation.tool_kind
        suggested_label = recommendation.label
        if (
            recommendation.label == "verification"
            and _open_edit_required(state)
            and not _has_edit_evidence(state)
            and not expected_artifact_exists(run, state, recommendation.criterion)
        ):
            issues.append(
                ActionReadinessIssue(
                    id="deliverable_edit_before_verification",
                    severity="info",
                    summary="A deliverable-creation criterion is still open, so implementation should happen before artifact verification.",
                    evidence=[recommendation.action],
                )
            )
            return _report(
                run,
                resume_decisions,
                task,
                "ready",
                True,
                "Create or modify the requested deliverable before running artifact verification.",
                "",
                "",
                issues,
            )
        if not recommendation.available or recommendation.tool_kind == "ask_user":
            issues.append(
                ActionReadinessIssue(
                    id="proof_tool_unavailable",
                    severity="blocker",
                    summary="The next proof recommendation needs a tool or user input that is not available.",
                    evidence=[recommendation.reason, recommendation.action],
                )
            )
            return _report(run, resume_decisions, task, "blocked", False, recommendation.action, suggested_tool, suggested_label, issues)
        missing_source_labels = set(state.source_evidence.missing_labels)
        readiness_missing_source_labels = set(state.readiness_source_ref_preview.missing_source_evidence_labels)
        if recommendation.label in readiness_missing_source_labels and recommendation.label in {"web", "browser"}:
            issues.append(
                ActionReadinessIssue(
                    id="readiness_source_ref_evidence_missing",
                    severity="info",
                    summary="Readiness source-ref preview is missing source evidence and should drive the next act step.",
                    evidence=[state.readiness_source_ref_preview.summary, recommendation.action],
                )
            )
        elif recommendation.label in missing_source_labels and recommendation.label in {"web", "browser"}:
            issues.append(
                ActionReadinessIssue(
                    id="source_evidence_missing",
                    severity="info",
                    summary="Missing source-visible evidence should drive the next act step.",
                    evidence=[state.source_evidence.summary, recommendation.action],
                )
            )
        else:
            issues.append(
                ActionReadinessIssue(
                    id="acceptance_proof_recommended",
                    severity="info",
                    summary="A compact acceptance proof action should drive the next act step.",
                    evidence=[recommendation.action],
                )
            )
        return _report(run, resume_decisions, task, "needs_proof", True, recommendation.action, suggested_tool, suggested_label, issues)

    if state.run_health.recommended_action == "verify":
        issues.append(
            ActionReadinessIssue(
                id="verification_recommended",
                severity="info",
                summary="Run health recommends verification before broad implementation work.",
                evidence=state.run_health.next_actions[:3],
            )
        )
        return _report(run, resume_decisions, task, "needs_proof", True, state.run_health.next_actions[0] if state.run_health.next_actions else "Run focused verification.", "", "", issues)

    return _report(run, resume_decisions, task, "ready", True, state.next_step or "Select the next safe tool action.", "", "", issues)


def _current_task(tasks: list[TaskNode], task_id: str) -> TaskNode | None:
    return next((task for task in tasks if task.id == task_id), None)


def _is_active_recovery_task(state: Any, task: TaskNode | None) -> bool:
    if state.recovery_plan.status != "active" or state.milestone != "act" or not task:
        return False
    task_title = task.title.strip()
    recovery_steps = [step.strip() for step in state.recovery_plan.steps if step.strip()]
    if state.recovery_plan.next_action:
        recovery_steps.append(state.recovery_plan.next_action.strip())
    return task_title in set(recovery_steps)


def _open_edit_required(state: Any) -> bool:
    return any(
        item.status != "verified" and "edit" in set(item.required_labels)
        for item in state.acceptance_evidence
    )


def _has_edit_evidence(state: Any) -> bool:
    if state.files_touched or state.patch_proposals or state.patch_applications:
        return True
    if getattr(state.workspace_diff, "total_files", 0):
        return True
    edit_tools = {"file_write", "patch_apply", "patch_propose", "workspace_promote"}
    return any(call.ok and call.name in edit_tools for call in state.tool_calls)


def _readiness_source_ref_refresh_required(run: RunRecord) -> bool:
    preview = run.state.readiness_source_ref_preview
    return bool(
        preview.run_id
        and preview.status == "missing_proof_refs"
        and preview.missing_proof_ref_labels
        and not preview.missing_source_evidence_labels
    )


def rank_acceptance_recommendations(run: RunRecord) -> list[AcceptanceEvidenceRecommendation]:
    state = run.state
    preview = state.readiness_source_ref_preview
    missing_source_labels = set(state.source_evidence.missing_labels)
    readiness_missing_source_labels = set(preview.missing_source_evidence_labels)
    recommendations = list(state.acceptance_recommendations)
    recommendations.extend(_readiness_source_ref_recommendations(run, recommendations))
    satisfied_pairs = {
        (trace.label, trace.selected_tool or trace.recommended_tool)
        for trace in state.acceptance_recommendation_traces
        if trace.status == "satisfied"
    }

    def priority(item: AcceptanceEvidenceRecommendation) -> tuple[int, int, str]:
        score = 0
        if item.label in readiness_missing_source_labels and item.label in {"web", "browser"}:
            score -= 160
        if item.id.startswith("readiness-source-ref-"):
            score -= 40
        if item.label in missing_source_labels and item.label in {"web", "browser"}:
            score -= 100
        if (item.label, item.tool_kind) in satisfied_pairs:
            score -= 20
        if item.label in {"web", "browser"}:
            score -= 5
        if not item.available or item.tool_kind == "ask_user":
            score += 40
        try:
            original_index = state.acceptance_recommendations.index(item)
        except ValueError:
            original_index = 999
        return score, original_index, item.id

    return sorted(recommendations, key=priority)


def _readiness_source_ref_recommendations(
    run: RunRecord,
    existing: list[AcceptanceEvidenceRecommendation],
) -> list[AcceptanceEvidenceRecommendation]:
    state = run.state
    preview = state.readiness_source_ref_preview
    if not preview.run_id or not preview.missing_source_evidence_labels:
        return []
    existing_pairs = {(item.label, item.tool_kind) for item in existing}
    recommendations: list[AcceptanceEvidenceRecommendation] = []
    for label in preview.missing_source_evidence_labels[:4]:
        if label not in {"web", "browser"}:
            continue
        item = _recommendation_for_label(
            run,
            "readiness-source-ref",
            f"Readiness source-ref preview needs compact {label} source evidence before proof-history refresh.",
            label,
        )
        if (item.label, item.tool_kind) in existing_pairs:
            continue
        item.id = f"readiness-source-ref-{label}"
        item.reason = f"Readiness source-ref preview is missing compact {label} source evidence."
        item.action = item.action.rstrip(".") + "; then refresh readiness source refs."
        recommendations.append(item)
    return recommendations

def _fallback_recommendation(run: RunRecord) -> AcceptanceEvidenceRecommendation | None:
    state = run.state
    if state.run_health.recommended_action != "verify":
        return None
    for item in state.acceptance_evidence:
        if item.status == "verified":
            continue
        labels = item.required_labels or infer_required_labels(item.criterion)
        missing = [label for label in labels if label not in set(item.matched_labels)]
        label = missing[0] if missing else "verification"
        return _recommendation_for_label(run, item.id or "criterion-1", item.criterion, label)
    for index, criterion in enumerate(state.acceptance_criteria):
        labels = infer_required_labels(criterion)
        label = labels[0] if labels else "verification"
        return _recommendation_for_label(run, f"criterion-{index + 1}", criterion, label)
    return None


def _recommendation_for_label(
    run: RunRecord,
    criterion_id: str,
    criterion: str,
    label: str,
) -> AcceptanceEvidenceRecommendation:
    state = run.state
    artifact_command = artifact_verification_command(run, state, criterion)
    test_command = artifact_command or (state.repo_map.test_commands[0] if state.repo_map.test_commands else "python -m pytest")
    if label == "verification":
        return AcceptanceEvidenceRecommendation(
            id=f"{criterion_id}-verification",
            criterion_id=criterion_id,
            criterion=criterion,
            label=label,
            tool_kind="run_tests",
            action=f"Run the smallest relevant verification command: {test_command}",
            command_hint=test_command,
            reason=(
                "Criterion still needs artifact existence/load proof."
                if artifact_command
                else "Criterion still needs test/build/lint proof."
            ),
        )
    if label == "browser":
        if state.browser_enabled:
            return AcceptanceEvidenceRecommendation(
                id=f"{criterion_id}-browser",
                criterion_id=criterion_id,
                criterion=criterion,
                label=label,
                tool_kind="browser_screenshot",
                action="Capture a browser screenshot of the relevant local page or dashboard.",
                command_hint="url=http://127.0.0.1:5173",
                reason="Criterion still needs visible browser proof.",
            )
        if state.desktop_enabled:
            return AcceptanceEvidenceRecommendation(
                id=f"{criterion_id}-browser",
                criterion_id=criterion_id,
                criterion=criterion,
                label=label,
                tool_kind="desktop_screenshot",
                action="Capture a supervised desktop screenshot of the relevant UI.",
                reason="Browser tools are disabled, but desktop inspection is available.",
            )
    if label == "checkpoint":
        return AcceptanceEvidenceRecommendation(
            id=f"{criterion_id}-checkpoint",
            criterion_id=criterion_id,
            criterion=criterion,
            label=label,
            tool_kind="obsidian_checkpoint",
            action="Write a compact checkpoint and refresh the handoff bundle.",
            reason="Criterion still needs durable memory/handoff proof.",
        )
    if label == "web" and state.web_enabled:
        return AcceptanceEvidenceRecommendation(
            id=f"{criterion_id}-web",
            criterion_id=criterion_id,
            criterion=criterion,
            label=label,
            tool_kind="web_search",
            action="Search or fetch a cited source and store the citation with the result.",
            command_hint=criterion,
            reason="Criterion still needs web/source evidence.",
        )
    return AcceptanceEvidenceRecommendation(
        id=f"{criterion_id}-{label}",
        criterion_id=criterion_id,
        criterion=criterion,
        label=label,
        tool_kind="ask_user",
        action=f"Ask how to prove the missing evidence label: {label}.",
        reason="No available built-in tool recommendation exists for this label.",
        available=False,
    )


def _report(
    run: RunRecord,
    resume_decisions: ResumeDecisionReport,
    task: TaskNode | None,
    status: str,
    ready_to_act: bool,
    recommended_action: str,
    suggested_tool: str,
    suggested_label: str,
    issues: list[ActionReadinessIssue],
) -> ActionReadinessReport:
    state = run.state
    summary = f"{status}: {recommended_action}" if recommended_action else status
    return ActionReadinessReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status=status,  # type: ignore[arg-type]
        ready_to_act=ready_to_act,
        summary=summary,
        recommended_action=recommended_action,
        suggested_tool=suggested_tool,
        suggested_label=suggested_label,
        milestone=state.milestone,
        current_task_id=state.current_task_id,
        current_task_status=task.status if task else "",
        active_tool=state.active_tool,
        run_health_level=state.run_health.level,
        run_health_action=state.run_health.recommended_action,
        resume_decision_matches=resume_decisions.current_matches_last_accepted,
        latest_resume_decision_id=resume_decisions.latest_accepted.id,
        act_preflight_checked_decision_id=state.act_preflight_checked_decision_id,
        issues=issues[:8],
    )
