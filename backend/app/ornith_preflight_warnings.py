from __future__ import annotations

from typing import Any

from .persistence import utc_now
from .schemas import (
    OrnithLaunchChecklistReport,
    OrnithPreflightWarningRecord,
    OrnithPreflightWarningReport,
)


def build_ornith_preflight_warning_report(
    run_id: str,
    events: list[dict[str, Any]],
    ornith_preflight: OrnithLaunchChecklistReport,
    *,
    limit: int = 12,
    include_checklist: bool = True,
) -> OrnithPreflightWarningReport:
    entries: list[OrnithPreflightWarningRecord] = []

    if include_checklist:
        for item in ornith_preflight.items:
            if item.status == "pass":
                continue
            entries.append(
                OrnithPreflightWarningRecord(
                    source="checklist",
                    item_id=item.id,
                    status=item.status,  # type: ignore[arg-type]
                    summary=_single_line(item.summary, 360),
                    evidence=[_single_line(value, 180) for value in item.evidence[:8]],
                    next_action=_single_line(item.next_action, 260),
                )
            )

    for event in events:
        if event.get("kind") != "act_preflight_reorient":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        context = data.get("handoff_action_context") if isinstance(data.get("handoff_action_context"), dict) else {}
        if not context:
            continue
        raw_status = str(context.get("status") or "warn")
        status = raw_status if raw_status in {"warn", "block"} else "warn"
        entries.append(
            OrnithPreflightWarningRecord(
                event_id=int(event.get("id") or 0),
                timestamp=str(event.get("timestamp") or ""),
                source="act_preflight_reorient",
                item_id="handoff_action_context",
                status=status,  # type: ignore[arg-type]
                summary=_single_line(str(context.get("summary") or event.get("message") or ""), 420),
                evidence=[_single_line(str(value), 180) for value in (context.get("evidence") or [])[:8]],
                next_action=_single_line(str(context.get("next_action") or ""), 280),
                message=_single_line(str(event.get("message") or ""), 420),
            )
        )

    entries = entries[-limit:]
    warning_count = sum(1 for entry in entries if entry.status == "warn")
    block_count = sum(1 for entry in entries if entry.status == "block")
    reorient_entries = [entry for entry in entries if entry.source == "act_preflight_reorient"]
    latest = entries[-1] if entries else OrnithPreflightWarningRecord()
    latest_reorient = reorient_entries[-1] if reorient_entries else OrnithPreflightWarningRecord()
    recommended_action = next((entry.next_action for entry in reversed(entries) if entry.next_action), "")
    if entries:
        summary = (
            f"{len(entries)} Ornith preflight warning record(s): "
            f"warnings={warning_count}, blocks={block_count}, action-context reorients={len(reorient_entries)}."
        )
    else:
        summary = "No Ornith preflight warnings recorded."
    return OrnithPreflightWarningReport(
        run_id=run_id,
        generated_at=utc_now(),
        total_count=len(entries),
        warning_count=warning_count,
        block_count=block_count,
        action_context_reorient_count=len(reorient_entries),
        latest_reorient_event_id=latest_reorient.event_id,
        latest_warning=latest.summary,
        summary=summary,
        recommended_action=recommended_action,
        entries=entries,
    )


def _single_line(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."