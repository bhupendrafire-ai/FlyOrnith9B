import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app import api as api_module
from app.engine import AgentLoopEngine
from app.events import EventBroker
from app.memory import ObsidianMemory
from app.persistence import RunStore
from app.schemas import AcceptanceCriterionEvidence, CheckpointQualityReport, DesktopEffectProofReport, DesktopSnapshot, ModelInteractionRecord, PatchApplication, PatchProposal, ReadinessRehearsalReport, ReadinessRehearsalStep, RecoveryPlan, ReportIntegrityRefreshRecord, ToolCallRecord, WebSource, WorkspaceIsolation
from app.tools import ToolResult

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


def test_desktop_effect_proof_preview_api_reports_latest_snapshot(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Use supervised desktop control",
        "Desktop effect proof API",
        str(tmp_path),
        [],
    )
    created.state.tool_calls.extend(
        [
            ToolCallRecord(
                id="desktop-click-1",
                name="desktop_click",
                ok=True,
                summary="Clicked the visible Save button.",
                created_at="2026-06-29T10:00:00+00:00",
            ),
            ToolCallRecord(
                id="desktop-shot-1",
                name="desktop_screenshot",
                ok=True,
                summary="Captured the visible post-click state.",
                created_at="2026-06-29T10:01:00+00:00",
            ),
        ]
    )
    created.state.desktop_snapshots.append(
        DesktopSnapshot(
            id="desktop-proof",
            timestamp="2026-06-29T10:01:00+00:00",
            title="Desktop screenshot",
            path=str(tmp_path / "desktop-proof.png"),
            summary="Captured the visible post-click state.",
        )
    )
    store.update_run(created.id, state=created.state)
    store.append_event(
        created.id,
        "desktop_effect_proof_repaired",
        "Refreshed stale desktop-effect proof metadata; no new desktop screenshot was needed.",
        {
            "desktop_effect_proof_repair": {
                "outcome": "metadata_refreshed",
                "summary": "Refreshed stale desktop-effect proof metadata; no new desktop screenshot was needed.",
                "previous_report_integrity": {"status": "needs_refresh"},
                "refreshed_report_integrity": {"status": "ok"},
                "previous_desktop_effect_proof": {"status": "needs_proof", "latest_action_id": "desktop-click-1"},
                "refreshed_desktop_effect_proof": {
                    "status": "proof_available",
                    "latest_action_id": "desktop-click-1",
                    "proof_call_id": "desktop-shot-1",
                    "proof_snapshot": {"id": "desktop-proof"},
                },
                "report_integrity_refresh_reasons": ["handoff.desktop_effect_proof.status stale"],
                "refresh_reason_count": 1,
            }
        },
    )

    response = client.get(f"/api/runs/{created.id}/desktop-effect-proof")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proof_available"
    assert body["requires_attention"] is False
    assert body["latest_action_tool"] == "desktop_click"
    assert body["proof_tool"] == "desktop_screenshot"
    assert body["proof_snapshot"]["id"] == "desktop-proof"
    assert any("snapshot=desktop-proof" in item for item in body["ledger"])

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    assert handoff.status_code == 200
    handoff_body = handoff.json()
    assert handoff_body["desktop_effect_proof"]["proof_snapshot"]["id"] == "desktop-proof"
    assert handoff_body["desktop_effect_proof_repairs"]["latest_outcome"] == "metadata_refreshed"

    timeline = client.get(f"/api/runs/{created.id}/timeline")
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    assert timeline_body["desktop_effect_proof"]["status"] == "proof_available"
    assert timeline_body["desktop_effect_proof_repairs"]["metadata_refreshed_count"] == 1
    assert timeline_body["handoff"]["desktop_effect_proof"]["proof_tool"] == "desktop_screenshot"
    assert timeline_body["handoff"]["desktop_effect_proof_repairs"]["latest_outcome"] == "metadata_refreshed"

    replay = client.get(f"/api/runs/{created.id}/replay")
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["desktop_effect_proof"]["proof_snapshot"]["id"] == "desktop-proof"
    assert replay_body["desktop_effect_proof_repairs"]["latest_outcome"] == "metadata_refreshed"
    assert replay_body["handoff"]["desktop_effect_proof"]["proof_snapshot"]["id"] == "desktop-proof"
    assert replay_body["handoff"]["desktop_effect_proof_repairs"]["entries"][0]["proof_snapshot_id"] == "desktop-proof"

    replay_md = client.get(f"/api/runs/{created.id}/replay.md")
    assert replay_md.status_code == 200
    assert "## Desktop Effect Proof" in replay_md.text
    assert "## Desktop Effect Proof Repairs" in replay_md.text
    assert "metadata_refreshed" in replay_md.text
    assert "desktop-proof" in replay_md.text


def test_self_scaffold_review_outcomes_api(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Let Ornith reshape its scaffold safely",
        "Self scaffold reviews API",
        str(tmp_path),
        [],
    )
    created.state.patch_applications.append(
        PatchApplication(
            id="apply-api-1",
            patch_id="patch-api-1",
            status="applied",
            files=["app.py"],
            backup_id="backup-api-1",
            manifest_path=str(tmp_path / "manifest-api.json"),
            summary="Applied patch-api-1 to app.py.",
            applied_at="2026-06-29T00:00:00+00:00",
        )
    )
    store.update_run(created.id, state=created.state)
    store.append_event(
        created.id,
        "operator_action_reviewed",
        "Operator accepted self-scaffold change intent for current guard/reorient changes.",
        {
            "operator_action": {"ui_target": "self_scaffold", "reason": "self_scaffold", "action": "Review guard posture."},
            "self_scaffold_review": {
                "status": "needs_review",
                "change_count": 2,
                "guard_count": 1,
                "reviewed_change_count": 2,
                "reviewed_change_ids": ["guard-1", "edit_evidence:0:patch-apply-applied-patch-api-1-app-py"],
                "remaining_goal_review": False,
            },
        },
    )

    response = client.get(f"/api/runs/{created.id}/self-scaffold-reviews")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reviewed"
    assert body["accepted_count"] == 1
    assert body["latest_reviewed_change_ids"] == ["guard-1", "edit_evidence:0:patch-apply-applied-patch-api-1-app-py"]

    rollback_response = client.get(f"/api/runs/{created.id}/self-scaffold-rollback-intents")
    assert rollback_response.status_code == 200
    rollback_body = rollback_response.json()
    assert rollback_body["status"] == "needs_approval"
    assert rollback_body["patch_rollback_count"] == 1
    rollback_entry = next(entry for entry in rollback_body["entries"] if entry["action_kind"] == "patch_rollback")
    assert rollback_entry["requires_approval"] is True
    assert rollback_entry["mutation_automatic"] is False

    rollback_approval_response = client.post(f"/api/runs/{created.id}/patches/patch-api-1/rollback")
    assert rollback_approval_response.status_code == 200
    assert rollback_approval_response.json()["status"] == "waiting_approval"
    approvals = store.list_approvals(created.id, status="pending")
    assert len(approvals) == 1
    assert approvals[0]["action_kind"] == "patch_rollback"
    assert approvals[0]["payload"]["args"]["patch_id"] == "patch-api-1"
    assert approvals[0]["payload"]["args"]["backup_id"] == "backup-api-1"
    assert approvals[0]["payload"]["preview"]["requires_approval"] is True
    assert approvals[0]["payload"]["preview"]["mutation_automatic"] is False
    assert all(application.status != "rolled_back" for application in store.get_run(created.id).state.patch_applications)
    duplicate_rollback = client.post(f"/api/runs/{created.id}/patches/patch-api-1/rollback")
    assert duplicate_rollback.status_code == 200
    assert len(store.list_approvals(created.id, status="pending")) == 1
    handoff = client.get(f"/api/runs/{created.id}/handoff")
    assert handoff.status_code == 200
    assert handoff.json()["self_scaffold_reviews"]["accepted_count"] == 1
    assert handoff.json()["self_scaffold_rollback_intents"]["patch_rollback_count"] == 1

    timeline = client.get(f"/api/runs/{created.id}/timeline")
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    assert timeline_body["self_scaffold_reviews"]["latest_reviewed_change_ids"] == ["guard-1", "edit_evidence:0:patch-apply-applied-patch-api-1-app-py"]
    assert timeline_body["self_scaffold_rollback_intents"]["patch_rollback_count"] == 1
    assert timeline_body["handoff"]["self_scaffold_reviews"]["status"] == "reviewed"
    assert timeline_body["handoff"]["self_scaffold_rollback_intents"]["status"] == "needs_approval"

    replay = client.get(f"/api/runs/{created.id}/replay")
    assert replay.status_code == 200
    assert replay.json()["self_scaffold_reviews"]["accepted_count"] == 1
    assert replay.json()["self_scaffold_rollback_intents"]["patch_rollback_count"] == 1

    replay_md = client.get(f"/api/runs/{created.id}/replay.md")
    assert replay_md.status_code == 200
    assert "Review outcomes:" in replay_md.text
    assert "Rollback intents:" in replay_md.text
    assert "patch_rollback" in replay_md.text


def test_resume_quality_endpoint_scores_compact_handoff(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth resume handoffs for long coding tasks",
        "Resume quality API",
        str(tmp_path),
        ["Resume handoff has a concrete next action"],
    )
    created.state.next_step = "Run the focused resume-quality tests and verify the handoff panel."
    created.state.handoff_summary.resume_prompt = (
        f"Resume AgentOrinth run {created.id}. Read Obsidian first, preserve original goal: {created.goal}. "
        f"Active goal: {created.state.goal}. Next action: {created.state.next_step}. "
        "Do not reload raw logs; use this handoff and latest compact events."
    )
    store.update_run(created.id, state=created.state)

    response = client.get(f"/api/runs/{created.id}/resume-quality")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["ready_to_resume"] is True
    assert body["concrete_next_action"] is True
    assert body["has_goal_anchor"] is True
    assert body["status"] in {"ready", "needs_refresh"}


def test_resume_quality_blocks_vague_resume_action(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth resume handoffs for long coding tasks",
        "Resume quality block",
        str(tmp_path),
        ["Resume handoff keeps a concrete next action"],
    )
    created.state.next_step = "continue"
    created.state.handoff_summary.resume_prompt = f"Resume AgentOrinth run {created.id}. Continue."
    store.update_run(created.id, status="paused", state=created.state)

    response = client.post(f"/api/runs/{created.id}/resume")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "paused"
    events = client.get(f"/api/runs/{created.id}/timeline").json()["events"]
    blocked = [event for event in events if event["kind"] == "resume_preflight_blocked"]
    assert blocked
    assert blocked[-1]["data"]["resume_prompt_quality"]["status"] == "blocked"


def test_resume_quality_flows_into_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth resume handoffs for long coding tasks",
        "Resume quality flow",
        str(tmp_path),
        ["Resume quality appears in compact audit surfaces"],
    )
    created.state.next_step = "Inspect /api/runs/{run_id}/resume-quality and replay markdown."
    store.update_run(created.id, state=created.state)

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    timeline = client.get(f"/api/runs/{created.id}/timeline")
    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")

    assert handoff.status_code == 200
    assert handoff.json()["resume_prompt_quality"]["run_id"] == created.id
    assert timeline.status_code == 200
    assert timeline.json()["resume_prompt_quality"]["run_id"] == created.id
    assert timeline.json()["handoff"]["resume_prompt_quality"]["run_id"] == created.id
    assert replay.status_code == 200
    assert replay.json()["resume_prompt_quality"]["run_id"] == created.id
    assert replay.json()["handoff"]["resume_prompt_quality"]["run_id"] == created.id
    assert replay_md.status_code == 200
    assert "## Resume Prompt Quality" in replay_md.text

def test_resume_handoff_diff_detects_changed_next_action(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth resume drift checks for long coding tasks",
        "Resume drift API",
        str(tmp_path),
        ["Resume drift report catches changed handoff context"],
    )
    created.state.next_step = "Run the focused resume drift endpoint test."
    store.update_run(created.id, status="paused", state=created.state)

    resumed = client.post(f"/api/runs/{created.id}/resume")
    assert resumed.status_code == 200
    engine._cancel_task(created.id)
    after_resume = store.get_run(created.id)
    assert after_resume.status in {"queued", "running"}

    after_resume.state.next_step = "Inspect the replay markdown for changed resume drift evidence."
    after_resume.state.milestone = "act"
    store.update_run(created.id, status="queued", state=after_resume.state)

    diff = client.get(f"/api/runs/{created.id}/resume-handoff-diff")
    assert diff.status_code == 200
    body = diff.json()
    assert body["latest_accepted_event_id"]
    assert body["status"] in {"changed", "blocked"}
    assert any(change["field"] == "next_action" for change in body["changes"])

    readiness = client.get(f"/api/runs/{created.id}/action-readiness")
    assert readiness.status_code == 200
    readiness_body = readiness.json()
    assert readiness_body["status"] == "reorient"
    assert any(issue["id"] == "resume_handoff_drift" for issue in readiness_body["issues"])


def test_resume_handoff_diff_flows_into_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth resume drift checks for long coding tasks",
        "Resume drift flow",
        str(tmp_path),
        [],
    )
    created.state.next_step = "Run the resume drift flow test."
    store.update_run(created.id, status="paused", state=created.state)
    resumed = client.post(f"/api/runs/{created.id}/resume")
    assert resumed.status_code == 200
    engine._cancel_task(created.id)

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    timeline = client.get(f"/api/runs/{created.id}/timeline")
    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")

    assert handoff.status_code == 200
    assert handoff.json()["resume_handoff_diff"]["run_id"] == created.id
    assert timeline.status_code == 200
    assert timeline.json()["resume_handoff_diff"]["run_id"] == created.id
    assert timeline.json()["handoff"]["resume_handoff_diff"]["run_id"] == created.id
    assert replay.status_code == 200
    assert replay.json()["resume_handoff_diff"]["run_id"] == created.id
    assert replay.json()["handoff"]["resume_handoff_diff"]["run_id"] == created.id
    assert replay_md.status_code == 200
    assert "## Resume Handoff Drift" in replay_md.text

def test_promotion_audit_flows_into_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "app.py").write_text("print('old')\n", encoding="utf-8")
    (workspace / "app.py").write_text("print('new')\n", encoding="utf-8")
    created = store.create_run(
        "Audit source promotion readiness",
        "Promotion audit API",
        str(workspace),
        [],
        workspace_isolation=WorkspaceIsolation(
            enabled=True,
            mode="copy",
            source_path=str(source),
            workspace_path=str(workspace),
            summary="Isolated copy.",
        ),
    )
    created.state.next_step = "Run focused verification before source promotion."
    store.update_run(created.id, status="paused", state=created.state)

    diff = client.get(f"/api/runs/{created.id}/workspace/diff")
    audit = client.get(f"/api/runs/{created.id}/promotion-audit")
    verification = client.get(f"/api/runs/{created.id}/promotion-verification")
    repair = client.get(f"/api/runs/{created.id}/promotion-repair")
    handoff = client.get(f"/api/runs/{created.id}/handoff")
    timeline = client.get(f"/api/runs/{created.id}/timeline")
    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")

    assert diff.status_code == 200
    assert audit.status_code == 200
    assert audit.json()["status"] == "needs_verification"
    assert any(issue["id"] == "verification_missing" for issue in audit.json()["issues"])
    assert verification.status_code == 200
    assert verification.json()["run_id"] == created.id
    assert verification.json()["status"] == "none"
    assert verification.json()["next_command"]
    assert repair.status_code == 200
    assert repair.json()["run_id"] == created.id
    assert repair.json()["phase"] == "none"
    assert handoff.status_code == 200
    assert handoff.json()["promotion_audit"]["run_id"] == created.id
    assert handoff.json()["promotion_verification"]["run_id"] == created.id
    assert handoff.json()["promotion_repair"]["run_id"] == created.id
    assert timeline.status_code == 200
    assert timeline.json()["promotion_audit"]["run_id"] == created.id
    assert timeline.json()["promotion_verification"]["run_id"] == created.id
    assert timeline.json()["promotion_repair"]["run_id"] == created.id
    assert timeline.json()["handoff"]["promotion_audit"]["run_id"] == created.id
    assert timeline.json()["handoff"]["promotion_verification"]["run_id"] == created.id
    assert timeline.json()["handoff"]["promotion_repair"]["run_id"] == created.id
    assert replay.status_code == 200
    assert replay.json()["promotion_audit"]["run_id"] == created.id
    assert replay.json()["promotion_verification"]["run_id"] == created.id
    assert replay.json()["promotion_repair"]["run_id"] == created.id
    assert replay.json()["handoff"]["promotion_audit"]["run_id"] == created.id
    assert replay.json()["handoff"]["promotion_verification"]["run_id"] == created.id
    assert replay.json()["handoff"]["promotion_repair"]["run_id"] == created.id
    assert replay_md.status_code == 200
    assert "## Promotion Audit" in replay_md.text
    assert "## Promotion Verification" in replay_md.text
    assert "## Promotion Repair" in replay_md.text



def test_workspace_promotion_api_requires_ready_audit(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "README.md").write_text("old\n", encoding="utf-8")
    (workspace / "README.md").write_text("new\n", encoding="utf-8")
    created = store.create_run(
        "Gate source promotion until verified",
        "Promotion audit gate",
        str(workspace),
        [],
        workspace_isolation=WorkspaceIsolation(
            enabled=True,
            mode="copy",
            source_path=str(source),
            workspace_path=str(workspace),
            summary="Isolated copy.",
        ),
    )

    blocked = client.post(f"/api/runs/{created.id}/workspace/promote", json={"files": [], "include_deletions": False})
    assert blocked.status_code == 200
    blocked_body = blocked.json()
    assert blocked_body["status"] == "paused"
    assert blocked_body["state"]["promotion_audit"]["status"] == "needs_verification"
    assert store.list_approvals(created.id, status="pending") == []

    verified = client.post(f"/api/runs/{created.id}/promotion-audit/verify")
    assert verified.status_code == 200
    assert verified.json()["state"]["promotion_audit"]["status"] == "ready"

    ready = client.post(f"/api/runs/{created.id}/workspace/promote", json={"files": [], "include_deletions": False})
    assert ready.status_code == 200
    ready_body = ready.json()
    assert ready_body["status"] == "waiting_approval"
    assert ready_body["state"]["promotion_audit"]["status"] == "ready"
    approvals = store.list_approvals(created.id, status="pending")
    assert approvals[0]["action_kind"] == "workspace_promote"




def test_operator_actions_api_filters_promotion_approval_gates_after_restart(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client_one, _engine_one, store_one = install_test_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "README.md").write_text("old\n", encoding="utf-8")
    (workspace / "README.md").write_text("new\n", encoding="utf-8")
    promoted = store_one.create_run(
        "Filter source-promotion approval gates",
        "Promotion filter API",
        str(workspace),
        [],
        workspace_isolation=WorkspaceIsolation(
            enabled=True,
            mode="copy",
            source_path=str(source),
            workspace_path=str(workspace),
            summary="Isolated copy.",
        ),
    )
    ordinary = store_one.create_run("Review ordinary approval", "Ordinary approval", str(tmp_path), [])
    store_one.create_approval(ordinary.id, "shell", {"command": "python -m pytest"}, "Approve ordinary shell.")
    store_one.update_run(ordinary.id, status="waiting_approval", state=ordinary.state)

    blocked = client_one.post(f"/api/runs/{promoted.id}/workspace/promote", json={"files": [], "include_deletions": False})
    assert blocked.status_code == 200
    assert blocked.json()["state"]["promotion_audit"]["status"] == "needs_verification"
    verified = client_one.post(f"/api/runs/{promoted.id}/promotion-audit/verify")
    assert verified.status_code == 200
    ready = client_one.post(f"/api/runs/{promoted.id}/workspace/promote", json={"files": [], "include_deletions": False})
    assert ready.status_code == 200
    assert ready.json()["status"] == "waiting_approval"

    client_two, _engine_two, _store_two = install_test_runtime(monkeypatch, tmp_path)
    recovered = client_two.post("/api/supervisor/recover")
    assert recovered.status_code == 200
    all_queue = client_two.get("/api/operator-actions?limit=50")
    filtered_queue = client_two.get("/api/operator-actions?limit=50&filter=promotion_approvals")
    proof_filter = client_two.get("/api/operator-actions?limit=50&filter=proof_reviews")
    invalid_filter = client_two.get("/api/operator-actions?filter=not_real")

    assert all_queue.status_code == 200
    all_body = all_queue.json()
    assert all_body["approval_count"] == 2
    assert all_body["promotion_approval_count"] == 1
    assert any(item["approval_kind"] == "workspace_promote" and item["promotion_gate"] for item in all_body["items"])
    assert any(item["approval_kind"] == "shell" and not item["promotion_gate"] for item in all_body["items"])
    assert filtered_queue.status_code == 200
    filtered_body = filtered_queue.json()
    assert filtered_body["total_count"] == all_body["total_count"]
    assert filtered_body["approval_count"] == all_body["approval_count"]
    assert filtered_body["promotion_approval_count"] == 1
    assert filtered_body["items"]
    assert all(item["promotion_gate"] for item in filtered_body["items"])
    assert {item["approval_kind"] for item in filtered_body["items"]} == {"workspace_promote"}
    assert proof_filter.status_code == 200
    assert proof_filter.json()["items"] == []
    assert invalid_filter.status_code == 400

def test_operator_actions_api_surfaces_desktop_approval_after_restart(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    _client_one, _engine_one, store_one = install_test_runtime(monkeypatch, tmp_path)
    created = store_one.create_run(
        "Approve supervised desktop action",
        "Desktop approval API",
        str(tmp_path),
        [],
    )
    approval = store_one.create_approval(
        created.id,
        "desktop_click",
        {"tool_name": "desktop_click", "args": {"x": 240, "y": 540, "window_title": "AgentOrinth Dashboard"}},
        "Approve supervised desktop click in the visible dashboard.",
    )
    store_one.update_run(created.id, status="waiting_approval", state=created.state)

    client_two, _engine_two, _store_two = install_test_runtime(monkeypatch, tmp_path)
    recovered = client_two.post("/api/supervisor/recover")
    all_queue = client_two.get("/api/operator-actions?limit=20")

    assert recovered.status_code == 200
    assert all_queue.status_code == 200
    body = all_queue.json()
    desktop_items = [item for item in body["items"] if item["approval_kind"] == "desktop_click"]

    assert body["approval_count"] == 1
    assert body["promotion_approval_count"] == 0
    assert desktop_items
    item = desktop_items[0]
    assert item["approval_id"] == approval["id"]
    assert item["ui_target"] == "approval"
    assert item["promotion_gate"] is False
    assert item["endpoint"] == f"/api/runs/{created.id}/approvals"
    assert "desktop_click" in item["action"]
    assert f"approval_id={approval['id']}" in item["details"]
def test_patch_apply_approval_endpoint_uses_existing_patch_proposal(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "demo.py"
    target.write_text("api_key=super-secret\nprint('old')\n", encoding="utf-8")
    created = store.create_run("Apply proposed patch", "Patch approval API", str(workspace), [])
    created.state.patch_proposals.append(
        PatchProposal(
            id="patch-demo",
            title="Update demo",
            summary="Replace old output without exposing api_key=super-secret in previews.",
            files=["demo.py"],
            diff=(
                "--- a/demo.py\n"
                "+++ b/demo.py\n"
                "@@ -1,2 +1,2 @@\n"
                "-api_key=super-secret\n"
                "-print('old')\n"
                "+api_key=super-secret-new\n"
                "+print('new')\n"
            ),
        )
    )
    store.update_run(created.id, state=created.state)

    response = client.post(f"/api/runs/{created.id}/patches/patch-demo/apply")

    assert response.status_code == 200
    assert response.json()["status"] == "waiting_approval"
    approvals = store.list_approvals(created.id, status="pending")
    assert len(approvals) == 1
    assert approvals[0]["action_kind"] == "patch_apply"
    assert approvals[0]["payload"]["args"]["patch_id"] == "patch-demo"
    assert approvals[0]["payload"]["args"]["diff"].startswith("--- a/demo.py")
    preview = approvals[0]["payload"]["preview"]
    assert preview["patch_id"] == "patch-demo"
    assert preview["title"] == "Update demo"
    assert preview["files"][0]["path"] == "demo.py"
    assert preview["files"][0]["diff_excerpt"].startswith("--- a/demo.py")
    assert "super-secret" not in preview["summary"]
    assert "super-secret" not in preview["files"][0]["diff_excerpt"]
    assert "[REDACTED]" in preview["files"][0]["diff_excerpt"]

    reviews_response = client.get(f"/api/runs/{created.id}/approval-reviews?status=pending")
    assert reviews_response.status_code == 200
    reviews = reviews_response.json()
    assert len(reviews) == 1
    assert "payload" not in reviews[0]
    assert reviews[0]["action_kind"] == "patch_apply"
    assert reviews[0]["high_risk"] is True
    assert reviews[0]["reviewed"] is False
    assert reviews[0]["review_count"] == 0
    assert reviews[0]["latest_review_event_id"] == 0
    assert reviews[0]["payload_keys"] == ["args", "files", "preview", "summary", "tool_name"]
    assert reviews[0]["preview"]["patch_id"] == "patch-demo"
    assert reviews[0]["preview"]["files"][0]["path"] == "demo.py"
    assert "super-secret" not in repr(reviews)
    assert "[REDACTED]" in repr(reviews)

    invalid_reviews = client.get(f"/api/runs/{created.id}/approval-reviews?status=bogus")
    assert invalid_reviews.status_code == 400

    duplicate = client.post(f"/api/runs/{created.id}/patches/patch-demo/apply")
    assert duplicate.status_code == 200
    assert len(store.list_approvals(created.id, status="pending")) == 1

    approved = client.post(f"/api/runs/{created.id}/approvals/{approvals[0]['id']}/approve")
    engine._cancel_task(created.id)
    assert approved.status_code == 200
    assert target.read_text(encoding="utf-8") == "api_key=super-secret-new\nprint('new')\n"
    updated = store.get_run(created.id)
    assert updated.state.patch_proposals[-1].status == "applied"
    assert updated.state.patch_applications[-1].patch_id == "patch-demo"


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
    timeline_body = timeline.json()
    assert timeline_body["resume_decisions"]["latest_accepted"]["source"] == "manual"
    assert timeline_body["checkpoint_quality_resumes"]["status"] == "none"
    assert timeline_body["checkpoint_quality_resumes"]["repair_count"] == 0
    decisions = client.get(f"/api/runs/{created.id}/resume-decisions")
    assert decisions.status_code == 200
    assert decisions.json()["latest_accepted"]["policy_action"] == "complete"
    assert decisions.json()["comparison_summary"]

    paused_again = client.post(f"/api/runs/{created.id}/pause")
    assert paused_again.status_code == 200
    assert paused_again.json()["status"] == "paused"

    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")
    assert replay.status_code == 200
    assert replay.json()["run_id"] == created.id
    assert replay.json()["event_count"] >= 3
    assert replay.json()["checkpoint_quality_resumes"]["status"] == "none"
    assert replay_md.status_code == 200
    assert "## Checkpoint-Quality Resume Repairs" not in replay_md.text



def test_compact_failure_context_survives_restart_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    _client_one, engine_one, store_one = install_test_runtime(monkeypatch, tmp_path)
    created = store_one.create_run(
        "Recover compact failure after restart",
        "Failure context restart",
        str(tmp_path),
        ["Tests pass"],
    )
    result = ToolResult(
        False,
        "shell",
        "exit 1: python broken.py",
        {
            "command": "python broken.py",
            "returncode": 1,
            "stderr": "File broken.py, line 3\nSyntaxError: invalid syntax\napi_key=super-secret",
        },
    )

    asyncio.run(engine_one._record_tool_result(created.id, result))
    recorded = store_one.get_run(created.id)
    assert recorded.state.failure_records[0].kind == "syntax_error"
    assert recorded.state.handoff_summary.failure_records[0].kind == "syntax_error"
    assert "super-secret" not in recorded.state.handoff_summary.failure_records[0].evidence_excerpt

    client_two, _engine_two, store_two = install_test_runtime(monkeypatch, tmp_path)
    reloaded = store_two.get_run(created.id)
    assert reloaded.state.failure_records[0].command == "python broken.py"

    handoff = client_two.get(f"/api/runs/{created.id}/handoff")
    timeline = client_two.get(f"/api/runs/{created.id}/timeline")
    replay = client_two.get(f"/api/runs/{created.id}/replay")
    replay_md = client_two.get(f"/api/runs/{created.id}/replay.md")
    assert handoff.status_code == 200
    assert timeline.status_code == 200
    assert replay.status_code == 200
    assert replay_md.status_code == 200

    replay_body = replay.json()
    failure_views = [
        handoff.json()["failure_records"][0],
        timeline.json()["failure_records"][0],
        replay_body["failure_records"][0],
        replay_body["handoff"]["failure_records"][0],
    ]
    for failure in failure_views:
        assert failure["kind"] == "syntax_error"
        assert failure["tool"] == "shell"
        assert failure["command"] == "python broken.py"
        assert failure["returncode"] == 1
        assert "SyntaxError" in failure["evidence_excerpt"]
        assert "super-secret" not in failure["evidence_excerpt"]
        assert "[REDACTED]" in failure["evidence_excerpt"]
        assert "patch the smallest affected file" in failure["recovery_hint"]

    failure_ledger = handoff.json()["action_context"]["failure_ledger"]
    assert any("cmd=python broken.py" in item and "rc=1" in item for item in failure_ledger)
    assert "## Failures" in replay_md.text
    assert "command `python broken.py`" in replay_md.text
    assert "[REDACTED]" in replay_md.text
    assert "super-secret" not in replay_md.text


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


def test_report_integrity_refresh_reasons_flow_into_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Refresh reason API", "Refresh reason API", str(tmp_path), [])
    reason = "stale:handoff.current_objective | expected=New goal | actual=Old goal"
    refresh_event = store.append_event(
        created.id,
        "report_integrity_refresh",
        "Refreshed compact handoff and report integrity before resume preflight.",
        {
            "report_integrity": {"status": "ok"},
            "previous_report_integrity": {"status": "needs_refresh"},
            "report_integrity_refresh_reasons": [reason],
            "refresh_reason_count": 1,
        },
    )
    preflight_event = store.append_event(
        created.id,
        "resume_preflight",
        "Resume preflight accepted after refresh.",
        {
            "accepted": True,
            "reason": "Policy simulation accepted resume.",
            "report_integrity_refreshed": True,
            "report_integrity_refresh_reasons": [reason],
        },
    )

    handoff = client.get(f"/api/runs/{created.id}/handoff")
    timeline = client.get(f"/api/runs/{created.id}/timeline")
    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")

    assert handoff.status_code == 200
    handoff_refresh = handoff.json()["report_integrity_refreshes"][0]
    assert handoff_refresh["event_id"] == refresh_event["id"]
    assert handoff_refresh["preflight_event_id"] == preflight_event["id"]
    assert handoff_refresh["reasons"] == [reason]
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    assert timeline_body["report_integrity_refreshes"][0]["event_id"] == refresh_event["id"]
    assert timeline_body["handoff"]["report_integrity_refreshes"][0]["preflight_event_id"] == preflight_event["id"]
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["report_integrity_refreshes"][0]["reasons"] == [reason]
    assert replay_body["handoff"]["report_integrity_refreshes"][0]["event_id"] == refresh_event["id"]
    assert replay_md.status_code == 200
    assert "Refreshes: `1`" in replay_md.text
    assert reason in replay_md.text

def test_checkpoint_quality_flows_into_handoff_timeline_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Checkpoint quality API", "Checkpoint quality API", str(tmp_path), [])
    created.state.next_step = "Verify checkpoint quality surfaces."
    created.state.handoff_summary.resume_prompt = (
        f"Resume AgentOrinth run {created.id}. Active goal: {created.state.goal}. "
        "Next action: Verify checkpoint quality surfaces. "
        "Do not reload raw logs; use this handoff and latest compact events."
    )
    reason = "stale:handoff.next_action | expected=Verify checkpoint quality surfaces | actual=Old"
    refresh_event = store.append_event(
        created.id,
        "report_integrity_refresh",
        "Refreshed compact handoff before checkpoint quality test.",
        {
            "report_integrity": {"status": "ok"},
            "previous_report_integrity": {"status": "needs_refresh"},
            "report_integrity_refresh_reasons": [reason],
            "refresh_reason_count": 1,
        },
    )
    created.state.report_integrity_refreshes = [
        ReportIntegrityRefreshRecord(
            event_id=refresh_event["id"],
            report_status="ok",
            previous_report_status="needs_refresh",
            reason_count=1,
            reasons=[reason],
        )
    ]
    store.update_run(created.id, state=created.state)
    engine.memory.append_run_started(created)
    engine.memory.append_checkpoint(created, created.state, "paused")
    quality = CheckpointQualityReport.model_validate(engine.get_checkpoint_quality(created.id))
    stored = store.get_run(created.id)
    stored.state.checkpoint_quality = quality
    stored.state.handoff_summary.checkpoint_quality = quality
    store.update_run(created.id, state=stored.state)

    endpoint = client.get(f"/api/runs/{created.id}/checkpoint-quality")
    handoff = client.get(f"/api/runs/{created.id}/handoff")
    timeline = client.get(f"/api/runs/{created.id}/timeline")
    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")

    assert endpoint.status_code == 200
    assert endpoint.json()["status"] == "ready"
    assert endpoint.json()["expected_refresh_event_id"] == refresh_event["id"]
    assert handoff.status_code == 200
    assert handoff.json()["checkpoint_quality"]["status"] == "ready"
    assert timeline.status_code == 200
    assert timeline.json()["checkpoint_quality"]["has_resume_prompt"] is True
    assert timeline.json()["handoff"]["checkpoint_quality"]["expected_refresh_event_id"] == refresh_event["id"]
    assert replay.status_code == 200
    assert replay.json()["checkpoint_quality"]["run_id"] == created.id
    assert replay.json()["handoff"]["checkpoint_quality"]["status"] == "ready"
    assert replay_md.status_code == 200
    assert "## Checkpoint Quality" in replay_md.text
    assert "Status: `ready`" in replay_md.text

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
    missing_sections = {check["section"] for check in body["checks"] if check["status"] == "missing"}
    assert "handoff.desktop_effect_proof" in missing_sections
    assert body["recommended_action"] == "Refresh handoff and replay reports before resuming the loop."



def test_report_integrity_endpoint_detects_stale_desktop_effect_proof_handoff(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Desktop proof integrity", "Desktop Proof Integrity API", str(tmp_path), [])
    created.state.handoff_summary.desktop_effect_proof = DesktopEffectProofReport.model_validate(
        engine.get_desktop_effect_proof_preview(created.id, limit=8)
    )
    created.state.tool_calls.append(
        ToolCallRecord(
            id="desktop-click-1",
            name="desktop_click",
            ok=True,
            summary="Clicked the visible Save button.",
            created_at="2026-06-29T10:00:00+00:00",
        )
    )
    store.update_run(created.id, state=created.state)

    response = client.get(f"/api/runs/{created.id}/report-integrity")

    assert response.status_code == 200
    body = response.json()
    checks = {check["section"]: check for check in body["checks"]}
    assert body["status"] == "needs_refresh"
    assert checks["handoff.desktop_effect_proof.status"]["status"] == "stale"
    assert checks["handoff.desktop_effect_proof.status"]["expected"] == "needs_proof"
    assert checks["handoff.desktop_effect_proof.status"]["actual"] == "not_required"
    assert checks["handoff.desktop_effect_proof.latest_action_id"]["status"] == "stale"
    assert checks["handoff.desktop_effect_proof.latest_action_id"]["expected"] == "desktop-click-1"

def test_report_integrity_endpoint_detects_stale_approval_review_handoff(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Approval integrity endpoint", "Approval Integrity API", str(tmp_path), [])
    approval = store.create_approval(
        created.id,
        "shell",
        {"tool_name": "shell", "args": {"command": "python -m pytest"}},
        "Approve shell verification.",
    )
    created.state.handoff_summary.approvals = []
    created.state.handoff_summary.approval_reviews = []
    store.update_run(created.id, state=created.state)

    response = client.get(f"/api/runs/{created.id}/report-integrity")

    assert response.status_code == 200
    body = response.json()
    checks = {check["section"]: check for check in body["checks"]}
    assert body["status"] == "needs_refresh"
    assert checks["handoff.approval_reviews"]["status"] == "missing"
    assert checks["handoff.approval_reviews"]["expected"] == str(approval["id"])
    assert checks["handoff.approvals.pending_count"]["status"] == "stale"
    assert checks["handoff.approvals.pending_count"]["expected"] == "1"
    assert checks["handoff.approvals.pending_count"]["actual"] == "0"


def test_report_integrity_endpoint_detects_stale_promotion_route_handoff(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Promotion route integrity", "Promotion Route Integrity API", str(tmp_path), [])
    approval = store.create_approval(
        created.id,
        "workspace_promote",
        {"tool_name": "workspace_promote", "args": {"source_path": str(tmp_path)}},
        "Promote isolated workspace changes.",
    )
    store.append_event(
        created.id,
        "operator_action_reviewed",
        "Operator opened queued action promotion_audit_promotion_approval_history_unresolved.",
        {
            "decision": "open",
            "operator_action": {
                "id": f"{created.id}:promotion_audit_promotion_approval_history_unresolved:{approval['id']}",
                "run_id": created.id,
                "title": created.title,
                "reason": "promotion_audit_promotion_approval_history_unresolved",
                "action": "Resolve reviewed workspace_promote approval before source promotion.",
                "endpoint": f"/api/runs/{created.id}/approvals",
                "method": "GET",
                "ui_target": "approval",
                "approval_id": approval["id"],
                "approval_kind": "workspace_promote",
                "details": [
                    "audit_status=ready",
                    "issue=promotion_approval_history_unresolved",
                    f"approval_id={approval['id']}",
                ],
            },
        },
    )
    store.update_run(created.id, status="waiting_approval", state=created.state)

    response = client.get(f"/api/runs/{created.id}/report-integrity")

    assert response.status_code == 200
    body = response.json()
    checks = {check["section"]: check for check in body["checks"]}
    assert body["status"] == "needs_refresh"
    assert checks["handoff.operator_dispatches.promotion_route_count"]["status"] == "stale"
    assert checks["handoff.operator_dispatches.promotion_route_count"]["expected"] == "1"
    assert checks["handoff.operator_dispatches.promotion_route_count"]["actual"] == "0"
    assert checks["handoff.operator_dispatches.unresolved_promotion_approval_ids"]["status"] == "mismatch"
    assert checks["handoff.operator_dispatches.unresolved_promotion_approval_ids"]["expected"] == str(approval["id"])
    assert checks["handoff.operator_dispatches.unresolved_promotion_approval_ids"]["actual"] == ""
    assert checks["handoff.operator_dispatches.pending_promotion_route_ids"]["status"] == "mismatch"
    assert checks["handoff.operator_dispatches.pending_promotion_route_ids"]["expected"] == str(approval["id"])
    assert checks["handoff.operator_dispatches.pending_promotion_route_ids"]["actual"] == ""

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
        "git_checkpoint_cadence",
    }.issubset(item_ids)
    patch_item = next(item for item in body["items"] if item["id"] == "patch_first_editing")
    assert patch_item["proof"]["tool_kind"] == "patch_propose"
    assert patch_item["proof"]["evidence_label"] == "edit"
    assert patch_item["proof"]["requires_approval"] is True
    git_item = next(item for item in body["items"] if item["id"] == "git_checkpoint_cadence")
    assert git_item["proof"]["tool_kind"] == "git_checkpoint"
    assert git_item["proof"]["evidence_label"] == "git"


def test_git_checkpoint_endpoint_reports_repo_posture(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run("Git checkpoint endpoint", "Git API", str(tmp_path), [])

    response = client.get(f"/api/runs/{created.id}/git-checkpoint")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created.id
    assert body["status"] in {"needs_remote", "verify_first", "commit_recommended", "push_recommended", "clean", "not_repo"}
    assert body["summary"]
    assert body["recommended_action"]


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
    assert body["self_scaffold_status"] in {"observed", "empty"}
    assert body["self_scaffold_pending_review_count"] == 0
    assert any(check["id"] == "objective_readiness" for check in body["checks"])
    assert any(check["id"] == "operator_dispatch_restart_smoke" for check in body["checks"])
    assert any(check["id"] == "self_scaffold_review" for check in body["checks"])


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
    assert body["self_scaffold_reviewed"] is True
    assert body["self_scaffold_review_event_id"]
    assert body["self_scaffold_reviewed_change_count"] >= 1
    assert body["post_review_handoff_goal_preserved"] is True
    assert body["post_review_handoff_next_action_preserved"] is True
    assert body["post_review_resume_prompt_goal_preserved"] is True
    assert body["post_review_resume_prompt_next_action_preserved"] is True
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
        "self_scaffold_guard_seeded",
        "self_scaffold_review",
        "post_review_handoff_alignment",
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
    assert report.json()["self_scaffold_reviewed"] is True
    assert report.json()["post_review_resume_prompt_next_action_preserved"] is True
    assert timeline.json()["readiness_rehearsal"]["status"] == "passed"
    assert handoff.json()["readiness_rehearsal"]["status"] == "passed"
    assert replay.json()["readiness_rehearsal"]["status"] == "passed"
    assert replay.json()["handoff"]["readiness_rehearsal"]["status"] == "passed"
    assert "## Readiness Rehearsal" in replay_md.text
    assert "Self scaffold review" in replay_md.text
    assert "Post-review handoff" in replay_md.text

    ledger = client.get("/api/rehearsals/readiness-claim")
    assert ledger.status_code == 200
    ledger_body = ledger.json()
    assert ledger_body["status"] == "passed"
    assert ledger_body["total_count"] == 1
    assert ledger_body["passed_count"] == 1
    assert ledger_body["failed_count"] == 0
    assert ledger_body["latest"]["run_id"] == run_id
    assert ledger_body["latest"]["passed_steps"] == len(body["steps"])
    assert ledger_body["latest"]["self_scaffold_reviewed"] is True
    assert ledger_body["latest"]["self_scaffold_reviewed_change_count"] >= 1
    assert ledger_body["latest"]["post_review_handoff_goal_preserved"] is True
    assert ledger_body["latest"]["post_review_resume_prompt_next_action_preserved"] is True
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


def test_restart_checkpoint_quality_handoff_refresh_writes_ready_obsidian_note(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    _client_one, engine_one, store_one = install_test_runtime(monkeypatch, tmp_path)
    created = store_one.create_run(
        "Improve AgentOrinth into a Codex-like long-running local coding harness",
        "Checkpoint refresh restart",
        str(tmp_path),
        ["Tests pass"],
    )
    created.state.next_step = "Resume only after Obsidian checkpoint quality is ready."
    store_one.update_run(created.id, status="paused", state=created.state)
    assert engine_one.memory.read_run_note(created.id) == ""

    client_two, _engine_two, store_two = install_test_runtime(monkeypatch, tmp_path)
    recovered = client_two.post("/api/supervisor/recover")
    assert recovered.status_code == 200
    recovered_body = recovered.json()
    assert recovered_body["checkpoint_quality_attention_count"] == 1
    assert recovered_body["operator_action_queue"]["checkpoint_quality_count"] == 1

    queue = client_two.get("/api/operator-actions?limit=50")
    assert queue.status_code == 200
    queue_body = queue.json()
    assert queue_body["checkpoint_quality_count"] == 1
    checkpoint_item = next(item for item in queue_body["items"] if item["reason"] == "checkpoint_quality")
    assert checkpoint_item["ui_target"] == "handoff_refresh"

    dispatched = client_two.post(
        "/api/operator-actions/dispatch",
        json={"item_id": checkpoint_item["id"], "decision": "dispatch", "confirmed": True},
    )
    assert dispatched.status_code == 200
    dispatched_body = dispatched.json()
    assert dispatched_body["status"] == "dispatched"
    assert dispatched_body["action_taken"] == "handoff_refresh"
    assert dispatched_body["queue"]["checkpoint_quality_count"] == 0

    note = _engine_two.memory.read_run_note(created.id)
    assert "### Checkpoint:" in note
    assert "- Active goal: Improve AgentOrinth into a Codex-like long-running local coding harness" in note
    assert "- Next action: Resume from refreshed compact context and handoff." in note
    assert "- Resume prompt: Resume AgentOrinth run" in note
    assert "Do not reload raw logs" in note

    quality = client_two.get(f"/api/runs/{created.id}/checkpoint-quality")
    assert quality.status_code == 200
    assert quality.json()["status"] == "ready"

    persisted = store_two.get_run(created.id)
    assert persisted.state.checkpoint_quality.status == "ready"
    assert persisted.state.handoff_summary.checkpoint_quality.status == "ready"

    client_three, _engine_three, store_three = install_test_runtime(monkeypatch, tmp_path)
    restarted = store_three.get_run(created.id)
    assert restarted.state.checkpoint_quality.status == "ready"
    assert restarted.state.handoff_summary.checkpoint_quality.status == "ready"

    recovered_again = client_three.post("/api/supervisor/recover")
    assert recovered_again.status_code == 200
    assert recovered_again.json()["checkpoint_quality_attention_count"] == 0
    queue_again = client_three.get("/api/operator-actions?limit=50")
    assert queue_again.status_code == 200
    queue_again_body = queue_again.json()
    assert queue_again_body["checkpoint_quality_count"] == 0
    assert not any(item["reason"] == "checkpoint_quality" for item in queue_again_body["items"])

    handoff = client_three.get(f"/api/runs/{created.id}/handoff")
    assert handoff.status_code == 200
    handoff_body = handoff.json()
    assert handoff_body["checkpoint_quality"]["status"] == "ready"
    assert handoff_body["checkpoint_quality_resumes"]["status"] == "awaiting_resume"
    assert handoff_body["checkpoint_quality_resumes"]["repair_count"] == 1
    assert handoff_body["checkpoint_quality_resumes"]["awaiting_resume_count"] == 1
    persisted_awaiting = store_three.get_run(created.id)
    assert persisted_awaiting.state.checkpoint_quality_resumes.status == "awaiting_resume"
    assert persisted_awaiting.state.handoff_summary.checkpoint_quality_resumes.awaiting_resume_count == 1

    resumed = client_three.post(f"/api/runs/{created.id}/resume")
    _engine_three._cancel_task(created.id)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"

    events = store_three.list_events(created.id)
    accepted_preflight = next(event for event in events if event["kind"] == "resume_preflight")
    assert accepted_preflight["data"]["accepted"] is True
    assert accepted_preflight["data"]["source"] == "manual"
    assert accepted_preflight["data"]["policy_simulation"]["policy_action"] == "verify"
    assert accepted_preflight["data"]["resume_prompt_quality"]["status"] == "ready"
    assert not any(event["kind"] == "resume_preflight_blocked" for event in events)

    resumed_quality = client_three.get(f"/api/runs/{created.id}/checkpoint-quality")
    assert resumed_quality.status_code == 200
    assert resumed_quality.json()["status"] == "ready"
    resumed_handoff = client_three.get(f"/api/runs/{created.id}/handoff")
    assert resumed_handoff.status_code == 200
    resumed_handoff_body = resumed_handoff.json()
    assert resumed_handoff_body["checkpoint_quality"]["status"] == "ready"
    assert resumed_handoff_body["checkpoint_quality_resumes"]["status"] == "resumed"
    assert resumed_handoff_body["checkpoint_quality_resumes"]["resumed_after_repair_count"] == 1
    assert resumed_handoff_body["checkpoint_quality_resumes"]["latest"]["resume_event_id"] == accepted_preflight["id"]
    stale_before_timeline = store_three.get_run(created.id)
    stale_before_timeline.state.checkpoint_quality_resumes = persisted_awaiting.state.checkpoint_quality_resumes
    stale_before_timeline.state.handoff_summary.checkpoint_quality_resumes = (
        persisted_awaiting.state.handoff_summary.checkpoint_quality_resumes
    )
    store_three.update_run(created.id, state=stale_before_timeline.state)

    timeline = client_three.get(f"/api/runs/{created.id}/timeline")
    assert timeline.status_code == 200
    timeline_resume = timeline.json()["checkpoint_quality_resumes"]
    assert timeline_resume["status"] == "resumed"
    assert timeline_resume["repair_count"] == 1
    assert timeline_resume["latest"]["repair_reason"] == "checkpoint_quality"
    assert timeline_resume["latest"]["repair_ui_target"] == "handoff_refresh"
    assert timeline_resume["latest"]["resume_event_id"] == accepted_preflight["id"]
    assert timeline_resume["latest"]["checkpoint_quality_ready"] is True
    persisted_resumed = store_three.get_run(created.id)
    assert persisted_resumed.state.checkpoint_quality_resumes.status == "resumed"
    assert persisted_resumed.state.handoff_summary.checkpoint_quality_resumes.latest.resume_event_id == accepted_preflight["id"]

    stale_before_replay = store_three.get_run(created.id)
    stale_before_replay.state.checkpoint_quality_resumes = persisted_awaiting.state.checkpoint_quality_resumes
    stale_before_replay.state.handoff_summary.checkpoint_quality_resumes = (
        persisted_awaiting.state.handoff_summary.checkpoint_quality_resumes
    )
    store_three.update_run(created.id, state=stale_before_replay.state)

    replay = client_three.get(f"/api/runs/{created.id}/replay")
    replay_md = client_three.get(f"/api/runs/{created.id}/replay.md")
    assert replay.status_code == 200
    assert replay.json()["checkpoint_quality_resumes"]["status"] == "resumed"
    assert replay.json()["handoff"]["checkpoint_quality_resumes"]["latest"]["resume_event_id"] == accepted_preflight["id"]
    persisted_replay = store_three.get_run(created.id)
    assert persisted_replay.state.checkpoint_quality_resumes.status == "resumed"
    assert persisted_replay.state.handoff_summary.checkpoint_quality_resumes.latest.resume_event_id == accepted_preflight["id"]
    assert replay_md.status_code == 200
    assert "## Checkpoint-Quality Resume Repairs" in replay_md.text
    assert f"resume `#{accepted_preflight['id']}` `verify` accepted `True`" in replay_md.text

    repair_event_id = timeline_resume["latest"]["repair_completed_event_id"]
    client_four, engine_four, store_four = install_test_runtime(monkeypatch, tmp_path)
    restarted_after_resume = store_four.get_run(created.id)
    assert restarted_after_resume.state.checkpoint_quality_resumes.status == "resumed"
    assert restarted_after_resume.state.handoff_summary.checkpoint_quality_resumes.latest.resume_event_id == accepted_preflight["id"]
    memory_context = engine_four._reload_anchor_context(restarted_after_resume, restarted_after_resume.state)
    assert restarted_after_resume.state.checkpoint_quality_resumes.status == "resumed"
    assert restarted_after_resume.state.handoff_summary.checkpoint_quality_resumes.status == "resumed"
    assert (
        restarted_after_resume.state.handoff_summary.checkpoint_quality_resumes.latest.resume_event_id
        == accepted_preflight["id"]
    )

    compact_prompt, context_snapshot = engine_four.context_compiler.compile(
        restarted_after_resume,
        restarted_after_resume.state,
        memory_context,
        store_four.list_events(created.id, limit=40),
    )
    assert "checkpoint_quality_resumes" in context_snapshot.sections
    assert "Checkpoint-quality resume repairs: resumed" in compact_prompt
    assert f"repair=#{repair_event_id}:checkpoint_quality:handoff_refresh" in compact_prompt
    assert f"resume=#{accepted_preflight['id']}:verify:accepted" in compact_prompt
    assert "checkpoint_ready=True:ready" in compact_prompt

    engine_four.memory.append_checkpoint(restarted_after_resume, restarted_after_resume.state, "resumed")
    note_after_resume = engine_four.memory.read_run_note(created.id)
    assert "- Checkpoint-quality resume repair: resumed repairs=1 resumed=1 blocked=0 awaiting=0" in note_after_resume
    assert f"repair=#{repair_event_id}:checkpoint_quality:handoff_refresh" in note_after_resume
    assert f"resume=#{accepted_preflight['id']}:verify:accepted" in note_after_resume
    assert "checkpoint=ready:True" in note_after_resume


def test_supervisor_queues_checkpoint_quality_handoff_refresh(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth into a Codex-like long-running local coding harness",
        "Checkpoint quality queue",
        str(tmp_path),
        [],
    )
    created.state.next_step = "Resume only after Obsidian checkpoint quality is ready."
    store.update_run(created.id, status="paused", state=created.state)

    recovered = client.post("/api/supervisor/recover")

    assert recovered.status_code == 200
    body = recovered.json()
    assert body["checkpoint_quality_attention_count"] >= 1
    run_entry = next(item for item in body["runs"] if item["run_id"] == created.id)
    assert run_entry["checkpoint_quality_requires_attention"] is True
    assert "checkpoint_quality" in run_entry["operator_attention_reasons"]
    assert run_entry["operator_attention_severity"] == "blocked"

    queue = client.get("/api/operator-actions?limit=50")
    assert queue.status_code == 200
    queue_body = queue.json()
    assert queue_body["checkpoint_quality_count"] == 1
    queue_items = {item["reason"]: item for item in queue_body["items"]}
    checkpoint_item = queue_items["checkpoint_quality"]
    assert checkpoint_item["ui_target"] == "handoff_refresh"
    assert checkpoint_item["method"] == "POST"
    assert checkpoint_item["endpoint"] == f"/api/runs/{created.id}/handoff/refresh"

    dispatched = client.post(
        "/api/operator-actions/dispatch",
        json={"item_id": checkpoint_item["id"], "decision": "dispatch", "confirmed": True},
    )
    assert dispatched.status_code == 200
    dispatched_body = dispatched.json()
    assert dispatched_body["status"] == "dispatched"
    assert dispatched_body["action_taken"] == "handoff_refresh"
    assert dispatched_body["queue"]["checkpoint_quality_count"] == 0

    refreshed = client.post("/api/supervisor/recover").json()
    refreshed_entry = next(item for item in refreshed["runs"] if item["run_id"] == created.id)
    assert refreshed_entry["checkpoint_quality"]["status"] == "ready"
    assert refreshed_entry["checkpoint_quality_requires_attention"] is False
    assert refreshed["checkpoint_quality_attention_count"] == 0
    assert refreshed["operator_action_queue"]["checkpoint_quality_count"] == 0

def test_operator_actions_route_ornith_preflight_refreshes(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, engine, store = install_test_runtime(monkeypatch, tmp_path)
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
    assert latest_action["context_target_tokens"] == engine.context_compiler.target_tokens

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
    assert "readiness_smoke_proof_status" in body["runs"][0]
    assert "readiness_smoke_proof_detail" in body["runs"][0]
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
    item = next(entry for entry in queue["items"] if entry["reason"] == "goal_confirmation")

    response = client.post(
        "/api/operator-actions/dispatch",
        json={"item_id": item["id"], "decision": "approve", "confirmed": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_confirmation"
    assert body["event_kind"] == "operator_action_confirmation_required"
    assert item["approval_kind"] == "goal_update"
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
                '{"should_update": true, "proposed_goal": "Improve API goal confirmation flow for long runs", '
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
    assert body["state"]["proposed_goal"] == "Improve API goal confirmation flow for long runs"
    assert body["state"]["goal_evolution"]["pending_count"] == 1
    assert body["state"]["goal_evolution"]["latest_decision"]["source"] == "manual_review"
    evolution = client.get(f"/api/runs/{created.id}/goal/evolution").json()
    assert evolution["pending_count"] == 1
    assert evolution["latest_decision"]["proposed_goal"] == "Improve API goal confirmation flow for long runs"
    approvals = client.get(f"/api/runs/{created.id}/approvals").json()
    assert approvals[0]["action_kind"] == "goal_update"
    assert approvals[0]["payload"]["proposed_goal"] == "Improve API goal confirmation flow for long runs"


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

def test_readiness_proof_history_endpoint_flows_into_handoff_and_replay(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    client, _engine, store = install_test_runtime(monkeypatch, tmp_path)
    created = store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness proof API",
        str(tmp_path),
        [],
    )
    review_event = store.append_event(
        created.id,
        "operator_action_reviewed",
        "Operator accepted self-scaffold review.",
        {
            "self_scaffold_review": {
                "reviewed_change_count": 2,
                "reviewed_change_ids": ["guard-1", "edit_evidence:0:patch-apply-applied-patch-api-1-app-py"],
            }
        },
    )
    claim_event = store.append_event(
        created.id,
        "readiness_claim",
        "Readiness claim accepted after proof history review.",
        {"readiness_completion": {"can_claim_milestone": True}},
    )
    created = store.get_run(created.id)
    created.state.acceptance_evidence.append(
        AcceptanceCriterionEvidence(
            id="api-source-visible-readiness",
            criterion="Readiness proof carries web and browser refs.",
            status="verified",
            required_labels=["web", "browser"],
            matched_labels=["web", "browser"],
        )
    )
    created.state.web_sources.append(
        WebSource(
            id="web-api-proof-1",
            title="API readiness source proof",
            url="https://example.test/api-readiness",
            timestamp="2026-06-28T09:11:00+00:00",
            excerpt="Compact API web source proof for readiness evidence.",
            citation="[web-api-proof-1]",
        )
    )
    created.state.desktop_snapshots.append(
        DesktopSnapshot(
            id="browser-api-proof-1",
            title="Browser API readiness proof screenshot",
            timestamp="2026-06-28T09:12:00+00:00",
            path=str(tmp_path / "browser-api-proof.png"),
            summary="Browser screenshot proof for API readiness evidence.",
        )
    )
    created.state.readiness_rehearsal = ReadinessRehearsalReport(
        run_id=created.id,
        generated_at="2026-06-28T09:10:00+00:00",
        status="passed",
        summary="Readiness rehearsal passed with proof history.",
        restart_simulated=True,
        accepted_event_id=claim_event["id"],
        self_scaffold_reviewed=True,
        self_scaffold_review_event_id=review_event["id"],
        self_scaffold_reviewed_change_count=1,
        post_review_handoff_goal_preserved=True,
        post_review_handoff_next_action_preserved=True,
        post_review_resume_prompt_goal_preserved=True,
        post_review_resume_prompt_next_action_preserved=True,
        replay_attached=True,
        handoff_attached=True,
        steps=[
            ReadinessRehearsalStep(
                id="self_scaffold_review",
                status="passed",
                summary="Self-scaffold review was accepted after restart.",
                evidence=["reviewed=1"],
                event_id=review_event["id"],
                event_kind="operator_action_reviewed",
                run_status="paused",
                milestone="decide",
            ),
            ReadinessRehearsalStep(
                id="post_review_handoff_alignment",
                status="passed",
                summary="Post-review handoff preserved goal and next action.",
                evidence=["resume_prompt_next_action=True"],
                run_status="queued",
                milestone="decide",
            ),
            ReadinessRehearsalStep(
                id="accepted_claim",
                status="passed",
                summary="Readiness claim was accepted.",
                evidence=["claim_event=accepted"],
                event_id=claim_event["id"],
                event_kind="readiness_claim",
                run_status="completed",
                milestone="decide",
            ),
        ],
    )
    store.update_run(created.id, state=created.state)

    history = client.get(f"/api/runs/{created.id}/readiness-proof-history")
    source_ref_preview = client.get(f"/api/runs/{created.id}/readiness-source-refs")
    handoff = client.get(f"/api/runs/{created.id}/handoff")
    replay = client.get(f"/api/runs/{created.id}/replay")
    replay_md = client.get(f"/api/runs/{created.id}/replay.md")

    assert history.status_code == 200
    assert history.json()["status"] == "complete"
    assert history.json()["self_scaffold_review_count"] == 1
    assert history.json()["post_review_handoff_count"] == 1
    assert history.json()["source_evidence_ref_count"] == 2
    assert history.json()["source_evidence_labels"] == ["browser", "web"]
    claim_entries = [entry for entry in history.json()["entries"] if entry["proof_type"] == "readiness_claim"]
    assert claim_entries
    assert {ref["id"] for ref in claim_entries[0]["source_refs"]} == {"browser-api-proof-1", "web-api-proof-1"}
    assert source_ref_preview.status_code == 200
    source_ref_body = source_ref_preview.json()
    assert source_ref_body["status"] == "ready"
    assert source_ref_body["source_visible_labels"] == ["browser", "web"]
    assert source_ref_body["source_evidence_labels"] == ["browser", "web"]
    assert source_ref_body["proof_ref_labels"] == ["browser", "web"]
    assert source_ref_body["missing_proof_ref_labels"] == []
    assert source_ref_body["proof_ref_count"] == 2
    assert {item["label"] for item in source_ref_body["labels"]} == {"browser", "web"}
    assert handoff.status_code == 200
    assert handoff.json()["readiness_proof_history"]["status"] == "complete"
    assert handoff.json()["readiness_proof_history"]["source_evidence_ref_count"] == 2
    assert handoff.json()["readiness_source_ref_preview"]["status"] == "ready"
    assert handoff.json()["readiness_source_ref_preview"]["proof_ref_count"] == 2
    assert replay.status_code == 200
    assert replay.json()["readiness_proof_history"]["status"] == "complete"
    assert replay.json()["handoff"]["readiness_proof_history"]["post_review_handoff_count"] == 1
    assert replay.json()["handoff"]["readiness_proof_history"]["source_evidence_ref_count"] == 2
    assert replay.json()["readiness_source_ref_preview"]["status"] == "ready"
    assert replay.json()["handoff"]["readiness_source_ref_preview"]["proof_ref_count"] == 2
    assert replay_md.status_code == 200
    assert "## Readiness Proof History" in replay_md.text
    assert "## Readiness Source Refs" in replay_md.text
    assert "Source refs: `2`" in replay_md.text
    assert "web:web_source:web-api-proof-1" in replay_md.text
