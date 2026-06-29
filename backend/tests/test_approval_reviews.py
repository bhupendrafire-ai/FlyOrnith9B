from __future__ import annotations

from app.approval_reviews import approval_review_event_index, approval_review_label, approval_review_label_from_record


def review_event(event_id: int, approval_id: int, timestamp: str) -> dict:
    return {
        "id": event_id,
        "timestamp": timestamp,
        "kind": "operator_action_reviewed",
        "message": "reviewed",
        "data": {"operator_action": {"approval_id": approval_id}},
    }


def test_approval_review_event_index_counts_multiple_reviews_and_uses_latest_event() -> None:
    index = approval_review_event_index(
        [
            review_event(2, 17, "2026-06-28T10:00:00+00:00"),
            {"id": 3, "kind": "operator_action_dispatched", "timestamp": "2026-06-28T10:01:00+00:00", "data": {}},
            review_event(5, 17, "2026-06-28T10:05:00+00:00"),
            review_event(4, 23, "2026-06-28T10:04:00+00:00"),
            review_event(1, 0, "2026-06-28T09:59:00+00:00"),
        ]
    )

    assert index[17]["review_count"] == 2
    assert index[17]["latest_review_event_id"] == 5
    assert index[17]["latest_reviewed_at"] == "2026-06-28T10:05:00+00:00"
    assert index[23]["review_count"] == 1
    assert 0 not in index


def test_approval_review_label_formats_review_state() -> None:
    assert approval_review_label("shell", "pending") == "shell:pending:unreviewed"
    assert (
        approval_review_label("shell", "pending", review_count=2, latest_review_event_id=5)
        == "shell:pending:reviewed:x2:event#5"
    )
    assert (
        approval_review_label_from_record(
            {"action_kind": "workspace_promote", "status": "pending"},
            {"review_count": 1, "latest_review_event_id": 9},
        )
        == "workspace_promote:pending:reviewed:x1:event#9"
    )