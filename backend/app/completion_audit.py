from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .acceptance import compact_label_progress, infer_required_labels
from .artifact_verification import expected_artifact_suffix
from .schemas import (
    AcceptanceCriterionEvidence,
    CompletionAuditIssue,
    CompletionAuditReport,
    RunRecord,
    ToolCallRecord,
)


EDIT_LIKE_TOOLS = {"file_write", "patch_apply", "patch_rollback", "workspace_promote"}


def build_completion_audit(
    run: RunRecord,
    approvals: list[dict[str, Any]],
    *,
    strict_stale_evidence: bool = True,
    stale_edit_tools: set[str] | None = None,
) -> CompletionAuditReport:
    evidence = _evidence_for_run(run)
    issues: list[CompletionAuditIssue] = []
    next_actions: list[str] = []
    pending_approvals = [approval for approval in approvals if approval.get("status") == "pending"]
    stale = _stale_evidence(evidence, run.state.tool_calls, stale_edit_tools or EDIT_LIKE_TOOLS)
    html_quality_issues = _html_render_quality_issues(run)

    if run.state.acceptance_criteria and not all(item.status == "verified" for item in evidence):
        open_items = [item.criterion for item in evidence if item.status == "open"]
        failed_items = [item.criterion for item in evidence if item.status == "failed"]
        blocked_items = [item.criterion for item in evidence if item.status == "blocked"]
        issues.append(
            CompletionAuditIssue(
                id="acceptance_not_verified",
                severity="blocker",
                summary="Not all acceptance criteria have verified evidence.",
                evidence=[f"open: {item}" for item in open_items[:6]]
                + [f"failed: {item}" for item in failed_items[:6]]
                + [f"blocked: {item}" for item in blocked_items[:6]]
                + [
                    f"labels: {item.criterion} -> {compact_label_progress(item.required_labels, item.matched_labels)}"
                    for item in evidence
                    if item.status == "open" and item.required_labels
                ][:6],
            )
        )
        next_actions.append("Run or record focused verification for each open acceptance criterion.")
    elif not run.state.acceptance_criteria:
        issues.append(
            CompletionAuditIssue(
                id="no_acceptance_criteria",
                severity="warning",
                summary="No acceptance criteria are configured; completion relies on loop policy and human review.",
            )
        )
        next_actions.append("Add acceptance criteria for stronger completion proof.")

    if stale:
        severity = "blocker" if strict_stale_evidence else "warning"
        issues.append(
            CompletionAuditIssue(
                id="stale_acceptance_evidence",
                severity=severity,
                summary=(
                    "Some verified criteria may be stale because edits happened after verification."
                    if strict_stale_evidence
                    else "Some verified criteria may be stale, but strict stale-evidence blocking is disabled."
                ),
                evidence=[_stale_summary(item) for item in stale[:6]],
            )
        )
        next_actions.append(
            "Re-run verification after the latest edit-like tool call."
            if strict_stale_evidence
            else "Review whether stale verification should be refreshed before handoff."
        )

    if pending_approvals:
        issues.append(
            CompletionAuditIssue(
                id="pending_approvals",
                severity="blocker",
                summary="Pending approvals must be resolved before completion.",
                evidence=[f"{approval.get('action_kind')}: {approval.get('reason')}" for approval in pending_approvals[:6]],
            )
        )
        next_actions.append("Resolve pending approvals in the dashboard.")

    if html_quality_issues:
        issues.append(
            CompletionAuditIssue(
                id="html_render_quality",
                severity="blocker",
                summary="Rendered HTML artifact has visible quality issues.",
                evidence=html_quality_issues[:6],
            )
        )
        next_actions.append("Fix the rendered HTML artifact and recapture browser proof.")

    if run.state.blockers:
        issues.append(
            CompletionAuditIssue(
                id="unresolved_blockers",
                severity="blocker",
                summary="Unresolved blockers remain in run state.",
                evidence=run.state.blockers[-6:],
            )
        )
        next_actions.append("Clear or explicitly resolve blockers before finishing.")

    if run.state.recovery_plan.status == "active":
        issues.append(
            CompletionAuditIssue(
                id="active_recovery",
                severity="blocker",
                summary="An active recovery plan is still unresolved.",
                evidence=[run.state.recovery_plan.summary],
            )
        )
        next_actions.append("Resume or replan recovery before completion.")

    latest_recovery_outcome = run.state.verification_outcomes.latest_recovery_outcome
    if latest_recovery_outcome.id:
        if latest_recovery_outcome.outcome == "failed":
            issues.append(
                CompletionAuditIssue(
                    id="recovery_verification_failed",
                    severity="blocker",
                    summary="The latest recovery proof failed and must be replanned before completion.",
                    evidence=[_recovery_outcome_summary(latest_recovery_outcome)],
                )
            )
            next_actions.append("Replan recovery before retrying the same failed proof action.")
        elif latest_recovery_outcome.outcome == "recovery_resolved":
            issues.append(
                CompletionAuditIssue(
                    id="recovery_verification_resolved",
                    severity="info",
                    summary="The latest recovery proof produced resolved evidence.",
                    evidence=[_recovery_outcome_summary(latest_recovery_outcome)],
                )
            )
        elif latest_recovery_outcome.closed_recovery or latest_recovery_outcome.during_recovery:
            issues.append(
                CompletionAuditIssue(
                    id="recovery_verification_unresolved",
                    severity="warning",
                    summary="The latest recovery proof ran without resolved evidence.",
                    evidence=[_recovery_outcome_summary(latest_recovery_outcome)],
                )
            )
            next_actions.append("Inspect or refresh recovery evidence before completion.")

    if run.state.failure_records:
        issues.append(
            CompletionAuditIssue(
                id="recent_failures",
                severity="warning",
                summary="Recent failure records should be reviewed before completion.",
                evidence=[f"{record.kind}:{record.tool} x{record.count}" for record in run.state.failure_records[-6:]],
            )
        )

    blocker_count = sum(1 for issue in issues if issue.severity == "blocker")
    can_finish = blocker_count == 0
    return CompletionAuditReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status="ready" if can_finish else "not_ready",
        can_finish=can_finish,
        acceptance_total=len(evidence),
        acceptance_verified=sum(1 for item in evidence if item.status == "verified"),
        acceptance_open=sum(1 for item in evidence if item.status == "open"),
        acceptance_failed=sum(1 for item in evidence if item.status == "failed"),
        acceptance_blocked=sum(1 for item in evidence if item.status == "blocked"),
        pending_approvals=len(pending_approvals),
        blocker_count=len(run.state.blockers),
        recent_failure_count=len(run.state.failure_records),
        stale_evidence_count=len(stale),
        issues=issues,
        next_actions=list(dict.fromkeys(next_actions))[:8],
    )


def _evidence_for_run(run: RunRecord) -> list[AcceptanceCriterionEvidence]:
    by_criterion = {item.criterion: item for item in run.state.acceptance_evidence}
    evidence: list[AcceptanceCriterionEvidence] = []
    for index, criterion in enumerate(run.state.acceptance_criteria):
        existing = by_criterion.get(criterion)
        item = existing.model_copy(deep=True) if existing else AcceptanceCriterionEvidence(
            id=f"criterion-{index + 1}",
            criterion=criterion,
            status="open",
            required_labels=infer_required_labels(criterion),
            notes="No evidence record found.",
        )
        if not item.required_labels:
            item.required_labels = infer_required_labels(criterion)
        if item.required_labels:
            item.matched_labels = [label for label in item.required_labels if label in set(item.matched_labels)]
            item.label_checked_at = {
                label: item.label_checked_at[label]
                for label in item.required_labels
                if label in item.label_checked_at
            }
        evidence.append(item)
    return evidence


def _html_render_quality_issues(run: RunRecord) -> list[str]:
    if expected_artifact_suffix(run, run.state) != ".html":
        return []
    browser_calls = [call for call in run.state.tool_calls if call.name == "browser_screenshot" and call.ok]
    if not browser_calls:
        return []
    latest = browser_calls[-1]
    args = latest.args or {}
    visible_text = str(args.get("visible_text") or "")
    console_errors = [str(item) for item in args.get("console_errors") or [] if str(item).strip()]
    issues: list[str] = []
    lowered = f" {visible_text.lower()} "
    for token in ("undefined", "nan", "[object object]"):
        if token in lowered:
            issues.append(f"Visible browser text contains placeholder/runtime value: {token}.")
    if console_errors:
        issues.extend(f"Browser console error: {item}" for item in console_errors[:3])
    return issues


def _stale_evidence(
    evidence: list[AcceptanceCriterionEvidence],
    tool_calls: list[ToolCallRecord],
    edit_tools: set[str],
) -> list[AcceptanceCriterionEvidence]:
    latest_edit = max(
        (_parse_time(call.created_at) for call in tool_calls if call.name in edit_tools),
        default=None,
    )
    if not latest_edit:
        return []
    stale: list[AcceptanceCriterionEvidence] = []
    for item in evidence:
        if item.status != "verified":
            continue
        if item.required_labels:
            label_times = [
                _parse_time(item.label_checked_at.get(label, ""))
                for label in item.required_labels
            ]
            if any(checked is None or checked < latest_edit for checked in label_times):
                stale.append(item)
            continue
        checked = _parse_time(item.last_checked)
        if checked is None or checked < latest_edit:
            stale.append(item)
    return stale


def _stale_summary(item: AcceptanceCriterionEvidence) -> str:
    if item.required_labels:
        label_parts = [
            f"{label}:{item.label_checked_at.get(label) or 'never'}"
            for label in item.required_labels
        ]
        return f"{item.criterion}: " + ", ".join(label_parts)
    return f"{item.criterion}: last checked {item.last_checked or 'never'}"


def _recovery_outcome_summary(outcome: Any) -> str:
    label = outcome.proof_label or ",".join(outcome.labels_satisfied) or "proof"
    return f"{outcome.tool}:{outcome.outcome}:{label}: {outcome.summary}"


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
