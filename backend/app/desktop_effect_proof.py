from __future__ import annotations

from typing import Any

from .persistence import utc_now
from .schemas import (
    DesktopEffectProofRepairRecord,
    DesktopEffectProofRepairReport,
    DesktopEffectProofReport,
    DesktopSnapshot,
    RunRecord,
    ToolCallRecord,
)
from .tools import redact_secrets


DESKTOP_EFFECT_TOOLS = {"desktop_click", "desktop_type"}
DESKTOP_PROOF_TOOLS = {"desktop_screenshot", "desktop_window_list"}


def build_desktop_effect_proof_preview(run: RunRecord, *, limit: int = 5) -> DesktopEffectProofReport:
    state = run.state
    latest_action_index = _latest_successful_index(state.tool_calls, DESKTOP_EFFECT_TOOLS)
    latest_action = state.tool_calls[latest_action_index] if latest_action_index >= 0 else None
    proof_calls = _successful_calls_after(state.tool_calls, latest_action_index, DESKTOP_PROOF_TOOLS)
    latest_proof = proof_calls[-1] if proof_calls else None
    desktop_snapshots = _desktop_snapshots(state.desktop_snapshots)
    proof_snapshot = desktop_snapshots[-1] if latest_proof and latest_proof.name == "desktop_screenshot" and desktop_snapshots else None
    requires_attention = latest_action is not None and latest_proof is None
    status = "not_required"
    if latest_action and requires_attention:
        status = "needs_proof"
    elif latest_action and latest_proof:
        status = "proof_available"

    return DesktopEffectProofReport(
        run_id=run.id,
        generated_at=utc_now(),
        status=status,
        requires_attention=requires_attention,
        latest_action_id=latest_action.id if latest_action else "",
        latest_action_tool=latest_action.name if latest_action else "",
        latest_action_created_at=latest_action.created_at if latest_action else "",
        latest_action_summary=_compact_summary(latest_action.summary if latest_action else "", 220),
        proof_call_id=latest_proof.id if latest_proof else "",
        proof_tool=latest_proof.name if latest_proof else "",
        proof_created_at=latest_proof.created_at if latest_proof else "",
        proof_summary=_compact_summary(latest_proof.summary if latest_proof else "", 220),
        proof_snapshot=proof_snapshot,
        proof_snapshot_count=len(desktop_snapshots),
        ledger=_proof_ledger(latest_action, latest_proof, proof_snapshot, limit=limit),
        recommended_action=_recommended_action(status, state.desktop_enabled),
    )


def _latest_successful_index(calls: list[ToolCallRecord], names: set[str]) -> int:
    for index in range(len(calls) - 1, -1, -1):
        call = calls[index]
        if call.ok and call.name in names:
            return index
    return -1


def _successful_calls_after(calls: list[ToolCallRecord], index: int, names: set[str]) -> list[ToolCallRecord]:
    if index < 0:
        return []
    return [call for call in calls[index + 1 :] if call.ok and call.name in names]


def _desktop_snapshots(snapshots: list[DesktopSnapshot]) -> list[DesktopSnapshot]:
    return [
        snapshot
        for snapshot in snapshots
        if snapshot.id.startswith("desktop-") or snapshot.title.lower().startswith("desktop")
    ]


def _proof_ledger(
    latest_action: ToolCallRecord | None,
    latest_proof: ToolCallRecord | None,
    proof_snapshot: DesktopSnapshot | None,
    *,
    limit: int,
) -> list[str]:
    ledger: list[str] = []
    if latest_action:
        ledger.append(
            _compact_summary(
                f"action={latest_action.name}:id={latest_action.id}:at={latest_action.created_at}:summary={latest_action.summary}",
                320,
            )
        )
    if latest_proof:
        ledger.append(
            _compact_summary(
                f"proof={latest_proof.name}:id={latest_proof.id}:at={latest_proof.created_at}:summary={latest_proof.summary}",
                320,
            )
        )
    if proof_snapshot:
        ledger.append(
            _compact_summary(
                f"snapshot={proof_snapshot.id}:title={proof_snapshot.title}:at={proof_snapshot.timestamp}:path={proof_snapshot.path}:summary={proof_snapshot.summary}",
                360,
            )
        )
    return ledger[: max(1, min(8, limit))]


def _recommended_action(status: str, desktop_enabled: bool) -> str:
    if status == "needs_proof" and desktop_enabled:
        return "Capture desktop_screenshot or desktop_window_list proof before another desktop click/type."
    if status == "needs_proof":
        return "Desktop proof is required, but desktop inspection tools are disabled; ask the user to verify the visible effect."
    if status == "proof_available":
        return "Desktop effect proof is current; continue only if the visible state matches the intended action."
    return "No desktop click/type effect is waiting for visual proof."


def _compact_summary(value: str, limit: int) -> str:
    text = " ".join(redact_secrets(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def build_desktop_effect_proof_repairs(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> DesktopEffectProofRepairReport:
    entries: list[DesktopEffectProofRepairRecord] = []
    for event in sorted(events, key=lambda item: int(item.get("id") or 0), reverse=True):
        record = _repair_record_from_event(event)
        if record is not None:
            entries.append(record)
    bounded = entries[: max(1, min(limit, 50))]
    metadata_count = sum(1 for entry in entries if entry.outcome == "metadata_refreshed")
    capture_count = sum(1 for entry in entries if entry.outcome == "capture_completed")
    capture_failed_count = sum(1 for entry in entries if entry.outcome == "capture_failed")
    blocked_count = sum(1 for entry in entries if entry.outcome == "blocked")
    skipped_count = sum(1 for entry in entries if entry.outcome == "skipped_noop")
    latest = entries[0] if entries else None
    if latest is None:
        summary = "No desktop effect proof repair outcomes recorded."
        recommended_action = "Use Desktop Effect Proof only when a desktop action needs proof or handoff proof metadata is stale."
        latest_outcome = ""
    else:
        latest_outcome = latest.outcome
        summary = (
            f"{len(entries)} desktop proof repair outcome(s): {metadata_count} metadata refresh, "
            f"{capture_count} capture, {blocked_count} blocked."
        )
        if latest.outcome == "metadata_refreshed":
            recommended_action = "Use the refreshed handoff proof metadata; no new screenshot was needed for the latest repair."
        elif latest.outcome == "capture_completed":
            recommended_action = "Review the captured desktop proof before another desktop click/type."
        elif latest.outcome == "blocked":
            recommended_action = "Resolve desktop inspection availability or ask the user to verify the visible effect."
        elif latest.outcome == "capture_failed":
            recommended_action = "Inspect the failed proof capture before allowing another desktop action."
        else:
            recommended_action = "No proof repair was needed for the latest Desktop Effect Proof action."
    return DesktopEffectProofRepairReport(
        run_id=run.id,
        generated_at=utc_now(),
        total_count=len(entries),
        metadata_refreshed_count=metadata_count,
        capture_completed_count=capture_count,
        capture_failed_count=capture_failed_count,
        blocked_count=blocked_count,
        skipped_noop_count=skipped_count,
        latest_outcome=latest_outcome,
        summary=summary,
        recommended_action=recommended_action,
        entries=bounded,
    )


def _repair_record_from_event(event: dict[str, Any]) -> DesktopEffectProofRepairRecord | None:
    kind = str(event.get("kind") or "")
    if kind not in {
        "desktop_effect_proof_repaired",
        "desktop_effect_proof_captured",
        "desktop_effect_proof_blocked",
        "desktop_effect_proof_skipped",
    }:
        return None
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    repair = data.get("desktop_effect_proof_repair") if isinstance(data.get("desktop_effect_proof_repair"), dict) else {}
    previous_integrity = _dict_value(repair.get("previous_report_integrity") or data.get("previous_report_integrity"))
    refreshed_integrity = _dict_value(repair.get("refreshed_report_integrity") or data.get("report_integrity"))
    previous_proof = _dict_value(repair.get("previous_desktop_effect_proof") or data.get("previous_desktop_effect_proof"))
    refreshed_proof = _dict_value(repair.get("refreshed_desktop_effect_proof") or data.get("desktop_effect_proof"))
    reasons = _string_items(repair.get("report_integrity_refresh_reasons") or data.get("report_integrity_refresh_reasons"))
    outcome = str(repair.get("outcome") or "")
    if not outcome:
        if kind == "desktop_effect_proof_captured":
            outcome = "capture_completed"
        elif kind == "desktop_effect_proof_blocked":
            outcome = "blocked"
        elif kind == "desktop_effect_proof_repaired":
            outcome = "metadata_refreshed"
        else:
            outcome = "skipped_noop"
    if outcome not in {"metadata_refreshed", "capture_completed", "capture_failed", "blocked", "skipped_noop"}:
        outcome = "skipped_noop"
    proof_snapshot = refreshed_proof.get("proof_snapshot") if isinstance(refreshed_proof.get("proof_snapshot"), dict) else {}
    return DesktopEffectProofRepairRecord(
        event_id=int(event.get("id") or 0),
        timestamp=str(event.get("timestamp") or ""),
        outcome=outcome,  # type: ignore[arg-type]
        previous_integrity_status=str(previous_integrity.get("status") or ""),
        refreshed_integrity_status=str(refreshed_integrity.get("status") or ""),
        previous_proof_status=str(previous_proof.get("status") or ""),
        refreshed_proof_status=str(refreshed_proof.get("status") or ""),
        latest_action_id=str(refreshed_proof.get("latest_action_id") or previous_proof.get("latest_action_id") or ""),
        proof_call_id=str(refreshed_proof.get("proof_call_id") or previous_proof.get("proof_call_id") or ""),
        proof_snapshot_id=str(proof_snapshot.get("id") or ""),
        reason_count=int(repair.get("refresh_reason_count") or data.get("refresh_reason_count") or len(reasons)),
        reasons=reasons[:8],
        summary=_compact_summary(str(repair.get("summary") or event.get("message") or ""), 280),
    )


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_compact_summary(str(item), 240) for item in value if str(item).strip()]