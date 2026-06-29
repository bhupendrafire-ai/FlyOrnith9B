from __future__ import annotations

from typing import Any

from .acceptance import compact_label_progress
from .action_context import build_action_context_pack
from .action_readiness import build_action_readiness
from .action_readiness_decisions import build_action_readiness_decision_report
from .approval_reviews import approval_review_event_index, approval_review_label
from .autonomy_decisions import build_autonomy_decision_report
from .checkpoint_quality_resume import build_checkpoint_quality_resume_report
from .completion_audit import build_completion_audit
from .desktop_effect_proof import build_desktop_effect_proof_preview, build_desktop_effect_proof_repairs
from .git_checkpoints import build_git_checkpoint_report
from .goal_evolution import build_goal_evolution_report
from .objective_readiness import build_objective_readiness
from .operator_dispatches import build_operator_dispatch_ledger
from .ornith_preflight_actions import build_ornith_preflight_action_ledger
from .ornith_preflight_warnings import build_ornith_preflight_warning_report
from .policy_simulation import build_policy_simulation
from .post_action_retry import build_post_action_retry_report
from .promotion_audit import build_promotion_audit
from .promotion_repair import build_promotion_repair_report
from .promotion_verification import build_promotion_verification_report
from .persistence import utc_now
from .profile_adaptation import compact_adaptation_review
from .readiness_completion import build_readiness_completion
from .readiness_source_refs import build_readiness_source_ref_preview
from .recovery_decisions import build_recovery_decision_report
from .report_integrity import build_report_integrity, build_report_integrity_refreshes
from .resume_decisions import build_resume_decision_report
from .resume_handoff_diff import build_resume_handoff_diff
from .resume_quality import build_resume_prompt_quality
from .run_health import build_run_health
from .run_progress import build_run_progress
from .self_scaffold import build_self_scaffold_report, build_self_scaffold_review_report, build_self_scaffold_rollback_intent_report
from .source_evidence import build_source_evidence_preview
from .tools import TOOL_NAMES
from .verification_outcomes import build_verification_outcome_report
from .schemas import (
    ApprovalReviewSummary,
    ModelProfileAdaptationReview,
    OrnithLaunchChecklistReport,
    ReadinessProofHistoryRecord,
    ReadinessProofHistoryReport,
    ReadinessProofSourceRef,
    ReplayApproval,
    ReplayBundle,
    ReplayEvent,
    RunRecord,
)


_READINESS_PROOF_STEP_TYPES = {
    "self_scaffold_review": "self_scaffold_review",
    "post_review_handoff_alignment": "post_review_handoff",
    "accepted_claim": "readiness_claim",
    "refused_claim": "readiness_claim",
    "restart_resume_preflight": "readiness_rehearsal",
    "compact_context": "readiness_rehearsal",
}

_SOURCE_REF_PROOF_TYPES = {
    "post_review_handoff",
    "resume_prompt_preservation",
    "readiness_claim",
    "readiness_rehearsal",
}


def _item_value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _compact_line(value: Any, limit: int) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."


def _readiness_source_refs(source_evidence: Any | None, *, limit: int = 6) -> list[ReadinessProofSourceRef]:
    if source_evidence is None:
        return []
    entries = list(_item_value(source_evidence, "entries", []) or [])
    refs: list[ReadinessProofSourceRef] = []
    seen: set[str] = set()
    bounded_limit = max(1, min(limit, 12))
    for entry in entries:
        kind = str(_item_value(entry, "kind", ""))
        if kind not in {"web_source", "browser_snapshot", "desktop_snapshot"}:
            continue
        entry_id = str(_item_value(entry, "id", ""))
        target = str(_item_value(entry, "url", "") or _item_value(entry, "path", ""))
        key = f"{kind}:{entry_id or target}"
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            ReadinessProofSourceRef(
                id=entry_id,
                kind=kind,  # type: ignore[arg-type]
                evidence_label=str(_item_value(entry, "evidence_label", "")),
                title=_compact_line(_item_value(entry, "title", ""), 140),
                target=_compact_line(target, 220),
                linked_criteria=[str(item) for item in (_item_value(entry, "linked_criteria", []) or [])[:4]],
                citation=_compact_line(_item_value(entry, "citation", ""), 120),
            )
        )
        if len(refs) >= bounded_limit:
            break
    return refs


def _source_refs_for_proof(proof_type: str, source_refs: list[ReadinessProofSourceRef]) -> list[ReadinessProofSourceRef]:
    if proof_type in _SOURCE_REF_PROOF_TYPES:
        return source_refs[:4]
    return []


def build_readiness_proof_history(
    run: RunRecord,
    events: list[dict[str, Any]],
    readiness_rehearsal: Any | None = None,
    self_scaffold: Any | None = None,
    source_evidence: Any | None = None,
    *,
    limit: int = 20,
) -> ReadinessProofHistoryReport:
    rehearsal = readiness_rehearsal or run.state.readiness_rehearsal
    event_by_id = {int(event.get("id") or 0): event for event in events}
    source_report = source_evidence if source_evidence is not None else build_source_evidence_preview(run, limit=min(max(limit, 1), 20))
    source_refs = _readiness_source_refs(source_report, limit=6)
    entries: list[ReadinessProofHistoryRecord] = []
    seen_event_ids: set[int] = set()

    def add_entry(entry: ReadinessProofHistoryRecord) -> None:
        if not entry.source_refs:
            entry.source_refs = _source_refs_for_proof(entry.proof_type, source_refs)
        if entry.event_id:
            seen_event_ids.add(entry.event_id)
        entries.append(entry)

    def step_status(status: str) -> str:
        if status == "passed":
            return "pass"
        if status == "failed":
            return "block"
        if status in {"pending", "skipped"}:
            return "warn"
        return "info"

    for step in getattr(rehearsal, "steps", []) or []:
        proof_type = _READINESS_PROOF_STEP_TYPES.get(step.id)
        if proof_type is None:
            continue
        event = event_by_id.get(int(step.event_id or 0), {})
        evidence = [str(item) for item in (step.evidence or [])[:6]]
        if step.id == "post_review_handoff_alignment":
            evidence.append(
                "post_review_flags="
                f"handoff_goal:{getattr(rehearsal, 'post_review_handoff_goal_preserved', False)},"
                f"handoff_next:{getattr(rehearsal, 'post_review_handoff_next_action_preserved', False)},"
                f"resume_goal:{getattr(rehearsal, 'post_review_resume_prompt_goal_preserved', False)},"
                f"resume_next:{getattr(rehearsal, 'post_review_resume_prompt_next_action_preserved', False)}"
            )
        add_entry(
            ReadinessProofHistoryRecord(
                event_id=int(step.event_id or 0),
                timestamp=str(event.get("timestamp") or getattr(rehearsal, "generated_at", "")),
                source="rehearsal_step",
                proof_type=proof_type,
                status=step_status(str(step.status)),
                step_id=step.id,
                summary=step.summary,
                evidence=evidence,
                run_status=step.run_status,
                milestone=step.milestone,
            )
        )

    for event in events:
        event_id = int(event.get("id") or 0)
        if event_id in seen_event_ids:
            continue
        kind = str(event.get("kind") or "")
        data = event.get("data") or {}
        if kind == "operator_action_reviewed" and data.get("self_scaffold_review"):
            review = data.get("self_scaffold_review") or {}
            reviewed_count = int(review.get("reviewed_change_count") or 0)
            add_entry(
                ReadinessProofHistoryRecord(
                    event_id=event_id,
                    timestamp=str(event.get("timestamp") or ""),
                    source="operator_event",
                    proof_type="self_scaffold_review",
                    status="pass" if reviewed_count > 0 else "warn",
                    summary=str(event.get("message") or "Operator reviewed self-scaffold change."),
                    evidence=[
                        f"reviewed_changes={reviewed_count}",
                        f"reviewed_ids={','.join(str(item) for item in (review.get('reviewed_change_ids') or [])[:6])}",
                    ],
                )
            )
        elif kind in {"readiness_claim", "readiness_claim_blocked"}:
            add_entry(
                ReadinessProofHistoryRecord(
                    event_id=event_id,
                    timestamp=str(event.get("timestamp") or ""),
                    source="claim_event",
                    proof_type="readiness_claim",
                    status="pass" if kind == "readiness_claim" else "block",
                    summary=str(event.get("message") or kind),
                    evidence=[f"kind={kind}"],
                )
            )

    rehearsal_run_id = str(getattr(rehearsal, "run_id", "") or "")
    if rehearsal_run_id:
        has_self_scaffold_review = any(entry.proof_type == "self_scaffold_review" and entry.status == "pass" for entry in entries)
        has_post_review_handoff = any(entry.proof_type == "post_review_handoff" and entry.status == "pass" for entry in entries)
        has_readiness_claim = any(entry.proof_type == "readiness_claim" and entry.status == "pass" for entry in entries)
        post_review_handoff_preserved = bool(
            getattr(rehearsal, "post_review_handoff_goal_preserved", False)
            and getattr(rehearsal, "post_review_handoff_next_action_preserved", False)
            and getattr(rehearsal, "post_review_resume_prompt_goal_preserved", False)
            and getattr(rehearsal, "post_review_resume_prompt_next_action_preserved", False)
        )
        if (
            not has_self_scaffold_review
            and getattr(rehearsal, "self_scaffold_reviewed", False)
            and int(getattr(rehearsal, "self_scaffold_reviewed_change_count", 0) or 0) > 0
        ):
            event_id = int(getattr(rehearsal, "self_scaffold_review_event_id", 0) or 0)
            event = event_by_id.get(event_id, {})
            add_entry(
                ReadinessProofHistoryRecord(
                    event_id=event_id,
                    timestamp=str(event.get("timestamp") or getattr(rehearsal, "generated_at", "")),
                    source="report",
                    proof_type="self_scaffold_review",
                    status="pass",
                    summary="Readiness report proves self-scaffold review was accepted.",
                    evidence=[
                        f"self_scaffold_reviewed={getattr(rehearsal, 'self_scaffold_reviewed', False)}",
                        f"review_event={event_id}",
                        f"reviewed_changes={int(getattr(rehearsal, 'self_scaffold_reviewed_change_count', 0) or 0)}",
                    ],
                )
            )
        if post_review_handoff_preserved and not has_post_review_handoff:
            add_entry(
                ReadinessProofHistoryRecord(
                    timestamp=str(getattr(rehearsal, "generated_at", "")),
                    source="report",
                    proof_type="post_review_handoff",
                    status="pass",
                    summary="Readiness report proves post-review handoff and resume prompt preservation.",
                    evidence=[
                        f"handoff_goal={getattr(rehearsal, 'post_review_handoff_goal_preserved', False)}",
                        f"handoff_next={getattr(rehearsal, 'post_review_handoff_next_action_preserved', False)}",
                        f"resume_prompt_goal={getattr(rehearsal, 'post_review_resume_prompt_goal_preserved', False)}",
                        f"resume_prompt_next={getattr(rehearsal, 'post_review_resume_prompt_next_action_preserved', False)}",
                    ],
                )
            )
        accepted_event_id = int(getattr(rehearsal, "accepted_event_id", 0) or 0)
        if accepted_event_id and not has_readiness_claim:
            event = event_by_id.get(accepted_event_id, {})
            add_entry(
                ReadinessProofHistoryRecord(
                    event_id=accepted_event_id,
                    timestamp=str(event.get("timestamp") or getattr(rehearsal, "generated_at", "")),
                    source="report",
                    proof_type="readiness_claim",
                    status="pass",
                    summary="Readiness report records an accepted readiness claim.",
                    evidence=[f"accepted_event={accepted_event_id}"],
                )
            )
    if getattr(rehearsal, "run_id", "") and not entries:
        status = getattr(rehearsal, "status", "not_run")
        add_entry(
            ReadinessProofHistoryRecord(
                timestamp=str(getattr(rehearsal, "generated_at", "")),
                source="report",
                proof_type="readiness_rehearsal",
                status="pass" if status == "passed" else "block" if status == "failed" else "warn",
                summary=str(getattr(rehearsal, "summary", "Readiness rehearsal report recorded.")),
                evidence=[
                    f"self_scaffold_reviewed={getattr(rehearsal, 'self_scaffold_reviewed', False)}",
                    f"post_review_handoff_goal={getattr(rehearsal, 'post_review_handoff_goal_preserved', False)}",
                    f"post_review_resume_next={getattr(rehearsal, 'post_review_resume_prompt_next_action_preserved', False)}",
                ],
            )
        )

    entries = entries[-limit:]
    self_scaffold_review_count = sum(1 for entry in entries if entry.proof_type == "self_scaffold_review" and entry.status == "pass")
    post_review_handoff_count = sum(1 for entry in entries if entry.proof_type == "post_review_handoff" and entry.status == "pass")
    resume_prompt_preservation_count = sum(
        1
        for entry in entries
        if entry.proof_type == "post_review_handoff"
        and entry.status == "pass"
        and any("resume_prompt" in item or "resume_next" in item for item in entry.evidence)
    )
    readiness_claim_count = sum(1 for entry in entries if entry.proof_type == "readiness_claim" and entry.status == "pass")
    blocking_count = sum(1 for entry in entries if entry.status == "block")
    scaffold_report = self_scaffold or run.state.self_scaffold
    reviewed_from_scaffold = int(getattr(scaffold_report, "reviewed_change_count", 0) or 0)
    rehearsal_complete = bool(
        getattr(rehearsal, "self_scaffold_reviewed", False)
        and getattr(rehearsal, "self_scaffold_review_event_id", 0)
        and getattr(rehearsal, "post_review_handoff_goal_preserved", False)
        and getattr(rehearsal, "post_review_handoff_next_action_preserved", False)
        and getattr(rehearsal, "post_review_resume_prompt_goal_preserved", False)
        and getattr(rehearsal, "post_review_resume_prompt_next_action_preserved", False)
    )
    if not entries:
        status = "empty"
        summary = "No readiness proof history recorded."
        recommended_action = "Run the readiness rehearsal before trusting long-run readiness proof."
    elif blocking_count:
        status = "needs_attention"
        summary = "Readiness proof history has blocking proof events."
        recommended_action = "Inspect blocked proof entries and rerun the readiness rehearsal after repair."
    elif rehearsal_complete and self_scaffold_review_count and post_review_handoff_count:
        status = "complete"
        summary = "Readiness proof history confirms self-scaffold review and post-review handoff preservation."
        recommended_action = "Use this compact proof history as handoff/replay evidence instead of raw logs."
    else:
        status = "partial"
        summary = "Readiness proof history is present but missing a required proof family."
        recommended_action = "Review self-scaffold and post-review handoff proof before claiming long-run readiness."
    if reviewed_from_scaffold and self_scaffold_review_count == 0:
        summary += f" Self-scaffold report has {reviewed_from_scaffold} reviewed change(s) without a matching proof-history event."
    linked_refs: dict[str, ReadinessProofSourceRef] = {}
    for entry in entries:
        for ref in entry.source_refs:
            key = f"{ref.kind}:{ref.id or ref.target}"
            if key not in linked_refs:
                linked_refs[key] = ref
    source_evidence_labels = sorted({ref.evidence_label for ref in linked_refs.values() if ref.evidence_label})
    if linked_refs:
        preview = ", ".join(
            f"{ref.evidence_label}:{ref.kind}:{ref.id or ref.title or ref.target}"
            for ref in list(linked_refs.values())[:4]
        )
        source_evidence_summary = f"Readiness proof history links {len(linked_refs)} compact source evidence artifact(s): {preview}."
    else:
        source_evidence_summary = "No compact source evidence refs linked to readiness proof history."
    latest_event_id = max((entry.event_id for entry in entries), default=0)
    latest_summary = entries[-1].summary if entries else ""
    return ReadinessProofHistoryReport(
        run_id=run.id,
        generated_at=utc_now(),
        status=status,
        total_count=len(entries),
        self_scaffold_review_count=self_scaffold_review_count,
        post_review_handoff_count=post_review_handoff_count,
        resume_prompt_preservation_count=resume_prompt_preservation_count,
        readiness_claim_count=readiness_claim_count,
        blocking_count=blocking_count,
        source_evidence_ref_count=len(linked_refs),
        source_evidence_labels=source_evidence_labels,
        source_evidence_summary=source_evidence_summary,
        latest_event_id=latest_event_id,
        latest_summary=latest_summary,
        summary=summary,
        recommended_action=recommended_action,
        entries=entries,
    )

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
    approval_review_index = approval_review_event_index(events)
    compact_approvals = [
        compact_approval(approval, approval_review_index.get(int(approval.get("id") or 0), {}))
        for approval in approvals
    ]
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
    resume_prompt_quality = build_resume_prompt_quality(health_run)
    health_run.state.resume_prompt_quality = resume_prompt_quality
    resume_handoff_diff = build_resume_handoff_diff(
        health_run,
        events,
        current_policy=policy_simulation,
        current_quality=resume_prompt_quality,
    )
    health_run.state.resume_handoff_diff = resume_handoff_diff
    autonomy_decisions = build_autonomy_decision_report(health_run, events, policy_simulation)
    health_run.state.autonomy_decisions = autonomy_decisions
    run_progress = build_run_progress(health_run, approvals, completion_audit, policy_simulation)
    readiness_run = health_run.model_copy(deep=True)
    readiness_run.state.run_health = run_health
    action_readiness = build_action_readiness(readiness_run, resume_decisions)
    recovery_decisions = build_recovery_decision_report(run, action_readiness_decisions)
    verification_outcomes = build_verification_outcome_report(run, events, recovery_decisions)
    health_run.state.verification_outcomes = verification_outcomes
    operator_dispatches = build_operator_dispatch_ledger(events, run_id=run.id, limit=20)
    health_run.state.operator_dispatches = operator_dispatches
    promotion_audit = build_promotion_audit(
        health_run,
        approvals=approvals,
        verification_outcomes=verification_outcomes,
        resume_handoff_diff=resume_handoff_diff,
    )
    health_run.state.promotion_audit = promotion_audit
    promotion_verification = _build_replay_promotion_verification(health_run, events)
    health_run.state.promotion_verification = promotion_verification
    promotion_repair = build_promotion_repair_report(health_run)
    health_run.state.promotion_repair = promotion_repair
    goal_evolution = build_goal_evolution_report(run)
    git_checkpoint = build_git_checkpoint_report(run)
    post_action_retries = build_post_action_retry_report(run)
    report_integrity_refreshes = build_report_integrity_refreshes(events, limit=8)
    checkpoint_quality = run.state.checkpoint_quality
    if not checkpoint_quality.run_id:
        checkpoint_quality = run.state.handoff_summary.checkpoint_quality
    checkpoint_quality_resumes = build_checkpoint_quality_resume_report(
        run,
        events,
        checkpoint_quality=checkpoint_quality,
        limit=8,
    )
    ornith_preflight_actions = build_ornith_preflight_action_ledger(events, run_id=run.id, limit=20)
    source_evidence = build_source_evidence_preview(run, limit=20)
    desktop_effect_proof = build_desktop_effect_proof_preview(run, limit=8)
    desktop_effect_proof_repairs = build_desktop_effect_proof_repairs(run, events, limit=8)
    health_run.state.desktop_effect_proof = desktop_effect_proof
    health_run.state.desktop_effect_proof_repairs = desktop_effect_proof_repairs
    action_context_run = run.model_copy(deep=True)
    action_context_run.state.source_evidence = source_evidence
    action_context_run.state.desktop_effect_proof = desktop_effect_proof
    action_context_run.state.desktop_effect_proof_repairs = desktop_effect_proof_repairs
    action_context_run.state.run_health = run_health
    action_context_run.state.action_readiness = action_readiness
    action_context_run.state.action_readiness_decisions = action_readiness_decisions
    action_context_run.state.recovery_decisions = recovery_decisions
    action_context_run.state.verification_outcomes = verification_outcomes
    action_context_run.state.promotion_audit = promotion_audit
    action_context_run.state.promotion_verification = promotion_verification
    action_context_run.state.goal_evolution = goal_evolution
    action_context_run.state.promotion_repair = promotion_repair
    action_context = build_action_context_pack(action_context_run)
    action_context_run.state.action_context = action_context
    self_scaffold = build_self_scaffold_report(action_context_run, events, limit=12)
    self_scaffold_reviews = build_self_scaffold_review_report(action_context_run, events, limit=8)
    self_scaffold_rollback_intents = build_self_scaffold_rollback_intent_report(
        action_context_run,
        events,
        self_scaffold=self_scaffold,
        reviews=self_scaffold_reviews,
        limit=8,
    )
    readiness_proof_history = build_readiness_proof_history(
        action_context_run,
        events,
        run.state.readiness_rehearsal,
        self_scaffold,
        source_evidence,
        limit=20,
    )
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
    ornith_preflight_warnings = build_ornith_preflight_warning_report(
        run.id,
        events,
        ornith_preflight,
        limit=12,
    )
    handoff = run.state.handoff_summary.model_copy(
        update={
            "model_profile_adaptation_reviews": compact_reviews[:5],
            "approvals": compact_handoff_approval_labels(compact_approvals),
            "approval_reviews": compact_handoff_approval_reviews(compact_approvals),
            "completion_audit": completion_audit,
            "acceptance_recommendations": run.state.acceptance_recommendations,
            "acceptance_recommendation_traces": run.state.acceptance_recommendation_traces[-20:],
            "run_health": run_health,
            "policy_simulation": policy_simulation,
            "resume_decisions": resume_decisions,
            "resume_prompt_quality": resume_prompt_quality,
            "resume_handoff_diff": resume_handoff_diff,
            "promotion_audit": promotion_audit,
            "promotion_verification": promotion_verification,
            "promotion_repair": promotion_repair,
            "run_progress": run_progress,
            "action_readiness": action_readiness,
            "action_readiness_decisions": action_readiness_decisions,
            "autonomy_decisions": autonomy_decisions,
            "recovery_decisions": recovery_decisions,
            "verification_outcomes": verification_outcomes,
            "goal_evolution": goal_evolution,
            "git_checkpoint": git_checkpoint,
            "post_action_retries": post_action_retries,
            "operator_dispatches": operator_dispatches,
            "operator_dispatch_restart_smoke": run.state.operator_dispatch_restart_smoke,
            "ornith_preflight_actions": ornith_preflight_actions,
            "ornith_preflight_warnings": ornith_preflight_warnings,
            "readiness_proof_history": readiness_proof_history,
            "report_integrity_refreshes": report_integrity_refreshes,
            "checkpoint_quality": checkpoint_quality,
            "checkpoint_quality_resumes": checkpoint_quality_resumes,
            "source_evidence": source_evidence,
            "desktop_effect_proof": desktop_effect_proof,
            "desktop_effect_proof_repairs": desktop_effect_proof_repairs,
            "failure_records": run.state.failure_records[-20:],
            "action_context": action_context,
            "self_scaffold": self_scaffold,
            "self_scaffold_reviews": self_scaffold_reviews,
            "self_scaffold_rollback_intents": self_scaffold_rollback_intents,
            "context_snapshot": run.state.context_snapshot,
            "ornith_preflight": ornith_preflight,
            "objective_readiness_proof_outcomes": run.state.objective_readiness_proof_outcomes[-20:],
            "readiness_rehearsal": run.state.readiness_rehearsal,
        }
    )
    report_integrity = build_report_integrity(health_run, events, handoff=handoff, approvals=approvals)
    handoff.report_integrity = report_integrity
    handoff.report_integrity_refreshes = report_integrity_refreshes
    health_run.state.report_integrity = report_integrity
    health_run.state.report_integrity_refreshes = report_integrity_refreshes
    objective_readiness = build_objective_readiness(health_run, tool_names=set(TOOL_NAMES))
    handoff.objective_readiness = objective_readiness
    readiness_completion = build_readiness_completion(
        health_run,
        objective_readiness,
        run_progress,
        completion_audit,
        ornith_preflight_warnings=ornith_preflight_warnings,
        self_scaffold=self_scaffold,
        readiness_proof_history=readiness_proof_history,
    )
    handoff.readiness_completion = readiness_completion
    readiness_source_ref_preview = build_readiness_source_ref_preview(
        health_run.model_copy(update={"state": health_run.state}),
        source_evidence,
        readiness_proof_history,
        readiness_completion,
        limit=20,
    )
    health_run.state.readiness_source_ref_preview = readiness_source_ref_preview
    handoff.readiness_source_ref_preview = readiness_source_ref_preview
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
        git_checkpoint=git_checkpoint,
        milestone=run.state.milestone,
        next_action=run.state.next_step,
        context_pressure=run.state.context_budget.pressure,
        context_snapshot=run.state.context_snapshot,
        resume_prompt_quality=resume_prompt_quality,
        resume_handoff_diff=resume_handoff_diff,
        promotion_audit=promotion_audit,
        promotion_verification=promotion_verification,
        promotion_repair=promotion_repair,
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
        report_integrity_refreshes=report_integrity_refreshes,
        checkpoint_quality=checkpoint_quality,
        checkpoint_quality_resumes=checkpoint_quality_resumes,
        objective_readiness=objective_readiness,
        objective_readiness_proof_outcomes=run.state.objective_readiness_proof_outcomes[-20:],
        readiness_completion=readiness_completion,
        readiness_source_ref_preview=readiness_source_ref_preview,
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
        ornith_preflight_warnings=ornith_preflight_warnings,
        readiness_proof_history=readiness_proof_history,
        source_evidence=source_evidence,
        desktop_effect_proof=desktop_effect_proof,
        desktop_effect_proof_repairs=desktop_effect_proof_repairs,
        action_context=action_context,
        self_scaffold=self_scaffold,
        self_scaffold_reviews=self_scaffold_reviews,
        self_scaffold_rollback_intents=self_scaffold_rollback_intents,
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


def _build_replay_promotion_verification(run: RunRecord, events: list[dict[str, Any]]):
    preferred = run.state.repo_map.test_commands[0] if run.state.repo_map.test_commands else "python -m compileall ."
    initial_alternate = _promotion_verification_alternate_command(run, preferred)
    probe = build_promotion_verification_report(
        run,
        events,
        preferred_command=preferred,
        alternate_command=initial_alternate,
    )
    alternate = _promotion_verification_alternate_command(run, probe.latest_failed_command or preferred)
    return build_promotion_verification_report(
        run,
        events,
        preferred_command=preferred,
        alternate_command=alternate,
    )


def _promotion_verification_alternate_command(run: RunRecord, failed_command: str) -> str:
    normalized = failed_command.lower().strip()
    scripts = run.state.repo_map.package_scripts
    if scripts:
        for script_name in ("build", "lint", "typecheck", "test"):
            command = f"npm run {script_name}"
            if script_name in scripts and command.lower() != normalized:
                return command
    if "python -m compileall" not in normalized:
        return "python -m compileall ."
    for path in [*run.state.files_touched, *(item.path for item in run.state.workspace_diff.files), *run.state.repo_map.key_files]:
        if str(path).endswith(".py"):
            normalized_path = str(path).replace("/", "\\")
            return f'python -m py_compile "{normalized_path}"'
    return failed_command or "python -m compileall ."


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




def compact_approval(approval: dict[str, Any], review_meta: dict[str, Any] | None = None) -> ReplayApproval:
    payload = approval.get("payload") if isinstance(approval.get("payload"), dict) else {}
    preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    files_raw = preview.get("files") if isinstance(preview, dict) else []
    files: list[str] = []
    if isinstance(files_raw, list):
        for item in files_raw[:12]:
            if isinstance(item, dict):
                status = str(item.get("status") or "change")
                path = str(item.get("path") or "unknown")
                files.append(f"{status}: {path}")
    if not files:
        fallback_files = payload.get("files") if isinstance(payload.get("files"), list) else args.get("files")
        if isinstance(fallback_files, list):
            for item in fallback_files[:12]:
                path = str(item or "").strip()
                if path:
                    files.append(f"patch: {path}")
    if not files and approval.get("action_kind") == "patch_apply" and args.get("patch_id"):
        files.append(f"patch: {args.get('patch_id')}")

    preview_summary = ""
    if isinstance(preview, dict):
        preview_summary = single_line(str(preview.get("summary") or ""), 600)
    if not preview_summary:
        preview_summary = single_line(str(payload.get("summary") or ""), 600)
    if not preview_summary and approval.get("action_kind") == "patch_apply" and args.get("diff"):
        preview_summary = "Patch diff preview available for approval."
    review_meta = review_meta or {}
    review_count = int(review_meta.get("review_count") or 0)
    return ReplayApproval(
        id=int(approval.get("id") or 0),
        status=str(approval.get("status") or ""),
        action_kind=str(approval.get("action_kind") or ""),
        reason=single_line(str(approval.get("reason") or ""), 600),
        created_at=str(approval.get("created_at") or ""),
        resolved_at=approval.get("resolved_at"),
        reviewed=review_count > 0,
        review_count=review_count,
        latest_reviewed_at=str(review_meta.get("latest_reviewed_at") or ""),
        latest_review_event_id=int(review_meta.get("latest_review_event_id") or 0),
        preview_summary=preview_summary,
        preview_files=files,
    )

def compact_handoff_approval_labels(approvals: list[ReplayApproval]) -> list[str]:
    return [
        approval_review_label(
            approval.action_kind,
            approval.status,
            review_count=approval.review_count,
            latest_review_event_id=approval.latest_review_event_id,
        )
        for approval in approvals
        if approval.status == "pending"
    ]


def compact_handoff_approval_reviews(approvals: list[ReplayApproval]) -> list[ApprovalReviewSummary]:
    high_risk_kinds = {"patch_apply", "shell", "workspace_promote", "desktop_click", "desktop_type"}
    return [
        ApprovalReviewSummary(
            id=approval.id,
            status=approval.status or "pending",  # type: ignore[arg-type]
            action_kind=approval.action_kind,
            summary=(approval.preview_summary or approval.reason)[:500],
            reviewed=approval.reviewed,
            review_count=approval.review_count,
            latest_reviewed_at=approval.latest_reviewed_at,
            latest_review_event_id=approval.latest_review_event_id,
            high_risk=approval.action_kind in high_risk_kinds,
            files=approval.preview_files[:8],
        )
        for approval in approvals
        if approval.status == "pending"
    ]


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
    if bundle.context_snapshot.generated_at:
        lines.extend(["", "## Context Coverage"])
        lines.append(f"- Status: `{bundle.context_snapshot.coverage_status}` tokens `{bundle.context_snapshot.estimated_tokens}` sections `{bundle.context_snapshot.selected_section_count}` dropped `{bundle.context_snapshot.dropped_section_count}`")
        if bundle.context_snapshot.required_sections_missing:
            lines.append(f"- Required missing: {', '.join(bundle.context_snapshot.required_sections_missing[:12])}")
        if bundle.context_snapshot.dropped_sections:
            lines.append(f"- Dropped: {', '.join(bundle.context_snapshot.dropped_sections[:12])}")
        lines.append(f"- Recommended action: {bundle.context_snapshot.recommended_action}")

    if bundle.resume_prompt_quality.generated_at:
        lines.extend(["", "## Resume Prompt Quality"])
        lines.append(f"- Status: `{bundle.resume_prompt_quality.status}` score `{bundle.resume_prompt_quality.score}` ready `{bundle.resume_prompt_quality.ready_to_resume}`")
        lines.append(f"- Next action: {bundle.resume_prompt_quality.next_action or bundle.next_action}")
        lines.append(f"- Recommended action: {bundle.resume_prompt_quality.recommended_action}")
        for issue in bundle.resume_prompt_quality.issues[:8]:
            lines.append(f"- {issue.severity}: {issue.id} - {issue.summary}")

    if bundle.resume_handoff_diff.generated_at:
        lines.extend(["", "## Resume Handoff Drift"])
        lines.append(f"- Status: `{bundle.resume_handoff_diff.status}` changes `{bundle.resume_handoff_diff.changed_count}` blockers `{bundle.resume_handoff_diff.blocker_count}`")
        lines.append(f"- Baseline: `{bundle.resume_handoff_diff.latest_accepted_event_id}` from `{bundle.resume_handoff_diff.latest_accepted_source or 'unknown'}`")
        lines.append(f"- Recommended action: {bundle.resume_handoff_diff.recommended_action}")
        for change in bundle.resume_handoff_diff.changes[:8]:
            lines.append(f"- {change.severity}: {change.field} - {change.summary}")

    if bundle.promotion_audit.generated_at:
        lines.extend(["", "## Promotion Audit"])
        lines.append(f"- Status: `{bundle.promotion_audit.status}` ready `{bundle.promotion_audit.ready_to_promote}` changed `{bundle.promotion_audit.changed_file_count}`")
        lines.append(f"- Latest verification: {bundle.promotion_audit.latest_verification or 'none'}")
        lines.append(f"- Drift/Git: `{bundle.promotion_audit.resume_drift_status}` / `{bundle.promotion_audit.git_checkpoint_status}`")
        lines.append(f"- Approval histories: unresolved `{bundle.promotion_audit.unresolved_approval_history_count}`")
        for history in bundle.promotion_audit.unresolved_approval_histories[:4]:
            lines.append(f"- Unresolved gate: {history}")
        lines.append(f"- Recommended action: {bundle.promotion_audit.recommended_action}")
        for issue in bundle.promotion_audit.issues[:8]:
            evidence = "; ".join(issue.evidence[:3])
            suffix = f" Evidence: {evidence}" if evidence else ""
            lines.append(f"- `{issue.severity}` {issue.id}: {issue.summary}{suffix}")

    if bundle.promotion_verification.generated_at:
        lines.extend(["", "## Promotion Verification"])
        lines.append(f"- Status: `{bundle.promotion_verification.status}` attempts `{bundle.promotion_verification.attempt_count}` failed `{bundle.promotion_verification.failed_count}` hints `{bundle.promotion_verification.repair_hint_count}`")
        lines.append(f"- Next command: `{bundle.promotion_verification.next_command or 'none'}` alternate `{bundle.promotion_verification.should_use_alternate}`")
        if bundle.promotion_verification.latest_repair_hint:
            lines.append(f"- Latest repair hint: {bundle.promotion_verification.latest_repair_hint}")
        lines.append(f"- Recommended action: {bundle.promotion_verification.recommended_action}")
        for attempt in bundle.promotion_verification.attempts[-8:]:
            target = f" `{attempt.suspected_file}:{attempt.suspected_line}`" if attempt.suspected_file and attempt.suspected_line else f" `{attempt.suspected_file}`" if attempt.suspected_file else ""
            hint = f" Hint: {attempt.repair_hint}" if attempt.repair_hint else ""
            lines.append(
                f"- #{attempt.event_id} `{attempt.ok}` `{attempt.audit_status or 'unknown'}` `{attempt.failure_kind or 'none'}`{target} alternate `{attempt.selected_alternate}`: {attempt.command}{hint}"
            )


    if bundle.promotion_repair.generated_at:
        lines.extend(["", "## Promotion Repair"])
        target = bundle.promotion_repair.target_file or "none"
        if bundle.promotion_repair.target_line:
            target = f"{target}:{bundle.promotion_repair.target_line}"
        lines.append(f"- Phase: `{bundle.promotion_repair.phase}` active `{bundle.promotion_repair.active}` target `{target}`")
        lines.append(f"- File read: `{bundle.promotion_repair.file_read}` patch `{bundle.promotion_repair.patch_status or 'none'}` proposal `{bundle.promotion_repair.patch_proposal_id or 'none'}`")
        lines.append(f"- Next: `{bundle.promotion_repair.next_tool or 'none'}` {bundle.promotion_repair.next_action}")
        if bundle.promotion_repair.repair_hint:
            lines.append(f"- Repair hint: {bundle.promotion_repair.repair_hint}")
    if bundle.git_checkpoint.generated_at:
        lines.extend(["", "## Git Checkpoint"])
        lines.append(f"- Status: `{bundle.git_checkpoint.status}`")
        lines.append(f"- Summary: {bundle.git_checkpoint.summary}")
        lines.append(f"- Recommended action: {bundle.git_checkpoint.recommended_action}")
        lines.append(f"- Branch: `{bundle.git_checkpoint.branch or ''}` head `{bundle.git_checkpoint.head_sha or ''}` remotes `{bundle.git_checkpoint.remote_count}` GitHub `{bundle.git_checkpoint.github_remote_count}`")

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
            review_state = "unreviewed"
            if approval.reviewed:
                review_state = f"reviewed x{approval.review_count}"
                if approval.latest_review_event_id:
                    review_state = f"{review_state} event #{approval.latest_review_event_id}"
                if approval.latest_reviewed_at:
                    review_state = f"{review_state} at {approval.latest_reviewed_at}"
            lines.append(
                f"- #{approval.id} `{approval.status}` `{approval.action_kind}` `{review_state}`: {approval.reason}"
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
    if bundle.desktop_effect_proof.run_id:
        lines.extend(["", "## Desktop Effect Proof"])
        lines.append(
            f"- Status: `{bundle.desktop_effect_proof.status}` requires attention `{bundle.desktop_effect_proof.requires_attention}`"
        )
        if bundle.desktop_effect_proof.latest_action_tool:
            lines.append(
                f"- Latest action: `{bundle.desktop_effect_proof.latest_action_tool}` {bundle.desktop_effect_proof.latest_action_summary}"
            )
        if bundle.desktop_effect_proof.proof_tool:
            lines.append(
                f"- Proof: `{bundle.desktop_effect_proof.proof_tool}` {bundle.desktop_effect_proof.proof_summary}"
            )
        if bundle.desktop_effect_proof.proof_snapshot:
            snapshot = bundle.desktop_effect_proof.proof_snapshot
            lines.append(f"- Snapshot: `{snapshot.id}` {snapshot.title} {snapshot.timestamp} {snapshot.path}")
        lines.append(f"- Recommended action: {bundle.desktop_effect_proof.recommended_action}")
        for item in bundle.desktop_effect_proof.ledger[:6]:
            lines.append(f"- {item}")
    if bundle.desktop_effect_proof_repairs.run_id:
        lines.extend(["", "## Desktop Effect Proof Repairs"])
        lines.append(f"- {bundle.desktop_effect_proof_repairs.summary}")
        lines.append(f"- Recommended action: {bundle.desktop_effect_proof_repairs.recommended_action}")
        for entry in bundle.desktop_effect_proof_repairs.entries[:6]:
            reasons = "; ".join(entry.reasons[:2])
            reason_text = f" reasons: {reasons}" if reasons else ""
            lines.append(
                f"- #{entry.event_id} `{entry.outcome}` proof `{entry.previous_proof_status}` -> `{entry.refreshed_proof_status}` "
                f"integrity `{entry.previous_integrity_status}` -> `{entry.refreshed_integrity_status}` snapshot `{entry.proof_snapshot_id or 'none'}`.{reason_text}"
            )
    if bundle.action_context.generated_at:
        lines.extend(["", "## Action Context"])
        for line in bundle.action_context.compact_prompt.splitlines():
            lines.append(line if line.startswith("-") else f"- {line}")

    if bundle.self_scaffold.generated_at:
        lines.extend(["", "## Self Scaffold"])
        lines.append(f"- Status: `{bundle.self_scaffold.status}` changes `{bundle.self_scaffold.change_count}` reversible `{bundle.self_scaffold.reversible_count}`")
        lines.append(
            f"- Reviews: `{bundle.self_scaffold.reviewed_change_count}` reviewed across `{bundle.self_scaffold.review_count}` review event(s); "
            f"latest `#{bundle.self_scaffold.latest_review_event_id or 0}`"
        )
        lines.append(f"- Summary: {bundle.self_scaffold.summary}")
        lines.append(f"- Recommended action: {bundle.self_scaffold.recommended_action}")
        if bundle.self_scaffold_reviews.run_id:
            lines.append(f"- Review outcomes: {bundle.self_scaffold_reviews.summary}")
            lines.append(f"- Review next: {bundle.self_scaffold_reviews.recommended_action}")
            for review in bundle.self_scaffold_reviews.entries[:6]:
                ids = ",".join(review.reviewed_change_ids[:4]) or "none"
                lines.append(
                    f"- Review `#{review.event_id}` `{review.status}` reviewed `{review.reviewed_change_count}` "
                    f"remaining_goal `{review.remaining_goal_review}` ids `{ids}`"
                )
        if bundle.self_scaffold_rollback_intents.run_id:
            lines.append(f"- Rollback intents: {bundle.self_scaffold_rollback_intents.summary}")
            lines.append(f"- Rollback next: {bundle.self_scaffold_rollback_intents.recommended_action}")
            for intent in bundle.self_scaffold_rollback_intents.entries[:6]:
                files = ",".join(intent.files[:4]) or "none"
                lines.append(
                    f"- Intent `{intent.id}` `{intent.action_kind}` status `{intent.status}` tool `{intent.proposed_tool or 'none'}` "
                    f"approval `{intent.requires_approval}` patch `{intent.patch_id or 'none'}` files `{files}`"
                )
        for change in bundle.self_scaffold.changes[:10]:
            evidence = "; ".join(change.evidence[:3])
            suffix = f" Evidence: {evidence}" if evidence else ""
            lines.append(
                f"- `{change.kind}` `{change.status}` `{change.source}` {change.structure_ref}: {change.intent} Reverse: {change.reverse_hint}{suffix}"
            )
    if bundle.operator_dispatches.total_count:
        lines.extend(["", "## Operator Dispatches"])
        lines.append(f"- {bundle.operator_dispatches.summary}")
        lines.append(f"- Recommended action: {bundle.operator_dispatches.recommended_action}")
        for history in bundle.operator_dispatches.unresolved_approval_histories[:8]:
            sequence = " -> ".join(history.sequence[:8])
            kind = f" `{history.approval_kind}`" if history.approval_kind else ""
            summary = f" {history.action_summary}" if history.action_summary else ""
            lines.append(
                f"- Unresolved approval #{history.approval_id}{kind}: events `{history.event_count}` reviewed `{history.reviewed_count}` "
                f"confirmation `{history.confirmation_required_count}` dispatched `{history.dispatched_count}` "
                f"blocked `{history.blocked_count}` latest `{history.latest_status}` #{history.latest_event_id}.{summary} {sequence}"
            )
        for history in bundle.operator_dispatches.approval_histories[:8]:
            sequence = " -> ".join(history.sequence[:8])
            kind = f" `{history.approval_kind}`" if history.approval_kind else ""
            summary = f" {history.action_summary}" if history.action_summary else ""
            lines.append(
                f"- Approval #{history.approval_id}{kind}: events `{history.event_count}` reviewed `{history.reviewed_count}` "
                f"confirmation `{history.confirmation_required_count}` dispatched `{history.dispatched_count}` "
                f"blocked `{history.blocked_count}` latest `{history.latest_status}` #{history.latest_event_id}.{summary} {sequence}"
            )
        if bundle.operator_dispatches.promotion_route_count:
            lines.append(
                f"- Promotion routes: `{bundle.operator_dispatches.promotion_route_count}` approval routes `{bundle.operator_dispatches.promotion_approval_route_count}` "
                f"approval histories `{bundle.operator_dispatches.promotion_approval_history_count}` unresolved `{bundle.operator_dispatches.unresolved_promotion_approval_history_count}`"
            )
        for history in bundle.operator_dispatches.unresolved_promotion_approval_histories[:8]:
            sequence = " -> ".join(history.sequence[:8])
            kind = f" `{history.approval_kind}`" if history.approval_kind else ""
            summary = f" {history.action_summary}" if history.action_summary else ""
            lines.append(
                f"- Unresolved promotion approval #{history.approval_id}{kind}: latest `{history.latest_status}` #{history.latest_event_id}.{summary} {sequence}"
            )
        for history in bundle.operator_dispatches.promotion_approval_histories[:8]:
            sequence = " -> ".join(history.sequence[:8])
            kind = f" `{history.approval_kind}`" if history.approval_kind else ""
            summary = f" {history.action_summary}" if history.action_summary else ""
            lines.append(
                f"- Promotion approval #{history.approval_id}{kind}: latest `{history.latest_status}` #{history.latest_event_id} dispatched `{history.dispatched_count}`.{summary} {sequence}"
            )
        for route in bundle.operator_dispatches.promotion_routes[:8]:
            approval = f" approval#{route.approval_id}" if route.approval_id else ""
            kind = f" `{route.approval_kind}`" if route.approval_kind else ""
            summary = route.action_summary or route.message
            lines.append(
                f"- Promotion route #{route.event_id}: `{route.status}` `{route.decision or 'open'}` `{route.action_reason}` -> `{route.ui_target}`{approval}{kind}: {summary}"
            )
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
        if bundle.report_integrity_refreshes:
            latest_refresh = bundle.report_integrity_refreshes[0]
            lines.append(
                f"- Refreshes: `{len(bundle.report_integrity_refreshes)}` latest `#{latest_refresh.event_id}` "
                f"previous `{latest_refresh.previous_report_status or 'unknown'}` -> `{latest_refresh.report_status or 'unknown'}` "
                f"reasons `{latest_refresh.reason_count}`"
            )
            if latest_refresh.preflight_event_id:
                lines.append(
                    f"- Latest refresh preflight: `#{latest_refresh.preflight_event_id}` "
                    f"`{latest_refresh.preflight_event_kind}` accepted `{latest_refresh.preflight_accepted}`"
                )
            for reason in latest_refresh.reasons[:5]:
                lines.append(f"- Refresh reason: {reason}")
        for check in bundle.report_integrity.checks:
            if check.status != "ok":
                lines.append(f"- `{check.status}` {check.section}: {check.summary}")
    if bundle.checkpoint_quality.run_id:
        lines.extend(["", "## Checkpoint Quality"])
        lines.append(f"- Status: `{bundle.checkpoint_quality.status}`")
        lines.append(f"- Run note: `{bundle.checkpoint_quality.run_note_present}` chars `{bundle.checkpoint_quality.run_note_chars}`")
        lines.append(
            f"- Anchors: goal `{bundle.checkpoint_quality.has_active_goal}`, next `{bundle.checkpoint_quality.has_next_action}`, resume `{bundle.checkpoint_quality.has_resume_prompt}`, refresh `{bundle.checkpoint_quality.has_report_integrity_refresh}`"
        )
        lines.append(f"- Summary: {bundle.checkpoint_quality.summary}")
        for issue in bundle.checkpoint_quality.issues[:6]:
            lines.append(f"- `{issue.severity}` {issue.id}: {issue.summary}")
    if bundle.checkpoint_quality_resumes.run_id and bundle.checkpoint_quality_resumes.repair_count:
        lines.extend(["", "## Checkpoint-Quality Resume Repairs"])
        lines.append(f"- Status: `{bundle.checkpoint_quality_resumes.status}`")
        lines.append(
            f"- Repairs: `{bundle.checkpoint_quality_resumes.repair_count}` resumed `{bundle.checkpoint_quality_resumes.resumed_after_repair_count}` "
            f"blocked `{bundle.checkpoint_quality_resumes.blocked_after_repair_count}` awaiting `{bundle.checkpoint_quality_resumes.awaiting_resume_count}`"
        )
        lines.append(f"- Recommended action: {bundle.checkpoint_quality_resumes.recommended_action}")
        for entry in bundle.checkpoint_quality_resumes.entries[:8]:
            resume = f" resume `#{entry.resume_event_id}` `{entry.resume_policy_action}` accepted `{entry.resume_accepted}`" if entry.resume_event_id else " resume `pending`"
            lines.append(
                f"- Repair `#{entry.repair_completed_event_id}` `{entry.repair_reason}` -> `{entry.repair_ui_target}`{resume}; "
                f"checkpoint `{entry.checkpoint_quality_status}` ready `{entry.checkpoint_quality_ready}`. {entry.summary}"
            )
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
        if bundle.readiness_completion.self_scaffold_status:
            lines.append(
                f"- Self scaffold: `{bundle.readiness_completion.self_scaffold_status}` pending `{bundle.readiness_completion.self_scaffold_pending_review_count}` "
                f"reviews `{bundle.readiness_completion.self_scaffold_reviewed_change_count}/{bundle.readiness_completion.self_scaffold_review_count}`"
            )
        if bundle.readiness_completion.source_visible_required_label_count or bundle.readiness_completion.readiness_proof_source_ref_count:
            missing = ", ".join(bundle.readiness_completion.source_visible_missing_ref_labels[:6]) or "none"
            labels = ", ".join(bundle.readiness_completion.readiness_proof_source_ref_labels[:6]) or "none"
            lines.append(
                f"- Source refs: visible `{bundle.readiness_completion.source_visible_matched_label_count}/{bundle.readiness_completion.source_visible_required_label_count}` "
                f"proof refs `{bundle.readiness_completion.readiness_proof_source_ref_count}` labels `{labels}` missing `{missing}`"
            )
        for check in bundle.readiness_completion.checks:
            lines.append(f"- `{check.status}` {check.id}: {check.summary}")
        for action in bundle.readiness_completion.next_actions[:5]:
            lines.append(f"- Next: {action}")
    if bundle.readiness_source_ref_preview.run_id:
        lines.extend(["", "## Readiness Source Refs"])
        missing_evidence = ", ".join(bundle.readiness_source_ref_preview.missing_source_evidence_labels[:6]) or "none"
        missing_proof = ", ".join(bundle.readiness_source_ref_preview.missing_proof_ref_labels[:6]) or "none"
        source_labels = ", ".join(bundle.readiness_source_ref_preview.source_evidence_labels[:6]) or "none"
        proof_labels = ", ".join(bundle.readiness_source_ref_preview.proof_ref_labels[:6]) or "none"
        lines.append(f"- Status: `{bundle.readiness_source_ref_preview.status}`")
        lines.append(f"- Summary: {bundle.readiness_source_ref_preview.summary}")
        lines.append(
            f"- Labels: source `{source_labels}` proof `{proof_labels}` missing evidence `{missing_evidence}` missing proof `{missing_proof}`"
        )
        lines.append(f"- Recommended action: {bundle.readiness_source_ref_preview.recommended_action}")
    if bundle.readiness_rehearsal.run_id:
        lines.extend(["", "## Readiness Rehearsal"])
        lines.append(f"- Status: `{bundle.readiness_rehearsal.status}`")
        lines.append(f"- Scenario: `{bundle.readiness_rehearsal.scenario}`")
        lines.append(f"- Summary: {bundle.readiness_rehearsal.summary}")
        lines.append(f"- Restart simulated: `{bundle.readiness_rehearsal.restart_simulated}`")
        lines.append(
            f"- Events: refused `#{bundle.readiness_rehearsal.refused_event_id}` accepted `#{bundle.readiness_rehearsal.accepted_event_id}` completed `#{bundle.readiness_rehearsal.completed_event_id}`"
        )
        lines.append(
            f"- Self scaffold review: `{bundle.readiness_rehearsal.self_scaffold_reviewed}` event `#{bundle.readiness_rehearsal.self_scaffold_review_event_id}` reviewed `{bundle.readiness_rehearsal.self_scaffold_reviewed_change_count}`"
        )
        lines.append(
            f"- Post-review handoff: goal `{bundle.readiness_rehearsal.post_review_handoff_goal_preserved}` next `{bundle.readiness_rehearsal.post_review_handoff_next_action_preserved}` resume-goal `{bundle.readiness_rehearsal.post_review_resume_prompt_goal_preserved}` resume-next `{bundle.readiness_rehearsal.post_review_resume_prompt_next_action_preserved}`"
        )
        if bundle.readiness_rehearsal.compact_context_tokens:
            sections = ", ".join(bundle.readiness_rehearsal.compact_context_sections[:10])
            lines.append(f"- Compact context tokens: `{bundle.readiness_rehearsal.compact_context_tokens}` sections: {sections}")
        for step in bundle.readiness_rehearsal.steps:
            evidence = "; ".join(step.evidence[:4])
            suffix = f" Evidence: {evidence}" if evidence else ""
            event = f" event=#{step.event_id}" if step.event_id else ""
            lines.append(f"- `{step.status}` {step.id}{event}: {step.summary}{suffix}")
    if bundle.readiness_proof_history.total_count:
        lines.extend(["", "## Readiness Proof History"])
        lines.append(f"- Status: `{bundle.readiness_proof_history.status}`")
        lines.append(f"- Summary: {bundle.readiness_proof_history.summary}")
        lines.append(
            f"- Proofs: self-scaffold `{bundle.readiness_proof_history.self_scaffold_review_count}` "
            f"post-review handoff `{bundle.readiness_proof_history.post_review_handoff_count}` "
            f"resume prompt `{bundle.readiness_proof_history.resume_prompt_preservation_count}` "
            f"readiness claims `{bundle.readiness_proof_history.readiness_claim_count}` blocks `{bundle.readiness_proof_history.blocking_count}`"
        )
        if bundle.readiness_proof_history.source_evidence_ref_count:
            labels = ", ".join(bundle.readiness_proof_history.source_evidence_labels[:6]) or "none"
            lines.append(
                f"- Source refs: `{bundle.readiness_proof_history.source_evidence_ref_count}` labels `{labels}`. "
                f"{bundle.readiness_proof_history.source_evidence_summary}"
            )
        lines.append(f"- Recommended action: {bundle.readiness_proof_history.recommended_action}")
        for entry in bundle.readiness_proof_history.entries[:12]:
            event = f"#{entry.event_id}" if entry.event_id else "report"
            evidence = "; ".join(entry.evidence[:4])
            evidence_text = f" Evidence: {evidence}" if evidence else ""
            source_refs = "; ".join(
                f"{ref.evidence_label}:{ref.kind}:{ref.id or ref.title or ref.target}"
                for ref in entry.source_refs[:3]
            )
            source_text = f" Sources: {source_refs}" if source_refs else ""
            step = f" `{entry.step_id}`" if entry.step_id else ""
            lines.append(
                f"- {event} `{entry.status}` `{entry.proof_type}` `{entry.source}`{step}: {entry.summary}{evidence_text}{source_text}"
            )
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
    if bundle.ornith_preflight_warnings.total_count:
        lines.extend(["", "## Ornith Preflight Warning History"])
        lines.append(f"- {bundle.ornith_preflight_warnings.summary}")
        lines.append(
            f"- Warnings: `{bundle.ornith_preflight_warnings.warning_count}` blocks `{bundle.ornith_preflight_warnings.block_count}` action-context reorients `{bundle.ornith_preflight_warnings.action_context_reorient_count}`"
        )
        if bundle.ornith_preflight_warnings.recommended_action:
            lines.append(f"- Recommended action: {bundle.ornith_preflight_warnings.recommended_action}")
        for entry in bundle.ornith_preflight_warnings.entries[:12]:
            event = f"#{entry.event_id}" if entry.event_id else "current"
            evidence = "; ".join(entry.evidence[:4])
            evidence_text = f" Evidence: {evidence}" if evidence else ""
            next_text = f" Next: {entry.next_action}" if entry.next_action else ""
            lines.append(
                f"- {event} `{entry.status}` `{entry.source}` {entry.item_id}: {entry.summary}{evidence_text}{next_text}"
            )
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
            details = []
            if failure.command:
                details.append(f"command `{failure.command}`")
            if failure.target:
                details.append(f"target `{failure.target}`")
            if failure.returncode is not None:
                details.append(f"rc `{failure.returncode}`")
            detail_text = f" ({'; '.join(details)})" if details else ""
            lines.append(f"- `{failure.kind}` `{failure.tool}` x{failure.count}{detail_text}: {failure.recovery_hint}")
            if failure.evidence_excerpt:
                lines.append(f"  Evidence: {failure.evidence_excerpt[:500]}")
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


