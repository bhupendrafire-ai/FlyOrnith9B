from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .approval_reviews import approval_review_event_index, approval_review_label_from_record
from .desktop_effect_proof import build_desktop_effect_proof_preview
from .operator_dispatches import build_operator_dispatch_ledger
from .schemas import HandoffBundle, ReportIntegrityCheck, ReportIntegrityRefreshRecord, ReportIntegrityReport, RunRecord


REPORT_SECTIONS = (
    "completion_audit",
    "run_health",
    "policy_simulation",
    "resume_decisions",
    "resume_prompt_quality",
    "resume_handoff_diff",
    "promotion_verification",
    "promotion_repair",
    "run_progress",
    "context_snapshot",
    "ornith_preflight",
    "action_readiness",
    "action_readiness_decisions",
    "autonomy_decisions",
    "recovery_decisions",
    "verification_outcomes",
)


def build_report_integrity(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    handoff: HandoffBundle | None = None,
    approvals: list[dict[str, Any]] | None = None,
) -> ReportIntegrityReport:
    inspected_handoff = handoff or run.state.handoff_summary
    approval_review_index = approval_review_event_index(events)
    checks: list[ReportIntegrityCheck] = [
        _text_check("handoff.current_objective", run.state.goal, inspected_handoff.current_objective),
        _text_check("handoff.next_action", run.state.next_step, inspected_handoff.next_action),
        _presence_check("handoff.resume_prompt", inspected_handoff.resume_prompt),
    ]
    checks.extend(_section_check(run, inspected_handoff, section) for section in REPORT_SECTIONS)
    checks.extend(_consistency_checks(run, inspected_handoff))
    checks.extend(_approval_review_checks(inspected_handoff, approvals, approval_review_index))
    checks.extend(_operator_dispatch_checks(run, inspected_handoff, events, approvals))
    checks.extend(_desktop_effect_proof_checks(run, inspected_handoff))
    latest_event = events[-1] if events else {}
    missing_count = sum(1 for item in checks if item.status == "missing")
    stale_count = sum(1 for item in checks if item.status == "stale")
    mismatch_count = sum(1 for item in checks if item.status == "mismatch")
    status = "needs_refresh" if missing_count or stale_count or mismatch_count else "ok"
    return ReportIntegrityReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status=status,
        check_count=len(checks),
        ok_count=sum(1 for item in checks if item.status == "ok"),
        missing_count=missing_count,
        stale_count=stale_count,
        mismatch_count=mismatch_count,
        latest_event_id=int(latest_event.get("id") or 0),
        latest_event_timestamp=str(latest_event.get("timestamp") or ""),
        summary=_summary(status, missing_count, stale_count, mismatch_count),
        recommended_action=_recommended_action(status),
        checks=checks,
    )


RESUME_PREFLIGHT_EVENT_KINDS = {"resume_preflight", "resume_preflight_blocked"}


def build_report_integrity_refreshes(
    events: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[ReportIntegrityRefreshRecord]:
    records: list[ReportIntegrityRefreshRecord] = []
    pending: list[ReportIntegrityRefreshRecord] = []
    for event in sorted(events, key=lambda item: int(item.get("id") or 0)):
        kind = str(event.get("kind") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if kind == "report_integrity_refresh":
            reasons = _refresh_reasons_from_data(data)
            record = ReportIntegrityRefreshRecord(
                event_id=int(event.get("id") or 0),
                timestamp=str(event.get("timestamp") or ""),
                report_status=_report_status(data.get("report_integrity")),
                previous_report_status=_report_status(data.get("previous_report_integrity")),
                reason_count=int(data.get("refresh_reason_count") or len(reasons)),
                reasons=reasons[:8],
            )
            records.append(record)
            pending.append(record)
            continue
        if kind not in RESUME_PREFLIGHT_EVENT_KINDS or not pending:
            continue
        preflight_reasons = _string_items(data.get("report_integrity_refresh_reasons"))
        if not bool(data.get("report_integrity_refreshed")) and not preflight_reasons:
            continue
        for record in reversed(pending):
            if record.preflight_event_id:
                continue
            if preflight_reasons and record.reasons and preflight_reasons != record.reasons:
                continue
            record.preflight_event_id = int(event.get("id") or 0)
            record.preflight_event_kind = kind
            record.preflight_accepted = bool(data.get("accepted")) if "accepted" in data else None
            record.preflight_reason = _compact_refresh_text(str(data.get("reason") or ""), 240)
            break
    bounded = max(1, min(limit, 50))
    return list(reversed(records[-bounded:]))


def _refresh_reasons_from_data(data: dict[str, Any]) -> list[str]:
    reasons = _string_items(data.get("report_integrity_refresh_reasons"))
    if reasons:
        return reasons[:8]
    source = data.get("previous_report_integrity")
    if not isinstance(source, dict):
        source = data.get("report_integrity")
    checks = source.get("checks") if isinstance(source, dict) else []
    derived: list[str] = []
    if not isinstance(checks, list):
        return derived
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "")
        if status == "ok":
            continue
        section = _compact_refresh_text(str(check.get("section") or ""), 120)
        expected = _compact_refresh_text(str(check.get("expected") or ""), 120)
        actual = _compact_refresh_text(str(check.get("actual") or ""), 120)
        summary = _compact_refresh_text(str(check.get("summary") or ""), 180)
        parts = [f"{status}:{section}"]
        if expected or actual:
            parts.append(f"expected={expected or '<empty>'}")
            parts.append(f"actual={actual or '<empty>'}")
        if summary:
            parts.append(summary)
        derived.append(" | ".join(parts))
        if len(derived) >= 8:
            break
    return derived


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_compact_refresh_text(str(item), 260) for item in value[:8] if str(item).strip()]


def _report_status(value: Any) -> str:
    return str(value.get("status") or "") if isinstance(value, dict) else ""


def _compact_refresh_text(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."
def _section_check(run: RunRecord, handoff: HandoffBundle, section: str) -> ReportIntegrityCheck:
    value = getattr(handoff, section, None)
    if value is None:
        return ReportIntegrityCheck(
            section=section,
            status="missing",
            summary=f"{section} is missing from the handoff bundle.",
        )
    run_id = str(getattr(value, "run_id", "") or "")
    generated_at = str(getattr(value, "generated_at", "") or "")
    if not run_id:
        return ReportIntegrityCheck(
            section=section,
            status="missing",
            summary=f"{section} has not been generated for this run.",
            expected=run.id,
            actual=run_id,
            generated_at=generated_at,
        )
    if run_id != run.id:
        return ReportIntegrityCheck(
            section=section,
            status="mismatch",
            summary=f"{section} belongs to a different run.",
            expected=run.id,
            actual=run_id,
            generated_at=generated_at,
        )
    if not generated_at:
        return ReportIntegrityCheck(
            section=section,
            status="missing",
            summary=f"{section} is missing a generated_at timestamp.",
            expected="generated_at",
            actual="",
            generated_at=generated_at,
        )
    return ReportIntegrityCheck(
        section=section,
        status="ok",
        summary=f"{section} is present for this run.",
        expected=run.id,
        actual=run_id,
        generated_at=generated_at,
    )


def _consistency_checks(run: RunRecord, handoff: HandoffBundle) -> list[ReportIntegrityCheck]:
    policy = handoff.policy_simulation
    progress = handoff.run_progress
    resume = handoff.resume_decisions
    autonomy = handoff.autonomy_decisions
    checks = [
        _text_check("policy_simulation.current_status", run.status, policy.current_status),
        _text_check("policy_simulation.current_milestone", run.state.milestone, policy.current_milestone),
        _text_check("run_progress.current_policy_action", policy.policy_action, progress.current_policy_action),
        _text_check("resume_decisions.current_policy_action", policy.policy_action, resume.current_policy_action),
        _text_check("autonomy_decisions.current_policy_action", policy.policy_action, autonomy.current_policy_action),
        _number_check("run_progress.acceptance_total", len(run.state.acceptance_criteria), progress.acceptance_total),
    ]
    if handoff.action_readiness.run_id and handoff.action_readiness.milestone:
        checks.append(
            _text_check("action_readiness.milestone", run.state.milestone, handoff.action_readiness.milestone)
        )
    return checks


def _approval_review_checks(
    handoff: HandoffBundle,
    approvals: list[dict[str, Any]] | None,
    review_index: dict[int, dict[str, Any]],
) -> list[ReportIntegrityCheck]:
    checks: list[ReportIntegrityCheck] = []
    pending = [
        approval
        for approval in (approvals or [])
        if str(approval.get("status") or "") == "pending"
    ]
    pending_by_id = {int(approval.get("id") or 0): approval for approval in pending}
    pending_ids = sorted(pending_by_id)
    pending_reviews = [review for review in handoff.approval_reviews if review.status == "pending"]
    review_ids = sorted(review.id for review in pending_reviews)
    label_count = sum(1 for label in handoff.approvals if ":pending" in label)

    if approvals is not None:
        if pending_ids and not review_ids:
            checks.append(
                ReportIntegrityCheck(
                    section="handoff.approval_reviews",
                    status="missing",
                    summary="Pending approvals exist but structured approval-review summaries are missing from handoff.",
                    expected=",".join(str(item) for item in pending_ids),
                    actual="",
                )
            )
        else:
            checks.append(
                _list_check(
                    "handoff.approval_reviews",
                    pending_ids,
                    review_ids,
                    ok_summary="Structured approval-review summaries match pending approvals.",
                    bad_summary="Structured approval-review summaries do not match pending approvals.",
                )
            )
        checks.append(_number_check("handoff.approvals.pending_count", len(pending_ids), label_count))
        expected_review_counts = {
            approval_id: int(review_index.get(approval_id, {}).get("review_count") or 0)
            for approval_id in pending_ids
        }
        actual_review_counts = {review.id: review.review_count for review in pending_reviews}
        checks.append(
            _mapping_check(
                "handoff.approval_reviews.review_count",
                expected_review_counts,
                actual_review_counts,
            )
        )
        expected_latest_events = {
            approval_id: int(review_index.get(approval_id, {}).get("latest_review_event_id") or 0)
            for approval_id in pending_ids
        }
        actual_latest_events = {review.id: review.latest_review_event_id for review in pending_reviews}
        checks.append(
            _mapping_check(
                "handoff.approval_reviews.latest_review_event_id",
                expected_latest_events,
                actual_latest_events,
            )
        )
        expected_labels = sorted(
            approval_review_label_from_record(approval, review_index.get(approval_id, {}))
            for approval_id, approval in pending_by_id.items()
        )
        checks.append(_string_list_check("handoff.approvals", expected_labels, sorted(handoff.approvals)))
    elif handoff.approvals and not handoff.approval_reviews:
        checks.append(
            ReportIntegrityCheck(
                section="handoff.approval_reviews",
                status="missing",
                summary="Legacy pending approval labels exist without structured approval-review summaries.",
                expected=str(label_count),
                actual="0",
            )
        )

    if handoff.approval_reviews:
        reviewed_labels = sum(1 for label in handoff.approvals if ":reviewed" in label)
        unreviewed_labels = sum(1 for label in handoff.approvals if ":unreviewed" in label)
        reviewed_summaries = sum(1 for review in pending_reviews if review.reviewed)
        unreviewed_summaries = sum(1 for review in pending_reviews if not review.reviewed)
        checks.append(_number_check("handoff.approval_labels.reviewed_count", reviewed_summaries, reviewed_labels))
        checks.append(_number_check("handoff.approval_labels.unreviewed_count", unreviewed_summaries, unreviewed_labels))
    return checks




def _desktop_effect_proof_checks(run: RunRecord, handoff: HandoffBundle) -> list[ReportIntegrityCheck]:
    current = build_desktop_effect_proof_preview(run, limit=8)
    report = handoff.desktop_effect_proof
    if not report.run_id:
        return [
            ReportIntegrityCheck(
                section="handoff.desktop_effect_proof",
                status="missing",
                summary="Desktop effect proof preview is missing from handoff.",
                expected=current.status,
                actual="",
            )
        ]
    if report.run_id != run.id:
        return [
            ReportIntegrityCheck(
                section="handoff.desktop_effect_proof",
                status="mismatch",
                summary="Desktop effect proof preview belongs to a different run.",
                expected=run.id,
                actual=report.run_id,
                generated_at=report.generated_at,
            )
        ]
    checks = [
        _presence_check("handoff.desktop_effect_proof.generated_at", report.generated_at),
        _text_check("handoff.desktop_effect_proof.status", current.status, report.status),
        _text_check("handoff.desktop_effect_proof.latest_action_id", current.latest_action_id, report.latest_action_id),
        _text_check("handoff.desktop_effect_proof.proof_call_id", current.proof_call_id, report.proof_call_id),
        _text_check(
            "handoff.desktop_effect_proof.proof_snapshot_id",
            current.proof_snapshot.id if current.proof_snapshot else "",
            report.proof_snapshot.id if report.proof_snapshot else "",
        ),
        _number_check(
            "handoff.desktop_effect_proof.proof_snapshot_count",
            current.proof_snapshot_count,
            report.proof_snapshot_count,
        ),
    ]
    return checks

PROMOTION_APPROVAL_KINDS = {"patch_apply", "workspace_promote"}


def _operator_dispatch_checks(
    run: RunRecord,
    handoff: HandoffBundle,
    events: list[dict[str, Any]],
    approvals: list[dict[str, Any]] | None,
) -> list[ReportIntegrityCheck]:
    current = build_operator_dispatch_ledger(events, run_id=run.id, limit=100)
    handoff_report = handoff.operator_dispatches
    checks = [
        _number_check(
            "handoff.operator_dispatches.promotion_route_count",
            current.promotion_route_count,
            handoff_report.promotion_route_count,
        ),
        _number_check(
            "handoff.operator_dispatches.promotion_approval_route_count",
            current.promotion_approval_route_count,
            handoff_report.promotion_approval_route_count,
        ),
        _number_check(
            "handoff.operator_dispatches.promotion_approval_history_count",
            current.promotion_approval_history_count,
            handoff_report.promotion_approval_history_count,
        ),
        _number_check(
            "handoff.operator_dispatches.unresolved_promotion_approval_history_count",
            current.unresolved_promotion_approval_history_count,
            handoff_report.unresolved_promotion_approval_history_count,
        ),
        _list_check(
            "handoff.operator_dispatches.promotion_approval_history_ids",
            sorted(history.approval_id for history in current.promotion_approval_histories),
            sorted(history.approval_id for history in handoff_report.promotion_approval_histories),
            ok_summary="Promotion approval route histories match current operator dispatch events.",
            bad_summary="Promotion approval route histories do not match current operator dispatch events.",
        ),
        _list_check(
            "handoff.operator_dispatches.unresolved_promotion_approval_ids",
            sorted(history.approval_id for history in current.unresolved_promotion_approval_histories),
            sorted(history.approval_id for history in handoff_report.unresolved_promotion_approval_histories),
            ok_summary="Unresolved promotion approval route histories match current operator dispatch events.",
            bad_summary="Unresolved promotion approval route histories do not match current operator dispatch events.",
        ),
    ]
    if approvals is not None:
        pending_promotion_ids = {
            int(approval.get("id") or 0)
            for approval in approvals
            if str(approval.get("status") or "") == "pending"
            and str(approval.get("action_kind") or "") in PROMOTION_APPROVAL_KINDS
        }
        routed_ids = {history.approval_id for history in current.promotion_approval_histories}
        expected_unresolved_ids = sorted(pending_promotion_ids & routed_ids)
        actual_unresolved_ids = sorted(
            history.approval_id for history in handoff_report.unresolved_promotion_approval_histories
        )
        checks.append(
            _list_check(
                "handoff.operator_dispatches.pending_promotion_route_ids",
                expected_unresolved_ids,
                actual_unresolved_ids,
                ok_summary="Pending routed promotion approvals match unresolved promotion approval histories.",
                bad_summary="Pending routed promotion approvals do not match unresolved promotion approval histories.",
            )
        )
    return checks


def _mapping_check(
    section: str,
    expected_items: dict[int, int],
    actual_items: dict[int, int],
) -> ReportIntegrityCheck:
    status = "ok" if expected_items == actual_items else "stale"
    return ReportIntegrityCheck(
        section=section,
        status=status,  # type: ignore[arg-type]
        summary=(
            f"{section} matches current review events."
            if status == "ok"
            else f"{section} does not match current review events."
        ),
        expected=_format_mapping(expected_items),
        actual=_format_mapping(actual_items),
    )


def _format_mapping(items: dict[int, int]) -> str:
    return ",".join(f"{key}:{items[key]}" for key in sorted(items))


def _string_list_check(section: str, expected_items: list[str], actual_items: list[str]) -> ReportIntegrityCheck:
    status = "ok" if expected_items == actual_items else "mismatch"
    return ReportIntegrityCheck(
        section=section,
        status=status,  # type: ignore[arg-type]
        summary=(
            f"{section} matches current pending approval labels."
            if status == "ok"
            else f"{section} does not match current pending approval labels."
        ),
        expected=";".join(expected_items),
        actual=";".join(actual_items),
    )


def _list_check(
    section: str,
    expected_items: list[int],
    actual_items: list[int],
    *,
    ok_summary: str,
    bad_summary: str,
) -> ReportIntegrityCheck:
    status = "ok" if expected_items == actual_items else "mismatch"
    return ReportIntegrityCheck(
        section=section,
        status=status,  # type: ignore[arg-type]
        summary=ok_summary if status == "ok" else bad_summary,
        expected=",".join(str(item) for item in expected_items),
        actual=",".join(str(item) for item in actual_items),
    )


def _text_check(section: str, expected: str, actual: str) -> ReportIntegrityCheck:
    status = "ok" if expected == actual else "stale"
    return ReportIntegrityCheck(
        section=section,
        status=status,  # type: ignore[arg-type]
        summary=(
            f"{section} matches current state."
            if status == "ok"
            else f"{section} does not match current state."
        ),
        expected=expected,
        actual=actual,
    )


def _number_check(section: str, expected: int, actual: int) -> ReportIntegrityCheck:
    status = "ok" if expected == actual else "stale"
    return ReportIntegrityCheck(
        section=section,
        status=status,  # type: ignore[arg-type]
        summary=(
            f"{section} matches current state."
            if status == "ok"
            else f"{section} does not match current state."
        ),
        expected=str(expected),
        actual=str(actual),
    )


def _presence_check(section: str, value: str) -> ReportIntegrityCheck:
    if value:
        return ReportIntegrityCheck(section=section, status="ok", summary=f"{section} is present.")
    return ReportIntegrityCheck(section=section, status="missing", summary=f"{section} is missing.")


def _summary(status: str, missing_count: int, stale_count: int, mismatch_count: int) -> str:
    if status == "ok":
        return "Handoff and replay report index is complete and aligned with current run state."
    return (
        "Handoff/replay report index needs refresh: "
        f"{missing_count} missing, {stale_count} stale, {mismatch_count} mismatched."
    )


def _recommended_action(status: str) -> str:
    if status == "ok":
        return "Resume from the current compact handoff."
    return "Refresh handoff and replay reports before resuming the loop."



