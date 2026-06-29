from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from .acceptance import infer_required_labels
from .schemas import CompletionAuditReport, PolicySimulationReport, RunHealthReport, RunRecord


ACTIVE_STATUSES = {"queued", "running", "paused"}
ATTENTION_STATUSES = {"waiting_approval", "waiting_goal_confirmation", "blocked", "error"}
PolicyAction = Literal["continue", "verify", "recover", "pause", "wait_approval", "ask_user", "complete"]


def build_policy_simulation(
    run: RunRecord,
    completion_audit: CompletionAuditReport,
    run_health: RunHealthReport,
) -> PolicySimulationReport:
    state = run.state
    action = run_health.recommended_action
    predicted_status = _active_status(run.status)
    predicted_milestone = state.milestone
    safe_to_resume = True
    effects: list[str] = []
    reason = run_health.summary
    next_action = state.next_step or _first(run_health.next_actions) or "Continue with the next safe action."

    recommended_tool = ""
    recommended_label = ""
    recommendation = _first_recommendation(run)
    if recommendation:
        recommended_tool = recommendation["tool"]
        recommended_label = recommendation["label"]
        if action == "verify":
            next_action = recommendation["action"]

    if run.status == "completed":
        action = "complete"
        predicted_status = "completed"
        safe_to_resume = False
        reason = "Run is already completed."
        next_action = "No resume action required."
        effects.append("Keep the completed run closed unless the user starts a new run.")
    elif run.status == "canceled":
        action = "pause"
        predicted_status = "canceled"
        safe_to_resume = False
        reason = "Run was canceled."
        next_action = "Create a new run if the goal should continue."
        effects.append("Do not auto-resume a canceled run.")
    elif run.status == "waiting_goal_confirmation":
        action = "ask_user"
        predicted_status = "waiting_goal_confirmation"
        safe_to_resume = False
        reason = "A proposed /goal update is waiting for user confirmation."
        next_action = "Accept or reject the proposed goal revision."
        effects.append("Keep the loop paused until the goal statement is confirmed.")
    elif action == "wait_approval":
        predicted_status = "waiting_approval"
        safe_to_resume = False
        next_action = _first(run_health.next_actions) or "Resolve pending approvals in the dashboard."
        effects.append("Keep the run gated on explicit dashboard approval.")
    elif action == "recover":
        predicted_status = "paused"
        safe_to_resume = False
        next_action = (
            state.recovery_plan.next_action
            if state.recovery_plan.status == "active" and state.recovery_plan.next_action
            else _first(run_health.next_actions)
            or "Resume or replan recovery before continuing."
        )
        effects.append("Pause the loop and checkpoint recovery context.")
        if state.recovery_plan.status == "active":
            effects.append("Use the active recovery plan as the next task list.")
    elif action in {"ask_user", "pause"}:
        predicted_status = "paused"
        safe_to_resume = False
        next_action = _first(run_health.next_actions) or "Review run health before continuing."
        effects.append("Pause the run so the user can resolve the health signal.")
    elif action == "verify":
        predicted_milestone = "act"
        effects.append("Route the next action to the smallest missing acceptance proof.")
        effects.append("Record a recommendation trace if a proof recommendation drives the tool call.")
    elif completion_audit.can_finish:
        action = "complete"
        predicted_status = "completed"
        next_action = "Mark the run completed after the decision milestone."
        reason = "Completion audit is ready and run health allows finishing."
        effects.append("Finish the run and write final memory.")
    else:
        effects.append("Continue from the next safe action after the decision milestone.")

    auto_resume_eligible = safe_to_resume and run.status not in ATTENTION_STATUSES and action in {"continue", "verify", "complete"}
    blocking_signals = [
        signal.id
        for signal in run_health.signals
        if signal.severity in {"warning", "critical"}
    ]

    return PolicySimulationReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        current_status=run.status,
        current_milestone=state.milestone,
        predicted_status=predicted_status,
        predicted_milestone=predicted_milestone,
        policy_action=action,  # type: ignore[arg-type]
        safe_to_resume=safe_to_resume,
        auto_resume_eligible=auto_resume_eligible,
        summary=_summary(action, predicted_status, predicted_milestone),
        reason=reason,
        next_action=next_action,
        recommended_tool=recommended_tool,
        recommended_label=recommended_label,
        effects=list(dict.fromkeys(effects))[:8],
        blocking_signals=blocking_signals[:8],
        run_health=run_health,
        completion_audit=completion_audit,
    )


def _active_status(status: str) -> str:
    if status in ACTIVE_STATUSES:
        return "running"
    return status


def _first(items: list[str]) -> str:
    return items[0] if items else ""


def _summary(action: PolicyAction | str, status: str, milestone: str) -> str:
    return f"Would {action} -> {status}/{milestone}."


def _first_recommendation(run: RunRecord) -> dict[str, str] | None:
    state = run.state
    if state.acceptance_recommendations:
        recommendation = state.acceptance_recommendations[0]
        return {
            "tool": recommendation.tool_kind,
            "label": recommendation.label,
            "action": recommendation.action,
        }

    for item in state.acceptance_evidence:
        if item.status == "verified":
            continue
        missing = [
            label
            for label in item.required_labels or infer_required_labels(item.criterion)
            if label not in set(item.matched_labels)
        ]
        label = missing[0] if missing else "verification"
        return _recommendation_for_label(run, label, item.criterion)

    for criterion in state.acceptance_criteria:
        labels = infer_required_labels(criterion)
        label = labels[0] if labels else "verification"
        return _recommendation_for_label(run, label, criterion)

    return None


def _recommendation_for_label(run: RunRecord, label: str, criterion: str) -> dict[str, str]:
    state = run.state
    test_command = state.repo_map.test_commands[0] if state.repo_map.test_commands else "python -m pytest"
    if label == "verification":
        return {
            "tool": "run_tests",
            "label": label,
            "action": f"Run the smallest relevant verification command: {test_command}",
        }
    if label == "checkpoint":
        return {
            "tool": "obsidian_checkpoint",
            "label": label,
            "action": "Write a compact checkpoint and refresh the handoff bundle.",
        }
    if label == "browser":
        if state.browser_enabled:
            return {
                "tool": "browser_screenshot",
                "label": label,
                "action": "Capture a browser screenshot of the relevant local page or dashboard.",
            }
        if state.desktop_enabled:
            return {
                "tool": "desktop_screenshot",
                "label": label,
                "action": "Capture a supervised desktop screenshot of the relevant UI.",
            }
        return {
            "tool": "ask_user",
            "label": label,
            "action": "Ask to enable browser or desktop tools, or revise the browser-facing criterion.",
        }
    if label == "web":
        return {
            "tool": "web_search" if state.web_enabled else "ask_user",
            "label": label,
            "action": (
                "Search or fetch a cited source and store the citation with the result."
                if state.web_enabled
                else "Ask to enable web tools or provide an offline source."
            ),
        }
    if label == "edit":
        return {
            "tool": "patch_propose",
            "label": label,
            "action": "Propose a focused patch tied to this criterion before applying edits.",
        }
    return {
        "tool": "ask_user",
        "label": label,
        "action": f"Ask how to prove the missing evidence label for {criterion}.",
    }
