from __future__ import annotations

from datetime import datetime, timezone

from .schemas import (
    CompletionAuditReport,
    ObjectiveReadinessReport,
    OperatorDispatchRestartSmokeLedgerReport,
    OrnithPreflightWarningReport,
    ReadinessCompletionCheck,
    ReadinessCompletionReport,
    ReadinessProofHistoryReport,
    ReadinessRehearsalLedgerReport,
    RunProgressReport,
    RunRecord,
    SelfScaffoldReport,
)
from .goal_classification import is_harness_improvement_goal


REQUIRED_VERIFIED_COUNT = 9
SOURCE_VISIBLE_LABELS = {"web", "browser"}


def build_readiness_completion(
    run: RunRecord,
    objective_readiness: ObjectiveReadinessReport,
    run_progress: RunProgressReport,
    completion_audit: CompletionAuditReport,
    readiness_rehearsal_ledger: ReadinessRehearsalLedgerReport | None = None,
    operator_dispatch_restart_smoke_ledger: OperatorDispatchRestartSmokeLedgerReport | None = None,
    *,
    ornith_preflight_warnings: OrnithPreflightWarningReport | None = None,
    self_scaffold: SelfScaffoldReport | None = None,
    readiness_proof_history: ReadinessProofHistoryReport | None = None,
    require_rehearsal_ledger: bool = False,
    require_dispatch_restart_smoke_ledger: bool = False,
) -> ReadinessCompletionReport:
    if not _is_harness_improvement_goal(run):
        return ReadinessCompletionReport(
            run_id=run.id,
            generated_at=_now(),
            status="not_applicable",
            summary="Readiness completion gate applies only to AgentOrinth/Ornith/Orint/Codex-like harness-improvement runs.",
            objective_status=objective_readiness.status,
            run_progress_status=run_progress.status,
            completion_status=completion_audit.status,
        )

    checks = [
        _objective_check(objective_readiness),
        _completion_check(completion_audit),
        _progress_check(run_progress),
        _proof_preference_check(objective_readiness),
    ]
    if require_rehearsal_ledger or readiness_rehearsal_ledger is not None:
        checks.append(_readiness_rehearsal_check(readiness_rehearsal_ledger))
    if require_dispatch_restart_smoke_ledger or operator_dispatch_restart_smoke_ledger is not None:
        checks.append(_operator_dispatch_restart_smoke_check(operator_dispatch_restart_smoke_ledger))
    if ornith_preflight_warnings is not None:
        checks.append(_ornith_preflight_warning_check(ornith_preflight_warnings))
    if self_scaffold is not None:
        checks.append(_self_scaffold_check(self_scaffold))
    source_visible_required_labels = _source_visible_labels(run, field="required_labels")
    source_visible_matched_labels = _source_visible_labels(run, field="matched_labels")
    source_ref_labels = sorted(set(readiness_proof_history.source_evidence_labels) if readiness_proof_history else set())
    source_visible_labels = sorted(set(source_visible_required_labels) | set(source_visible_matched_labels))
    source_visible_missing_ref_labels = [label for label in source_visible_labels if label not in source_ref_labels]
    if source_visible_labels:
        checks.append(
            _readiness_proof_source_ref_check(
                source_visible_labels,
                source_visible_missing_ref_labels,
                readiness_proof_history,
            )
        )
    blocking = sum(1 for check in checks if check.status == "block")
    warnings = sum(1 for check in checks if check.status == "warn")
    can_claim = blocking == 0 and _objective_ready_enough(objective_readiness)
    status = "ready" if can_claim else "blocked" if blocking else "needs_more_evidence"
    confidence = _confidence(can_claim, warnings, objective_readiness)
    next_actions = [check.next_action for check in checks if check.next_action]

    return ReadinessCompletionReport(
        run_id=run.id,
        generated_at=_now(),
        status=status,
        can_claim_milestone=can_claim,
        confidence=confidence,
        summary=_summary(status, confidence, objective_readiness, completion_audit, run_progress),
        objective_status=objective_readiness.status,
        run_progress_status=run_progress.status,
        completion_status=completion_audit.status,
        rehearsal_ledger_status=readiness_rehearsal_ledger.status if readiness_rehearsal_ledger else "",
        rehearsal_latest_run_id=(
            readiness_rehearsal_ledger.latest.run_id
            if readiness_rehearsal_ledger and readiness_rehearsal_ledger.latest
            else ""
        ),
        rehearsal_passed_count=readiness_rehearsal_ledger.passed_count if readiness_rehearsal_ledger else 0,
        rehearsal_failed_count=readiness_rehearsal_ledger.failed_count if readiness_rehearsal_ledger else 0,
        dispatch_restart_smoke_ledger_status=(
            operator_dispatch_restart_smoke_ledger.status if operator_dispatch_restart_smoke_ledger else ""
        ),
        dispatch_restart_smoke_latest_run_id=(
            operator_dispatch_restart_smoke_ledger.latest.run_id
            if operator_dispatch_restart_smoke_ledger and operator_dispatch_restart_smoke_ledger.latest
            else ""
        ),
        dispatch_restart_smoke_passed_count=(
            operator_dispatch_restart_smoke_ledger.passed_count if operator_dispatch_restart_smoke_ledger else 0
        ),
        dispatch_restart_smoke_failed_count=(
            operator_dispatch_restart_smoke_ledger.failed_count if operator_dispatch_restart_smoke_ledger else 0
        ),
        ornith_preflight_warning_count=ornith_preflight_warnings.warning_count if ornith_preflight_warnings else 0,
        ornith_preflight_block_count=ornith_preflight_warnings.block_count if ornith_preflight_warnings else 0,
        ornith_preflight_reorient_count=(
            ornith_preflight_warnings.action_context_reorient_count if ornith_preflight_warnings else 0
        ),
        self_scaffold_status=self_scaffold.status if self_scaffold else "",
        self_scaffold_pending_review_count=(
            sum(1 for change in self_scaffold.changes if change.status == "needs_review")
            if self_scaffold
            else 0
        ),
        self_scaffold_review_count=self_scaffold.review_count if self_scaffold else 0,
        self_scaffold_reviewed_change_count=self_scaffold.reviewed_change_count if self_scaffold else 0,
        self_scaffold_latest_review_event_id=(
            self_scaffold.latest_review_event_id if self_scaffold else 0
        ),
        source_visible_required_label_count=len(source_visible_required_labels),
        source_visible_matched_label_count=len(source_visible_matched_labels),
        readiness_proof_source_ref_count=(
            readiness_proof_history.source_evidence_ref_count if readiness_proof_history else 0
        ),
        readiness_proof_source_ref_labels=source_ref_labels,
        source_visible_missing_ref_labels=source_visible_missing_ref_labels,
        required_verified_count=REQUIRED_VERIFIED_COUNT,
        verified_count=objective_readiness.verified_count,
        partial_count=objective_readiness.partial_count,
        missing_count=objective_readiness.missing_count,
        failed_count=objective_readiness.failed_count,
        proof_preference_count=len(objective_readiness.proof_preferences),
        open_preference_count=_open_preference_count(objective_readiness),
        blocking_count=blocking,
        warning_count=warnings,
        checks=checks,
        next_actions=list(dict.fromkeys(next_actions))[:8],
    )


def _is_harness_improvement_goal(run: RunRecord) -> bool:
    return is_harness_improvement_goal(run.goal, run.state.goal)


def _objective_check(report: ObjectiveReadinessReport) -> ReadinessCompletionCheck:
    evidence = [
        f"status={report.status}",
        f"verified={report.verified_count}",
        f"partial={report.partial_count}",
        f"missing={report.missing_count}",
        f"failed={report.failed_count}",
    ]
    if _objective_ready_enough(report):
        status = "pass" if report.partial_count == 0 else "warn"
        return ReadinessCompletionCheck(
            id="objective_readiness",
            status=status,
            summary=(
                "Objective readiness has enough verified evidence for a milestone claim."
                if status == "pass"
                else "Objective readiness is ready with one remaining partial item."
            ),
            evidence=evidence,
            next_action=(
                ""
                if status == "pass"
                else "Optionally verify the remaining partial readiness item before claiming high confidence."
            ),
        )
    return ReadinessCompletionCheck(
        id="objective_readiness",
        status="block" if report.failed_count or report.missing_count else "warn",
        summary="Objective readiness does not yet prove enough major harness requirements.",
        evidence=evidence,
        next_action=report.next_actions[0] if report.next_actions else report.recommended_action,
    )


def _completion_check(report: CompletionAuditReport) -> ReadinessCompletionCheck:
    evidence = [
        f"status={report.status}",
        f"can_finish={report.can_finish}",
        f"acceptance={report.acceptance_verified}/{report.acceptance_total}",
        f"pending_approvals={report.pending_approvals}",
        f"blockers={report.blocker_count}",
        f"stale={report.stale_evidence_count}",
    ]
    if not report.can_finish:
        return ReadinessCompletionCheck(
            id="completion_audit",
            status="block",
            summary="Completion audit still has blockers.",
            evidence=evidence,
            next_action=report.next_actions[0] if report.next_actions else "Resolve completion audit blockers.",
        )
    if report.acceptance_total == 0:
        return ReadinessCompletionCheck(
            id="completion_audit",
            status="warn",
            summary="Completion audit has no ordinary acceptance criteria; readiness evidence is carrying the milestone proof.",
            evidence=evidence,
            next_action="Add acceptance criteria for stronger non-meta completion proof when appropriate.",
        )
    return ReadinessCompletionCheck(
        id="completion_audit",
        status="pass",
        summary="Completion audit has no blockers.",
        evidence=evidence,
    )


def _progress_check(report: RunProgressReport) -> ReadinessCompletionCheck:
    evidence = [
        f"status={report.status}",
        f"can_keep_running={report.can_keep_running}",
        f"should_pause={report.should_pause}",
        f"policy={report.current_policy_action}",
        f"pending_approvals={report.pending_approval_count}",
    ]
    if report.status in {"needs_recovery", "waiting", "blocked"} or report.should_pause:
        return ReadinessCompletionCheck(
            id="run_progress",
            status="block",
            summary="Run progress is not in a claimable state.",
            evidence=evidence,
            next_action=report.next_actions[0] if report.next_actions else "Resume progress before claiming readiness.",
        )
    if report.status == "needs_verification":
        return ReadinessCompletionCheck(
            id="run_progress",
            status="block",
            summary="Run progress still needs verification.",
            evidence=evidence,
            next_action=report.next_actions[0] if report.next_actions else "Run focused verification before claiming readiness.",
        )
    return ReadinessCompletionCheck(
        id="run_progress",
        status="pass",
        summary="Run progress is stable enough for a readiness claim.",
        evidence=evidence,
    )


def _proof_preference_check(report: ObjectiveReadinessReport) -> ReadinessCompletionCheck:
    open_items = [
        item
        for item in report.items
        if item.status != "verified" and (item.preferred_proof.tool_kind or item.preferred_proof.strategy)
    ]
    if not open_items:
        return ReadinessCompletionCheck(
            id="proof_preferences",
            status="pass",
            summary="No open proof preferences remain for unverified readiness items.",
            evidence=[f"preferences={len(report.proof_preferences)}"],
        )
    failed = [item for item in open_items if item.latest_outcome.outcome == "failed"]
    partial = [item for item in open_items if item.latest_outcome.outcome == "partial"]
    status = "block" if failed else "warn"
    first = failed[0] if failed else partial[0] if partial else open_items[0]
    return ReadinessCompletionCheck(
        id="proof_preferences",
        status=status,
        summary="Open proof preferences still point to readiness evidence that needs follow-up.",
        evidence=[
            f"{item.id}:{item.status}:{item.preferred_proof.tool_kind}/{item.preferred_proof.strategy}:{item.latest_outcome.outcome}"
            for item in open_items[:6]
        ],
        next_action=first.next_action or first.preferred_proof.action,
    )


def _readiness_rehearsal_check(
    ledger: ReadinessRehearsalLedgerReport | None,
) -> ReadinessCompletionCheck:
    if ledger is None or ledger.latest is None or ledger.status == "never_run":
        return ReadinessCompletionCheck(
            id="readiness_rehearsal",
            status="block",
            summary="No cross-run readiness rehearsal has passed.",
            evidence=["status=never_run"],
            next_action="Run the readiness-claim smoke rehearsal before claiming Codex-like harness readiness.",
        )
    latest = ledger.latest
    evidence = [
        f"ledger={ledger.status}",
        f"latest={latest.run_id}:{latest.status}",
        f"restart={latest.restart_simulated}",
        f"replay={latest.replay_attached}",
        f"handoff={latest.handoff_attached}",
        f"events=refused:{latest.refused_event_id}/accepted:{latest.accepted_event_id}/completed:{latest.completed_event_id}",
        f"self_scaffold_reviewed={latest.self_scaffold_reviewed}",
        f"self_scaffold_review_event={latest.self_scaffold_review_event_id or 'none'}",
        f"self_scaffold_reviewed_changes={latest.self_scaffold_reviewed_change_count}",
        f"post_review_handoff_goal={latest.post_review_handoff_goal_preserved}",
        f"post_review_handoff_next={latest.post_review_handoff_next_action_preserved}",
        f"post_review_resume_goal={latest.post_review_resume_prompt_goal_preserved}",
        f"post_review_resume_next={latest.post_review_resume_prompt_next_action_preserved}",
        f"steps={latest.passed_steps}/{latest.step_count}",
        f"history=passed:{ledger.passed_count}/failed:{ledger.failed_count}/running:{ledger.running_count}",
    ]
    if latest.status == "running":
        return ReadinessCompletionCheck(
            id="readiness_rehearsal",
            status="block",
            summary="Latest readiness rehearsal is still running.",
            evidence=evidence,
            next_action=ledger.next_action,
        )
    if latest.status == "failed":
        return ReadinessCompletionCheck(
            id="readiness_rehearsal",
            status="block",
            summary="Latest readiness rehearsal failed.",
            evidence=evidence,
            next_action=latest.next_action or ledger.next_action,
        )
    if not (
        latest.restart_simulated
        and latest.replay_attached
        and latest.handoff_attached
        and latest.refused_event_id
        and latest.accepted_event_id
        and latest.completed_event_id
        and latest.self_scaffold_reviewed
        and latest.self_scaffold_review_event_id
        and latest.self_scaffold_reviewed_change_count > 0
        and latest.post_review_handoff_goal_preserved
        and latest.post_review_handoff_next_action_preserved
        and latest.post_review_resume_prompt_goal_preserved
        and latest.post_review_resume_prompt_next_action_preserved
        and latest.step_count
        and latest.passed_steps == latest.step_count
    ):
        return ReadinessCompletionCheck(
            id="readiness_rehearsal",
            status="block",
            summary="Latest readiness rehearsal is incomplete.",
            evidence=evidence,
            next_action="Rerun the readiness-claim smoke rehearsal so it proves self-scaffold review plus post-review handoff goal/next-action preservation.",
        )
    if ledger.failed_count:
        return ReadinessCompletionCheck(
            id="readiness_rehearsal",
            status="warn",
            summary="Latest readiness rehearsal passed, but recent rehearsal history includes failures.",
            evidence=evidence,
            next_action="Compare the latest passed rehearsal with recent failed smoke evidence before claiming high confidence.",
        )
    return ReadinessCompletionCheck(
        id="readiness_rehearsal",
        status="pass",
        summary="Latest readiness rehearsal passed with restart, self-scaffold review, post-review handoff, replay, and handoff evidence.",
        evidence=evidence,
    )


def _operator_dispatch_restart_smoke_check(
    ledger: OperatorDispatchRestartSmokeLedgerReport | None,
) -> ReadinessCompletionCheck:
    if ledger is None or ledger.latest is None or ledger.status == "never_run":
        return ReadinessCompletionCheck(
            id="operator_dispatch_restart_smoke",
            status="block",
            summary="No cross-run operator-dispatch restart smoke has passed.",
            evidence=["status=never_run"],
            next_action="Run the operator-dispatch restart smoke before claiming Codex-like harness readiness.",
        )
    latest = ledger.latest
    evidence = [
        f"ledger={ledger.status}",
        f"latest={latest.run_id}:{latest.status}",
        f"restart={latest.restart_simulated}",
        f"dispatch_event={latest.dispatch_event_id}",
        f"ledger_attached={latest.ledger_attached}",
        f"handoff={latest.handoff_attached}",
        f"replay={latest.replay_attached}",
        f"context={latest.context_attached}",
        f"steps={latest.passed_steps}/{latest.step_count}",
        f"history=passed:{ledger.passed_count}/failed:{ledger.failed_count}/running:{ledger.running_count}",
    ]
    if latest.status == "running":
        return ReadinessCompletionCheck(
            id="operator_dispatch_restart_smoke",
            status="block",
            summary="Latest operator-dispatch restart smoke is still running.",
            evidence=evidence,
            next_action=ledger.next_action,
        )
    if latest.status == "failed":
        return ReadinessCompletionCheck(
            id="operator_dispatch_restart_smoke",
            status="block",
            summary="Latest operator-dispatch restart smoke failed.",
            evidence=evidence,
            next_action=latest.next_action or ledger.next_action,
        )
    if not (
        latest.restart_simulated
        and latest.dispatch_event_id
        and latest.ledger_attached
        and latest.handoff_attached
        and latest.replay_attached
        and latest.context_attached
        and latest.step_count
        and latest.passed_steps == latest.step_count
    ):
        return ReadinessCompletionCheck(
            id="operator_dispatch_restart_smoke",
            status="block",
            summary="Latest operator-dispatch restart smoke is incomplete.",
            evidence=evidence,
            next_action="Rerun the operator-dispatch restart smoke and inspect any failed step.",
        )
    if ledger.failed_count:
        return ReadinessCompletionCheck(
            id="operator_dispatch_restart_smoke",
            status="warn",
            summary="Latest operator-dispatch restart smoke passed, but recent smoke history includes failures.",
            evidence=evidence,
            next_action="Compare the latest passed dispatch restart smoke with recent failed smoke evidence before claiming high confidence.",
        )
    return ReadinessCompletionCheck(
        id="operator_dispatch_restart_smoke",
        status="pass",
        summary="Latest operator-dispatch restart smoke passed with dispatch, handoff, replay, and compact context evidence.",
        evidence=evidence,
    )


def _ornith_preflight_warning_check(report: OrnithPreflightWarningReport) -> ReadinessCompletionCheck:
    evidence = [
        f"warnings={report.warning_count}",
        f"blocks={report.block_count}",
        f"action_context_reorients={report.action_context_reorient_count}",
        f"latest_reorient_event={report.latest_reorient_event_id or 'none'}",
    ]
    if report.latest_warning:
        evidence.append(f"latest={report.latest_warning}")
    if report.entries:
        evidence.extend(report.entries[-1].evidence[:4])
    if report.total_count == 0:
        return ReadinessCompletionCheck(
            id="ornith_preflight_warnings",
            status="pass",
            summary="Ornith preflight warning history is clean.",
            evidence=evidence,
        )
    return ReadinessCompletionCheck(
        id="ornith_preflight_warnings",
        status="block",
        summary="Ornith preflight warning history is dirty; refresh/reorient before claiming long-run readiness.",
        evidence=evidence,
        next_action=report.recommended_action or "Refresh Ornith preflight and handoff action context before claiming readiness.",
    )

def _self_scaffold_check(report: SelfScaffoldReport) -> ReadinessCompletionCheck:
    pending = [change for change in report.changes if change.status == "needs_review"]
    evidence = [
        f"status={report.status}",
        f"changes={report.change_count}",
        f"pending={len(pending)}",
        f"guards={report.guard_count}",
        f"reviewed={report.reviewed_change_count}",
        f"reviews={report.review_count}",
        f"latest_review_event={report.latest_review_event_id or 'none'}",
    ]
    if report.latest_change:
        evidence.append(f"latest={report.latest_change}")
    evidence.extend(f"pending:{change.kind}:{change.id}" for change in pending[:4])
    if not pending and report.status in {"empty", "observed"}:
        return ReadinessCompletionCheck(
            id="self_scaffold_review",
            status="pass",
            summary="Self-scaffold change-intent ledger has no unresolved review items.",
            evidence=evidence,
        )
    return ReadinessCompletionCheck(
        id="self_scaffold_review",
        status="block",
        summary="Self-scaffold change-intent ledger has unresolved review items.",
        evidence=evidence,
        next_action=report.recommended_action or "Review self-scaffold change intent before claiming long-run readiness.",
    )
def _source_visible_labels(run: RunRecord, *, field: str) -> list[str]:
    labels: set[str] = set()
    for item in run.state.acceptance_evidence:
        for label in getattr(item, field, []) or []:
            if label in SOURCE_VISIBLE_LABELS:
                labels.add(label)
    return sorted(labels)


def _readiness_proof_source_ref_check(
    source_visible_labels: list[str],
    missing_ref_labels: list[str],
    history: ReadinessProofHistoryReport | None,
) -> ReadinessCompletionCheck:
    source_ref_count = history.source_evidence_ref_count if history else 0
    source_ref_labels = sorted(set(history.source_evidence_labels) if history else set())
    evidence = [
        f"source_visible_labels={','.join(source_visible_labels) if source_visible_labels else 'none'}",
        f"source_refs={source_ref_count}",
        f"source_ref_labels={','.join(source_ref_labels) if source_ref_labels else 'none'}",
        f"missing_ref_labels={','.join(missing_ref_labels) if missing_ref_labels else 'none'}",
    ]
    if history and history.latest_summary:
        evidence.append(f"latest={history.latest_summary}")
    if history and history.source_evidence_summary:
        evidence.append(history.source_evidence_summary)
    if not history or not history.generated_at:
        return ReadinessCompletionCheck(
            id="readiness_proof_source_refs",
            status="block",
            summary="Source-visible criteria need compact source refs in readiness proof history before a readiness claim.",
            evidence=evidence,
            next_action="Refresh readiness proof history after capturing web/browser source evidence before claiming readiness.",
        )
    if source_ref_count <= 0 or missing_ref_labels:
        return ReadinessCompletionCheck(
            id="readiness_proof_source_refs",
            status="block",
            summary="Readiness proof history is missing source refs for source-visible criteria.",
            evidence=evidence,
            next_action="Link compact web/browser source evidence to readiness proof history before claiming readiness.",
        )
    return ReadinessCompletionCheck(
        id="readiness_proof_source_refs",
        status="pass",
        summary="Readiness proof history links compact source refs for source-visible criteria.",
        evidence=evidence,
    )


def _objective_ready_enough(report: ObjectiveReadinessReport) -> bool:
    return (
        report.status == "ready"
        and report.verified_count >= REQUIRED_VERIFIED_COUNT
        and report.failed_count == 0
        and report.missing_count == 0
        and report.partial_count <= 1
    )


def _open_preference_count(report: ObjectiveReadinessReport) -> int:
    return sum(
        1
        for item in report.items
        if item.status != "verified" and (item.preferred_proof.tool_kind or item.preferred_proof.strategy)
    )


def _confidence(can_claim: bool, warnings: int, report: ObjectiveReadinessReport) -> str:
    if not can_claim:
        return "low"
    if warnings == 0 and report.verified_count == len(report.items):
        return "high"
    return "medium"


def _summary(
    status: str,
    confidence: str,
    objective_readiness: ObjectiveReadinessReport,
    completion_audit: CompletionAuditReport,
    run_progress: RunProgressReport,
) -> str:
    if status == "ready":
        return (
            f"Ready to claim readiness milestone with {confidence} confidence: "
            f"{objective_readiness.verified_count}/{len(objective_readiness.items)} readiness items verified, "
            f"completion={completion_audit.status}, progress={run_progress.status}."
        )
    if status == "blocked":
        return (
            f"Blocked from claiming readiness milestone: objective={objective_readiness.status}, "
            f"completion={completion_audit.status}, progress={run_progress.status}."
        )
    return (
        f"Needs more readiness evidence before claim: objective={objective_readiness.status}, "
        f"completion={completion_audit.status}, progress={run_progress.status}."
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
