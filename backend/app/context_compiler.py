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


class ContextCompiler:
    def __init__(self, target_tokens: int, profile: ModelProfile = GENERIC_PROFILE) -> None:
        self.target_tokens = target_tokens
        self.profile = profile

    def compile(self, run: RunRecord, state: RunState, memory: MemoryContext, latest_events: list[dict]) -> tuple[str, ContextSnapshot]:
        sections: list[tuple[str, str]] = [
            ("goal", self._goal_section(run, state)),
            ("model_profile", self.profile.summary),
            ("handoff", state.handoff_summary.model_dump_json(exclude_defaults=True)[: self.profile.handoff_chars]),
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
            ("source_evidence", self._source_evidence_line(state)),
            ("action_context", self._action_context_line(state)),
            ("run_health", state.run_health.model_dump_json()),
            ("ornith_preflight", self._ornith_preflight_line(state)),
            ("ornith_preflight_actions", self._ornith_preflight_action_line(state)),
            ("run_progress", self._run_progress_line(state)),
            ("report_integrity", self._report_integrity_line(state)),
            ("objective_readiness", self._objective_readiness_line(state)),
            ("resume_decisions", state.handoff_summary.resume_decisions.model_dump_json()),
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
        for name, body in sections:
            candidate = f"## {name}\n{body.strip()}"
            if estimate_tokens("\n\n".join(selected + [candidate])) > self.target_tokens:
                continue
            selected.append(candidate)
            selected_names.append(name)
        prompt = "\n\n".join(selected)
        snapshot = ContextSnapshot(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            estimated_tokens=estimate_tokens(prompt),
            sections=selected_names,
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
                "Next evidence actions: " + "; ".join(
                    f"{item.criterion} -> {item.tool_kind}:{item.action}"
                    for item in state.acceptance_recommendations[:5]
                ),
                "Evidence action traces: " + "; ".join(
                    f"{item.status}:{item.label}:{item.selected_tool}"
                    for item in state.acceptance_recommendation_traces[-5:]
                ),
                self._source_evidence_line(state),
                self._action_context_line(state),
                f"Run health: {state.run_health.level}:{state.run_health.recommended_action}:{state.run_health.score}",
                self._ornith_preflight_line(state),
                self._ornith_preflight_action_line(state),
                self._run_progress_line(state),
                self._report_integrity_line(state),
                self._objective_readiness_line(state),
                self._readiness_completion_line(state),
                self._readiness_rehearsal_line(state),
                self._resume_decision_line(state),
                self._autonomy_decision_line(state),
                self._operator_dispatch_line(state),
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


    def _acceptance_line(self, item: object) -> str:
        required = getattr(item, "required_labels", [])
        matched = getattr(item, "matched_labels", [])
        progress = compact_label_progress(required, matched)
        suffix = f"[{progress}]" if progress else ""
        return f"{getattr(item, 'status', 'open')}:{getattr(item, 'criterion', '')}{suffix}"


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
        return (
            f"Report integrity: {report.status}; ok={report.ok_count}/{report.check_count}; "
            f"missing={report.missing_count}; stale={report.stale_count}; mismatch={report.mismatch_count}; "
            f"{report.recommended_action}"
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
            f"blockers={report.blocking_count}; warnings={report.warning_count}; {report.summary}"
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
        return (
            f"Operator dispatches: latest={latest_text}; dispatched={report.dispatched_count}; "
            f"confirmation_required={report.confirmation_required_count}; reviewed={report.reviewed_count}; "
            f"blocked={report.blocked_count}; {report.recommended_action}"
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
