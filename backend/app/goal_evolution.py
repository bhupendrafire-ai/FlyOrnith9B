from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .schemas import GoalEvolutionDecisionRecord, GoalEvolutionReport, RunRecord, RunState


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_goal_evolution_report(run: RunRecord) -> GoalEvolutionReport:
    decisions = run.state.goal_evolution.decisions[-30:]
    latest = decisions[-1] if decisions else GoalEvolutionDecisionRecord()
    pending = [item for item in decisions if item.status == "pending"]
    accepted = [item for item in decisions if item.status == "accepted"]
    rejected = [item for item in decisions if item.status == "rejected"]
    unchanged = [item for item in decisions if item.status == "unchanged"]

    if pending:
        summary = f"Goal update pending confirmation: {pending[-1].proposed_goal}"
        recommended = "Ask the operator to approve or reject the pending /goal update before resuming."
    elif latest.id:
        summary = f"Latest goal review {latest.status}: {latest.reason or latest.proposed_goal or latest.previous_goal}"
        recommended = "Continue under the active goal unless scope, blockers, acceptance criteria, or stop conditions materially change."
    else:
        summary = "No goal evolution reviews have been recorded."
        recommended = "Use /goal review when the long-run objective materially changes."

    return GoalEvolutionReport(
        run_id=run.id,
        generated_at=utc_stamp(),
        active_goal=run.state.goal,
        proposed_goal=run.state.proposed_goal or "",
        decision_count=len(decisions),
        pending_count=len(pending),
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        unchanged_count=len(unchanged),
        latest_decision=latest,
        summary=summary,
        recommended_action=recommended,
        decisions=decisions,
    )


def record_goal_proposal(
    state: RunState,
    run: RunRecord,
    *,
    proposed_goal: str,
    reason: str,
    source: str,
    approval_id: int = 0,
) -> GoalEvolutionDecisionRecord:
    latest = state.goal_evolution.decisions[-1] if state.goal_evolution.decisions else None
    if (
        latest
        and latest.status == "pending"
        and latest.proposed_goal == proposed_goal
        and latest.approval_id in {0, approval_id}
    ):
        latest.reason = reason or latest.reason
        latest.source = source or latest.source
        latest.approval_id = approval_id or latest.approval_id
        decision = latest
    else:
        decision = GoalEvolutionDecisionRecord(
            id=f"goal-{uuid4().hex[:8]}",
            status="pending",
            source=source,
            previous_goal=state.goal,
            proposed_goal=proposed_goal,
            reason=reason,
            material_change=_material_change_summary(state),
            step_count=state.step_count,
            milestone=state.milestone,
            approval_id=approval_id,
            created_at=utc_stamp(),
        )
        state.goal_evolution.decisions.append(decision)
        state.goal_evolution.decisions = state.goal_evolution.decisions[-30:]
    state.goal_evolution = build_goal_evolution_report(run.model_copy(update={"state": state}))
    return decision


def record_goal_unchanged(
    state: RunState,
    run: RunRecord,
    *,
    reason: str,
    source: str,
) -> GoalEvolutionDecisionRecord:
    decision = GoalEvolutionDecisionRecord(
        id=f"goal-{uuid4().hex[:8]}",
        status="unchanged",
        source=source,
        previous_goal=state.goal,
        proposed_goal="",
        reason=reason,
        material_change=_material_change_summary(state),
        step_count=state.step_count,
        milestone=state.milestone,
        created_at=utc_stamp(),
        resolved_at=utc_stamp(),
    )
    state.goal_evolution.decisions.append(decision)
    state.goal_evolution.decisions = state.goal_evolution.decisions[-30:]
    state.goal_evolution = build_goal_evolution_report(run.model_copy(update={"state": state}))
    return decision


def resolve_goal_proposal(
    state: RunState,
    run: RunRecord,
    *,
    proposed_goal: str,
    accepted: bool,
    approval_id: int = 0,
    reason: str = "",
) -> None:
    decision = _find_pending_goal_decision(state, proposed_goal, approval_id)
    if decision is None:
        decision = GoalEvolutionDecisionRecord(
            id=f"goal-{uuid4().hex[:8]}",
            status="pending",
            source="approval",
            previous_goal=state.goal,
            proposed_goal=proposed_goal,
            reason=reason,
            material_change=_material_change_summary(state),
            step_count=state.step_count,
            milestone=state.milestone,
            approval_id=approval_id,
            created_at=utc_stamp(),
        )
        state.goal_evolution.decisions.append(decision)
    decision.status = "accepted" if accepted else "rejected"
    decision.reason = reason or decision.reason
    decision.resolved_at = utc_stamp()
    decision.approval_id = approval_id or decision.approval_id
    state.goal_evolution.decisions = state.goal_evolution.decisions[-30:]
    state.goal_evolution = build_goal_evolution_report(run.model_copy(update={"state": state}))


def _find_pending_goal_decision(
    state: RunState,
    proposed_goal: str,
    approval_id: int,
) -> GoalEvolutionDecisionRecord | None:
    for decision in reversed(state.goal_evolution.decisions):
        if decision.status != "pending":
            continue
        if approval_id and decision.approval_id == approval_id:
            return decision
        if proposed_goal and decision.proposed_goal == proposed_goal:
            return decision
    return None


def _material_change_summary(state: RunState) -> str:
    parts: list[str] = []
    if state.blockers:
        parts.append(f"blockers={len(state.blockers)}")
    if state.acceptance_criteria:
        parts.append(f"criteria={len(state.acceptance_criteria)}")
    if state.risks:
        parts.append(f"risks={len(state.risks)}")
    if state.next_step:
        parts.append(f"next={state.next_step[:120]}")
    return "; ".join(parts) or "No material change signal recorded."
