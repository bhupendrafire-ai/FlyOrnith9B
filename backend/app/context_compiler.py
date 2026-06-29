from __future__ import annotations

import json
from datetime import datetime, timezone

from .acceptance import compact_label_progress
from .action_context import render_action_context_pack
from .memory import MemoryContext
from .model_profile import GENERIC_PROFILE, ModelProfile
from .schemas import ContextSnapshot, RunRecord, RunState


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


REQUIRED_CONTEXT_SECTIONS = {
    "goal",
    "handoff",
    "approval_reviews",
    "repo_map",
    "task_graph",
    "action_context",
    "self_scaffold",
    "readiness_source_ref_preview",
    "desktop_effect_proof",
    "run_health",
    "objective_readiness",
    "resume_prompt_quality",
    "resume_handoff_diff",
    "promotion_audit",
    "promotion_verification",
    "promotion_repair",
    "recent_tools",
    "recent_events",
    "memory",
}


class ContextCompiler:
    def __init__(self, target_tokens: int, profile: ModelProfile = GENERIC_PROFILE) -> None:
        self.target_tokens = target_tokens
        self.profile = profile

    def compile(self, run: RunRecord, state: RunState, memory: MemoryContext, latest_events: list[dict]) -> tuple[str, ContextSnapshot]:
        sections: list[tuple[str, str]] = [
            ("goal", self._goal_section(run, state)),
            ("model_profile", self.profile.summary),
            ("handoff", state.handoff_summary.model_dump_json(exclude_defaults=True)[: self.profile.handoff_chars]),
            ("approval_reviews", self._approval_review_line(state)),
            ("repo_map", state.repo_map.model_dump_json()),
            ("task_graph", json.dumps([task.model_dump() for task in state.task_graph[-12:]], ensure_ascii=True)),
            ("acceptance_evidence", json.dumps([item.model_dump() for item in state.acceptance_evidence], ensure_ascii=True)),
            (
                "acceptance_recommendations",
                json.dumps([item.model_dump() for item in state.acceptance_recommendations[:8]], ensure_ascii=True),
            ),
            (
                "acceptance_recommendation_traces",
                json.dumps([item.model_dump() for item in state.acceptance_recommendation_traces[-8:]], ensure_ascii=True),
            ),
            ("goal_evolution", self._goal_evolution_line(state)),
            ("git_checkpoint", self._git_checkpoint_line(state)),
            ("source_evidence", self._source_evidence_line(state)),
            ("readiness_source_ref_preview", self._readiness_source_ref_preview_line(state)),
            ("desktop_effect_proof", self._desktop_effect_proof_line(state)),
            ("action_context", self._action_context_line(state)),
            ("self_scaffold", self._self_scaffold_line(state)),
            ("run_health", state.run_health.model_dump_json()),
            ("ornith_preflight", self._ornith_preflight_line(state)),
            ("ornith_preflight_actions", self._ornith_preflight_action_line(state)),
            ("run_progress", self._run_progress_line(state)),
            ("report_integrity", self._report_integrity_line(state)),
            ("checkpoint_quality", self._checkpoint_quality_line(state)),
            ("checkpoint_quality_resumes", self._checkpoint_quality_resume_line(state)),
            ("objective_readiness", self._objective_readiness_line(state)),
            ("resume_decisions", state.handoff_summary.resume_decisions.model_dump_json()),
            ("resume_prompt_quality", self._resume_prompt_quality_line(state)),
            ("resume_handoff_diff", self._resume_handoff_diff_line(state)),
            ("promotion_audit", self._promotion_audit_line(state)),
            ("promotion_verification", self._promotion_verification_line(state)),
            ("promotion_repair", self._promotion_repair_line(state)),
            ("autonomy_decisions", self._autonomy_decision_line(state)),
            ("operator_dispatches", self._operator_dispatch_line(state)),
            ("action_readiness", state.action_readiness.model_dump_json()),
            ("action_readiness_decisions", state.action_readiness_decisions.model_dump_json()),
            ("readiness_completion", self._readiness_completion_line(state)),
            ("readiness_rehearsal", self._readiness_rehearsal_line(state)),
            ("recovery_decisions", state.recovery_decisions.model_dump_json()),
            ("verification_outcomes", state.verification_outcomes.model_dump_json()),
            ("post_action_retries", self._post_action_retry_line(state)),
            ("recent_tools", json.dumps([call.model_dump() for call in state.tool_calls[-8:]], ensure_ascii=True)),
            ("recent_events", json.dumps(latest_events[-10:], ensure_ascii=True)),
            ("memory", memory.as_prompt_text()[: self.profile.memory_chars]),
        ]

        selected: list[str] = []
        selected_names: list[str] = []
        all_names: list[str] = []
        token_estimates: dict[str, int] = {}
        for name, body in sections:
            candidate = f"## {name}\n{body.strip()}"
            all_names.append(name)
            token_estimates[name] = estimate_tokens(candidate)
            if estimate_tokens("\n\n".join(selected + [candidate])) > self.target_tokens:
                continue
            selected.append(candidate)
            selected_names.append(name)
        prompt = "\n\n".join(selected)
        selected_set = set(selected_names)
        dropped_sections = [name for name in all_names if name not in selected_set]
        required_missing = [name for name in all_names if name in REQUIRED_CONTEXT_SECTIONS and name not in selected_set]
        coverage_status = "critical" if required_missing else "degraded" if dropped_sections else "ok"
        if coverage_status == "critical":
            recommended_action = "Checkpoint and re-orient from handoff before asking Ornith for another broad action."
        elif coverage_status == "degraded":
            recommended_action = "Continue with selected compact context; use replay/API references for omitted optional sections."
        else:
            recommended_action = "Context coverage is complete under the current target."
        snapshot = ContextSnapshot(
            run_id=run.id,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            estimated_tokens=estimate_tokens(prompt),
            sections=selected_names,
            selected_section_count=len(selected_names),
            dropped_sections=dropped_sections,
            dropped_section_count=len(dropped_sections),
            required_sections_missing=required_missing,
            section_token_estimates=token_estimates,
            coverage_status=coverage_status,
            recommended_action=recommended_action,
            prompt_preview=prompt[:4000],
        )
        return prompt, snapshot

    def _goal_section(self, run: RunRecord, state: RunState) -> str:
        return "\n".join(
            [
                f"Original goal: {run.goal}",
                f"Active goal: {state.goal}",
                f"Milestone: {state.milestone}",
                f"Next step: {state.next_step}",
                "Acceptance criteria: " + "; ".join(state.acceptance_criteria),
                "Acceptance evidence: " + "; ".join(
                    self._acceptance_line(item) for item in state.acceptance_evidence
                ),
                self._goal_evolution_line(state),
                self._git_checkpoint_line(state),
                "Next evidence actions: " + "; ".join(
                    f"{item.criterion} -> {item.tool_kind}:{item.action}"
                    for item in state.acceptance_recommendations[:5]
                ),
                "Evidence action traces: " + "; ".join(
                    f"{item.status}:{item.label}:{item.selected_tool}"
                    for item in state.acceptance_recommendation_traces[-5:]
                ),
                self._source_evidence_line(state),
                self._readiness_source_ref_preview_line(state),
                self._action_context_line(state),
                f"Run health: {state.run_health.level}:{state.run_health.recommended_action}:{state.run_health.score}",
                self._ornith_preflight_line(state),
                self._ornith_preflight_action_line(state),
                self._run_progress_line(state),
                self._report_integrity_line(state),
                self._checkpoint_quality_line(state),
                self._checkpoint_quality_resume_line(state),
                self._objective_readiness_line(state),
                self._readiness_completion_line(state),
                self._readiness_rehearsal_line(state),
                self._resume_decision_line(state),
                self._resume_prompt_quality_line(state),
                self._resume_handoff_diff_line(state),
                self._promotion_verification_line(state),
                self._promotion_repair_line(state),
                self._autonomy_decision_line(state),
                self._operator_dispatch_line(state),
                self._approval_review_line(state),
                self._action_readiness_line(state),
                self._action_readiness_decision_line(state),
                self._recovery_decision_line(state),
                self._verification_outcome_line(state),
                self._post_action_retry_line(state),
                "Open blockers: " + "; ".join(state.blockers[-6:]),
            ]
        )

    def _goal_evolution_line(self, state: RunState) -> str:
        report = state.goal_evolution
        if not report.generated_at:
            report = state.handoff_summary.goal_evolution
        if not report.generated_at:
            return "Goal evolution: none"
        latest = report.latest_decision
        latest_text = f"{latest.status}:{latest.source}" if latest.id else "none"
        proposed = f" proposed={report.proposed_goal}" if report.proposed_goal else ""
        return (
            f"Goal evolution: latest={latest_text}; pending={report.pending_count}; "
            f"accepted={report.accepted_count}; rejected={report.rejected_count}; "
            f"unchanged={report.unchanged_count};{proposed} {report.recommended_action}"
        )


    def _git_checkpoint_line(self, state: RunState) -> str:
        report = state.git_checkpoint
        if not report.generated_at:
            report = state.handoff_summary.git_checkpoint
        if not report.generated_at:
            return "Git checkpoint: unknown"
        remote_text = ",".join(report.remote_names) if report.remote_names else "none"
        return (
            f"Git checkpoint: {report.status}; changed={report.changed_count}; "
            f"staged={report.staged_count}; modified={report.modified_count}; "
            f"untracked={report.untracked_count}; ahead={report.ahead_count}; "
            f"branch={report.branch or ''}; remotes={remote_text}; {report.recommended_action}"
        )


    def _acceptance_line(self, item: object) -> str:
        required = getattr(item, "required_labels", [])
        matched = getattr(item, "matched_labels", [])
        progress = compact_label_progress(required, matched)
        suffix = f"[{progress}]" if progress else ""
        return f"{getattr(item, 'status', 'open')}:{getattr(item, 'criterion', '')}{suffix}"


    def _self_scaffold_line(self, state: RunState) -> str:
        report = state.self_scaffold
        if not report.generated_at:
            report = state.handoff_summary.self_scaffold
        if not report.generated_at:
            return "No self-scaffold change-intent report has been generated yet."
        changes = [
            f"{item.kind}:{item.status}:{item.summary} reverse={item.reverse_hint}"
            for item in report.changes[:8]
        ]
        review_report = state.self_scaffold_reviews
        if not review_report.run_id:
            review_report = state.handoff_summary.self_scaffold_reviews
        latest_review = review_report.entries[0].summary if review_report.entries else ""
        rollback_report = state.self_scaffold_rollback_intents
        if not rollback_report.run_id:
            rollback_report = state.handoff_summary.self_scaffold_rollback_intents
        latest_rollback_intent = rollback_report.entries[0].summary if rollback_report.entries else ""
        return json.dumps(
            {
                "status": report.status,
                "summary": report.summary,
                "recommended_action": report.recommended_action,
                "latest_change": report.latest_change,
                "review_count": report.review_count,
                "reviewed_change_count": report.reviewed_change_count,
                "latest_review_event_id": report.latest_review_event_id,
                "review_outcomes": review_report.summary,
                "review_latest": latest_review,
                "review_next": review_report.recommended_action,
                "rollback_intents": rollback_report.summary,
                "rollback_latest": latest_rollback_intent,
                "rollback_next": rollback_report.recommended_action,
                "changes": changes,
            },
            ensure_ascii=True,
        )

    def _action_context_line(self, state: RunState) -> str:
        pack = state.action_context
        if not pack.generated_at:
            pack = state.handoff_summary.action_context
        return render_action_context_pack(pack)
    def _source_evidence_line(self, state: RunState) -> str:
        report = state.source_evidence
        if not report.generated_at:
            report = state.handoff_summary.source_evidence
        if not report.generated_at:
            return "Source evidence: none"
        missing = ",".join(report.missing_labels) if report.missing_labels else "none"
        latest = report.latest_evidence or "none"
        return (
            f"Source evidence: total={report.total_count}; web={report.web_source_count}; "
            f"browser={report.browser_snapshot_count}; desktop={report.desktop_snapshot_count}; "
            f"linked_criteria={report.linked_criterion_count}; matched={report.matched_label_count}/{report.required_label_count}; "
            f"missing={missing}; latest={latest}; {report.recommended_action}"
        )

    def _readiness_source_ref_preview_line(self, state: RunState) -> str:
        report = state.readiness_source_ref_preview
        if not report.run_id:
            report = state.handoff_summary.readiness_source_ref_preview
        if not report.run_id:
            return "Readiness source refs: unknown"
        source_labels = ",".join(report.source_evidence_labels[:6]) or "none"
        proof_labels = ",".join(report.proof_ref_labels[:6]) or "none"
        missing_evidence = ",".join(report.missing_source_evidence_labels[:6]) or "none"
        missing_proof = ",".join(report.missing_proof_ref_labels[:6]) or "none"
        return (
            f"Readiness source refs: {report.status}; source_labels={source_labels}; "
            f"proof_labels={proof_labels}; missing_evidence={missing_evidence}; "
            f"missing_proof={missing_proof}; {report.recommended_action}"
        )

    def _desktop_effect_proof_line(self, state: RunState) -> str:
        report = state.desktop_effect_proof
        if not report.run_id:
            report = state.handoff_summary.desktop_effect_proof
        if not report.run_id:
            return "Desktop effect proof: unknown"
        snapshot = report.proof_snapshot.id if report.proof_snapshot else "none"
        latest_action = report.latest_action_tool or "none"
        proof = report.proof_tool or "none"
        ledger = " | ".join(report.ledger[:3]) or "none"
        repairs = state.desktop_effect_proof_repairs
        if not repairs.run_id:
            repairs = state.handoff_summary.desktop_effect_proof_repairs
        repair_label = "none"
        if repairs.run_id and repairs.total_count:
            repair_label = f"{repairs.latest_outcome or 'unknown'}/{repairs.total_count}"
        return (
            f"Desktop effect proof: {report.status}; requires_attention={report.requires_attention}; "
            f"latest_action={latest_action}; proof={proof}; snapshot={snapshot}; repairs={repair_label}; "
            f"ledger={ledger}; {report.recommended_action}"
        )

    def _ornith_preflight_line(self, state: RunState) -> str:
        report = state.ornith_preflight
        if not report.generated_at:
            report = state.handoff_summary.ornith_preflight
        if not report.generated_at:
            return "Ornith preflight: unknown"
        blockers = sum(1 for item in report.items if item.status == "block")
        warnings = sum(1 for item in report.items if item.status == "warn")
        next_action = report.next_actions[0] if report.next_actions else ""
        return (
            f"Ornith preflight: {report.status}; mode={report.mode}; "
            f"ready_start={report.ready_to_start}; ready_resume={report.ready_to_resume}; "
            f"blockers={blockers}; warnings={warnings}; smoke={report.readiness_smoke_status}; "
            f"dispatch={report.dispatch_restart_smoke_status}; health={report.run_health_level}/{report.run_health_action}; "
            f"next={next_action}"
        )

    def _ornith_preflight_action_line(self, state: RunState) -> str:
        report = state.ornith_preflight_actions
        if not report.generated_at:
            report = state.handoff_summary.ornith_preflight_actions
        if not report.generated_at:
            return "Ornith preflight actions: none"
        latest = report.entries[0] if report.entries else None
        latest_text = (
            f"{latest.status}:{latest.item_id}:{latest.ui_target}"
            if latest
            else "none"
        )
        return (
            f"Ornith preflight actions: latest={latest_text}; completed={report.completed_count}; "
            f"dispatched={report.dispatched_count}; context={report.context_checkpoint_count}; "
            f"handoff={report.handoff_refresh_count}; smoke={report.smoke_count}; {report.recommended_action}"
        )

    def _approval_review_line(self, state: RunState) -> str:
        reviews = state.handoff_summary.approval_reviews
        if not reviews and state.handoff_summary.approvals:
            return "Approval gates: " + "; ".join(state.handoff_summary.approvals[:8])
        if not reviews:
            return "Approval gates: none"
        pending = [item for item in reviews if item.status == "pending"]
        reviewed = [item for item in pending if item.reviewed]
        unreviewed = [item for item in pending if not item.reviewed]
        high_risk = [item for item in pending if item.high_risk]
        latest = max(reviews, key=lambda item: item.latest_review_event_id, default=None)
        latest_text = (
            f"{latest.action_kind}#{latest.id}:event#{latest.latest_review_event_id}"
            if latest and latest.latest_review_event_id
            else "none"
        )
        samples = "; ".join(
            f"{item.action_kind}#{item.id}:{'reviewed' if item.reviewed else 'unreviewed'}:{item.summary}"
            for item in pending[:4]
        )
        suffix = f"; {samples}" if samples else ""
        return (
            f"Approval gates: pending={len(pending)}; unreviewed={len(unreviewed)}; "
            f"reviewed={len(reviewed)}; high_risk={len(high_risk)}; latest={latest_text}{suffix}"
        )

    def _resume_decision_line(self, state: RunState) -> str:
        report = state.handoff_summary.resume_decisions
        if not report.run_id:
            return "Resume decision: none"
        latest = report.latest_decision
        latest_text = (
            f"{'accepted' if latest.accepted else 'blocked'}:{latest.source}:{latest.policy_action}"
            if latest.id
            else "none"
        )
        match = "matches" if report.current_matches_last_accepted else "differs"
        return f"Resume decision: latest={latest_text}; current-vs-accepted={match}; {report.recommended_action}"

    def _resume_prompt_quality_line(self, state: RunState) -> str:
        report = state.resume_prompt_quality
        if not report.generated_at:
            report = state.handoff_summary.resume_prompt_quality
        if not report.generated_at:
            return "Resume prompt quality: not generated"
        return (
            f"Resume prompt quality: {report.status}; score={report.score}; "
            f"concrete_next={report.concrete_next_action}; context={report.context_coverage_status}; "
            f"action={report.recommended_action}"
        )

    def _resume_handoff_diff_line(self, state: RunState) -> str:
        report = state.resume_handoff_diff
        if not report.generated_at:
            report = state.handoff_summary.resume_handoff_diff
        if not report.generated_at:
            return "Resume handoff drift: not generated"
        return (
            f"Resume handoff drift: {report.status}; baseline={report.latest_accepted_event_id}; "
            f"changes={report.changed_count}; blockers={report.blocker_count}; {report.recommended_action}"
        )

    def _promotion_audit_line(self, state: RunState) -> str:
        report = state.promotion_audit
        if not report.generated_at:
            report = state.handoff_summary.promotion_audit
        if not report.generated_at:
            return "Promotion audit: not generated"
        latest = report.latest_verification or "none"
        approval_history = report.unresolved_approval_histories[0] if report.unresolved_approval_histories else ""
        approval_text = f"; approval_history={approval_history}" if approval_history else ""
        return (
            f"Promotion audit: {report.status}; ready={report.ready_to_promote}; "
            f"changed={report.changed_file_count}; patches={report.patch_proposal_count}/{report.patch_application_count}; "
            f"pending_patches={report.pending_patch_count}; pending_approvals={report.pending_approval_count}; "
            f"unresolved_approval_histories={report.unresolved_approval_history_count}{approval_text}; "
            f"drift={report.resume_drift_status}; latest_verification={latest}; {report.recommended_action}"
        )

    def _promotion_verification_line(self, state: RunState) -> str:
        report = state.promotion_verification
        if not report.generated_at:
            report = state.handoff_summary.promotion_verification
        if not report.generated_at:
            return "Promotion verification: not generated"
        latest = report.latest_attempt
        latest_text = f"{latest.ok}:{latest.command}" if latest.command else "none"
        file_text = f"; file={report.latest_suspected_file}" if report.latest_suspected_file else ""
        hint_text = f"; repair={report.latest_repair_hint}" if report.latest_repair_hint else ""
        return (
            f"Promotion verification: {report.status}; attempts={report.attempt_count}; "
            f"failed={report.failed_count}; repeated={report.repeated_failure_count}; "
            f"latest={latest_text}; failure={report.latest_failure_kind or 'none'}{file_text}; "
            f"next={report.next_command or 'none'}; alternate={report.should_use_alternate}{hint_text}; "
            f"{report.recommended_action}"
        )

    def _promotion_repair_line(self, state: RunState) -> str:
        report = state.promotion_repair
        if not report.generated_at:
            report = state.handoff_summary.promotion_repair
        if not report.generated_at:
            return "Promotion repair: not generated"
        target = report.target_file or "none"
        if report.target_line:
            target = f"{target}:{report.target_line}"
        patch = f"{report.patch_status}:{report.patch_proposal_id}" if report.patch_proposal_id else report.patch_status or "none"
        return (
            f"Promotion repair: {report.phase}; active={report.active}; target={target}; "
            f"file_read={report.file_read}; patch={patch}; next_tool={report.next_tool or 'none'}; "
            f"next_verify={report.next_verification_command or 'none'}; {report.next_action or report.summary}"
        )
    def _run_progress_line(self, state: RunState) -> str:
        report = state.run_progress
        if not report.run_id:
            return "Run progress: unknown"
        return (
            f"Run progress: {report.status}; keep_running={report.can_keep_running}; "
            f"tasks={report.task_completed}/{report.task_total}; "
            f"acceptance={report.acceptance_verified}/{report.acceptance_total}; {report.summary}"
        )

    def _report_integrity_line(self, state: RunState) -> str:
        report = state.report_integrity
        if not report.run_id:
            return "Report integrity: unknown"
        refreshes = state.report_integrity_refreshes or state.handoff_summary.report_integrity_refreshes
        refresh_text = ""
        if refreshes:
            latest = refreshes[0]
            reason = latest.reasons[0] if latest.reasons else ""
            reason_text = f"; refresh_reason={reason[:180]}" if reason else ""
            preflight = f"; preflight=#{latest.preflight_event_id}:{latest.preflight_event_kind}" if latest.preflight_event_id else ""
            refresh_text = (
                f"; refresh=#{latest.event_id}:{latest.previous_report_status or 'unknown'}->{latest.report_status or 'unknown'}"
                f" reasons={latest.reason_count}{preflight}{reason_text}"
            )
        return (
            f"Report integrity: {report.status}; ok={report.ok_count}/{report.check_count}; "
            f"missing={report.missing_count}; stale={report.stale_count}; mismatch={report.mismatch_count}; "
            f"{report.recommended_action}{refresh_text}"
        )

    def _checkpoint_quality_line(self, state: RunState) -> str:
        report = state.checkpoint_quality
        if not report.run_id:
            report = state.handoff_summary.checkpoint_quality
        if not report.run_id:
            return "Checkpoint quality: unknown"
        latest_issue = report.issues[0].id if report.issues else "none"
        refresh = f"; expected_refresh=#{report.expected_refresh_event_id}" if report.expected_refresh_event_id else ""
        return (
            f"Checkpoint quality: {report.status}; note={report.run_note_present}; "
            f"anchors=goal:{report.has_active_goal},next:{report.has_next_action},resume:{report.has_resume_prompt},refresh:{report.has_report_integrity_refresh}; "
            f"blockers={report.blocker_count}; warnings={report.warning_count}; latest_issue={latest_issue}{refresh}; "
            f"{report.recommended_action}"
        )
    def _checkpoint_quality_resume_line(self, state: RunState) -> str:
        report = state.checkpoint_quality_resumes
        if not report.run_id:
            report = state.handoff_summary.checkpoint_quality_resumes
        if not report.run_id or report.status == "none":
            return "Checkpoint-quality resume repairs: none"
        latest = report.latest
        repair = (
            f"repair=#{latest.repair_completed_event_id}:{latest.repair_reason}:{latest.repair_ui_target}"
            if latest.repair_completed_event_id
            else "repair=none"
        )
        if latest.resume_event_id:
            accepted = "accepted" if latest.resume_accepted else "blocked"
            policy = latest.resume_policy_action or "unknown"
            resume = f"; resume=#{latest.resume_event_id}:{policy}:{accepted}"
        else:
            resume = "; resume=awaiting"
        ready = f"; checkpoint_ready={latest.checkpoint_quality_ready}:{latest.checkpoint_quality_status or 'unknown'}"
        return (
            f"Checkpoint-quality resume repairs: {report.status}; repairs={report.repair_count}; "
            f"resumed={report.resumed_after_repair_count}; blocked={report.blocked_after_repair_count}; "
            f"awaiting={report.awaiting_resume_count}; {repair}{resume}{ready}; {report.recommended_action}"
        )

    def _objective_readiness_line(self, state: RunState) -> str:
        report = state.objective_readiness
        if not report.run_id:
            return "Objective readiness: unknown"
        next_action = report.next_actions[0] if report.next_actions else report.recommended_action
        proof = next(
            (
                f"{item.proof.tool_kind}:{item.proof.evidence_label}"
                for item in report.items
                if item.status != "verified" and (item.proof.tool_kind or item.proof.evidence_label)
            ),
            "",
        )
        proof_text = f"; proof={proof}" if proof else ""
        preferred = next(
            (
                f"{item.preferred_proof.tool_kind}:{item.preferred_proof.strategy}:{item.preferred_proof.confidence}"
                for item in report.items
                if item.status != "verified" and (item.preferred_proof.tool_kind or item.preferred_proof.strategy)
            ),
            "",
        )
        preferred_text = f"; prefer={preferred}" if preferred else ""
        return (
            f"Objective readiness: {report.status}; verified={report.verified_count}; "
            f"partial={report.partial_count}; missing={report.missing_count}; failed={report.failed_count}"
            f"{proof_text}{preferred_text}; {next_action}"
        )

    def _readiness_completion_line(self, state: RunState) -> str:
        report = state.readiness_completion
        if not report.run_id:
            return "Readiness completion: unknown"
        return (
            f"Readiness completion: {report.status}; claim={report.can_claim_milestone}; "
            f"confidence={report.confidence}; verified={report.verified_count}/{report.required_verified_count}; "
            f"blockers={report.blocking_count}; warnings={report.warning_count}; "
            f"self_scaffold={report.self_scaffold_status or 'unknown'}:{report.self_scaffold_pending_review_count}; "
            f"{report.summary}"
        )

    def _readiness_rehearsal_line(self, state: RunState) -> str:
        report = state.readiness_rehearsal
        if not report.run_id:
            return "Readiness rehearsal: not run"
        return (
            f"Readiness rehearsal: {report.status}; restart={report.restart_simulated}; "
            f"steps={sum(1 for step in report.steps if step.status == 'passed')}/{len(report.steps)}; "
            f"events=refused#{report.refused_event_id}/accepted#{report.accepted_event_id}/completed#{report.completed_event_id}; "
            f"{report.summary}"
        )

    def _autonomy_decision_line(self, state: RunState) -> str:
        report = state.autonomy_decisions
        if not report.run_id:
            return "Autonomy decisions: none"
        latest = report.latest_decision
        latest_text = (
            f"{latest.decision}:{latest.source}:{latest.kind}"
            if latest.id
            else "none"
        )
        return (
            f"Autonomy decisions: latest={latest_text}; "
            f"continue={report.continue_count}; recover={report.recover_count}; "
            f"wait={report.wait_count}; current={report.current_policy_action}; {report.recommended_action}"
        )

    def _operator_dispatch_line(self, state: RunState) -> str:
        report = state.operator_dispatches
        if not report.generated_at:
            report = state.handoff_summary.operator_dispatches
        if not report.generated_at:
            return "Operator dispatches: none"
        latest = report.entries[0] if report.entries else None
        latest_text = (
            f"{latest.status}:{latest.decision}:{latest.ui_target or latest.action_reason}"
            if latest
            else "none"
        )
        approval_history = (
            report.unresolved_approval_histories[0]
            if report.unresolved_approval_histories
            else report.approval_histories[0]
            if report.approval_histories
            else None
        )
        approval_text = ""
        if approval_history:
            approval_kind = f":kind={approval_history.approval_kind}" if approval_history.approval_kind else ""
            approval_action = f":action={approval_history.action_summary}" if approval_history.action_summary else ""
            approval_text = (
                f" approval_history=approval#{approval_history.approval_id}:latest={approval_history.latest_status}"
                f"{approval_kind}{approval_action}:events={approval_history.event_count}:seq={' -> '.join(approval_history.sequence[:5])};"
            )
        promotion_route = report.promotion_routes[0] if report.promotion_routes else None
        route_text = ""
        if promotion_route:
            route_text = (
                f" promotion_route=event#{promotion_route.event_id}:{promotion_route.action_reason}"
                f"->{promotion_route.ui_target}:approval#{promotion_route.approval_id};"
            )
        promotion_history = (
            report.unresolved_promotion_approval_histories[0]
            if report.unresolved_promotion_approval_histories
            else report.promotion_approval_histories[0]
            if report.promotion_approval_histories
            else None
        )
        promotion_history_text = ""
        if promotion_history:
            promotion_kind = f":kind={promotion_history.approval_kind}" if promotion_history.approval_kind else ""
            promotion_action = f":action={promotion_history.action_summary}" if promotion_history.action_summary else ""
            promotion_history_text = (
                f" promotion_approval_history=approval#{promotion_history.approval_id}:latest={promotion_history.latest_status}"
                f"{promotion_kind}{promotion_action}:events={promotion_history.event_count}:seq={' -> '.join(promotion_history.sequence[:5])};"
            )
        return (
            f"Operator dispatches: latest={latest_text}; dispatched={report.dispatched_count}; "
            f"confirmation_required={report.confirmation_required_count}; reviewed={report.reviewed_count}; "
            f"blocked={report.blocked_count}; approval_histories={report.approval_history_count}; "
            f"unresolved_approval_histories={report.unresolved_approval_history_count}; "
            f"promotion_routes={report.promotion_route_count}; promotion_approval_routes={report.promotion_approval_route_count}; "
            f"promotion_approval_histories={report.promotion_approval_history_count}; "
            f"unresolved_promotion_approval_histories={report.unresolved_promotion_approval_history_count};"
            f"{approval_text}{route_text}{promotion_history_text} {report.recommended_action}"
        )

    def _action_readiness_line(self, state: RunState) -> str:
        report = state.action_readiness
        if not report.run_id:
            return "Action readiness: unknown"
        tool = f"; tool={report.suggested_tool}:{report.suggested_label}" if report.suggested_tool else ""
        return f"Action readiness: {report.status}; ready={report.ready_to_act}; {report.recommended_action}{tool}"

    def _action_readiness_decision_line(self, state: RunState) -> str:
        report = state.action_readiness_decisions
        if not report.run_id:
            return "Action readiness decisions: none"
        latest = report.latest_decision
        latest_text = (
            f"{latest.status}:{latest.source}:{latest.selected_tool or latest.kind}"
            if latest.id
            else "none"
        )
        return (
            f"Action readiness decisions: latest={latest_text}; "
            f"satisfied={report.satisfied_count}; failed={report.failed_count}; {report.recommended_action}"
        )

    def _recovery_decision_line(self, state: RunState) -> str:
        report = state.recovery_decisions
        if not report.run_id:
            return "Recovery decisions: none"
        latest = report.latest_decision
        latest_text = (
            f"{latest.status}:{latest.trigger}:{latest.tool}:{latest.proof_label}"
            if latest.id
            else "none"
        )
        return (
            f"Recovery decisions: latest={latest_text}; active={report.active_recovery}; "
            f"resolved={report.resolved_count}; {report.recommended_action}"
        )


    def _post_action_retry_line(self, state: RunState) -> str:
        report = state.post_action_retries
        if not report.generated_at:
            report = state.handoff_summary.post_action_retries
        if not report.generated_at:
            return "Post-action retries: none"
        latest = report.latest_decision
        latest_text = (
            f"{latest.status}:{latest.trigger_tool}->{latest.selected_tool}"
            if latest.id
            else "none"
        )
        return (
            f"Post-action retries: latest={latest_text}; pending={report.pending_count}; "
            f"resolved={report.resolved_count}; failed={report.failed_count}; {report.recommended_action}"
        )
    def _verification_outcome_line(self, state: RunState) -> str:
        report = state.verification_outcomes
        if not report.run_id:
            return "Verification outcomes: none"
        latest = report.latest_outcome
        latest_text = (
            f"{latest.outcome}:{latest.tool}:{latest.proof_label}"
            if latest.id
            else "none"
        )
        return (
            f"Verification outcomes: latest={latest_text}; recovery_resolved={report.recovery_resolved_count}; "
            f"failed={report.failed_count}; {report.recommended_action}"
        )
