from __future__ import annotations

from datetime import datetime, timezone

from .schemas import CheckpointQualityIssue, CheckpointQualityReport, HandoffBundle, RunRecord, RunState


def build_checkpoint_quality(
    run: RunRecord,
    state: RunState,
    *,
    note_text: str,
    run_note_path: str = "",
    handoff: HandoffBundle | None = None,
) -> CheckpointQualityReport:
    bundle = handoff or state.handoff_summary
    note = note_text or ""
    note_lower = note.lower()
    issues: list[CheckpointQualityIssue] = []

    def add_issue(issue_id: str, severity: str, summary: str, evidence: str, action: str) -> None:
        issues.append(
            CheckpointQualityIssue(
                id=issue_id,
                severity=severity,  # type: ignore[arg-type]
                summary=summary,
                evidence=evidence[:500],
                recommended_action=action,
            )
        )

    run_note_present = bool(note.strip())
    has_checkpoint_heading = "### checkpoint:" in note_lower or "## final summary:" in note_lower
    has_active_goal = "- active goal:" in note_lower
    has_current_step = "- current step:" in note_lower
    has_next_action = "- next action:" in note_lower
    has_resume_prompt = "- resume prompt:" in note_lower and "resume agentorinth run" in note_lower
    has_no_raw_logs_instruction = "do not reload raw logs" in note_lower
    has_report_integrity_refresh = "- report integrity refresh:" in note_lower

    if not run_note_present:
        add_issue(
            "run_note_missing",
            "blocker",
            "Obsidian run note is missing or empty.",
            f"path={run_note_path or 'unknown'}",
            "Write an Obsidian checkpoint before unattended resume.",
        )
    else:
        required_markers = [
            ("checkpoint_heading_missing", has_checkpoint_heading, "latest checkpoint heading"),
            ("active_goal_missing", has_active_goal, "active goal"),
            ("current_step_missing", has_current_step, "current step"),
            ("next_action_missing", has_next_action, "next action"),
            ("resume_prompt_missing", has_resume_prompt, "resume prompt"),
        ]
        for issue_id, present, label in required_markers:
            if not present:
                add_issue(
                    issue_id,
                    "blocker",
                    f"Obsidian run note is missing the {label} resume anchor.",
                    f"missing={label}",
                    "Append a compact Obsidian checkpoint with active goal, next action, and resume prompt.",
                )

        if bundle.resume_prompt and "do not reload raw logs" in bundle.resume_prompt.lower() and not has_no_raw_logs_instruction:
            add_issue(
                "raw_log_instruction_missing",
                "warning",
                "Obsidian run note does not repeat the compact-resume instruction.",
                "missing=Do not reload raw logs",
                "Include the resume prompt line from the current handoff in the next checkpoint.",
            )

    refreshes = state.report_integrity_refreshes or bundle.report_integrity_refreshes
    expected_refresh = bool(refreshes)
    expected_refresh_event_id = int(refreshes[0].event_id) if refreshes else 0
    expected_refresh_reason = refreshes[0].reasons[0][:240] if refreshes and refreshes[0].reasons else ""
    if expected_refresh:
        refresh_id_present = f"#{expected_refresh_event_id}" in note
        if not has_report_integrity_refresh or not refresh_id_present:
            add_issue(
                "report_integrity_refresh_missing",
                "blocker",
                "Latest report-integrity refresh breadcrumb is missing from the Obsidian checkpoint.",
                f"expected_refresh=#{expected_refresh_event_id}",
                "Append a checkpoint after refreshing handoff/report integrity so the resume cause is durable.",
            )

    blocker_count = sum(1 for issue in issues if issue.severity == "blocker")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    if blocker_count:
        status = "needs_checkpoint"
        recommended_action = "Write or refresh the Obsidian checkpoint before allowing unattended Ornith resume."
    else:
        status = "ready"
        recommended_action = "Checkpoint anchors are present; resume from compact handoff and Obsidian note."

    if not run.id:
        status = "unknown"
        recommended_action = "No run id was available for checkpoint-quality analysis."

    summary = (
        "Obsidian checkpoint includes the required long-loop resume anchors."
        if status == "ready"
        else f"Obsidian checkpoint is missing {blocker_count} required resume anchor(s)."
    )
    return CheckpointQualityReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status=status,  # type: ignore[arg-type]
        run_note_present=run_note_present,
        run_note_path=run_note_path,
        run_note_chars=len(note),
        has_checkpoint_heading=has_checkpoint_heading,
        has_active_goal=has_active_goal,
        has_current_step=has_current_step,
        has_next_action=has_next_action,
        has_resume_prompt=has_resume_prompt,
        has_no_raw_logs_instruction=has_no_raw_logs_instruction,
        expected_report_integrity_refresh=expected_refresh,
        has_report_integrity_refresh=has_report_integrity_refresh,
        expected_refresh_event_id=expected_refresh_event_id,
        expected_refresh_reason=expected_refresh_reason,
        issue_count=len(issues),
        blocker_count=blocker_count,
        warning_count=warning_count,
        summary=summary,
        recommended_action=recommended_action,
        issues=issues,
    )
