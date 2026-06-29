from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import (
    AcceptanceRecommendationTrace,
    ActionReadinessDecisionRecord,
    ActionReadinessDecisionReport,
    RunRecord,
    ToolCallRecord,
)


READINESS_DECISION_EVENT_KINDS = {
    "action_readiness_tool",
    "action_readiness_policy",
    "action_readiness_replan",
    "action_readiness_reorient",
}


def build_action_readiness_decision_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    decision_limit: int = 12,
) -> ActionReadinessDecisionReport:
    traces = {trace.id: trace for trace in run.state.acceptance_recommendation_traces}
    decisions = [
        decision
        for decision in (
            _decision_from_event(event, traces, run.state.tool_calls)
            for event in events
            if event.get("kind") in READINESS_DECISION_EVENT_KINDS
        )
        if decision is not None
    ]
    latest = decisions[-1] if decisions else ActionReadinessDecisionRecord()
    latest_tool = next((item for item in reversed(decisions) if item.selected_tool), ActionReadinessDecisionRecord())
    latest_policy = next(
        (item for item in reversed(decisions) if item.source == "policy"),
        ActionReadinessDecisionRecord(),
    )
    summary, recommended_action = _report_summary(latest)
    blocked_statuses = {"blocked", "waiting_approval", "recover"}
    tool_statuses = {"selected", "executed", "satisfied", "failed", "waiting_approval"}

    return ActionReadinessDecisionReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        decision_count=len(decisions),
        selected_count=sum(1 for item in decisions if item.selected_tool and item.status in tool_statuses),
        satisfied_count=sum(1 for item in decisions if item.status == "satisfied"),
        failed_count=sum(1 for item in decisions if item.status == "failed"),
        blocked_count=sum(1 for item in decisions if item.status in blocked_statuses),
        policy_gate_count=sum(1 for item in decisions if item.source == "policy"),
        harness_selected_count=sum(1 for item in decisions if item.selected_tool and item.source == "harness"),
        model_selected_count=sum(1 for item in decisions if item.selected_tool and item.source == "model"),
        fallback_selected_count=sum(1 for item in decisions if item.selected_tool and item.source == "fallback"),
        latest_decision=latest,
        latest_tool_decision=latest_tool,
        latest_policy_decision=latest_policy,
        summary=summary,
        recommended_action=recommended_action,
        decisions=decisions[-decision_limit:],
    )


def _decision_from_event(
    event: dict[str, Any],
    traces: dict[str, AcceptanceRecommendationTrace],
    tool_calls: list[ToolCallRecord],
) -> ActionReadinessDecisionRecord | None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    readiness = data.get("action_readiness") if isinstance(data.get("action_readiness"), dict) else {}
    if event.get("kind") == "action_readiness_tool":
        action = data.get("selected_action") if isinstance(data.get("selected_action"), dict) else {}
        return _tool_decision(event, readiness, action, traces, tool_calls)
    return _policy_decision(event, readiness)


def _tool_decision(
    event: dict[str, Any],
    readiness: dict[str, Any],
    action: dict[str, Any],
    traces: dict[str, AcceptanceRecommendationTrace],
    tool_calls: list[ToolCallRecord],
) -> ActionReadinessDecisionRecord:
    trace_id = str(action.get("recommendation_trace_id") or "")
    trace = traces.get(trace_id)
    selected_tool = str(action.get("tool") or "")
    matched_call = _matching_tool_call(tool_calls, selected_tool, str(event.get("timestamp") or ""))
    status = trace.status if trace else "selected"
    result_ok = trace.result_ok if trace else None
    result_summary = trace.result_summary if trace else ""
    evidence_status = trace.evidence_status if trace else ""
    source = trace.source if trace else "harness"
    criterion_id = trace.criterion_id if trace else str(action.get("recommendation_criterion_id") or "")
    criterion = trace.criterion if trace else ""
    label = trace.label if trace else str(action.get("recommendation_label") or readiness.get("suggested_label") or "")
    recommendation_id = trace.recommendation_id if trace else str(action.get("recommendation_id") or "")

    if trace is None and matched_call is not None:
        result_ok = matched_call.ok
        result_summary = matched_call.summary
        status = "waiting_approval" if matched_call.needs_approval else "executed" if matched_call.ok else "failed"

    return ActionReadinessDecisionRecord(
        id=int(event.get("id") or 0),
        timestamp=str(event.get("timestamp") or ""),
        kind=str(event.get("kind") or ""),
        status=status,
        readiness_status=str(readiness.get("status") or ""),
        ready_to_act=bool(readiness.get("ready_to_act")),
        source=source,
        selected_tool=selected_tool,
        suggested_tool=str(readiness.get("suggested_tool") or ""),
        suggested_label=str(readiness.get("suggested_label") or ""),
        recommendation_trace_id=trace_id,
        recommendation_id=recommendation_id,
        criterion_id=criterion_id,
        criterion=criterion,
        label=label,
        result_ok=result_ok,
        result_summary=result_summary,
        evidence_status=evidence_status,
        summary=_tool_summary(source, selected_tool, label, status),
        reason=str(readiness.get("recommended_action") or event.get("message") or ""),
    )


def _policy_decision(event: dict[str, Any], readiness: dict[str, Any]) -> ActionReadinessDecisionRecord | None:
    status = _policy_status(str(event.get("kind") or ""), str(readiness.get("status") or ""))
    return ActionReadinessDecisionRecord(
        id=int(event.get("id") or 0),
        timestamp=str(event.get("timestamp") or ""),
        kind=str(event.get("kind") or ""),
        status=status,
        readiness_status=str(readiness.get("status") or ""),
        ready_to_act=bool(readiness.get("ready_to_act")),
        source="policy",
        suggested_tool=str(readiness.get("suggested_tool") or ""),
        suggested_label=str(readiness.get("suggested_label") or ""),
        summary=_policy_summary(status, str(readiness.get("summary") or event.get("message") or "")),
        reason=str(readiness.get("recommended_action") or event.get("message") or ""),
    )


def _policy_status(kind: str, readiness_status: str) -> str:
    if kind == "action_readiness_replan" or readiness_status == "needs_replan":
        return "replanned"
    if kind == "action_readiness_reorient" or readiness_status == "reorient":
        return "reoriented"
    if readiness_status == "waiting_approval":
        return "waiting_approval"
    if readiness_status == "recover":
        return "recover"
    return "blocked"


def _matching_tool_call(tool_calls: list[ToolCallRecord], selected_tool: str, event_timestamp: str) -> ToolCallRecord | None:
    if not selected_tool:
        return None
    event_time = _parse_time(event_timestamp)
    candidates = [call for call in tool_calls if call.name == selected_tool]
    if event_time is not None:
        candidates = [
            call
            for call in candidates
            if (call_time := _parse_time(call.created_at)) is not None and call_time >= event_time
        ]
    return candidates[-1] if candidates else None


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _tool_summary(source: str, selected_tool: str, label: str, status: str) -> str:
    owner = source or "unknown"
    proof = f" for {label}" if label else ""
    if status == "satisfied":
        return f"{owner} selected {selected_tool}{proof}; intended proof was satisfied."
    if status == "failed":
        return f"{owner} selected {selected_tool}{proof}; tool result failed."
    if status == "waiting_approval":
        return f"{owner} selected {selected_tool}{proof}; action is waiting for approval."
    if status == "executed":
        return f"{owner} selected {selected_tool}{proof}; tool ran but proof is still unresolved."
    return f"{owner} selected {selected_tool}{proof}; waiting for result."


def _policy_summary(status: str, readiness_summary: str) -> str:
    if readiness_summary:
        return readiness_summary
    if status == "replanned":
        return "Action readiness routed the run back to planning."
    if status == "reoriented":
        return "Action readiness routed the run back to orientation."
    if status == "waiting_approval":
        return "Action readiness gated the run on a pending approval."
    if status == "recover":
        return "Action readiness paused the run for recovery."
    return "Action readiness blocked tool execution."


def _report_summary(latest: ActionReadinessDecisionRecord) -> tuple[str, str]:
    if not latest.id:
        return (
            "No action-readiness decisions recorded yet.",
            "Use the current action-readiness report before selecting the next tool.",
        )
    if latest.status == "satisfied":
        return (
            latest.summary,
            "Continue with the next milestone using the compact satisfied-proof context.",
        )
    if latest.status == "failed":
        return (
            latest.summary,
            "Recover or replan before repeating the same readiness-driven action.",
        )
    if latest.status == "executed":
        return (
            latest.summary,
            "Inspect remaining acceptance evidence and choose the next smallest proof action.",
        )
    if latest.status == "waiting_approval":
        return (
            latest.summary,
            "Wait for dashboard approval or ask the user before continuing.",
        )
    if latest.status in {"replanned", "reoriented"}:
        return (
            latest.summary,
            "Continue from the routed milestone with fresh compact context.",
        )
    if latest.status == "recover":
        return (
            latest.summary,
            "Resume through the recovery path only after reviewing the handoff.",
        )
    if latest.status == "blocked":
        return (
            latest.summary,
            "Resolve the readiness blocker before executing another tool.",
        )
    return (
        latest.summary,
        "Wait for the matching tool result or refresh action-readiness before acting.",
    )
