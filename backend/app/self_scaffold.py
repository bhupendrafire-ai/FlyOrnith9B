from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import (
    RunRecord,
    SelfScaffoldChangeRecord,
    SelfScaffoldReport,
    SelfScaffoldReviewRecord,
    SelfScaffoldReviewReport,
    SelfScaffoldRollbackIntentRecord,
    SelfScaffoldRollbackIntentReport,
)


REVIEWABLE_REVIEW_KINDS = {"model_guard", "event"}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_self_scaffold_report(
    run: RunRecord,
    events: list[dict[str, Any]] | None = None,
    *,
    limit: int = 12,
) -> SelfScaffoldReport:
    state = run.state
    changes: list[SelfScaffoldChangeRecord] = []
    seen: set[str] = set()

    def add(record: SelfScaffoldChangeRecord) -> None:
        if not record.id or record.id in seen:
            return
        seen.add(record.id)
        changes.append(record)

    current_task = next((task for task in state.task_graph if task.id == state.current_task_id), None)
    if state.task_graph:
        counts = _task_status_counts(run)
        add(
            SelfScaffoldChangeRecord(
                id=f"task_graph:{state.current_task_id or len(state.task_graph)}",
                kind="task_graph",
                status="active",
                source="run_state",
                structure_ref=state.current_task_id or "task_graph",
                summary=(
                    f"Task graph anchors Ornith's current work: {len(state.task_graph)} task(s), "
                    f"current={state.current_task_id or 'none'}."
                ),
                intent="Let Ornith decompose and reshape the coding run without losing the active unit of work.",
                reversible=True,
                reverse_hint="Use dashboard steering or replan to regenerate the task graph from the active goal.",
                evidence=[
                    f"current={current_task.status}:{current_task.title}" if current_task else "current=missing",
                    counts,
                    *state.action_context.task_transition_ledger[-2:],
                ],
            )
        )

    pack = state.action_context
    if pack.generated_at or pack.selected_tool or pack.compact_prompt:
        add(
            SelfScaffoldChangeRecord(
                id=f"action_context:{pack.selected_tool or pack.current_task_id or 'pack'}",
                kind="action_context",
                status="active",
                source="action_context",
                structure_ref=pack.current_task_id or state.current_task_id or "action_context",
                summary=(
                    f"Action context packs the next tool posture: {pack.selected_tool or 'none'}"
                    f":{pack.selected_label or 'none'}."
                ),
                intent="Give Ornith a compact working memory for the next action without replaying raw logs.",
                reversible=True,
                reverse_hint="Refresh the handoff/action-context pack or re-run preflight before the next act milestone.",
                evidence=[
                    f"selected={pack.selected_tool or 'none'}:{pack.selected_label or 'none'}",
                    f"readiness={pack.action_readiness_status or 'unknown'}",
                    f"context={pack.context_budget or 'unknown'}",
                ],
            )
        )

    if state.tool_profile or any([state.web_enabled, state.browser_enabled, state.desktop_enabled]):
        add(
            SelfScaffoldChangeRecord(
                id=f"tool_posture:{state.tool_profile}",
                kind="tool_posture",
                status="active",
                source="run_state",
                structure_ref=state.tool_profile,
                summary=(
                    f"Tool posture is {state.tool_profile}; web={state.web_enabled}, "
                    f"browser={state.browser_enabled}, desktop={state.desktop_enabled}."
                ),
                intent="Expose the harness tools surrounding Ornith without changing the model identity.",
                reversible=True,
                reverse_hint="Create or steer a run with different tool toggles/profile; do not mutate the model server.",
                evidence=[
                    f"tool_profile={state.tool_profile}",
                    f"web={state.web_enabled}",
                    f"browser={state.browser_enabled}",
                    f"desktop={state.desktop_enabled}",
                ],
            )
        )

    for index, item in enumerate(pack.model_guard_ledger[-3:]):
        add(
            SelfScaffoldChangeRecord(
                id=f"model_guard:{index}:{_compact_id(item)}",
                kind="model_guard",
                status="needs_review",
                source="action_context",
                structure_ref=pack.current_task_id or state.current_task_id,
                summary="A model guard changed or constrained the selected action.",
                intent="Protect Ornith from acting on a stale task/tool mismatch while keeping the guard visible.",
                reversible=True,
                reverse_hint="Accept the guard by continuing, or steer/replan to choose a different task/tool.",
                evidence=[item],
            )
        )

    for index, item in enumerate(pack.edit_evidence_ledger[-3:]):
        add(
            SelfScaffoldChangeRecord(
                id=f"edit_evidence:{index}:{_compact_id(item)}",
                kind="edit_evidence",
                status="observed",
                source="action_context",
                structure_ref=pack.current_task_id or state.current_task_id,
                summary="Edit evidence is attached to the current self-scaffold state.",
                intent="Keep patch-first edits tied to the task graph and acceptance evidence.",
                reversible=True,
                reverse_hint="Inspect or reject the pending patch/workspace promotion before applying to source.",
                evidence=[item],
            )
        )

    if state.goal_evolution.decision_count or state.proposed_goal:
        status = "needs_review" if state.goal_evolution.pending_count or state.proposed_goal else "observed"
        add(
            SelfScaffoldChangeRecord(
                id=f"goal_evolution:{state.goal_evolution.latest_decision.id or state.proposed_goal or 'review'}",
                kind="goal_evolution",
                status=status,
                source=state.goal_evolution.latest_decision.source or "run_state",
                structure_ref=state.goal_evolution.latest_decision.id or "goal_evolution",
                summary=state.goal_evolution.summary or "Goal evolution ledger is attached.",
                intent="Let Ornith propose sharper long-run goals while requiring explicit user confirmation.",
                reversible=True,
                reverse_hint="Accept or reject the pending /goal approval; rejected proposals leave the active goal unchanged.",
                evidence=[
                    f"pending={state.goal_evolution.pending_count}",
                    f"accepted={state.goal_evolution.accepted_count}",
                    f"rejected={state.goal_evolution.rejected_count}",
                ],
            )
        )

    for event in (events or [])[-20:]:
        kind = str(event.get("kind") or "")
        if kind not in {"checkpoint", "context_checkpoint", "goal_proposed", "act_preflight_reorient", "operator_action_dispatched"}:
            continue
        event_id = int(event.get("id") or 0)
        add(
            SelfScaffoldChangeRecord(
                id=f"event:{event_id}:{kind}",
                kind="checkpoint" if kind == "checkpoint" else "event",
                status="observed" if kind != "act_preflight_reorient" else "needs_review",
                source=kind,
                structure_ref=f"event#{event_id}",
                summary=str(event.get("message") or kind)[:240],
                intent="Preserve the compact reason this structural state changed.",
                reversible=True,
                reverse_hint="Use replay or handoff refresh to inspect this event before continuing broad autonomy.",
                evidence=[f"event_id={event_id}", f"kind={kind}"],
                event_id=event_id,
                created_at=str(event.get("timestamp") or ""),
            )
        )

    bounded = changes[-limit:]
    review_events = _self_scaffold_review_events(events or [])
    latest_review = review_events[-1] if review_events else {}
    latest_resolving_review = next(
        (event for event in reversed(review_events) if _reviewed_change_ids(event)),
        latest_review,
    )
    latest_reviewed_change_ids = _reviewed_change_ids(latest_resolving_review)
    latest_review_event_id = int(latest_resolving_review.get("id") or 0) if latest_resolving_review else 0
    if latest_reviewed_change_ids:
        resolved: list[SelfScaffoldChangeRecord] = []
        for item in bounded:
            if (
                item.status == "needs_review"
                and item.kind in REVIEWABLE_REVIEW_KINDS
                and item.id in latest_reviewed_change_ids
            ):
                evidence = [*item.evidence, f"reviewed_event_id={latest_review_event_id}"]
                resolved.append(item.model_copy(update={"status": "observed", "evidence": evidence}))
            else:
                resolved.append(item)
        bounded = resolved
    needs_review = [item for item in bounded if item.status == "needs_review"]
    current_reviewed_change_count = sum(1 for item in bounded if item.id in latest_reviewed_change_ids)
    reviewed_change_count = max(
        current_reviewed_change_count,
        _reviewed_change_count(latest_resolving_review),
    )
    status = "empty" if not bounded else "needs_review" if needs_review else "observed"
    latest = bounded[-1].summary if bounded else ""
    summary = (
        "No self-scaffold change intent recorded."
        if not bounded
        else (
            f"{len(bounded)} self-scaffold change(s): {len(needs_review)} need review, "
            f"{reviewed_change_count} reviewed."
        )
    )
    recommended_action = (
        "Review pending self-scaffold changes before broad autonomy."
        if needs_review
        else "Continue; latest self-scaffold review accepted current guard/reorient changes."
        if reviewed_change_count
        else "Continue; use this ledger to refresh or reverse scaffold changes without raw logs."
    )
    return SelfScaffoldReport(
        run_id=run.id,
        generated_at=utc_stamp(),
        status=status,
        change_count=len(bounded),
        task_graph_count=sum(1 for item in bounded if item.kind == "task_graph"),
        action_context_count=sum(1 for item in bounded if item.kind == "action_context"),
        tool_posture_count=sum(1 for item in bounded if item.kind == "tool_posture"),
        guard_count=sum(1 for item in bounded if item.kind == "model_guard"),
        reversible_count=sum(1 for item in bounded if item.reversible),
        review_count=len(review_events),
        reviewed_change_count=reviewed_change_count,
        latest_reviewed_at=str(latest_resolving_review.get("timestamp") or "") if latest_resolving_review else "",
        latest_review_event_id=latest_review_event_id,
        latest_reviewed_change_ids=sorted(latest_reviewed_change_ids),
        latest_change=latest,
        summary=summary,
        recommended_action=recommended_action,
        changes=bounded,
    )


def _self_scaffold_review_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviewed: list[dict[str, Any]] = []
    for event in events:
        if event.get("kind") != "operator_action_reviewed":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        operator_action = data.get("operator_action") if isinstance(data.get("operator_action"), dict) else {}
        review = data.get("self_scaffold_review") if isinstance(data.get("self_scaffold_review"), dict) else {}
        if operator_action.get("ui_target") == "self_scaffold" or review:
            reviewed.append(event)
    return reviewed


def _reviewed_change_ids(event: dict[str, Any]) -> set[str]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    review = data.get("self_scaffold_review") if isinstance(data.get("self_scaffold_review"), dict) else {}
    values = review.get("reviewed_change_ids") if isinstance(review.get("reviewed_change_ids"), list) else []
    return {str(value) for value in values if str(value).strip()}


def _reviewed_change_count(event: dict[str, Any]) -> int:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    review = data.get("self_scaffold_review") if isinstance(data.get("self_scaffold_review"), dict) else {}
    try:
        return int(review.get("reviewed_change_count") or 0)
    except (TypeError, ValueError):
        return 0


def _task_status_counts(run: RunRecord) -> str:
    statuses: dict[str, int] = {}
    for task in run.state.task_graph:
        statuses[task.status] = statuses.get(task.status, 0) + 1
    return ",".join(f"{key}={value}" for key, value in sorted(statuses.items()))


def _compact_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in value.lower())
    return "-".join(part for part in safe.split("-") if part)[:60] or "item"


def build_self_scaffold_review_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> SelfScaffoldReviewReport:
    entries: list[SelfScaffoldReviewRecord] = []
    for event in reversed(_self_scaffold_review_events(events)):
        entry = _self_scaffold_review_record(event)
        if entry is not None:
            entries.append(entry)
    bounded = entries[: max(1, min(limit, 50))]
    accepted_count = sum(1 for entry in entries if entry.status == "accepted")
    partial_count = sum(1 for entry in entries if entry.status == "partial")
    noop_count = sum(1 for entry in entries if entry.status == "noop")
    reviewed_change_count = sum(entry.reviewed_change_count for entry in entries)
    remaining_goal_review_count = sum(1 for entry in entries if entry.remaining_goal_review)
    latest = entries[0] if entries else None
    if latest is None:
        status = "none"
        summary = "No self-scaffold review outcomes recorded."
        recommended_action = "Review self-scaffold changes before broad autonomy when the supervisor queue requests it."
        latest_event_id = 0
        latest_ids: list[str] = []
    else:
        status = "needs_goal_review" if latest.remaining_goal_review else "reviewed"
        latest_event_id = latest.event_id
        latest_ids = latest.reviewed_change_ids
        summary = (
            f"{len(entries)} self-scaffold review outcome(s): {accepted_count} accepted, "
            f"{partial_count} partial, {noop_count} noop; {reviewed_change_count} change(s) reviewed."
        )
        recommended_action = (
            "Resolve the remaining goal-evolution review before broad autonomy."
            if latest.remaining_goal_review
            else "Continue from the reviewed self-scaffold state; use reverse hints if the accepted guard posture was wrong."
        )
    return SelfScaffoldReviewReport(
        run_id=run.id,
        generated_at=utc_stamp(),
        status=status,  # type: ignore[arg-type]
        total_count=len(entries),
        accepted_count=accepted_count,
        partial_count=partial_count,
        noop_count=noop_count,
        reviewed_change_count=reviewed_change_count,
        remaining_goal_review_count=remaining_goal_review_count,
        latest_event_id=latest_event_id,
        latest_reviewed_change_ids=latest_ids,
        summary=summary,
        recommended_action=recommended_action,
        entries=bounded,
    )


def _self_scaffold_review_record(event: dict[str, Any]) -> SelfScaffoldReviewRecord | None:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    review = data.get("self_scaffold_review") if isinstance(data.get("self_scaffold_review"), dict) else {}
    if not review:
        return None
    values = review.get("reviewed_change_ids") if isinstance(review.get("reviewed_change_ids"), list) else []
    reviewed_ids = [str(value) for value in values if str(value).strip()]
    try:
        reviewed_count = int(review.get("reviewed_change_count") or len(reviewed_ids))
    except (TypeError, ValueError):
        reviewed_count = len(reviewed_ids)
    remaining_goal = bool(review.get("remaining_goal_review"))
    if reviewed_count and remaining_goal:
        status = "partial"
    elif reviewed_count:
        status = "accepted"
    else:
        status = "noop"
    operator_action = data.get("operator_action") if isinstance(data.get("operator_action"), dict) else {}
    return SelfScaffoldReviewRecord(
        event_id=int(event.get("id") or 0),
        timestamp=str(event.get("timestamp") or ""),
        status=status,  # type: ignore[arg-type]
        change_count=_safe_int(review.get("change_count")),
        guard_count=_safe_int(review.get("guard_count")),
        reviewed_change_count=reviewed_count,
        reviewed_change_ids=reviewed_ids[:12],
        remaining_goal_review=remaining_goal,
        action_reason=str(operator_action.get("reason") or ""),
        action_summary=str(operator_action.get("action") or operator_action.get("summary") or ""),
        summary=str(event.get("message") or "Self-scaffold review outcome recorded.")[:280],
    )



def build_self_scaffold_rollback_intent_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    self_scaffold: SelfScaffoldReport | None = None,
    reviews: SelfScaffoldReviewReport | None = None,
    limit: int = 8,
) -> SelfScaffoldRollbackIntentReport:
    scaffold_report = self_scaffold or build_self_scaffold_report(run, events, limit=50)
    review_report = reviews or build_self_scaffold_review_report(run, events, limit=50)
    change_index = {change.id: change for change in scaffold_report.changes}
    latest_patch = _latest_applied_patch(run)
    entries: list[SelfScaffoldRollbackIntentRecord] = []
    seen: set[str] = set()

    for review in review_report.entries:
        if review.status == "noop":
            continue
        for change_id in review.reviewed_change_ids:
            key = f"{review.event_id}:{change_id}"
            if key in seen:
                continue
            seen.add(key)
            change = change_index.get(change_id)
            if change is None:
                patchish_review = "patch" in change_id.lower() or "edit_evidence" in change_id.lower()
                action_kind = "patch_rollback" if latest_patch is not None and patchish_review else "steer"
                reverse_hint = (
                    "Reviewed patch/edit evidence can be reversed only through an explicit patch rollback approval."
                    if action_kind == "patch_rollback"
                    else "Inspect replay for this accepted self-scaffold change before reversing it."
                )
                summary = (
                    f"Accepted self-scaffold change {change_id} maps to applied patch backup {latest_patch.backup_id}; request patch rollback approval before acting."
                    if action_kind == "patch_rollback" and latest_patch is not None
                    else f"Accepted self-scaffold change {change_id} has no current compact change row; use steering or replay before acting."
                )
                evidence = [f"review_event_id={review.event_id}", f"reviewed_change_id={change_id}", "change_row=missing"]
                change_kind = "edit_evidence" if patchish_review else "unknown"
            else:
                action_kind = _rollback_action_kind(change, latest_patch is not None)
                reverse_hint = change.reverse_hint
                summary = _rollback_intent_summary(change, action_kind)
                evidence = [
                    f"review_event_id={review.event_id}",
                    f"review_status={review.status}",
                    f"change_source={change.source}",
                    f"structure_ref={change.structure_ref}",
                    *change.evidence[:3],
                ]
                change_kind = change.kind
            patch = latest_patch if action_kind == "patch_rollback" else None
            rolled_back = bool(patch and _patch_was_rolled_back(run, patch.patch_id, patch.backup_id))
            status = "resolved" if rolled_back else "needs_approval" if patch else "suggested"
            entries.append(
                SelfScaffoldRollbackIntentRecord(
                    id=f"rollback-intent:{review.event_id}:{_compact_id(change_id)}",
                    source_review_event_id=review.event_id,
                    reviewed_change_id=change_id,
                    change_kind=change_kind,
                    action_kind=action_kind,  # type: ignore[arg-type]
                    status=status,  # type: ignore[arg-type]
                    proposed_tool="patch_rollback" if patch else _proposed_tool_for_action(action_kind),
                    requires_approval=bool(patch and not rolled_back),
                    mutation_automatic=False,
                    patch_id=patch.patch_id if patch else "",
                    backup_id=patch.backup_id if patch else "",
                    rollback_manifest_path=patch.manifest_path if patch else "",
                    files=patch.files[:8] if patch else [],
                    reverse_hint=reverse_hint,
                    summary=summary,
                    evidence=evidence,
                )
            )

    bounded = entries[: max(1, min(limit, 50))]
    patch_rollback_count = sum(1 for entry in entries if entry.action_kind == "patch_rollback")
    steering_count = sum(1 for entry in entries if entry.action_kind != "patch_rollback")
    latest_review_event_id = max((entry.source_review_event_id for entry in entries), default=0)
    if not entries:
        status = "none"
        summary = "No accepted self-scaffold reverse hints have produced rollback or steering intent yet."
        recommended_action = "Continue; use self-scaffold reverse hints if accepted guard posture proves wrong."
    elif any(entry.status == "needs_approval" for entry in entries):
        status = "needs_approval"
        summary = (
            f"{len(entries)} self-scaffold rollback/steering intent(s): "
            f"{patch_rollback_count} patch rollback candidate(s), {steering_count} steering intent(s)."
        )
        recommended_action = "Review the patch rollback intent explicitly; do not mutate the workspace automatically."
    elif all(entry.status == "resolved" for entry in entries):
        status = "resolved"
        summary = f"{len(entries)} self-scaffold rollback intent(s) are already resolved."
        recommended_action = "Continue from the resolved self-scaffold recovery state."
    else:
        status = "available"
        summary = (
            f"{len(entries)} self-scaffold rollback/steering intent(s): "
            f"{patch_rollback_count} patch rollback candidate(s), {steering_count} steering intent(s)."
        )
        recommended_action = "Use steering, handoff refresh, or explicit patch review if the accepted scaffold posture proves wrong."
    return SelfScaffoldRollbackIntentReport(
        run_id=run.id,
        generated_at=utc_stamp(),
        status=status,  # type: ignore[arg-type]
        intent_count=len(entries),
        patch_rollback_count=patch_rollback_count,
        steering_count=steering_count,
        latest_review_event_id=latest_review_event_id,
        summary=summary,
        recommended_action=recommended_action,
        entries=bounded,
    )


def _rollback_action_kind(change: SelfScaffoldChangeRecord, has_applied_patch: bool) -> str:
    text = f"{change.kind} {change.summary} {change.reverse_hint}".lower()
    if "patch" in text or "workspace promotion" in text or "workspace_promote" in text:
        return "patch_rollback" if has_applied_patch else "patch_review"
    if change.kind == "goal_evolution":
        return "goal_review"
    if change.kind in {"action_context", "checkpoint", "event"} and ("handoff" in text or "replay" in text):
        return "handoff_refresh"
    return "steer"


def _rollback_intent_summary(change: SelfScaffoldChangeRecord, action_kind: str) -> str:
    if action_kind == "patch_rollback":
        return f"Accepted reverse hint for {change.kind} can be turned into an explicit patch rollback review."
    if action_kind == "patch_review":
        return f"Accepted reverse hint for {change.kind} points at patch/workspace evidence; inspect patch state before acting."
    if action_kind == "goal_review":
        return "Accepted reverse hint points at goal evolution; resolve /goal review rather than mutating code."
    if action_kind == "handoff_refresh":
        return "Accepted reverse hint points at stale context; refresh handoff/replay before continuing."
    return f"Accepted reverse hint for {change.kind} should become a steering or replan note if the scaffold was wrong."


def _proposed_tool_for_action(action_kind: str) -> str:
    return {
        "patch_review": "patch_propose",
        "goal_review": "ask_user",
        "handoff_refresh": "obsidian_checkpoint",
        "steer": "ask_user",
    }.get(action_kind, "ask_user")


def _latest_applied_patch(run: RunRecord):
    for patch in reversed(run.state.patch_applications):
        if patch.status == "applied" and patch.backup_id and patch.manifest_path:
            return patch
    return None


def _patch_was_rolled_back(run: RunRecord, patch_id: str, backup_id: str) -> bool:
    for patch in reversed(run.state.patch_applications):
        if patch.status != "rolled_back":
            continue
        if patch_id and patch.patch_id == patch_id:
            return True
        if backup_id and patch.backup_id == backup_id:
            return True
    return False
def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
