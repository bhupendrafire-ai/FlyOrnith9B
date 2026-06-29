from __future__ import annotations

from typing import Any


def approval_review_event_index(events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}
    for event in events:
        if event.get("kind") != "operator_action_reviewed":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        action = data.get("operator_action") if isinstance(data.get("operator_action"), dict) else {}
        approval_id = int(action.get("approval_id") or 0)
        if approval_id <= 0:
            continue
        current = index.setdefault(
            approval_id,
            {"review_count": 0, "latest_reviewed_at": "", "latest_review_event_id": 0},
        )
        current["review_count"] = int(current.get("review_count") or 0) + 1
        event_id = int(event.get("id") or 0)
        if event_id >= int(current.get("latest_review_event_id") or 0):
            current["latest_review_event_id"] = event_id
            current["latest_reviewed_at"] = str(event.get("timestamp") or "")
    return index


def approval_review_label(
    action_kind: str,
    status: str,
    *,
    review_count: int = 0,
    latest_review_event_id: int = 0,
) -> str:
    review_state = "reviewed" if review_count > 0 else "unreviewed"
    label = f"{action_kind}:{status}:{review_state}"
    if review_count:
        label = f"{label}:x{review_count}"
    if latest_review_event_id:
        label = f"{label}:event#{latest_review_event_id}"
    return label


def approval_review_label_from_record(
    approval: dict[str, Any],
    review_meta: dict[str, Any] | None = None,
) -> str:
    review_meta = review_meta or approval
    return approval_review_label(
        str(approval.get("action_kind") or ""),
        str(approval.get("status") or ""),
        review_count=int(review_meta.get("review_count") or 0),
        latest_review_event_id=int(review_meta.get("latest_review_event_id") or 0),
    )