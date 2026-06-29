from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import api as api_module
from app.engine import AgentLoopEngine
from app.events import EventBroker
from app.memory import MemoryContext, ObsidianMemory
from app.persistence import RunStore
from app.tools import ToolResult
from app.schemas import DesktopSnapshot, OperatorDispatchLedgerReport

from conftest import make_config


class FakeModel:
    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.2, max_tokens: int = 1200) -> str:
        return '{"should_update": false, "proposed_goal": "", "reason": ""}'


def install_runtime(monkeypatch: Any, tmp_path: Path) -> tuple[TestClient, AgentLoopEngine, RunStore]:
    config = make_config(tmp_path)
    store = RunStore(config.sqlite_path)
    memory = ObsidianMemory(config.obsidian_vault_path)
    broker = EventBroker()
    engine = AgentLoopEngine(config, store, memory, FakeModel(), broker)  # type: ignore[arg-type]
    monkeypatch.setattr(api_module, "config", config)
    monkeypatch.setattr(api_module, "store", store)
    monkeypatch.setattr(api_module, "memory", memory)
    monkeypatch.setattr(api_module, "broker", broker)
    monkeypatch.setattr(api_module, "engine", engine)
    return TestClient(api_module.app), engine, store


def create_desktop_approval(store: RunStore, tmp_path: Path, *, action_kind: str, title: str) -> tuple[Any, dict[str, Any]]:
    run = store.create_run(
        f"Resolve supervised {action_kind} approval",
        title,
        str(tmp_path),
        [],
    )
    run.state.blockers.append("Manual follow-up after supervised desktop approval keeps resume preflight paused.")
    approval = store.create_approval(
        run.id,
        action_kind,
        {
            "tool_name": action_kind,
            "args": {
                "x": 240,
                "y": 540,
                "text": "visible non-secret text" if action_kind == "desktop_type" else "",
                "window_title": "AgentOrinth Dashboard",
            },
        },
        f"Approve supervised {action_kind} in the visible dashboard.",
    )
    store.update_run(run.id, status="waiting_approval", state=run.state)
    return run, approval


def test_desktop_approval_preview_includes_target_and_latest_snapshot(monkeypatch: Any, tmp_path: Path) -> None:
    _client, engine, store = install_runtime(monkeypatch, tmp_path)
    run = store.create_run(
        "Preview supervised desktop typing approval",
        "Desktop approval preview",
        str(tmp_path),
        [],
    )
    run.state.desktop_snapshots.extend(
        [
            DesktopSnapshot(
                id="browser-old",
                timestamp="2026-06-29T00:00:00+00:00",
                title="Browser screenshot",
                path=str(tmp_path / "browser.png"),
                summary="Browser screenshot should not be used for desktop target preview.",
            ),
            DesktopSnapshot(
                id="desktop-latest",
                timestamp="2026-06-29T00:01:00+00:00",
                title="Desktop screenshot - AgentOrinth Dashboard",
                path=str(tmp_path / "desktop.png"),
                summary="Visible dashboard before supervised desktop typing.",
            ),
        ]
    )
    store.update_run(run.id, state=run.state)
    result = ToolResult(
        False,
        "desktop_type",
        "Supervised desktop typing needs approval.",
        {
            "x": 240,
            "y": 540,
            "window_title": "AgentOrinth Dashboard",
            "text": "api_key=super-secret should be redacted",
        },
        needs_approval=True,
    )

    payload = engine._approval_payload_for_tool_result(run.state, result)
    approval = store.create_approval(run.id, result.kind, payload, result.summary)
    review = engine.get_approval_reviews(run.id, status="pending")[0]
    preview = review["preview"]
    fields = {field["label"]: field["value"] for field in preview["fields"]}

    assert approval["payload"]["preview"]["desktop_snapshot"]["id"] == "desktop-latest"
    assert preview["tool_name"] == "desktop_type"
    assert preview["high_risk"] is True
    assert preview["requires_supervision"] is True
    assert preview["desktop_snapshot"]["id"] == "desktop-latest"
    assert fields["tool"] == "desktop_type"
    assert fields["x"] == "240"
    assert fields["y"] == "540"
    assert fields["window"] == "AgentOrinth Dashboard"
    assert fields["screenshot"] == "desktop-latest"
    assert fields["screenshot title"] == "Desktop screenshot - AgentOrinth Dashboard"
    assert "[REDACTED]" in fields["text preview"]
    assert "super-secret" not in str(review)
    assert "desktop-latest" in review["summary"]
    assert review["high_risk"] is True

    stored = store.get_run(run.id)
    stored.state.handoff_summary = engine._make_handoff(stored, stored.state)
    prompt, snapshot = engine.context_compiler.compile(stored, stored.state, MemoryContext(hits=[], warnings=[]), [])
    assert stored.state.handoff_summary.approval_reviews[0].summary == review["summary"][:500]
    assert "desktop-latest" in stored.state.handoff_summary.approval_reviews[0].summary
    assert "Approval gates:" in prompt
    assert "desktop_type" in prompt
    assert "desktop-latest" in prompt
    assert "approval_reviews" in snapshot.sections


def desktop_queue_item(client: TestClient, run_id: str, action_kind: str) -> dict[str, Any]:
    recovered = client.post("/api/supervisor/recover")
    assert recovered.status_code == 200
    response = client.get("/api/operator-actions?limit=50")
    assert response.status_code == 200
    items = [
        item
        for item in response.json()["items"]
        if item["run_id"] == run_id and item["approval_kind"] == action_kind
    ]
    assert items
    return items[0]


def dispatch(client: TestClient, item_id: str, decision: str, *, confirmed: bool) -> dict[str, Any]:
    response = client.post(
        "/api/operator-actions/dispatch",
        json={"item_id": item_id, "decision": decision, "confirmed": confirmed},
    )
    assert response.status_code == 200
    return response.json()


def run_ledger(client: TestClient, run_id: str) -> dict[str, Any]:
    response = client.get(f"/api/runs/{run_id}/operator-dispatches")
    assert response.status_code == 200
    return response.json()


def assert_compact_surfaces_include_dispatch_history(
    client: TestClient,
    engine: AgentLoopEngine,
    run_id: str,
    approval_id: int,
    action_kind: str,
    decision: str,
) -> None:
    handoff = client.get(f"/api/runs/{run_id}/handoff")
    replay = client.get(f"/api/runs/{run_id}/replay")
    replay_md = client.get(f"/api/runs/{run_id}/replay.md")
    assert handoff.status_code == 200
    assert replay.status_code == 200
    assert replay_md.status_code == 200
    handoff_history = handoff.json()["operator_dispatches"]["approval_histories"][0]
    replay_history = replay.json()["operator_dispatches"]["approval_histories"][0]
    assert handoff_history["approval_id"] == approval_id
    assert replay_history["approval_id"] == approval_id
    assert handoff_history["latest_status"] == "dispatched"
    assert replay_history["latest_status"] == "dispatched"
    assert handoff_history["approval_kind"] == action_kind
    assert replay_history["approval_kind"] == action_kind
    assert action_kind in handoff_history["action_summary"]
    assert action_kind in replay_history["action_summary"]
    assert f"`{action_kind}`" in replay_md.text
    hint = (
        "human_approved_supervised_action"
        if decision == "approve"
        else "human_rejected_do_not_repeat_without_new_evidence"
    )
    handoff_desktop = handoff.json()["action_context"]["desktop_supervision_ledger"]
    replay_desktop = replay.json()["handoff"]["action_context"]["desktop_supervision_ledger"]
    assert any(f"approval#{approval_id}" in item and f"kind={action_kind}" in item for item in handoff_desktop)
    assert any(f"decision={decision}" in item and hint in item for item in handoff_desktop)
    assert any(f"decision={decision}" in item and hint in item for item in replay_desktop)

    stored = engine.store.get_run(run_id)
    stored.state.operator_dispatches = OperatorDispatchLedgerReport.model_validate(
        engine.get_operator_dispatches(run_id, limit=12)
    )
    prompt, snapshot = engine.context_compiler.compile(stored, stored.state, MemoryContext(hits=[], warnings=[]), [])
    assert "operator_dispatches" in snapshot.sections
    assert f"approval_history=approval#{approval_id}" in prompt
    assert f"kind={action_kind}" in prompt
    assert f"action=Review {action_kind} approval" in prompt
    assert f"approval#{approval_id}:kind={action_kind}" in prompt
    assert f"decision={decision}" in prompt
    assert hint in prompt
    if decision == "approve":
        assert "desktop_effect_check_required" in prompt


def test_desktop_click_approval_dispatch_history_survives_restart_open_confirm_approve(monkeypatch: Any, tmp_path: Path) -> None:
    _client_one, _engine_one, store_one = install_runtime(monkeypatch, tmp_path)
    run, approval = create_desktop_approval(
        store_one,
        tmp_path,
        action_kind="desktop_click",
        title="Desktop click dispatch approve",
    )

    client_two, _engine_two, _store_two = install_runtime(monkeypatch, tmp_path)
    item = desktop_queue_item(client_two, run.id, "desktop_click")
    assert item["approval_id"] == approval["id"]
    assert item["promotion_gate"] is False

    opened = dispatch(client_two, item["id"], "open", confirmed=False)
    assert opened["status"] == "reviewed"
    assert opened["event_kind"] == "operator_action_reviewed"
    opened_ledger = run_ledger(client_two, run.id)
    assert opened_ledger["unresolved_approval_history_count"] == 1
    assert opened_ledger["unresolved_approval_histories"][0]["approval_id"] == approval["id"]
    assert opened_ledger["unresolved_approval_histories"][0]["latest_status"] == "reviewed"
    assert opened_ledger["entries"][0]["approval_kind"] == "desktop_click"

    client_three, _engine_three, _store_three = install_runtime(monkeypatch, tmp_path)
    persisted_open = run_ledger(client_three, run.id)
    assert persisted_open["unresolved_approval_histories"][0]["latest_status"] == "reviewed"
    item = desktop_queue_item(client_three, run.id, "desktop_click")
    unconfirmed = dispatch(client_three, item["id"], "approve", confirmed=False)
    assert unconfirmed["status"] == "requires_confirmation"
    assert unconfirmed["event_kind"] == "operator_action_confirmation_required"

    client_four, _engine_four, _store_four = install_runtime(monkeypatch, tmp_path)
    persisted_confirmation = run_ledger(client_four, run.id)
    assert persisted_confirmation["unresolved_approval_histories"][0]["latest_status"] == "confirmation_required"
    item = desktop_queue_item(client_four, run.id, "desktop_click")
    approved = dispatch(client_four, item["id"], "approve", confirmed=True)
    assert approved["status"] == "dispatched"
    assert approved["action_taken"] == "approve"
    assert approved["event_kind"] == "operator_action_dispatched"

    final_ledger = run_ledger(client_four, run.id)
    assert final_ledger["total_count"] == 3
    assert final_ledger["reviewed_count"] == 1
    assert final_ledger["confirmation_required_count"] == 1
    assert final_ledger["dispatched_count"] == 1
    assert final_ledger["unresolved_approval_history_count"] == 0
    history = final_ledger["approval_histories"][0]
    assert history["approval_id"] == approval["id"]
    assert history["latest_status"] == "dispatched"
    assert history["latest_decision"] == "approve"
    assert history["sequence"] == [
        f"reviewed#{final_ledger['entries'][2]['event_id']}:open",
        f"confirmation_required#{final_ledger['entries'][1]['event_id']}:approve",
        f"dispatched#{final_ledger['entries'][0]['event_id']}:approve",
    ]
    approvals = client_four.get(f"/api/runs/{run.id}/approvals")
    assert approvals.status_code == 200
    assert approvals.json()[0]["status"] == "approved"
    assert_compact_surfaces_include_dispatch_history(client_four, _engine_four, run.id, approval["id"], "desktop_click", "approve")


def test_desktop_type_approval_dispatch_history_survives_restart_open_confirm_reject(monkeypatch: Any, tmp_path: Path) -> None:
    _client_one, _engine_one, store_one = install_runtime(monkeypatch, tmp_path)
    run, approval = create_desktop_approval(
        store_one,
        tmp_path,
        action_kind="desktop_type",
        title="Desktop type dispatch reject",
    )

    client_two, _engine_two, _store_two = install_runtime(monkeypatch, tmp_path)
    item = desktop_queue_item(client_two, run.id, "desktop_type")
    opened = dispatch(client_two, item["id"], "open", confirmed=False)
    assert opened["status"] == "reviewed"

    client_three, _engine_three, _store_three = install_runtime(monkeypatch, tmp_path)
    item = desktop_queue_item(client_three, run.id, "desktop_type")
    unconfirmed = dispatch(client_three, item["id"], "reject", confirmed=False)
    assert unconfirmed["status"] == "requires_confirmation"

    client_four, _engine_four, _store_four = install_runtime(monkeypatch, tmp_path)
    persisted_confirmation = run_ledger(client_four, run.id)
    assert persisted_confirmation["unresolved_approval_histories"][0]["latest_status"] == "confirmation_required"
    item = desktop_queue_item(client_four, run.id, "desktop_type")
    rejected = dispatch(client_four, item["id"], "reject", confirmed=True)
    assert rejected["status"] == "dispatched"
    assert rejected["action_taken"] == "reject"

    final_ledger = run_ledger(client_four, run.id)
    assert final_ledger["unresolved_approval_history_count"] == 0
    history = final_ledger["approval_histories"][0]
    assert history["approval_id"] == approval["id"]
    assert history["latest_status"] == "dispatched"
    assert history["latest_decision"] == "reject"
    assert history["sequence"] == [
        f"reviewed#{final_ledger['entries'][2]['event_id']}:open",
        f"confirmation_required#{final_ledger['entries'][1]['event_id']}:reject",
        f"dispatched#{final_ledger['entries'][0]['event_id']}:reject",
    ]
    approvals = client_four.get(f"/api/runs/{run.id}/approvals")
    assert approvals.status_code == 200
    assert approvals.json()[0]["status"] == "rejected"
    assert_compact_surfaces_include_dispatch_history(client_four, _engine_four, run.id, approval["id"], "desktop_type", "reject")