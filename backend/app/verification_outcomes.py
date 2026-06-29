from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import (
    AcceptanceCriterionEvidence,
    AcceptanceRecommendationTrace,
    RecoveryDecisionRecord,
    RecoveryDecisionReport,
    RunRecord,
    ToolCallRecord,
    VerificationOutcomeRecord,
    VerificationOutcomeReport,
)


def build_verification_outcome_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    recovery_decisions: RecoveryDecisionReport | None = None,
    *,
    outcome_limit: int = 16,
) -> VerificationOutcomeReport:
    state = run.state
    recovery_report = recovery_decisions or state.recovery_decisions
    recovery_resumes = _recovery_resume_events(events)
    records = [
        _record_from_tool_call(
            call,
            state.acceptance_evidence,
            state.acceptance_recommendation_traces,
            recovery_report,
            recovery_resumes,
        )
        for call in state.tool_calls[-40:]
    ]
    records = [record for record in records if _is_relevant(record)]
    latest = records[-1] if records else VerificationOutcomeRecord()
    latest_recovery = next((item for item in reversed(records) if item.during_recovery or item.closed_recovery), VerificationOutcomeRecord())
    summary, recommended_action = _summary(latest, latest_recovery)

    return VerificationOutcomeReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        outcome_count=len(records),
        verified_count=sum(1 for item in records if item.outcome in {"verified", "recovery_resolved"}),
        failed_count=sum(1 for item in records if item.outcome == "failed"),
        recovery_outcome_count=sum(1 for item in records if item.during_recovery or item.closed_recovery),
        recovery_resolved_count=sum(1 for item in records if item.closed_recovery and item.resolved_recovery_evidence),
        recovery_unresolved_count=sum(1 for item in records if item.closed_recovery and not item.resolved_recovery_evidence),
        latest_outcome=latest,
        latest_recovery_outcome=latest_recovery,
        summary=summary,
        recommended_action=recommended_action,
        outcomes=records[-outcome_limit:],
    )


def _record_from_tool_call(
    call: ToolCallRecord,
    evidence_items: list[AcceptanceCriterionEvidence],
    traces: list[AcceptanceRecommendationTrace],
    recovery_report: RecoveryDecisionReport,
    recovery_resumes: list[dict[str, Any]],
) -> VerificationOutcomeRecord:
    evidence = _matching_evidence(call, evidence_items)
    trace = _matching_trace(call, traces)
    recovery = _matching_recovery(call, recovery_report)
    resume_event = _matching_resume_event(call, recovery, recovery_resumes)
    labels_satisfied = _labels_satisfied_by_call(call, evidence)
    closed_recovery = bool(recovery.id and recovery.status == "resolved" and _tool_matches_recovery(call, recovery))
    during_recovery = bool(resume_event or closed_recovery or (recovery.id and recovery.status == "active"))
    resolved_recovery_evidence = bool(
        recovery.id
        and (
            recovery.resolved_by_evidence
            or (
                evidence
                and (
                    evidence.status == "verified"
                    or bool(labels_satisfied)
                )
            )
        )
    )
    outcome = _outcome(call, labels_satisfied, evidence, closed_recovery, resolved_recovery_evidence)
    criterion_id = evidence.id if evidence else trace.criterion_id
    criterion = evidence.criterion if evidence else trace.criterion
    proof_label = _proof_label(evidence, labels_satisfied, trace, recovery)

    return VerificationOutcomeRecord(
        id=f"outcome-{call.id}",
        timestamp=call.created_at,
        tool_call_id=call.id,
        tool=call.name,
        ok=call.ok,
        needs_approval=call.needs_approval,
        outcome=outcome,
        summary=call.summary,
        during_recovery=during_recovery,
        recovery_id=recovery.id,
        recovery_trigger=recovery.trigger,
        recovery_status=recovery.status,
        recovery_resume_event_id=int(resume_event.get("id") or 0) if resume_event else 0,
        recovery_resume_timestamp=str(resume_event.get("timestamp") or "") if resume_event else "",
        closed_recovery=closed_recovery,
        resolved_recovery_evidence=resolved_recovery_evidence,
        proof_label=proof_label,
        criterion_id=criterion_id,
        criterion=criterion,
        evidence_status=evidence.status if evidence else trace.evidence_status,
        required_labels=evidence.required_labels if evidence else [],
        matched_labels=evidence.matched_labels if evidence else [],
        labels_satisfied=labels_satisfied,
        recommendation_trace_id=trace.id,
        recommendation_status=trace.status,
        readiness_decision_id=recovery.readiness_decision_id,
        selected_strategy=recovery.selected_strategy,
    )


def _matching_evidence(
    call: ToolCallRecord,
    evidence_items: list[AcceptanceCriterionEvidence],
) -> AcceptanceCriterionEvidence | None:
    summary = call.summary.strip()
    exact = [
        item
        for item in evidence_items
        if item.last_tool == call.name and any(summary and summary in evidence for evidence in item.evidence)
    ]
    if exact:
        return exact[-1]
    by_tool = [item for item in evidence_items if item.last_tool == call.name]
    if by_tool:
        return by_tool[-1]
    return None


def _matching_trace(
    call: ToolCallRecord,
    traces: list[AcceptanceRecommendationTrace],
) -> AcceptanceRecommendationTrace:
    exact = [
        trace
        for trace in traces
        if trace.selected_tool == call.name and trace.result_summary and trace.result_summary in call.summary
    ]
    if exact:
        return exact[-1]
    by_tool = [trace for trace in traces if trace.selected_tool == call.name]
    return by_tool[-1] if by_tool else AcceptanceRecommendationTrace(
        id="",
        recommendation_id="",
        criterion_id="",
        criterion="",
        label="",
        recommended_tool="",
        selected_tool="",
    )


def _matching_recovery(
    call: ToolCallRecord,
    recovery_report: RecoveryDecisionReport,
) -> RecoveryDecisionRecord:
    candidates = [
        item
        for item in recovery_report.decisions
        if item.tool == call.name and _call_in_recovery_window(call, item)
    ]
    if candidates:
        return candidates[-1]
    active = recovery_report.active_decision
    if active.id and active.tool == call.name:
        return active
    return RecoveryDecisionRecord()


def _tool_matches_recovery(call: ToolCallRecord, recovery: RecoveryDecisionRecord) -> bool:
    return bool(recovery.id and recovery.tool == call.name)


def _call_in_recovery_window(call: ToolCallRecord, recovery: RecoveryDecisionRecord) -> bool:
    call_time = _parse_time(call.created_at)
    if call_time is None:
        return False
    start = _parse_time(recovery.created_at)
    end = _parse_time(recovery.resolved_at)
    if start and call_time < start:
        return False
    if end and call_time <= end:
        return True
    return recovery.status == "active"


def _matching_resume_event(
    call: ToolCallRecord,
    recovery: RecoveryDecisionRecord,
    recovery_resumes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    call_time = _parse_time(call.created_at)
    if call_time is None:
        return None
    candidates = []
    for event in recovery_resumes:
        event_time = _parse_time(str(event.get("timestamp") or ""))
        if event_time is None or event_time > call_time:
            continue
        plan = event.get("recovery_plan") if isinstance(event.get("recovery_plan"), dict) else {}
        if recovery.id and plan.get("id") and plan.get("id") != recovery.id:
            continue
        candidates.append(event)
    return candidates[-1] if candidates else None


def _recovery_resume_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resumes: list[dict[str, Any]] = []
    for event in events:
        if event.get("kind") != "recovery_resume":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        plan = data.get("recovery_plan") if isinstance(data.get("recovery_plan"), dict) else {}
        resumes.append(
            {
                "id": event.get("id"),
                "timestamp": event.get("timestamp"),
                "recovery_plan": plan,
            }
        )
    return resumes


def _labels_satisfied_by_call(
    call: ToolCallRecord,
    evidence: AcceptanceCriterionEvidence | None,
) -> list[str]:
    if not evidence:
        return []
    call_time = _parse_time(call.created_at)
    if call_time is None:
        return evidence.matched_labels if evidence.last_tool == call.name else []
    labels = [
        label
        for label, checked_at in evidence.label_checked_at.items()
        if label in set(evidence.matched_labels)
        and (checked_time := _parse_time(checked_at)) is not None
        and checked_time >= call_time
    ]
    if not labels and evidence.last_tool == call.name and evidence.status == "verified":
        labels = evidence.matched_labels
    return labels


def _proof_label(
    evidence: AcceptanceCriterionEvidence | None,
    labels_satisfied: list[str],
    trace: AcceptanceRecommendationTrace,
    recovery: RecoveryDecisionRecord,
) -> str:
    if labels_satisfied:
        return labels_satisfied[0]
    if trace.label:
        return trace.label
    if recovery.proof_label:
        return recovery.proof_label
    if evidence and evidence.matched_labels:
        return evidence.matched_labels[-1]
    return ""


def _outcome(
    call: ToolCallRecord,
    labels_satisfied: list[str],
    evidence: AcceptanceCriterionEvidence | None,
    closed_recovery: bool,
    resolved_recovery_evidence: bool,
) -> str:
    if call.needs_approval:
        return "waiting_approval"
    if not call.ok:
        return "failed"
    if closed_recovery and resolved_recovery_evidence:
        return "recovery_resolved"
    if evidence and evidence.status == "verified" and labels_satisfied:
        return "verified"
    if labels_satisfied:
        return "partial"
    if closed_recovery:
        return "recovery_tool_succeeded"
    return "executed"


def _is_relevant(record: VerificationOutcomeRecord) -> bool:
    if record.during_recovery or record.closed_recovery:
        return True
    if record.criterion_id or record.labels_satisfied or record.recommendation_trace_id:
        return True
    if record.tool in {"run_tests", "browser_screenshot", "desktop_screenshot", "web_search", "web_fetch", "obsidian_checkpoint"}:
        return True
    return False


def _summary(
    latest: VerificationOutcomeRecord,
    latest_recovery: VerificationOutcomeRecord,
) -> tuple[str, str]:
    if latest_recovery.id:
        if latest_recovery.outcome == "recovery_resolved":
            return (
                f"Recovery proof closed by {latest_recovery.tool}: {latest_recovery.summary}",
                "Continue from the next milestone with the verified recovery evidence.",
            )
        if latest_recovery.outcome == "failed":
            return (
                f"Recovery proof failed in {latest_recovery.tool}: {latest_recovery.summary}",
                "Replan recovery before retrying the same proof action.",
            )
        return (
            f"Latest recovery proof outcome is {latest_recovery.outcome} from {latest_recovery.tool}: {latest_recovery.summary}",
            "Inspect recovery evidence status before resuming the main loop.",
        )
    if latest.id:
        return (
            f"Latest verification outcome is {latest.outcome} from {latest.tool}: {latest.summary}",
            "Use acceptance evidence and recovery decisions before selecting the next proof action.",
        )
    return (
        "No verification outcomes recorded yet.",
        "Run the smallest proof action when acceptance or recovery requires evidence.",
    )


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
