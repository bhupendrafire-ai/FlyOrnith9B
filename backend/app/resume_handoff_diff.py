from __future__ import annotations

from typing import Any

from .persistence import utc_now
from .schemas import (
    ContextSnapshot,
    PolicySimulationReport,
    ResumeHandoffDiffChange,
    ResumeHandoffDiffReport,
    ResumePromptQualityReport,
    RunRecord,
)


def build_resume_handoff_diff(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    current_policy: PolicySimulationReport,
    current_quality: ResumePromptQualityReport,
) -> ResumeHandoffDiffReport:
    accepted = _latest_accepted_preflight(events)
    if accepted is None:
        return ResumeHandoffDiffReport(
            run_id=run.id,
            generated_at=utc_now(),
            status="no_baseline",
            ready_to_continue=True,
            summary="No accepted resume preflight baseline is recorded yet.",
            recommended_action="Run a resume preflight before relying on a long-loop handoff baseline.",
        )

    data = accepted.get("data") if isinstance(accepted.get("data"), dict) else {}
    accepted_policy = _policy_from_data(data)
    accepted_quality = _quality_from_data(data)
    accepted_context = _context_from_data(data)
    accepted_handoff = data.get("handoff_snapshot") if isinstance(data.get("handoff_snapshot"), dict) else {}
    current_context = run.state.context_snapshot
    current_handoff = _current_handoff_snapshot(run)
    changes: list[ResumeHandoffDiffChange] = []

    _compare(
        changes,
        "policy_action",
        _get(accepted_policy, "policy_action"),
        current_policy.policy_action,
        "Accepted resume policy action changed.",
        severity="warning",
    )
    _compare(
        changes,
        "predicted_milestone",
        _get(accepted_policy, "predicted_milestone"),
        current_policy.predicted_milestone,
        "Accepted resume milestone changed.",
        severity="warning",
    )
    _compare(
        changes,
        "recommended_tool",
        _get(accepted_policy, "recommended_tool"),
        current_policy.recommended_tool,
        "Accepted recommended tool changed.",
        severity="warning",
    )
    _compare(
        changes,
        "recommended_label",
        _get(accepted_policy, "recommended_label"),
        current_policy.recommended_label,
        "Accepted recommended proof label changed.",
        severity="warning",
    )
    _compare(
        changes,
        "next_action",
        str(accepted_handoff.get("next_action") or _get(accepted_quality, "next_action")),
        current_handoff["next_action"],
        "Current handoff next action differs from the accepted resume snapshot.",
        severity="warning",
    )
    _compare(
        changes,
        "milestone",
        str(accepted_handoff.get("milestone") or _get(accepted_policy, "current_milestone")),
        current_handoff["milestone"],
        "Current milestone differs from the accepted resume snapshot.",
        severity="warning",
    )
    _compare(
        changes,
        "current_task_id",
        str(accepted_handoff.get("current_task_id") or ""),
        current_handoff["current_task_id"],
        "Current task anchor differs from the accepted resume snapshot.",
        severity="warning",
    )
    _compare(
        changes,
        "active_goal",
        str(accepted_handoff.get("active_goal") or ""),
        current_handoff["active_goal"],
        "Active goal differs from the accepted resume snapshot.",
        severity="blocker",
    )
    _compare(
        changes,
        "resume_quality_status",
        _get(accepted_quality, "status"),
        current_quality.status,
        "Resume prompt quality status changed since the accepted preflight.",
        severity="blocker" if current_quality.status == "blocked" else "warning",
    )
    _compare(
        changes,
        "resume_quality_concrete_next",
        str(_get(accepted_quality, "concrete_next_action")),
        str(current_quality.concrete_next_action),
        "Concrete-next-action readiness changed since accepted preflight.",
        severity="blocker" if not current_quality.concrete_next_action else "warning",
    )

    if accepted_context.generated_at:
        _compare(
            changes,
            "context_coverage",
            accepted_context.coverage_status,
            current_context.coverage_status,
            "Context coverage changed since the accepted resume snapshot.",
            severity="blocker" if current_context.coverage_status == "critical" else "warning",
        )
        _compare(
            changes,
            "context_required_missing",
            ",".join(accepted_context.required_sections_missing),
            ",".join(current_context.required_sections_missing),
            "Required compact-context omissions changed since accepted preflight.",
            severity="blocker" if current_context.required_sections_missing else "warning",
        )
        _compare(
            changes,
            "context_selected_sections",
            str(accepted_context.selected_section_count),
            str(current_context.selected_section_count),
            "Selected compact-context section count changed.",
            severity="info",
        )

    if current_quality.status == "blocked" and not any(change.field == "resume_quality_status" for change in changes):
        changes.append(
            ResumeHandoffDiffChange(
                id="current_resume_quality_blocked",
                severity="blocker",
                field="resume_quality_status",
                accepted=_get(accepted_quality, "status"),
                current=current_quality.status,
                summary=current_quality.recommended_action or current_quality.summary,
            )
        )
    if current_context.coverage_status == "critical" and not any(change.field == "context_coverage" for change in changes):
        changes.append(
            ResumeHandoffDiffChange(
                id="current_context_critical",
                severity="blocker",
                field="context_coverage",
                accepted=accepted_context.coverage_status,
                current=current_context.coverage_status,
                summary=current_context.recommended_action,
            )
        )

    blocker_count = sum(1 for change in changes if change.severity == "blocker")
    warning_count = sum(1 for change in changes if change.severity == "warning")
    if blocker_count:
        status = "blocked"
        recommended = "Refresh handoff/context and run a new resume preflight before letting Ornith act."
    elif changes:
        status = "changed"
        recommended = "Review handoff drift and refresh resume preflight before asking Ornith for a broad action."
    else:
        status = "stable"
        recommended = "Continue under the latest accepted resume handoff snapshot."

    return ResumeHandoffDiffReport(
        run_id=run.id,
        generated_at=utc_now(),
        status=status,  # type: ignore[arg-type]
        ready_to_continue=status != "blocked",
        latest_accepted_event_id=int(accepted.get("id") or 0),
        latest_accepted_at=str(accepted.get("timestamp") or ""),
        latest_accepted_source=str(data.get("source") or ""),
        changed_count=len(changes),
        blocker_count=blocker_count,
        warning_count=warning_count,
        summary=f"{status}: {len(changes)} handoff drift change(s), {blocker_count} blocker(s), {warning_count} warning(s).",
        recommended_action=recommended,
        changes=changes[:16],
    )


def _latest_accepted_preflight(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("kind") != "resume_preflight":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if data.get("accepted") is False:
            continue
        return event
    return None


def _policy_from_data(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("policy_simulation")
    return value if isinstance(value, dict) else {}


def _quality_from_data(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("resume_prompt_quality")
    return value if isinstance(value, dict) else {}


def _context_from_data(data: dict[str, Any]) -> ContextSnapshot:
    value = data.get("context_snapshot")
    if isinstance(value, dict):
        return ContextSnapshot.model_validate(value)
    handoff = data.get("handoff_snapshot") if isinstance(data.get("handoff_snapshot"), dict) else {}
    value = handoff.get("context_snapshot")
    if isinstance(value, dict):
        return ContextSnapshot.model_validate(value)
    return ContextSnapshot()


def _current_handoff_snapshot(run: RunRecord) -> dict[str, str]:
    state = run.state
    return {
        "active_goal": state.goal,
        "next_action": state.next_step or state.handoff_summary.next_action,
        "milestone": state.milestone,
        "current_task_id": state.current_task_id,
    }


def _compare(
    changes: list[ResumeHandoffDiffChange],
    field: str,
    accepted: str,
    current: str,
    summary: str,
    *,
    severity: str,
) -> None:
    accepted = _compact(accepted)
    current = _compact(current)
    if accepted == current:
        return
    if not accepted and not current:
        return
    changes.append(
        ResumeHandoffDiffChange(
            id=f"handoff_diff_{field}",
            severity=severity,  # type: ignore[arg-type]
            field=field,
            accepted=accepted,
            current=current,
            summary=summary,
        )
    )


def _get(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    return str(value)


def _compact(value: str, limit: int = 220) -> str:
    return " ".join(str(value or "").split())[:limit]