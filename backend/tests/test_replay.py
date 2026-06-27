from pathlib import Path

from app.persistence import RunStore
from app.replay import build_replay_bundle
from app.schemas import (
    AcceptanceCriterionEvidence,
    AcceptanceEvidenceRecommendation,
    AcceptanceRecommendationTrace,
    DesktopSnapshot,
    GoalEvolutionDecisionRecord,
    GoalEvolutionReport,
    ModelInteractionRecord,
    ModelProfileAdaptationProposal,
    OrnithLaunchChecklistReport,
    PolicySimulationReport,
    PostActionRetryDecisionRecord,
    PostActionRetryReport,
    RecoveryPlan,
    RunLease,
    ToolCallRecord,
    WebSource,
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
    assert "# Replay: Replay" in bundle.markdown
    assert "Resume run" in bundle.markdown


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
    assert "## Source Evidence" in bundle.markdown
    assert "## Action Context" in bundle.markdown
    assert "Source preview docs" in bundle.markdown

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

    bundle = build_replay_bundle(
        store.get_run(run.id),
        events=store.list_events(run.id),
        approvals=store.list_approvals(run.id),
    )

    assert bundle.report_integrity.status == "ok"
    assert bundle.handoff.report_integrity.ok_count == bundle.report_integrity.ok_count
    assert "## Report Integrity" in bundle.markdown
    assert "Handoff and replay report index is complete" in bundle.markdown


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
