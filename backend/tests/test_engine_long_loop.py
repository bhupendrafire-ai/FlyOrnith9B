from __future__ import annotations

import asyncio
import subprocess
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from app.engine import AgentLoopEngine
from app.events import EventBroker
from app.memory import ObsidianMemory
from app.persistence import RunStore
from app.readiness_completion import build_readiness_completion
from app.schemas import (
    AcceptanceCriterionEvidence,
    AcceptanceRecommendationTrace,
    CompletionAuditReport,
    ContextBudget,
    ObjectiveReadinessItem,
    ObjectiveReadinessProofPreference,
    OperatorActionDispatchRequest,
    OperatorDispatchRestartSmokeLedgerEntry,
    OperatorDispatchRestartSmokeLedgerReport,
    OperatorDispatchRestartSmokeReport,
    ObjectiveReadinessProofOutcome,
    ObjectiveReadinessReport,
    PolicySimulationReport,
    ReadinessRehearsalLedgerEntry,
    ReadinessRehearsalLedgerReport,
    ReadinessRehearsalReport,
    ReadinessRehearsalStep,
    RunProgressReport,
    RecoveryPlan,
    RunLease,
    ToolCallRecord,
    WorkspaceIsolation,
)
from app.tools import ToolResult

from conftest import make_config


class FakeModel:
    async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
        return '{"should_update": false, "proposed_goal": "", "reason": ""}'


def make_engine(
    tmp_path: Path,
    *,
    auto_resume: bool = False,
    auto_resume_max_runs: int = 1,
    **config_overrides,
) -> AgentLoopEngine:
    config = replace(
        make_config(tmp_path),
        enable_supervisor_auto_resume=auto_resume,
        supervisor_auto_resume_max_runs=auto_resume_max_runs,
        **config_overrides,
    )
    return AgentLoopEngine(
        config,
        RunStore(config.sqlite_path),
        ObsidianMemory(config.obsidian_vault_path),
        FakeModel(),  # type: ignore[arg-type]
        EventBroker(),
    )


OBJECTIVE_READINESS_ITEM_IDS = [
    "isolated_workspaces",
    "patch_first_editing",
    "durable_task_graph",
    "compact_context",
    "repo_map",
    "verification_critic_loop",
    "failure_recovery",
    "replay_audit_trails",
    "obsidian_handoffs",
    "goal_evolution",
]


def objective_readiness_outcomes(item_ids: list[str]) -> list[ObjectiveReadinessProofOutcome]:
    return [
        ObjectiveReadinessProofOutcome(
            id=f"obj-proof-{item_id}",
            item_id=item_id,
            tool="run_tests",
            evidence_label="objective",
            strategy="fixture_proof",
            outcome="verified",
            ok=True,
            summary=f"{item_id} verified by focused fixture.",
            proof_action="Verify readiness fixture.",
            created_at="2026-06-27T08:00:00+00:00",
        )
        for item_id in item_ids
    ]


def passed_rehearsal_ledger(run_id: str = "run-smoke") -> ReadinessRehearsalLedgerReport:
    latest = ReadinessRehearsalLedgerEntry(
        run_id=run_id,
        generated_at="2026-06-27T08:00:00+00:00",
        status="passed",
        summary="Readiness rehearsal passed.",
        rehearsal_workspace="H:\\AgentOrinth\\agentic-coding-system\\data\\workspaces\\rehearsals\\run-smoke",
        restart_simulated=True,
        replay_attached=True,
        handoff_attached=True,
        compact_context_tokens=1200,
        refused_event_id=1,
        accepted_event_id=2,
        completed_event_id=3,
        step_count=7,
        passed_steps=7,
    )
    return ReadinessRehearsalLedgerReport(
        generated_at="2026-06-27T08:00:00+00:00",
        status="passed",
        summary=f"Latest readiness rehearsal passed for {run_id}.",
        total_count=1,
        passed_count=1,
        latest=latest,
        entries=[latest],
    )


def passed_dispatch_restart_smoke_ledger(
    run_id: str = "run-dispatch-smoke",
) -> OperatorDispatchRestartSmokeLedgerReport:
    latest = OperatorDispatchRestartSmokeLedgerEntry(
        run_id=run_id,
        generated_at="2026-06-27T08:00:00+00:00",
        status="passed",
        summary="Operator-dispatch restart smoke passed.",
        restart_simulated=True,
        dispatch_event_id=4,
        compact_context_tokens=900,
        ledger_attached=True,
        handoff_attached=True,
        replay_attached=True,
        context_attached=True,
        step_count=6,
        passed_steps=6,
    )
    return OperatorDispatchRestartSmokeLedgerReport(
        generated_at="2026-06-27T08:00:00+00:00",
        status="passed",
        summary=f"Latest operator-dispatch restart smoke passed for {run_id}.",
        total_count=1,
        passed_count=1,
        latest=latest,
        entries=[latest],
    )


def seed_passed_rehearsal(engine: AgentLoopEngine, tmp_path: Path, generated_at: str = "2026-06-27T08:00:00+00:00") -> str:
    run = engine.store.create_run(
        "Readiness smoke seed",
        "Readiness smoke seed",
        str(tmp_path),
        [],
        tool_profile="ornith_rehearsal",
    )
    report = ReadinessRehearsalReport(
        run_id=run.id,
        generated_at=generated_at,
        status="passed",
        summary="Seeded readiness rehearsal passed.",
        rehearsal_workspace=str(tmp_path),
        restart_simulated=True,
        refused_event_id=1,
        accepted_event_id=2,
        completed_event_id=3,
        compact_context_tokens=1200,
        replay_attached=True,
        handoff_attached=True,
        steps=[
            ReadinessRehearsalStep(
                id=f"step-{index}",
                status="passed",
                summary=f"Seed step {index} passed.",
                event_id=index,
            )
            for index in range(1, 8)
        ],
    )
    run.state.readiness_rehearsal = report
    run.state.handoff_summary.readiness_rehearsal = report
    engine.store.update_run(run.id, status="completed", state=run.state)
    return run.id


def seed_passed_dispatch_restart_smoke(engine: AgentLoopEngine, tmp_path: Path, generated_at: str = "2026-06-27T08:00:00+00:00") -> str:
    run = engine.store.create_run(
        "Operator dispatch smoke seed",
        "Operator dispatch smoke seed",
        str(tmp_path),
        [],
        tool_profile="ornith_operator_smoke",
    )
    report = OperatorDispatchRestartSmokeReport(
        run_id=run.id,
        generated_at=generated_at,
        status="passed",
        summary="Seeded operator-dispatch restart smoke passed.",
        restart_simulated=True,
        dispatch_event_id=4,
        compact_context_tokens=900,
        compact_context_sections=["operator_dispatches", "handoff", "replay"],
        ledger_attached=True,
        handoff_attached=True,
        replay_attached=True,
        context_attached=True,
        steps=[
            ReadinessRehearsalStep(
                id=f"dispatch-step-{index}",
                status="passed",
                summary=f"Seed dispatch step {index} passed.",
                event_id=index,
            )
            for index in range(1, 7)
        ],
    )
    run.state.operator_dispatch_restart_smoke = report
    run.state.handoff_summary.operator_dispatch_restart_smoke = report
    engine.store.update_run(run.id, status="completed", state=run.state)
    return run.id


def make_git_workspace(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_handoff_contains_resume_prompt(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Build long loop", "Loop", str(tmp_path), ["checkpoint"])
    run.state.next_step = "Continue safely"

    handoff = engine._make_handoff(run, run.state)

    assert handoff.original_goal == "Build long loop"
    assert "Resume AgentOrinth run" in handoff.resume_prompt
    assert handoff.next_action == "Continue safely"
    assert handoff.repo_map_summary
    assert handoff.current_task_id
    assert handoff.acceptance_evidence[0].status == "open"


def test_plan_milestone_injects_objective_readiness_for_harness_goal(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Improve AgentOrinth into a Codex-like long coding harness",
            "Harness plan",
            str(tmp_path),
            [],
        )
        created.state.milestone = "plan"
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)

        assert updated.state.milestone == "act"
        assert any(step.startswith("Objective readiness:") for step in updated.state.current_plan)
        assert updated.state.objective_readiness.next_actions
        assert "Proof:" in updated.state.current_plan[1]
        assert any("Objective readiness added plan action" in fact for fact in updated.state.facts_learned)

    asyncio.run(run())


def test_plan_milestone_does_not_inject_objective_readiness_for_ordinary_goal(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Fix dashboard filtering bug", "Ordinary plan", str(tmp_path), [])
        created.state.milestone = "plan"
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)

        assert not any(step.startswith("Objective readiness:") for step in updated.state.current_plan)

    asyncio.run(run())


def test_choose_action_uses_objective_readiness_proof_tool_for_current_task(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Improve AgentOrinth harness verification", "Readiness proof", str(tmp_path), [])
        created.state.repo_map.test_commands = ["pytest -q"]
        created.state.current_plan = [
            "Objective readiness: Run the smallest verification action and record the outcome. Proof: run_tests / verification."
        ]
        created.state.task_graph = engine._tasks_from_plan(created.state.current_plan, [])
        created.state.current_task_id = created.state.task_graph[0].id
        created.state.next_step = created.state.current_plan[0]
        created.state.step_count = 1
        engine._build_objective_readiness(created, created.state)

        action = await engine._choose_action(created, "compact context")

        assert action["tool"] == "run_tests"
        assert action["args"]["command"] == "pytest -q"
        assert action["objective_readiness_item_id"] == "verification_critic_loop"
        assert created.state.model_interactions[-1].summary == "Harness selected objective-readiness proof tool: run_tests."

    asyncio.run(run())


def test_objective_readiness_prefers_compile_check_after_failed_test_proof(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Improve AgentOrinth harness verification", "Readiness preference", str(tmp_path), [])
    run.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-proof-failed",
            item_id="verification_critic_loop",
            tool="run_tests",
            evidence_label="verification",
            strategy="smallest_test",
            outcome="failed",
            ok=False,
            summary="Broad tests failed.",
            proof_action="Run the smallest relevant verification command.",
        )
    ]
    run = engine.store.update_run(run.id, state=run.state)

    report = engine._build_objective_readiness(run, run.state)
    item = next(item for item in report.items if item.id == "verification_critic_loop")

    assert item.status == "failed"
    assert item.preferred_proof.tool_kind == "shell"
    assert item.preferred_proof.strategy == "compile_check"
    assert item.preferred_proof.command_hint == "python -m compileall backend\\app"
    assert report.proof_preferences[0].item_id == "verification_critic_loop"
    assert any("compile_check" in action for action in report.next_actions)


def test_choose_action_uses_objective_readiness_preferred_strategy(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Improve AgentOrinth harness verification", "Readiness preferred action", str(tmp_path), [])
        created.state.current_plan = [
            "Objective readiness: Run the smallest verification action and record the outcome. Proof: run_tests / verification."
        ]
        created.state.task_graph = engine._tasks_from_plan(created.state.current_plan, [])
        created.state.current_task_id = created.state.task_graph[0].id
        created.state.next_step = created.state.current_plan[0]
        created.state.step_count = 1
        created.state.objective_readiness_proof_outcomes = [
            ObjectiveReadinessProofOutcome(
                id="obj-proof-failed",
                item_id="verification_critic_loop",
                tool="run_tests",
                evidence_label="verification",
                strategy="smallest_test",
                outcome="failed",
                ok=False,
                summary="Broad tests failed.",
                proof_action="Run the smallest relevant verification command.",
            )
        ]
        engine._build_objective_readiness(created, created.state)

        action = await engine._choose_action(created, "compact context")

        assert action["tool"] == "shell"
        assert action["args"]["command"] == "python -m compileall backend\\app"
        assert action["objective_readiness_item_id"] == "verification_critic_loop"
        assert action["objective_readiness_proof_strategy"] == "compile_check"
        assert "compile check" in action["objective_readiness_proof_action"]

    asyncio.run(run())


def test_choose_action_supervises_approval_sensitive_objective_readiness_proof(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Improve AgentOrinth patch-first harness", "Readiness approval", str(tmp_path), [])
        created.state.current_plan = [
            "Objective readiness: Exercise patch_propose on a real edit and verify approval-gated patch_apply. Proof: patch_propose / edit."
        ]
        created.state.task_graph = engine._tasks_from_plan(created.state.current_plan, [])
        created.state.current_task_id = created.state.task_graph[0].id
        created.state.next_step = created.state.current_plan[0]
        created.state.step_count = 1
        engine._build_objective_readiness(created, created.state)

        action = await engine._choose_action(created, "compact context")

        assert action["tool"] == "ask_user"
        assert "requires supervised approval" in action["args"]["question"]
        assert "patch_first_editing" in action["args"]["question"]

    asyncio.run(run())


def test_objective_readiness_proof_success_updates_matrix(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Improve AgentOrinth harness verification",
            "Readiness outcome",
            str(tmp_path),
            ["Tests pass"],
        )
        engine._ensure_acceptance_evidence(created.state)
        created.state.repo_map.test_commands = ["pytest -q"]
        created.state.current_plan = [
            "Objective readiness: Run the smallest verification action and record the outcome. Proof: run_tests / verification."
        ]
        created.state.task_graph = engine._tasks_from_plan(created.state.current_plan, [])
        created.state.current_task_id = created.state.task_graph[0].id
        created.state.next_step = created.state.current_plan[0]
        created.state.step_count = 1
        engine._build_objective_readiness(created, created.state)
        engine.store.update_run(created.id, state=created.state)
        run_record = engine.store.get_run(created.id)

        action = await engine._choose_action(run_record, "compact context")
        await engine._record_tool_result(
            created.id,
            ToolResult(True, "run_tests", "All tests passed.", {"command": "pytest -q"}),
            action=action,
        )
        updated = engine.store.get_run(created.id)
        outcome = updated.state.objective_readiness_proof_outcomes[-1]
        report = engine._build_objective_readiness(updated, updated.state)
        item = next(item for item in report.items if item.id == "verification_critic_loop")

        assert outcome.item_id == "verification_critic_loop"
        assert outcome.outcome == "verified"
        assert item.status == "verified"
        assert item.latest_outcome.id == outcome.id

    asyncio.run(run())


def test_objective_readiness_proof_failure_updates_matrix(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Improve AgentOrinth harness verification", "Readiness failed", str(tmp_path), [])
        created.state.current_plan = [
            "Objective readiness: Run the smallest verification action and record the outcome. Proof: run_tests / verification."
        ]
        created.state.task_graph = engine._tasks_from_plan(created.state.current_plan, [])
        created.state.current_task_id = created.state.task_graph[0].id
        created.state.next_step = created.state.current_plan[0]
        created.state.step_count = 1
        engine._build_objective_readiness(created, created.state)
        engine.store.update_run(created.id, state=created.state)
        run_record = engine.store.get_run(created.id)

        action = await engine._choose_action(run_record, "compact context")
        await engine._record_tool_result(
            created.id,
            ToolResult(False, "run_tests", "Tests failed.", {"command": "python -m pytest"}),
            action=action,
        )
        updated = engine.store.get_run(created.id)
        report = engine._build_objective_readiness(updated, updated.state)
        item = next(item for item in report.items if item.id == "verification_critic_loop")

        assert updated.state.objective_readiness_proof_outcomes[-1].outcome == "failed"
        assert item.status == "failed"
        assert report.failed_count >= 1
        assert "alternate proof" in item.next_action

    asyncio.run(run())


def test_readiness_completion_gate_allows_harness_milestone_claim(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness completion",
        str(tmp_path),
        ["Harness readiness is verified"],
    )
    items = [
        ObjectiveReadinessItem(
            id=f"item-{index}",
            requirement=f"Requirement {index}",
            status="verified",
        )
        for index in range(10)
    ]
    objective = ObjectiveReadinessReport(
        run_id=run.id,
        status="ready",
        verified_count=10,
        partial_count=0,
        missing_count=0,
        failed_count=0,
        items=items,
    )
    completion = CompletionAuditReport(
        run_id=run.id,
        status="ready",
        can_finish=True,
        acceptance_total=1,
        acceptance_verified=1,
    )
    progress = RunProgressReport(
        run_id=run.id,
        status="near_completion",
        can_keep_running=True,
        near_completion=True,
    )

    report = build_readiness_completion(
        run,
        objective,
        progress,
        completion,
        passed_rehearsal_ledger(),
        passed_dispatch_restart_smoke_ledger(),
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    assert report.status == "ready"
    assert report.can_claim_milestone is True
    assert report.confidence == "high"
    assert report.blocking_count == 0
    assert any(check.id == "readiness_rehearsal" and check.status == "pass" for check in report.checks)
    assert any(check.id == "operator_dispatch_restart_smoke" and check.status == "pass" for check in report.checks)


def test_readiness_completion_gate_blocks_missing_rehearsal_ledger(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness missing smoke",
        str(tmp_path),
        ["Harness readiness is verified"],
    )
    items = [
        ObjectiveReadinessItem(
            id=f"item-{index}",
            requirement=f"Requirement {index}",
            status="verified",
        )
        for index in range(10)
    ]
    objective = ObjectiveReadinessReport(
        run_id=run.id,
        status="ready",
        verified_count=10,
        items=items,
    )
    completion = CompletionAuditReport(
        run_id=run.id,
        status="ready",
        can_finish=True,
        acceptance_total=1,
        acceptance_verified=1,
    )
    progress = RunProgressReport(
        run_id=run.id,
        status="near_completion",
        can_keep_running=True,
        near_completion=True,
    )

    report = build_readiness_completion(
        run,
        objective,
        progress,
        completion,
        ReadinessRehearsalLedgerReport(status="never_run"),
        passed_dispatch_restart_smoke_ledger(),
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert report.rehearsal_ledger_status == "never_run"
    assert any(check.id == "readiness_rehearsal" and check.status == "block" for check in report.checks)


def test_readiness_completion_gate_blocks_missing_dispatch_restart_smoke_ledger(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness missing dispatch smoke",
        str(tmp_path),
        ["Harness readiness is verified"],
    )
    items = [
        ObjectiveReadinessItem(
            id=f"item-{index}",
            requirement=f"Requirement {index}",
            status="verified",
        )
        for index in range(10)
    ]
    objective = ObjectiveReadinessReport(
        run_id=run.id,
        status="ready",
        verified_count=10,
        items=items,
    )
    completion = CompletionAuditReport(
        run_id=run.id,
        status="ready",
        can_finish=True,
        acceptance_total=1,
        acceptance_verified=1,
    )
    progress = RunProgressReport(
        run_id=run.id,
        status="near_completion",
        can_keep_running=True,
        near_completion=True,
    )

    report = build_readiness_completion(
        run,
        objective,
        progress,
        completion,
        passed_rehearsal_ledger(),
        OperatorDispatchRestartSmokeLedgerReport(status="never_run"),
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert report.dispatch_restart_smoke_ledger_status == "never_run"
    assert any(check.id == "operator_dispatch_restart_smoke" and check.status == "block" for check in report.checks)


def test_readiness_completion_gate_blocks_failed_objective_preference(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness blocked",
        str(tmp_path),
        ["Harness readiness is verified"],
    )
    failed_item = ObjectiveReadinessItem(
        id="verification_critic_loop",
        requirement="Long tasks need verification.",
        status="failed",
        next_action="Choose an alternate proof.",
        preferred_proof=ObjectiveReadinessProofPreference(
            item_id="verification_critic_loop",
            tool_kind="shell",
            strategy="compile_check",
            action="Run compile check.",
        ),
        latest_outcome=ObjectiveReadinessProofOutcome(
            id="obj-proof-failed",
            item_id="verification_critic_loop",
            tool="run_tests",
            strategy="smallest_test",
            outcome="failed",
            summary="Tests failed.",
        ),
    )
    objective = ObjectiveReadinessReport(
        run_id=run.id,
        status="not_ready",
        verified_count=8,
        partial_count=1,
        failed_count=1,
        items=[failed_item],
        next_actions=["Choose an alternate proof."],
    )
    completion = CompletionAuditReport(
        run_id=run.id,
        status="ready",
        can_finish=True,
        acceptance_total=1,
        acceptance_verified=1,
    )
    progress = RunProgressReport(run_id=run.id, status="near_completion", near_completion=True)

    report = build_readiness_completion(run, objective, progress, completion)

    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert any(check.id == "proof_preferences" and check.status == "block" for check in report.checks)
    assert report.open_preference_count == 1


def test_decide_milestone_records_readiness_claim_before_completion(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        seed_passed_rehearsal(engine, tmp_path)
        seed_passed_dispatch_restart_smoke(engine, tmp_path)
        created = engine.store.create_run(
            "Improve Orint model into a Codex-like coding harness",
            "Readiness claim decision",
            str(tmp_path),
            ["Harness readiness"],
        )
        created.state.milestone = "decide"
        created.state.acceptance_evidence = [
            AcceptanceCriterionEvidence(
                id="criterion-1",
                criterion="Harness readiness",
                status="verified",
                evidence=["Harness readiness verified."],
                last_tool="run_tests",
                last_checked="2026-06-27T08:00:00+00:00",
            )
        ]
        created.state.objective_readiness_proof_outcomes = objective_readiness_outcomes(OBJECTIVE_READINESS_ITEM_IDS)
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)

        updated = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)
        kinds = [event["kind"] for event in events]
        autonomy = engine.get_autonomy_decisions(created.id)

        assert updated.status == "completed"
        assert "readiness_claim" in kinds
        assert kinds.index("readiness_claim") < kinds.index("completed")
        assert updated.state.handoff_summary.readiness_completion.can_claim_milestone is True
        assert any(
            decision["kind"] == "readiness_claim"
            and decision["decision"] == "complete"
            and decision["source"] == "readiness_completion"
            for decision in autonomy["decisions"]
        )

    asyncio.run(run())


def test_decide_milestone_routes_blocked_readiness_claim_to_smallest_proof(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Improve AgentOrinth into a Codex-like long coding harness",
            "Readiness claim blocked",
            str(tmp_path),
            ["Harness readiness"],
        )
        created.state.milestone = "decide"
        created.state.acceptance_evidence = [
            AcceptanceCriterionEvidence(
                id="criterion-1",
                criterion="Harness readiness",
                status="verified",
                evidence=["Harness readiness verified."],
                last_tool="run_tests",
                last_checked="2026-06-27T08:00:00+00:00",
            )
        ]
        created.state.objective_readiness_proof_outcomes = objective_readiness_outcomes(
            OBJECTIVE_READINESS_ITEM_IDS[:8]
        )
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)

        updated = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)
        blocked_event = next(event for event in events if event["kind"] == "readiness_claim_blocked")
        autonomy = engine.get_autonomy_decisions(created.id)
        action = await engine._choose_action(updated, "compact context")

        assert updated.status == "queued"
        assert updated.state.milestone == "act"
        assert updated.state.next_step.startswith("Objective readiness:")
        assert updated.state.readiness_completion.can_claim_milestone is False
        assert blocked_event["data"]["accepted"] is False
        assert not any(event["kind"] == "completed" for event in events)
        assert any(
            decision["kind"] == "readiness_claim_blocked"
            and decision["decision"] == "verify"
            and decision["source"] == "readiness_completion"
            for decision in autonomy["decisions"]
        )
        assert action["tool"] == "obsidian_checkpoint"
        assert action["objective_readiness_item_id"] == "obsidian_handoffs"

    asyncio.run(run())


def test_readiness_claim_rehearsal_survives_checkpoint_restart_and_resume(tmp_path: Path) -> None:
    async def run() -> None:
        make_git_workspace(tmp_path)
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Improve Orinth into a Codex-like long-running local coding harness",
            "Readiness rehearsal",
            str(tmp_path),
            ["Harness readiness"],
            tool_profile="ornith_rehearsal",
        )
        created.state.milestone = "decide"
        created.state.acceptance_evidence = [
            AcceptanceCriterionEvidence(
                id="criterion-1",
                criterion="Harness readiness",
                status="verified",
                evidence=["Harness readiness verified before claim rehearsal."],
                last_tool="run_tests",
                last_checked="2026-06-27T08:00:00+00:00",
            )
        ]
        created.state.objective_readiness_proof_outcomes = objective_readiness_outcomes(
            [
                item_id
                for item_id in OBJECTIVE_READINESS_ITEM_IDS
                if item_id not in {"obsidian_handoffs", "goal_evolution"}
            ]
        )
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        await engine_one._run_one_milestone(created.id)
        refused = engine_one.store.get_run(created.id)
        refused_events = engine_one.store.list_events(created.id)

        assert refused.status == "queued"
        assert refused.state.milestone == "act"
        assert refused.state.readiness_completion.can_claim_milestone is False
        assert refused.state.current_task_id.startswith("task-readiness-")
        assert refused.state.next_step.startswith("Objective readiness:")
        assert any(event["kind"] == "readiness_claim_blocked" for event in refused_events)
        assert not any(event["kind"] == "completed" for event in refused_events)

        await engine_one._run_one_milestone(created.id)
        after_proof = engine_one.store.get_run(created.id)
        assert after_proof.state.milestone == "verify"
        assert after_proof.state.objective_readiness_proof_outcomes[-1].item_id == "obsidian_handoffs"
        assert after_proof.state.objective_readiness_proof_outcomes[-1].tool == "obsidian_checkpoint"

        await engine_one._run_one_milestone(created.id)
        after_verify = engine_one.store.get_run(created.id)
        assert after_verify.state.milestone == "checkpoint"
        assert after_verify.state.tool_calls[-1].name == "shell"
        assert "git status --short" in after_verify.state.commands_run[-1]

        await engine_one._run_one_milestone(created.id)
        checkpointed = engine_one.store.get_run(created.id)
        assert checkpointed.state.milestone == "decide"
        assert "Resume AgentOrinth run" in checkpointed.state.handoff_summary.resume_prompt
        assert engine_one.memory.read_run_note(created.id)

        engine_one.store.update_run(created.id, status="paused", state=checkpointed.state)
        engine_two = make_engine(tmp_path)
        resumed = await engine_two.resume_run(created.id)
        engine_two._cancel_task(created.id)
        resume_events = engine_two.store.list_events(created.id)
        resume_preflight = next(event for event in resume_events if event["kind"] == "resume_preflight")

        assert resumed.status == "queued"
        assert resume_preflight["data"]["accepted"] is True
        assert resume_preflight["data"]["policy_simulation"]["policy_action"] == "complete"

        await engine_two._run_one_milestone(created.id)
        completed = engine_two.store.get_run(created.id)
        completed_events = engine_two.store.list_events(created.id)
        kinds = [event["kind"] for event in completed_events]
        autonomy = engine_two.get_autonomy_decisions(created.id)
        memory_context = engine_two.memory.consult(completed.goal, run_id=completed.id)
        prompt, snapshot = engine_two.context_compiler.compile(
            completed,
            completed.state,
            memory_context,
            engine_two.store.list_events(completed.id, limit=20),
        )

        assert completed.status == "completed"
        assert completed.state.readiness_completion.can_claim_milestone is True
        assert completed.state.objective_readiness.verified_count >= 9
        assert completed.state.memory_refs
        assert kinds.count("readiness_claim_blocked") == 1
        assert kinds.count("readiness_claim") == 1
        assert kinds.index("readiness_claim_blocked") < kinds.index("readiness_claim") < kinds.index("completed")
        assert any(
            decision["kind"] == "readiness_claim_blocked"
            and decision["decision"] == "verify"
            for decision in autonomy["decisions"]
        )
        assert any(
            decision["kind"] == "readiness_claim"
            and decision["decision"] == "complete"
            for decision in autonomy["decisions"]
        )
        assert "Do not reload raw logs" in completed.state.handoff_summary.resume_prompt
        assert snapshot.estimated_tokens <= engine_two.context_compiler.target_tokens
        assert len(engine_two.store.list_events(completed.id, limit=20)) <= 20
        assert "## handoff" in prompt
        assert "## memory" in prompt
        assert "Checkpoint:" in prompt

    asyncio.run(run())


def test_acceptance_evidence_gates_completion_until_verified(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Run checks", "Checks", str(tmp_path), ["Run tests pass"])

    assert not engine._should_finish(run.state)

    result = type(
        "Result",
        (),
        {
            "ok": True,
            "kind": "run_tests",
            "summary": "All tests passed.",
            "data": {"command": "python -m pytest"},
            "needs_approval": False,
            "web_sources": [],
            "desktop_snapshots": [],
            "patch_proposals": [],
            "patch_applications": [],
            "workspace_diff": None,
            "workspace_promotions": [],
        },
    )()

    async def record() -> None:
        await engine._record_tool_result(run.id, result)  # type: ignore[arg-type]

    asyncio.run(record())
    updated = engine.store.get_run(run.id)

    assert updated.state.acceptance_evidence[0].status == "verified"
    assert updated.state.acceptance_evidence[0].required_labels == ["verification"]
    assert updated.state.acceptance_evidence[0].matched_labels == ["verification"]
    assert "run_tests [verification]: All tests passed." in updated.state.acceptance_evidence[0].evidence
    assert engine._should_finish(updated.state)


def test_checkpoint_milestone_verifies_checkpoint_criterion(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Write checkpoint",
        "Checkpoint criterion",
        str(tmp_path),
        ["Obsidian checkpoint is written"],
    )

    engine._record_acceptance_checkpoint(run.state)

    assert run.state.acceptance_evidence[0].status == "verified"
    assert run.state.acceptance_evidence[0].last_tool == "checkpoint"
    assert run.state.acceptance_evidence[0].matched_labels == ["checkpoint"]


def test_acceptance_evidence_requires_all_labels_for_multi_part_criterion(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Verify dashboard and tests",
        "Multi evidence",
        str(tmp_path),
        ["Dashboard starts and tests pass"],
    )
    engine._ensure_acceptance_evidence(run.state)
    assert [item.label for item in run.state.acceptance_recommendations] == ["verification", "browser"]
    assert run.state.acceptance_recommendations[0].tool_kind == "run_tests"
    assert run.state.acceptance_recommendations[1].tool_kind == "browser_screenshot"

    test_result = type(
        "Result",
        (),
        {
            "ok": True,
            "kind": "run_tests",
            "summary": "All tests passed.",
            "data": {"command": "python -m pytest"},
            "needs_approval": False,
            "web_sources": [],
            "desktop_snapshots": [],
            "patch_proposals": [],
            "patch_applications": [],
            "workspace_diff": None,
            "workspace_promotions": [],
        },
    )()
    browser_result = type(
        "Result",
        (),
        {
            "ok": True,
            "kind": "browser_screenshot",
            "summary": "Dashboard screenshot captured.",
            "data": {},
            "needs_approval": False,
            "web_sources": [],
            "desktop_snapshots": [],
            "patch_proposals": [],
            "patch_applications": [],
            "workspace_diff": None,
            "workspace_promotions": [],
        },
    )()

    engine._update_acceptance_evidence(run.state, test_result)  # type: ignore[arg-type]

    item = run.state.acceptance_evidence[0]
    assert item.required_labels == ["verification", "browser"]
    assert item.matched_labels == ["verification"]
    assert item.status == "open"
    assert [item.label for item in run.state.acceptance_recommendations] == ["browser"]

    engine._update_acceptance_evidence(run.state, browser_result)  # type: ignore[arg-type]

    assert item.matched_labels == ["verification", "browser"]
    assert item.status == "verified"
    assert set(item.label_checked_at) == {"verification", "browser"}
    assert run.state.acceptance_recommendations == []


def test_acceptance_recommendations_respect_disabled_tools(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Verify web and dashboard",
        "Disabled evidence",
        str(tmp_path),
        ["Latest web source and dashboard screenshot"],
    )
    run.state.web_enabled = False
    run.state.browser_enabled = False
    run.state.desktop_enabled = False

    engine._ensure_acceptance_evidence(run.state)

    recommendations = {item.label: item for item in run.state.acceptance_recommendations}
    assert recommendations["web"].tool_kind == "ask_user"
    assert not recommendations["web"].available
    assert recommendations["browser"].tool_kind == "ask_user"
    assert not recommendations["browser"].available


def test_choose_action_uses_available_acceptance_recommendation(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Run verification", "Recommended action", str(tmp_path), ["Tests pass"])
        created.state.step_count = 1

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "run_tests"
        assert action["args"]["command"] == "python -m pytest"
        assert action["recommendation_trace_id"]
        assert created.state.action_context.selected_tool == "run_tests"
        assert created.state.action_context.selected_label == "verification"
        assert "selected_proof=run_tests:verification" in created.state.action_context.compact_prompt
        assert created.state.acceptance_recommendation_traces[0].status == "selected"
        assert "acceptance recommendation" in created.state.model_interactions[-1].summary

    asyncio.run(run())


def test_recommendation_trace_resolves_when_evidence_label_is_satisfied(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Run verification", "Trace action", str(tmp_path), ["Tests pass"])
        created.state.step_count = 1
        action = await engine._choose_action(created, "tiny context")
        engine.store.update_run(created.id, state=created.state)

        await engine._record_tool_result(
            created.id,
            ToolResult(True, "run_tests", "All tests passed.", {"command": "python -m pytest"}),
            action=action,
        )
        updated = engine.store.get_run(created.id)
        trace = updated.state.acceptance_recommendation_traces[0]

        assert trace.status == "satisfied"
        assert trace.result_ok is True
        assert trace.evidence_status == "verified"
        assert trace.label == "verification"

    asyncio.run(run())


def test_recommendation_trace_records_failed_result(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Run verification", "Trace failure", str(tmp_path), ["Tests pass"])
        created.state.step_count = 1
        action = await engine._choose_action(created, "tiny context")
        engine.store.update_run(created.id, state=created.state)

        await engine._record_tool_result(
            created.id,
            ToolResult(False, "run_tests", "Tests failed.", {"command": "python -m pytest"}),
            action=action,
        )
        trace = engine.store.get_run(created.id).state.acceptance_recommendation_traces[0]

        assert trace.status == "failed"
        assert trace.result_ok is False
        assert trace.result_summary == "Tests failed."

    asyncio.run(run())


def test_choose_action_keeps_initial_workspace_inspection_before_recommendation(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Run verification", "Initial action", str(tmp_path), ["Tests pass"])

        action = await engine._choose_action(created, "tiny context")

        assert action == {"tool": "file_read", "args": {"path": "."}, "thought_summary": "Inspect workspace file list first."}

    asyncio.run(run())


def test_choose_action_falls_back_to_ask_user_for_unavailable_recommendation(tmp_path: Path) -> None:
    class BadActionModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            return '{"tool":"invent_magic","args":{},"thought_summary":"Try impossible tool."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = BadActionModel()  # type: ignore[assignment]
        created = engine.store.create_run(
            "Verify dashboard",
            "Unavailable recommendation",
            str(tmp_path),
            ["Dashboard starts"],
        )
        created.state.step_count = 1
        created.state.browser_enabled = False
        created.state.desktop_enabled = False

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "ask_user"
        assert "enable browser or desktop" in action["args"]["question"].lower()
        assert created.state.model_interactions[-1].fallback_used

    asyncio.run(run())


def test_choose_action_prompt_includes_edit_recommendation_without_empty_patch(tmp_path: Path) -> None:
    class CapturingModel:
        def __init__(self) -> None:
            self.user_prompt = ""

        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            self.user_prompt = messages[-1]["content"]
            return '{"tool":"file_read","args":{"path":"."},"thought_summary":"Inspect before patching."}'

    async def run() -> None:
        model = CapturingModel()
        engine = make_engine(tmp_path)
        engine.model = model  # type: ignore[assignment]
        created = engine.store.create_run("Implement change", "Edit recommendation", str(tmp_path), ["Implement change"])
        created.state.step_count = 1

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "file_read"
        assert "Ornith action context" in model.user_prompt
        assert "selected_proof=patch_propose:edit" in model.user_prompt
        assert "Acceptance proof recommendations" in model.user_prompt
        assert "patch_propose" in model.user_prompt
        assert created.state.action_context.selected_tool == "file_read"
        assert created.state.action_context.selected_label == "edit"

    asyncio.run(run())


def test_completion_audit_blocks_open_criteria_and_pending_approval(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Audit completion", "Audit", str(tmp_path), ["Tests pass"])
    engine.store.create_approval(run.id, "shell", {"command": "npm install -g demo"}, "Global install.")

    audit = engine.get_completion_audit(run.id)

    assert not audit["can_finish"]
    assert audit["acceptance_open"] == 1
    assert audit["pending_approvals"] == 1
    assert {issue["id"] for issue in audit["issues"]} >= {"acceptance_not_verified", "pending_approvals"}


def test_completion_audit_flags_stale_verified_evidence_after_edit(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Audit stale evidence", "Stale audit", str(tmp_path), ["Tests pass"])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Tests pass",
            status="verified",
            required_labels=["verification"],
            matched_labels=["verification"],
            label_checked_at={"verification": "2026-06-27T08:00:00+00:00"},
            evidence=["run_tests: All tests passed."],
            last_tool="run_tests",
            last_checked="2026-06-27T08:00:00+00:00",
        )
    ]
    run.state.tool_calls.append(
        ToolCallRecord(
            id="tool-edit",
            name="patch_apply",
            ok=True,
            summary="Applied patch.",
            created_at="2026-06-27T08:05:00+00:00",
        )
    )
    engine.store.update_run(run.id, state=run.state)

    audit = engine.get_completion_audit(run.id)

    assert not audit["can_finish"]
    assert audit["stale_evidence_count"] == 1
    assert any(issue["id"] == "stale_acceptance_evidence" for issue in audit["issues"])


def test_rerunning_verification_refreshes_stale_evidence(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Audit refreshed evidence", "Refresh audit", str(tmp_path), ["Tests pass"])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Tests pass",
            status="verified",
            required_labels=["verification"],
            matched_labels=["verification"],
            label_checked_at={"verification": "2026-06-27T08:00:00+00:00"},
            evidence=["run_tests [verification]: All tests passed."],
            last_tool="run_tests",
            last_checked="2026-06-27T08:00:00+00:00",
        )
    ]
    run.state.tool_calls.append(
        ToolCallRecord(
            id="tool-edit",
            name="patch_apply",
            ok=True,
            summary="Applied patch.",
            created_at="2026-06-27T08:05:00+00:00",
        )
    )
    refresh_result = type(
        "Result",
        (),
        {
            "ok": True,
            "kind": "run_tests",
            "summary": "All tests passed after patch.",
            "data": {"command": "python -m pytest"},
        },
    )()

    engine._update_acceptance_evidence(run.state, refresh_result)  # type: ignore[arg-type]
    engine.store.update_run(run.id, state=run.state)
    audit = engine.get_completion_audit(run.id)

    assert audit["can_finish"]
    assert audit["stale_evidence_count"] == 0


def test_completion_audit_can_make_stale_evidence_advisory(tmp_path: Path) -> None:
    engine = make_engine(tmp_path, completion_strict_stale_evidence=False)
    run = engine.store.create_run("Audit advisory stale evidence", "Advisory audit", str(tmp_path), ["Tests pass"])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Tests pass",
            status="verified",
            required_labels=["verification"],
            matched_labels=["verification"],
            label_checked_at={"verification": "2026-06-27T08:00:00+00:00"},
            evidence=["run_tests: All tests passed."],
            last_tool="run_tests",
            last_checked="2026-06-27T08:00:00+00:00",
        )
    ]
    run.state.tool_calls.append(
        ToolCallRecord(
            id="tool-edit",
            name="patch_apply",
            ok=True,
            summary="Applied patch.",
            created_at="2026-06-27T08:05:00+00:00",
        )
    )
    engine.store.update_run(run.id, state=run.state)

    audit = engine.get_completion_audit(run.id)

    assert audit["can_finish"]
    assert audit["stale_evidence_count"] == 1
    stale_issue = next(issue for issue in audit["issues"] if issue["id"] == "stale_acceptance_evidence")
    assert stale_issue["severity"] == "warning"


def test_completion_policy_controls_verification_tool_mapping(tmp_path: Path) -> None:
    engine = make_engine(tmp_path, completion_verification_tools=("custom_verify",))
    run = engine.store.create_run("Run custom checks", "Custom checks", str(tmp_path), ["Run checks pass"])
    result = type(
        "Result",
        (),
        {
            "ok": True,
            "kind": "custom_verify",
            "summary": "Custom checks passed.",
            "data": {"command": "custom check"},
        },
    )()

    engine._update_acceptance_evidence(run.state, result)  # type: ignore[arg-type]

    assert run.state.acceptance_evidence[0].status == "verified"
    assert run.state.acceptance_evidence[0].last_tool == "custom_verify"


def test_context_pressure_triggers_drift(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Build long loop", "Loop", str(tmp_path), [])
    run.state.context_budget = ContextBudget(target_tokens=1000, estimated_tokens=2000, pressure="high")

    assert "Context budget pressure" in engine._detect_drift(run, run.state)


def test_run_health_flags_recovery_and_context_pressure(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Recover run", "Health", str(tmp_path), [])
    run.state.context_budget = ContextBudget(target_tokens=1000, estimated_tokens=2000, pressure="high")
    run.state.failure_counts["shell"] = 3
    run.state.recovery_plan = RecoveryPlan(
        id="recovery-1",
        status="active",
        failure_kind="timeout",
        tool="shell",
        summary="Repeated shell timeout.",
        next_action="Run narrower diagnostic.",
    )

    health = engine._build_run_health(run, run.state)

    assert health.level == "blocked"
    assert health.recommended_action == "recover"
    assert health.score >= 70
    assert {"context_pressure_high", "repeated_failures", "active_recovery"} <= {signal.id for signal in health.signals}


def test_run_health_recommends_verify_for_stale_evidence(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Refresh stale proof", "Health stale", str(tmp_path), ["Tests pass"])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Tests pass",
            status="verified",
            required_labels=["verification"],
            matched_labels=["verification"],
            label_checked_at={"verification": "2026-06-27T08:00:00+00:00"},
            evidence=["run_tests [verification]: All tests passed."],
            last_tool="run_tests",
            last_checked="2026-06-27T08:00:00+00:00",
        )
    ]
    run.state.tool_calls.append(
        ToolCallRecord(
            id="tool-edit",
            name="patch_apply",
            ok=True,
            summary="Applied patch.",
            created_at="2026-06-27T08:05:00+00:00",
        )
    )

    health = engine._build_run_health(run, run.state)

    assert health.recommended_action == "verify"
    assert any(signal.id == "stale_acceptance_evidence" for signal in health.signals)


def test_run_health_uses_recommendation_trace_failures(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Trace health", "Health traces", str(tmp_path), ["Tests pass"])
    run.state.acceptance_recommendation_traces = [
        AcceptanceRecommendationTrace(
            id="rec-trace-1",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            status="failed",
            result_ok=False,
            result_summary="Tests failed.",
        )
    ]

    health = engine._build_run_health(run, run.state)

    assert health.level == "watch"
    assert any(signal.id == "recommendation_trace_failures" for signal in health.signals)


def test_run_health_recovers_on_repeated_readiness_proof_failures(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Trace readiness failures", "Health readiness failures", str(tmp_path), ["Tests pass"])
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
            status="failed",
            result_ok=False,
            result_summary="Tests failed once.",
        ),
        AcceptanceRecommendationTrace(
            id="rec-trace-2",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            source="harness",
            status="failed",
            result_ok=False,
            result_summary="Tests failed twice.",
        ),
    ]
    run = engine.store.update_run(run.id, state=run.state)
    for trace in run.state.acceptance_recommendation_traces:
        engine.store.append_event(
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
                    "recommendation_trace_id": trace.id,
                    "recommendation_id": trace.recommendation_id,
                    "recommendation_label": trace.label,
                    "recommendation_criterion_id": trace.criterion_id,
                },
            },
        )

    run = engine.store.get_run(run.id)
    health = engine._build_run_health(run, run.state)
    simulation = engine._build_policy_simulation(run, run.state)

    assert health.recommended_action == "recover"
    assert any(signal.id == "readiness_proof_failures" for signal in health.signals)
    assert simulation.policy_action == "recover"
    assert not simulation.safe_to_resume


def test_run_health_recovers_on_repeated_unresolved_readiness_proof(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Trace unresolved readiness", "Health readiness unresolved", str(tmp_path), ["Tests pass"])
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
            status="executed",
            result_ok=True,
            result_summary="Command ran but criterion stayed open.",
            evidence_status="open",
        ),
        AcceptanceRecommendationTrace(
            id="rec-trace-2",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            source="harness",
            status="executed",
            result_ok=True,
            result_summary="Command ran again but criterion stayed open.",
            evidence_status="open",
        ),
    ]
    run = engine.store.update_run(run.id, state=run.state)
    for trace in run.state.acceptance_recommendation_traces:
        engine.store.append_event(
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
                    "recommendation_trace_id": trace.id,
                    "recommendation_id": trace.recommendation_id,
                    "recommendation_label": trace.label,
                    "recommendation_criterion_id": trace.criterion_id,
                },
            },
        )

    run = engine.store.get_run(run.id)
    health = engine._build_run_health(run, run.state)
    simulation = engine._build_policy_simulation(run, run.state)

    assert health.recommended_action == "recover"
    assert any(signal.id == "readiness_proof_unresolved_loop" for signal in health.signals)
    assert simulation.policy_action == "recover"
    assert not simulation.safe_to_resume


def test_run_health_recovers_on_repeated_objective_readiness_proof_failures(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth harness verification",
        "Objective proof health",
        str(tmp_path),
        [],
    )
    run.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-proof-1",
            item_id="verification_critic_loop",
            tool="run_tests",
            evidence_label="verification",
            outcome="failed",
            ok=False,
            summary="Tests failed once.",
        ),
        ObjectiveReadinessProofOutcome(
            id="obj-proof-2",
            item_id="verification_critic_loop",
            tool="run_tests",
            evidence_label="verification",
            outcome="failed",
            ok=False,
            summary="Tests failed twice.",
        ),
    ]
    run = engine.store.update_run(run.id, state=run.state)

    health = engine._build_run_health(run, run.state)
    simulation = engine._build_policy_simulation(run, run.state)

    assert health.recommended_action == "recover"
    assert any(signal.id == "objective_readiness_proof_failures" for signal in health.signals)
    assert any("alternate objective-readiness proof" in action for action in health.next_actions)
    assert simulation.policy_action == "recover"
    assert not simulation.safe_to_resume


def test_run_health_policy_pauses_for_context_pressure(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Pause high context", "Health policy", str(tmp_path), [])
        created.state.context_budget = ContextBudget(target_tokens=1000, estimated_tokens=2000, pressure="high")

        status = await engine._apply_run_health_policy(created, created.state)
        updated = engine.store.get_run(created.id)

        assert status == "pause"
        assert updated.status == "paused"
        assert updated.state.run_health.recommended_action == "pause"
        assert engine.store.list_events(created.id)[-1]["kind"] == "health_policy"

    asyncio.run(run())


def test_run_health_policy_creates_readiness_recovery_plan(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Recover readiness loop", "Readiness recovery", str(tmp_path), ["Tests pass"])
        created.state.acceptance_recommendation_traces = [
            AcceptanceRecommendationTrace(
                id="rec-trace-1",
                recommendation_id="criterion-1-verification",
                criterion_id="criterion-1",
                criterion="Tests pass",
                label="verification",
                recommended_tool="run_tests",
                selected_tool="run_tests",
                source="harness",
                status="failed",
                result_ok=False,
                result_summary="Tests failed once.",
            ),
            AcceptanceRecommendationTrace(
                id="rec-trace-2",
                recommendation_id="criterion-1-verification",
                criterion_id="criterion-1",
                criterion="Tests pass",
                label="verification",
                recommended_tool="run_tests",
                selected_tool="run_tests",
                source="harness",
                status="failed",
                result_ok=False,
                result_summary="Tests failed twice.",
            ),
        ]
        created = engine.store.update_run(created.id, status="queued", state=created.state)
        for trace in created.state.acceptance_recommendation_traces:
            engine.store.append_event(
                created.id,
                "action_readiness_tool",
                "needs_proof: Run tests.",
                {
                    "action_readiness": {
                        "run_id": created.id,
                        "status": "needs_proof",
                        "ready_to_act": True,
                        "suggested_tool": "run_tests",
                        "suggested_label": "verification",
                        "recommended_action": "Run the smallest relevant verification command.",
                    },
                    "selected_action": {
                        "tool": "run_tests",
                        "recommendation_trace_id": trace.id,
                        "recommendation_id": trace.recommendation_id,
                        "recommendation_label": trace.label,
                        "recommendation_criterion_id": trace.criterion_id,
                    },
                },
            )
        created = engine.store.get_run(created.id)

        status = await engine._apply_run_health_policy(created, created.state)
        updated = engine.store.get_run(created.id)

        assert status == "recover"
        assert updated.status == "paused"
        assert updated.state.recovery_plan.status == "active"
        assert updated.state.recovery_plan.trigger == "readiness_decision_loop"
        assert updated.state.recovery_plan.failure_kind == "readiness_proof_failure"
        assert updated.state.recovery_plan.tool == "run_tests"
        assert updated.state.recovery_plan.attempts == 2
        assert updated.state.current_plan == updated.state.recovery_plan.steps
        assert "single failing test" in " ".join(updated.state.recovery_plan.steps)
        assert updated.state.next_step.startswith("Review the readiness decision ledger")
        report = engine.get_recovery_decisions(created.id)
        assert report["active_recovery"] is True
        assert report["latest_decision"]["trigger"] == "readiness_decision_loop"
        assert report["latest_decision"]["proof_label"] == "verification"
        assert "single failing test" in report["latest_decision"]["selected_strategy"]

    asyncio.run(run())


def test_run_health_policy_creates_objective_readiness_recovery_plan(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Improve AgentOrinth harness verification",
            "Objective readiness recovery",
            str(tmp_path),
            [],
        )
        created.state.objective_readiness_proof_outcomes = [
            ObjectiveReadinessProofOutcome(
                id="obj-proof-1",
                item_id="verification_critic_loop",
                tool="run_tests",
                evidence_label="verification",
                outcome="failed",
                ok=False,
                summary="Tests failed once.",
            ),
            ObjectiveReadinessProofOutcome(
                id="obj-proof-2",
                item_id="verification_critic_loop",
                tool="run_tests",
                evidence_label="verification",
                outcome="failed",
                ok=False,
                summary="Tests failed twice.",
            ),
        ]
        created = engine.store.update_run(created.id, status="queued", state=created.state)

        status = await engine._apply_run_health_policy(created, created.state)
        updated = engine.store.get_run(created.id)

        assert status == "recover"
        assert updated.status == "paused"
        assert updated.state.recovery_plan.status == "active"
        assert updated.state.recovery_plan.trigger == "objective_readiness_proof_loop"
        assert updated.state.recovery_plan.failure_kind == "objective_readiness_proof_failure"
        assert updated.state.recovery_plan.tool == "run_tests"
        assert updated.state.recovery_plan.attempts == 2
        assert updated.state.current_plan == updated.state.recovery_plan.steps
        assert "single test" in " ".join(updated.state.recovery_plan.steps)
        assert updated.state.next_step.startswith("Review the objective-readiness proof outcomes")
        report = engine.get_recovery_decisions(created.id)
        assert report["active_recovery"] is True
        assert report["latest_decision"]["trigger"] == "objective_readiness_proof_loop"
        assert report["latest_decision"]["proof_label"] == "verification"
        assert report["latest_decision"]["criterion_id"] == "verification_critic_loop"
        assert "single test" in report["latest_decision"]["selected_strategy"]

    asyncio.run(run())


def test_run_health_policy_routes_open_evidence_to_verification(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Verify acceptance", "Health verify", str(tmp_path), ["Tests pass"])
        created.state.milestone = "decide"

        status = await engine._apply_run_health_policy(created, created.state)
        updated = engine.store.get_run(created.id)

        assert status == "verify"
        assert updated.status == "queued"
        assert updated.state.milestone == "act"
        assert updated.state.run_health.recommended_action == "verify"
        assert engine.store.list_events(created.id)[-1]["kind"] == "health_verify"

    asyncio.run(run())


def test_policy_simulation_previews_verification_route(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run("Verify acceptance", "Policy preview", str(tmp_path), ["Tests pass"])
    created.state.milestone = "decide"
    engine._ensure_acceptance_evidence(created.state)

    simulation = engine._build_policy_simulation(created, created.state)

    assert simulation.policy_action == "verify"
    assert simulation.predicted_status == "running"
    assert simulation.predicted_milestone == "act"
    assert simulation.safe_to_resume
    assert simulation.recommended_tool == "run_tests"
    assert simulation.recommended_label == "verification"
    assert "smallest missing acceptance proof" in simulation.effects[0]


def test_resume_run_records_accepted_preflight_snapshot(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Resume with proof", "Resume preflight", str(tmp_path), ["Tests pass"])
        engine.store.update_run(created.id, status="paused", state=created.state)

        updated = await engine.resume_run(created.id)
        engine._cancel_task(created.id)
        events = engine.store.list_events(created.id)
        preflight = next(event for event in events if event["kind"] == "resume_preflight")

        assert updated.status == "queued"
        assert preflight["data"]["accepted"] is True
        assert preflight["data"]["source"] == "manual"
        assert preflight["data"]["policy_simulation"]["policy_action"] == "verify"
        assert preflight["data"]["policy_simulation"]["recommended_tool"] == "run_tests"
        assert any(event["kind"] == "control" and "manual preflight" in event["message"] for event in events)
        report = engine.get_resume_decisions(created.id)
        assert report["accepted_count"] == 1
        assert report["latest_accepted"]["source"] == "manual"
        assert report["current_matches_last_accepted"] is True

    asyncio.run(run())


def test_resume_refreshes_stale_report_integrity_before_preflight(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Refresh stale handoff", "Integrity preflight", str(tmp_path), [])
        created.state.goal = "Sharper active goal before resume"
        created.state.handoff_summary.current_objective = "Old active goal"
        engine.store.update_run(created.id, status="paused", state=created.state)

        updated = await engine.resume_run(created.id)
        engine._cancel_task(created.id)
        refreshed = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)

        assert updated.status == "queued"
        assert refreshed.state.handoff_summary.current_objective == "Sharper active goal before resume"
        assert refreshed.state.handoff_summary.report_integrity.status == "ok"
        assert any(event["kind"] == "report_integrity_refresh" for event in events)
        assert any(event["kind"] == "resume_preflight" for event in events)

    asyncio.run(run())


def test_resume_run_blocks_unsafe_preflight(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Blocked resume", "Blocked preflight", str(tmp_path), [])
        created.state.blockers.append("Need user decision.")
        engine.store.update_run(created.id, status="blocked", state=created.state)

        updated = await engine.resume_run(created.id)
        events = engine.store.list_events(created.id)
        preflight = next(event for event in events if event["kind"] == "resume_preflight_blocked")

        assert updated.status == "blocked"
        assert preflight["data"]["accepted"] is False
        assert preflight["data"]["policy_simulation"]["policy_action"] == "ask_user"
        assert not any(event["kind"] == "control" and "Run resumed" in event["message"] for event in events)
        report = engine.get_resume_decisions(created.id)
        assert report["blocked_count"] == 1
        assert report["latest_blocked"]["policy_action"] == "ask_user"
        assert "blocked" in report["recommended_action"].lower()

    asyncio.run(run())


def test_act_preflight_reorients_when_resume_policy_diverges(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Verify acceptance", "Act preflight", str(tmp_path), ["Tests pass"])
        accepted_simulation = PolicySimulationReport(
            run_id=created.id,
            current_status="paused",
            current_milestone="act",
            predicted_status="running",
            predicted_milestone="act",
            policy_action="continue",
            safe_to_resume=True,
            auto_resume_eligible=True,
            summary="Would continue -> running/act.",
        )
        decision = engine.store.append_event(
            created.id,
            "resume_preflight",
            "Resume preflight accepted for manual.",
            {
                "source": "manual",
                "accepted": True,
                "reason": "Accepted older continue snapshot.",
                "policy_simulation": accepted_simulation.model_dump(),
            },
        )
        created.state.milestone = "act"
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)

        assert updated.state.milestone == "orient"
        assert updated.state.act_preflight_checked_decision_id == decision["id"]
        assert any(event["kind"] == "act_preflight_reorient" for event in events)
        assert not updated.state.tool_calls
        assert "differs from the latest accepted resume snapshot" in updated.state.latest_summary

    asyncio.run(run())


def test_action_readiness_recommends_acceptance_proof(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run("Verify acceptance", "Readiness proof", str(tmp_path), ["Tests pass"])
    created.state.milestone = "act"
    engine._ensure_acceptance_evidence(created.state)
    created = engine.store.update_run(created.id, status="queued", state=created.state)

    report = engine._build_action_readiness(created, created.state)

    assert report.status == "needs_proof"
    assert report.ready_to_act
    assert report.suggested_tool == "run_tests"
    assert report.suggested_label == "verification"
    assert report.issues[0].id == "acceptance_proof_recommended"

def test_action_readiness_prioritizes_missing_browser_source_evidence(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Verify dashboard and tests",
        "Readiness source proof",
        str(tmp_path),
        ["Dashboard starts and tests pass"],
    )
    created.state.milestone = "act"
    engine._ensure_acceptance_evidence(created.state)
    created = engine.store.update_run(created.id, status="queued", state=created.state)

    report = engine._build_action_readiness(created, created.state)

    assert report.status == "needs_proof"
    assert report.ready_to_act
    assert report.suggested_tool == "browser_screenshot"
    assert report.suggested_label == "browser"
    assert report.issues[0].id == "source_evidence_missing"
    assert created.state.source_evidence.missing_labels == ["browser"]


def test_choose_action_uses_ranked_source_evidence_recommendation_before_model(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Verify dashboard and tests",
            "Ranked source action",
            str(tmp_path),
            ["Dashboard starts and tests pass"],
        )
        created.state.step_count = 1
        engine._ensure_acceptance_evidence(created.state)
        engine._build_action_readiness(created, created.state)

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "browser_screenshot"
        assert action["args"]["url"] == "http://127.0.0.1:5173"
        assert action["recommendation_label"] == "browser"
        assert created.state.action_context.selected_tool == "browser_screenshot"
        assert created.state.action_context.selected_label == "browser"
        assert created.state.action_context.missing_source_labels == ["browser"]
        assert "source_evidence missing=browser" in created.state.action_context.compact_prompt
        assert created.state.acceptance_recommendation_traces[0].label == "browser"
        assert "acceptance recommendation" in created.state.model_interactions[-1].summary

    asyncio.run(run())

def test_action_readiness_blocks_active_tool_state(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run("Wait for approval", "Readiness blocked", str(tmp_path), [])
    created.state.milestone = "act"
    created.state.active_tool = "workspace_promote"
    created = engine.store.update_run(created.id, status="waiting_approval", state=created.state)

    report = engine._build_action_readiness(created, created.state)

    assert report.status == "waiting_approval"
    assert not report.ready_to_act
    assert report.issues[0].id == "active_tool_or_approval"


def test_act_milestone_uses_action_readiness_proof_tool_before_model(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Verify acceptance", "Readiness act", str(tmp_path), ["Tests pass"])
        created.state.milestone = "act"
        engine.store.update_run(created.id, status="queued", state=created.state)
        captured: list[dict] = []

        async def fail_choose(_run, _memory_text):  # noqa: ANN001
            raise AssertionError("model action selection should not run for action-readiness proof")

        async def fake_execute(_run, action):  # noqa: ANN001
            captured.append(action)
            return ToolResult(True, action["tool"], "All tests passed.", action.get("args", {}))

        engine._choose_action = fail_choose  # type: ignore[method-assign]
        engine._execute_action = fake_execute  # type: ignore[method-assign]

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)

        assert captured[0]["tool"] == "run_tests"
        assert updated.state.milestone == "verify"
        assert updated.state.acceptance_evidence[0].status == "verified"
        assert any(event["kind"] == "action_readiness_tool" for event in engine.store.list_events(created.id))

    asyncio.run(run())


def test_action_readiness_decision_report_marks_readiness_tool_satisfied(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Verify acceptance", "Readiness decision", str(tmp_path), ["Tests pass"])
        created.state.milestone = "act"
        engine.store.update_run(created.id, status="queued", state=created.state)

        async def fail_choose(_run, _memory_text):  # noqa: ANN001
            raise AssertionError("readiness proof should bypass model action selection")

        async def fake_execute(_run, action):  # noqa: ANN001
            return ToolResult(True, action["tool"], "All tests passed.", action.get("args", {}))

        engine._choose_action = fail_choose  # type: ignore[method-assign]
        engine._execute_action = fake_execute  # type: ignore[method-assign]

        await engine._run_one_milestone(created.id)

        report = engine.get_action_readiness_decisions(created.id)

        assert report["decision_count"] == 1
        assert report["satisfied_count"] == 1
        assert report["harness_selected_count"] == 1
        assert report["latest_tool_decision"]["status"] == "satisfied"
        assert report["latest_tool_decision"]["selected_tool"] == "run_tests"
        assert report["latest_tool_decision"]["label"] == "verification"
        assert report["latest_tool_decision"]["evidence_status"] == "verified"
        assert "satisfied" in report["summary"]

    asyncio.run(run())


def test_act_milestone_pauses_when_action_readiness_is_blocked(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Blocked act", "Readiness blocked act", str(tmp_path), [])
        created.state.milestone = "act"
        created.state.blockers.append("Need user decision.")
        engine.store.update_run(created.id, status="queued", state=created.state)

        async def fail_execute(_run, _action):  # noqa: ANN001
            raise AssertionError("tool execution should not run when readiness is blocked")

        engine._execute_action = fail_execute  # type: ignore[method-assign]

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)

        assert updated.status == "paused"
        assert updated.state.milestone == "act"
        assert updated.state.latest_summary.startswith("blocked:")
        assert any(event["kind"] == "action_readiness_policy" for event in engine.store.list_events(created.id))
        report = engine.get_action_readiness_decisions(created.id)
        assert report["blocked_count"] == 1
        assert report["latest_policy_decision"]["status"] == "blocked"
        assert report["latest_policy_decision"]["source"] == "policy"

    asyncio.run(run())


def test_act_milestone_replans_when_action_readiness_needs_replan(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Replan act", "Readiness replan act", str(tmp_path), [])
        created.state.milestone = "act"
        created.state.task_graph[0].status = "blocked"
        created.state.current_plan = ["Old blocked plan."]
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)

        assert updated.state.milestone == "plan"
        assert updated.state.current_plan == []
        assert updated.state.latest_summary.startswith("needs_replan:")
        assert any(event["kind"] == "action_readiness_replan" for event in engine.store.list_events(created.id))

    asyncio.run(run())


def test_run_health_policy_pauses_for_active_recovery(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Recover via health", "Health recover", str(tmp_path), [])
        created.state.recovery_plan = RecoveryPlan(
            id="recovery-1",
            status="active",
            failure_kind="timeout",
            tool="shell",
            summary="Repeated shell timeout.",
            next_action="Run narrower diagnostic.",
            steps=["Run narrower diagnostic."],
        )
        created.state.failure_counts["shell"] = 3

        status = await engine._apply_run_health_policy(created, created.state)
        updated = engine.store.get_run(created.id)

        assert status == "recover"
        assert updated.status == "paused"
        assert updated.state.next_step == "Run narrower diagnostic."
        assert updated.state.run_health.recommended_action == "recover"
        autonomy = engine.get_autonomy_decisions(created.id)
        assert autonomy["latest_decision"]["decision"] == "recover"
        assert autonomy["latest_decision"]["source"] == "run_health"
        assert autonomy["recover_count"] == 1
        assert "Repeated shell timeout" in autonomy["latest_decision"]["reason"]

    asyncio.run(run())


def test_goal_proposal_creates_confirmation_approval(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Original goal", "Goal run", str(tmp_path), [])

        updated = await engine.propose_goal(created.id, "Sharper active goal", "Long run learned more context.")
        approvals = engine.store.list_approvals(created.id)

        assert updated.status == "waiting_goal_confirmation"
        assert updated.state.proposed_goal == "Sharper active goal"
        assert approvals[0]["action_kind"] == "goal_update"
        assert updated.state.goal_evolution.pending_count == 1
        assert updated.state.goal_evolution.latest_decision.source == "manual"
        assert updated.state.goal_evolution.latest_decision.approval_id == approvals[0]["id"]
        assert updated.state.handoff_summary.goal_evolution.pending_count == 1

    asyncio.run(run())


def test_goal_review_asks_model_then_waits_for_confirmation(tmp_path: Path) -> None:
    class GoalReviewModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            return (
                '{"should_update": true, "proposed_goal": "Sharper active goal", '
                '"reason": "Long run learned more context."}'
            )

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = GoalReviewModel()  # type: ignore[assignment]
        created = engine.store.create_run("Original goal", "Goal review", str(tmp_path), [])

        updated = await engine.review_goal(created.id)
        approvals = engine.store.list_approvals(created.id)

        assert updated.status == "waiting_goal_confirmation"
        assert updated.state.goal == "Original goal"
        assert updated.state.proposed_goal == "Sharper active goal"
        assert updated.state.model_interactions[-1].kind == "goal"
        assert approvals[0]["action_kind"] == "goal_update"
        assert approvals[0]["payload"]["proposed_goal"] == "Sharper active goal"
        assert updated.state.goal_evolution.pending_count == 1
        assert updated.state.goal_evolution.latest_decision.source == "manual_review"
        assert updated.state.goal_evolution.latest_decision.proposed_goal == "Sharper active goal"

    asyncio.run(run())


def test_goal_review_records_unchanged_decision(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Original goal", "Goal unchanged", str(tmp_path), [])

        updated = await engine.review_goal(created.id)

        assert updated.status == "queued"
        assert updated.state.proposed_goal is None
        assert updated.state.goal_evolution.unchanged_count == 1
        assert updated.state.goal_evolution.latest_decision.status == "unchanged"
        assert updated.state.goal_evolution.latest_decision.source == "manual_review"
        assert updated.state.handoff_summary.goal_evolution.unchanged_count == 1

    asyncio.run(run())


def test_goal_approval_resolves_goal_evolution_ledger(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Original goal", "Goal approval", str(tmp_path), [])
        await engine.propose_goal(created.id, "Sharper active goal", "Long run learned more context.")
        approval = engine.store.list_approvals(created.id)[0]

        await engine.approve_action(created.id, approval["id"])
        updated = engine.store.get_run(created.id)

        assert updated.state.goal == "Sharper active goal"
        assert updated.state.proposed_goal is None
        assert updated.state.goal_evolution.accepted_count == 1
        assert updated.state.goal_evolution.pending_count == 0
        assert updated.state.goal_evolution.latest_decision.status == "accepted"
        assert updated.state.handoff_summary.goal_evolution.accepted_count == 1

    asyncio.run(run())


def test_failure_records_are_classified(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Classify failures", "Failures", str(tmp_path), [])
    result = type(
        "Result",
        (),
        {
            "ok": False,
            "kind": "shell",
            "summary": "Command timed out after 1s.",
            "data": {},
            "needs_approval": False,
            "web_sources": [],
            "desktop_snapshots": [],
            "patch_proposals": [],
        },
    )()

    async def record() -> None:
        await engine._record_tool_result(run.id, result)  # type: ignore[arg-type]

    asyncio.run(record())
    updated = engine.store.get_run(run.id)

    assert updated.state.failure_records[0].kind == "timeout"
    assert "Reduce command scope" in updated.state.failure_records[0].recovery_hint

def test_failed_action_queues_post_action_retry(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Recover failed test", "Post retry", str(tmp_path), ["Tests pass"])
        action = {"tool": "run_tests", "args": {"command": "python -m pytest"}, "thought_summary": "Run tests."}

        await engine._record_tool_result(
            created.id,
            ToolResult(False, "run_tests", "Tests failed.", {"command": "python -m pytest"}),
            action=action,
        )
        updated = engine.store.get_run(created.id)
        decision = updated.state.post_action_retries.latest_decision

        assert updated.state.post_action_retries.decision_count == 1
        assert updated.state.post_action_retries.pending_count == 1
        assert decision.status == "pending"
        assert decision.trigger_tool == "run_tests"
        assert decision.selected_tool == "shell"
        assert decision.command_hint == "python -m compileall backend\\app"
        assert updated.state.active_tool == ""

    asyncio.run(run())


def test_choose_action_uses_pending_post_action_retry(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Recover failed test", "Post retry action", str(tmp_path), ["Tests pass"])
        await engine._record_tool_result(
            created.id,
            ToolResult(False, "run_tests", "Tests failed.", {"command": "python -m pytest"}),
            action={"tool": "run_tests", "args": {"command": "python -m pytest"}},
        )
        updated = engine.store.get_run(created.id)
        updated.state.step_count = 1

        action = await engine._choose_action(updated, "tiny context")

        assert action["tool"] == "shell"
        assert action["args"]["command"] == "python -m compileall backend\\app"
        assert action["post_action_retry_id"]
        assert updated.state.post_action_retries.latest_decision.status == "selected"
        assert updated.state.action_context.selected_tool == "shell"
        assert "post-action retry" in updated.state.model_interactions[-1].summary

    asyncio.run(run())


def test_post_action_retry_resolves_from_retry_result(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Recover failed test", "Post retry resolved", str(tmp_path), ["Tests pass"])
        await engine._record_tool_result(
            created.id,
            ToolResult(False, "run_tests", "Tests failed.", {"command": "python -m pytest"}),
            action={"tool": "run_tests", "args": {"command": "python -m pytest"}},
        )
        updated = engine.store.get_run(created.id)
        action = await engine._choose_action(updated, "tiny context")
        engine.store.update_run(updated.id, state=updated.state)

        await engine._record_tool_result(
            created.id,
            ToolResult(True, "shell", "Compile check passed.", {"command": action["args"]["command"]}),
            action=action,
        )
        resolved = engine.store.get_run(created.id).state.post_action_retries

        assert resolved.resolved_count == 1
        assert resolved.pending_count == 0
        assert resolved.latest_decision.status == "resolved"
        assert resolved.latest_decision.resolution_tool == "shell"
        assert resolved.latest_decision.resolution_ok is True

    asyncio.run(run())


def test_act_milestone_stays_in_act_for_post_action_retry(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Recover failed test", "Post retry loop", str(tmp_path), ["Tests pass"])
        created.state.milestone = "act"
        engine.store.update_run(created.id, status="queued", state=created.state)

        async def fake_execute(_run, action):  # noqa: ANN001
            return ToolResult(False, action["tool"], "Tests failed.", {"command": action.get("args", {}).get("command", "")})

        engine._execute_action = fake_execute  # type: ignore[method-assign]

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)

        assert updated.state.milestone == "act"
        assert updated.state.post_action_retries.pending_count == 1
        assert updated.state.post_action_retries.latest_decision.selected_tool == "shell"
        assert updated.state.current_plan[0].startswith("Run a focused compile")
        assert any(event["kind"] == "post_action_retry" for event in events)

    asyncio.run(run())

def test_repeated_failure_activates_recovery_plan(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Recover from repeated failures", "Recovery", str(tmp_path), [])

    def result(summary: str = "Command timed out after 1s."):  # noqa: ANN202
        return type(
            "Result",
            (),
            {
                "ok": False,
                "kind": "shell",
                "summary": summary,
                "data": {},
                "needs_approval": False,
                "web_sources": [],
                "desktop_snapshots": [],
                "patch_proposals": [],
            },
        )()

    async def record() -> None:
        await engine._record_tool_result(run.id, result())  # type: ignore[arg-type]
        await engine._record_tool_result(run.id, result())  # type: ignore[arg-type]
        await engine._record_tool_result(run.id, result())  # type: ignore[arg-type]

    asyncio.run(record())
    updated = engine.store.get_run(run.id)

    assert updated.state.recovery_plan.status == "active"
    assert updated.state.recovery_plan.failure_kind == "timeout"
    assert updated.state.recovery_plan.attempts == 3
    assert updated.state.current_plan == updated.state.recovery_plan.steps
    assert updated.state.milestone == "orient"
    assert "Reduce command scope" in updated.state.next_step


def test_success_resolves_active_recovery_plan(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Resolve recovery", "Recovery resolved", str(tmp_path), [])
    run.state.recovery_plan.status = "active"
    run.state.recovery_plan.summary = "Recover from shell failure."
    run.state.recovery_plan.steps = ["Run narrower command."]
    engine.store.update_run(run.id, state=run.state)
    result = type(
        "Result",
        (),
        {
            "ok": True,
            "kind": "shell",
            "summary": "exit 0: echo ok",
            "data": {"command": "echo ok"},
            "needs_approval": False,
            "web_sources": [],
            "desktop_snapshots": [],
            "patch_proposals": [],
        },
    )()

    async def record() -> None:
        await engine._record_tool_result(run.id, result)  # type: ignore[arg-type]

    asyncio.run(record())
    updated = engine.store.get_run(run.id)

    assert updated.state.recovery_plan.status == "resolved"
    assert updated.state.recovery_history[-1].status == "resolved"
    assert "Resolved recovery plan" in updated.state.facts_learned[-1]


def test_resume_recovery_queues_run_and_clears_retry_counter(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Resume recovery", "Recovery resume", str(tmp_path), [])
        created.state.recovery_plan.status = "active"
        created.state.recovery_plan.tool = "shell"
        created.state.recovery_plan.failure_kind = "timeout"
        created.state.recovery_plan.summary = "Repeated shell timeout."
        created.state.recovery_plan.next_action = "Reduce command scope."
        created.state.recovery_plan.steps = ["Reduce command scope.", "Run narrower diagnostic."]
        created.state.failure_counts["shell"] = 3
        engine.store.update_run(created.id, status="paused", state=created.state)

        updated = await engine.resume_recovery(created.id)
        engine._cancel_task(created.id)
        events = engine.store.list_events(created.id)
        preflight = next(event for event in events if event["kind"] == "resume_preflight")

        assert updated.status == "queued"
        assert "shell" not in updated.state.failure_counts
        assert updated.state.milestone == "orient"
        assert updated.state.current_plan == ["Reduce command scope.", "Run narrower diagnostic."]
        assert preflight["data"]["source"] == "recovery"
        assert preflight["data"]["policy_simulation"]["policy_action"] == "recover"
        assert "Explicit recovery resume" in preflight["data"]["reason"]

    asyncio.run(run())


def test_replan_recovery_supersedes_active_plan(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Replan recovery", "Recovery replan", str(tmp_path), [])
        created.state.recovery_plan.id = "recovery-old"
        created.state.recovery_plan.status = "active"
        created.state.recovery_plan.tool = "shell"
        created.state.recovery_plan.failure_kind = "timeout"
        created.state.recovery_plan.summary = "Repeated shell timeout."
        created.state.recovery_plan.next_action = "Reduce command scope."
        created.state.recovery_plan.steps = ["Reduce command scope."]
        created.state.recovery_plan.attempts = 3
        engine.store.update_run(created.id, status="paused", state=created.state)

        updated = await engine.replan_recovery(created.id)

        assert updated.status == "paused"
        assert updated.state.recovery_plan.status == "active"
        assert updated.state.recovery_plan.id != "recovery-old"
        assert updated.state.recovery_history[-1].status == "superseded"
        assert updated.state.current_plan[0] == "Review the latest replay export and handoff before retrying."

    asyncio.run(run())


def test_replan_recovery_uses_readiness_decision_strategy(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Replan readiness recovery", "Readiness replan", str(tmp_path), ["Tests pass"])
        created.state.recovery_plan = RecoveryPlan(
            id="recovery-readiness",
            status="active",
            trigger="readiness_decision_loop",
            failure_kind="readiness_proof_failure",
            tool="run_tests",
            attempts=2,
            summary="Readiness proof loop for verification via run_tests.",
            next_action="Review readiness decisions.",
            steps=["Review readiness decisions."],
        )
        created.state.acceptance_recommendation_traces = [
            AcceptanceRecommendationTrace(
                id="rec-trace-1",
                recommendation_id="criterion-1-verification",
                criterion_id="criterion-1",
                criterion="Tests pass",
                label="verification",
                recommended_tool="run_tests",
                selected_tool="run_tests",
                source="harness",
                status="failed",
                result_ok=False,
                result_summary="Tests failed once.",
            ),
            AcceptanceRecommendationTrace(
                id="rec-trace-2",
                recommendation_id="criterion-1-verification",
                criterion_id="criterion-1",
                criterion="Tests pass",
                label="verification",
                recommended_tool="run_tests",
                selected_tool="run_tests",
                source="harness",
                status="failed",
                result_ok=False,
                result_summary="Tests failed twice.",
            ),
        ]
        created = engine.store.update_run(created.id, status="paused", state=created.state)
        for trace in created.state.acceptance_recommendation_traces:
            engine.store.append_event(
                created.id,
                "action_readiness_tool",
                "needs_proof: Run tests.",
                {
                    "action_readiness": {
                        "run_id": created.id,
                        "status": "needs_proof",
                        "ready_to_act": True,
                        "suggested_tool": "run_tests",
                        "suggested_label": "verification",
                        "recommended_action": "Run the smallest relevant verification command.",
                    },
                    "selected_action": {
                        "tool": "run_tests",
                        "recommendation_trace_id": trace.id,
                        "recommendation_id": trace.recommendation_id,
                        "recommendation_label": trace.label,
                        "recommendation_criterion_id": trace.criterion_id,
                    },
                },
            )
        refreshed = engine.store.get_run(created.id)
        engine._build_action_readiness_decision_report(refreshed, refreshed.state)
        engine.store.update_run(refreshed.id, state=refreshed.state)

        updated = await engine.replan_recovery(created.id)

        assert updated.state.recovery_plan.status == "active"
        assert updated.state.recovery_plan.trigger == "manual_replan"
        assert "Replanned readiness recovery" in updated.state.recovery_plan.summary
        assert "single failing test" in " ".join(updated.state.recovery_plan.steps)
        assert updated.state.recovery_history[-1].trigger == "readiness_decision_loop"

    asyncio.run(run())


def test_recovery_decision_report_marks_readiness_recovery_resolved_by_evidence(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Resolve readiness recovery", "Recovery decision", str(tmp_path), ["Tests pass"])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="criterion-1",
            criterion="Tests pass",
            status="verified",
            required_labels=["verification"],
            matched_labels=["verification"],
            label_checked_at={"verification": "2026-06-27T08:00:00+00:00"},
            evidence=["run_tests [verification]: All tests passed."],
            last_tool="run_tests",
            last_checked="2026-06-27T08:00:00+00:00",
        )
    ]
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
            status="failed",
            result_ok=False,
            result_summary="Tests failed before recovery.",
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
            next_action="Review readiness decisions.",
            steps=[
                "Review the readiness decision ledger for verification via run_tests.",
                "Run a narrower diagnostic than the repeated test command, such as a single failing test, import check, or focused lint/build target.",
                "Verify verification with the narrowest successful alternate proof.",
            ],
            created_at="2026-06-27T08:00:00+00:00",
            resolved_at="2026-06-27T08:05:00+00:00",
        )
    ]
    run = engine.store.update_run(run.id, state=run.state)
    engine.store.append_event(
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

    report = engine.get_recovery_decisions(run.id)

    assert report["resolved_count"] == 1
    assert report["latest_decision"]["resolved_by_evidence"] is True
    assert report["latest_decision"]["evidence_status"] == "verified"
    assert report["latest_decision"]["proof_label"] == "verification"
    assert "continue from the next milestone" in report["recommended_action"]


def test_verification_outcome_report_links_recovery_result_to_acceptance_evidence(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Close recovery with proof", "Verification outcome", str(tmp_path), ["Tests pass"])
        created.state.recovery_plan = RecoveryPlan(
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
            created_at="2026-06-27T08:00:00+00:00",
        )
        engine.store.update_run(created.id, state=created.state)

        await engine._record_tool_result(
            created.id,
            ToolResult(True, "run_tests", "All tests passed.", {"command": "python -m pytest"}),
        )

        report = engine.get_verification_outcomes(created.id)
        updated = engine.store.get_run(created.id)

        assert updated.state.recovery_history[-1].status == "resolved"
        assert updated.state.acceptance_evidence[0].status == "verified"
        assert report["recovery_resolved_count"] == 1
        assert report["latest_recovery_outcome"]["outcome"] == "recovery_resolved"
        assert report["latest_recovery_outcome"]["closed_recovery"] is True
        assert report["latest_recovery_outcome"]["resolved_recovery_evidence"] is True
        assert report["latest_recovery_outcome"]["evidence_status"] == "verified"
        assert "verification" in report["latest_recovery_outcome"]["labels_satisfied"]

        health = engine._build_run_health(updated, updated.state)
        audit = engine.get_completion_audit(updated.id)

        assert any(signal.id == "recovery_verification_resolved" for signal in health.signals)
        assert health.recommended_action != "recover"
        assert any(issue["id"] == "recovery_verification_resolved" for issue in audit["issues"])
        assert not any(issue["id"] == "recovery_verification_failed" for issue in audit["issues"])

    asyncio.run(run())


def test_failed_recovery_verification_forces_replan_before_completion(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Recover failing proof", "Failed recovery outcome", str(tmp_path), ["Tests pass"])
        created.state.recovery_plan = RecoveryPlan(
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
            created_at="2026-06-27T08:00:00+00:00",
        )
        engine.store.update_run(created.id, state=created.state)

        await engine._record_tool_result(
            created.id,
            ToolResult(False, "run_tests", "Tests failed during recovery.", {"command": "python -m pytest"}),
        )

        updated = engine.store.get_run(created.id)
        report = engine.get_verification_outcomes(updated.id)
        health = engine._build_run_health(updated, updated.state)
        audit = engine.get_completion_audit(updated.id)

        assert report["latest_recovery_outcome"]["outcome"] == "failed"
        assert health.recommended_action == "recover"
        assert any(signal.id == "recovery_verification_failed" for signal in health.signals)
        failed_issue = next(issue for issue in audit["issues"] if issue["id"] == "recovery_verification_failed")
        assert failed_issue["severity"] == "blocker"
        assert not audit["can_finish"]

    asyncio.run(run())


def test_startup_recovery_pauses_stale_running_active_recovery(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Recover after restart", "Startup recovery", str(tmp_path), [])
        created.state.recovery_plan.status = "active"
        created.state.recovery_plan.tool = "shell"
        created.state.recovery_plan.failure_kind = "timeout"
        created.state.recovery_plan.summary = "Repeated shell timeout."
        created.state.recovery_plan.next_action = "Run narrower diagnostic."
        created.state.recovery_plan.steps = ["Run narrower diagnostic.", "Checkpoint recovery result."]
        created.state.failure_counts["shell"] = 3
        engine_one.store.update_run(created.id, status="running", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)

        assert report["recovered"] == 1
        assert recovered.status == "paused"
        assert "shell" not in recovered.state.failure_counts
        assert recovered.state.milestone == "orient"
        assert recovered.state.current_plan == ["Run narrower diagnostic.", "Checkpoint recovery result."]
        assert "Startup restored active recovery plan" in recovered.state.facts_learned[-1]
        assert engine_two.store.list_events(created.id)[-1]["kind"] == "supervisor"

    asyncio.run(run())


def test_run_lease_acquire_heartbeat_and_release(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run("Lease lifecycle", "Lease", str(tmp_path), [])

    leased = engine._acquire_run_lease(created.id, "test_acquire")
    heartbeat = engine._heartbeat_run_lease(created.id, "test_heartbeat")
    engine._release_run_lease(created.id, "test_release")
    released = engine.store.get_run(created.id)

    assert leased.state.run_lease.status == "active"
    assert leased.state.run_lease.owner_id == engine.engine_id
    assert heartbeat is not None
    assert heartbeat.state.run_lease.heartbeat_count == 1
    assert released.state.run_lease.status == "released"
    assert released.state.run_lease.expires_at == ""
    assert released.state.run_lease.last_event == "test_release"


def test_startup_recovery_preserves_live_foreign_lease(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Live elsewhere", "Live lease", str(tmp_path), [])
        now = engine_one._utc_datetime()
        created.state.run_lease = RunLease(
            id="lease-live",
            owner_id="engine-other",
            status="active",
            acquired_at=engine_one._iso_datetime(now),
            heartbeat_at=engine_one._iso_datetime(now),
            expires_at=engine_one._iso_datetime(now + timedelta(seconds=60)),
            ttl_seconds=60,
        )
        engine_one.store.update_run(created.id, status="running", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        preserved = engine_two.store.get_run(created.id)

        assert report["live"] == 1
        assert report["runs"][0]["action"] == "live_lease_preserved"
        assert preserved.status == "running"
        assert preserved.state.run_lease.status == "active"

    asyncio.run(run())


def test_startup_recovery_repairs_expired_lease(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Expired lease", "Expired", str(tmp_path), [])
        now = engine_one._utc_datetime()
        created.state.run_lease = RunLease(
            id="lease-expired",
            owner_id="engine-old",
            status="active",
            acquired_at=engine_one._iso_datetime(now - timedelta(seconds=90)),
            heartbeat_at=engine_one._iso_datetime(now - timedelta(seconds=90)),
            expires_at=engine_one._iso_datetime(now - timedelta(seconds=30)),
            ttl_seconds=60,
        )
        engine_one.store.update_run(created.id, status="running", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)

        assert report["recovered"] == 1
        assert report["stale"] == 1
        assert recovered.status == "paused"
        assert recovered.state.run_lease.status == "stale"

    asyncio.run(run())

def test_supervisor_queues_missing_source_evidence_attention(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Verify dashboard and tests",
            "Source evidence attention",
            str(tmp_path),
            ["Dashboard starts and tests pass"],
        )
        engine_one._ensure_acceptance_evidence(created.state)
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        source_items = [item for item in queue["items"] if item["reason"] == "source_evidence"]

        assert report["source_evidence_attention_count"] == 1
        assert entry["source_evidence_requires_attention"] is True
        assert entry["source_evidence"]["missing_labels"] == ["browser"]
        assert "source_evidence" in entry["operator_attention_reasons"]
        assert source_items
        assert source_items[0]["ui_target"] == "source_evidence"
        assert source_items[0]["endpoint"] == f"/api/runs/{created.id}/source-evidence"

    asyncio.run(run())

def test_supervisor_auto_resumes_safe_queued_run_when_enabled(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Auto resume me", "Auto resume", str(tmp_path), [])
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        engine_two = make_engine(tmp_path, auto_resume=True, auto_resume_max_runs=1)
        report = await engine_two.recover_stale_runs()
        engine_two._cancel_task(created.id)
        recovered = engine_two.store.get_run(created.id)

        assert report["auto_resumed"] == 1
        assert report["runs"][0]["action"] == "auto_resumed"
        assert report["runs"][0]["policy_simulation"]["policy_action"] == "complete"
        assert report["runs"][0]["run_progress"]["status"] == "near_completion"
        assert report["runs"][0]["run_progress"]["can_keep_running"] is True
        assert recovered.status == "queued"
        assert "Supervisor auto-resumed stale queued run" in recovered.state.facts_learned[-1]
        assert not recovered.state.blockers
        preflight = next(event for event in engine_two.store.list_events(created.id) if event["kind"] == "resume_preflight")
        assert preflight["data"]["source"] == "supervisor"
        assert preflight["data"]["policy_simulation"]["policy_action"] == "complete"

    asyncio.run(run())


def test_supervisor_auto_resume_pauses_blocked_queued_run(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Do not auto resume", "Blocked auto resume", str(tmp_path), [])
        created.state.blockers.append("Needs user decision.")
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        engine_two = make_engine(tmp_path, auto_resume=True, auto_resume_max_runs=1)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)

        assert report["auto_resumed"] == 0
        assert report["recovered"] == 1
        assert report["runs"][0]["action"] == "paused_for_resume"
        assert report["runs"][0]["run_progress"]["status"] == "blocked"
        assert "Policy simulation blocks auto-resume" in report["runs"][0]["auto_resume_reason"]
        assert recovered.status == "paused"

    asyncio.run(run())


def test_ornith_resume_preflight_reports_fresh_smoke_and_health(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Ornith resume preflight",
        str(tmp_path),
        [],
    )
    fresh_smoke_time = engine._iso_datetime(engine._utc_datetime() + timedelta(seconds=60))
    seed_passed_rehearsal(engine, tmp_path, generated_at=fresh_smoke_time)
    seed_passed_dispatch_restart_smoke(engine, tmp_path, generated_at=fresh_smoke_time)

    report = engine.get_ornith_launch_checklist(created.id)
    items = {item["id"]: item for item in report["items"]}

    assert report["mode"] == "resume"
    assert report["ready_to_resume"] is True
    assert report["readiness_smoke_status"] == "passed"
    assert report["dispatch_restart_smoke_status"] == "passed"
    assert items["readiness_smoke"]["status"] == "pass"
    assert items["operator_dispatch_restart_smoke"]["status"] == "pass"
    assert items["run_health"]["status"] == "pass"
def test_ornith_preflight_enters_handoff_and_compact_context(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Ornith handoff preflight",
        str(tmp_path),
        [],
    )

    handoff = engine._make_handoff(created, created.state)
    created.state.handoff_summary = handoff
    items = {item.id: item for item in handoff.ornith_preflight.items}
    memory_context = engine.memory.consult(created.state.goal, run_id=created.id)
    prompt, snapshot = engine.context_compiler.compile(created, created.state, memory_context, [])

    assert handoff.ornith_preflight.run_id == created.id
    assert created.state.ornith_preflight.run_id == created.id
    assert items["handoff_anchor"].status == "pass"
    assert "ornith_preflight" in snapshot.sections
    assert "Ornith preflight:" in prompt

def test_run_health_marks_missing_dispatch_restart_smoke_attention(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Harness missing dispatch smoke health",
        str(tmp_path),
        [],
    )

    health = engine._build_run_health(created, created.state)
    signal_ids = {signal.id for signal in health.signals}

    assert health.level == "watch"
    assert health.score >= 30
    assert "operator_dispatch_restart_smoke_attention" in signal_ids
    assert any("operator-dispatch restart smoke" in action for action in health.next_actions)


def test_run_health_records_passed_dispatch_restart_smoke_as_positive_evidence(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Harness dispatch smoke ready health",
        str(tmp_path),
        [],
    )
    fresh_smoke_time = engine._iso_datetime(engine._utc_datetime() + timedelta(seconds=60))
    seed_passed_rehearsal(engine, tmp_path, generated_at=fresh_smoke_time)
    seed_passed_dispatch_restart_smoke(engine, tmp_path, generated_at=fresh_smoke_time)

    health = engine._build_run_health(created, created.state)
    signals = {signal.id: signal for signal in health.signals}

    assert health.level == "healthy"
    assert health.recommended_action == "continue"
    assert "operator_dispatch_restart_smoke_attention" not in signals
    assert signals["operator_dispatch_restart_smoke_ready"].severity == "info"
    assert any("handoff=replay=context=attached" in item for item in signals["operator_dispatch_restart_smoke_ready"].evidence)

def test_supervisor_reports_missing_readiness_smoke_for_harness_runs(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Improve AgentOrinth into a Codex-like long coding harness",
            "Harness needs smoke",
            str(tmp_path),
            [],
        )
        engine_one.store.update_run(created.id, status="running", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = report["runs"][0]

        assert report["readiness_rehearsal_ledger"]["status"] == "never_run"
        assert report["readiness_smoke_attention_count"] == 1
        assert report["operator_attention_count"] == 1
        assert entry["readiness_smoke_required"] is True
        assert entry["readiness_smoke_status"] == "missing"
        assert entry["readiness_smoke_requires_attention"] is True
        assert "smoke" in entry["readiness_smoke_action"]
        assert entry["operator_attention_required"] is True
        assert "readiness_smoke" in entry["operator_attention_reasons"]
        assert entry["operator_attention_severity"] in {"watch", "blocked"}
        assert entry["supervisor_priority"] >= 75
        assert entry["run_health"]["level"] == "watch"
        assert any(signal["id"] == "readiness_smoke_attention" for signal in entry["run_health"]["signals"])
        assert any(
            signal["id"] == "operator_dispatch_restart_smoke_attention"
            for signal in entry["run_health"]["signals"]
        )

    asyncio.run(run())


def test_supervisor_reports_stale_readiness_smoke_for_newer_harness_runs(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        seed_passed_rehearsal(engine_one, tmp_path)
        created = engine_one.store.create_run(
            "Improve AgentOrinth into a Codex-like long coding harness",
            "Harness stale smoke",
            str(tmp_path),
            [],
        )
        engine_one.store.update_run(created.id, status="running", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        stale_entry = next(item for item in report["runs"] if item["run_id"] == created.id)

        assert report["readiness_rehearsal_ledger"]["status"] == "passed"
        assert report["readiness_smoke_attention_count"] == 1
        assert report["operator_attention_count"] == 1
        assert stale_entry["readiness_smoke_status"] == "stale"
        assert stale_entry["readiness_smoke_requires_attention"] is True
        assert stale_entry["readiness_smoke_latest_run_id"]
        assert "readiness_smoke" in stale_entry["operator_attention_reasons"]
        assert stale_entry["supervisor_priority"] >= 75
        assert any(signal["id"] == "readiness_smoke_attention" for signal in stale_entry["run_health"]["signals"])

    asyncio.run(run())


def test_supervisor_surfaces_paused_smoke_attention_runs(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        harness = engine_one.store.create_run(
            "Improve AgentOrinth into a Codex-like long coding harness",
            "Paused harness smoke",
            str(tmp_path),
            [],
        )
        ordinary = engine_one.store.create_run("Fix a small bug", "Paused ordinary", str(tmp_path), [])
        engine_one.store.update_run(harness.id, status="paused", state=harness.state)
        engine_one.store.update_run(ordinary.id, status="paused", state=ordinary.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()

        assert report["readiness_smoke_attention_count"] == 1
        assert report["operator_attention_count"] == 1
        assert report["operator_attention_watch_count"] == 1
        assert [item["run_id"] for item in report["runs"]] == [harness.id]
        assert report["runs"][0]["action"] == "operator_attention"
        assert report["runs"][0]["operator_attention_required"] is True
        assert "readiness_smoke" in report["runs"][0]["operator_attention_reasons"]
        assert "ornith_preflight" in report["runs"][0]["operator_attention_reasons"]
        assert report["runs"][0]["ornith_preflight_requires_attention"] is True
        assert report["runs"][0]["supervisor_priority"] >= 75

    asyncio.run(run())


def test_supervisor_operator_attention_rolls_up_approvals_recovery_and_blockers(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        approval_run = engine_one.store.create_run("Review approval", "Approval attention", str(tmp_path), [])
        engine_one.store.create_approval(approval_run.id, "shell", {"command": "python -m pytest"}, "Approve shell.")
        engine_one.store.update_run(approval_run.id, status="waiting_approval", state=approval_run.state)

        recovery_run = engine_one.store.create_run("Recover work", "Recovery attention", str(tmp_path), [])
        recovery_run.state.recovery_plan.status = "active"
        recovery_run.state.recovery_plan.next_action = "Run narrower recovery proof."
        engine_one.store.update_run(recovery_run.id, status="paused", state=recovery_run.state)

        blocker_run = engine_one.store.create_run("Blocked work", "Blocker attention", str(tmp_path), [])
        blocker_run.state.blockers.append("Needs user decision.")
        engine_one.store.update_run(blocker_run.id, status="blocked", state=blocker_run.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entries = {item["run_id"]: item for item in report["runs"]}

        assert report["pending_approval_count"] == 1
        assert report["operator_attention_count"] == 3
        assert report["operator_attention_blocked_count"] == 3
        assert report["operator_recovery_count"] == 1
        assert report["operator_blocker_count"] == 1
        assert entries[approval_run.id]["operator_attention_reasons"][:2] == ["approval", "waiting_approval"]
        assert "recovery" in entries[recovery_run.id]["operator_attention_reasons"]
        assert "blocker" in entries[blocker_run.id]["operator_attention_reasons"]
        assert all(item["operator_attention_required"] for item in entries.values())
        queue = report["operator_action_queue"]
        queue_reasons = {item["reason"] for item in queue["items"]}

        assert queue["total_count"] == 3
        assert queue["blocked_count"] == 3
        assert queue["approval_count"] == 1
        assert queue["recovery_count"] == 1
        assert queue["blocker_count"] == 1
        assert queue_reasons == {"approval", "recovery", "blocker"}
        approval_item = next(item for item in queue["items"] if item["reason"] == "approval")
        recovery_item = next(item for item in queue["items"] if item["reason"] == "recovery")
        blocker_item = next(item for item in queue["items"] if item["reason"] == "blocker")
        assert approval_item["approval_id"] > 0
        assert approval_item["endpoint"] == f"/api/runs/{approval_run.id}/approvals"
        assert recovery_item["endpoint"] == f"/api/runs/{recovery_run.id}/recovery/resume"
        assert blocker_item["ui_target"] == "steer"

        unconfirmed = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(
                item_id=approval_item["id"],
                decision="reject",
                confirmed=False,
            )
        )
        assert unconfirmed.status == "requires_confirmation"
        assert engine_two.store.list_approvals(approval_run.id, status="pending")

        rejected = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(
                item_id=approval_item["id"],
                decision="reject",
                confirmed=True,
            )
        )
        assert rejected.status == "dispatched"
        assert rejected.action_taken == "reject"
        assert rejected.queue.approval_count == 0
        assert not engine_two.store.list_approvals(approval_run.id, status="pending")
        event_kinds = [event["kind"] for event in engine_two.store.list_events(approval_run.id)]
        assert "operator_action_confirmation_required" in event_kinds
        assert "operator_action_dispatched" in event_kinds
        ledger = engine_two.get_operator_dispatches(approval_run.id)
        assert ledger["total_count"] == 2
        assert ledger["confirmation_required_count"] == 1
        assert ledger["dispatched_count"] == 1
        assert ledger["entries"][0]["status"] == "dispatched"
        assert ledger["entries"][0]["approval_id"] == approval_item["approval_id"]

    asyncio.run(run())


def test_supervisor_auto_resume_respects_max_runs(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        first = engine_one.store.create_run("Auto resume one", "Auto one", str(tmp_path), [])
        second = engine_one.store.create_run("Auto resume two", "Auto two", str(tmp_path), [])
        engine_one.store.update_run(first.id, status="queued", state=first.state)
        engine_one.store.update_run(second.id, status="queued", state=second.state)

        engine_two = make_engine(tmp_path, auto_resume=True, auto_resume_max_runs=1)
        report = await engine_two.recover_stale_runs()
        engine_two._cancel_task(first.id)
        engine_two._cancel_task(second.id)

        assert report["auto_resumed"] == 1
        assert sum(1 for item in report["runs"] if item["action"] == "auto_resumed") == 1
        assert sum(1 for item in report["runs"] if item["action"] == "paused_for_resume") == 1
        assert any(item["auto_resume_reason"] == "Auto-resume limit reached for this supervisor pass." for item in report["runs"])

    asyncio.run(run())


def test_startup_recovery_preserves_pending_workspace_promotion(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Preserve approval", "Promotion waiting", str(tmp_path), [])
        engine_one.store.create_approval(
            created.id,
            "workspace_promote",
            {"tool_name": "workspace_promote", "args": {"source_path": str(tmp_path)}},
            "Promote workspace changes.",
        )
        engine_one.store.update_run(created.id, status="waiting_approval", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)

        assert report["waiting_approval"] == 1
        assert recovered.status == "waiting_approval"
        assert recovered.state.next_step == "Wait for pending dashboard approval."
        assert "workspace_promote:pending" in recovered.state.handoff_summary.approvals

    asyncio.run(run())


def test_workspace_promotion_request_creates_approval(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("old\n", encoding="utf-8")
        (workspace / "README.md").write_text("new\n", encoding="utf-8")
        created = engine.store.create_run(
            "Promote isolated work",
            "Promotion",
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

        updated = await engine.request_workspace_promotion(created.id)
        approvals = engine.store.list_approvals(created.id, status="pending")

        assert updated.status == "waiting_approval"
        assert approvals[0]["action_kind"] == "workspace_promote"
        assert approvals[0]["payload"]["args"]["source_path"] == str(source)
        assert approvals[0]["payload"]["preview"]["summary"] == "1 workspace change(s): 0 added, 1 modified, 0 deleted."
        assert approvals[0]["payload"]["preview"]["files"][0]["path"] == "README.md"

    asyncio.run(run())


def test_workspace_promotion_request_reuses_pending_approval(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("old\n", encoding="utf-8")
        (workspace / "README.md").write_text("new\n", encoding="utf-8")
        created = engine.store.create_run(
            "Promote once",
            "Promotion idempotency",
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

        await engine.request_workspace_promotion(created.id)
        updated = await engine.request_workspace_promotion(created.id)
        approvals = engine.store.list_approvals(created.id, status="pending")

        assert updated.status == "waiting_approval"
        assert len(approvals) == 1
        assert "Reused existing pending workspace promotion approval" in updated.state.facts_learned[-1]

    asyncio.run(run())


def test_workspace_promotion_request_without_changes_pauses_without_approval(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("same\n", encoding="utf-8")
        (workspace / "README.md").write_text("same\n", encoding="utf-8")
        created = engine.store.create_run(
            "Promote isolated work",
            "Promotion",
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

        updated = await engine.request_workspace_promotion(created.id)

        assert updated.status == "paused"
        assert engine.store.list_approvals(created.id, status="pending") == []
        assert "No isolated workspace changes" in updated.state.facts_learned[-1]

    asyncio.run(run())


def test_workspace_promotion_survives_engine_recreation(tmp_path: Path) -> None:
    async def run() -> None:
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "app.py").write_text("print('old')\n", encoding="utf-8")
        (workspace / "app.py").write_text("print('new')\n", encoding="utf-8")
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Promote after restart",
            "Restart promotion",
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

        await engine_one.refresh_workspace_diff(created.id)
        await engine_one.request_workspace_promotion(created.id)
        approval = engine_one.store.list_approvals(created.id, status="pending")[0]

        engine_two = make_engine(tmp_path)
        await engine_two.approve_action(created.id, approval["id"])
        engine_two._cancel_task(created.id)
        restored = engine_two.store.get_run(created.id)

        assert (source / "app.py").read_text(encoding="utf-8") == "print('new')\n"
        assert restored.state.workspace_promotions[0].status == "promoted"
        assert restored.state.workspace_promotions[0].files == ["app.py"]
        assert restored.state.workspace_diff.total_files == 0

    asyncio.run(run())

