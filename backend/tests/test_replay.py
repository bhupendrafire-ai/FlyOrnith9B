from pathlib import Path

from app.context_compiler import ContextCompiler
from app.memory import MemoryContext
from app.persistence import RunStore
from app.replay import build_replay_bundle
from app.schemas import (
    AcceptanceCriterionEvidence,
    AcceptanceEvidenceRecommendation,
    AcceptanceRecommendationTrace,
    DesktopSnapshot,
    ContextSnapshot,
    GoalEvolutionDecisionRecord,
    GoalEvolutionReport,
    GitCheckpointReport,
    ModelInteractionRecord,
    ModelProfileAdaptationProposal,
    OrnithLaunchChecklistReport,
    PatchApplication,
    PatchProposal,
    PolicySimulationReport,
    PostActionRetryDecisionRecord,
    PostActionRetryReport,
    ReadinessRehearsalReport,
    ReadinessRehearsalStep,
    RecoveryPlan,
    RunLease,
    TaskNode,
    ToolCallRecord,
    WebSource,
    WorkspaceDiffFile,
    WorkspaceDiffSummary,
    WorkspaceIsolation,
)


def test_replay_bundle_compacts_events_and_approval_previews(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay this run", "Replay", str(tmp_path), [])
    store.append_event(
        run.id,
        "shell",
        "Ran a noisy command",
        {"ok": True, "stdout": "x" * 8000, "stderr": ""},
    )
    store.create_approval(
        run.id,
        "workspace_promote",
        {
            "preview": {
                "summary": "1 workspace change(s): 0 added, 1 modified, 0 deleted.",
                "files": [{"status": "modified", "path": "main.py", "diff_excerpt": "secret-free diff"}],
            }
        },
        "Promote isolated workspace changes.",
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.event_count == 1
    assert bundle.events[0].data_keys == ["ok", "stderr", "stdout"]
    assert "x" * 200 not in bundle.markdown
    assert bundle.approvals[0].preview_summary == "1 workspace change(s): 0 added, 1 modified, 0 deleted."
    assert bundle.approvals[0].preview_files == ["modified: main.py"]
    assert bundle.approvals[0].reviewed is False
    assert bundle.approvals[0].review_count == 0
    assert "# Replay: Replay" in bundle.markdown
    assert "`unreviewed`" in bundle.markdown
    assert "Resume run" in bundle.markdown


def test_replay_bundle_compacts_reviewed_approval_state(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay reviewed approval", "Reviewed approval", str(tmp_path), [])
    approval = store.create_approval(
        run.id,
        "shell",
        {"command": "python -m pytest"},
        "Approve shell command.",
    )
    review_event = store.append_event(
        run.id,
        "operator_action_reviewed",
        "Operator reviewed approval.",
        {
            "decision": "open",
            "confirmed": False,
            "operator_action": {
                "id": f"{run.id}:approval:shell",
                "run_id": run.id,
                "title": run.title,
                "reason": "approval",
                "action": "Review pending shell approval.",
                "ui_target": "approval",
                "approval_id": approval["id"],
            },
        },
    )
    second_review_event = store.append_event(
        run.id,
        "operator_action_reviewed",
        "Operator reviewed approval again.",
        {
            "decision": "open",
            "confirmed": False,
            "operator_action": {
                "id": f"{run.id}:approval:shell:second",
                "run_id": run.id,
                "title": run.title,
                "reason": "approval",
                "action": "Review pending shell approval again.",
                "ui_target": "approval",
                "approval_id": approval["id"],
            },
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.approvals[0].reviewed is True
    assert bundle.approvals[0].review_count == 2
    assert bundle.approvals[0].latest_review_event_id == second_review_event["id"]
    assert bundle.approvals[0].latest_reviewed_at == second_review_event["timestamp"]
    assert bundle.handoff.approval_reviews[0].id == approval["id"]
    assert bundle.handoff.approval_reviews[0].reviewed is True
    assert bundle.handoff.approval_reviews[0].review_count == 2
    assert bundle.handoff.approval_reviews[0].latest_review_event_id == second_review_event["id"]
    assert bundle.handoff.approval_reviews[0].high_risk is True
    assert f"reviewed x2 event #{second_review_event['id']}" in bundle.markdown


def test_replay_bundle_compacts_legacy_patch_apply_approval_preview(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay patch approval", "Replay patch", str(tmp_path), [])
    store.create_approval(
        run.id,
        "patch_apply",
        {
            "tool_name": "patch_apply",
            "args": {"patch_id": "patch-demo", "diff": "--- a/demo.py\n+++ b/demo.py\n"},
            "files": ["demo.py"],
            "summary": "Apply demo patch.",
        },
        "Apply patch proposal patch-demo.",
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.approvals[0].preview_summary == "Apply demo patch."
    assert bundle.approvals[0].preview_files == ["patch: demo.py"]
    assert "Preview: Apply demo patch." in bundle.markdown
    assert "patch: demo.py" in bundle.markdown

def test_replay_bundle_includes_operator_dispatch_ledger(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay operator dispatch", "Replay dispatch", str(tmp_path), [])
    store.append_event(
        run.id,
        "operator_action_dispatched",
        "Operator dispatched recovery resume.",
        {
            "decision": "dispatch",
            "confirmed": True,
            "note_supplied": False,
            "operator_action": {
                "id": f"{run.id}:recovery:recovery",
                "run_id": run.id,
                "title": run.title,
                "reason": "recovery",
                "action": "Resume active recovery.",
                "ui_target": "recovery",
                "approval_id": 0,
            },
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.operator_dispatches.dispatched_count == 1
    assert bundle.handoff.operator_dispatches.latest_action.startswith("dispatched")
    assert "## Operator Dispatches" in bundle.markdown
    assert "Operator dispatched recovery resume" in bundle.markdown


def test_replay_bundle_groups_operator_approval_history(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay approval history", "Replay approval history", str(tmp_path), [])
    approval = store.create_approval(run.id, "shell", {"command": "python -m pytest"}, "Approve shell.")
    action = {
        "id": f"{run.id}:approval:shell",
        "run_id": run.id,
        "title": run.title,
        "reason": "approval",
        "action": "Review pending shell approval.",
        "ui_target": "approval",
        "approval_id": approval["id"],
    }
    first = store.append_event(run.id, "operator_action_reviewed", "Operator reviewed approval.", {"decision": "open", "operator_action": action})
    second = store.append_event(run.id, "operator_action_confirmation_required", "Operator action requires confirmation.", {"decision": "reject", "operator_action": action})
    third = store.append_event(run.id, "operator_action_dispatched", "Operator rejected approval.", {"decision": "reject", "confirmed": True, "operator_action": action})

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )
    history = bundle.operator_dispatches.approval_histories[0]

    assert history.approval_id == approval["id"]
    assert history.event_count == 3
    assert history.reviewed_count == 1
    assert history.confirmation_required_count == 1
    assert history.dispatched_count == 1
    assert history.latest_event_id == third["id"]
    assert history.sequence == [
        f"reviewed#{first['id']}:open",
        f"confirmation_required#{second['id']}:reject",
        f"dispatched#{third['id']}:reject",
    ]
    assert f"Approval #{approval['id']}: events `3`" in bundle.markdown
    assert "reviewed#" in bundle.markdown


def test_replay_bundle_highlights_unresolved_operator_approval_history(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay unresolved approval history", "Replay unresolved approval history", str(tmp_path), [])
    approval = store.create_approval(run.id, "shell", {"command": "python -m pytest"}, "Approve shell.")
    action = {
        "id": f"{run.id}:approval:shell",
        "run_id": run.id,
        "title": run.title,
        "reason": "approval",
        "action": "Review pending shell approval.",
        "ui_target": "approval",
        "approval_id": approval["id"],
    }
    event = store.append_event(run.id, "operator_action_reviewed", "Operator reviewed approval.", {"decision": "open", "operator_action": action})

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )
    history = bundle.operator_dispatches.unresolved_approval_histories[0]

    assert bundle.operator_dispatches.unresolved_approval_history_count == 1
    assert history.approval_id == approval["id"]
    assert history.latest_status == "reviewed"
    assert history.latest_event_id == event["id"]
    assert history.sequence == [f"reviewed#{event['id']}:open"]
    assert f"Unresolved approval #{approval['id']}: events `1`" in bundle.markdown


def test_replay_bundle_highlights_promotion_approval_operator_route(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay promotion route", "Replay promotion route", str(tmp_path), [])
    approval = store.create_approval(
        run.id,
        "workspace_promote",
        {"tool_name": "workspace_promote", "args": {"source_path": str(tmp_path)}},
        "Promote isolated workspace changes.",
    )
    action = {
        "id": f"{run.id}:promotion_audit_promotion_approval_history_unresolved:{approval['id']}",
        "run_id": run.id,
        "title": run.title,
        "reason": "promotion_audit_promotion_approval_history_unresolved",
        "action": "Resolve reviewed workspace_promote approval before source promotion.",
        "endpoint": f"/api/runs/{run.id}/approvals",
        "method": "GET",
        "ui_target": "approval",
        "approval_id": approval["id"],
        "approval_kind": "workspace_promote",
        "details": ["audit_status=ready", "issue=promotion_approval_history_unresolved", f"approval_id={approval['id']}"],
    }
    event = store.append_event(
        run.id,
        "operator_action_reviewed",
        "Operator opened queued action promotion_audit_promotion_approval_history_unresolved.",
        {"decision": "open", "operator_action": action},
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )
    route = bundle.operator_dispatches.promotion_routes[0]

    assert bundle.operator_dispatches.promotion_route_count == 1
    assert bundle.operator_dispatches.promotion_approval_route_count == 1
    assert bundle.operator_dispatches.promotion_approval_history_count == 1
    assert bundle.operator_dispatches.unresolved_promotion_approval_history_count == 1
    assert bundle.operator_dispatches.unresolved_promotion_approval_histories[0].approval_id == approval["id"]
    assert route.event_id == event["id"]
    assert route.action_reason == "promotion_audit_promotion_approval_history_unresolved"
    assert route.approval_id == approval["id"]
    assert route.approval_kind == "workspace_promote"
    assert route.endpoint == f"/api/runs/{run.id}/approvals"
    assert f"approval_id={approval['id']}" in route.details
    assert bundle.handoff.operator_dispatches.promotion_approval_route_count == 1
    checks = {check.section: check for check in bundle.report_integrity.checks}
    assert checks["handoff.operator_dispatches.promotion_route_count"].status == "ok"
    assert checks["handoff.operator_dispatches.unresolved_promotion_approval_ids"].status == "ok"
    assert checks["handoff.operator_dispatches.unresolved_promotion_approval_ids"].expected == str(approval["id"])
    assert checks["handoff.operator_dispatches.pending_promotion_route_ids"].status == "ok"
    assert checks["handoff.operator_dispatches.pending_promotion_route_ids"].actual == str(approval["id"])
    assert "Promotion routes: `1` approval routes `1`" in bundle.markdown
    assert f"Promotion route #{event['id']}: `reviewed` `open` `promotion_audit_promotion_approval_history_unresolved` -> `approval` approval#{approval['id']} `workspace_promote`" in bundle.markdown

def test_replay_bundle_marks_promotion_approval_route_resolved_after_dispatch(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay resolved promotion route", "Replay resolved promotion route", str(tmp_path), [])
    approval = store.create_approval(
        run.id,
        "workspace_promote",
        {"tool_name": "workspace_promote", "args": {"source_path": str(tmp_path)}},
        "Promote isolated workspace changes.",
    )
    action = {
        "id": f"{run.id}:promotion_audit_promotion_approval_history_unresolved:{approval['id']}",
        "run_id": run.id,
        "title": run.title,
        "reason": "promotion_audit_promotion_approval_history_unresolved",
        "action": "Resolve reviewed workspace_promote approval before source promotion.",
        "endpoint": f"/api/runs/{run.id}/approvals",
        "method": "GET",
        "ui_target": "approval",
        "approval_id": approval["id"],
        "approval_kind": "workspace_promote",
        "details": ["audit_status=ready", "issue=promotion_approval_history_unresolved", f"approval_id={approval['id']}"],
    }
    first = store.append_event(run.id, "operator_action_reviewed", "Operator opened promotion approval route.", {"decision": "open", "operator_action": action})
    second = store.append_event(run.id, "operator_action_confirmation_required", "Operator action requires confirmation.", {"decision": "approve", "operator_action": action})
    third = store.append_event(run.id, "operator_action_dispatched", "Operator approved promotion approval route.", {"decision": "approve", "confirmed": True, "operator_action": action})

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )
    history = bundle.operator_dispatches.promotion_approval_histories[0]

    assert bundle.operator_dispatches.promotion_route_count == 3
    assert bundle.operator_dispatches.promotion_approval_route_count == 3
    assert bundle.operator_dispatches.promotion_approval_history_count == 1
    assert bundle.operator_dispatches.unresolved_promotion_approval_history_count == 0
    assert bundle.operator_dispatches.unresolved_promotion_approval_histories == []
    assert history.approval_id == approval["id"]
    assert history.latest_status == "dispatched"
    assert history.latest_event_id == third["id"]
    assert history.dispatched_count == 1
    assert history.sequence == [
        f"reviewed#{first['id']}:open",
        f"confirmation_required#{second['id']}:approve",
        f"dispatched#{third['id']}:approve",
    ]
    assert f"Promotion approval #{approval['id']} `workspace_promote`: latest `dispatched` #{third['id']} dispatched `1`" in bundle.markdown
    assert f"Unresolved promotion approval #{approval['id']}" not in bundle.markdown

def test_replay_promotion_audit_includes_unresolved_promotion_approval_history(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "app.py").write_text("print('old')\n", encoding="utf-8")
    (workspace / "app.py").write_text("print('new')\n", encoding="utf-8")
    run = store.create_run(
        "Replay promotion approval history",
        "Replay promotion approval history",
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
    run.state.workspace_diff = WorkspaceDiffSummary(
        generated_at="2026-06-28T00:00:00+00:00",
        source_path=str(source),
        workspace_path=str(workspace),
        files=[WorkspaceDiffFile(path="app.py", status="modified")],
        total_files=1,
        modified=1,
        summary="1 workspace change(s): 0 added, 1 modified, 0 deleted.",
    )
    run.state.tool_calls.append(
        ToolCallRecord(
            id="tool-replay-promotion-test",
            name="shell",
            args={"command": "python -m py_compile app.py"},
            ok=True,
            summary="py_compile passed before source promotion.",
            created_at="2026-06-28T00:05:00+00:00",
        )
    )
    store.update_run(run.id, status="waiting_approval", state=run.state)
    approval = store.create_approval(
        run.id,
        "workspace_promote",
        {"tool_name": "workspace_promote", "args": {"source_path": str(source)}},
        "Promote isolated workspace changes.",
    )
    review_event = store.append_event(
        run.id,
        "operator_action_reviewed",
        "Operator reviewed workspace promotion approval.",
        {
            "decision": "open",
            "operator_action": {
                "id": f"{run.id}:approval:workspace_promote",
                "run_id": run.id,
                "title": run.title,
                "reason": "approval",
                "action": "Review pending workspace promotion approval.",
                "ui_target": "approval",
                "approval_id": approval["id"],
            },
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    expected = f"approval#{approval['id']}:latest=reviewed:events=1:seq=reviewed#{review_event['id']}:open"
    assert bundle.promotion_audit.unresolved_approval_history_count == 1
    assert bundle.promotion_audit.unresolved_approval_histories == [expected]
    assert any(issue.id == "promotion_approval_history_unresolved" for issue in bundle.promotion_audit.issues)
    assert bundle.handoff.promotion_audit.unresolved_approval_histories == [expected]
    assert "Approval histories: unresolved `1`" in bundle.markdown
    assert f"Unresolved gate: {expected}" in bundle.markdown

def test_replay_bundle_includes_ornith_preflight_action_outcomes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay Ornith action", "Replay preflight action", str(tmp_path), [])
    operator_action = {
        "id": f"{run.id}:ornith_preflight_context_budget:context_checkpoint",
        "run_id": run.id,
        "title": run.title,
        "reason": "ornith_preflight_context_budget",
        "action": "Refresh compact context before resuming Ornith.",
        "ui_target": "context_checkpoint",
        "approval_id": 0,
        "details": ["Context pressure is high."],
    }
    store.append_event(
        run.id,
        "operator_action_dispatched",
        "Operator dispatched Ornith preflight context checkpoint.",
        {"operator_action": operator_action},
    )
    store.append_event(
        run.id,
        "ornith_preflight_action",
        "Completed Ornith preflight context checkpoint.",
        {
            "operator_action": operator_action,
            "context_budget": {"pressure": "high", "estimated_tokens": 26000, "target_tokens": 18000},
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.ornith_preflight_actions.completed_count == 1
    assert bundle.ornith_preflight_actions.dispatched_count == 0
    assert bundle.ornith_preflight_actions.context_checkpoint_count == 1
    assert bundle.ornith_preflight_actions.entries[0].item_id == "context_budget"
    assert bundle.ornith_preflight_actions.entries[0].context_pressure == "high"
    assert bundle.handoff.ornith_preflight_actions.completed_count == 1
    assert "## Ornith Preflight Actions" in bundle.markdown
    assert "context_budget" in bundle.markdown


def test_replay_bundle_includes_ornith_preflight(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay Ornith preflight", "Replay preflight", str(tmp_path), [])
    run.state.ornith_preflight = OrnithLaunchChecklistReport(
        run_id=run.id,
        generated_at="2026-06-27T12:20:00+00:00",
        mode="resume",
        status="attention",
        ready_to_resume=True,
        summary="Ornith preflight is compacted for replay.",
        readiness_smoke_status="passed",
        dispatch_restart_smoke_status="stale",
        run_health_level="watch",
        run_health_action="continue",
        next_actions=["Refresh operator-dispatch restart smoke."],
    )
    run.state.handoff_summary.ornith_preflight = run.state.ornith_preflight
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.ornith_preflight.run_id == run.id
    assert bundle.handoff.ornith_preflight.run_id == run.id
    assert "## Ornith Preflight" in bundle.markdown
    assert "Ornith preflight is compacted for replay." in bundle.markdown

def test_replay_bundle_includes_ornith_preflight_warning_history(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay Ornith warning history", "Replay preflight warnings", str(tmp_path), [])
    run.state.ornith_preflight = OrnithLaunchChecklistReport(
        run_id=run.id,
        generated_at="2026-06-28T12:20:00+00:00",
        mode="resume",
        status="attention",
        ready_to_resume=False,
        summary="Ornith preflight found thin restart evidence.",
        items=[
            {
                "id": "handoff_action_context",
                "category": "memory",
                "status": "warn",
                "summary": "Handoff action context is too thin for unattended Ornith resume: missing restart_ledger.",
                "evidence": ["generated=True", "restart_ledger=0"],
                "next_action": "Refresh/checkpoint the run handoff.",
            }
        ],
        next_actions=["Refresh/checkpoint the run handoff."],
    )
    run.state.handoff_summary.ornith_preflight = run.state.ornith_preflight
    store.update_run(run.id, state=run.state)
    event = store.append_event(
        run.id,
        "act_preflight_reorient",
        "Act preflight detected thin handoff action context.",
        {
            "handoff_action_context": {
                "status": "warn",
                "summary": "Handoff action context is too thin for unattended Ornith resume: missing restart_ledger.",
                "evidence": ["generated=True", "compact=True", "restart_ledger=0"],
                "next_action": "Refresh/checkpoint the handoff before selecting the next tool action.",
            }
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.ornith_preflight_warnings.total_count == 2
    assert bundle.ornith_preflight_warnings.action_context_reorient_count == 1
    assert bundle.ornith_preflight_warnings.latest_reorient_event_id == event["id"]
    assert bundle.handoff.ornith_preflight_warnings.total_count == 2
    warning_check = next(check for check in bundle.readiness_completion.checks if check.id == "ornith_preflight_warnings")
    assert warning_check.status == "block"
    assert bundle.readiness_completion.ornith_preflight_warning_count == 2
    assert bundle.readiness_completion.ornith_preflight_reorient_count == 1
    assert "## Ornith Preflight Warning History" in bundle.markdown
    assert "action-context reorients `1`" in bundle.markdown
    assert f"#{event['id']} `warn` `act_preflight_reorient` handoff_action_context" in bundle.markdown
    assert "restart_ledger=0" in bundle.markdown

def test_replay_bundle_includes_active_recovery_plan(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay recovery", "Replay recovery", str(tmp_path), [])
    run.state.recovery_plan = RecoveryPlan(
        id="recovery-test",
        status="active",
        trigger="repeated_failure",
        failure_kind="timeout",
        tool="shell",
        attempts=3,
        summary="Repeated shell timeout.",
        next_action="Reduce command scope.",
        steps=["Reduce command scope.", "Run narrower diagnostic."],
    )
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.recovery_plan.status == "active"
    assert "## Active Recovery" in bundle.markdown
    assert "Reduce command scope." in bundle.markdown


def test_replay_bundle_includes_recovery_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay recovery decision", "Replay recovery decision", str(tmp_path), [])
    run.state.recovery_plan = RecoveryPlan(
        id="recovery-readiness",
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
    store.update_run(run.id, status="paused", state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.recovery_decisions.active_recovery
    assert bundle.handoff.recovery_decisions.active_decision.tool == "run_tests"
    assert "## Recovery Decisions" in bundle.markdown
    assert "narrower diagnostic" in bundle.markdown

def test_replay_bundle_includes_post_action_retries(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay retry lane", "Replay retry", str(tmp_path), [])
    decision = PostActionRetryDecisionRecord(
        id="post-retry-1",
        status="pending",
        trigger_tool="run_tests",
        trigger_summary="Tests failed.",
        failure_kind="command_failure",
        attempt_count=1,
        selected_tool="shell",
        selected_action="Run a focused compile diagnostic before repeating broad tests.",
        command_hint="python -m compileall backend\\app",
        reason="Broad test proof failed.",
    )
    run.state.post_action_retries = PostActionRetryReport(
        run_id=run.id,
        generated_at="2026-06-28T12:10:00+00:00",
        decision_count=1,
        pending_count=1,
        latest_decision=decision,
        summary="Post-action retry pending.",
        recommended_action=decision.selected_action,
        decisions=[decision],
    )
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.post_action_retries.decision_count == 1
    assert bundle.handoff.post_action_retries.pending_count == 1
    assert "## Post-Action Retries" in bundle.markdown
    assert "run_tests" in bundle.markdown
    assert "shell" in bundle.markdown

def test_replay_bundle_includes_verification_outcomes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay verification outcomes", "Replay verification outcomes", str(tmp_path), ["Tests pass"])
    run.state.tool_calls.append(
        ToolCallRecord(
            id="tool-run-tests",
            name="run_tests",
            ok=True,
            summary="All tests passed.",
            created_at="2026-06-27T08:04:00+00:00",
        )
    )
    run.state.acceptance_evidence = [
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
    run.state.recovery_history = [
        RecoveryPlan(
            id="recovery-readiness",
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
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.verification_outcomes.recovery_resolved_count == 1
    assert bundle.handoff.verification_outcomes.latest_recovery_outcome.outcome == "recovery_resolved"
    assert "## Verification Outcomes" in bundle.markdown
    assert "recovery_resolved" in bundle.markdown


def test_replay_bundle_marks_completed_runs(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Ship finished work", "Completed run", str(tmp_path), [])
    store.update_run(run.id, status="completed", state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.status == "completed"
    assert "- Status: `completed`" in bundle.markdown


def test_replay_bundle_includes_blocked_handoff_context(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume blocked work", "Blocked run", str(tmp_path), [])
    run.state.blockers.append("Need user approval before retrying desktop click.")
    run.state.handoff_summary.unresolved_blockers = run.state.blockers[:]
    store.update_run(run.id, status="blocked", state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.status == "blocked"
    assert "## Blockers" in bundle.markdown
    assert "Need user approval before retrying desktop click." in bundle.markdown


def test_replay_bundle_includes_run_lease(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay lease", "Replay lease", str(tmp_path), [])
    run.state.run_lease = RunLease(
        id="lease-test",
        owner_id="engine-test",
        status="active",
        heartbeat_at="2026-06-27T08:00:00+00:00",
        expires_at="2026-06-27T08:01:30+00:00",
    )
    store.update_run(run.id, status="running", state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.run_lease.status == "active"
    assert "## Run Lease" in bundle.markdown
    assert "engine-test" in bundle.markdown


def test_replay_bundle_includes_model_interactions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay model metrics", "Replay model metrics", str(tmp_path), [])
    run.state.model_interactions.append(
        ModelInteractionRecord(
            id="model-test",
            kind="action",
            ok=False,
            attempts=2,
            repaired=True,
            fallback_used=True,
            summary="Model action fallback used: git_status.",
            error="No valid JSON object found.",
        )
    )
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.model_interactions[0].fallback_used
    assert "## Model Interactions" in bundle.markdown
    assert "Model action fallback used" in bundle.markdown


def test_replay_bundle_includes_model_adaptation_reviews(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay adaptation review", "Replay adaptation", str(tmp_path), [])
    proposal = ModelProfileAdaptationProposal(
        id="proposal-test",
        profile_id="ornith",
        generated_at="2026-06-27T08:00:00+00:00",
        status="needs_confirmation",
        summary="Proposed patch-first prompt bias.",
    )
    store.create_model_adaptation_review(proposal, "accepted", "Use in future tuning.")

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
        model_adaptation_reviews=store.list_model_adaptation_reviews(),
    )

    assert bundle.model_profile_adaptation_reviews[0].decision == "accepted"
    assert bundle.handoff.model_profile_adaptation_reviews[0].proposal_summary == "Proposed patch-first prompt bias."
    assert "## Ornith Profile Adaptation Reviews" in bundle.markdown
    assert "Use in future tuning." in bundle.markdown


def test_replay_bundle_includes_source_evidence_preview(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay source evidence", "Replay sources", str(tmp_path), ["Browser and web proof"])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Browser and web proof",
            status="open",
            required_labels=["web", "browser"],
            matched_labels=["web", "browser"],
        )
    ]
    run.state.web_sources = [
        WebSource(
            id="web-1",
            title="Source preview docs",
            url="https://example.com/source-preview",
            timestamp="2026-06-28T12:00:00+00:00",
            excerpt="Source preview excerpt for replay.",
            citation="[Source preview docs](https://example.com/source-preview)",
        )
    ]
    run.state.tool_calls = [
        ToolCallRecord(
            id="tool-guard-1",
            name="file_read",
            args={
                "model_guard": "current_task_mismatch",
                "guarded_tool": "run_tests",
                "current_task_id": "task-edit",
                "current_task_kind": "edit",
                "guard_reason": "edit_task_selected_proof_tool_without_evidence",
            },
            ok=True,
            summary="Harness redirected premature proof to edit inspection.",
        )
    ]
    run.state.patch_proposals = [
        PatchProposal(
            id="patch-1",
            title="Patch app.py safely",
            files=["app.py"],
            diff="--- a/app.py\n+++ b/app.py\n@@\n-old\n+new\n",
            status="pending",
        )
    ]
    run.state.desktop_snapshots = [
        DesktopSnapshot(
            id="browser-1",
            timestamp="2026-06-28T12:01:00+00:00",
            title="Browser screenshot: http://127.0.0.1:5173",
            path=str(tmp_path / "browser.png"),
            summary="Captured browser screenshot.",
        )
    ]
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.source_evidence.total_count == 2
    assert bundle.source_evidence.browser_snapshot_count == 1
    assert bundle.source_evidence.missing_labels == []
    assert bundle.action_context.generated_at
    assert bundle.handoff.source_evidence.web_source_count == 1
    assert bundle.handoff.action_context.generated_at
    assert "Action context pack:" in bundle.action_context.compact_prompt
    assert "model_guards=current_task_mismatch" in bundle.action_context.compact_prompt
    assert "edit_evidence=patch:pending:patch-1:app.py" in bundle.action_context.compact_prompt
    assert "## Source Evidence" in bundle.markdown
    assert "## Action Context" in bundle.markdown
    assert "Source preview docs" in bundle.markdown
    assert "model_guards=current_task_mismatch" in bundle.markdown
    assert "edit_evidence=patch:pending:patch-1:app.py" in bundle.markdown


def test_replay_bundle_includes_desktop_effect_proof_preview(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay desktop proof", "Replay desktop", str(tmp_path), [])
    run.state.tool_calls = [
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
    run.state.desktop_snapshots = [
        DesktopSnapshot(
            id="desktop-proof",
            timestamp="2026-06-29T10:01:00+00:00",
            title="Desktop screenshot",
            path=str(tmp_path / "desktop-proof.png"),
            summary="Captured the visible post-click state.",
        )
    ]
    store.update_run(run.id, state=run.state)
    store.append_event(
        run.id,
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

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.desktop_effect_proof.status == "proof_available"
    assert bundle.desktop_effect_proof.proof_snapshot is not None
    assert bundle.desktop_effect_proof.proof_snapshot.id == "desktop-proof"
    assert bundle.handoff.desktop_effect_proof.proof_tool == "desktop_screenshot"
    checks = {check.section: check for check in bundle.report_integrity.checks}
    assert checks["handoff.desktop_effect_proof.status"].status == "ok"
    assert checks["handoff.desktop_effect_proof.proof_snapshot_id"].status == "ok"
    assert bundle.desktop_effect_proof_repairs.latest_outcome == "metadata_refreshed"
    assert bundle.desktop_effect_proof_repairs.metadata_refreshed_count == 1
    assert bundle.handoff.desktop_effect_proof_repairs.entries[0].proof_snapshot_id == "desktop-proof"
    assert "## Desktop Effect Proof" in bundle.markdown
    assert "## Desktop Effect Proof Repairs" in bundle.markdown
    assert "metadata_refreshed" in bundle.markdown
    assert "desktop-proof" in bundle.markdown

    compiled_run = store.get_run(run.id)
    compiled_run.state.desktop_effect_proof = bundle.desktop_effect_proof
    compiled_run.state.desktop_effect_proof_repairs = bundle.desktop_effect_proof_repairs
    compiled_run.state.handoff_summary = bundle.handoff
    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(
        compiled_run,
        compiled_run.state,
        MemoryContext(hits=[], warnings=[]),
        [],
    )
    assert "desktop_effect_proof" in snapshot.sections
    assert "Desktop effect proof: proof_available" in prompt
    assert "repairs=metadata_refreshed/1" in prompt
    assert "snapshot=desktop-proof" in prompt

def test_replay_bundle_includes_acceptance_evidence(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay criteria", "Replay criteria", str(tmp_path), ["Tests pass"])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Tests pass",
            status="verified",
            evidence=["run_tests: All tests passed."],
            last_tool="run_tests",
        )
    ]
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.acceptance_evidence[0].status == "verified"
    assert "## Acceptance Evidence" in bundle.markdown
    assert "run_tests: All tests passed." in bundle.markdown


def test_replay_bundle_includes_acceptance_recommendations(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay recommendations", "Replay recommendations", str(tmp_path), ["Dashboard starts"])
    run.state.acceptance_recommendations = [
        AcceptanceEvidenceRecommendation(
            id="criterion-1-browser",
            criterion_id="criterion-1",
            criterion="Dashboard starts",
            label="browser",
            tool_kind="browser_screenshot",
            action="Capture a browser screenshot.",
            command_hint="url=http://127.0.0.1:5173",
        )
    ]
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.acceptance_recommendations[0].tool_kind == "browser_screenshot"
    assert bundle.handoff.acceptance_recommendations[0].label == "browser"
    assert "## Acceptance Recommendations" in bundle.markdown
    assert "browser_screenshot" in bundle.markdown


def test_replay_bundle_includes_acceptance_recommendation_traces(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay recommendation trace", "Replay trace", str(tmp_path), ["Tests pass"])
    run.state.acceptance_recommendation_traces = [
        AcceptanceRecommendationTrace(
            id="rec-trace-1",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            source="harness",
            status="satisfied",
            result_ok=True,
            result_summary="All tests passed.",
            evidence_status="verified",
        )
    ]
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.acceptance_recommendation_traces[0].status == "satisfied"
    assert bundle.handoff.acceptance_recommendation_traces[0].label == "verification"
    assert "## Acceptance Recommendation Traces" in bundle.markdown
    assert "All tests passed." in bundle.markdown


def test_replay_bundle_includes_completion_audit(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay completion audit", "Replay audit", str(tmp_path), ["Tests pass"])

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert not bundle.completion_audit.can_finish
    assert bundle.completion_audit.acceptance_open == 1
    assert "## Completion Audit" in bundle.markdown
    assert "Not all acceptance criteria" in bundle.markdown


def test_replay_bundle_includes_run_health(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay run health", "Replay health", str(tmp_path), ["Tests pass"])

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.run_health.recommended_action == "verify"
    assert bundle.handoff.run_health.level == bundle.run_health.level
    assert "## Run Health" in bundle.markdown
    assert "Recommended action" in bundle.markdown


def test_replay_bundle_includes_policy_simulation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay policy simulation", "Replay policy", str(tmp_path), ["Tests pass"])

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.policy_simulation.policy_action == "verify"
    assert bundle.handoff.policy_simulation.predicted_milestone == "act"
    assert bundle.policy_simulation.recommended_tool == "run_tests"
    assert "## Policy Simulation" in bundle.markdown
    assert "run_tests" in bundle.markdown


def test_replay_bundle_includes_run_progress(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay run progress", "Replay progress", str(tmp_path), ["Tests pass"])

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.run_progress.status == "needs_verification"
    assert bundle.run_progress.acceptance_total == 1
    assert bundle.handoff.run_progress.current_policy_action == "verify"
    assert "## Run Progress" in bundle.markdown
    assert "Needs verification" in bundle.markdown


def test_replay_bundle_includes_report_integrity(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay report integrity", "Replay integrity", str(tmp_path), ["Tests pass"])
    _prompt, snapshot = ContextCompiler(4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])
    run.state.context_snapshot = snapshot
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.report_integrity.status == "ok"
    assert bundle.handoff.report_integrity.ok_count == bundle.report_integrity.ok_count
    assert "## Report Integrity" in bundle.markdown
    assert "Handoff and replay report index is complete" in bundle.markdown


def test_replay_bundle_includes_report_integrity_refresh_reasons(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay refresh reasons", "Replay refresh reasons", str(tmp_path), [])
    reason = "stale:handoff.approval_reviews.review_count | expected=1:2 | actual=1:1"
    refresh_event = store.append_event(
        run.id,
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
        run.id,
        "resume_preflight_blocked",
        "Resume preflight blocked after refresh.",
        {
            "accepted": False,
            "reason": "Pending approval still blocks resume.",
            "report_integrity_refreshed": True,
            "report_integrity_refresh_reasons": [reason],
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )
    refresh = bundle.report_integrity_refreshes[0]

    assert refresh.event_id == refresh_event["id"]
    assert refresh.previous_report_status == "needs_refresh"
    assert refresh.report_status == "ok"
    assert refresh.reason_count == 1
    assert refresh.reasons == [reason]
    assert refresh.preflight_event_id == preflight_event["id"]
    assert refresh.preflight_event_kind == "resume_preflight_blocked"
    assert refresh.preflight_accepted is False
    assert bundle.handoff.report_integrity_refreshes[0].event_id == refresh_event["id"]
    assert "Refreshes: `1`" in bundle.markdown
    assert f"Latest refresh preflight: `#{preflight_event['id']}`" in bundle.markdown
    assert f"Refresh reason: {reason}" in bundle.markdown

def test_replay_report_integrity_checks_approval_review_handoff(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay approval integrity", "Replay approval integrity", str(tmp_path), ["Tests pass"])
    _prompt, snapshot = ContextCompiler(4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])
    run.state.context_snapshot = snapshot
    approval = store.create_approval(
        run.id,
        "shell",
        {"tool_name": "shell", "args": {"command": "python -m pytest"}},
        "Approve shell verification.",
    )
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )
    checks = {check.section: check for check in bundle.report_integrity.checks}

    assert bundle.report_integrity.status == "ok"
    assert bundle.handoff.approvals == ["shell:pending:unreviewed"]
    assert bundle.handoff.approval_reviews[0].id == approval["id"]
    assert checks["handoff.approval_reviews"].status == "ok"
    assert checks["handoff.approvals.pending_count"].status == "ok"
    assert checks["handoff.approval_labels.unreviewed_count"].status == "ok"


def test_replay_bundle_includes_objective_readiness(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay objective readiness", "Replay objective readiness", str(tmp_path), ["Tests pass"])

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.objective_readiness.items
    assert bundle.objective_readiness.next_actions
    assert bundle.objective_readiness.items[0].proof.tool_kind
    assert bundle.handoff.objective_readiness.run_id == run.id
    assert "## Objective Readiness" in bundle.markdown
    assert "Verified/partial/missing/failed" in bundle.markdown
    assert "- Next:" in bundle.markdown
    assert "Proof:" in bundle.markdown
    assert "patch_first_editing" in bundle.markdown


def test_replay_bundle_includes_readiness_completion(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Replay readiness completion",
        str(tmp_path),
        [],
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.readiness_completion.run_id == run.id
    assert bundle.handoff.readiness_completion.run_id == run.id
    assert bundle.readiness_completion.can_claim_milestone is False
    assert "## Readiness Completion" in bundle.markdown
    assert "claim `False`" in bundle.markdown


def test_replay_bundle_includes_resume_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay resume decisions", "Replay resume", str(tmp_path), ["Tests pass"])
    simulation = PolicySimulationReport(
        run_id=run.id,
        current_status="paused",
        current_milestone="decide",
        predicted_status="running",
        predicted_milestone="act",
        policy_action="verify",
        safe_to_resume=True,
        auto_resume_eligible=True,
        recommended_tool="run_tests",
        recommended_label="verification",
        summary="Would verify -> running/act.",
    )
    store.append_event(
        run.id,
        "resume_preflight",
        "Resume preflight accepted for manual.",
        {
            "source": "manual",
            "accepted": True,
            "reason": "Policy simulation accepted resume.",
            "policy_simulation": simulation.model_dump(),
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.resume_decisions.accepted_count == 1
    assert bundle.handoff.resume_decisions.latest_accepted.source == "manual"
    assert "## Resume Decisions" in bundle.markdown
    assert "Policy simulation accepted resume." in bundle.markdown


def test_replay_bundle_includes_autonomy_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay autonomy decisions", "Replay autonomy", str(tmp_path), ["Tests pass"])
    store.append_event(run.id, "decide", "Continuing to next action.")
    store.append_event(run.id, "blocked", "Reached wall-clock loop budget.")

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.autonomy_decisions.continue_count == 1
    assert bundle.autonomy_decisions.blocked_count == 1
    assert bundle.handoff.autonomy_decisions.latest_decision.source == "loop_budget"
    assert "## Autonomy Decisions" in bundle.markdown
    assert "Reached wall-clock loop budget." in bundle.markdown


def test_replay_bundle_includes_action_readiness(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay readiness", "Replay readiness", str(tmp_path), ["Tests pass"])
    run.state.milestone = "act"
    store.update_run(run.id, status="queued", state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.action_readiness.status == "needs_proof"
    assert bundle.handoff.action_readiness.suggested_tool == "run_tests"
    assert "## Action Readiness" in bundle.markdown
    assert "run_tests" in bundle.markdown


def test_replay_bundle_includes_action_readiness_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay readiness decisions", "Replay readiness decisions", str(tmp_path), ["Tests pass"])
    run.state.acceptance_recommendation_traces = [
        AcceptanceRecommendationTrace(
            id="rec-trace-1",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            source="harness",
            status="satisfied",
            result_ok=True,
            result_summary="All tests passed.",
            evidence_status="verified",
        )
    ]
    store.update_run(run.id, state=run.state)
    store.append_event(
        run.id,
        "action_readiness_tool",
        "needs_proof: Run tests.",
        {
            "action_readiness": {
                "run_id": run.id,
                "status": "needs_proof",
                "ready_to_act": True,
                "suggested_tool": "run_tests",
                "suggested_label": "verification",
                "recommended_action": "Run the smallest relevant verification command.",
            },
            "selected_action": {
                "tool": "run_tests",
                "recommendation_trace_id": "rec-trace-1",
                "recommendation_id": "criterion-1-verification",
                "recommendation_label": "verification",
                "recommendation_criterion_id": "criterion-1",
            },
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.action_readiness_decisions.satisfied_count == 1
    assert bundle.handoff.action_readiness_decisions.latest_tool_decision.status == "satisfied"
    assert "## Action Readiness Decisions" in bundle.markdown
    assert "intended proof was satisfied" in bundle.markdown

def test_replay_bundle_includes_self_scaffold_change_intent(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Let Ornith reshape its harness", "Self Scaffold Replay", str(tmp_path), [])
    run.state.tool_profile = "ornith_self_scaffold"
    run.state.task_graph = [
        TaskNode(id="task-self", title="Revise task graph safely", kind="decision", status="in_progress")
    ]
    run.state.current_task_id = "task-self"
    run.state.files_touched.append("app.py")
    run.state.patch_proposals.append(
        PatchProposal(
            id="patch-1",
            title="Patch app.py safely",
            files=["app.py"],
            status="pending",
        )
    )
    run.state.patch_applications.append(
        PatchApplication(
            id="apply-1",
            patch_id="patch-1",
            status="applied",
            files=["app.py"],
            backup_id="backup-1",
            manifest_path=str(tmp_path / "manifest.json"),
            summary="Applied patch-1 to app.py.",
            applied_at="2026-06-29T00:00:00+00:00",
        )
    )
    run.state.tool_calls.append(
        ToolCallRecord(
            id="tool-guard",
            name="file_read",
            args={
                "model_guard": "current_task_mismatch",
                "guarded_tool": "run_tests",
                "current_task_id": "task-self",
                "current_task_kind": "decision",
                "guard_reason": "Ornith selected a proof tool before explaining the scaffold change.",
            },
            ok=False,
            summary="Guarded stale tool selection.",
        )
    )
    store.update_run(run.id, state=run.state)
    store.append_event(run.id, "context_checkpoint", "Refreshed self-scaffold context pack.", {"reason": "self_scaffold"})
    store.append_event(
        run.id,
        "operator_action_reviewed",
        "Operator accepted self-scaffold change intent for current guard/reorient changes.",
        {
            "operator_action": {"ui_target": "self_scaffold", "reason": "self_scaffold", "action": "Review guard posture."},
            "self_scaffold_review": {
                "status": "needs_review",
                "change_count": 4,
                "guard_count": 1,
                "reviewed_change_count": 2,
                "reviewed_change_ids": [
                    "model_guard:0:current-task-mismatch-guarded-run-tests-for-task-self",
                    "edit_evidence:2:patch-apply-applied-patch-1-app-py",
                ],
                "remaining_goal_review": False,
            },
        },
    )

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.self_scaffold.status == "needs_review"
    assert bundle.self_scaffold.task_graph_count == 1
    assert bundle.self_scaffold.action_context_count == 1
    assert bundle.self_scaffold.guard_count >= 1
    assert bundle.handoff.self_scaffold.change_count == bundle.self_scaffold.change_count
    assert any(change.kind == "tool_posture" for change in bundle.self_scaffold.changes)
    assert any("without replaying raw logs" in change.intent for change in bundle.self_scaffold.changes)
    assert bundle.self_scaffold_reviews.status == "reviewed"
    assert bundle.self_scaffold_reviews.accepted_count == 1
    assert bundle.self_scaffold_reviews.reviewed_change_count == 2
    assert bundle.self_scaffold_rollback_intents.status == "needs_approval"
    assert bundle.self_scaffold_rollback_intents.patch_rollback_count == 1
    assert bundle.self_scaffold_rollback_intents.steering_count >= 1
    rollback_intent = next(entry for entry in bundle.self_scaffold_rollback_intents.entries if entry.action_kind == "patch_rollback")
    assert rollback_intent.proposed_tool == "patch_rollback"
    assert rollback_intent.requires_approval is True
    assert rollback_intent.mutation_automatic is False
    assert rollback_intent.patch_id == "patch-1"
    assert rollback_intent.backup_id == "backup-1"
    assert bundle.handoff.self_scaffold_rollback_intents.patch_rollback_count == 1
    assert bundle.handoff.self_scaffold_reviews.latest_event_id == bundle.self_scaffold_reviews.latest_event_id
    assert "## Self Scaffold" in bundle.markdown
    assert "Review outcomes:" in bundle.markdown
    assert "Rollback intents:" in bundle.markdown
    assert "patch_rollback" in bundle.markdown
    assert "Review `#" in bundle.markdown
    assert "Reverse:" in bundle.markdown

    prompt, snapshot = ContextCompiler(6000).compile(
        store.get_run(run.id),
        store.get_run(run.id).state.model_copy(update={"self_scaffold": bundle.self_scaffold, "handoff_summary": bundle.handoff}),
        MemoryContext(hits=[], warnings=[]),
        [],
    )
    assert "## self_scaffold" in prompt
    assert "review_outcomes" in prompt
    assert "rollback_intents" in prompt
    assert "patch rollback candidate" in prompt
    assert "self-scaffold review outcome" in prompt
    assert "self_scaffold" in snapshot.sections

def test_replay_bundle_includes_goal_evolution(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Keep the original goal", "Goal Replay", str(tmp_path), [])
    decision = GoalEvolutionDecisionRecord(
        id="goal-review-1",
        status="pending",
        source="scheduled_review",
        previous_goal="Keep the original goal",
        proposed_goal="Sharper replay goal",
        reason="The run found a clearer next objective.",
        material_change="next=verify replay",
        step_count=3,
        milestone="decide",
        approval_id=42,
        created_at="2026-06-27T08:00:00+00:00",
    )
    run.state.proposed_goal = "Sharper replay goal"
    run.state.goal_evolution = GoalEvolutionReport(decisions=[decision])
    store.update_run(run.id, status="waiting_goal_confirmation", state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.goal_evolution.pending_count == 1
    assert bundle.handoff.goal_evolution.latest_decision.proposed_goal == "Sharper replay goal"
    assert "## Goal Evolution" in bundle.markdown
    assert "Sharper replay goal" in bundle.markdown

def test_replay_bundle_includes_git_checkpoint(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay git posture", "Git Replay", str(tmp_path), [])
    run.state.git_checkpoint = GitCheckpointReport(
        run_id=run.id,
        generated_at="2026-06-27T08:01:00+00:00",
        status="commit_recommended",
        branch="main",
        head_sha="abc1234",
        remote_names=["origin"],
        remote_count=1,
        github_remote_count=1,
        changed_count=2,
        summary="Git checkpoint commit_recommended: changed=2.",
        recommended_action="Commit a scoped local checkpoint.",
    )
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.git_checkpoint.status in {"commit_recommended", "verify_first", "needs_remote", "clean", "not_repo"}
    assert bundle.handoff.git_checkpoint.generated_at
    assert "## Git Checkpoint" in bundle.markdown
    assert "Recommended action" in bundle.markdown

def test_replay_bundle_includes_context_coverage(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Replay context coverage", "Context Replay", str(tmp_path), [])
    run.state.context_snapshot = ContextSnapshot(
        run_id=run.id,
        generated_at="2026-06-27T08:01:00+00:00",
        estimated_tokens=1200,
        sections=["goal", "handoff"],
        selected_section_count=2,
        dropped_sections=["memory"],
        dropped_section_count=1,
        required_sections_missing=["memory"],
        coverage_status="critical",
        recommended_action="Checkpoint and re-orient from handoff before asking Ornith for another broad action.",
        prompt_preview="## goal\nReplay context coverage",
    )
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.context_snapshot.coverage_status == "critical"
    assert bundle.handoff.context_snapshot.required_sections_missing == ["memory"]
    assert "## Context Coverage" in bundle.markdown
    assert "Required missing: memory" in bundle.markdown

def test_replay_bundle_includes_readiness_proof_history(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness proof history",
        str(tmp_path),
        [],
    )
    review_event = store.append_event(
        run.id,
        "operator_action_reviewed",
        "Operator accepted self-scaffold review.",
        {
            "self_scaffold_review": {
                "reviewed_change_count": 2,
                "reviewed_change_ids": ["guard-1", "guard-2"],
            }
        },
    )
    claim_event = store.append_event(
        run.id,
        "readiness_claim",
        "Readiness claim accepted after proof history review.",
        {"readiness_completion": {"can_claim_milestone": True}},
    )
    run = store.get_run(run.id)
    run.state.acceptance_evidence.append(
        AcceptanceCriterionEvidence(
            id="replay-source-visible-readiness",
            criterion="Readiness proof carries web and browser refs.",
            status="verified",
            required_labels=["web", "browser"],
            matched_labels=["web", "browser"],
        )
    )
    run.state.web_sources.append(
        WebSource(
            id="web-proof-1",
            title="Readiness source proof",
            url="https://example.test/readiness",
            timestamp="2026-06-28T09:01:00+00:00",
            excerpt="Compact web source proof for readiness evidence.",
            citation="[web-proof-1]",
        )
    )
    run.state.desktop_snapshots.append(
        DesktopSnapshot(
            id="browser-proof-1",
            title="Browser readiness proof screenshot",
            timestamp="2026-06-28T09:02:00+00:00",
            path=str(tmp_path / "browser-proof.png"),
            summary="Browser screenshot proof for readiness evidence.",
        )
    )
    run.state.readiness_rehearsal = ReadinessRehearsalReport(
        run_id=run.id,
        generated_at="2026-06-28T09:00:00+00:00",
        status="passed",
        summary="Readiness rehearsal passed with proof history.",
        restart_simulated=True,
        accepted_event_id=claim_event["id"],
        self_scaffold_reviewed=True,
        self_scaffold_review_event_id=review_event["id"],
        self_scaffold_reviewed_change_count=2,
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
                evidence=["reviewed=2"],
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
    store.update_run(run.id, state=run.state)

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.readiness_proof_history.status == "complete"
    assert bundle.readiness_proof_history.self_scaffold_review_count == 1
    assert bundle.readiness_proof_history.post_review_handoff_count == 1
    assert bundle.readiness_proof_history.resume_prompt_preservation_count == 1
    assert bundle.readiness_proof_history.readiness_claim_count == 1
    assert bundle.readiness_proof_history.source_evidence_ref_count == 2
    assert bundle.readiness_proof_history.source_evidence_labels == ["browser", "web"]
    claim_entries = [entry for entry in bundle.readiness_proof_history.entries if entry.proof_type == "readiness_claim"]
    assert claim_entries
    assert {ref.id for ref in claim_entries[0].source_refs} == {"browser-proof-1", "web-proof-1"}
    assert bundle.handoff.readiness_proof_history.status == "complete"
    assert bundle.handoff.readiness_proof_history.source_evidence_ref_count == 2
    assert bundle.readiness_source_ref_preview.status == "ready"
    assert bundle.readiness_source_ref_preview.proof_ref_count == 2
    assert bundle.handoff.readiness_source_ref_preview.status == "ready"
    assert bundle.handoff.readiness_source_ref_preview.proof_ref_count == 2
    assert "## Readiness Proof History" in bundle.markdown
    assert "## Readiness Source Refs" in bundle.markdown
    assert "post-review handoff" in bundle.markdown
    assert "Source refs: `2`" in bundle.markdown
    assert "web:web_source:web-proof-1" in bundle.markdown
