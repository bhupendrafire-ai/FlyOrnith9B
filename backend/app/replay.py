from __future__ import annotations

from typing import Any

from .acceptance import compact_label_progress
from .action_context import build_action_context_pack
from .action_readiness import build_action_readiness
from .action_readiness_decisions import build_action_readiness_decision_report
from .autonomy_decisions import build_autonomy_decision_report
from .completion_audit import build_completion_audit
from .goal_evolution import build_goal_evolution_report
from .objective_readiness import build_objective_readiness
from .operator_dispatches import build_operator_dispatch_ledger
from .ornith_preflight_actions import build_ornith_preflight_action_ledger
from .policy_simulation import build_policy_simulation
from .post_action_retry import build_post_action_retry_report
from .persistence import utc_now
from .profile_adaptation import compact_adaptation_review
from .readiness_completion import build_readiness_completion
from .recovery_decisions import build_recovery_decision_report
from .report_integrity import build_report_integrity
from .resume_decisions import build_resume_decision_report
from .run_health import build_run_health
from .run_progress import build_run_progress
from .source_evidence import build_source_evidence_preview
from .tools import TOOL_NAMES
from .verification_outcomes import build_verification_outcome_report
from .schemas import ModelProfileAdaptationReview, OrnithLaunchChecklistReport, ReplayApproval, ReplayBundle, ReplayEvent, RunRecord


def build_replay_bundle(
    run: RunRecord,
    *,
    events: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    model_adaptation_reviews: list[ModelProfileAdaptationReview] | None = None,
    strict_stale_evidence: bool = True,
    stale_edit_tools: set[str] | None = None,
    event_limit: int = 80,
) -> ReplayBundle:
    compact_events = [compact_event(event) for event in events[-event_limit:]]
    compact_approvals = [compact_approval(approval) for approval in approvals]
    compact_reviews = [
        compact_adaptation_review(review)
        for review in (model_adaptation_reviews or [])[:10]
    ]
    completion_audit = build_completion_audit(
        run,
        approvals,
        strict_stale_evidence=strict_stale_evidence,
        stale_edit_tools=stale_edit_tools,
    )
    action_readiness_decisions = build_action_readiness_decision_report(run, events)
    health_run = run.model_copy(deep=True)
    health_run.state.action_readiness_decisions = action_readiness_decisions
    run_health = build_run_health(health_run, approvals, completion_audit)
    health_run.state.run_health = run_health
    policy_simulation = build_policy_simulation(health_run, completion_audit, run_health)
    resume_decisions = build_resume_decision_report(health_run, events, policy_simulation)
    autonomy_decisions = build_autonomy_decision_report(health_run, events, policy_simulation)
    health_run.state.autonomy_decisions = autonomy_decisions
    run_progress = build_run_progress(health_run, approvals, completion_audit, policy_simulation)
    readiness_run = health_run.model_copy(deep=True)
    readiness_run.state.run_health = run_health
    action_readiness = build_action_readiness(readiness_run, resume_decisions)
    recovery_decisions = build_recovery_decision_report(run, action_readiness_decisions)
    verification_outcomes = build_verification_outcome_report(run, events, recovery_decisions)
    goal_evolution = build_goal_evolution_report(run)
    post_action_retries = build_post_action_retry_report(run)
    operator_dispatches = build_operator_dispatch_ledger(events, run_id=run.id, limit=20)
    ornith_preflight_actions = build_ornith_preflight_action_ledger(events, run_id=run.id, limit=20)
    source_evidence = build_source_evidence_preview(run, limit=20)
    action_context_run = run.model_copy(deep=True)
    action_context_run.state.source_evidence = source_evidence
    action_context_run.state.run_health = run_health
    action_context_run.state.action_readiness = action_readiness
    action_context_run.state.action_readiness_decisions = action_readiness_decisions
    action_context_run.state.recovery_decisions = recovery_decisions
    action_context_run.state.verification_outcomes = verification_outcomes
    action_context = build_action_context_pack(action_context_run)
    ornith_preflight = run.state.ornith_preflight
    if not ornith_preflight.generated_at:
        ornith_preflight = run.state.handoff_summary.ornith_preflight
    if not ornith_preflight.generated_at:
        pending_approvals = sum(1 for approval in approvals if approval.get("status") == "pending")
        ornith_preflight = OrnithLaunchChecklistReport(
            run_id=run.id,
            generated_at=utc_now(),
            mode="resume",
            status="attention",
            ready_to_resume=False,
            summary="Replay generated a compact placeholder because this run had no stored Ornith preflight; refresh preflight before resuming.",
            model_profile_id=run.state.tool_profile,
            tool_profile=run.state.tool_profile,
            web_enabled=run.state.web_enabled,
            browser_enabled=run.state.browser_enabled,
            desktop_enabled=run.state.desktop_enabled,
            context_pressure=run.state.context_budget.pressure,
            context_tokens=run.state.context_budget.estimated_tokens,
            context_target_tokens=run.state.context_budget.target_tokens,
            pending_approval_count=pending_approvals,
            readiness_smoke_status=run.state.readiness_rehearsal.status or "not_run",
            dispatch_restart_smoke_status=run.state.operator_dispatch_restart_smoke.status or "not_run",
            run_health_level=run_health.level,
            run_health_action=run_health.recommended_action,
            next_actions=["Refresh Ornith preflight before resuming this run."],
        )
    handoff = run.state.handoff_summary.model_copy(
        update={
            "model_profile_adaptation_reviews": compact_reviews[:5],
            "completion_audit": completion_audit,
            "acceptance_recommendations": run.state.acceptance_recommendations,
            "acceptance_recommendation_traces": run.state.acceptance_recommendation_traces[-20:],
            "run_health": run_health,
            "policy_simulation": policy_simulation,
            "resume_decisions": resume_decisions,
            "run_progress": run_progress,
            "action_readiness": action_readiness,
            "action_readiness_decisions": action_readiness_decisions,
            "autonomy_decisions": autonomy_decisions,
            "recovery_decisions": recovery_decisions,
            "verification_outcomes": verification_outcomes,
            "goal_evolution": goal_evolution,
            "post_action_retries": post_action_retries,
            "operator_dispatches": operator_dispatches,
            "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke,
            "ornith_preflight_actions": ornith_preflight_actions,
            "source_evidence": source_evidence,
            "action_context": action_context,
            "ornith_preflight": ornith_preflight,
            "objective_readiness_proof_outcomes": run.state.objective_readiness_proof_outcomes[-20:],
            "readiness_rehearsal": run.state.readiness_rehearsal,
        }
    )
    report_integrity = build_report_integrity(health_run, events, handoff=handoff)
    handoff.report_integrity = report_integrity
    health_run.state.report_integrity = report_integrity
    objective_readiness = build_objective_readiness(health_run, tool_names=set(TOOL_NAMES))
    handoff.objective_readiness = objective_readiness
    readiness_completion = build_readiness_completion(
        health_run,
        objective_readiness,
        run_progress,
        completion_audit,
    )
    handoff.readiness_completion = readiness_completion
    bundle = ReplayBundle(
        run_id=run.id,
        title=run.title,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
        workspace_path=run.workspace_path,
        original_goal=run.goal,
        active_goal=run.state.goal,
        goal_evolution=goal_evolution,
        milestone=run.state.milestone,
        next_action=run.state.next_step,
        context_pressure=run.state.context_budget.pressure,
        handoff=handoff,
        event_count=len(events),
        approval_count=len(approvals),
        events=compact_events,
        approvals=compact_approvals,
        acceptance_evidence=run.state.acceptance_evidence,
        acceptance_recommendations=run.state.acceptance_recommendations,
        acceptance_recommendation_traces=run.state.acceptance_recommendation_traces[-20:],
        run_health=run_health,
        completion_audit=completion_audit,
        policy_simulation=policy_simulation,
        resume_decisions=resume_decisions,
        run_progress=run_progress,
        report_integrity=report_integrity,
        objective_readiness=objective_readiness,
        objective_readiness_proof_outcomes=run.state.objective_readiness_proof_outcomes[-20:],
        readiness_completion=readiness_completion,
        readiness_rehearsal=run.state.readiness_rehearsal,
        action_readiness=action_readiness,
        action_readiness_decisions=action_readiness_decisions,
        autonomy_decisions=autonomy_decisions,
        recovery_decisions=recovery_decisions,
        verification_outcomes=verification_outcomes,
        post_action_retries=post_action_retries,
        operator_dispatches=operator_dispatches,
        operator_dispatch_restart_smoke=run.state.operator_dispatch_restart_smoke,
        ornith_preflight=ornith_preflight,
        ornith_preflight_actions=ornith_preflight_actions,
        source_evidence=source_evidence,
        action_context=action_context,
        task_graph=run.state.task_graph[-20:],
        tool_calls=run.state.tool_calls[-20:],
        model_interactions=run.state.model_interactions[-20:],
        failure_records=run.state.failure_records[-20:],
        recovery_plan=run.state.recovery_plan,
        recovery_history=run.state.recovery_history[-10:],
        model_profile_adaptation_reviews=compact_reviews,
        run_lease=run.state.run_lease,
        workspace_diff_summary=run.state.workspace_diff.summary,
        workspace_promotions=run.state.workspace_promotions[-10:],
        patch_applications=run.state.patch_applications[-10:],
    )
    bundle.markdown = render_replay_markdown(bundle)
    return bundle


def compact_event(event: dict[str, Any]) -> ReplayEvent:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    ok = data.get("ok") if isinstance(data, dict) and isinstance(data.get("ok"), bool) else None
    return ReplayEvent(
        id=int(event.get("id") or 0),
        timestamp=str(event.get("timestamp") or ""),
        kind=str(event.get("kind") or ""),
        message=single_line(str(event.get("message") or ""), 600),
        ok=ok,
        data_keys=sorted(str(key) for key in data.keys())[:30] if isinstance(data, dict) else [],
    )


def compact_approval(approval: dict[str, Any]) -> ReplayApproval:
    payload = approval.get("payload") if isinstance(approval.get("payload"), dict) else {}
    preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
    files_raw = preview.get("files") if isinstance(preview, dict) else []
    files: list[str] = []
    if isinstance(files_raw, list):
        for item in files_raw[:12]:
            if isinstance(item, dict):
                status = str(item.get("status") or "change")
                path = str(item.get("path") or "unknown")
                files.append(f"{status}: {path}")
    return ReplayApproval(
        id=int(approval.get("id") or 0),
        status=str(approval.get("status") or ""),
        action_kind=str(approval.get("action_kind") or ""),
        reason=single_line(str(approval.get("reason") or ""), 600),
        created_at=str(approval.get("created_at") or ""),
        resolved_at=approval.get("resolved_at"),
        preview_summary=single_line(str(preview.get("summary") or ""), 600) if isinstance(preview, dict) else "",
        preview_files=files,
    )


def render_replay_markdown(bundle: ReplayBundle) -> str:
    lines = [
        f"# Replay: {bundle.title}",
        "",
        f"- Run: `{bundle.run_id}`",
        f"- Status: `{bundle.status}`",
        f"- Created: {bundle.created_at}",
        f"- Updated: {bundle.updated_at}",
        f"- Workspace: `{bundle.workspace_path}`",
        f"- Context pressure: `{bundle.context_pressure}`",
        "",
        "## Goal",
        "",
        f"- Original: {bundle.original_goal}",
        f"- Active: {bundle.active_goal}",
        f"- Milestone: `{bundle.milestone}`",
        f"- Next action: {bundle.next_action}",
    ]
    if bundle.goal_evolution.decision_count:
        lines.extend(["", "## Goal Evolution"])
        lines.append(f"- Decisions: `{bundle.goal_evolution.decision_count}` pending `{bundle.goal_evolution.pending_count}` accepted `{bundle.goal_evolution.accepted_count}` rejected `{bundle.goal_evolution.rejected_count}` unchanged `{bundle.goal_evolution.unchanged_count}`")
        lines.append(f"- Summary: {bundle.goal_evolution.summary}")
        lines.append(f"- Recommended action: {bundle.goal_evolution.recommended_action}")
        for decision in bundle.goal_evolution.decisions[-8:]:
            proposed = f" -> {decision.proposed_goal}" if decision.proposed_goal else ""
            lines.append(
                f"- `{decision.status}` `{decision.source}`{proposed}: {decision.reason or decision.material_change}"
            )
    lines.extend([
        "",
        "## Handoff",
        "",
        bundle.handoff.resume_prompt or "No resume prompt recorded.",
        "",
        "## Approvals",
    ])
    if bundle.approvals:
        for approval in bundle.approvals[:20]:
            lines.append(
                f"- #{approval.id} `{approval.status}` `{approval.action_kind}`: {approval.reason}"
            )
            if approval.preview_summary:
                lines.append(f"  Preview: {approval.preview_summary}")
            for file in approval.preview_files[:8]:
                lines.append(f"  - {file}")
    else:
        lines.append("- None.")
    if bundle.source_evidence.total_count:
        lines.extend(["", "## Source Evidence"])
        lines.append(f"- {bundle.source_evidence.summary}")
        lines.append(f"- Recommended action: {bundle.source_evidence.recommended_action}")
        for entry in bundle.source_evidence.entries[:12]:
            target = entry.url or entry.path
            linked = "; ".join(entry.linked_criteria[:3])
            linked_text = f" Criteria: {linked}" if linked else ""
            excerpt = f" Excerpt: {entry.excerpt}" if entry.excerpt else ""
            lines.append(
                f"- `{entry.kind}` `{entry.evidence_label}` {entry.title or target}.{linked_text}{excerpt}"
            )
    if bundle.action_context.generated_at:
        lines.extend(["", "## Action Context"])
        for line in bundle.action_context.compact_prompt.splitlines():
            lines.append(line if line.startswith("-") else f"- {line}")

    if bundle.operator_dispatches.total_count:
        lines.extend(["", "## Operator Dispatches"])
        lines.append(f"- {bundle.operator_dispatches.summary}")
        lines.append(f"- Recommended action: {bundle.operator_dispatches.recommended_action}")
        for entry in bundle.operator_dispatches.entries[:12]:
            target = f" `{entry.ui_target}`" if entry.ui_target else ""
            approval = f" approval#{entry.approval_id}" if entry.approval_id else ""
            lines.append(
                f"- #{entry.event_id} `{entry.status}` `{entry.decision}`{target}{approval}: {entry.message}"
            )
    if bundle.ornith_preflight_actions.total_count:
        lines.extend(["", "## Ornith Preflight Actions"])
        lines.append(f"- {bundle.ornith_preflight_actions.summary}")
        lines.append(f"- Recommended action: {bundle.ornith_preflight_actions.recommended_action}")
        for entry in bundle.ornith_preflight_actions.entries[:12]:
            context = f" context={entry.context_pressure}/{entry.context_tokens}" if entry.context_pressure else ""
            lines.append(
                f"- #{entry.event_id} `{entry.status}` `{entry.item_id}` `{entry.ui_target}`{context}: {entry.message}"
            )
    if bundle.operator_dispatch_restart_smoke.run_id:
        lines.extend(["", "## Operator Dispatch Restart Smoke"])
        lines.append(f"- Status: `{bundle.operator_dispatch_restart_smoke.status}`")
        lines.append(f"- Summary: {bundle.operator_dispatch_restart_smoke.summary}")
        lines.append(f"- Restart simulated: `{bundle.operator_dispatch_restart_smoke.restart_simulated}`")
        lines.append(
            f"- Attached: ledger `{bundle.operator_dispatch_restart_smoke.ledger_attached}` handoff `{bundle.operator_dispatch_restart_smoke.handoff_attached}` replay `{bundle.operator_dispatch_restart_smoke.replay_attached}` context `{bundle.operator_dispatch_restart_smoke.context_attached}`"
        )
        if bundle.operator_dispatch_restart_smoke.compact_context_tokens:
            sections = ", ".join(bundle.operator_dispatch_restart_smoke.compact_context_sections[:10])
            lines.append(f"- Compact context tokens: `{bundle.operator_dispatch_restart_smoke.compact_context_tokens}` sections: {sections}")
        for step in bundle.operator_dispatch_restart_smoke.steps:
            evidence = "; ".join(step.evidence[:3])
            suffix = f" Evidence: {evidence}" if evidence else ""
            lines.append(f"- `{step.status}` {step.id}: {step.summary}{suffix}")
    lines.extend(["", "## Recent Events"])
    if bundle.events:
        for event in bundle.events[-30:]:
            ok = "" if event.ok is None else f" ok={event.ok}"
            lines.append(f"- #{event.id} `{event.kind}`{ok}: {event.message}")
    else:
        lines.append("- None.")
    if bundle.acceptance_evidence:
        lines.extend(["", "## Acceptance Evidence"])
        for item in bundle.acceptance_evidence:
            evidence = "; ".join(item.evidence[-3:])
            suffix = f" Evidence: {evidence}" if evidence else ""
            progress = compact_label_progress(item.required_labels, item.matched_labels)
            label_text = f" `{progress}`" if progress else ""
            lines.append(f"- `{item.status}`{label_text} {item.criterion}.{suffix}")
    if bundle.acceptance_recommendations:
        lines.extend(["", "## Acceptance Recommendations"])
        for item in bundle.acceptance_recommendations[:12]:
            available = "available" if item.available else "unavailable"
            hint = f" Hint: {item.command_hint}" if item.command_hint else ""
            lines.append(f"- `{item.label}` `{item.tool_kind}` `{available}` {item.action}{hint}")
    if bundle.acceptance_recommendation_traces:
        lines.extend(["", "## Acceptance Recommendation Traces"])
        for item in bundle.acceptance_recommendation_traces[-12:]:
            result = f" result={item.result_ok}" if item.result_ok is not None else ""
            lines.append(
                f"- `{item.status}` `{item.source}` `{item.label}` {item.recommended_tool} -> {item.selected_tool}{result}: {item.result_summary or item.action_summary}"
            )
    if bundle.run_health.run_id:
        lines.extend(["", "## Run Health"])
        lines.append(f"- Level: `{bundle.run_health.level}`")
        lines.append(f"- Score: `{bundle.run_health.score}`")
        lines.append(f"- Recommended action: `{bundle.run_health.recommended_action}`")
        for signal in bundle.run_health.signals[:8]:
            evidence = "; ".join(signal.evidence[:3])
            suffix = f" Evidence: {evidence}" if evidence else ""
            lines.append(f"- `{signal.severity}` {signal.summary}{suffix}")
    if bundle.policy_simulation.run_id:
        lines.extend(["", "## Policy Simulation"])
        lines.append(f"- Prediction: `{bundle.policy_simulation.policy_action}` -> `{bundle.policy_simulation.predicted_status}` / `{bundle.policy_simulation.predicted_milestone}`")
        lines.append(f"- Safe to resume: `{bundle.policy_simulation.safe_to_resume}`")
        lines.append(f"- Next action: {bundle.policy_simulation.next_action}")
        if bundle.policy_simulation.recommended_tool:
            lines.append(
                f"- Recommendation: `{bundle.policy_simulation.recommended_label}` via `{bundle.policy_simulation.recommended_tool}`"
            )
        for effect in bundle.policy_simulation.effects[:6]:
            lines.append(f"- {effect}")
    if bundle.run_progress.run_id:
        lines.extend(["", "## Run Progress"])
        lines.append(f"- Status: `{bundle.run_progress.status}`")
        lines.append(f"- Can keep running: `{bundle.run_progress.can_keep_running}`")
        lines.append(f"- Should pause: `{bundle.run_progress.should_pause}`")
        lines.append(f"- Tasks: `{bundle.run_progress.task_completed}/{bundle.run_progress.task_total}` ({bundle.run_progress.task_progress_percent}%)")
        lines.append(f"- Acceptance: `{bundle.run_progress.acceptance_verified}/{bundle.run_progress.acceptance_total}` ({bundle.run_progress.acceptance_coverage_percent}%)")
        lines.append(f"- Summary: {bundle.run_progress.summary}")
        for action in bundle.run_progress.next_actions[:6]:
            lines.append(f"- Next: {action}")
    if bundle.report_integrity.run_id:
        lines.extend(["", "## Report Integrity"])
        lines.append(f"- Status: `{bundle.report_integrity.status}`")
        lines.append(f"- Checks: `{bundle.report_integrity.ok_count}/{bundle.report_integrity.check_count}` ok")
        lines.append(f"- Missing/stale/mismatch: `{bundle.report_integrity.missing_count}/{bundle.report_integrity.stale_count}/{bundle.report_integrity.mismatch_count}`")
        lines.append(f"- Summary: {bundle.report_integrity.summary}")
        for check in bundle.report_integrity.checks:
            if check.status != "ok":
                lines.append(f"- `{check.status}` {check.section}: {check.summary}")
    if bundle.objective_readiness.run_id:
        lines.extend(["", "## Objective Readiness"])
        lines.append(f"- Status: `{bundle.objective_readiness.status}`")
        lines.append(
            f"- Verified/partial/missing/failed: `{bundle.objective_readiness.verified_count}/{bundle.objective_readiness.partial_count}/{bundle.objective_readiness.missing_count}/{bundle.objective_readiness.failed_count}`"
        )
        lines.append(f"- Summary: {bundle.objective_readiness.summary}")
        lines.append(f"- Recommended action: {bundle.objective_readiness.recommended_action}")
        for action in bundle.objective_readiness.next_actions[:5]:
            lines.append(f"- Next: {action}")
        for item in bundle.objective_readiness.items:
            lines.append(f"- `{item.status}` {item.id}: {item.requirement}")
            if item.proof.tool_kind or item.proof.action:
                hint = f" Hint: {item.proof.command_hint}" if item.proof.command_hint else ""
                approval = " approval_required" if item.proof.requires_approval else ""
                strategy = f" `{item.proof.strategy}`" if item.proof.strategy else ""
                lines.append(
                    f"  Proof: `{item.proof.tool_kind}` `{item.proof.evidence_label}`{strategy}{approval}: {item.proof.action}{hint}"
                )
            if item.preferred_proof.tool_kind or item.preferred_proof.action:
                preference_hint = f" Hint: {item.preferred_proof.command_hint}" if item.preferred_proof.command_hint else ""
                lines.append(
                    f"  Prefer: `{item.preferred_proof.tool_kind}` `{item.preferred_proof.strategy}` "
                    f"confidence `{item.preferred_proof.confidence}`: {item.preferred_proof.action}{preference_hint}"
                )
            if item.latest_outcome.id:
                strategy = f" `{item.latest_outcome.strategy}`" if item.latest_outcome.strategy else ""
                lines.append(
                    f"  Outcome: `{item.latest_outcome.outcome}` `{item.latest_outcome.tool}`{strategy}: {item.latest_outcome.summary}"
                )
    if bundle.readiness_completion.run_id:
        lines.extend(["", "## Readiness Completion"])
        lines.append(f"- Status: `{bundle.readiness_completion.status}` claim `{bundle.readiness_completion.can_claim_milestone}` confidence `{bundle.readiness_completion.confidence}`")
        lines.append(f"- Summary: {bundle.readiness_completion.summary}")
        lines.append(
            f"- Objective/progress/completion: `{bundle.readiness_completion.objective_status}` / `{bundle.readiness_completion.run_progress_status}` / `{bundle.readiness_completion.completion_status}`"
        )
        lines.append(
            f"- Verified/required: `{bundle.readiness_completion.verified_count}/{bundle.readiness_completion.required_verified_count}` warnings `{bundle.readiness_completion.warning_count}` blockers `{bundle.readiness_completion.blocking_count}`"
        )
        for check in bundle.readiness_completion.checks:
            lines.append(f"- `{check.status}` {check.id}: {check.summary}")
        for action in bundle.readiness_completion.next_actions[:5]:
            lines.append(f"- Next: {action}")
    if bundle.readiness_rehearsal.run_id:
        lines.extend(["", "## Readiness Rehearsal"])
        lines.append(f"- Status: `{bundle.readiness_rehearsal.status}`")
        lines.append(f"- Scenario: `{bundle.readiness_rehearsal.scenario}`")
        lines.append(f"- Summary: {bundle.readiness_rehearsal.summary}")
        lines.append(f"- Restart simulated: `{bundle.readiness_rehearsal.restart_simulated}`")
        lines.append(
            f"- Events: refused `#{bundle.readiness_rehearsal.refused_event_id}` accepted `#{bundle.readiness_rehearsal.accepted_event_id}` completed `#{bundle.readiness_rehearsal.completed_event_id}`"
        )
        if bundle.readiness_rehearsal.compact_context_tokens:
            sections = ", ".join(bundle.readiness_rehearsal.compact_context_sections[:10])
            lines.append(f"- Compact context tokens: `{bundle.readiness_rehearsal.compact_context_tokens}` sections: {sections}")
        for step in bundle.readiness_rehearsal.steps:
            evidence = "; ".join(step.evidence[:4])
            suffix = f" Evidence: {evidence}" if evidence else ""
            event = f" event=#{step.event_id}" if step.event_id else ""
            lines.append(f"- `{step.status}` {step.id}{event}: {step.summary}{suffix}")
    if bundle.ornith_preflight.generated_at:
        lines.extend(["", "## Ornith Preflight"])
        lines.append(f"- Status: `{bundle.ornith_preflight.status}` mode `{bundle.ornith_preflight.mode}`")
        lines.append(f"- Summary: {bundle.ornith_preflight.summary}")
        lines.append(
            f"- Ready start/resume: `{bundle.ornith_preflight.ready_to_start}/{bundle.ornith_preflight.ready_to_resume}` health `{bundle.ornith_preflight.run_health_level}/{bundle.ornith_preflight.run_health_action}`"
        )
        lines.append(
            f"- Smoke: readiness `{bundle.ornith_preflight.readiness_smoke_status}` dispatch `{bundle.ornith_preflight.dispatch_restart_smoke_status}` approvals `{bundle.ornith_preflight.pending_approval_count}`"
        )
        for item in bundle.ornith_preflight.items:
            if item.status != "pass":
                lines.append(f"- `{item.status}` {item.category}/{item.id}: {item.summary}")
        for action in bundle.ornith_preflight.next_actions[:5]:
            lines.append(f"- Next: {action}")
    if bundle.resume_decisions.run_id:
        lines.extend(["", "## Resume Decisions"])
        lines.append(f"- Decisions: `{bundle.resume_decisions.decision_count}` accepted `{bundle.resume_decisions.accepted_count}` blocked `{bundle.resume_decisions.blocked_count}`")
        lines.append(f"- Current matches last accepted: `{bundle.resume_decisions.current_matches_last_accepted}`")
        lines.append(f"- Comparison: {bundle.resume_decisions.comparison_summary}")
        lines.append(f"- Recommended action: {bundle.resume_decisions.recommended_action}")
        for decision in bundle.resume_decisions.decisions[-6:]:
            outcome = "accepted" if decision.accepted else "blocked"
            lines.append(
                f"- #{decision.id} `{outcome}` `{decision.source}` {decision.policy_action} -> {decision.predicted_status}/{decision.predicted_milestone}: {decision.reason}"
            )
    if bundle.autonomy_decisions.run_id:
        lines.extend(["", "## Autonomy Decisions"])
        lines.append(
            f"- Decisions: `{bundle.autonomy_decisions.decision_count}` continue `{bundle.autonomy_decisions.continue_count}` recover `{bundle.autonomy_decisions.recover_count}` wait `{bundle.autonomy_decisions.wait_count}` complete `{bundle.autonomy_decisions.complete_count}` blocked `{bundle.autonomy_decisions.blocked_count}`"
        )
        lines.append(f"- Current policy: `{bundle.autonomy_decisions.current_policy_action}` safe `{bundle.autonomy_decisions.current_safe_to_resume}`")
        lines.append(f"- Summary: {bundle.autonomy_decisions.summary}")
        lines.append(f"- Recommended action: {bundle.autonomy_decisions.recommended_action}")
        for decision in bundle.autonomy_decisions.decisions[-8:]:
            signals = f" signals={','.join(decision.blocking_signals)}" if decision.blocking_signals else ""
            health = f" health={decision.health_level}/{decision.health_action}/{decision.health_score}" if decision.health_action else ""
            lines.append(
                f"- #{decision.id} `{decision.decision}` `{decision.source}`{health}{signals}: {decision.reason}"
            )
    if bundle.action_readiness.run_id:
        lines.extend(["", "## Action Readiness"])
        lines.append(f"- Status: `{bundle.action_readiness.status}`")
        lines.append(f"- Ready to act: `{bundle.action_readiness.ready_to_act}`")
        lines.append(f"- Recommendation: {bundle.action_readiness.recommended_action}")
        if bundle.action_readiness.suggested_tool:
            lines.append(f"- Suggested tool: `{bundle.action_readiness.suggested_tool}` `{bundle.action_readiness.suggested_label}`")
        for issue in bundle.action_readiness.issues[:8]:
            evidence = "; ".join(issue.evidence[:3])
            suffix = f" Evidence: {evidence}" if evidence else ""
            lines.append(f"- `{issue.severity}` {issue.summary}{suffix}")
    if bundle.action_readiness_decisions.run_id:
        lines.extend(["", "## Action Readiness Decisions"])
        lines.append(f"- Decisions: `{bundle.action_readiness_decisions.decision_count}` selected `{bundle.action_readiness_decisions.selected_count}` satisfied `{bundle.action_readiness_decisions.satisfied_count}` failed `{bundle.action_readiness_decisions.failed_count}`")
        lines.append(f"- Summary: {bundle.action_readiness_decisions.summary}")
        lines.append(f"- Recommended action: {bundle.action_readiness_decisions.recommended_action}")
        for decision in bundle.action_readiness_decisions.decisions[-8:]:
            tool = f" {decision.selected_tool}" if decision.selected_tool else ""
            label = f" `{decision.label or decision.suggested_label}`" if decision.label or decision.suggested_label else ""
            result = f" result={decision.result_ok}" if decision.result_ok is not None else ""
            lines.append(
                f"- #{decision.id} `{decision.status}` `{decision.source}`{tool}{label}{result}: {decision.summary}"
            )
    if bundle.completion_audit.run_id:
        lines.extend(["", "## Completion Audit"])
        lines.append(f"- Status: `{bundle.completion_audit.status}`")
        lines.append(f"- Can finish: `{bundle.completion_audit.can_finish}`")
        for issue in bundle.completion_audit.issues[:10]:
            evidence = "; ".join(issue.evidence[:3])
            suffix = f" Evidence: {evidence}" if evidence else ""
            lines.append(f"- `{issue.severity}` {issue.summary}{suffix}")
    lines.extend(["", "## Tasks"])
    if bundle.task_graph:
        for task in bundle.task_graph[:20]:
            lines.append(f"- `{task.status}` `{task.kind}` {task.title}")
    else:
        lines.append("- None.")
    if bundle.model_interactions:
        lines.extend(["", "## Model Interactions"])
        for interaction in bundle.model_interactions[-12:]:
            flags = []
            if interaction.repaired:
                flags.append("repaired")
            if interaction.fallback_used:
                flags.append("fallback")
            flag_text = f" ({', '.join(flags)})" if flags else ""
            lines.append(
                f"- `{interaction.kind}` ok={interaction.ok} attempts={interaction.attempts}{flag_text}: {interaction.summary}"
            )
    if bundle.run_lease.status != "none":
        lines.extend(["", "## Run Lease"])
        lines.append(f"- Status: `{bundle.run_lease.status}`")
        lines.append(f"- Owner: `{bundle.run_lease.owner_id}`")
        lines.append(f"- Heartbeat: {bundle.run_lease.heartbeat_at or 'none'}")
        lines.append(f"- Expires: {bundle.run_lease.expires_at or 'none'}")
    if bundle.handoff.unresolved_blockers:
        lines.extend(["", "## Blockers"])
        for blocker in bundle.handoff.unresolved_blockers[:12]:
            lines.append(f"- {blocker}")
    if bundle.workspace_diff_summary:
        lines.extend(["", "## Workspace Diff", "", f"- {bundle.workspace_diff_summary}"])
    if bundle.workspace_promotions:
        lines.extend(["", "## Workspace Promotions"])
        for promotion in bundle.workspace_promotions:
            lines.append(f"- `{promotion.status}` {promotion.summary} ({', '.join(promotion.files[:8])})")
    if bundle.patch_applications:
        lines.extend(["", "## Patch Applications"])
        for patch in bundle.patch_applications:
            lines.append(f"- `{patch.status}` {patch.summary} ({', '.join(patch.files[:8])})")
    if bundle.failure_records:
        lines.extend(["", "## Failures"])
        for failure in bundle.failure_records:
            lines.append(f"- `{failure.kind}` `{failure.tool}` x{failure.count}: {failure.recovery_hint}")
    if bundle.recovery_plan.status == "active":
        lines.extend(["", "## Active Recovery"])
        lines.append(f"- Trigger: `{bundle.recovery_plan.trigger}`")
        lines.append(f"- Tool: `{bundle.recovery_plan.tool}`")
        lines.append(f"- Summary: {bundle.recovery_plan.summary}")
        for step in bundle.recovery_plan.steps[:8]:
            lines.append(f"  - {step}")
    if bundle.recovery_decisions.run_id:
        lines.extend(["", "## Recovery Decisions"])
        lines.append(f"- Decisions: `{bundle.recovery_decisions.decision_count}` readiness `{bundle.recovery_decisions.readiness_recovery_count}` resolved `{bundle.recovery_decisions.resolved_count}` unresolved `{bundle.recovery_decisions.unresolved_count}`")
        lines.append(f"- Summary: {bundle.recovery_decisions.summary}")
        lines.append(f"- Recommended action: {bundle.recovery_decisions.recommended_action}")
        for decision in bundle.recovery_decisions.decisions[-8:]:
            label = f" `{decision.proof_label}`" if decision.proof_label else ""
            evidence = f" evidence={decision.evidence_status}" if decision.evidence_status else ""
            lines.append(
                f"- `{decision.status}` `{decision.trigger}` `{decision.tool}`{label}{evidence}: {decision.selected_strategy or decision.summary}"
            )
    if bundle.verification_outcomes.run_id:
        lines.extend(["", "## Verification Outcomes"])
        lines.append(f"- Outcomes: `{bundle.verification_outcomes.outcome_count}` verified `{bundle.verification_outcomes.verified_count}` failed `{bundle.verification_outcomes.failed_count}` recovery `{bundle.verification_outcomes.recovery_outcome_count}`")
        lines.append(f"- Summary: {bundle.verification_outcomes.summary}")
        lines.append(f"- Recommended action: {bundle.verification_outcomes.recommended_action}")
        for outcome in bundle.verification_outcomes.outcomes[-8:]:
            recovery = f" recovery={outcome.recovery_id}" if outcome.recovery_id else ""
            label = f" `{outcome.proof_label}`" if outcome.proof_label else ""
            labels = f" labels={','.join(outcome.labels_satisfied)}" if outcome.labels_satisfied else ""
            lines.append(
                f"- `{outcome.outcome}` `{outcome.tool}`{label}{recovery}{labels}: {outcome.summary}"
            )
    if bundle.post_action_retries.decision_count:
        lines.extend(["", "## Post-Action Retries"])
        lines.append(f"- Decisions: `{bundle.post_action_retries.decision_count}` pending `{bundle.post_action_retries.pending_count}` resolved `{bundle.post_action_retries.resolved_count}` failed `{bundle.post_action_retries.failed_count}`")
        lines.append(f"- Summary: {bundle.post_action_retries.summary}")
        lines.append(f"- Recommended action: {bundle.post_action_retries.recommended_action}")
        for decision in bundle.post_action_retries.decisions[-8:]:
            lines.append(
                f"- `{decision.status}` `{decision.trigger_tool}` -> `{decision.selected_tool}`: {decision.selected_action}"
            )
    if bundle.recovery_history:
        lines.extend(["", "## Recovery History"])
        for plan in bundle.recovery_history[-10:]:
            lines.append(f"- `{plan.status}` `{plan.tool}` {plan.summary}")
    if bundle.model_profile_adaptation_reviews:
        lines.extend(["", "## Ornith Profile Adaptation Reviews"])
        for review in bundle.model_profile_adaptation_reviews[:10]:
            titles = "; ".join(review.action_titles[:5])
            title_text = f" Actions: {titles}." if titles else ""
            note_text = f" Note: {review.reviewer_note}" if review.reviewer_note else ""
            lines.append(
                f"- `{review.decision}` `{review.profile_id}` {review.proposal_summary}.{title_text}{note_text}"
            )
    lines.append("")
    return "\n".join(lines)


def single_line(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


