from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import CheckpointQualityReport, CheckpointQualityResumeRecord, CheckpointQualityResumeReport, RunRecord


REPAIR_REASONS = {"checkpoint_quality", "ornith_preflight_checkpoint_quality"}
REPAIR_EVENT_KINDS = {"operator_action_dispatched", "ornith_preflight_action"}
RESUME_EVENT_KINDS = {"resume_preflight", "resume_preflight_blocked"}


def build_checkpoint_quality_resume_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    checkpoint_quality: CheckpointQualityReport | None = None,
    limit: int = 8,
) -> CheckpointQualityResumeReport:
    ordered = sorted(events, key=lambda event: int(event.get("id") or 0))
    repair_events = [event for event in ordered if event.get("kind") == "ornith_preflight_action"]
    repairs = [_repair_record(event) for event in repair_events]
    repairs = [repair for repair in repairs if repair is not None]
    if not repairs:
        repairs = [_repair_record(event) for event in ordered if event.get("kind") in REPAIR_EVENT_KINDS]
        repairs = [repair for repair in repairs if repair is not None]
    resumes = [event for event in ordered if event.get("kind") in RESUME_EVENT_KINDS]
    quality = checkpoint_quality or run.state.checkpoint_quality or run.state.handoff_summary.checkpoint_quality
    entries: list[CheckpointQualityResumeRecord] = []

    for index, repair in enumerate(repairs):
        next_repair_id = repairs[index + 1].repair_completed_event_id if index + 1 < len(repairs) else 0
        resume = next(
            (
                event
                for event in resumes
                if int(event.get("id") or 0) > repair.repair_completed_event_id
                and (not next_repair_id or int(event.get("id") or 0) < next_repair_id)
            ),
            None,
        )
        if resume:
            _attach_resume(repair, resume)
        repair.checkpoint_quality_status = quality.status
        repair.checkpoint_quality_ready = quality.status == "ready"
        repair.summary = _record_summary(repair)
        entries.append(repair)

    latest = entries[-1] if entries else CheckpointQualityResumeRecord()
    resumed_after_repair = sum(1 for entry in entries if entry.resume_event_id and entry.resume_accepted is True)
    blocked_after_repair = sum(1 for entry in entries if entry.resume_event_id and entry.resume_accepted is False)
    awaiting_resume = sum(1 for entry in entries if not entry.resume_event_id)
    status = "none"
    if latest.repair_completed_event_id and not latest.resume_event_id:
        status = "awaiting_resume"
    elif latest.resume_accepted is True:
        status = "resumed"
    elif latest.resume_accepted is False:
        status = "blocked"
    summary = _report_summary(status, len(entries), resumed_after_repair, blocked_after_repair, awaiting_resume)
    recommended_action = _recommended_action(status, latest)

    return CheckpointQualityResumeReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status=status,  # type: ignore[arg-type]
        repair_count=len(entries),
        resumed_after_repair_count=resumed_after_repair,
        blocked_after_repair_count=blocked_after_repair,
        awaiting_resume_count=awaiting_resume,
        latest=latest,
        summary=summary,
        recommended_action=recommended_action,
        entries=entries[-limit:],
    )


def _repair_record(event: dict[str, Any]) -> CheckpointQualityResumeRecord | None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    action = data.get("operator_action") if isinstance(data.get("operator_action"), dict) else {}
    reason = str(action.get("reason") or "")
    if reason not in REPAIR_REASONS:
        return None
    event_id = int(event.get("id") or 0)
    return CheckpointQualityResumeRecord(
        repair_event_id=event_id,
        repair_completed_event_id=event_id,
        repair_timestamp=str(event.get("timestamp") or ""),
        repair_reason=reason,
        repair_ui_target=str(action.get("ui_target") or ""),
        repair_action=str(action.get("action") or ""),
    )


def _attach_resume(record: CheckpointQualityResumeRecord, event: dict[str, Any]) -> None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    policy = data.get("policy_simulation") if isinstance(data.get("policy_simulation"), dict) else {}
    accepted = bool(data.get("accepted")) if "accepted" in data else event.get("kind") == "resume_preflight"
    record.resume_event_id = int(event.get("id") or 0)
    record.resume_timestamp = str(event.get("timestamp") or "")
    record.resume_source = str(data.get("source") or "")
    record.resume_accepted = accepted
    record.resume_policy_action = str(policy.get("policy_action") or "")
    record.resume_reason = str(data.get("reason") or event.get("message") or "")[:500]


def _record_summary(record: CheckpointQualityResumeRecord) -> str:
    if not record.resume_event_id:
        return f"Checkpoint-quality repair #{record.repair_completed_event_id} is awaiting a resume preflight."
    outcome = "accepted" if record.resume_accepted else "blocked"
    return (
        f"Checkpoint-quality repair #{record.repair_completed_event_id} was followed by "
        f"{outcome} resume preflight #{record.resume_event_id}."
    )


def _report_summary(status: str, repair_count: int, resumed: int, blocked: int, awaiting: int) -> str:
    if status == "none":
        return "No checkpoint-quality repair resume breadcrumb is recorded."
    return (
        f"Checkpoint-quality repairs: {repair_count}; resumed after repair: {resumed}; "
        f"blocked after repair: {blocked}; awaiting resume: {awaiting}."
    )


def _recommended_action(status: str, latest: CheckpointQualityResumeRecord) -> str:
    if status == "none":
        return "No checkpoint-quality repair resume breadcrumb is needed unless checkpoint repair runs."
    if status == "awaiting_resume":
        return "Run resume preflight from the repaired checkpoint before acting."
    if status == "blocked":
        return "Resolve the blocked resume preflight before continuing from checkpoint repair."
    if latest.checkpoint_quality_ready:
        return "Continue from the accepted resume preflight and repaired checkpoint-quality handoff."
    return "Refresh checkpoint quality before continuing from this repaired resume."
