from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .action_readiness import rank_acceptance_recommendations
from .schemas import ActionContextPack, AcceptanceEvidenceRecommendation, RunRecord, ToolCallRecord
from .source_evidence import build_source_evidence_preview
from .tools import redact_secrets


def build_action_context_pack(run: RunRecord, *, selected_action: dict[str, Any] | None = None) -> ActionContextPack:
    state = run.state
    source_evidence = state.source_evidence if state.source_evidence.generated_at else build_source_evidence_preview(run, limit=8)
    state.source_evidence = source_evidence
    source_ref_preview = _readiness_source_ref_preview(state)
    source_ref_action = _readiness_source_ref_action(source_ref_preview)
    ranked = rank_acceptance_recommendations(run)
    recommendation = _select_recommendation(ranked, selected_action, state.action_readiness.suggested_tool, state.action_readiness.suggested_label)
    current_task = next((task for task in state.task_graph if task.id == state.current_task_id), None)
    selected_tool = str((selected_action or {}).get("tool") or (recommendation.tool_kind if recommendation else state.action_readiness.suggested_tool))
    selected_label = str(
        (selected_action or {}).get("recommendation_label")
        or (selected_action or {}).get("objective_readiness_evidence_label")
        or (recommendation.label if recommendation else state.action_readiness.suggested_label)
    )
    selected_action_text = str(
        (selected_action or {}).get("objective_readiness_proof_action")
        or (selected_action or {}).get("thought_summary")
        or (recommendation.action if recommendation else state.action_readiness.recommended_action)
    )
    recovery_hint = ""
    if state.recovery_plan.status == "active":
        recovery_hint = state.recovery_plan.next_action or state.recovery_plan.summary
    elif state.run_health.recommended_action in {"recover", "verify", "pause"}:
        recovery_hint = state.run_health.next_actions[0] if state.run_health.next_actions else state.run_health.summary

    pack = ActionContextPack(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        milestone=state.milestone,
        workspace_summary=_single_line(state.workspace_isolation.summary, 260),
        active_workspace_path=str(run.workspace_path or state.workspace_isolation.workspace_path or ""),
        source_workspace_path=str(state.workspace_isolation.source_path or ""),
        path_guidance=_workspace_path_guidance(run),
        current_task_id=state.current_task_id,
        current_task_title=current_task.title if current_task else "",
        task_transition_ledger=_task_transition_ledger(run),
        model_guard_ledger=_model_guard_ledger(state.tool_calls, selected_action),
        edit_evidence_ledger=_edit_evidence_ledger(run),
        desktop_supervision_ledger=_desktop_supervision_ledger(run),
        action_readiness_status=state.action_readiness.status,
        selected_tool=selected_tool,
        selected_label=selected_label,
        selected_action=_single_line(selected_action_text, 280),
        selected_reason=_single_line(recommendation.reason if recommendation else "", 220),
        selected_command_hint=_single_line(recommendation.command_hint if recommendation else _command_from_action(selected_action), 180),
        selected_criterion=_single_line(recommendation.criterion if recommendation else "", 220),
        source_evidence_summary=_single_line(source_evidence.summary, 260),
        missing_source_labels=source_evidence.missing_labels[:6],
        latest_source_evidence=_single_line(source_evidence.latest_evidence, 220),
        readiness_source_ref_status=source_ref_preview.status if source_ref_preview.run_id else "",
        readiness_source_ref_action=_single_line(source_ref_action, 260),
        readiness_source_ref_missing_evidence_labels=source_ref_preview.missing_source_evidence_labels[:6],
        readiness_source_ref_missing_proof_labels=source_ref_preview.missing_proof_ref_labels[:6],
        readiness_source_ref_source_labels=source_ref_preview.source_evidence_labels[:6],
        readiness_source_ref_proof_labels=source_ref_preview.proof_ref_labels[:6],
        recent_verified_commands=_recent_commands(state.commands_run),
        recent_verified_files=_recent_files(state.files_touched),
        recent_successes=_recent_successes(state.tool_calls),
        failure_ledger=_failure_ledger(run),
        resolved_failure_ledger=_resolved_failure_ledger(run),
        promotion_repair_hints=_promotion_repair_hints(run),
        recovery_hint=_single_line(recovery_hint, 260),
        context_budget=f"{state.context_budget.estimated_tokens}/{state.context_budget.target_tokens}:{state.context_budget.pressure}",
    )
    pack.compact_prompt = render_action_context_pack(pack)
    return pack


def render_action_context_pack(pack: ActionContextPack) -> str:
    if not pack.generated_at:
        return "Action context pack: none"
    lines = [
        "Action context pack:",
        f"- milestone={pack.milestone}; task={pack.current_task_id or 'none'}:{pack.current_task_title or 'untitled'}; readiness={pack.action_readiness_status or 'unknown'}",
        f"- workspace=active:{pack.active_workspace_path or 'unknown'}; source:{pack.source_workspace_path or 'unknown'}; {pack.workspace_summary or 'no workspace summary'}; path_rule={pack.path_guidance or 'use relative paths under active workspace'}",
        f"- task_transitions={_join(pack.task_transition_ledger)}",
        f"- model_guards={_join(pack.model_guard_ledger)}",
        f"- edit_evidence={_join(pack.edit_evidence_ledger)}",
        f"- desktop_supervision={_join(pack.desktop_supervision_ledger)}",
        f"- selected_proof={pack.selected_tool or 'none'}:{pack.selected_label or 'none'}; action={pack.selected_action or 'none'}",
        f"- selected_reason={pack.selected_reason or 'none'}; hint={pack.selected_command_hint or 'none'}; criterion={pack.selected_criterion or 'none'}",
        f"- source_evidence missing={','.join(pack.missing_source_labels) if pack.missing_source_labels else 'none'}; latest={pack.latest_source_evidence or 'none'}; {pack.source_evidence_summary or 'none'}",
        f"- source_refs status={pack.readiness_source_ref_status or 'none'}; missing_evidence={_join_csv(pack.readiness_source_ref_missing_evidence_labels)}; missing_proof={_join_csv(pack.readiness_source_ref_missing_proof_labels)}; source={_join_csv(pack.readiness_source_ref_source_labels)}; proof={_join_csv(pack.readiness_source_ref_proof_labels)}; action={pack.readiness_source_ref_action or 'none'}",
        f"- verified_commands={_join(pack.recent_verified_commands)}",
        f"- verified_files={_join(pack.recent_verified_files)}",
        f"- recent_successes={_join(pack.recent_successes)}",
        f"- failure_ledger={_join(pack.failure_ledger)}",
        f"- resolved_failure_ledger={_join(pack.resolved_failure_ledger)}",
        f"- promotion_repair_hints={_join(pack.promotion_repair_hints)}",
        f"- recovery_hint={pack.recovery_hint or 'none'}; context={pack.context_budget or 'unknown'}",
    ]
    return "\n".join(lines)


def _workspace_path_guidance(run: RunRecord) -> str:
    isolation = run.state.workspace_isolation
    source = str(isolation.source_path or "").strip()
    active = str(run.workspace_path or isolation.workspace_path or "").strip()
    if source and active and source != active:
        return "file paths are relative to active workspace; source absolute paths map to the same relative path in active workspace; promote when ready"
    return "file paths are relative to the active workspace"



def _readiness_source_ref_preview(state: Any) -> Any:
    report = state.readiness_source_ref_preview
    if not report.run_id:
        report = state.handoff_summary.readiness_source_ref_preview
    return report


def _readiness_source_ref_action(report: Any) -> str:
    if not getattr(report, "run_id", ""):
        return ""
    missing_evidence = list(getattr(report, "missing_source_evidence_labels", []) or [])
    missing_proof = list(getattr(report, "missing_proof_ref_labels", []) or [])
    if missing_evidence:
        return "Capture compact source evidence for " + ",".join(missing_evidence[:6]) + "; then refresh readiness source refs."
    if missing_proof:
        return "Dispatch readiness source-ref refresh before broad coding; proof refs missing for " + ",".join(missing_proof[:6]) + "."
    return str(getattr(report, "recommended_action", "") or "")


def _join_csv(items: list[str]) -> str:
    return ",".join(str(item) for item in items if str(item).strip()) or "none"

def _select_recommendation(
    ranked: list[AcceptanceEvidenceRecommendation],
    selected_action: dict[str, Any] | None,
    readiness_tool: str = "",
    readiness_label: str = "",
) -> AcceptanceEvidenceRecommendation | None:
    selected_action = selected_action or {}
    recommendation_id = str(selected_action.get("recommendation_id") or "")
    if recommendation_id:
        match = next((item for item in ranked if item.id == recommendation_id), None)
        if match:
            return match
    selected_tool = str(selected_action.get("tool") or readiness_tool or "")
    selected_label = str(selected_action.get("recommendation_label") or readiness_label or "")
    if selected_tool or selected_label:
        match = next(
            (
                item
                for item in ranked
                if (not selected_tool or item.tool_kind == selected_tool) and (not selected_label or item.label == selected_label)
            ),
            None,
        )
        if match:
            return match
    return ranked[0] if ranked else None


def _edit_evidence_ledger(run: RunRecord) -> list[str]:
    state = run.state
    ledger: list[str] = []
    for path in reversed(state.files_touched[-6:]):
        value = str(path or "").strip()
        if value:
            ledger.append(_single_line(f"touched:{value}", 220))
    for proposal in reversed(state.patch_proposals[-6:]):
        if proposal.status not in {"pending", "approved", "applied"}:
            continue
        files = ",".join(str(item) for item in proposal.files[:3]) or "files=unknown"
        label = f"patch:{proposal.status}:{proposal.id}:{files}"
        if proposal.title:
            label = f"{label}; {proposal.title}"
        ledger.append(_single_line(label, 260))
    for application in reversed(state.patch_applications[-6:]):
        if application.status != "applied":
            continue
        files = ",".join(str(item) for item in application.files[:3]) or "files=unknown"
        ledger.append(_single_line(f"patch_apply:{application.status}:{application.patch_id or application.id}:{files}", 240))
    diff = state.workspace_diff
    if diff.total_files or diff.files:
        ledger.append(
            _single_line(
                f"workspace_diff:{diff.total_files or len(diff.files)} files added={diff.added} modified={diff.modified} deleted={diff.deleted}",
                220,
            )
        )
    return ledger[:6]



def _desktop_supervision_ledger(run: RunRecord) -> list[str]:
    state = run.state
    report = state.operator_dispatches
    if not report.generated_at:
        report = state.handoff_summary.operator_dispatches
    histories = list(report.approval_histories or report.unresolved_approval_histories)
    ledger: list[str] = []
    effect_entry = _desktop_effect_check_ledger_entry(state.tool_calls)
    if effect_entry:
        ledger.append(effect_entry)
    for history in histories:
        kind = str(history.approval_kind or "").strip()
        if kind not in {"desktop_click", "desktop_type"}:
            continue
        decision = str(history.latest_decision or "").strip()
        hint = _desktop_supervision_hint(history.latest_status, decision)
        parts = [
            f"approval#{history.approval_id}",
            f"kind={kind}",
            f"status={history.latest_status or 'unknown'}",
        ]
        if decision:
            parts.append(f"decision={decision}")
        if hint:
            parts.append(f"hint={hint}")
        action = history.action_summary or history.action_title or history.action_reason
        if action:
            parts.append(f"action={redact_secrets(action)}")
        if history.sequence:
            parts.append(f"seq={'->'.join(history.sequence[-3:])}")
        ledger.append(_single_line(":".join(parts), 320))
        if len(ledger) >= 4:
            break
    return ledger



def _desktop_effect_check_ledger_entry(tool_calls: list[ToolCallRecord]) -> str:
    for call in reversed(tool_calls):
        if not call.ok:
            continue
        if call.name in {"desktop_screenshot", "desktop_window_list"}:
            return ""
        if call.name not in {"desktop_click", "desktop_type"}:
            continue
        summary = _single_line(redact_secrets(call.summary), 140)
        bits = [
            "desktop_effect_check_required",
            f"after={call.name}",
            "hint=capture_desktop_screenshot_or_window_list_before_next_click_type",
        ]
        if summary:
            bits.append(f"summary={summary}")
        return _single_line(":".join(bits), 300)
    return ""

def _desktop_supervision_hint(status: str, decision: str) -> str:
    if status == "dispatched" and decision == "approve":
        return "human_approved_supervised_action"
    if status == "dispatched" and decision == "reject":
        return "human_rejected_do_not_repeat_without_new_evidence"
    if status in {"reviewed", "confirmation_required"}:
        return "await_supervisor_decision"
    if status == "blocked":
        return "blocked_by_supervisor"
    return ""

def _model_guard_ledger(tool_calls: list[ToolCallRecord], selected_action: dict[str, Any] | None) -> list[str]:
    ledger: list[str] = []
    selected = _model_guard_entry(selected_action or {}, selected_tool=str((selected_action or {}).get("tool") or ""), prefix="selected")
    if selected:
        ledger.append(selected)
    for call in reversed(tool_calls):
        entry = _model_guard_entry(call.args, selected_tool=call.name)
        if entry:
            ledger.append(entry)
        if len(ledger) >= 6:
            break
    return ledger[:6]


def _model_guard_entry(values: dict[str, Any], *, selected_tool: str = "", prefix: str = "") -> str:
    guard = str(values.get("model_guard") or "").strip()
    if not guard:
        return ""
    parts = [guard]
    if prefix:
        parts.append(prefix)
    if selected_tool:
        parts.append(f"tool={selected_tool}")
    labels = [
        ("guarded_tool", "from"),
        ("guarded_desktop_tool", "after"),
        ("guarded_task_id", "guarded_task"),
        ("guarded_failure_id", "failure"),
        ("current_task_id", "current"),
        ("current_task_kind", "kind"),
        ("guard_reason", "reason"),
    ]
    for key, label in labels:
        value = str(values.get(key) or "").strip()
        if value:
            parts.append(f"{label}={value}")
    return _single_line("; ".join(parts), 260)


def _task_transition_ledger(run: RunRecord) -> list[str]:
    state = run.state
    if not state.task_graph:
        return []
    ledger: list[str] = []
    current_index = next(
        (index for index, task in enumerate(state.task_graph) if task.id == state.current_task_id),
        -1,
    )
    for task in state.task_graph:
        if task.status not in {"completed", "failed", "blocked", "skipped"}:
            continue
        evidence = task.evidence[-1] if task.evidence else task.notes
        detail = f"; evidence={evidence}" if evidence else ""
        ledger.append(_single_line(f"{task.status}:{task.id}:{task.title}{detail}", 260))
    current = state.task_graph[current_index] if current_index >= 0 else None
    if current:
        ledger.append(_single_line(f"current:{current.status}:{current.id}:{current.title}", 220))
        next_task = next(
            (
                task
                for task in state.task_graph[current_index + 1 :]
                if task.status in {"pending", "in_progress"}
            ),
            None,
        )
    else:
        next_task = next((task for task in state.task_graph if task.status in {"pending", "in_progress"}), None)
    if next_task and (not current or next_task.id != current.id):
        ledger.append(_single_line(f"next:{next_task.status}:{next_task.id}:{next_task.title}", 220))
    return ledger[-6:]


def _recent_successes(tool_calls: list[ToolCallRecord]) -> list[str]:
    successes: list[str] = []
    for call in reversed(tool_calls):
        if not call.ok:
            continue
        successes.append(_single_line(f"{call.name}: {call.summary}", 180))
        if len(successes) >= 4:
            break
    return list(reversed(successes))


def _recent_commands(commands: list[str]) -> list[str]:
    return [_single_line(command, 180) for command in commands[-4:]]


def _recent_files(files: list[str]) -> list[str]:
    unique: list[str] = []
    for item in reversed(files):
        if item not in unique:
            unique.append(item)
        if len(unique) >= 6:
            break
    return list(reversed([_single_line(item, 180) for item in unique]))


def _failure_ledger(run: RunRecord) -> list[str]:
    state = run.state
    ledger: list[str] = []
    for record in state.failure_records[-4:]:
        details = []
        if record.command:
            details.append(f"cmd={record.command}")
        if record.target:
            details.append(f"target={record.target}")
        if record.returncode is not None:
            details.append(f"rc={record.returncode}")
        if record.evidence_excerpt:
            details.append(f"evidence={record.evidence_excerpt}")
        detail_text = "; ".join(details)
        suffix = f"; {detail_text}" if detail_text else ""
        ledger.append(_single_line(f"{record.kind}:{record.tool}:x{record.count}:{record.recovery_hint or record.summary}{suffix}", 260))
    for tool, count in sorted(state.failure_counts.items()):
        summary = f"count:{tool}:x{count}"
        if summary not in ledger:
            ledger.append(summary)
    return ledger[-6:]



def _resolved_failure_ledger(run: RunRecord) -> list[str]:
    state = run.state
    ledger: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        compact = _single_line(value, 280)
        if compact and compact not in seen:
            seen.add(compact)
            ledger.append(compact)

    for decision in state.post_action_retries.decisions[-8:]:
        if decision.status != "resolved":
            continue
        tool = decision.resolution_tool or decision.selected_tool or "tool"
        failure_kind = f":{decision.failure_kind}" if decision.failure_kind else ""
        summary = decision.resolution_summary or decision.selected_action
        add(f"retry:{decision.trigger_tool or 'tool'}->{tool}{failure_kind}; ok={decision.resolution_ok}; {summary}")

    for decision in state.recovery_decisions.decisions[-8:]:
        if not (decision.resolved_by_evidence or decision.status == "resolved"):
            continue
        proof = f":{decision.proof_label}" if decision.proof_label else ""
        evidence = "verified" if decision.resolved_by_evidence else (decision.evidence_status or decision.status)
        detail = decision.summary or decision.selected_strategy or decision.next_action
        add(f"recovery:{decision.trigger or 'manual'}:{decision.tool or 'tool'}{proof}; evidence={evidence}; {detail}")

    for outcome in state.verification_outcomes.outcomes[-8:]:
        if outcome.outcome != "recovery_resolved":
            continue
        labels = f"; labels={','.join(outcome.labels_satisfied)}" if outcome.labels_satisfied else ""
        add(f"verification:recovery_resolved:{outcome.tool or 'tool'}:{outcome.proof_label or 'none'}{labels}; {outcome.summary}")

    return ledger[-6:]


def _promotion_repair_hints(run: RunRecord) -> list[str]:
    state = run.state
    report = state.promotion_verification
    if not report.generated_at:
        report = state.handoff_summary.promotion_verification
    if not report.generated_at:
        return []
    hints: list[str] = []
    seen: set[str] = set()
    attempts = report.attempts or ([report.latest_attempt] if report.latest_attempt.command else [])
    for attempt in reversed(attempts):
        if not attempt.repair_hint and not attempt.evidence_excerpt:
            continue
        location = attempt.suspected_file
        if location and attempt.suspected_line:
            location = f"{location}:{attempt.suspected_line}"
        bits = [attempt.failure_kind or "failed"]
        if location:
            bits.append(location)
        if attempt.returncode:
            bits.append(f"rc={attempt.returncode}")
        detail = attempt.repair_hint or attempt.evidence_excerpt
        hint = _single_line(f"{':'.join(bits)} -> {detail}", 260)
        if hint in seen:
            continue
        seen.add(hint)
        hints.append(hint)
        if len(hints) >= 3:
            break
    if report.next_command:
        hints.append(_single_line(f"next_promotion_verification={report.next_command}", 180))
    return hints[:4]


def _command_from_action(action: dict[str, Any] | None) -> str:
    args = (action or {}).get("args")
    if isinstance(args, dict) and args.get("command"):
        return str(args.get("command"))
    return ""


def _join(items: list[str]) -> str:
    return "; ".join(items) if items else "none"


def _single_line(value: str, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]
