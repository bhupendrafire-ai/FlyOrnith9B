from __future__ import annotations

from pathlib import Path

from app.context_compiler import ContextCompiler
from app.memory import MemoryContext
from app.persistence import RunStore
from app.repo_map import build_repo_map
from app.schemas import (
    ActionContextPack,
    ActionReadinessDecisionRecord,
    ActionReadinessDecisionReport,
    ActionReadinessReport,
    AcceptanceEvidenceRecommendation,
    GoalEvolutionDecisionRecord,
    GoalEvolutionReport,
    OperatorDispatchLedgerEntry,
    OperatorDispatchLedgerReport,
    OrnithLaunchChecklistReport,
    OrnithPreflightActionLedgerEntry,
    OrnithPreflightActionLedgerReport,
    PostActionRetryDecisionRecord,
    PostActionRetryReport,
    AcceptanceRecommendationTrace,
    RecoveryDecisionRecord,
    RecoveryDecisionReport,
    ResumeDecisionRecord,
    ResumeDecisionReport,
    SourceEvidencePreviewEntry,
    SourceEvidencePreviewReport,
    RunHealthReport,
    VerificationOutcomeRecord,
    VerificationOutcomeReport,
)


def test_repo_map_discovers_manifests_and_commands(tmp_path: Path) -> None:
    (tmp_path / "frontend").mkdir()
    (tmp_path / "README.md").write_text("# Demo", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest", encoding="utf-8")
    (tmp_path / "frontend" / "package.json").write_text(
        '{"scripts":{"build":"vite build","test":"vitest"}}',
        encoding="utf-8",
    )

    repo_map = build_repo_map(tmp_path)

    assert "README.md" in repo_map.manifests
    assert repo_map.package_scripts["build"] == "vite build"
    assert "npm run test" in repo_map.test_commands
    assert "python -m pytest" in repo_map.test_commands


def test_context_compiler_uses_compact_sections(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Improve harness", "Harness", str(tmp_path), ["verify"])
    run.state.repo_map.summary = "Tiny repo map"
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "Original goal" in prompt
    assert "repo_map" in snapshot.sections
    assert snapshot.estimated_tokens < 2000
    assert snapshot.prompt_preview


def test_context_compiler_includes_acceptance_recommendations(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Verify dashboard", "Harness", str(tmp_path), ["Dashboard starts"])
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
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "acceptance_recommendations" in snapshot.sections
    assert "browser_screenshot" in prompt
    assert "Next evidence actions" in prompt


def test_context_compiler_includes_acceptance_recommendation_traces(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Verify tests", "Harness", str(tmp_path), ["Tests pass"])
    run.state.acceptance_recommendation_traces = [
        AcceptanceRecommendationTrace(
            id="rec-trace-1",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            status="satisfied",
            result_ok=True,
            result_summary="All tests passed.",
        )
    ]
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "acceptance_recommendation_traces" in snapshot.sections
    assert "Evidence action traces" in prompt
    assert "satisfied:verification:run_tests" in prompt


def test_context_compiler_includes_run_health(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Watch health", "Harness", str(tmp_path), [])
    run.state.run_health = RunHealthReport(
        run_id=run.id,
        score=35,
        level="watch",
        recommended_action="pause",
        summary="watch: pause (35/100)",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "run_health" in snapshot.sections
    assert "Run health: watch:pause:35" in prompt

def test_context_compiler_includes_ornith_preflight(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume Ornith safely", "Harness", str(tmp_path), [])
    run.state.ornith_preflight = OrnithLaunchChecklistReport(
        run_id=run.id,
        generated_at="2026-06-27T12:15:00+00:00",
        mode="resume",
        status="attention",
        ready_to_resume=True,
        summary="Ornith can resume after dispatch smoke is refreshed.",
        readiness_smoke_status="passed",
        dispatch_restart_smoke_status="stale",
        run_health_level="watch",
        run_health_action="continue",
        next_actions=["Run operator-dispatch restart smoke before the final claim."],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "ornith_preflight" in snapshot.sections
    assert "Ornith preflight: attention" in prompt
    assert "dispatch=stale" in prompt
    assert "Run operator-dispatch restart smoke" in prompt


def test_context_compiler_includes_ornith_preflight_actions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume Ornith with action evidence", "Harness", str(tmp_path), [])
    latest = OrnithPreflightActionLedgerEntry(
        event_id=12,
        run_id=run.id,
        timestamp="2026-06-27T12:30:00+00:00",
        kind="ornith_preflight_action",
        status="completed",
        item_id="context_budget",
        action_reason="ornith_preflight_context_budget",
        action_summary="Refresh compact context before resuming Ornith.",
        ui_target="context_checkpoint",
        context_pressure="high",
        context_tokens=26000,
        context_target_tokens=18000,
        message="Completed Ornith preflight context checkpoint.",
    )
    run.state.ornith_preflight_actions = OrnithPreflightActionLedgerReport(
        run_id=run.id,
        generated_at="2026-06-27T12:30:00+00:00",
        total_count=1,
        completed_count=1,
        context_checkpoint_count=1,
        latest_action="completed:context_checkpoint",
        recommended_action="Use completed preflight actions as compact resume evidence.",
        entries=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "ornith_preflight_actions" in snapshot.sections
    assert "Ornith preflight actions: latest=completed:context_budget:context_checkpoint" in prompt
    assert "completed=1" in prompt
    assert "context=1" in prompt


def test_context_compiler_includes_resume_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume carefully", "Harness", str(tmp_path), [])
    decision = ResumeDecisionRecord(
        id=42,
        source="manual",
        accepted=True,
        policy_action="continue",
        predicted_status="running",
        predicted_milestone="act",
    )
    run.state.handoff_summary.resume_decisions = ResumeDecisionReport(
        run_id=run.id,
        decision_count=1,
        accepted_count=1,
        latest_decision=decision,
        latest_accepted=decision,
        current_policy_action="continue",
        current_predicted_status="running",
        current_predicted_milestone="act",
        current_matches_last_accepted=True,
        comparison_summary="Current policy simulation matches the latest accepted resume snapshot.",
        recommended_action="Continue under the accepted resume context.",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "resume_decisions" in snapshot.sections
    assert "Resume decision: latest=accepted:manual:continue" in prompt
    assert "Continue under the accepted resume context." in prompt


def test_context_compiler_includes_operator_dispatches(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Supervise carefully", "Harness", str(tmp_path), [])
    latest = OperatorDispatchLedgerEntry(
        event_id=11,
        run_id=run.id,
        timestamp="2026-06-27T12:00:00+00:00",
        kind="operator_action_dispatched",
        status="dispatched",
        decision="dispatch",
        confirmed=True,
        action_reason="recovery",
        action_title="Recovery attention",
        action_summary="Resume active recovery.",
        ui_target="recovery",
        message="Operator dispatched recovery resume.",
    )
    run.state.operator_dispatches = OperatorDispatchLedgerReport(
        run_id=run.id,
        generated_at="2026-06-27T12:00:00+00:00",
        total_count=1,
        dispatched_count=1,
        latest_action="dispatched:dispatch",
        recommended_action="Use dispatched operator actions as compact supervision evidence.",
        entries=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "operator_dispatches" in snapshot.sections
    assert "Operator dispatches: latest=dispatched:dispatch:recovery" in prompt
    assert "dispatched=1" in prompt


def test_context_compiler_includes_action_readiness(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Act carefully", "Harness", str(tmp_path), [])
    run.state.action_readiness = ActionReadinessReport(
        run_id=run.id,
        status="needs_proof",
        ready_to_act=True,
        recommended_action="Run the smallest relevant verification command.",
        suggested_tool="run_tests",
        suggested_label="verification",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "action_readiness" in snapshot.sections
    assert "Action readiness: needs_proof; ready=True" in prompt
    assert "tool=run_tests:verification" in prompt


def test_context_compiler_includes_action_readiness_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Trace readiness", "Harness", str(tmp_path), [])
    latest = ActionReadinessDecisionRecord(
        id=7,
        status="satisfied",
        source="harness",
        selected_tool="run_tests",
        label="verification",
        summary="harness selected run_tests for verification; intended proof was satisfied.",
    )
    run.state.action_readiness_decisions = ActionReadinessDecisionReport(
        run_id=run.id,
        decision_count=1,
        selected_count=1,
        satisfied_count=1,
        latest_decision=latest,
        latest_tool_decision=latest,
        summary=latest.summary,
        recommended_action="Continue with the next milestone using the compact satisfied-proof context.",
        decisions=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "action_readiness_decisions" in snapshot.sections
    assert "Action readiness decisions: latest=satisfied:harness:run_tests" in prompt
    assert "satisfied=1" in prompt


def test_context_compiler_includes_recovery_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Recover carefully", "Harness", str(tmp_path), [])
    latest = RecoveryDecisionRecord(
        id="recovery-1",
        status="active",
        trigger="readiness_decision_loop",
        tool="run_tests",
        proof_label="verification",
        selected_strategy="Run a narrower diagnostic than the repeated test command.",
        next_action="Review readiness decisions.",
        summary="active recovery for verification: Run a narrower diagnostic.",
    )
    run.state.recovery_decisions = RecoveryDecisionReport(
        run_id=run.id,
        decision_count=1,
        active_recovery=True,
        readiness_recovery_count=1,
        latest_decision=latest,
        active_decision=latest,
        latest_readiness_decision=latest,
        summary=latest.summary,
        recommended_action="Resume or replan active recovery: Review readiness decisions.",
        decisions=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "recovery_decisions" in snapshot.sections
    assert "Recovery decisions: latest=active:readiness_decision_loop:run_tests:verification" in prompt
    assert "active=True" in prompt

def test_context_compiler_includes_action_context_pack(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Use packed action context", "Harness", str(tmp_path), ["Tests pass"])
    run.state.action_context = ActionContextPack(
        run_id=run.id,
        generated_at="2026-06-28T12:05:00+00:00",
        milestone="act",
        current_task_id="task-1",
        current_task_title="Run focused proof",
        action_readiness_status="needs_proof",
        selected_tool="run_tests",
        selected_label="verification",
        selected_action="Run the smallest relevant verification command: python -m pytest",
        selected_reason="Criterion still needs test proof.",
        selected_command_hint="python -m pytest",
        selected_criterion="Tests pass",
        missing_source_labels=[],
        recent_verified_commands=["python -m compileall backend\\app"],
        recent_verified_files=["backend/app/engine.py"],
        recent_successes=["shell: compile passed"],
        failure_ledger=["timeout:shell:x2:Reduce command scope"],
        context_budget="1200/24000:low",
        compact_prompt=(
            "Action context pack:\n"
            "- selected_proof=run_tests:verification; action=Run the smallest relevant verification command: python -m pytest\n"
            "- failure_ledger=timeout:shell:x2:Reduce command scope"
        ),
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "action_context" in snapshot.sections
    assert "Action context pack:" in prompt
    assert "selected_proof=run_tests:verification" in prompt
    assert "failure_ledger=timeout:shell:x2" in prompt

def test_context_compiler_includes_source_evidence_preview(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Use compact source evidence", "Harness", str(tmp_path), [])
    run.state.source_evidence = SourceEvidencePreviewReport(
        run_id=run.id,
        generated_at="2026-06-28T12:00:00+00:00",
        total_count=2,
        web_source_count=1,
        browser_snapshot_count=1,
        linked_criterion_count=1,
        required_label_count=2,
        matched_label_count=1,
        missing_labels=["browser"],
        latest_evidence="browser_snapshot:Browser screenshot",
        recommended_action="Capture missing source evidence labels before claiming related criteria: browser",
        entries=[
            SourceEvidencePreviewEntry(
                id="browser-1",
                kind="browser_snapshot",
                title="Browser screenshot",
                tool_kind="browser_screenshot",
                evidence_label="browser",
                linked_criteria=["Dashboard visible"],
                summary="Captured browser screenshot.",
            )
        ],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "source_evidence" in snapshot.sections
    assert "Source evidence: total=2; web=1; browser=1" in prompt
    assert "missing=browser" in prompt
def test_context_compiler_includes_post_action_retries(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Retry compactly", "Post retry context", str(tmp_path), [])
    decision = PostActionRetryDecisionRecord(
        id="post-retry-1",
        status="pending",
        trigger_tool="run_tests",
        failure_kind="command_failure",
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
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "post_action_retries" in snapshot.sections
    assert "Post-action retries: latest=pending:run_tests->shell" in prompt
    assert "pending=1" in prompt

def test_context_compiler_includes_verification_outcomes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Verify after recovery", "Harness", str(tmp_path), [])
    latest = VerificationOutcomeRecord(
        id="outcome-tool-run-tests",
        tool_call_id="tool-run-tests",
        tool="run_tests",
        outcome="recovery_resolved",
        summary="All tests passed.",
        during_recovery=True,
        recovery_id="recovery-1",
        closed_recovery=True,
        resolved_recovery_evidence=True,
        proof_label="verification",
        evidence_status="verified",
        labels_satisfied=["verification"],
    )
    run.state.verification_outcomes = VerificationOutcomeReport(
        run_id=run.id,
        outcome_count=1,
        verified_count=1,
        recovery_outcome_count=1,
        recovery_resolved_count=1,
        latest_outcome=latest,
        latest_recovery_outcome=latest,
        summary="Recovery proof closed by run_tests: All tests passed.",
        recommended_action="Continue from the next milestone with the verified recovery evidence.",
        outcomes=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "verification_outcomes" in snapshot.sections
    assert "Verification outcomes: latest=recovery_resolved:run_tests:verification" in prompt
    assert "recovery_resolved=1" in prompt

def test_context_compiler_includes_goal_evolution(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Original goal", "Goal Context", str(tmp_path), [])
    decision = GoalEvolutionDecisionRecord(
        id="goal-context-1",
        status="pending",
        source="scheduled_review",
        previous_goal="Original goal",
        proposed_goal="Sharper context goal",
        reason="The objective narrowed after verification.",
        material_change="next=verify focused proof",
        step_count=3,
        milestone="decide",
        approval_id=7,
        created_at="2026-06-27T08:00:00+00:00",
    )
    run.state.proposed_goal = "Sharper context goal"
    run.state.goal_evolution = GoalEvolutionReport(
        run_id=run.id,
        generated_at="2026-06-27T08:01:00+00:00",
        active_goal=run.state.goal,
        proposed_goal="Sharper context goal",
        decision_count=1,
        pending_count=1,
        latest_decision=decision,
        summary="Goal update pending confirmation: Sharper context goal",
        recommended_action="Ask the operator to approve or reject the pending /goal update before resuming.",
        decisions=[decision],
    )

    prompt, snapshot = ContextCompiler(4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "goal_evolution" in snapshot.sections
    assert "Goal evolution: latest=pending:scheduled_review" in prompt
    assert "proposed=Sharper context goal" in prompt

