from __future__ import annotations

import re

from .persistence import utc_now
from .schemas import HandoffBundle, ResumePromptQualityIssue, ResumePromptQualityReport, RunRecord


GENERIC_NEXT_ACTIONS = {
    "",
    "continue",
    "continue.",
    "keep going",
    "resume",
    "next step",
    "do the next step",
    "ask user whether to continue.",
}

CONCRETE_ACTION_VERBS = {
    "accept",
    "apply",
    "ask",
    "build",
    "capture",
    "checkpoint",
    "compile",
    "consult",
    "fetch",
    "inspect",
    "open",
    "propose",
    "read",
    "refresh",
    "replan",
    "resolve",
    "review",
    "run",
    "search",
    "test",
    "verify",
    "write",
}


def build_resume_prompt_quality(
    run: RunRecord,
    *,
    handoff: HandoffBundle | None = None,
) -> ResumePromptQualityReport:
    state = run.state
    handoff = handoff or state.handoff_summary
    prompt = (handoff.resume_prompt or "").strip()
    next_action = (handoff.next_action or state.next_step or "").strip()
    issues: list[ResumePromptQualityIssue] = []

    has_goal_anchor = bool(prompt and (_mentions_goal(prompt, run.goal) or _mentions_goal(prompt, handoff.original_goal)))
    has_context_anchor = _has_context_anchor(prompt)
    concrete_next_action = _is_concrete_next_action(next_action)
    has_action_context = bool(
        state.action_context.generated_at
        or handoff.action_context.generated_at
        or state.action_context.selected_action
        or handoff.action_context.selected_action
        or state.current_task_id
        or handoff.current_task_id
        or state.task_graph
        or handoff.task_graph
    )
    has_evidence_refs = bool(
        state.files_touched
        or handoff.files_touched
        or state.commands_run
        or handoff.commands_and_tests
        or state.acceptance_recommendations
        or handoff.acceptance_recommendations
        or state.source_evidence.total_count
        or handoff.source_evidence.total_count
        or state.repo_map.summary
        or handoff.repo_map_summary
    )
    snapshot = state.context_snapshot if state.context_snapshot.generated_at else handoff.context_snapshot
    context_coverage_status = snapshot.coverage_status if snapshot.generated_at else "missing"

    def add_issue(
        issue_id: str,
        severity: str,
        summary: str,
        evidence: list[str],
        next_issue_action: str,
    ) -> None:
        issues.append(
            ResumePromptQualityIssue(
                id=issue_id,
                severity=severity,  # type: ignore[arg-type]
                summary=summary,
                evidence=evidence,
                next_action=next_issue_action,
            )
        )

    if not prompt:
        add_issue(
            "missing_resume_prompt",
            "blocker",
            "No compact resume prompt is available for this run.",
            ["prompt_chars=0"],
            "Refresh the handoff bundle before resuming Ornith.",
        )
    elif len(prompt) < 80:
        add_issue(
            "short_resume_prompt",
            "warning",
            "Resume prompt is unusually short for a long-running coding handoff.",
            [f"prompt_chars={len(prompt)}"],
            "Refresh the handoff with goal, next action, and compact context anchors.",
        )

    if prompt and run.id not in prompt:
        add_issue(
            "missing_run_anchor",
            "warning",
            "Resume prompt does not name the run id.",
            [f"run_id={run.id}"],
            "Regenerate the resume prompt so restart/replay tooling can identify the run.",
        )
    if not has_goal_anchor:
        add_issue(
            "missing_goal_anchor",
            "blocker",
            "Resume prompt does not preserve the original or active goal anchor.",
            [_goal_fragment(run.goal) or "goal fragment unavailable"],
            "Refresh the handoff with the original goal and active objective before continuing.",
        )
    if not concrete_next_action:
        add_issue(
            "vague_next_action",
            "blocker",
            "Next action is missing or too vague for Ornith to resume safely.",
            [next_action or "next_action=missing"],
            "Write a concrete next command, file, tool, or verification action into the handoff.",
        )
    if prompt and not has_context_anchor:
        add_issue(
            "weak_context_anchor",
            "warning",
            "Resume prompt does not clearly tell Ornith to use Obsidian/compact handoff context instead of raw logs.",
            ["obsidian/second-brain/raw-log guard not all present"],
            "Regenerate the resume prompt with Obsidian and no-raw-log instructions.",
        )
    if snapshot.generated_at and snapshot.coverage_status == "critical":
        add_issue(
            "critical_context_coverage",
            "blocker",
            "Compiled context omitted required sections.",
            snapshot.required_sections_missing or ["required context omitted"],
            snapshot.recommended_action or "Recompile context under a larger target before resuming.",
        )
    elif not snapshot.generated_at:
        add_issue(
            "missing_context_snapshot",
            "warning",
            "No compiled context snapshot is attached to this handoff yet.",
            ["context_snapshot=missing"],
            "Compile compact context and refresh the handoff before unattended resume.",
        )
    elif snapshot.coverage_status == "degraded":
        add_issue(
            "degraded_context_coverage",
            "warning",
            "Compiled context dropped optional sections.",
            snapshot.dropped_sections[:8] or ["optional context dropped"],
            snapshot.recommended_action,
        )
    if not has_action_context:
        add_issue(
            "missing_action_context",
            "warning",
            "No bounded action-context pack or current task anchor is attached.",
            ["action_context=missing", f"task_graph={len(state.task_graph)}"],
            "Refresh the action-context pack before the next act milestone.",
        )
    if not has_evidence_refs:
        add_issue(
            "thin_evidence_refs",
            "warning",
            "Handoff has little bounded evidence for commands, files, source proof, or acceptance recommendations.",
            ["files=0", "commands=0", "recommendations=0"],
            "Add a small verification/source/checkpoint evidence record before unattended resume.",
        )

    blocker_count = sum(1 for issue in issues if issue.severity == "blocker")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    score = max(0, 100 - blocker_count * 35 - warning_count * 12)
    if blocker_count:
        status = "blocked"
    elif warning_count:
        status = "needs_refresh"
    else:
        status = "ready"
    recommended_action = _first_action(issues) or "Resume from the compact handoff and execute the concrete next action."

    return ResumePromptQualityReport(
        run_id=run.id,
        generated_at=utc_now(),
        status=status,  # type: ignore[arg-type]
        ready_to_resume=status != "blocked",
        score=score,
        summary=f"{status}: resume prompt quality score {score}/100 with {blocker_count} blocker(s) and {warning_count} warning(s).",
        prompt_chars=len(prompt),
        next_action=next_action,
        concrete_next_action=concrete_next_action,
        has_goal_anchor=has_goal_anchor,
        has_context_anchor=has_context_anchor,
        has_action_context=has_action_context,
        has_evidence_refs=has_evidence_refs,
        context_coverage_status=context_coverage_status,
        recommended_action=recommended_action,
        issues=issues[:12],
    )


def _is_concrete_next_action(value: str) -> bool:
    lowered = " ".join(value.lower().split())
    if lowered in {"done", "done.", "complete", "complete.", "completed", "completed."}:
        return True
    if lowered in GENERIC_NEXT_ACTIONS or len(lowered) < 12:
        return False
    tokens = set(re.findall(r"[a-z_][a-z0-9_/-]*", lowered))
    if tokens & CONCRETE_ACTION_VERBS:
        return True
    if re.search(r"(backend|frontend|tests?|api|/api/|\.py|\.ts|\.tsx|npm|pytest|compile|git|obsidian|handoff)", lowered):
        return True
    return False


def _has_context_anchor(prompt: str) -> bool:
    lowered = prompt.lower()
    has_memory = "obsidian" in lowered or "second-brain" in lowered or "second brain" in lowered
    has_compact = "handoff" in lowered or "compact" in lowered
    has_raw_guard = "raw log" in lowered or "raw history" in lowered or "do not reload" in lowered
    return has_memory and has_compact and has_raw_guard


def _mentions_goal(prompt: str, goal: str) -> bool:
    fragment = _goal_fragment(goal)
    if not fragment:
        return False
    return fragment.lower() in _normalized_goal_text(prompt)


def _goal_fragment(goal: str) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", goal or "")
    if not words:
        return ""
    return " ".join(words[: min(10, len(words))])


def _normalized_goal_text(value: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", value or "")).lower()


def _first_action(issues: list[ResumePromptQualityIssue]) -> str:
    for severity in ("blocker", "warning", "info"):
        for issue in issues:
            if issue.severity == severity and issue.next_action:
                return issue.next_action
    return ""
