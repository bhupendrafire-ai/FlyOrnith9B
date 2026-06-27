from pathlib import Path

from fastapi.testclient import TestClient

from app import api as api_module
from app.engine import AgentLoopEngine
from app.events import EventBroker
from app.memory import ObsidianMemory
from app.persistence import RunStore
from app.schemas import AcceptanceCriterionEvidence, DesktopSnapshot, ModelInteractionRecord, RecoveryPlan, ToolCallRecord, WebSource

from conftest import make_config


class FakeModel:
    async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
        return '{"should_update": false, "proposed_goal": "", "reason": ""}'


def install_test_runtime(monkeypatch, tmp_path: Path) -> tuple[TestClient, AgentLoopEngine, RunStore]:  # noqa: ANN001
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


def test_ornith_launch_preflight_api_reports_global_posture(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, _store = install_test_runtime(monkeypatch, tmp_path)

    response = client.get("/api/ornith/preflight")

    assert response.status_code == 200
    body = response.json()
    item_ids = {item["id"] for item in body["items"]}

    assert body["mode"] == "launch"
    assert body["model_profile_id"] == "ornith"
    assert body["ready_to_start"] is True
    assert body["readiness_smoke_status"] == "never_run"
    assert body["dispatch_restart_smoke_status"] == "never_run"
    assert {"model_profile", "tool_toggles", "readiness_smoke", "operator_dispatch_restart_smoke"} <= item_ids
    assert body["next_actions"]


def test_ornith_resume_preflight_api_blocks_pending_approval_and_context(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Preflight blocked",
        str(tmp_path),
        [],
    )
    created.state.context_budget.pressure = "high"
    created.state.context_budget.estimated_tokens = 26000
    created.state.context_budget.target_tokens = 18000
    store.update_run(created.id, status="waiting_approval", state=created.state)
    store.create_approval(created.id, "shell", {"command": "python -m pytest"}, "Approve verification shell.")

    response = client.get(f"/api/runs/{created.id}/ornith-preflight")

    assert response.status_code == 200
    body = response.json()
    items = {item["id"]: item for item in body["items"]}

    assert body["mode"] == "resume"
    assert body["status"] == "blocked"
    assert body["ready_to_resume"] is False
    assert body["pending_approval_count"] == 1
    assert items["context_budget"]["status"] == "block"
    assert items["approval_posture"]["status"] == "block"
    assert any("Resolve pending approvals" in action for action in body["next_actions"])
def test_ornith_preflight_flows_into_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Preflight handoff",
        str(tmp_path),
        [],
    )

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    timeline = client.get(f"/api/runs/{created.id}/timeline")
    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")

    assert handoff.status_code == 200
    handoff_body = handoff.json()
    assert handoff_body["ornith_preflight"]["run_id"] == created.id
    assert handoff_body["ornith_preflight"]["mode"] == "resume"
    assert not any(
        check["section"] == "ornith_preflight" and check["status"] == "missing"
        for check in handoff_body["report_integrity"]["checks"]
    )
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    assert timeline_body["ornith_preflight"]["run_id"] == created.id
    assert timeline_body["handoff"]["ornith_preflight"]["run_id"] == created.id
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["ornith_preflight"]["run_id"] == created.id
    assert replay_body["handoff"]["ornith_preflight"]["run_id"] == created.id
    assert replay_md.status_code == 200
    assert "## Ornith Preflight" in replay_md.text

def test_source_evidence_preview_flows_into_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Verify dashboard with source-visible proof",
        "Source evidence API",
        str(tmp_path),
        ["Dashboard has browser and web proof"],
    )
    created.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Dashboard has browser and web proof",
            status="open",
            required_labels=["web", "browser"],
            matched_labels=["web"],
            evidence=["web_fetch [web]: Fetched dashboard docs."],
            last_tool="web_fetch",
        )
    ]
    created.state.web_sources = [
        WebSource(
            id="web-1",
            title="Dashboard docs",
            url="https://example.com/dashboard",
            timestamp="2026-06-28T12:00:00+00:00",
            excerpt="Dashboard source excerpt with enough detail for operator review.",
            citation="[Dashboard docs](https://example.com/dashboard)",
        )
    ]
    created.state.desktop_snapshots = [
        DesktopSnapshot(
            id="browser-1",
            timestamp="2026-06-28T12:01:00+00:00",
            title="Browser screenshot: http://127.0.0.1:5173",
            path=str(tmp_path / "browser.png"),
            summary="Captured dashboard browser screenshot.",
        )
    ]
    store.update_run(created.id, state=created.state)

    source = client.get(f"/api/runs/{created.id}/source-evidence")
    assert source.status_code == 200
    body = source.json()
    assert body["total_count"] == 2
    assert body["web_source_count"] == 1
    assert body["browser_snapshot_count"] == 1
    assert body["missing_labels"] == ["browser"]
    assert body["entries"][0]["linked_criteria"] == ["Dashboard has browser and web proof"]

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    assert handoff.status_code == 200
    assert handoff.json()["source_evidence"]["total_count"] == 2

    timeline = client.get(f"/api/runs/{created.id}/timeline")
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    assert timeline_body["source_evidence"]["browser_snapshot_count"] == 1
    assert timeline_body["handoff"]["source_evidence"]["web_source_count"] == 1

    replay = client.get(f"/api/runs/{created.id}/replay")
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["source_evidence"]["total_count"] == 2
    assert replay_body["handoff"]["source_evidence"]["total_count"] == 2

    replay_md = client.get(f"/api/runs/{created.id}/replay.md")
    assert replay_md.status_code == 200
    assert "## Source Evidence" in replay_md.text
    assert "Dashboard docs" in replay_md.text

def test_pause_resume_public_api_survives_runtime_recreation(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine_one, store_one = install_test_runtime(monkeypatch, tmp_path)
    created = store_one.create_run("Pause and resume after restart", "Restart API", str(tmp_path), [])

    paused = client.post(f"/api/runs/{created.id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    client, engine_two, _store_two = install_test_runtime(monkeypatch, tmp_path)
    resumed = client.post(f"/api/runs/{created.id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"
    engine_two._cancel_task(created.id)
    timeline = client.get(f"/api/runs/{created.id}/timeline")
    assert timeline.status_code == 200
    preflight_events = [event for event in timeline.json()["events"] if event["kind"] == "resume_preflight"]
    assert preflight_events
    assert preflight_events[-1]["data"]["policy_simulation"]["policy_action"] == "complete"
    assert timeline.json()["resume_decisions"]["latest_accepted"]["source"] == "manual"
    decisions = client.get(f"/api/runs/{created.id}/resume-decisions")
    assert decisions.status_code == 200
    assert decisions.json()["latest_accepted"]["policy_action"] == "complete"
    assert decisions.json()["comparison_summary"]

    paused_again = client.post(f"/api/runs/{created.id}/pause")
    assert paused_again.status_code == 200
    assert paused_again.json()["status"] == "paused"

    replay = client.get(f"/api/runs/{created.id}/replay")
    assert replay.status_code == 200
    assert replay.json()["run_id"] == created.id
    assert replay.json()["event_count"] >= 3


def test_timeline_exposes_acceptance_evidence(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Expose criteria", "Criteria API", str(tmp_path), ["Tests pass"])
    engine._ensure_acceptance_evidence(created.state)
    store.update_run(created.id, state=created.state)

    response = client.get(f"/api/runs/{created.id}/timeline")

    assert response.status_code == 200
    body = response.json()
    assert body["acceptance_evidence"][0]["criterion"] == "Tests pass"
    assert body["acceptance_evidence"][0]["status"] == "open"
    assert body["acceptance_recommendations"][0]["tool_kind"] == "run_tests"
    assert body["acceptance_recommendation_traces"] == []
    assert body["run_health"]["recommended_action"] == "verify"
    assert body["completion_audit"]["acceptance_open"] == 1


def test_completion_audit_endpoint_explains_unfinished_run(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Audit endpoint", "Audit API", str(tmp_path), ["Tests pass"])
    store.create_approval(created.id, "shell", {"command": "Remove-Item demo"}, "Destructive command.")

    response = client.get(f"/api/runs/{created.id}/completion-audit")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert not body["can_finish"]
    assert body["pending_approvals"] == 1
    assert any(issue["id"] == "acceptance_not_verified" for issue in body["issues"])


def test_run_health_endpoint_reports_compact_status(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Health endpoint", "Health API", str(tmp_path), ["Tests pass"])

    response = client.get(f"/api/runs/{created.id}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["recommended_action"] == "verify"
    assert any(signal["id"] == "open_acceptance_evidence" for signal in body["signals"])


def test_run_progress_endpoint_reports_coverage_status(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Progress endpoint", "Progress API", str(tmp_path), ["Tests pass"])

    response = client.get(f"/api/runs/{created.id}/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["status"] == "needs_verification"
    assert body["acceptance_total"] == 1
    assert body["acceptance_verified"] == 0
    assert body["current_policy_action"] == "verify"
    assert body["can_keep_running"] is True
    assert body["next_actions"]


def test_report_integrity_endpoint_detects_stale_handoff(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Integrity endpoint", "Integrity API", str(tmp_path), [])
    created.state.goal = "Sharper active goal after compaction"
    store.update_run(created.id, state=created.state)

    response = client.get(f"/api/runs/{created.id}/report-integrity")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["status"] == "needs_refresh"
    assert body["stale_count"] >= 1
    stale_sections = {check["section"] for check in body["checks"] if check["status"] == "stale"}
    assert "handoff.current_objective" in stale_sections
    assert body["recommended_action"] == "Refresh handoff and replay reports before resuming the loop."


def test_objective_readiness_endpoint_maps_harness_requirements(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Objective readiness endpoint", "Objective readiness API", str(tmp_path), ["Tests pass"])

    response = client.get(f"/api/runs/{created.id}/objective-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["status"] in {"partial", "not_ready", "ready"}
    assert body["verified_count"] + body["partial_count"] + body["missing_count"] + body["failed_count"] == len(body["items"])
    assert body["recommended_action"]
    assert body["next_actions"]
    assert "Proof:" in body["next_actions"][0]
    item_ids = {item["id"] for item in body["items"]}
    assert {
        "isolated_workspaces",
        "patch_first_editing",
        "replay_audit_trails",
        "goal_evolution",
    }.issubset(item_ids)
    patch_item = next(item for item in body["items"] if item["id"] == "patch_first_editing")
    assert patch_item["proof"]["tool_kind"] == "patch_propose"
    assert patch_item["proof"]["evidence_label"] == "edit"
    assert patch_item["proof"]["requires_approval"] is True


def test_policy_simulation_endpoint_previews_next_policy(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Policy endpoint", "Policy API", str(tmp_path), ["Tests pass"])

    response = client.get(f"/api/runs/{created.id}/policy-simulation")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["policy_action"] == "verify"
    assert body["predicted_milestone"] == "act"
    assert body["recommended_tool"] == "run_tests"
    assert body["safe_to_resume"] is True


def test_autonomy_decisions_endpoint_reports_stop_and_continue_choices(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Autonomy endpoint", "Autonomy API", str(tmp_path), ["Tests pass"])
    store.append_event(created.id, "decide", "Continuing to next action.")
    store.append_event(created.id, "blocked", "Reached MAX_LOOP_STEPS.")

    response = client.get(f"/api/runs/{created.id}/autonomy-decisions")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["decision_count"] == 2
    assert body["continue_count"] == 1
    assert body["blocked_count"] == 1
    assert body["latest_decision"]["decision"] == "blocked"
    assert body["latest_decision"]["source"] == "loop_budget"


def test_action_readiness_endpoint_reports_next_act_state(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Readiness endpoint", "Readiness API", str(tmp_path), ["Tests pass"])
    created.state.milestone = "act"
    store.update_run(created.id, status="queued", state=created.state)

    response = client.get(f"/api/runs/{created.id}/action-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["status"] == "needs_proof"
    assert body["ready_to_act"] is True
    assert body["suggested_tool"] == "run_tests"


def test_readiness_completion_endpoint_reports_harness_gate(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness completion API",
        str(tmp_path),
        [],
    )

    response = client.get(f"/api/runs/{created.id}/readiness-completion")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["status"] in {"blocked", "needs_more_evidence"}
    assert body["can_claim_milestone"] is False
    assert body["dispatch_restart_smoke_ledger_status"] == "never_run"
    assert any(check["id"] == "objective_readiness" for check in body["checks"])
    assert any(check["id"] == "operator_dispatch_restart_smoke" for check in body["checks"])


def test_readiness_rehearsal_api_runs_smoke_and_attaches_report(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)

    empty_ledger = client.get("/api/rehearsals/readiness-claim")
    assert empty_ledger.status_code == 200
    assert empty_ledger.json()["status"] == "never_run"
    assert empty_ledger.json()["total_count"] == 0

    response = client.post("/api/rehearsals/readiness-claim")

    assert response.status_code == 200
    body = response.json()
    run_id = body["run_id"]
    stored = store.get_run(run_id)
    assert body["status"] == "passed"
    assert body["restart_simulated"] is True
    assert body["refused_event_id"]
    assert body["accepted_event_id"]
    assert body["completed_event_id"]
    assert body["handoff_attached"] is True
    assert body["replay_attached"] is True
    assert stored.status == "completed"
    assert stored.state.readiness_rehearsal.status == "passed"
    assert stored.state.handoff_summary.readiness_rehearsal.status == "passed"
    assert [step["id"] for step in body["steps"]] == [
        "refused_claim",
        "routed_proof",
        "verify_after_proof",
        "checkpoint_handoff",
        "restart_resume_preflight",
        "accepted_claim",
        "compact_context",
    ]

    report = client.get(f"/api/runs/{run_id}/readiness-rehearsal")
    timeline = client.get(f"/api/runs/{run_id}/timeline")
    handoff = client.get(f"/api/runs/{run_id}/handoff")
    replay = client.get(f"/api/runs/{run_id}/replay")
    replay_md = client.get(f"/api/runs/{run_id}/replay.md")

    assert report.status_code == 200
    assert report.json()["status"] == "passed"
    assert timeline.json()["readiness_rehearsal"]["status"] == "passed"
    assert handoff.json()["readiness_rehearsal"]["status"] == "passed"
    assert replay.json()["readiness_rehearsal"]["status"] == "passed"
    assert replay.json()["handoff"]["readiness_rehearsal"]["status"] == "passed"
    assert "## Readiness Rehearsal" in replay_md.text

    ledger = client.get("/api/rehearsals/readiness-claim")
    assert ledger.status_code == 200
    ledger_body = ledger.json()
    assert ledger_body["status"] == "passed"
    assert ledger_body["total_count"] == 1
    assert ledger_body["passed_count"] == 1
    assert ledger_body["failed_count"] == 0
    assert ledger_body["latest"]["run_id"] == run_id
    assert ledger_body["latest"]["passed_steps"] == len(body["steps"])
    assert ledger_body["entries"][0]["replay_attached"] is True


def test_operator_dispatch_restart_smoke_api_proves_resume_ledger(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)

    empty_ledger = client.get("/api/rehearsals/operator-dispatch-restart")
    assert empty_ledger.status_code == 200
    assert empty_ledger.json()["status"] == "never_run"
    assert empty_ledger.json()["total_count"] == 0

    response = client.post("/api/rehearsals/operator-dispatch-restart")

    assert response.status_code == 200
    body = response.json()
    run_id = body["run_id"]
    assert body["status"] == "passed"
    assert body["restart_simulated"] is True
    assert body["dispatch_event_id"] > 0
    assert body["ledger_attached"] is True
    assert body["handoff_attached"] is True
    assert body["replay_attached"] is True
    assert body["context_attached"] is True
    assert body["compact_context_tokens"] > 0
    assert "operator_dispatches" in body["compact_context_sections"]
    assert [step["id"] for step in body["steps"]] == [
        "queued_operator_action",
        "dispatch_logged",
        "restart_loaded_ledger",
        "handoff_attached_ledger",
        "replay_attached_ledger",
        "context_attached_ledger",
    ]
    assert all(step["status"] == "passed" for step in body["steps"])

    stored = store.get_run(run_id)
    assert stored.state.operator_dispatch_restart_smoke.status == "passed"
    assert stored.state.handoff_summary.operator_dispatch_restart_smoke.status == "passed"
    assert stored.state.handoff_summary.operator_dispatches.dispatched_count >= 1

    report = client.get(f"/api/runs/{run_id}/operator-dispatch-restart-smoke")
    ledger = client.get(f"/api/runs/{run_id}/operator-dispatches")
    handoff = client.get(f"/api/runs/{run_id}/handoff")
    replay = client.get(f"/api/runs/{run_id}/replay")
    replay_md = client.get(f"/api/runs/{run_id}/replay.md")
    timeline = client.get(f"/api/runs/{run_id}/timeline")

    assert report.status_code == 200
    assert report.json()["status"] == "passed"
    assert ledger.status_code == 200
    assert ledger.json()["dispatched_count"] >= 1
    assert handoff.status_code == 200
    assert handoff.json()["operator_dispatches"]["dispatched_count"] >= 1
    assert handoff.json()["operator_dispatch_restart_smoke"]["status"] == "passed"
    assert replay.status_code == 200
    assert replay.json()["operator_dispatches"]["dispatched_count"] >= 1
    assert replay.json()["operator_dispatch_restart_smoke"]["status"] == "passed"
    assert replay.json()["handoff"]["operator_dispatch_restart_smoke"]["status"] == "passed"
    assert replay_md.status_code == 200
    assert "## Operator Dispatches" in replay_md.text
    assert "## Operator Dispatch Restart Smoke" in replay_md.text
    assert timeline.status_code == 200
    assert timeline.json()["operator_dispatches"]["dispatched_count"] >= 1
    assert timeline.json()["operator_dispatch_restart_smoke"]["status"] == "passed"

    smoke_ledger = client.get("/api/rehearsals/operator-dispatch-restart")
    assert smoke_ledger.status_code == 200
    smoke_ledger_body = smoke_ledger.json()
    assert smoke_ledger_body["status"] == "passed"
    assert smoke_ledger_body["total_count"] == 1
    assert smoke_ledger_body["passed_count"] == 1
    assert smoke_ledger_body["failed_count"] == 0
    assert smoke_ledger_body["latest"]["run_id"] == run_id
    assert smoke_ledger_body["latest"]["dispatch_event_id"] == body["dispatch_event_id"]
    assert smoke_ledger_body["latest"]["passed_steps"] == len(body["steps"])
    assert smoke_ledger_body["entries"][0]["context_attached"] is True

    supervisor = client.get("/api/supervisor")
    assert supervisor.status_code == 200
    supervisor_body = supervisor.json()
    assert supervisor_body["operator_dispatch_restart_smoke_ledger"]["status"] == "passed"
    assert supervisor_body["operator_dispatch_restart_smoke_ledger"]["latest"]["run_id"] == run_id
    assert supervisor_body["operator_dispatch_restart_smoke_attention_count"] == 0


def test_supervisor_queues_missing_operator_dispatch_restart_smoke(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth into a Codex-like long-running local coding harness",
        "Dispatch smoke supervisor",
        str(tmp_path),
        [],
    )

    response = client.post("/api/supervisor/recover")

    assert response.status_code == 200
    body = response.json()
    assert body["operator_dispatch_restart_smoke_ledger"]["status"] == "never_run"
    assert body["operator_dispatch_restart_smoke_attention_count"] >= 1
    run_entry = next(item for item in body["runs"] if item["run_id"] == created.id)
    assert run_entry["operator_dispatch_restart_smoke_required"] is True
    assert run_entry["operator_dispatch_restart_smoke_status"] == "missing"
    assert run_entry["operator_dispatch_restart_smoke_requires_attention"] is True
    assert "operator_dispatch_restart_smoke" in run_entry["operator_attention_reasons"]
    queue_items = body["operator_action_queue"]["items"]
    dispatch_smoke_items = [item for item in queue_items if item["reason"] == "operator_dispatch_restart_smoke"]
    assert dispatch_smoke_items
    assert dispatch_smoke_items[0]["endpoint"] == "/api/rehearsals/operator-dispatch-restart"
    assert dispatch_smoke_items[0]["ui_target"] == "operator_dispatch_restart_smoke"

def test_operator_actions_route_ornith_preflight_refreshes(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth into a Codex-like long-running local coding harness",
        "Ornith preflight queue",
        str(tmp_path),
        [],
    )
    created.state.context_budget.pressure = "high"
    created.state.context_budget.estimated_tokens = 26000
    created.state.context_budget.target_tokens = 18000
    created.state.handoff_summary.resume_prompt = ""
    created.state.handoff_summary.original_goal = ""
    store.update_run(created.id, status="paused", state=created.state)

    recovered = client.post("/api/supervisor/recover")

    assert recovered.status_code == 200
    supervisor_body = recovered.json()
    assert supervisor_body["ornith_preflight_attention_count"] >= 1
    run_entry = next(item for item in supervisor_body["runs"] if item["run_id"] == created.id)
    assert run_entry["ornith_preflight_requires_attention"] is True
    assert run_entry["ornith_preflight_status"] in {"attention", "blocked"}
    assert "ornith_preflight" in run_entry["operator_attention_reasons"]

    queue = client.get("/api/operator-actions?limit=50")
    assert queue.status_code == 200
    queue_body = queue.json()
    assert queue_body["preflight_count"] >= 2
    queue_items = {item["reason"]: item for item in queue_body["items"]}
    context_item = queue_items["ornith_preflight_context_budget"]
    handoff_item = queue_items["ornith_preflight_handoff_anchor"]
    assert context_item["ui_target"] == "context_checkpoint"
    assert context_item["method"] == "POST"
    assert handoff_item["ui_target"] == "handoff_refresh"

    unconfirmed = client.post(
        "/api/operator-actions/dispatch",
        json={"item_id": context_item["id"], "decision": "dispatch", "confirmed": False},
    )
    assert unconfirmed.status_code == 200
    assert unconfirmed.json()["status"] == "requires_confirmation"

    dispatched = client.post(
        "/api/operator-actions/dispatch",
        json={"item_id": context_item["id"], "decision": "dispatch", "confirmed": True},
    )
    assert dispatched.status_code == 200
    dispatched_body = dispatched.json()
    assert dispatched_body["status"] == "dispatched"
    assert dispatched_body["action_taken"] == "context_checkpoint"
    assert "compact context" in dispatched_body["message"]

    preflight_actions = client.get(f"/api/runs/{created.id}/ornith-preflight-actions")
    assert preflight_actions.status_code == 200
    preflight_body = preflight_actions.json()
    assert preflight_body["completed_count"] == 1
    assert preflight_body["dispatched_count"] == 0
    assert preflight_body["context_checkpoint_count"] == 1
    assert preflight_body["handoff_refresh_count"] == 0
    latest_action = preflight_body["entries"][0]
    assert latest_action["status"] == "completed"
    assert latest_action["item_id"] == "context_budget"
    assert latest_action["ui_target"] == "context_checkpoint"
    assert latest_action["context_pressure"] in {"low", "medium", "high"}
    assert latest_action["context_tokens"] <= latest_action["context_target_tokens"]
    assert latest_action["context_target_tokens"] == 18000

    timeline = client.get(f"/api/runs/{created.id}/timeline")
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    event_kinds = [event["kind"] for event in timeline_body["events"]]
    assert "operator_action_confirmation_required" in event_kinds
    assert "operator_action_dispatched" in event_kinds
    assert "ornith_preflight_action" in event_kinds
    assert timeline_body["ornith_preflight_actions"]["completed_count"] == 1
    assert timeline_body["handoff"]["ornith_preflight_actions"]["completed_count"] == 1

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    assert handoff.status_code == 200
    assert handoff.json()["ornith_preflight_actions"]["completed_count"] == 1

    replay = client.get(f"/api/runs/{created.id}/replay")
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["ornith_preflight_actions"]["completed_count"] == 1
    assert replay_body["handoff"]["ornith_preflight_actions"]["completed_count"] == 1

    replay_md = client.get(f"/api/runs/{created.id}/replay.md")
    assert replay_md.status_code == 200
    assert "## Ornith Preflight Actions" in replay_md.text
    assert "context_budget" in replay_md.text

def test_action_readiness_decisions_endpoint_reports_compact_ledger(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Readiness ledger", "Readiness ledger API", str(tmp_path), ["Tests pass"])
    store.append_event(
        created.id,
        "action_readiness_policy",
        "blocked: Need user decision.",
        {
            "action_readiness": {
                "run_id": created.id,
                "status": "blocked",
                "ready_to_act": False,
                "summary": "blocked: Need user decision.",
                "recommended_action": "Resolve blocker before acting.",
            }
        },
    )

    response = client.get(f"/api/runs/{created.id}/action-readiness-decisions")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["decision_count"] == 1
    assert body["blocked_count"] == 1
    assert body["latest_policy_decision"]["source"] == "policy"


def test_recovery_decisions_endpoint_reports_active_recovery(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Recovery decisions", "Recovery decisions API", str(tmp_path), [])
    created.state.recovery_plan = RecoveryPlan(
        id="recovery-api",
        status="active",
        trigger="readiness_decision_loop",
        failure_kind="readiness_proof_failure",
        tool="run_tests",
        attempts=2,
        summary="Readiness proof loop for verification via run_tests.",
        next_action="Review readiness decisions.",
        steps=[
            "Review the readiness decision ledger for verification via run_tests.",
            "Run a narrower diagnostic than the repeated test command.",
        ],
    )
    store.update_run(created.id, status="paused", state=created.state)

    response = client.get(f"/api/runs/{created.id}/recovery-decisions")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["active_recovery"] is True
    assert body["active_decision"]["trigger"] == "readiness_decision_loop"
    assert "narrower diagnostic" in body["active_decision"]["selected_strategy"]


def test_verification_outcomes_endpoint_reports_recovery_closure(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Verification outcomes", "Verification outcomes API", str(tmp_path), ["Tests pass"])
    created.state.tool_calls.append(
        ToolCallRecord(
            id="tool-run-tests",
            name="run_tests",
            ok=True,
            summary="All tests passed.",
            created_at="2026-06-27T08:04:00+00:00",
        )
    )
    created.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Tests pass",
            status="verified",
            required_labels=["verification"],
            matched_labels=["verification"],
            label_checked_at={"verification": "2026-06-27T08:04:00+00:00"},
            evidence=["run_tests [verification]: All tests passed."],
            last_tool="run_tests",
            last_checked="2026-06-27T08:04:00+00:00",
        )
    ]
    created.state.recovery_history = [
        RecoveryPlan(
            id="recovery-api",
            status="resolved",
            trigger="readiness_decision_loop",
            failure_kind="readiness_proof_failure",
            tool="run_tests",
            attempts=2,
            summary="Readiness proof loop for verification via run_tests.",
            steps=["Review readiness decisions.", "Run a narrower diagnostic."],
            created_at="2026-06-27T08:00:00+00:00",
            resolved_at="2026-06-27T08:05:00+00:00",
        )
    ]
    store.update_run(created.id, status="queued", state=created.state)

    response = client.get(f"/api/runs/{created.id}/verification-outcomes")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["recovery_resolved_count"] == 1
    assert body["latest_recovery_outcome"]["outcome"] == "recovery_resolved"
    assert body["latest_recovery_outcome"]["evidence_status"] == "verified"


def test_completion_policy_endpoint_exposes_verification_policy(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, _store = install_test_runtime(monkeypatch, tmp_path)

    response = client.get("/api/completion-policy")

    assert response.status_code == 200
    body = response.json()
    assert body["strict_stale_evidence"] is True
    assert "verification" in body["evidence_labels"]
    assert "patch_apply" in body["stale_edit_tools"]
    assert "run_tests" in body["verification_tools"]
    assert "checkpoint" in body["checkpoint_tools"]


def test_supervisor_recover_endpoint_repairs_stale_running_run(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Repair stale run", "Supervisor API", str(tmp_path), [])
    store.update_run(created.id, status="running", state=created.state)

    recovered = client.post("/api/supervisor/recover")
    assert recovered.status_code == 200
    body = recovered.json()
    assert body["recovered"] == 1
    assert body["runs"][0]["action"] == "paused_for_resume"
    assert "run_health" in body["runs"][0]
    assert "run_progress" in body["runs"][0]
    assert "objective_readiness" in body["runs"][0]
    assert body["runs"][0]["objective_readiness_action"]
    assert "proof" in body["runs"][0]["objective_readiness_action"]
    assert body["runs"][0]["run_progress"]["status"] in {"near_completion", "on_track"}
    assert body["readiness_rehearsal_ledger"]["status"] == "never_run"
    assert "operator_attention_count" in body
    assert "pending_approval_count" in body
    assert body["runs"][0]["readiness_smoke_status"] in {"not_applicable", "missing"}
    assert "readiness_smoke_action" in body["runs"][0]
    assert "supervisor_priority" in body["runs"][0]
    assert "operator_attention_reasons" in body["runs"][0]

    run = client.get(f"/api/runs/{created.id}")
    assert run.status_code == 200
    assert run.json()["status"] == "paused"

    supervisor = client.get("/api/supervisor")
    assert supervisor.status_code == 200
    assert supervisor.json()["recovered"] == 1

    operator_actions = client.get("/api/operator-actions")
    assert operator_actions.status_code == 200
    assert "summary" in operator_actions.json()
    assert "items" in operator_actions.json()


def test_operator_action_dispatch_endpoint_requires_confirmation(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Confirm queued approval", "Approval dispatch API", str(tmp_path), [])
    state = created.state
    state.proposed_goal = "Confirm queued approval with updated goal."
    store.create_approval(
        created.id,
        "goal_update",
        {"proposed_goal": state.proposed_goal, "reason": "Exercise operator dispatcher."},
        "Confirm updated goal.",
    )
    store.update_run(created.id, status="waiting_goal_confirmation", state=state)

    recovered = client.post("/api/supervisor/recover")
    assert recovered.status_code == 200
    queue = client.get("/api/operator-actions").json()
    item = next(entry for entry in queue["items"] if entry["reason"] == "approval")

    response = client.post(
        "/api/operator-actions/dispatch",
        json={"item_id": item["id"], "decision": "approve", "confirmed": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_confirmation"
    assert body["event_kind"] == "operator_action_confirmation_required"
    assert store.list_approvals(created.id, status="pending")

    run_ledger = client.get(f"/api/runs/{created.id}/operator-dispatches")
    assert run_ledger.status_code == 200
    assert run_ledger.json()["confirmation_required_count"] == 1
    all_ledger = client.get("/api/operator-actions/dispatches")
    assert all_ledger.status_code == 200
    assert all_ledger.json()["total_count"] >= 1


def test_model_profile_eval_endpoint_reports_ornith_fixture_metrics(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, _store = install_test_runtime(monkeypatch, tmp_path)

    response = client.get("/api/model-profile/eval")

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "ornith"
    assert body["fallback_needed"] == 1
    assert body["patch_first_fail"] == 1
    assert any(case["id"] == "unknown_tool_fallback" for case in body["cases"])


def test_model_quality_endpoint_reports_compact_live_patterns(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Classify model behavior", "Quality API", str(tmp_path), [])
    created.state.model_interactions.append(
        ModelInteractionRecord(
            id="model-fallback",
            kind="action",
            ok=False,
            attempts=2,
            fallback_used=True,
            error="Unknown or missing tool: invent_magic",
            raw_excerpt="do not leak this raw output",
            summary="Model action fallback used: git_status.",
            created_at="2026-06-27T08:01:00+00:00",
        )
    )
    store.update_run(created.id, state=created.state)

    response = client.get("/api/model-profile/quality")

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "ornith"
    assert body["interaction_count"] == 1
    assert body["issue_counts"]["unknown_tool"] == 1
    assert body["fallback_count"] == 1
    assert "raw_excerpt" not in body["samples"][0]
    assert "do not leak" not in response.text


def test_model_adaptation_endpoint_returns_confirmation_gated_proposal(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Adapt endpoint", "Adapt API", str(tmp_path), [])
    created.state.model_interactions.append(
        ModelInteractionRecord(
            id="model-write",
            kind="action",
            ok=True,
            attempts=1,
            summary="Model selected tool file_write.",
            raw_excerpt="raw write output",
            created_at="2026-06-27T08:02:00+00:00",
        )
    )
    store.update_run(created.id, state=created.state)

    response = client.get("/api/model-profile/adaptation")

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "ornith"
    assert body["confirmation_required"]
    assert body["status"] == "needs_confirmation"
    assert any(action["change"] == "policy_bias" for action in body["actions"])
    assert all(action["requires_confirmation"] for action in body["actions"])
    assert "raw write output" not in response.text


def test_goal_review_endpoint_queues_model_proposal_for_confirmation(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    class GoalReviewModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            return (
                '{"should_update": true, "proposed_goal": "Sharper API goal", '
                '"reason": "The run has a clearer next objective."}'
            )

    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
    engine.model = GoalReviewModel()  # type: ignore[assignment]
    created = store.create_run("Original API goal", "Goal API", str(tmp_path), [])

    response = client.post(f"/api/runs/{created.id}/goal/review")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_goal_confirmation"
    assert body["state"]["goal"] == "Original API goal"
    assert body["state"]["proposed_goal"] == "Sharper API goal"
    assert body["state"]["goal_evolution"]["pending_count"] == 1
    assert body["state"]["goal_evolution"]["latest_decision"]["source"] == "manual_review"
    evolution = client.get(f"/api/runs/{created.id}/goal/evolution").json()
    assert evolution["pending_count"] == 1
    assert evolution["latest_decision"]["proposed_goal"] == "Sharper API goal"
    approvals = client.get(f"/api/runs/{created.id}/approvals").json()
    assert approvals[0]["action_kind"] == "goal_update"
    assert approvals[0]["payload"]["proposed_goal"] == "Sharper API goal"


def test_model_adaptation_review_endpoint_records_decision(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Review adaptation", "Review API", str(tmp_path), [])
    created.state.model_interactions.append(
        ModelInteractionRecord(
            id="model-write",
            kind="action",
            ok=True,
            attempts=1,
            summary="Model selected tool file_write.",
            raw_excerpt="raw review output",
            created_at="2026-06-27T08:02:00+00:00",
        )
    )
    store.update_run(created.id, state=created.state)
    proposal = client.get("/api/model-profile/adaptation").json()

    response = client.post(
        "/api/model-profile/adaptation/reviews",
        json={
            "proposal": proposal,
            "decision": "rejected",
            "reviewer_note": "Too broad for now.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["proposal"]["id"] == proposal["id"]
    assert "raw review output" not in response.text

    listed = client.get("/api/model-profile/adaptation/reviews")
    assert listed.status_code == 200
    assert listed.json()[0]["reviewer_note"] == "Too broad for now."

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    assert handoff.status_code == 200
    assert handoff.json()["model_profile_adaptation_reviews"][0]["decision"] == "rejected"

    replay = client.get(f"/api/runs/{created.id}/replay")
    assert replay.status_code == 200
    assert replay.json()["model_profile_adaptation_reviews"][0]["reviewer_note"] == "Too broad for now."

