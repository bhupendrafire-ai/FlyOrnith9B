from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .schemas import PostActionRetryDecisionRecord, PostActionRetryReport, RunRecord, RunState, ToolCallRecord


def build_post_action_retry_report(run: RunRecord) -> PostActionRetryReport:
    decisions = run.state.post_action_retries.decisions[-20:]
    latest = decisions[-1] if decisions else PostActionRetryDecisionRecord()
    pending = [item for item in decisions if item.status in {"pending", "selected"}]
    resolved = [item for item in decisions if item.status == "resolved"]
    failed = [item for item in decisions if item.status == "failed"]
    if pending:
        summary = f"Post-action retry pending: {pending[-1].selected_action}"
        recommended = pending[-1].selected_action
    elif latest.id:
        summary = f"Latest post-action retry {latest.status}: {latest.selected_tool or latest.trigger_tool}."
        recommended = latest.resolution_summary or latest.selected_action
    else:
        summary = "No post-action retry has been proposed."
        recommended = "Use normal action readiness."
    return PostActionRetryReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        decision_count=len(decisions),
        pending_count=len(pending),
        resolved_count=len(resolved),
        failed_count=len(failed),
        latest_decision=latest,
        summary=summary,
        recommended_action=recommended,
        decisions=decisions,
    )


def propose_post_action_retry(
    run: RunRecord,
    *,
    result: Any,
    action: dict[str, Any],
    failure_kind: str,
    attempt_count: int,
) -> PostActionRetryDecisionRecord | None:
    state = run.state
    if result.ok or result.needs_approval:
        return None
    if action.get("post_action_retry_id"):
        return None
    if state.recovery_plan.status == "active":
        return None
    if attempt_count >= 3:
        return None
    selected_tool, selected_action, command_hint, reason = _retry_strategy(result, action, state)
    if not selected_tool:
        return None
    pack = state.action_context
    action_context_summary = pack.compact_prompt[:700] if pack.generated_at else ""
    return PostActionRetryDecisionRecord(
        id=f"post-retry-{uuid4().hex[:8]}",
        status="pending",
        trigger_tool=str(result.kind),
        trigger_summary=str(result.summary)[:500],
        failure_kind=failure_kind,
        attempt_count=attempt_count,
        selected_tool=selected_tool,
        selected_action=selected_action,
        command_hint=command_hint,
        reason=reason,
        action_context_summary=action_context_summary,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def resolve_post_action_retry(state: RunState, action: dict[str, Any], result: Any) -> None:
    retry_id = str(action.get("post_action_retry_id") or "")
    if not retry_id:
        return
    decision = next((item for item in state.post_action_retries.decisions if item.id == retry_id), None)
    if not decision:
        return
    decision.status = "resolved" if result.ok else "failed"
    decision.resolved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decision.resolution_tool = str(result.kind)
    decision.resolution_ok = bool(result.ok)
    decision.resolution_summary = str(result.summary)[:500]
    state.post_action_retries = build_post_action_retry_report(
        RunRecord(
            id=state.post_action_retries.run_id,
            title="retry-state",
            goal=state.goal,
            status="running",
            workspace_path="",
            state=state,
            created_at="",
            updated_at="",
        )
    )


def retry_action_from_decision(decision: PostActionRetryDecisionRecord) -> dict[str, Any] | None:
    if not decision.id or decision.status not in {"pending", "selected"}:
        return None
    if _missing_artifact_verification(decision.trigger_summary, decision.trigger_summary.lower()):
        return None
    thought = f"Use post-action retry after {decision.trigger_tool} failure: {decision.reason or decision.selected_action}"
    base = {
        "thought_summary": thought,
        "post_action_retry_id": decision.id,
        "post_action_retry_reason": decision.reason,
    }
    if decision.selected_tool in {"shell", "run_tests"}:
        return {"tool": decision.selected_tool, "args": {"command": decision.command_hint}, **base}
    if decision.selected_tool == "git_status":
        return {"tool": "git_status", "args": {}, **base}
    if decision.selected_tool == "browser_open":
        return {"tool": "browser_open", "args": {"url": decision.command_hint or "http://127.0.0.1:5173"}, **base}
    if decision.selected_tool == "browser_screenshot":
        return {"tool": "browser_screenshot", "args": {"url": decision.command_hint or "http://127.0.0.1:5173"}, **base}
    if decision.selected_tool == "file_read":
        return {"tool": "file_read", "args": {"path": decision.command_hint or "."}, **base}
    if decision.selected_tool == "ask_user":
        return {"tool": "ask_user", "args": {"question": decision.selected_action, "reason": decision.reason}, **base}
    return None


def mark_post_action_retry_selected(state: RunState, retry_id: str) -> None:
    decision = next((item for item in state.post_action_retries.decisions if item.id == retry_id), None)
    if not decision or decision.status != "pending":
        return
    decision.status = "selected"
    state.post_action_retries = build_post_action_retry_report(
        RunRecord(
            id=state.post_action_retries.run_id,
            title="retry-state",
            goal=state.goal,
            status="running",
            workspace_path="",
            state=state,
            created_at="",
            updated_at="",
        )
    )


def _retry_strategy(result: Any, action: dict[str, Any], state: RunState) -> tuple[str, str, str, str]:
    kind = str(result.kind)
    command = _command_from_result(result)
    summary = str(result.summary).lower()
    if kind == "shell" and _missing_artifact_verification(command, summary):
        return ("", "", "", "")
    if kind == "run_tests":
        command_hint = _compile_command(state)
        return (
            "shell",
            f"Run a focused compile/import diagnostic before repeating broad tests: {command_hint}",
            command_hint,
            "Broad test proof failed; Ornith should isolate syntax/import failures before another full test run.",
        )
    if kind == "shell" and "timed out" in str(result.summary).lower():
        return (
            "git_status",
            "Check workspace state after the timed-out shell command before retrying a narrower command.",
            "",
            "Shell command timed out; inspect state with a cheap non-mutating command first.",
        )
    if kind == "shell" and command and "compileall" not in command:
        command_hint = _compile_command(state)
        return (
            "shell",
            f"Run a narrower compile diagnostic instead of repeating the failed shell command: {command_hint}",
            command_hint,
            "Shell action failed; use a narrower compile/import diagnostic before replanning.",
        )
    if kind == "browser_screenshot":
        url = _url_from_action(action)
        return (
            "browser_open",
            f"Open the target page before retrying screenshot capture: {url}",
            url,
            "Screenshot failed; open the page explicitly before capturing visual proof.",
        )
    if kind in {"web_search", "web_fetch"}:
        return (
            "ask_user",
            "Provide or confirm the source to use after the web evidence action failed.",
            "",
            "Web evidence failed; avoid repeated broad search without a better source hint.",
        )
    return (
        "git_status",
        "Inspect workspace state before choosing another tool after the failed action.",
        "",
        "Failed action needs a cheap state check before broader replanning.",
    )


def _compile_command(state: RunState) -> str:
    for command in reversed(state.commands_run):
        if "compileall" in command or "py_compile" in command:
            return command
    return "python -m compileall backend\\app"


def _command_from_result(result: Any) -> str:
    data = getattr(result, "data", {})
    return str(data.get("command") or "") if isinstance(data, dict) else ""


def _missing_artifact_verification(command: str, summary: str) -> bool:
    lowered = command.lower()
    return (
        ("*.pptx" in lowered or "*.html" in lowered)
        and ("no pptx files found" in summary or "no html files found" in summary)
    )


def _url_from_action(action: dict[str, Any]) -> str:
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    return str(args.get("url") or "http://127.0.0.1:5173")
