from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import CompletionAuditReport, RunHealthReport, RunHealthSignal, RunRecord


def build_run_health(
    run: RunRecord,
    approvals: list[dict[str, Any]],
    completion_audit: CompletionAuditReport,
    *,
    lease_live: bool = False,
) -> RunHealthReport:
    state = run.state
    signals: list[RunHealthSignal] = []
    next_actions: list[str] = []
    score = 0

    pending_approvals = [approval for approval in approvals if approval.get("status") == "pending"]
    if pending_approvals:
        score += 25
        signals.append(
            RunHealthSignal(
                id="pending_approvals",
                severity="warning",
                summary="Pending approvals are blocking autonomous progress.",
                evidence=[f"{item.get('action_kind')}: {item.get('reason')}" for item in pending_approvals[:4]],
            )
        )
        next_actions.append("Resolve pending approvals in the dashboard.")

    if state.context_budget.pressure == "high":
        score += 25
        signals.append(
            RunHealthSignal(
                id="context_pressure_high",
                severity="warning",
                summary="Context budget pressure is high; compact and re-orient before continuing.",
                evidence=[f"{state.context_budget.estimated_tokens}/{state.context_budget.target_tokens} tokens"],
            )
        )
        next_actions.append("Checkpoint, compact context, and re-orient from handoff.")
    elif state.context_budget.pressure == "medium":
        score += 10
        signals.append(
            RunHealthSignal(
                id="context_pressure_medium",
                severity="info",
                summary="Context budget pressure is rising.",
                evidence=[f"{state.context_budget.estimated_tokens}/{state.context_budget.target_tokens} tokens"],
            )
        )

    max_failure_count = max(state.failure_counts.values(), default=0)
    if max_failure_count >= 3:
        score += 35
        signals.append(
            RunHealthSignal(
                id="repeated_failures",
                severity="critical",
                summary="A tool has failed repeatedly.",
                evidence=[f"{tool}: {count}" for tool, count in sorted(state.failure_counts.items())[-4:]],
            )
        )
        next_actions.append("Use the active recovery plan or replan around the failing tool.")
    elif max_failure_count > 0:
        score += 10
        signals.append(
            RunHealthSignal(
                id="recent_failures",
                severity="warning",
                summary="Recent tool failures need attention.",
                evidence=[f"{tool}: {count}" for tool, count in sorted(state.failure_counts.items())[-4:]],
            )
        )

    if state.recovery_plan.status == "active":
        score += 30
        signals.append(
            RunHealthSignal(
                id="active_recovery",
                severity="critical",
                summary="An active recovery plan is unresolved.",
                evidence=[state.recovery_plan.summary],
            )
        )
        next_actions.append(state.recovery_plan.next_action or "Resume or replan recovery.")

    latest_recovery_outcome = state.verification_outcomes.latest_recovery_outcome
    if latest_recovery_outcome.id:
        if latest_recovery_outcome.outcome == "failed":
            score += 35
            signals.append(
                RunHealthSignal(
                    id="recovery_verification_failed",
                    severity="critical",
                    summary="The latest recovery proof failed.",
                    evidence=[_recovery_outcome_summary(latest_recovery_outcome)],
                )
            )
            next_actions.append("Replan recovery before retrying the same proof action.")
        elif latest_recovery_outcome.outcome == "recovery_resolved":
            signals.append(
                RunHealthSignal(
                    id="recovery_verification_resolved",
                    severity="info",
                    summary="The latest recovery proof resolved the recovery path.",
                    evidence=[_recovery_outcome_summary(latest_recovery_outcome)],
                )
            )
        elif latest_recovery_outcome.closed_recovery or latest_recovery_outcome.during_recovery:
            score += 20
            signals.append(
                RunHealthSignal(
                    id="recovery_verification_unresolved",
                    severity="warning",
                    summary="The latest recovery proof has not produced resolved evidence.",
                    evidence=[_recovery_outcome_summary(latest_recovery_outcome)],
                )
            )
            next_actions.append("Inspect recovery evidence before resuming the main loop.")

    if state.blockers:
        score += 30
        signals.append(
            RunHealthSignal(
                id="unresolved_blockers",
                severity="critical",
                summary="Unresolved blockers remain in run state.",
                evidence=state.blockers[-4:],
            )
        )
        next_actions.append("Ask the user or replan around blockers.")

    if completion_audit.stale_evidence_count:
        score += min(25, completion_audit.stale_evidence_count * 12)
        signals.append(
            RunHealthSignal(
                id="stale_acceptance_evidence",
                severity="warning",
                summary="Verified acceptance evidence may be stale after edits.",
                evidence=[issue.summary for issue in completion_audit.issues if issue.id == "stale_acceptance_evidence"][:3],
            )
        )
        next_actions.append("Refresh verification for stale acceptance labels.")

    trace_failures = [
        trace
        for trace in state.acceptance_recommendation_traces[-12:]
        if trace.status in {"failed", "waiting_approval"}
    ]
    trace_executed_open = [
        trace
        for trace in state.acceptance_recommendation_traces[-12:]
        if trace.status == "executed"
    ]
    if trace_failures:
        score += max(30, min(35, len(trace_failures) * 15))
        signals.append(
            RunHealthSignal(
                id="recommendation_trace_failures",
                severity="warning",
                summary="Recommended proof actions failed or need approval.",
                evidence=[f"{trace.label}:{trace.selected_tool}:{trace.status}" for trace in trace_failures[:5]],
            )
        )
        next_actions.append("Review failed recommendation traces before retrying the same proof action.")
    if trace_executed_open:
        score += min(20, len(trace_executed_open) * 8)
        signals.append(
            RunHealthSignal(
                id="recommendation_not_satisfied",
                severity="warning",
                summary="Recommended actions executed without satisfying their intended evidence labels.",
                evidence=[f"{trace.label}:{trace.selected_tool}" for trace in trace_executed_open[:5]],
            )
        )
        next_actions.append("Try a narrower proof action for still-open evidence labels.")

    readiness_decisions = [
        decision
        for decision in state.action_readiness_decisions.decisions[-12:]
        if decision.selected_tool
    ]
    readiness_failures = [
        decision
        for decision in readiness_decisions
        if decision.status == "failed"
    ]
    satisfied_readiness_pairs = {
        _decision_key(decision)
        for decision in readiness_decisions
        if decision.status == "satisfied"
    }
    satisfied_readiness_pairs.update(
        (trace.label or "unknown", trace.selected_tool or trace.recommended_tool)
        for trace in state.acceptance_recommendation_traces[-24:]
        if trace.status == "satisfied" and (trace.selected_tool or trace.recommended_tool)
    )
    satisfied_readiness_labels = {
        label
        for evidence in state.acceptance_evidence
        if evidence.status == "verified"
        for label in evidence.matched_labels
    }
    readiness_unresolved = [
        decision
        for decision in readiness_decisions
        if decision.status == "executed"
        and _decision_key(decision) not in satisfied_readiness_pairs
        and (decision.label or decision.suggested_label or "unknown") not in satisfied_readiness_labels
    ]
    repeated_readiness_failures = _repeated_decision_buckets(readiness_failures)
    repeated_readiness_unresolved = _repeated_decision_buckets(readiness_unresolved)
    if repeated_readiness_failures:
        score += 35
        signals.append(
            RunHealthSignal(
                id="readiness_proof_failures",
                severity="critical",
                summary="Action-readiness proof tools have repeatedly failed.",
                evidence=repeated_readiness_failures[:5],
            )
        )
        next_actions.append("Recover or replan before retrying the same readiness proof tool.")
    elif readiness_failures:
        score += min(20, len(readiness_failures) * 10)
        signals.append(
            RunHealthSignal(
                id="readiness_proof_failure",
                severity="warning",
                summary="A readiness-selected proof tool failed.",
                evidence=[
                    f"{item.label or item.suggested_label}:{item.selected_tool}:{item.result_summary or item.summary}"
                    for item in readiness_failures[:5]
                ],
            )
        )
        next_actions.append("Review the failed readiness proof before retrying it.")
    if repeated_readiness_unresolved:
        score += 35
        signals.append(
            RunHealthSignal(
                id="readiness_proof_unresolved_loop",
                severity="critical",
                summary="Action-readiness proof tools repeatedly ran without satisfying their intended evidence.",
                evidence=repeated_readiness_unresolved[:5],
            )
        )
        next_actions.append("Replan the proof strategy instead of repeating the unresolved readiness action.")
    elif readiness_unresolved:
        score += min(18, len(readiness_unresolved) * 9)
        signals.append(
            RunHealthSignal(
                id="readiness_proof_unresolved",
                severity="warning",
                summary="A readiness-selected tool ran but left the intended proof unresolved.",
                evidence=[
                    f"{item.label or item.suggested_label}:{item.selected_tool}:{item.result_summary or item.summary}"
                    for item in readiness_unresolved[:5]
                ],
            )
        )
        next_actions.append("Choose a narrower proof action for the unresolved readiness evidence.")

    verified_objective_items = {
        item.id
        for item in getattr(state.objective_readiness, "items", [])
        if getattr(item, "status", "") == "verified"
    }
    objective_outcomes = [
        outcome
        for outcome in getattr(state, "objective_readiness_proof_outcomes", [])[-12:]
        if outcome.item_id and outcome.tool and outcome.item_id not in verified_objective_items
    ]
    objective_failures = [outcome for outcome in objective_outcomes if outcome.outcome == "failed"]
    objective_partials = [outcome for outcome in objective_outcomes if outcome.outcome == "partial"]
    objective_waiting = [outcome for outcome in objective_outcomes if outcome.outcome == "waiting_approval"]
    repeated_objective_failures = _repeated_objective_outcome_buckets(objective_failures)
    repeated_objective_partials = _repeated_objective_outcome_buckets(objective_partials)
    if repeated_objective_failures:
        score += 35
        signals.append(
            RunHealthSignal(
                id="objective_readiness_proof_failures",
                severity="critical",
                summary="Objective-readiness proof tools have repeatedly failed.",
                evidence=repeated_objective_failures[:5],
            )
        )
        next_actions.append("Recover or choose an alternate objective-readiness proof before retrying the same tool.")
    elif objective_failures:
        score += min(20, len(objective_failures) * 10)
        signals.append(
            RunHealthSignal(
                id="objective_readiness_proof_failure",
                severity="warning",
                summary="An objective-readiness proof tool failed.",
                evidence=[_objective_outcome_summary(outcome) for outcome in objective_failures[:5]],
            )
        )
        next_actions.append("Review the failed objective-readiness proof and choose a narrower alternate proof.")
    if repeated_objective_partials:
        score += 30
        signals.append(
            RunHealthSignal(
                id="objective_readiness_proof_partial_loop",
                severity="critical",
                summary="Objective-readiness proof tools repeatedly ran without fully verifying the item.",
                evidence=repeated_objective_partials[:5],
            )
        )
        next_actions.append("Replan the objective-readiness proof strategy before repeating the same partial proof.")
    elif objective_partials:
        score += min(15, len(objective_partials) * 8)
        signals.append(
            RunHealthSignal(
                id="objective_readiness_proof_partial",
                severity="warning",
                summary="An objective-readiness proof produced only partial evidence.",
                evidence=[_objective_outcome_summary(outcome) for outcome in objective_partials[:5]],
            )
        )
        next_actions.append("Use the playbook to select a proof that can fully verify the objective-readiness item.")
    if objective_waiting:
        score += 20
        signals.append(
            RunHealthSignal(
                id="objective_readiness_proof_waiting_approval",
                severity="warning",
                summary="An objective-readiness proof is waiting on supervised approval.",
                evidence=[_objective_outcome_summary(outcome) for outcome in objective_waiting[:5]],
            )
        )
        next_actions.append("Resolve the objective-readiness proof approval before continuing.")

    if run.status in {"queued", "running"} and state.run_lease.status == "active" and not lease_live:
        score += 20
        signals.append(
            RunHealthSignal(
                id="stale_or_orphaned_lease",
                severity="warning",
                summary="Run appears active but the lease is not live for this engine.",
                evidence=[f"owner={state.run_lease.owner_id}", f"expires={state.run_lease.expires_at}"],
            )
        )
        next_actions.append("Let the supervisor pause or recover the stale run before continuing.")

    if not completion_audit.can_finish and completion_audit.acceptance_open:
        score += min(15, completion_audit.acceptance_open * 5)
        signals.append(
            RunHealthSignal(
                id="open_acceptance_evidence",
                severity="info",
                summary="Acceptance criteria remain open.",
                evidence=[f"open={completion_audit.acceptance_open}", f"verified={completion_audit.acceptance_verified}"],
            )
        )

    score = min(100, score)
    level = _level_for_score(score, signals)
    recommended_action = _recommended_action(signals, completion_audit)
    if not next_actions and recommended_action == "continue":
        next_actions.append("Continue with the next planned safe action.")

    return RunHealthReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        score=score,
        level=level,
        recommended_action=recommended_action,
        summary=f"{level}: {recommended_action} ({score}/100)",
        signals=signals[:12],
        next_actions=list(dict.fromkeys(next_actions))[:8],
    )


def _level_for_score(score: int, signals: list[RunHealthSignal]) -> str:
    if any(signal.severity == "critical" for signal in signals) or score >= 70:
        return "blocked" if any(signal.id in {"unresolved_blockers", "active_recovery"} for signal in signals) else "stuck"
    if score >= 30:
        return "watch"
    return "healthy"


def _recommended_action(signals: list[RunHealthSignal], completion_audit: CompletionAuditReport) -> str:
    ids = {signal.id for signal in signals}
    if "pending_approvals" in ids or "objective_readiness_proof_waiting_approval" in ids:
        return "wait_approval"
    if "unresolved_blockers" in ids:
        return "ask_user"
    if (
        "active_recovery" in ids
        or "repeated_failures" in ids
        or "recovery_verification_failed" in ids
        or "stale_or_orphaned_lease" in ids
        or "readiness_proof_failures" in ids
        or "readiness_proof_unresolved_loop" in ids
        or "objective_readiness_proof_failures" in ids
        or "objective_readiness_proof_partial_loop" in ids
    ):
        return "recover"
    if "context_pressure_high" in ids:
        return "pause"
    if (
        "readiness_proof_failure" in ids
        or "readiness_proof_unresolved" in ids
        or "objective_readiness_proof_failure" in ids
        or "objective_readiness_proof_partial" in ids
    ):
        return "verify"
    if "stale_acceptance_evidence" in ids or completion_audit.acceptance_open:
        return "verify"
    return "continue"


def _recovery_outcome_summary(outcome: Any) -> str:
    label = outcome.proof_label or ",".join(outcome.labels_satisfied) or "proof"
    return f"{outcome.tool}:{outcome.outcome}:{label}: {outcome.summary}"


def _repeated_decision_buckets(decisions: list[Any]) -> list[str]:
    counts: dict[tuple[str, str], int] = {}
    examples: dict[tuple[str, str], str] = {}
    for decision in decisions:
        key = _decision_key(decision)
        counts[key] = counts.get(key, 0) + 1
        examples[key] = decision.result_summary or decision.summary
    return [
        f"{label}:{tool}: {count} attempt(s); latest={examples.get((label, tool), '')}"
        for (label, tool), count in sorted(counts.items())
        if count >= 2
    ]


def _decision_key(decision: Any) -> tuple[str, str]:
    return (decision.label or decision.suggested_label or "unknown", decision.selected_tool)


def _repeated_objective_outcome_buckets(outcomes: list[Any]) -> list[str]:
    counts: dict[tuple[str, str], int] = {}
    examples: dict[tuple[str, str], str] = {}
    for outcome in outcomes:
        key = (outcome.item_id, outcome.tool)
        counts[key] = counts.get(key, 0) + 1
        examples[key] = outcome.summary
    return [
        f"{item_id}:{tool}: {count} attempt(s); latest={examples.get((item_id, tool), '')}"
        for (item_id, tool), count in sorted(counts.items())
        if count >= 2
    ]


def _objective_outcome_summary(outcome: Any) -> str:
    label = outcome.evidence_label or outcome.item_id or "objective_readiness"
    return f"{outcome.item_id}:{outcome.tool}:{outcome.outcome}:{label}: {outcome.summary}"
