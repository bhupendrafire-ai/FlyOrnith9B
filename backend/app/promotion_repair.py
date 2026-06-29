from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .schemas import PatchApplication, PatchProposal, PromotionRepairReport, PromotionVerificationAttemptRecord, RunRecord, ToolCallRecord


ACTIVE_VERIFICATION_STATUSES = {"needs_retry", "repeated_failure"}
CLOSED_PATCH_STATUSES = {"rejected", "rolled_back"}


def build_promotion_repair_report(run: RunRecord) -> PromotionRepairReport:
    state = run.state
    verification = state.promotion_verification
    if not verification.generated_at:
        verification = state.handoff_summary.promotion_verification
    generated_at = _utc_stamp()
    if not verification.generated_at:
        return PromotionRepairReport(
            run_id=run.id,
            generated_at=generated_at,
            summary="No promotion verification report exists yet.",
            next_action="Run promotion verification before entering promotion repair.",
        )
    if verification.status not in ACTIVE_VERIFICATION_STATUSES:
        return PromotionRepairReport(
            run_id=run.id,
            generated_at=generated_at,
            phase="none",
            active=False,
            next_verification_command=verification.next_command,
            summary=f"Promotion repair is inactive because verification status is {verification.status}.",
            next_action=verification.recommended_action,
        )
    attempt = _latest_repair_attempt(verification.attempts, verification.latest_attempt)
    if not attempt or not attempt.suspected_file:
        return PromotionRepairReport(
            run_id=run.id,
            generated_at=generated_at,
            phase="none",
            active=False,
            failure_kind=verification.latest_failure_kind,
            repair_hint=verification.latest_repair_hint,
            latest_failed_command=verification.latest_failed_command,
            next_verification_command=verification.next_command,
            summary="Promotion verification failed, but no file-focused repair target was classified.",
            next_action=verification.recommended_action,
        )
    target_file = _repair_read_path(run, attempt.suspected_file)
    if not target_file:
        return PromotionRepairReport(
            run_id=run.id,
            generated_at=generated_at,
            phase="none",
            active=False,
            failure_kind=attempt.failure_kind or verification.latest_failure_kind,
            repair_hint=attempt.repair_hint or verification.latest_repair_hint,
            latest_failed_command=verification.latest_failed_command,
            next_verification_command=verification.next_command,
            summary="Promotion repair target is outside the run workspace or unsafe to read.",
            next_action="Ask the operator to inspect the promotion verification target path before continuing.",
        )

    read_call = _latest_file_read_after_failure(state.tool_calls, target_file, attempt.command)
    proposal = _latest_patch_proposal(state.patch_proposals, target_file)
    application = _latest_patch_application(state.patch_applications, target_file)
    phase = "needs_file_read"
    next_tool = "file_read"
    next_action = f"Read `{target_file}` before proposing a promotion repair patch."
    patch_status = ""
    patch_id = ""
    application_id = ""
    if application and application.status == "applied":
        phase = "ready_to_verify"
        next_tool = "run_tests"
        next_action = f"Rerun promotion verification: {verification.next_command or 'select the promotion verification command'}."
        application_id = application.id
        patch_status = application.status
    elif proposal:
        patch_id = proposal.id
        patch_status = proposal.status
        if proposal.status == "applied":
            phase = "ready_to_verify"
            next_tool = "run_tests"
            next_action = f"Rerun promotion verification: {verification.next_command or 'select the promotion verification command'}."
        else:
            phase = "patch_proposed"
            next_tool = "patch_apply"
            next_action = f"Review and, if approved, apply promotion repair patch `{proposal.id}` before verification."
    elif read_call:
        phase = "needs_patch_proposal"
        next_tool = "patch_propose"
        next_action = f"Propose a minimal patch for `{target_file}` using the promotion repair hint."

    file_excerpt_chars = 0
    if read_call and isinstance(read_call.args, dict):
        file_excerpt_chars = len(str(read_call.args.get("content") or ""))
    target = target_file if not attempt.suspected_line else f"{target_file}:{attempt.suspected_line}"
    return PromotionRepairReport(
        run_id=run.id,
        generated_at=generated_at,
        phase=phase,  # type: ignore[arg-type]
        active=True,
        target_file=target_file,
        target_line=attempt.suspected_line,
        failure_kind=attempt.failure_kind or verification.latest_failure_kind,
        repair_hint=attempt.repair_hint or verification.latest_repair_hint,
        evidence_excerpt=attempt.evidence_excerpt,
        latest_failed_command=attempt.command or verification.latest_failed_command,
        file_read=bool(read_call),
        file_read_tool_id=read_call.id if read_call else "",
        file_excerpt_chars=file_excerpt_chars,
        patch_proposal_id=patch_id,
        patch_status=patch_status,
        patch_application_id=application_id,
        next_tool=next_tool,
        next_action=next_action,
        next_verification_command=verification.next_command,
        summary=f"Promotion repair phase `{phase}` for `{target}`; next tool `{next_tool}`.",
    )


def _latest_repair_attempt(
    attempts: list[PromotionVerificationAttemptRecord],
    latest_attempt: PromotionVerificationAttemptRecord,
) -> PromotionVerificationAttemptRecord | None:
    candidates = attempts or ([latest_attempt] if latest_attempt.command else [])
    for attempt in reversed(candidates):
        if not attempt.ok and (attempt.repair_hint or attempt.suspected_file):
            return attempt
    return latest_attempt if latest_attempt.command and (latest_attempt.repair_hint or latest_attempt.suspected_file) else None


def _repair_read_path(run: RunRecord, suspected_file: str) -> str:
    value = str(suspected_file or "").strip().strip("'\"")
    if not value:
        return ""
    candidate = Path(value)
    workspace = Path(run.workspace_path).resolve()
    if candidate.is_absolute():
        try:
            return str(candidate.resolve().relative_to(workspace)).replace("\\", "/")
        except ValueError:
            return ""
    parts = [part for part in candidate.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return ""
    return str(Path(*parts)).replace("\\", "/")


def _latest_file_read_after_failure(tool_calls: list[ToolCallRecord], target_file: str, failed_command: str) -> ToolCallRecord | None:
    normalized = _normalize_path(target_file)
    for call in reversed(tool_calls):
        if call.name == "file_read" and call.ok and _normalize_path(str(call.args.get("path") or "")) == normalized:
            return call
        if failed_command and call.name == "run_tests" and str(call.args.get("command") or "") == failed_command:
            return None
    return None


def _latest_patch_proposal(proposals: list[PatchProposal], target_file: str) -> PatchProposal | None:
    normalized = _normalize_path(target_file)
    for proposal in reversed(proposals):
        if proposal.status in CLOSED_PATCH_STATUSES:
            continue
        if any(_normalize_path(str(path)) == normalized for path in proposal.files):
            return proposal
    return None


def _latest_patch_application(applications: list[PatchApplication], target_file: str) -> PatchApplication | None:
    normalized = _normalize_path(target_file)
    for application in reversed(applications):
        if any(_normalize_path(str(path)) == normalized for path in application.files):
            return application
    return None


def _normalize_path(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").lstrip("./").lower()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")