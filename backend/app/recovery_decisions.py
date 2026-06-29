from __future__ import annotations

from datetime import datetime, timezone

from .schemas import (
    AcceptanceCriterionEvidence,
    ActionReadinessDecisionRecord,
    ActionReadinessDecisionReport,
    ObjectiveReadinessProofOutcome,
    RecoveryDecisionRecord,
    RecoveryDecisionReport,
    RecoveryPlan,
    RunRecord,
)

READINESS_RECOVERY_TRIGGERS = {"readiness_decision_loop", "objective_readiness_proof_loop"}


def build_recovery_decision_report(
    run: RunRecord,
    action_readiness_decisions: ActionReadinessDecisionReport | None = None,
    *,
    decision_limit: int = 12,
) -> RecoveryDecisionReport:
    state = run.state
    readiness_report = action_readiness_decisions or state.action_readiness_decisions
    plans = [*state.recovery_history]
    if state.recovery_plan.status == "active":
        plans.append(state.recovery_plan)
    decisions = [
        _record_from_plan(
            plan,
            readiness_report,
            state.acceptance_evidence,
            getattr(state, "objective_readiness_proof_outcomes", []),
        )
        for plan in plans
        if plan.status != "none" or plan.id
    ]
    latest = decisions[-1] if decisions else RecoveryDecisionRecord()
    active = next((item for item in reversed(decisions) if item.status == "active"), RecoveryDecisionRecord())
    latest_readiness = next(
        (item for item in reversed(decisions) if item.trigger in READINESS_RECOVERY_TRIGGERS),
        RecoveryDecisionRecord(),
    )
    summary, recommended_action = _summary(latest, active)

    return RecoveryDecisionReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        decision_count=len(decisions),
        active_recovery=bool(active.id),
        readiness_recovery_count=sum(1 for item in decisions if item.trigger in READINESS_RECOVERY_TRIGGERS),
        resolved_count=sum(1 for item in decisions if item.status == "resolved" or item.resolved_by_evidence),
        unresolved_count=sum(1 for item in decisions if item.status == "active" and not item.resolved_by_evidence),
        latest_decision=latest,
        active_decision=active,
        latest_readiness_decision=latest_readiness,
        summary=summary,
        recommended_action=recommended_action,
        decisions=decisions[-decision_limit:],
    )


def _record_from_plan(
    plan: RecoveryPlan,
    readiness_report: ActionReadinessDecisionReport,
    evidence: list[AcceptanceCriterionEvidence],
    objective_outcomes: list[ObjectiveReadinessProofOutcome],
) -> RecoveryDecisionRecord:
    readiness = _matching_readiness_decision(plan, readiness_report)
    objective_outcome = _matching_objective_outcome(plan, objective_outcomes)
    if objective_outcome.id:
        proof_label = objective_outcome.evidence_label or objective_outcome.item_id
        proof_status = objective_outcome.outcome
        criterion_id = objective_outcome.item_id
        criterion = f"Objective readiness: {objective_outcome.item_id}"
        evidence_status = objective_outcome.outcome
        resolved_by_evidence = objective_outcome.outcome == "verified"
    else:
        proof_label = readiness.label or readiness.suggested_label
        proof_status = readiness.status
        criterion_id = readiness.criterion_id
        criterion = readiness.criterion
        matched_evidence = _matching_evidence(evidence, readiness)
        evidence_status = matched_evidence.status if matched_evidence else readiness.evidence_status
        resolved_by_evidence = bool(
            matched_evidence
            and (
                matched_evidence.status == "verified"
                or (proof_label and proof_label in set(matched_evidence.matched_labels))
            )
        )
        if matched_evidence:
            criterion_id = criterion_id or matched_evidence.id
            criterion = criterion or matched_evidence.criterion
    selected_strategy = _selected_strategy(plan)
    summary = _record_summary(plan, proof_label, selected_strategy, evidence_status, resolved_by_evidence)

    return RecoveryDecisionRecord(
        id=plan.id,
        status=plan.status,
        trigger=plan.trigger,
        failure_kind=plan.failure_kind,
        tool=plan.tool,
        attempts=plan.attempts,
        created_at=plan.created_at,
        resolved_at=plan.resolved_at,
        proof_label=proof_label,
        proof_status=proof_status,
        criterion_id=criterion_id,
        criterion=criterion,
        evidence_status=evidence_status,
        readiness_decision_id=readiness.id,
        readiness_decision_status=readiness.status,
        activation_reason=plan.summary,
        selected_strategy=selected_strategy,
        next_action=plan.next_action,
        resolved_by_evidence=resolved_by_evidence,
        summary=summary,
    )


def _matching_readiness_decision(
    plan: RecoveryPlan,
    readiness_report: ActionReadinessDecisionReport,
) -> ActionReadinessDecisionRecord:
    if plan.trigger != "readiness_decision_loop" and not plan.failure_kind.startswith("readiness_"):
        return ActionReadinessDecisionRecord()
    expected_status = "executed" if "unresolved" in plan.failure_kind else "failed"
    candidates = [
        item
        for item in readiness_report.decisions
        if item.selected_tool == plan.tool and item.status == expected_status
    ]
    if not candidates:
        candidates = [
            item
            for item in readiness_report.decisions
            if item.selected_tool == plan.tool and item.status in {"failed", "executed"}
        ]
    if not candidates and readiness_report.latest_tool_decision.selected_tool == plan.tool:
        return readiness_report.latest_tool_decision
    return candidates[-1] if candidates else ActionReadinessDecisionRecord()


def _matching_objective_outcome(
    plan: RecoveryPlan,
    outcomes: list[ObjectiveReadinessProofOutcome],
) -> ObjectiveReadinessProofOutcome:
    if plan.trigger != "objective_readiness_proof_loop" and not plan.failure_kind.startswith("objective_readiness_"):
        return ObjectiveReadinessProofOutcome()
    item_id = _objective_item_id_from_plan(plan)
    candidates = [
        outcome
        for outcome in outcomes
        if outcome.tool == plan.tool and (not item_id or outcome.item_id == item_id)
    ]
    if not candidates:
        candidates = [outcome for outcome in outcomes if outcome.tool == plan.tool]
    return candidates[-1] if candidates else ObjectiveReadinessProofOutcome()


def _objective_item_id_from_plan(plan: RecoveryPlan) -> str:
    marker = "Objective-readiness proof loop for "
    if marker not in plan.summary:
        return ""
    tail = plan.summary.split(marker, 1)[1]
    return tail.split(" via ", 1)[0].strip()


def _matching_evidence(
    evidence: list[AcceptanceCriterionEvidence],
    readiness: ActionReadinessDecisionRecord,
) -> AcceptanceCriterionEvidence | None:
    if not readiness.id:
        return None
    for item in evidence:
        if readiness.criterion_id and item.id == readiness.criterion_id:
            return item
        if readiness.criterion and item.criterion == readiness.criterion:
            return item
    return None


def _selected_strategy(plan: RecoveryPlan) -> str:
    if not plan.steps:
        return plan.next_action
    if plan.trigger in READINESS_RECOVERY_TRIGGERS:
        if plan.steps[0].lower().startswith("review the latest replay") and len(plan.steps) > 2:
            return plan.steps[2]
        if len(plan.steps) > 1:
            return plan.steps[1]
    return plan.steps[0]


def _record_summary(
    plan: RecoveryPlan,
    proof_label: str,
    selected_strategy: str,
    evidence_status: str,
    resolved_by_evidence: bool,
) -> str:
    label = f" for {proof_label}" if proof_label else ""
    if resolved_by_evidence:
        return f"{plan.status} recovery{label}: evidence is verified; strategy was {selected_strategy}"
    if plan.status == "active":
        return f"active recovery{label}: {selected_strategy}"
    if plan.status == "resolved":
        suffix = f"; evidence_status={evidence_status}" if evidence_status else ""
        return f"resolved recovery{label}{suffix}: {selected_strategy}"
    if plan.status == "superseded":
        return f"superseded recovery{label}: {selected_strategy}"
    return plan.summary or selected_strategy


def _summary(latest: RecoveryDecisionRecord, active: RecoveryDecisionRecord) -> tuple[str, str]:
    if active.id:
        return (
            active.summary,
            f"Resume or replan active recovery: {active.next_action or active.selected_strategy}",
        )
    if not latest.id:
        return (
            "No recovery decisions recorded yet.",
            "Continue normal health and readiness policy checks.",
        )
    if latest.resolved_by_evidence:
        return (
            latest.summary,
            "Recovery resolved the intended evidence; continue from the next milestone.",
        )
    if latest.status == "resolved":
        return (
            latest.summary,
            "Verify acceptance evidence before treating recovery as complete.",
        )
    if latest.status == "superseded":
        return (
            latest.summary,
            "Use the latest active or replanned recovery context.",
        )
    return (
        latest.summary,
        "Review the latest recovery decision before continuing.",
    )
