from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import PolicySimulationReport, ResumeDecisionRecord, ResumeDecisionReport, RunRecord


PREFLIGHT_EVENT_KINDS = {"resume_preflight", "resume_preflight_blocked"}


def build_resume_decision_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    current_policy_simulation: PolicySimulationReport,
    *,
    decision_limit: int = 12,
) -> ResumeDecisionReport:
    all_decisions = [_decision_from_event(event) for event in events if event.get("kind") in PREFLIGHT_EVENT_KINDS]
    all_decisions = [decision for decision in all_decisions if decision is not None]
    accepted = [decision for decision in all_decisions if decision.accepted]
    blocked = [decision for decision in all_decisions if not decision.accepted]
    latest = all_decisions[-1] if all_decisions else ResumeDecisionRecord()
    latest_accepted = accepted[-1] if accepted else ResumeDecisionRecord()
    latest_blocked = blocked[-1] if blocked else ResumeDecisionRecord()
    matches_last_accepted = bool(latest_accepted.id) and _signature(latest_accepted) == _simulation_signature(current_policy_simulation)
    comparison, recommended_action = _comparison(
        latest=latest,
        latest_accepted=latest_accepted,
        latest_blocked=latest_blocked,
        current=current_policy_simulation,
        matches_last_accepted=matches_last_accepted,
    )

    return ResumeDecisionReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        decision_count=len(all_decisions),
        accepted_count=len(accepted),
        blocked_count=len(blocked),
        latest_decision=latest,
        latest_accepted=latest_accepted,
        latest_blocked=latest_blocked,
        current_policy_action=current_policy_simulation.policy_action,
        current_predicted_status=current_policy_simulation.predicted_status,
        current_predicted_milestone=current_policy_simulation.predicted_milestone,
        current_recommended_tool=current_policy_simulation.recommended_tool,
        current_recommended_label=current_policy_simulation.recommended_label,
        current_matches_last_accepted=matches_last_accepted,
        comparison_summary=comparison,
        recommended_action=recommended_action,
        decisions=all_decisions[-decision_limit:],
    )


def _decision_from_event(event: dict[str, Any]) -> ResumeDecisionRecord | None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    simulation_data = data.get("policy_simulation") if isinstance(data.get("policy_simulation"), dict) else {}
    if not simulation_data:
        return None
    simulation = PolicySimulationReport.model_validate(simulation_data)
    accepted = bool(data.get("accepted")) if "accepted" in data else event.get("kind") == "resume_preflight"
    source = str(data.get("source") or "")
    reason = str(data.get("reason") or event.get("message") or "")
    return ResumeDecisionRecord(
        id=int(event.get("id") or 0),
        timestamp=str(event.get("timestamp") or ""),
        kind=str(event.get("kind") or ""),
        source=source,
        accepted=accepted,
        reason=reason,
        policy_action=simulation.policy_action,
        predicted_status=simulation.predicted_status,
        predicted_milestone=simulation.predicted_milestone,
        safe_to_resume=simulation.safe_to_resume,
        auto_resume_eligible=simulation.auto_resume_eligible,
        recommended_tool=simulation.recommended_tool,
        recommended_label=simulation.recommended_label,
        health_level=simulation.run_health.level,
        health_action=simulation.run_health.recommended_action,
        health_score=simulation.run_health.score,
        summary=_decision_summary(source, accepted, simulation),
    )


def _decision_summary(source: str, accepted: bool, simulation: PolicySimulationReport) -> str:
    status = "accepted" if accepted else "blocked"
    return f"{source or 'unknown'} {status}: {simulation.policy_action} -> {simulation.predicted_status}/{simulation.predicted_milestone}"


def _signature(decision: ResumeDecisionRecord) -> tuple[str, str, str, str, str]:
    return (
        decision.policy_action,
        decision.predicted_status,
        decision.predicted_milestone,
        decision.recommended_tool,
        decision.recommended_label,
    )


def _simulation_signature(simulation: PolicySimulationReport) -> tuple[str, str, str, str, str]:
    return (
        simulation.policy_action,
        simulation.predicted_status,
        simulation.predicted_milestone,
        simulation.recommended_tool,
        simulation.recommended_label,
    )


def _comparison(
    *,
    latest: ResumeDecisionRecord,
    latest_accepted: ResumeDecisionRecord,
    latest_blocked: ResumeDecisionRecord,
    current: PolicySimulationReport,
    matches_last_accepted: bool,
) -> tuple[str, str]:
    if latest_blocked.id and (not latest.id or latest_blocked.id == latest.id):
        return (
            f"Latest resume preflight was blocked from {latest_blocked.source or 'unknown'}: {latest_blocked.reason}",
            "Resolve the blocked preflight before acting.",
        )
    if not latest_accepted.id:
        return (
            "No accepted resume preflight is recorded for this run.",
            "Run a resume preflight before continuing long-loop work.",
        )
    if matches_last_accepted:
        return (
            "Current policy simulation matches the latest accepted resume snapshot.",
            "Continue under the accepted resume context.",
        )
    return (
        "Current policy simulation differs from the latest accepted resume snapshot.",
        f"Refresh resume preflight before acting; current policy is {current.policy_action}.",
    )
