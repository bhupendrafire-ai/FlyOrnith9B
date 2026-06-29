from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import OperatorApprovalHistory, OperatorDispatchLedgerEntry, OperatorDispatchLedgerReport

OPERATOR_DISPATCH_EVENT_STATUS = {
    "operator_action_confirmation_required": "confirmation_required",
    "operator_action_reviewed": "reviewed",
    "operator_action_dispatched": "dispatched",
    "operator_action_blocked": "blocked",
}


def build_operator_dispatch_ledger(
    events: list[dict[str, Any]],
    *,
    run_id: str = "",
    limit: int = 20,
) -> OperatorDispatchLedgerReport:
    entries: list[OperatorDispatchLedgerEntry] = []
    for event in sorted(events, key=lambda item: int(item.get("id") or 0), reverse=True):
        kind = str(event.get("kind") or "")
        status = OPERATOR_DISPATCH_EVENT_STATUS.get(kind)
        if not status:
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        action = data.get("operator_action") if isinstance(data.get("operator_action"), dict) else {}
        entries.append(
            OperatorDispatchLedgerEntry(
                event_id=int(event.get("id") or 0),
                run_id=str(event.get("run_id") or action.get("run_id") or run_id),
                timestamp=str(event.get("timestamp") or ""),
                kind=kind,
                status=status,  # type: ignore[arg-type]
                decision=str(data.get("decision") or ""),
                confirmed=bool(data.get("confirmed") or False),
                action_reason=_single_line(str(action.get("reason") or ""), 120),
                action_title=_single_line(str(action.get("title") or ""), 160),
                action_summary=_single_line(str(action.get("action") or ""), 240),
                ui_target=str(action.get("ui_target") or ""),
                approval_id=int(action.get("approval_id") or 0),
                approval_kind=_single_line(str(action.get("approval_kind") or ""), 80),
                endpoint=_single_line(str(action.get("endpoint") or ""), 180),
                details=[_single_line(str(item), 180) for item in _list_items(action.get("details"))[:6]],
                message=_single_line(str(event.get("message") or ""), 300),
                note_supplied=bool(data.get("note_supplied") or False),
            )
        )

    bounded_limit = max(1, min(limit, 100))
    bounded = entries[:bounded_limit]
    approval_histories = _approval_histories(entries)
    unresolved_approval_histories = [history for history in approval_histories if history.latest_status != "dispatched"]
    promotion_routes = [entry for entry in entries if entry.action_reason.startswith("promotion_audit")]
    promotion_approval_routes = [entry for entry in promotion_routes if entry.ui_target == "approval" and entry.approval_id > 0]
    promotion_approval_ids = {entry.approval_id for entry in promotion_approval_routes}
    promotion_approval_histories = [
        history for history in approval_histories if history.approval_id in promotion_approval_ids
    ]
    unresolved_promotion_approval_histories = [
        history for history in promotion_approval_histories if history.latest_status != "dispatched"
    ]
    dispatched_count = sum(1 for entry in entries if entry.status == "dispatched")
    confirmation_count = sum(1 for entry in entries if entry.status == "confirmation_required")
    reviewed_count = sum(1 for entry in entries if entry.status == "reviewed")
    blocked_count = sum(1 for entry in entries if entry.status == "blocked")
    latest = entries[0] if entries else None
    if latest is None:
        summary = "No operator dispatch activity recorded."
        recommended_action = "Use the operator queue when a run needs human supervision."
        latest_action = ""
    else:
        latest_action = f"{latest.status}:{latest.decision or latest.action_reason or latest.ui_target}"
        summary = (
            f"{len(entries)} operator dispatch event(s): {dispatched_count} dispatched, "
            f"{confirmation_count} confirmation-required, {reviewed_count} reviewed, {blocked_count} blocked."
        )
        if blocked_count:
            recommended_action = "Review blocked operator actions before resuming affected runs."
        elif confirmation_count and not dispatched_count:
            recommended_action = "Confirm or cancel pending operator actions from the queue."
        elif dispatched_count:
            recommended_action = "Use dispatched operator actions as compact supervision evidence in handoff/replay."
        else:
            recommended_action = "Continue reviewing queued actions as needed."

    return OperatorDispatchLedgerReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        total_count=len(entries),
        dispatched_count=dispatched_count,
        confirmation_required_count=confirmation_count,
        reviewed_count=reviewed_count,
        blocked_count=blocked_count,
        latest_action=latest_action,
        summary=summary,
        recommended_action=recommended_action,
        approval_history_count=len(approval_histories),
        unresolved_approval_history_count=len(unresolved_approval_histories),
        promotion_route_count=len(promotion_routes),
        promotion_approval_route_count=len(promotion_approval_routes),
        promotion_approval_history_count=len(promotion_approval_histories),
        unresolved_promotion_approval_history_count=len(unresolved_promotion_approval_histories),
        approval_histories=approval_histories[:bounded_limit],
        unresolved_approval_histories=unresolved_approval_histories[:bounded_limit],
        promotion_approval_histories=promotion_approval_histories[:bounded_limit],
        unresolved_promotion_approval_histories=unresolved_promotion_approval_histories[:bounded_limit],
        promotion_routes=promotion_routes[:bounded_limit],
        entries=bounded,
    )


def _approval_histories(entries: list[OperatorDispatchLedgerEntry]) -> list[OperatorApprovalHistory]:
    grouped: dict[int, list[OperatorDispatchLedgerEntry]] = {}
    for entry in entries:
        if entry.approval_id <= 0:
            continue
        grouped.setdefault(entry.approval_id, []).append(entry)
    histories: list[OperatorApprovalHistory] = []
    for approval_id, items in grouped.items():
        ordered = sorted(items, key=lambda item: item.event_id)
        latest = max(items, key=lambda item: item.event_id)
        histories.append(
            OperatorApprovalHistory(
                approval_id=approval_id,
                run_id=latest.run_id,
                event_count=len(items),
                reviewed_count=sum(1 for item in items if item.status == "reviewed"),
                confirmation_required_count=sum(1 for item in items if item.status == "confirmation_required"),
                dispatched_count=sum(1 for item in items if item.status == "dispatched"),
                blocked_count=sum(1 for item in items if item.status == "blocked"),
                latest_event_id=latest.event_id,
                latest_timestamp=latest.timestamp,
                latest_status=latest.status,
                latest_decision=latest.decision,
                action_reason=latest.action_reason,
                action_title=latest.action_title,
                action_summary=latest.action_summary,
                approval_kind=latest.approval_kind,
                ui_target=latest.ui_target,
                sequence=[_sequence_item(item) for item in ordered[-8:]],
            )
        )
    histories.sort(key=lambda item: item.latest_event_id, reverse=True)
    return histories


def _sequence_item(entry: OperatorDispatchLedgerEntry) -> str:
    detail = entry.decision or entry.ui_target or entry.action_reason
    suffix = f":{detail}" if detail else ""
    return f"{entry.status}#{entry.event_id}{suffix}"


def _list_items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _single_line(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."