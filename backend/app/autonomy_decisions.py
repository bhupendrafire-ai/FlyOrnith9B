from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import AutonomyDecisionRecord, AutonomyDecisionReport, PolicySimulationReport, RunRecord


AUTONOMY_EVENT_KINDS = {
    "resume_preflight",
    "resume_preflight_blocked",
    "health_verify",
    "health_policy",
    "act_preflight_reorient",
    "action_readiness_policy",
    "action_readiness_replan",
    "action_readiness_reorient",
    "readiness_claim",
    "readiness_claim_blocked",
    "drift",
    "goal_proposed",
    "goal_review",
    "approval_required",
    "recovery_plan",
    "blocked",
    "completed",
    "decide",
    "control",
    "supervisor",
}

STOP_DECISIONS = {"recover", "pause", "wait_approval", "ask_user", "complete", "reorient", "replan", "blocked", "wait_goal"}
CONTINUE_DECISIONS = {"continue", "verify", "resume"}
WAIT_DECISIONS = {"wait_approval", "wait_goal", "ask_user"}


def build_autonomy_decision_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    current_policy: PolicySimulationReport | None = None,
    *,
    decision_limit: int = 16,
) -> AutonomyDecisionReport:
    policy = current_policy or run.state.handoff_summary.policy_simulation
    decisions = [
        decision
        for decision in (_decision_from_event(event) for event in events if event.get("kind") in AUTONOMY_EVENT_KINDS)
        if decision is not None
    ]
    latest = decisions[-1] if decisions else AutonomyDecisionRecord()
    latest_stop = next((item for item in reversed(decisions) if item.decision in STOP_DECISIONS), AutonomyDecisionRecord())
    latest_continue = next((item for item in reversed(decisions) if item.decision in CONTINUE_DECISIONS), AutonomyDecisionRecord())
    summary, recommended_action = _summary(latest, policy)

    return AutonomyDecisionReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        decision_count=len(decisions),
        continue_count=sum(1 for item in decisions if item.decision == "continue"),
        pause_count=sum(1 for item in decisions if item.decision == "pause"),
        recover_count=sum(1 for item in decisions if item.decision == "recover"),
        wait_count=sum(1 for item in decisions if item.decision in WAIT_DECISIONS),
        complete_count=sum(1 for item in decisions if item.decision == "complete"),
        blocked_count=sum(1 for item in decisions if item.decision == "blocked"),
        latest_decision=latest,
        latest_stop_decision=latest_stop,
        latest_continue_decision=latest_continue,
        current_policy_action=policy.policy_action,
        current_safe_to_resume=policy.safe_to_resume,
        current_next_action=policy.next_action,
        summary=summary,
        recommended_action=recommended_action,
        decisions=decisions[-decision_limit:],
    )


def _decision_from_event(event: dict[str, Any]) -> AutonomyDecisionRecord | None:
    kind = str(event.get("kind") or "")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    timestamp = str(event.get("timestamp") or "")
    message = str(event.get("message") or "")

    if kind in {"resume_preflight", "resume_preflight_blocked"}:
        return _resume_preflight_decision(event, data, timestamp, message)
    if kind in {"health_verify", "health_policy"}:
        return _health_decision(event, data, timestamp, message)
    if kind.startswith("action_readiness_"):
        return _action_readiness_decision(event, data, timestamp, message)
    if kind in {"readiness_claim", "readiness_claim_blocked"}:
        return _readiness_claim_decision(event, data, timestamp, message)
    if kind == "act_preflight_reorient":
        return _base(event, timestamp, "reorient", "resume_preflight", message, next_action="Re-orient before acting.")
    if kind == "drift":
        return _base(event, timestamp, "reorient", "drift_check", message, next_action="Re-orient because drift was detected.")
    if kind == "goal_proposed":
        return _base(event, timestamp, "wait_goal", "goal_review", message, next_action="Accept or reject the proposed goal revision.")
    if kind == "goal_review":
        return _base(event, timestamp, "continue", "goal_review", message)
    if kind == "approval_required":
        return _base(event, timestamp, "wait_approval", "tool_policy", message, next_action="Resolve pending approval in the dashboard.")
    if kind == "recovery_plan":
        return _base(event, timestamp, "recover", "failure_policy", message, next_action=_recovery_next_action(data))
    if kind == "blocked":
        return _base(event, timestamp, "blocked", _blocked_source(message), message, next_action="Resolve the blocker before continuing.")
    if kind == "completed":
        return _base(event, timestamp, "complete", "completion_audit", message, next_action="Run is complete.")
    if kind == "decide":
        return _base(event, timestamp, "continue", "milestone_decide", message, next_action="Continue with the next safe action.")
    if kind == "control":
        return _control_decision(event, timestamp, message)
    if kind == "supervisor":
        return _base(event, timestamp, "pause", "supervisor", message, next_action="Review supervisor recovery before resuming.")
    return None


def _resume_preflight_decision(
    event: dict[str, Any],
    data: dict[str, Any],
    timestamp: str,
    message: str,
) -> AutonomyDecisionRecord:
    simulation_data = data.get("policy_simulation") if isinstance(data.get("policy_simulation"), dict) else {}
    simulation = PolicySimulationReport.model_validate(simulation_data) if simulation_data else PolicySimulationReport()
    accepted = bool(data.get("accepted"))
    decision = "resume" if accepted else _decision_from_policy_action(simulation.policy_action)
    return _base(
        event,
        timestamp,
        decision,
        f"resume_preflight:{data.get('source') or 'unknown'}",
        str(data.get("reason") or message),
        policy_action=simulation.policy_action,
        predicted_status=simulation.predicted_status,
        predicted_milestone=simulation.predicted_milestone,
        health_level=simulation.run_health.level,
        health_action=simulation.run_health.recommended_action,
        health_score=simulation.run_health.score,
        safe_to_resume=simulation.safe_to_resume,
        auto_resume_eligible=simulation.auto_resume_eligible,
        next_action=simulation.next_action,
        blocking_signals=simulation.blocking_signals,
    )


def _health_decision(
    event: dict[str, Any],
    data: dict[str, Any],
    timestamp: str,
    message: str,
) -> AutonomyDecisionRecord:
    health = data.get("run_health") if isinstance(data.get("run_health"), dict) else {}
    action = str(health.get("recommended_action") or ("verify" if event.get("kind") == "health_verify" else "pause"))
    reason = _with_signal_evidence(message, health.get("signals"))
    return _base(
        event,
        timestamp,
        _decision_from_policy_action(action),
        "run_health",
        reason,
        health_level=str(health.get("level") or ""),
        health_action=action,
        health_score=int(health.get("score") or 0),
        next_action=_first_text(health.get("next_actions")) or message,
        blocking_signals=_signal_ids(health.get("signals")),
    )


def _action_readiness_decision(
    event: dict[str, Any],
    data: dict[str, Any],
    timestamp: str,
    message: str,
) -> AutonomyDecisionRecord:
    readiness = data.get("action_readiness") if isinstance(data.get("action_readiness"), dict) else {}
    status = str(readiness.get("status") or "")
    decision = {
        "recover": "recover",
        "waiting_approval": "wait_approval",
        "blocked": "pause",
        "needs_replan": "replan",
        "reorient": "reorient",
    }.get(status, "continue")
    if event.get("kind") == "action_readiness_replan":
        decision = "replan"
    elif event.get("kind") == "action_readiness_reorient":
        decision = "reorient"
    return _base(
        event,
        timestamp,
        decision,
        "action_readiness",
        str(readiness.get("summary") or message),
        next_action=str(readiness.get("recommended_action") or ""),
    )


def _readiness_claim_decision(
    event: dict[str, Any],
    data: dict[str, Any],
    timestamp: str,
    message: str,
) -> AutonomyDecisionRecord:
    readiness = data.get("readiness_completion") if isinstance(data.get("readiness_completion"), dict) else {}
    can_claim = bool(data.get("accepted") or readiness.get("can_claim_milestone"))
    next_action = str(data.get("next_action") or _first_text(readiness.get("next_actions")) or "")
    status = str(readiness.get("status") or "")
    reason = str(readiness.get("summary") or message)
    decision = "complete" if can_claim else "verify" if next_action else "replan"
    if status == "not_applicable":
        decision = "continue"
    return _base(
        event,
        timestamp,
        decision,
        "readiness_completion",
        reason,
        predicted_milestone="act" if decision == "verify" else "decide",
        next_action=next_action or ("Run is ready to complete." if can_claim else "Replan the readiness claim."),
        blocking_signals=_readiness_check_ids(readiness),
    )


def _control_decision(event: dict[str, Any], timestamp: str, message: str) -> AutonomyDecisionRecord:
    lowered = message.lower()
    if "paused" in lowered:
        decision = "pause"
    elif "resumed" in lowered:
        decision = "resume"
    elif "canceled" in lowered:
        decision = "pause"
    else:
        decision = "continue"
    return _base(event, timestamp, decision, "manual_control", message)


def _base(
    event: dict[str, Any],
    timestamp: str,
    decision: str,
    source: str,
    reason: str,
    *,
    policy_action: str = "",
    predicted_status: str = "",
    predicted_milestone: str = "",
    health_level: str = "",
    health_action: str = "",
    health_score: int = 0,
    safe_to_resume: bool = False,
    auto_resume_eligible: bool = False,
    next_action: str = "",
    blocking_signals: list[str] | None = None,
) -> AutonomyDecisionRecord:
    milestone = predicted_milestone or _milestone_from_message(reason)
    return AutonomyDecisionRecord(
        id=int(event.get("id") or 0),
        timestamp=timestamp,
        kind=str(event.get("kind") or ""),
        milestone=milestone,
        decision=decision,  # type: ignore[arg-type]
        source=source,
        policy_action=policy_action,
        predicted_status=predicted_status,
        predicted_milestone=predicted_milestone,
        health_level=health_level,
        health_action=health_action,
        health_score=health_score,
        safe_to_resume=safe_to_resume,
        auto_resume_eligible=auto_resume_eligible,
        reason=reason,
        next_action=next_action,
        blocking_signals=blocking_signals or [],
        summary=_decision_summary(decision, source, reason),
    )


def _decision_from_policy_action(action: str) -> str:
    return {
        "continue": "continue",
        "verify": "verify",
        "recover": "recover",
        "pause": "pause",
        "wait_approval": "wait_approval",
        "ask_user": "ask_user",
        "complete": "complete",
    }.get(action, "pause")


def _milestone_from_message(message: str) -> str:
    lowered = message.lower()
    for milestone in ("orient", "plan", "act", "verify", "checkpoint", "decide"):
        if milestone in lowered:
            return milestone
    return ""


def _first_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return ""


def _signal_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value[:8]:
        if isinstance(item, dict):
            signal_id = str(item.get("id") or "")
            if signal_id:
                ids.append(signal_id)
    return ids


def _readiness_check_ids(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    checks = value.get("checks")
    if not isinstance(checks, list):
        return []
    ids: list[str] = []
    for item in checks[:8]:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"block", "warn"}:
            continue
        check_id = str(item.get("id") or "")
        if check_id:
            ids.append(check_id)
    return ids


def _with_signal_evidence(message: str, value: Any) -> str:
    if not isinstance(value, list):
        return message
    evidence: list[str] = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        for entry in item.get("evidence") or []:
            text = str(entry)
            if text:
                evidence.append(text)
    if not evidence:
        return message
    return f"{message} Evidence: {'; '.join(evidence[:6])}"


def _recovery_next_action(data: dict[str, Any]) -> str:
    plan = data.get("recovery_plan") if isinstance(data.get("recovery_plan"), dict) else {}
    return str(plan.get("next_action") or "Resume or replan recovery before continuing.")


def _blocked_source(message: str) -> str:
    lowered = message.lower()
    if "max_loop_steps" in lowered or "wall-clock" in lowered or "budget" in lowered:
        return "loop_budget"
    return "blocker"


def _decision_summary(decision: str, source: str, reason: str) -> str:
    compact_reason = " ".join(reason.split())
    if compact_reason:
        return f"{source} chose {decision}: {compact_reason}"
    return f"{source} chose {decision}."


def _summary(latest: AutonomyDecisionRecord, policy: PolicySimulationReport) -> tuple[str, str]:
    if latest.id:
        if latest.decision in STOP_DECISIONS:
            return latest.summary, latest.next_action or "Review the stop decision before resuming."
        if latest.decision == "verify":
            return latest.summary, latest.next_action or "Run the next focused verification action."
        if latest.decision == "resume":
            return latest.summary, "Resume from the accepted policy snapshot."
        return latest.summary, latest.next_action or "Continue with the next safe action."
    if policy.run_id:
        decision = _decision_from_policy_action(policy.policy_action)
        return (
            f"Current policy would choose {decision}: {policy.reason}",
            policy.next_action or "Use the current policy simulation before acting.",
        )
    return (
        "No autonomy decisions recorded yet.",
        "Record the next milestone or policy decision before relying on compaction.",
    )
