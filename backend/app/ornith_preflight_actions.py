from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import OrnithPreflightActionLedgerEntry, OrnithPreflightActionLedgerReport


def build_ornith_preflight_action_ledger(
    events: list[dict[str, Any]],
    *,
    run_id: str = "",
    limit: int = 20,
) -> OrnithPreflightActionLedgerReport:
    completed_reasons = {
        str(_event_action(event).get("reason") or "")
        for event in events
        if str(event.get("kind") or "") == "ornith_preflight_action"
    }
    entries: list[OrnithPreflightActionLedgerEntry] = []
    for event in sorted(events, key=lambda item: int(item.get("id") or 0), reverse=True):
        kind = str(event.get("kind") or "")
        action = _event_action(event)
        reason = str(action.get("reason") or "")
        if kind == "ornith_preflight_action":
            status = "completed"
        elif kind == "operator_action_dispatched" and reason.startswith("ornith_preflight_") and reason not in completed_reasons:
            status = "dispatched"
        else:
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        context_budget = data.get("context_budget") if isinstance(data.get("context_budget"), dict) else {}
        entries.append(
            OrnithPreflightActionLedgerEntry(
                event_id=int(event.get("id") or 0),
                run_id=str(event.get("run_id") or action.get("run_id") or run_id),
                timestamp=str(event.get("timestamp") or ""),
                kind=kind,
                status=status,  # type: ignore[arg-type]
                item_id=_item_id(reason),
                action_reason=_single_line(reason, 160),
                action_summary=_single_line(str(action.get("action") or ""), 260),
                ui_target=str(action.get("ui_target") or ""),
                context_pressure=str(context_budget.get("pressure") or ""),
                context_tokens=int(context_budget.get("estimated_tokens") or 0),
                context_target_tokens=int(context_budget.get("target_tokens") or 0),
                message=_single_line(str(event.get("message") or ""), 300),
                details=[
                    _single_line(str(item), 180)
                    for item in (action.get("details") if isinstance(action.get("details"), list) else [])[:4]
                ],
            )
        )

    bounded = entries[: max(1, min(limit, 100))]
    completed_count = sum(1 for entry in entries if entry.status == "completed")
    dispatched_count = sum(1 for entry in entries if entry.status == "dispatched")
    context_count = sum(1 for entry in entries if entry.ui_target == "context_checkpoint")
    handoff_count = sum(1 for entry in entries if entry.ui_target == "handoff_refresh")
    smoke_count = sum(
        1
        for entry in entries
        if entry.ui_target in {"readiness_rehearsal", "operator_dispatch_restart_smoke"}
    )
    latest = entries[0] if entries else None
    if latest is None:
        summary = "No Ornith preflight actions have been dispatched."
        recommended_action = "Use the operator queue when Ornith preflight reports warning or blocked items."
        latest_action = ""
    else:
        latest_action = f"{latest.status}:{latest.ui_target or latest.item_id}"
        summary = (
            f"{len(entries)} Ornith preflight action event(s): {completed_count} completed, "
            f"{dispatched_count} dispatched/pending completion."
        )
        if dispatched_count:
            recommended_action = "Check whether dispatched preflight actions completed before resuming autonomy."
        else:
            recommended_action = "Use completed preflight actions as compact resume evidence."

    return OrnithPreflightActionLedgerReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        total_count=len(entries),
        completed_count=completed_count,
        dispatched_count=dispatched_count,
        context_checkpoint_count=context_count,
        handoff_refresh_count=handoff_count,
        smoke_count=smoke_count,
        latest_action=latest_action,
        summary=summary,
        recommended_action=recommended_action,
        entries=bounded,
    )


def _event_action(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    action = data.get("operator_action") if isinstance(data.get("operator_action"), dict) else {}
    return action


def _item_id(reason: str) -> str:
    if reason.startswith("ornith_preflight_"):
        return reason.removeprefix("ornith_preflight_")
    return reason


def _single_line(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."