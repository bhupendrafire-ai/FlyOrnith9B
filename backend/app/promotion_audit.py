from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import (
    PromotionAuditIssue,
    PromotionAuditReport,
    ResumeHandoffDiffReport,
    RunRecord,
    ToolCallRecord,
    VerificationOutcomeReport,
)

EDIT_TOOL_NAMES = {"file_write", "patch_apply", "patch_rollback"}
VERIFY_TOOL_NAMES = {"run_tests"}
PROMOTION_APPROVAL_KINDS = {"patch_apply", "workspace_promote"}
VERIFY_COMMAND_MARKERS = (
    "pytest",
    "npm test",
    "npm run build",
    "npm run lint",
    "pnpm test",
    "pnpm exec tsc",
    "pnpm run build",
    "pnpm run lint",
    "python -m compileall",
    "python -m py_compile",
    "dotnet test",
    "cargo test",
    "gradlew.bat test",
    "gradlew test",
    "tsc",
    "vitest",
)
EDIT_COMMAND_MARKERS = (
    "apply_patch",
    "set-content",
    "add-content",
    "remove-item",
    "move-item",
    "copy-item",
    "python - <<",
    "python -c",
    "node -e",
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_promotion_audit(
    run: RunRecord,
    *,
    approvals: list[dict[str, Any]] | None = None,
    verification_outcomes: VerificationOutcomeReport | None = None,
    resume_handoff_diff: ResumeHandoffDiffReport | None = None,
) -> PromotionAuditReport:
    state = run.state
    diff = state.workspace_diff
    isolation = state.workspace_isolation
    approvals = approvals or []
    verification_report = verification_outcomes or state.verification_outcomes
    drift_report = resume_handoff_diff or state.resume_handoff_diff
    changed_files = {item.path for item in diff.files}
    issues: list[PromotionAuditIssue] = []

    if not isolation.enabled or not isolation.source_path or isolation.source_path == run.workspace_path:
        return PromotionAuditReport(
            run_id=run.id,
            generated_at=utc_stamp(),
            status="not_applicable",
            workspace_diff_status="not_isolated",
            workspace_diff_summary=diff.summary,
            resume_drift_status=drift_report.status,
            git_checkpoint_status=state.git_checkpoint.status,
            summary="Source promotion audit is not applicable because this run is not using a separate source workspace.",
            recommended_action="Continue in the active workspace or enable isolated workspaces before source promotion.",
        )

    if diff.total_files <= 0:
        return PromotionAuditReport(
            run_id=run.id,
            generated_at=utc_stamp(),
            status="not_applicable",
            workspace_diff_status="no_changes",
            workspace_diff_summary=diff.summary,
            resume_drift_status=drift_report.status,
            git_checkpoint_status=state.git_checkpoint.status,
            summary="No isolated workspace changes are currently available to promote.",
            recommended_action="Refresh the workspace diff after making isolated changes.",
        )

    latest_verification = _latest_verification_call(state.tool_calls)
    latest_change = _latest_change_call(state.tool_calls)
    pending_patches = _pending_patch_count(state.patch_proposals, changed_files)
    pending_approval_ids = _pending_promotion_approval_ids(approvals)
    pending_approvals = len(pending_approval_ids)
    unresolved_approval_histories = _unresolved_promotion_approval_histories(state, pending_approval_ids)

    if diff.truncated:
        issues.append(
            PromotionAuditIssue(
                id="diff_truncated",
                severity="warning",
                summary="Workspace diff is truncated, so the operator cannot inspect every changed file from the compact preview.",
                evidence=[diff.summary],
                next_action="Inspect the full workspace diff or narrow the file list before promotion.",
            )
        )
    if not state.patch_proposals and not state.patch_applications:
        issues.append(
            PromotionAuditIssue(
                id="patch_ledger_empty",
                severity="warning",
                summary="No patch proposal/application ledger is attached to the current workspace changes.",
                evidence=[f"changed_files={diff.total_files}"],
                next_action="Prefer patch_propose and approval-gated patch_apply for code edits before promotion.",
            )
        )
    if pending_patches:
        issues.append(
            PromotionAuditIssue(
                id="pending_patch_review",
                severity="blocker",
                summary="Patch proposals touching the changed workspace are still pending or approved-but-unapplied.",
                evidence=[f"pending_patches={pending_patches}"],
                next_action="Resolve pending patch proposals before promoting workspace changes to source.",
            )
        )
    if drift_report.status in {"changed", "blocked"}:
        issues.append(
            PromotionAuditIssue(
                id="resume_drift_unstable",
                severity="blocker",
                summary="Resume handoff drift is not stable enough for source promotion.",
                evidence=[drift_report.summary, f"status={drift_report.status}"],
                next_action=drift_report.recommended_action or "Refresh handoff/context and run a new resume preflight.",
            )
        )
    if drift_report.status == "no_baseline":
        issues.append(
            PromotionAuditIssue(
                id="resume_drift_no_baseline",
                severity="info",
                summary="No accepted resume preflight baseline exists yet.",
                evidence=[drift_report.summary],
                next_action="Run a resume preflight before relying on this audit after restart or compaction.",
            )
        )
    if latest_verification is None:
        issues.append(
            PromotionAuditIssue(
                id="verification_missing",
                severity="warning",
                summary="No successful test/build verification was found for the pending workspace changes.",
                evidence=[verification_report.summary or "No verification outcome report available."],
                next_action="Run the narrowest relevant test/build command before asking to promote source changes.",
            )
        )
    elif latest_change and _is_before(latest_verification.created_at, latest_change.created_at):
        issues.append(
            PromotionAuditIssue(
                id="verification_stale",
                severity="warning",
                summary="The latest successful verification happened before the latest edit-like tool call.",
                evidence=[
                    f"verification={latest_verification.name}:{latest_verification.created_at}",
                    f"latest_change={latest_change.name}:{latest_change.created_at}",
                ],
                next_action="Re-run the narrowest relevant verification after the latest workspace edit.",
            )
        )
    if pending_approvals:
        issues.append(
            PromotionAuditIssue(
                id="promotion_approval_pending",
                severity="info",
                summary="A source-promotion-related approval is already pending.",
                evidence=[f"pending_approvals={pending_approvals}"],
                next_action="Resolve the existing source-promotion approval in the dashboard.",
            )
        )
    if unresolved_approval_histories:
        issues.append(
            PromotionAuditIssue(
                id="promotion_approval_history_unresolved",
                severity="info",
                summary="A source-promotion approval has unresolved operator review history.",
                evidence=unresolved_approval_histories[:4],
                next_action="Resolve the reviewed pending promotion or patch approval before source promotion.",
            )
        )

    blocker_count = sum(1 for issue in issues if issue.severity == "blocker")
    verification_needed = any(issue.id in {"verification_missing", "verification_stale"} for issue in issues)
    if blocker_count:
        status = "blocked"
    elif verification_needed:
        status = "needs_verification"
    else:
        status = "ready"

    recommended = _recommended_action(status, issues)
    latest_verification_text = _call_text(latest_verification) if latest_verification else ""
    return PromotionAuditReport(
        run_id=run.id,
        generated_at=utc_stamp(),
        status=status,  # type: ignore[arg-type]
        ready_to_promote=status == "ready",
        changed_file_count=diff.total_files,
        patch_proposal_count=len(state.patch_proposals),
        patch_application_count=len(state.patch_applications),
        promotion_count=len(state.workspace_promotions),
        pending_patch_count=pending_patches,
        pending_approval_count=pending_approvals,
        unresolved_approval_history_count=len(unresolved_approval_histories),
        unresolved_approval_histories=unresolved_approval_histories[:6],
        latest_verification=latest_verification_text,
        workspace_diff_status="changes_detected",
        workspace_diff_summary=diff.summary,
        resume_drift_status=drift_report.status,
        git_checkpoint_status=state.git_checkpoint.status,
        summary=(
            f"Promotion audit {status}: {diff.total_files} changed file(s), "
            f"{len(state.patch_proposals)} patch proposal(s), {len(state.patch_applications)} patch application(s), "
            f"{blocker_count} blocker(s)."
        ),
        recommended_action=recommended,
        issues=issues[:12],
    )


def _pending_promotion_approval_ids(approvals: list[dict[str, Any]]) -> set[int]:
    approval_ids: set[int] = set()
    for approval in approvals:
        if approval.get("status") != "pending":
            continue
        if approval.get("action_kind") not in PROMOTION_APPROVAL_KINDS:
            continue
        approval_id = int(approval.get("id") or 0)
        if approval_id > 0:
            approval_ids.add(approval_id)
    return approval_ids


def _unresolved_promotion_approval_histories(state: Any, approval_ids: set[int]) -> list[str]:
    if not approval_ids:
        return []
    reports = [
        getattr(state, "operator_dispatches", None),
        getattr(getattr(state, "handoff_summary", None), "operator_dispatches", None),
    ]
    for report in reports:
        if not report or not getattr(report, "generated_at", ""):
            continue
        summaries: list[str] = []
        for history in getattr(report, "unresolved_approval_histories", []) or []:
            approval_id = int(getattr(history, "approval_id", 0) or 0)
            if approval_id not in approval_ids:
                continue
            summaries.append(_approval_history_summary(history))
        if summaries:
            return summaries[:6]
    return []


def _approval_history_summary(history: Any) -> str:
    approval_id = int(getattr(history, "approval_id", 0) or 0)
    latest_status = str(getattr(history, "latest_status", "") or "unknown")
    event_count = int(getattr(history, "event_count", 0) or 0)
    sequence = [str(item) for item in (getattr(history, "sequence", []) or [])[:5]]
    sequence_text = f":seq={' -> '.join(sequence)}" if sequence else ""
    return f"approval#{approval_id}:latest={latest_status}:events={event_count}{sequence_text}"


def _pending_patch_count(patches: list[Any], changed_files: set[str]) -> int:
    count = 0
    for patch in patches:
        if getattr(patch, "status", "") not in {"pending", "approved"}:
            continue
        files = {str(item) for item in getattr(patch, "files", [])}
        if not changed_files or not files or files & changed_files:
            count += 1
    return count


def _latest_verification_call(calls: list[ToolCallRecord]) -> ToolCallRecord | None:
    for call in reversed(calls[-40:]):
        if not call.ok or call.needs_approval:
            continue
        if call.name in VERIFY_TOOL_NAMES:
            return call
        if call.name == "shell" and _looks_like_verification_command(call.args.get("command")):
            return call
    return None


def _latest_change_call(calls: list[ToolCallRecord]) -> ToolCallRecord | None:
    for call in reversed(calls[-40:]):
        if not call.ok or call.needs_approval:
            continue
        if call.name in EDIT_TOOL_NAMES:
            return call
        if call.name == "shell" and _looks_like_edit_command(call.args.get("command")):
            return call
    return None


def _looks_like_verification_command(command: Any) -> bool:
    text = str(command or "").lower()
    return any(marker in text for marker in VERIFY_COMMAND_MARKERS)


def _looks_like_edit_command(command: Any) -> bool:
    text = str(command or "").lower()
    return any(marker in text for marker in EDIT_COMMAND_MARKERS)


def _is_before(left: str, right: str) -> bool:
    left_time = _parse_time(left)
    right_time = _parse_time(right)
    if left_time is None or right_time is None:
        return False
    return left_time < right_time


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _call_text(call: ToolCallRecord | None) -> str:
    if call is None:
        return ""
    return f"{call.name}: {call.summary[:220]}"


def _recommended_action(status: str, issues: list[PromotionAuditIssue]) -> str:
    if status == "ready":
        pending = next((issue for issue in issues if issue.id == "promotion_approval_pending"), None)
        if pending:
            return pending.next_action
        return "Request workspace promotion approval; the compact audit has verification evidence and no blocking drift."
    if status == "needs_verification":
        issue = next((item for item in issues if item.id in {"verification_missing", "verification_stale"}), None)
        return issue.next_action if issue else "Run focused verification before requesting source promotion."
    if status == "blocked":
        issue = next((item for item in issues if item.severity == "blocker"), None)
        return issue.next_action if issue else "Resolve blocking promotion audit issues before source promotion."
    return "Promotion is not applicable for this run."