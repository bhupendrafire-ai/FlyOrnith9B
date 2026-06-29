from __future__ import annotations

import asyncio
import subprocess
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from app.engine import AgentLoopEngine
from app.events import EventBroker
from app.memory import MemoryContext, ObsidianMemory
from app.persistence import RunStore
from app.readiness_completion import build_readiness_completion
from app.schemas import (
    AcceptanceCriterionEvidence,
    AcceptanceRecommendationTrace,
    CompletionAuditReport,
    ContextBudget,
    DesktopEffectProofReport,
    ObjectiveReadinessItem,
    ObjectiveReadinessProofPreference,
    OperatorActionDispatchRequest,
    OperatorDispatchRestartSmokeLedgerEntry,
    OperatorDispatchRestartSmokeLedgerReport,
    OperatorDispatchRestartSmokeReport,
    OrnithPreflightWarningRecord,
    OrnithPreflightWarningReport,
    PostActionRetryDecisionRecord,
    PatchApplication,
    PatchProposal,
    ObjectiveReadinessProofOutcome,
    ObjectiveReadinessReport,
    PolicySimulationReport,
    PromotionVerificationAttemptRecord,
    PromotionVerificationReport,
    ReadinessRehearsalLedgerEntry,
    ReadinessSourceRefPreviewReport,
    ReadinessProofHistoryReport,
    ReadinessRehearsalLedgerReport,
    ReadinessRehearsalReport,
    ReadinessRehearsalStep,
    RunProgressReport,
    RecoveryPlan,
    ResumeHandoffDiffReport,
    SelfScaffoldChangeRecord,
    SelfScaffoldReport,
    RunLease,
    TaskNode,
    ToolCallRecord,
    DesktopSnapshot,
    WebSource,
    WorkspaceIsolation,
)
from app.tools import ToolResult, ToolRunner

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
    "git_checkpoint_cadence",
    "source_promotion_audit",
    "resume_prompt_quality",
    "resume_handoff_diff",
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
        self_scaffold_reviewed=True,
        self_scaffold_review_event_id=4,
        self_scaffold_reviewed_change_count=1,
        post_review_handoff_goal_preserved=True,
        post_review_handoff_next_action_preserved=True,
        post_review_resume_prompt_goal_preserved=True,
        post_review_resume_prompt_next_action_preserved=True,
        step_count=9,
        passed_steps=9,
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
        self_scaffold_reviewed=True,
        self_scaffold_review_event_id=4,
        self_scaffold_reviewed_change_count=1,
        post_review_handoff_goal_preserved=True,
        post_review_handoff_next_action_preserved=True,
        post_review_resume_prompt_goal_preserved=True,
        post_review_resume_prompt_next_action_preserved=True,
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
            for index in range(1, 10)
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
    run.state.acceptance_evidence.append(
        AcceptanceCriterionEvidence(
            id="source-visible-readiness",
            criterion="Readiness proof has web and browser source refs.",
            status="verified",
            required_labels=["web", "browser"],
            matched_labels=["web", "browser"],
        )
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
        ornith_preflight_warnings=OrnithPreflightWarningReport(run_id=run.id, generated_at="2026-06-28T00:00:00+00:00"),
        self_scaffold=SelfScaffoldReport(
            run_id=run.id,
            generated_at="2026-06-28T00:00:00+00:00",
            status="observed",
            change_count=1,
            reviewed_change_count=1,
            review_count=1,
            latest_review_event_id=22,
            changes=[
                SelfScaffoldChangeRecord(
                    id="model_guard:accepted",
                    kind="model_guard",
                    status="observed",
                    summary="Accepted guard review.",
                )
            ],
        ),
        readiness_proof_history=ReadinessProofHistoryReport(
            run_id=run.id,
            generated_at="2026-06-28T00:00:00+00:00",
            status="complete",
            source_evidence_ref_count=2,
            source_evidence_labels=["browser", "web"],
            source_evidence_summary="Readiness proof history links 2 compact source evidence artifact(s).",
            latest_summary="Readiness claim source refs are available.",
        ),
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    assert report.status == "ready"
    assert report.can_claim_milestone is True
    assert report.confidence == "high"
    assert report.blocking_count == 0
    assert report.ornith_preflight_warning_count == 0
    assert report.self_scaffold_status == "observed"
    assert report.self_scaffold_pending_review_count == 0
    assert report.self_scaffold_reviewed_change_count == 1
    assert report.source_visible_required_label_count == 2
    assert report.source_visible_matched_label_count == 2
    assert report.readiness_proof_source_ref_count == 2
    assert report.readiness_proof_source_ref_labels == ["browser", "web"]
    assert report.source_visible_missing_ref_labels == []
    source_ref_check = next(check for check in report.checks if check.id == "readiness_proof_source_refs")
    assert source_ref_check.status == "pass"
    assert "source_visible_labels=browser,web" in source_ref_check.evidence
    rehearsal_check = next(check for check in report.checks if check.id == "readiness_rehearsal")
    assert "self_scaffold_reviewed=True" in rehearsal_check.evidence
    assert "self_scaffold_reviewed_changes=1" in rehearsal_check.evidence
    assert "post_review_handoff_goal=True" in rehearsal_check.evidence
    assert "post_review_resume_next=True" in rehearsal_check.evidence
    assert any(check.id == "self_scaffold_review" and check.status == "pass" for check in report.checks)
    assert rehearsal_check.status == "pass"
    assert any(check.id == "operator_dispatch_restart_smoke" and check.status == "pass" for check in report.checks)
    assert any(check.id == "ornith_preflight_warnings" and check.status == "pass" for check in report.checks)


def test_readiness_completion_gate_blocks_missing_source_ref_label(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness missing source refs",
        str(tmp_path),
        ["Harness readiness has source-visible proof"],
    )
    run.state.acceptance_evidence.append(
        AcceptanceCriterionEvidence(
            id="source-visible-readiness",
            criterion="Readiness proof has web and browser source refs.",
            status="verified",
            required_labels=["web", "browser"],
            matched_labels=["web"],
        )
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
        ornith_preflight_warnings=OrnithPreflightWarningReport(run_id=run.id, generated_at="2026-06-28T00:00:00+00:00"),
        self_scaffold=SelfScaffoldReport(
            run_id=run.id,
            generated_at="2026-06-28T00:00:00+00:00",
            status="observed",
        ),
        readiness_proof_history=ReadinessProofHistoryReport(
            run_id=run.id,
            generated_at="2026-06-28T00:00:00+00:00",
            status="partial",
            source_evidence_ref_count=1,
            source_evidence_labels=["web"],
            source_evidence_summary="Readiness proof history links 1 compact source evidence artifact(s).",
        ),
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert report.source_visible_required_label_count == 2
    assert report.source_visible_matched_label_count == 1
    assert report.readiness_proof_source_ref_count == 1
    assert report.readiness_proof_source_ref_labels == ["web"]
    assert report.source_visible_missing_ref_labels == ["browser"]
    check = next(check for check in report.checks if check.id == "readiness_proof_source_refs")
    assert check.status == "block"
    assert "missing_ref_labels=browser" in check.evidence
    assert "source_ref_labels=web" in check.evidence
    assert any("source evidence" in action for action in report.next_actions)
def test_readiness_completion_gate_blocks_dirty_ornith_preflight_warning_history(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness dirty preflight",
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
    dirty_preflight = OrnithPreflightWarningReport(
        run_id=run.id,
        generated_at="2026-06-28T00:00:00+00:00",
        total_count=1,
        warning_count=1,
        action_context_reorient_count=1,
        latest_reorient_event_id=17,
        latest_warning="Handoff action context is too thin for unattended Ornith resume.",
        recommended_action="Refresh/checkpoint the handoff before claiming readiness.",
        entries=[
            OrnithPreflightWarningRecord(
                event_id=17,
                source="act_preflight_reorient",
                item_id="handoff_action_context",
                status="warn",
                summary="Handoff action context is too thin for unattended Ornith resume.",
                evidence=["restart_ledger=0"],
                next_action="Refresh/checkpoint the handoff before claiming readiness.",
            )
        ],
    )

    report = build_readiness_completion(
        run,
        objective,
        progress,
        completion,
        passed_rehearsal_ledger(),
        passed_dispatch_restart_smoke_ledger(),
        ornith_preflight_warnings=dirty_preflight,
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    check = next(check for check in report.checks if check.id == "ornith_preflight_warnings")
    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert report.ornith_preflight_warning_count == 1
    assert report.ornith_preflight_reorient_count == 1
    assert check.status == "block"
    assert "restart_ledger=0" in check.evidence
    assert check.next_action == "Refresh/checkpoint the handoff before claiming readiness."


def test_readiness_completion_gate_blocks_unreviewed_self_scaffold(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness dirty self scaffold",
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
    dirty_scaffold = SelfScaffoldReport(
        run_id=run.id,
        generated_at="2026-06-28T00:00:00+00:00",
        status="needs_review",
        change_count=1,
        guard_count=1,
        latest_change="A model guard changed or constrained the selected action.",
        recommended_action="Review pending self-scaffold changes before broad autonomy.",
        changes=[
            SelfScaffoldChangeRecord(
                id="model_guard:current-task-mismatch",
                kind="model_guard",
                status="needs_review",
                source="action_context",
                summary="A model guard changed or constrained the selected action.",
                evidence=["current_task_mismatch"],
            )
        ],
    )

    report = build_readiness_completion(
        run,
        objective,
        progress,
        completion,
        passed_rehearsal_ledger(),
        passed_dispatch_restart_smoke_ledger(),
        ornith_preflight_warnings=OrnithPreflightWarningReport(run_id=run.id, generated_at="2026-06-28T00:00:00+00:00"),
        self_scaffold=dirty_scaffold,
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    check = next(check for check in report.checks if check.id == "self_scaffold_review")
    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert report.self_scaffold_status == "needs_review"
    assert report.self_scaffold_pending_review_count == 1
    assert check.status == "block"
    assert "pending=1" in check.evidence
    assert check.next_action == "Review pending self-scaffold changes before broad autonomy."


def test_make_handoff_feeds_preflight_warning_history_into_readiness_completion(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Live preflight readiness",
        str(tmp_path),
        ["Harness readiness is verified"],
    )
    event = engine.store.append_event(
        run.id,
        "act_preflight_reorient",
        "Act preflight detected thin handoff action context.",
        {
            "handoff_action_context": {
                "status": "warn",
                "summary": "Handoff action context is too thin for unattended Ornith resume.",
                "evidence": ["generated=True", "restart_ledger=0"],
                "next_action": "Refresh/checkpoint the handoff before selecting the next tool action.",
            }
        },
    )

    handoff = engine._make_handoff(run, run.state)

    check = next(check for check in handoff.readiness_completion.checks if check.id == "ornith_preflight_warnings")
    assert handoff.ornith_preflight_warnings.action_context_reorient_count == 1
    assert handoff.ornith_preflight_warnings.latest_reorient_event_id == event["id"]
    assert handoff.readiness_completion.ornith_preflight_reorient_count == 1
    assert check.status == "block"
    assert "restart_ledger=0" in check.evidence


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


def test_readiness_completion_gate_blocks_rehearsal_without_self_scaffold_review(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness stale smoke contract",
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
    stale_ledger = passed_rehearsal_ledger()
    stale_latest = stale_ledger.latest.model_copy(
        update={
            "self_scaffold_reviewed": False,
            "self_scaffold_review_event_id": 0,
            "self_scaffold_reviewed_change_count": 0,
        }
    )
    stale_ledger.latest = stale_latest
    stale_ledger.entries = [stale_latest]

    report = build_readiness_completion(
        run,
        objective,
        progress,
        completion,
        stale_ledger,
        passed_dispatch_restart_smoke_ledger(),
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    check = next(check for check in report.checks if check.id == "readiness_rehearsal")
    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert check.status == "block"
    assert "self_scaffold_reviewed=False" in check.evidence
    assert "self_scaffold_reviewed_changes=0" in check.evidence
    assert "self-scaffold review" in check.next_action


def test_readiness_completion_gate_blocks_rehearsal_without_post_review_handoff_proof(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Readiness stale post-review handoff",
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
    stale_ledger = passed_rehearsal_ledger()
    stale_latest = stale_ledger.latest.model_copy(
        update={
            "post_review_handoff_goal_preserved": False,
            "post_review_handoff_next_action_preserved": False,
            "post_review_resume_prompt_goal_preserved": False,
            "post_review_resume_prompt_next_action_preserved": False,
        }
    )
    stale_ledger.latest = stale_latest
    stale_ledger.entries = [stale_latest]

    report = build_readiness_completion(
        run,
        objective,
        progress,
        completion,
        stale_ledger,
        passed_dispatch_restart_smoke_ledger(),
        require_rehearsal_ledger=True,
        require_dispatch_restart_smoke_ledger=True,
    )

    check = next(check for check in report.checks if check.id == "readiness_rehearsal")
    assert report.status == "blocked"
    assert report.can_claim_milestone is False
    assert check.status == "block"
    assert "post_review_handoff_goal=False" in check.evidence
    assert "post_review_resume_next=False" in check.evidence
    assert "post-review handoff" in check.next_action


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


def test_choose_action_guards_harness_proof_recommendation_during_empty_edit_task(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Patch before verification", "Edit before proof", str(tmp_path), ["Tests pass"])
        created.state.step_count = 1
        created.state.task_graph = [
            TaskNode(
                id="task-edit",
                title="Patch app.py safely",
                status="pending",
                kind="edit",
            )
        ]
        created.state.current_task_id = "task-edit"

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "file_read"
        assert action["args"] == {"path": "app.py"}
        assert action["model_guard"] == "current_task_mismatch"
        assert action["guarded_tool"] == "run_tests"
        assert action["guard_reason"] == "edit_task_selected_proof_tool_without_evidence"
        assert created.state.action_context.selected_tool == "file_read"
        assert any("current_task_mismatch" in item and "selected" in item for item in created.state.action_context.model_guard_ledger)
        assert created.state.model_interactions[-1].fallback_used
        assert "mismatched current edit task" in created.state.model_interactions[-1].summary

    asyncio.run(run())


def test_choose_action_uses_promotion_repair_hint_before_broad_recommendation(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        created = engine.store.create_run("Repair before verifying", "Promotion repair action", str(workspace), ["Tests pass"])
        created.state.step_count = 1
        latest = PromotionVerificationAttemptRecord(
            event_id=31,
            timestamp="2026-06-28T12:00:00+00:00",
            command="python -m py_compile broken.py",
            ok=False,
            audit_status="needs_verification",
            summary="Promotion verification failed.",
            returncode=1,
            failure_kind="syntax_error",
            suspected_file="broken.py",
            suspected_line=1,
            repair_hint="Open `broken.py:1` and fix invalid syntax before rerunning promotion verification.",
            evidence_excerpt="SyntaxError: invalid syntax",
        )
        created.state.promotion_verification = PromotionVerificationReport(
            run_id=created.id,
            generated_at="2026-06-28T12:00:00+00:00",
            status="needs_retry",
            attempt_count=1,
            failed_count=1,
            repeated_failure_count=1,
            repair_hint_count=1,
            latest_attempt=latest,
            latest_failed_command=latest.command,
            latest_failure_kind=latest.failure_kind,
            latest_suspected_file=latest.suspected_file,
            latest_repair_hint=latest.repair_hint,
            next_command="python -m compileall .",
            should_use_alternate=True,
            recommended_action=latest.repair_hint,
            attempts=[latest],
        )
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-failed-proof",
                name="run_tests",
                args={"command": latest.command},
                ok=False,
                summary="Promotion proof failed.",
            )
        )

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "file_read"
        assert action["args"]["path"] == "broken.py"
        assert action["promotion_failure_kind"] == "syntax_error"
        assert "broken.py:1" in action["thought_summary"]
        assert created.state.action_context.selected_tool == "file_read"
        assert "promotion_repair_hints=syntax_error:broken.py:1:rc=1" in created.state.action_context.compact_prompt
        assert "promotion repair target" in created.state.model_interactions[-1].summary

        class CapturingPatchModel:
            def __init__(self) -> None:
                self.user_prompt = ""

            async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
                self.user_prompt = messages[-1]["content"]
                return (
                    '{"tool":"patch_propose","args":{"title":"Repair broken.py syntax",'
                    '"summary":"Fix the promotion verification syntax failure in broken.py.",'
                    '"files":["broken.py"],'
                    '"diff":"--- a/broken.py\\n+++ b/broken.py\\n@@\\n-def broken(:\\n+def broken():\\n     pass\\n"},'
                    '"thought_summary":"Propose the focused promotion repair patch."}'
                )

        patch_model = CapturingPatchModel()
        engine.model = patch_model  # type: ignore[assignment]
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-read-repair-target",
                name="file_read",
                args={"path": "broken.py", "content": "def broken(:\n    pass\n"},
                ok=True,
                summary="Read broken.py.",
            )
        )
        followup = await engine._choose_action(created, "tiny context")

        assert followup["tool"] == "patch_propose"
        assert followup["args"]["files"] == ["broken.py"]
        assert "Promotion repair patch target" in patch_model.user_prompt
        assert "target=broken.py:1" in patch_model.user_prompt
        assert "file_excerpt:" in patch_model.user_prompt
        assert "def broken(:" in patch_model.user_prompt
        assert "do not rerun tests first" in patch_model.user_prompt

    asyncio.run(run())


def test_promotion_repair_loop_reads_proposes_applies_and_reruns_verification(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "broken.py").write_text("def broken():\n    pass\n", encoding="utf-8")
        (workspace / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        created = engine.store.create_run(
            "Repair promotion syntax failure",
            "Promotion repair loop",
            str(workspace),
            ["Promotion verification passes before source promotion"],
            workspace_isolation=WorkspaceIsolation(
                enabled=True,
                mode="copy",
                source_path=str(source),
                workspace_path=str(workspace),
                summary="Isolated copy.",
            ),
        )
        await engine.request_workspace_promotion(created.id)
        prepared = engine.store.get_run(created.id)
        prepared.state.repo_map.test_commands = ["python -m py_compile broken.py"]
        engine.store.update_run(prepared.id, status="paused", state=prepared.state)

        failed = await engine.run_promotion_audit_verification(created.id)

        assert failed.state.promotion_verification.status == "needs_retry"
        assert failed.state.promotion_repair.phase == "needs_file_read"
        assert failed.state.promotion_repair.next_tool == "file_read"

        read_action = await engine._choose_action(failed, "compact context")
        read_result = await engine._execute_action(failed, read_action)
        await engine._record_tool_result(created.id, read_result, action=read_action)
        after_read = engine.store.get_run(created.id)

        assert read_action["tool"] == "file_read"
        assert read_result.ok
        assert "def broken(:" in str(read_result.data.get("content") or "")
        assert after_read.state.promotion_repair.phase == "needs_patch_proposal"
        assert after_read.state.promotion_repair.next_tool == "patch_propose"

        class PatchModel:
            async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
                return (
                    '{"tool":"patch_propose","args":{"title":"Repair broken.py syntax",'
                    '"summary":"Fix the promotion verification syntax failure in broken.py.",'
                    '"files":["broken.py"],'
                    '"diff":"--- a/broken.py\\n+++ b/broken.py\\n@@ -1,2 +1,2 @@\\n-def broken(:\\n+def broken():\\n     pass\\n"},'
                    '"thought_summary":"Propose the focused promotion repair patch."}'
                )

        engine.model = PatchModel()  # type: ignore[assignment]
        patch_action = await engine._choose_action(after_read, "compact context")
        patch_result = await engine._execute_action(after_read, patch_action)
        await engine._record_tool_result(created.id, patch_result, action=patch_action)
        after_proposal = engine.store.get_run(created.id)

        assert patch_action["tool"] == "patch_propose"
        assert patch_result.ok
        assert after_proposal.state.patch_proposals
        assert after_proposal.state.promotion_repair.phase == "patch_proposed"
        assert after_proposal.state.promotion_repair.next_tool == "patch_apply"

        proposal = after_proposal.state.patch_proposals[-1]
        apply_args = {"patch_id": proposal.id, "title": proposal.title, "diff": proposal.diff}
        apply_result = await ToolRunner(workspace, engine.config).execute("patch_apply", apply_args, approved=True)
        await engine._record_tool_result(
            created.id,
            apply_result,
            action={
                "tool": "patch_apply",
                "args": apply_args,
                "thought_summary": "Apply approved promotion repair patch.",
            },
        )
        after_apply = engine.store.get_run(created.id)

        assert apply_result.ok
        assert (workspace / "broken.py").read_text(encoding="utf-8") == "def broken():\n    pass\n"
        assert after_apply.state.promotion_repair.phase == "ready_to_verify"
        assert after_apply.state.promotion_repair.next_tool == "run_tests"
        assert after_apply.state.promotion_repair.next_verification_command == "python -m compileall ."

        verified = await engine.run_promotion_audit_verification(created.id)
        events = [
            event
            for event in engine.store.list_events(created.id)
            if event["kind"] == "promotion_audit_verification"
        ]

        assert verified.state.promotion_verification.status == "ready"
        assert verified.state.promotion_audit.status == "ready"
        assert verified.state.promotion_repair.phase == "none"
        assert verified.state.promotion_repair.active is False
        assert [event["data"]["tool_ok"] for event in events] == [False, True]

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


def test_anchor_context_refresh_adopts_effective_context_target(tmp_path: Path) -> None:
    engine = make_engine(tmp_path, context_target_tokens=12000)
    run = engine.store.create_run("Resume old config run", "Old budget", str(tmp_path), [])
    run.state.context_budget = ContextBudget(target_tokens=24000, estimated_tokens=0, pressure="low")

    engine._reload_anchor_context(run, run.state)

    assert run.state.context_budget.target_tokens == engine.context_compiler.target_tokens


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


def test_verify_prefers_py_compile_for_touched_python_source(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
        created = engine.store.create_run("Verify touched Python", "Verify py", str(tmp_path), [])
        created.state.files_touched = ["app.py"]

        result = await engine._verify(created, created.state)

        assert result.ok
        assert result.kind == "shell"
        assert result.data["command"] == "python -m py_compile app.py"

    asyncio.run(run())


def test_verify_command_prefers_typecheck_for_touched_frontend_source(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest","build":"vite build","lint":"eslint .","typecheck":"tsc --noEmit"}}',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.tsx").write_text("export function App() { return null }\n", encoding="utf-8")
    created = engine.store.create_run("Verify touched TSX", "Verify tsx", str(tmp_path), [])

    command = engine._verification_command_for_touched_sources(created, created.state, ["src/App.tsx"])

    assert command == "npm run typecheck"
    assert created.state.repo_map.generated_at
def test_verify_milestone_attaches_compact_task_proof_to_handoff(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
        created = engine.store.create_run("Verify task proof", "Task proof", str(tmp_path), [])
        created.state.milestone = "verify"
        created.state.files_touched = ["app.py"]
        created.state.task_graph = [
            TaskNode(id="task-1", title="Patch app.py safely", kind="edit", status="in_progress")
        ]
        created.state.current_task_id = "task-1"
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)
        task = updated.state.task_graph[0]

        assert updated.state.milestone == "checkpoint"
        assert task.status == "completed"
        assert any(
            "verification:ok:shell" in item and "cmd=python -m py_compile app.py" in item
            for item in task.evidence
        )
        assert task.notes == "Latest verification ok: python -m py_compile app.py"
        assert "verification:ok:shell" in updated.state.handoff_summary.model_dump_json()

    asyncio.run(run())

def test_decide_advances_task_and_packs_task_transition_ledger(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Verify task transitions", "Task transition", str(tmp_path), ["Tests pass"])
        created.state.milestone = "decide"
        created.state.next_step = "Verify task transitions against Tests pass."
        created.state.task_graph = [
            TaskNode(
                id="task-1",
                title="Patch app.py safely",
                kind="edit",
                status="completed",
                evidence=["verification:ok:shell | cmd=python -m py_compile app.py"],
                notes="Latest verification ok: python -m py_compile app.py",
            ),
            TaskNode(id="task-2", title="Run focused acceptance verification", kind="verify", status="pending"),
        ]
        created.state.current_task_id = "task-1"
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)
        ledger = updated.state.handoff_summary.action_context.task_transition_ledger

        assert updated.state.milestone == "act"
        assert updated.state.current_task_id == "task-2"
        assert updated.state.handoff_summary.current_task_id == "task-2"
        assert updated.state.handoff_summary.action_context.current_task_id == "task-2"
        assert any("completed:task-1:Patch app.py safely" in item and "verification:ok:shell" in item for item in ledger)
        assert any("current:pending:task-2:Run focused acceptance verification" in item for item in ledger)
        assert "task_transitions=completed:task-1:Patch app.py safely" in updated.state.handoff_summary.action_context.compact_prompt

    asyncio.run(run())


def test_verify_milestone_attaches_critic_risk_to_task_handoff(tmp_path: Path) -> None:
    class CriticRiskModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            prompt = messages[-1]["content"]
            assert "Find concrete risks only" in prompt
            return '{"risk":"Need browser screenshot proof before claiming UI complete."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = CriticRiskModel()  # type: ignore[assignment]
        (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
        created = engine.store.create_run("Verify critic proof", "Critic proof", str(tmp_path), [])
        created.state.milestone = "verify"
        created.state.files_touched = ["app.py"]
        created.state.task_graph = [
            TaskNode(id="task-1", title="Patch app.py safely", kind="edit", status="in_progress")
        ]
        created.state.current_task_id = "task-1"
        engine.store.update_run(created.id, status="queued", state=created.state)

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)
        task = updated.state.task_graph[0]

        assert updated.state.milestone == "checkpoint"
        assert "Need browser screenshot proof" in updated.state.risks[-1]
        assert any("critic:risk | Need browser screenshot proof" in item for item in task.evidence)
        assert task.notes == "Latest critic risk: Need browser screenshot proof before claiming UI complete."
        assert "critic:risk" in updated.state.handoff_summary.model_dump_json()
        assert updated.state.model_interactions[-1].kind == "critic"
        assert updated.state.model_interactions[-1].ok

    asyncio.run(run())
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


def test_run_health_ignores_unresolved_readiness_after_satisfied_label(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Trace satisfied readiness", "Health readiness satisfied", str(tmp_path), ["Tests pass"])
    run.state.acceptance_evidence[0].status = "verified"
    run.state.acceptance_evidence[0].matched_labels = ["verification"]
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
        AcceptanceRecommendationTrace(
            id="rec-trace-3",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            source="harness",
            status="satisfied",
            result_ok=True,
            result_summary="Tests pass verified.",
            evidence_status="verified",
        ),
    ]
    run = engine.store.update_run(run.id, state=run.state)
    for trace in run.state.acceptance_recommendation_traces[:2]:
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

    assert health.recommended_action != "recover"
    assert not any(signal.id == "readiness_proof_unresolved_loop" for signal in health.signals)


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


def test_resume_refreshes_stale_approval_review_handoff_before_preflight(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Refresh approval review handoff", "Approval review preflight", str(tmp_path), [])
        approval = engine.store.create_approval(
            created.id,
            "shell",
            {"tool_name": "shell", "args": {"command": "python -m pytest"}},
            "Approve shell verification.",
        )
        first_review = engine.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator reviewed approval.",
            {"operator_action": {"approval_id": approval["id"]}},
        )
        created.state.handoff_summary = engine._make_handoff(created, created.state)
        engine.store.update_run(created.id, status="paused", state=created.state)
        second_review = engine.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator reviewed approval again.",
            {"operator_action": {"approval_id": approval["id"]}},
        )

        stale = engine.get_report_integrity(created.id)
        stale_checks = {check["section"]: check for check in stale["checks"]}
        assert stale["status"] == "needs_refresh"
        assert stale_checks["handoff.approval_reviews.review_count"]["expected"] == f"{approval['id']}:2"
        assert stale_checks["handoff.approval_reviews.review_count"]["actual"] == f"{approval['id']}:1"
        assert stale_checks["handoff.approvals"]["expected"] == f"shell:pending:reviewed:x2:event#{second_review['id']}"
        assert stale_checks["handoff.approvals"]["actual"] == f"shell:pending:reviewed:x1:event#{first_review['id']}"

        updated = await engine.resume_run(created.id)
        engine._cancel_task(created.id)
        refreshed = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)
        refreshed_review = refreshed.state.handoff_summary.approval_reviews[0]

        assert updated.status == "paused"
        assert refreshed_review.review_count == 2
        assert refreshed_review.latest_review_event_id == second_review["id"]
        assert refreshed.state.handoff_summary.approvals == [
            f"shell:pending:reviewed:x2:event#{second_review['id']}"
        ]
        assert refreshed.state.handoff_summary.report_integrity.status == "ok"
        refresh_event = next(event for event in events if event["kind"] == "report_integrity_refresh")
        refresh_reasons = refresh_event["data"]["report_integrity_refresh_reasons"]
        assert refresh_event["data"]["refresh_reason_count"] == len(refresh_reasons)
        assert any(
            "handoff.approval_reviews.review_count" in reason and f"{approval['id']}:2" in reason
            for reason in refresh_reasons
        )
        preflight = next(event for event in events if event["kind"] == "resume_preflight_blocked")
        assert preflight["data"]["report_integrity_refreshed"] is True
        assert preflight["data"]["report_integrity_refresh_reasons"] == refresh_reasons

    asyncio.run(run())


def test_restart_resume_refresh_breadcrumb_reaches_obsidian_checkpoint(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Restart with refresh breadcrumb",
            "Refresh breadcrumb restart",
            str(tmp_path),
            [],
        )
        approval = engine_one.store.create_approval(
            created.id,
            "shell",
            {"tool_name": "shell", "args": {"command": "python -m pytest"}},
            "Approve shell verification.",
        )
        first_review = engine_one.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator reviewed approval before checkpoint.",
            {"operator_action": {"approval_id": approval["id"]}},
        )
        created.state.handoff_summary = engine_one._make_handoff(created, created.state)
        engine_one.store.update_run(created.id, status="paused", state=created.state)
        engine_one.memory.append_run_started(created)
        second_review = engine_one.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator reviewed approval after backend stopped.",
            {"operator_action": {"approval_id": approval["id"]}},
        )

        engine_two = make_engine(tmp_path)
        updated = await engine_two.resume_run(created.id)
        refreshed = engine_two.store.get_run(created.id)
        refresh = refreshed.state.report_integrity_refreshes[0]
        await engine_two.pause_run(created.id)
        note = engine_two.memory.read_run_note(created.id)

        assert updated.status == "paused"
        assert refresh.previous_report_status == "needs_refresh"
        assert refresh.report_status == "ok"
        assert refresh.preflight_event_kind == "resume_preflight_blocked"
        assert any(
            "handoff.approval_reviews.review_count" in reason and f"{approval['id']}:2" in reason
            for reason in refresh.reasons
        )
        assert f"shell:pending:reviewed:x2:event#{second_review['id']}" in refreshed.state.handoff_summary.approvals
        assert f"shell:pending:reviewed:x1:event#{first_review['id']}" not in refreshed.state.handoff_summary.approvals
        assert f"Report integrity refresh: #{refresh.event_id} needs_refresh->ok reasons={refresh.reason_count}" in note
        assert "handoff.approval_reviews.review_count" in note
        assert f"preflight=#{refresh.preflight_event_id}:resume_preflight_blocked" in note

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


def test_act_preflight_reorients_when_handoff_action_context_is_thin(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Verify acceptance", "Act thin handoff context", str(tmp_path), ["Tests pass"])
        created.state.milestone = "act"
        engine._ensure_acceptance_evidence(created.state)
        created = engine.store.update_run(created.id, status="queued", state=created.state)
        accepted_simulation = engine._build_policy_simulation(created, created.state)
        decision = engine.store.append_event(
            created.id,
            "resume_preflight",
            "Resume preflight accepted for manual.",
            {
                "source": "manual",
                "accepted": True,
                "reason": "Accepted current policy snapshot with stale handoff action context.",
                "policy_simulation": accepted_simulation.model_dump(),
            },
        )

        created.state.handoff_summary.resume_decisions = engine._build_resume_decision_report(created, created.state)
        stable_diff = ResumeHandoffDiffReport(
            run_id=created.id,
            status="stable",
            ready_to_continue=True,
            latest_accepted_event_id=decision["id"],
            summary="Stable accepted preflight baseline.",
        )
        created.state.resume_handoff_diff = stable_diff
        created.state.handoff_summary.resume_handoff_diff = stable_diff
        created = engine.store.update_run(created.id, status="queued", state=created.state)

        assert await engine._apply_act_preflight_guard(created, created.state) is True
        updated = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)
        preflight = next(event for event in events if event["kind"] == "act_preflight_reorient")

        assert updated.state.milestone == "orient"
        assert updated.state.act_preflight_checked_decision_id == decision["id"]
        assert not updated.state.tool_calls
        assert "thin handoff action context" in updated.state.latest_summary
        assert preflight["data"]["handoff_action_context"]["status"] == "warn"
        assert "restart_ledger" in preflight["data"]["handoff_action_context"]["summary"]

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


def test_action_readiness_does_not_verify_artifact_before_creation(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Create a PowerPoint deck named AgentOrnith_use_cases.pptx.",
        "Artifact first",
        str(tmp_path),
        [
            "A PowerPoint .pptx file named AgentOrnith_use_cases.pptx exists in the run workspace root.",
            "Artifact verification confirms the .pptx is a valid PowerPoint zip with at least six slide XML files.",
        ],
    )
    created.state.milestone = "act"
    engine._ensure_acceptance_evidence(created.state)
    created = engine.store.update_run(created.id, status="queued", state=created.state)

    report = engine._build_action_readiness(created, created.state)

    assert report.status == "ready"
    assert report.ready_to_act
    assert report.issues[0].id == "artifact_missing_before_verification"
    assert "before running artifact verification" in report.recommended_action


def test_harness_smoke_gates_ignore_agentorinth_content_artifacts(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Create AgentOrnith_use_cases.pptx explaining where the AgentOrnith harness performs better.",
        "Content deck",
        str(tmp_path),
        [
            "AgentOrnith_use_cases.pptx exists in the run workspace root.",
            "Each use-case slide compares AgentOrnith harness vs simple command-line Ornith.",
        ],
    )

    readiness = engine._build_readiness_completion(created, created.state)
    health = engine._build_run_health(created, created.state)
    signal_ids = {signal.id for signal in health.signals}

    assert engine._is_harness_improvement_goal(created, created.state) is False
    assert readiness.status == "not_applicable"
    assert "operator_dispatch_restart_smoke_attention" not in signal_ids
    assert "readiness_smoke_attention" not in signal_ids
    assert not any("operator-dispatch restart smoke" in action for action in health.next_actions)


def test_harness_smoke_gates_apply_to_agentorinth_code_work(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Improve AgentOrinth backend approval policy and tool routing for long coding tasks.",
        "Harness code work",
        str(tmp_path),
        ["Approval policy supports long coding tasks."],
    )

    assert engine._is_harness_improvement_goal(created, created.state) is True


def test_choose_action_scaffolds_missing_pptx_artifact(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Create AgentOrnith_use_cases.pptx explaining five AgentOrnith use cases.",
            "PPT artifact",
            str(tmp_path),
            ["AgentOrnith_use_cases.pptx exists in the run workspace root."],
        )
        created.state.step_count = 1
        created = engine.store.update_run(created.id, status="queued", state=created.state)

        action = await engine._choose_action(created, "compact context")

        assert action["tool"] == "file_write"
        assert action["args"]["path"] == "_agentornith_create_pptx.py"
        assert "AgentOrnith_use_cases.pptx" in action["args"]["content"]

    asyncio.run(run())


def test_choose_action_runs_existing_pptx_scaffold(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Create AgentOrnith_use_cases.pptx explaining five AgentOrnith use cases.",
            "PPT artifact",
            str(tmp_path),
            ["AgentOrnith_use_cases.pptx exists in the run workspace root."],
        )
        Path(created.workspace_path, "_agentornith_create_pptx.py").write_text("print('ok')", encoding="utf-8")
        created.state.step_count = 1
        created = engine.store.update_run(created.id, status="queued", state=created.state)

        action = await engine._choose_action(created, "compact context")

        assert action["tool"] == "shell"
        assert "_agentornith_create_pptx.py" in action["args"]["command"]

    asyncio.run(run())


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



def test_choose_action_uses_readiness_source_ref_preview_recommendation_before_model(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Verify source-ref evidence gate",
            "Source-ref preview action",
            str(tmp_path),
            ["Readiness proof has web and browser source refs."],
        )
        created.state.step_count = 1
        created.state.milestone = "act"
        engine._ensure_acceptance_evidence(created.state)
        created.state.acceptance_evidence[0].status = "verified"
        created.state.acceptance_evidence[0].matched_labels = ["browser", "web"]
        created.state.acceptance_recommendations = []
        created.state.readiness_source_ref_preview = ReadinessSourceRefPreviewReport(
            run_id=created.id,
            generated_at="2026-06-29T10:00:00+00:00",
            status="missing_source_evidence",
            summary="Readiness source-ref preview is missing browser evidence.",
            recommended_action="Capture browser evidence, then refresh readiness source refs.",
            source_visible_labels=["browser", "web"],
            source_evidence_labels=["web"],
            proof_ref_labels=["web"],
            missing_source_evidence_labels=["browser"],
            missing_proof_ref_labels=["browser"],
        )
        report = engine._build_action_readiness(created, created.state)

        assert report.suggested_tool == "browser_screenshot"
        assert report.suggested_label == "browser"
        assert report.issues[0].id == "readiness_source_ref_evidence_missing"
        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "browser_screenshot"
        assert action["recommendation_id"] == "readiness-source-ref-browser"
        assert action["recommendation_label"] == "browser"
        assert created.state.action_context.selected_tool == "browser_screenshot"
        assert created.state.action_context.selected_reason == "Readiness source-ref preview is missing compact browser source evidence."
        assert created.state.action_context.readiness_source_ref_status == "missing_source_evidence"
        assert created.state.action_context.readiness_source_ref_missing_evidence_labels == ["browser"]
        assert "source_refs status=missing_source_evidence" in created.state.action_context.compact_prompt
        assert "then refresh readiness source refs" in created.state.action_context.compact_prompt
        assert created.state.acceptance_recommendation_traces[0].recommendation_id == "readiness-source-ref-browser"
        assert "acceptance recommendation" in created.state.model_interactions[-1].summary

    asyncio.run(run())
def test_stale_readiness_source_refs_pause_ornith_until_refresh(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Verify source-ref refresh gate",
            "Stale proof refs",
            str(tmp_path),
            ["Readiness proof has web and browser source refs."],
        )
        created.state.step_count = 1
        created.state.milestone = "act"
        engine._ensure_acceptance_evidence(created.state)
        created.state.acceptance_evidence[0].status = "verified"
        created.state.acceptance_evidence[0].matched_labels = ["browser", "web"]
        created.state.acceptance_recommendations = []
        created.state.readiness_source_ref_preview = ReadinessSourceRefPreviewReport(
            run_id=created.id,
            generated_at="2026-06-29T10:00:00+00:00",
            status="missing_proof_refs",
            summary="Readiness source evidence exists, but browser proof refs are stale.",
            recommended_action="Dispatch readiness source-ref refresh before broad coding.",
            source_visible_labels=["browser", "web"],
            source_evidence_labels=["browser", "web"],
            proof_ref_labels=["web"],
            missing_source_evidence_labels=[],
            missing_proof_ref_labels=["browser"],
        )

        report = engine._build_action_readiness(created, created.state)

        assert report.status == "blocked"
        assert report.ready_to_act is False
        assert report.suggested_tool == "ask_user"
        assert report.suggested_label == "readiness_source_refs"
        assert report.issues[0].id == "readiness_source_ref_refresh_required"
        assert "POST /api/runs/" in report.recommended_action
        assert "/readiness-source-refs/refresh" in report.recommended_action
        assert "missing_proof=browser" in report.issues[0].evidence

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "ask_user"
        assert action["model_guard"] == "readiness_source_ref_refresh_required"
        assert action["guarded_tool"] == "model_action_selection"
        assert action["endpoint"] == f"/api/runs/{created.id}/readiness-source-refs/refresh"
        assert action["method"] == "POST"
        assert action["missing_proof_labels"] == ["browser"]
        assert created.state.action_context.selected_tool == "ask_user"
        assert created.state.action_context.readiness_source_ref_status == "missing_proof_refs"
        assert created.state.action_context.readiness_source_ref_missing_proof_labels == ["browser"]
        assert "source_refs status=missing_proof_refs" in created.state.action_context.compact_prompt
        assert "Dispatch readiness source-ref refresh" in created.state.action_context.compact_prompt
        assert "paused Ornith action selection" in created.state.model_interactions[-1].summary

    asyncio.run(run())

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
                '{"should_update": true, "proposed_goal": "Improve original project objective with sharper implementation constraints", '
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
        assert updated.state.proposed_goal == "Improve original project objective with sharper implementation constraints"
        assert updated.state.model_interactions[-1].kind == "goal"
        assert approvals[0]["action_kind"] == "goal_update"
        assert approvals[0]["payload"]["proposed_goal"] == "Improve original project objective with sharper implementation constraints"
        assert updated.state.goal_evolution.pending_count == 1
        assert updated.state.goal_evolution.latest_decision.source == "manual_review"
        assert updated.state.goal_evolution.latest_decision.proposed_goal == "Improve original project objective with sharper implementation constraints"

    asyncio.run(run())


def test_goal_review_rejects_tactical_model_rewrite(tmp_path: Path) -> None:
    class TacticalGoalReviewModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            prompt = messages[-1]["content"]
            assert "Preserve the original objective anchors" in prompt
            return '{"should_update": true, "proposed_goal": "Fix tests", "reason": "Tests are failing now."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = TacticalGoalReviewModel()  # type: ignore[assignment]
        created = engine.store.create_run(
            "Improve AgentOrinth harness for long Ornith coding tasks",
            "Goal tactical guard",
            str(tmp_path),
            [],
        )

        updated = await engine.review_goal(created.id)
        approvals = engine.store.list_approvals(created.id)

        assert updated.status == "queued"
        assert updated.state.goal == "Improve AgentOrinth harness for long Ornith coding tasks"
        assert updated.state.proposed_goal is None
        assert approvals == []
        assert updated.state.goal_evolution.unchanged_count == 1
        assert updated.state.goal_evolution.latest_decision.status == "unchanged"
        assert "Rejected unsafe goal proposal" in updated.state.goal_evolution.latest_decision.reason
        assert "too short" in updated.state.goal_evolution.latest_decision.reason

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


def test_failure_records_keep_compact_command_context(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Classify syntax failures", "Failure context", str(tmp_path), [])
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

    async def record() -> None:
        await engine._record_tool_result(run.id, result)

    asyncio.run(record())
    updated = engine.store.get_run(run.id)
    failure = updated.state.failure_records[0]

    assert failure.kind == "syntax_error"
    assert failure.command == "python broken.py"
    assert failure.returncode == 1
    assert "SyntaxError" in failure.evidence_excerpt
    assert "super-secret" not in failure.evidence_excerpt
    assert "[REDACTED]" in failure.evidence_excerpt
    assert "patch the smallest affected file" in failure.recovery_hint
    assert any("cmd=python broken.py" in item and "rc=1" in item for item in updated.state.action_context.failure_ledger)

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


def test_missing_artifact_verification_does_not_queue_compile_retry(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Create AgentOrnith_use_cases.pptx.",
            "PPT artifact",
            str(tmp_path),
            ["AgentOrnith_use_cases.pptx exists in the run workspace root."],
        )
        command = (
            "python -c \"from pathlib import Path; "
            "files=sorted(Path('.').rglob('*.pptx')); assert files, 'no pptx files found'\""
        )

        await engine._record_tool_result(
            created.id,
            ToolResult(False, "shell", "exit 1: AssertionError: no pptx files found", {"command": command}),
            action={"tool": "shell", "args": {"command": command}},
        )
        updated = engine.store.get_run(created.id)

        assert updated.state.post_action_retries.decision_count == 0

    asyncio.run(run())


def test_legacy_missing_artifact_retry_is_ignored(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Create AgentOrnith_use_cases.pptx.",
            "PPT artifact",
            str(tmp_path),
            ["AgentOrnith_use_cases.pptx exists in the run workspace root."],
        )
        created.state.step_count = 1
        created.state.post_action_retries.decisions.append(
            PostActionRetryDecisionRecord(
                id="post-retry-legacy",
                status="pending",
                trigger_tool="shell",
                trigger_summary=(
                    "exit 1: python -c \"files=sorted(Path('.').rglob('*.pptx')); "
                    "assert files, 'no pptx files found'\""
                ),
                selected_tool="shell",
                selected_action="Run compile diagnostic.",
                command_hint="python -m compileall backend\\app",
                reason="Legacy retry created before artifact-missing handling.",
            )
        )
        created = engine.store.update_run(created.id, status="queued", state=created.state)

        action = await engine._choose_action(created, "compact context")

        assert not (
            action["tool"] == "shell"
            and action.get("args", {}).get("command") == "python -m compileall backend\\app"
        )

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
        final = engine.store.get_run(created.id)
        resolved = final.state.post_action_retries

        assert resolved.resolved_count == 1
        assert resolved.pending_count == 0
        assert resolved.latest_decision.status == "resolved"
        assert resolved.latest_decision.resolution_tool == "shell"
        assert resolved.latest_decision.resolution_ok is True
        assert any(
            "retry:run_tests->shell:test_failure" in item and "Compile check passed." in item
            for item in final.state.action_context.resolved_failure_ledger
        )
        assert final.state.handoff_summary.action_context.resolved_failure_ledger == final.state.action_context.resolved_failure_ledger
        assert "resolved_failure_ledger=retry:run_tests->shell:test_failure" in final.state.action_context.compact_prompt

    asyncio.run(run())





def test_desktop_effect_proof_preview_tracks_latest_action_and_snapshot(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run("Use supervised desktop control", "Desktop proof preview", str(tmp_path), [])

    empty = engine.get_desktop_effect_proof_preview(created.id)
    assert empty["status"] == "not_required"
    assert empty["requires_attention"] is False

    created.state.tool_calls.append(
        ToolCallRecord(
            id="desktop-click-1",
            name="desktop_click",
            ok=True,
            summary="Clicked the visible Save button.",
            created_at="2026-06-29T10:00:00+00:00",
        )
    )
    engine.store.update_run(created.id, state=created.state)

    needs = engine.get_desktop_effect_proof_preview(created.id)
    assert needs["status"] == "needs_proof"
    assert needs["requires_attention"] is True
    assert needs["latest_action_id"] == "desktop-click-1"
    assert needs["latest_action_tool"] == "desktop_click"
    assert "Clicked the visible Save button" in needs["latest_action_summary"]
    assert needs["proof_tool"] == ""
    assert any("action=desktop_click" in item for item in needs["ledger"])

    updated = engine.store.get_run(created.id)
    updated.state.tool_calls.append(
        ToolCallRecord(
            id="desktop-shot-1",
            name="desktop_screenshot",
            ok=True,
            summary="Captured the post-click desktop state.",
            created_at="2026-06-29T10:01:00+00:00",
        )
    )
    updated.state.desktop_snapshots.append(
        DesktopSnapshot(
            id="desktop-proof",
            timestamp="2026-06-29T10:01:00+00:00",
            title="Desktop screenshot",
            path=str(tmp_path / "desktop-proof.png"),
            summary="Captured the post-click desktop state.",
        )
    )
    engine.store.update_run(created.id, state=updated.state)

    proven = engine.get_desktop_effect_proof_preview(created.id)
    assert proven["status"] == "proof_available"
    assert proven["requires_attention"] is False
    assert proven["proof_tool"] == "desktop_screenshot"
    assert proven["proof_snapshot"]["id"] == "desktop-proof"
    assert any("snapshot=desktop-proof" in item for item in proven["ledger"])

def test_operator_dispatch_runs_desktop_effect_proof(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Use supervised desktop control", "Desktop proof queue", str(tmp_path), [])
        created.state.step_count = 1
        created.state.tool_calls.append(
            ToolCallRecord(
                id="desktop-click-1",
                name="desktop_click",
                ok=True,
                summary="Approved supervised desktop click recorded.",
            )
        )
        engine.store.update_run(created.id, status="paused", state=created.state)
        await engine.recover_stale_runs()
        queue = engine.get_operator_action_queue(limit=50)
        item = next(item for item in queue.items if item.run_id == created.id and item.ui_target == "desktop_effect_proof")

        async def fake_execute(_run, action):  # noqa: ANN001
            assert action["tool"] == "desktop_screenshot"
            return ToolResult(
                True,
                "desktop_screenshot",
                "Captured supervised desktop screenshot.",
                {"path": str(tmp_path / "desktop-proof.png")},
                desktop_snapshots=[
                    DesktopSnapshot(
                        id="desktop-proof",
                        timestamp="2026-06-29T10:00:00+00:00",
                        title="Desktop screenshot",
                        path=str(tmp_path / "desktop-proof.png"),
                        summary="Captured supervised desktop screenshot.",
                    )
                ],
            )

        engine._execute_action = fake_execute  # type: ignore[method-assign]
        result = await engine.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item.id, decision="dispatch", confirmed=True)
        )
        updated = engine.store.get_run(created.id)

        assert result.status == "dispatched"
        assert result.action_taken == "desktop_effect_proof"
        assert updated.state.tool_calls[-1].name == "desktop_screenshot"
        assert updated.state.tool_calls[-1].args["model_guard"] == "desktop_effect_unverified"
        assert updated.state.desktop_snapshots[-1].id == "desktop-proof"
        assert "desktop_effect_check_required" not in updated.state.action_context.compact_prompt
        assert updated.state.next_step == "Review desktop screenshot proof before any further desktop click/type."
        refreshed_queue = result.queue.model_dump()
        assert not any(
            queue_item["run_id"] == created.id and queue_item["ui_target"] == "desktop_effect_proof"
            for queue_item in refreshed_queue["items"]
        )

    asyncio.run(run())

def test_operator_dispatch_refreshes_stale_desktop_effect_proof_metadata_without_new_capture(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Use supervised desktop control", "Desktop proof metadata repair", str(tmp_path), [])
        created.state.step_count = 1
        created.state.tool_calls.extend(
            [
                ToolCallRecord(
                    id="desktop-click-1",
                    name="desktop_click",
                    ok=True,
                    summary="Approved supervised desktop click recorded.",
                    created_at="2026-06-29T10:00:00+00:00",
                ),
                ToolCallRecord(
                    id="desktop-shot-1",
                    name="desktop_screenshot",
                    ok=True,
                    summary="Captured supervised desktop screenshot.",
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
                summary="Captured supervised desktop screenshot.",
            )
        )
        stale_report = DesktopEffectProofReport(
            run_id=created.id,
            generated_at="2026-06-29T10:00:30+00:00",
            status="needs_proof",
            requires_attention=True,
            latest_action_id="desktop-click-1",
            latest_action_tool="desktop_click",
            latest_action_summary="Approved supervised desktop click recorded.",
            recommended_action="Stale report still thinks proof is missing.",
        )
        created.state.desktop_effect_proof = stale_report
        created.state.handoff_summary.desktop_effect_proof = stale_report
        engine.store.update_run(created.id, status="paused", state=created.state)

        report = await engine.recover_stale_runs()
        queue = report["operator_action_queue"]
        item = next(
            item
            for item in queue["items"]
            if item["run_id"] == created.id and item["ui_target"] == "desktop_effect_proof"
        )

        async def fail_execute(_run, _action):  # noqa: ANN001
            raise AssertionError("metadata repair should not capture another desktop screenshot")

        engine._execute_action = fail_execute  # type: ignore[method-assign]
        result = await engine.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=True)
        )
        updated = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id, limit=20)

        assert result.status == "dispatched"
        assert result.action_taken == "desktop_effect_proof"
        assert [call.name for call in updated.state.tool_calls].count("desktop_screenshot") == 1
        assert any(event["kind"] == "desktop_effect_proof_repaired" for event in events)
        assert not any(event["kind"] == "desktop_effect_proof_captured" for event in events)
        assert updated.state.desktop_effect_proof.status == "proof_available"
        assert updated.state.handoff_summary.desktop_effect_proof.proof_snapshot is not None
        assert updated.state.handoff_summary.desktop_effect_proof.proof_snapshot.id == "desktop-proof"
        assert updated.state.desktop_effect_proof_repairs.latest_outcome == "metadata_refreshed"
        assert updated.state.desktop_effect_proof_repairs.metadata_refreshed_count == 1
        assert updated.state.desktop_effect_proof_repairs.capture_completed_count == 0
        assert updated.state.handoff_summary.desktop_effect_proof_repairs.latest_outcome == "metadata_refreshed"
        assert not any(
            queue_item.run_id == created.id and queue_item.ui_target == "desktop_effect_proof"
            for queue_item in result.queue.items
        )

    asyncio.run(run())

def test_supervisor_queues_report_integrity_desktop_effect_proof_repair(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Use supervised desktop control", "Desktop proof integrity queue", str(tmp_path), [])
        stale_report = DesktopEffectProofReport(
            run_id=created.id,
            generated_at="2026-06-29T10:00:00+00:00",
            status="not_required",
            requires_attention=False,
            recommended_action="No desktop proof required yet.",
        )
        created.state.desktop_effect_proof = stale_report
        created.state.handoff_summary.desktop_effect_proof = stale_report
        created.state.tool_calls.append(
            ToolCallRecord(
                id="desktop-click-1",
                name="desktop_click",
                ok=True,
                summary="Approved supervised desktop click recorded after the stale proof preview.",
            )
        )
        engine.store.update_run(created.id, status="paused", state=created.state)

        report = await engine.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        proof_items = [item for item in queue["items"] if item["run_id"] == created.id and item["reason"] == "desktop_effect_proof"]

        assert report["desktop_effect_proof_attention_count"] == 1
        assert entry["desktop_effect_proof_requires_attention"] is True
        assert entry["report_integrity_status"] == "needs_refresh"
        assert entry["report_integrity_desktop_effect_proof_requires_attention"] is True
        assert "handoff.desktop_effect_proof.status" in entry["report_integrity_desktop_effect_proof_detail"]
        assert queue["desktop_effect_proof_count"] == 1
        assert proof_items
        item = proof_items[0]
        assert item["endpoint"] == f"/api/runs/{created.id}/desktop-effect/verify"
        assert item["method"] == "POST"
        assert item["ui_target"] == "desktop_effect_proof"
        assert any("report_integrity=needs_refresh" in detail for detail in item["details"])
        assert any("handoff.desktop_effect_proof.status" in detail for detail in item["details"])

    asyncio.run(run())
def test_choose_action_requires_desktop_effect_check_before_next_click(tmp_path: Path) -> None:
    class DesktopClickModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            return '{"tool":"desktop_click","args":{"x":120,"y":240},"thought_summary":"Click again after approval."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = DesktopClickModel()  # type: ignore[assignment]
        created = engine.store.create_run("Use supervised desktop control", "Desktop effect guard", str(tmp_path), [])
        created.state.step_count = 1
        created.state.tool_calls.append(
            ToolCallRecord(
                id="desktop-click-1",
                name="desktop_click",
                ok=True,
                summary="Approved supervised desktop click recorded.",
            )
        )

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "desktop_screenshot"
        assert action["model_guard"] == "desktop_effect_unverified"
        assert action["guarded_tool"] == "desktop_click"
        assert action["guarded_desktop_tool"] == "desktop_click"
        assert "before another desktop_click" in action["thought_summary"]
        assert "desktop_effect_check_required" in created.state.action_context.compact_prompt
        assert any(
            "desktop_effect_unverified" in item and "after=desktop_click" in item
            for item in created.state.action_context.model_guard_ledger
        )
        assert created.state.model_interactions[-1].fallback_used is True
        assert "unverified desktop action" in created.state.model_interactions[-1].summary

    asyncio.run(run())


def test_choose_action_allows_desktop_click_after_effect_check(tmp_path: Path) -> None:
    class DesktopClickModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            return '{"tool":"desktop_click","args":{"x":120,"y":240},"thought_summary":"Click after screenshot proof."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = DesktopClickModel()  # type: ignore[assignment]
        created = engine.store.create_run("Use supervised desktop control", "Desktop effect cleared", str(tmp_path), [])
        created.state.step_count = 1
        created.state.tool_calls.extend(
            [
                ToolCallRecord(
                    id="desktop-click-1",
                    name="desktop_click",
                    ok=True,
                    summary="Approved supervised desktop click recorded.",
                ),
                ToolCallRecord(
                    id="desktop-shot-1",
                    name="desktop_screenshot",
                    ok=True,
                    summary="Captured supervised desktop screenshot.",
                ),
            ]
        )

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "desktop_click"
        assert "model_guard" not in action
        assert "desktop_effect_check_required" not in created.state.action_context.compact_prompt

    asyncio.run(run())

def test_model_guard_ledger_survives_tool_result_and_handoff(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Record guard", "Guard ledger", str(tmp_path), ["Tests pass"])
        action = {
            "tool": "run_tests",
            "args": {"command": "pytest -q"},
            "thought_summary": "Re-anchor on current verify task.",
            "model_guard": "current_task_mismatch",
            "guarded_tool": "patch_propose",
            "current_task_id": "task-verify",
            "current_task_kind": "verify",
            "guard_reason": "verify_task_selected_edit_tool",
        }

        await engine._record_tool_result(
            created.id,
            ToolResult(True, "run_tests", "Tests passed.", {"command": "pytest -q"}),
            action=action,
        )
        updated = engine.store.get_run(created.id)

        latest_args = updated.state.tool_calls[-1].args
        assert latest_args["model_guard"] == "current_task_mismatch"
        assert latest_args["guarded_tool"] == "patch_propose"
        assert any(
            "current_task_mismatch" in item
            and "from=patch_propose" in item
            and "reason=verify_task_selected_edit_tool" in item
            for item in updated.state.action_context.model_guard_ledger
        )
        assert updated.state.handoff_summary.action_context.model_guard_ledger == updated.state.action_context.model_guard_ledger
        assert "model_guards=current_task_mismatch" in updated.state.action_context.compact_prompt

    asyncio.run(run())


def test_edit_evidence_ledger_survives_patch_result_handoff_and_task(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Record edit evidence", "Edit evidence", str(tmp_path), ["Patch app.py safely"])
        created.state.task_graph = [
            TaskNode(
                id="task-edit",
                title="Patch app.py safely",
                status="pending",
                kind="edit",
            )
        ]
        created.state.current_task_id = "task-edit"
        patch = PatchProposal(
            id="patch-1",
            title="Patch app.py safely",
            summary="Use the safer implementation.",
            files=["app.py"],
            diff="--- a/app.py\n+++ b/app.py\n@@\n-old\n+new\n",
            status="pending",
        )

        await engine._record_tool_result(
            created.id,
            ToolResult(True, "patch_propose", "Patch proposal recorded.", {"files": ["app.py"]}, patch_proposals=[patch]),
            action={"tool": "patch_propose", "args": {"files": ["app.py"]}, "thought_summary": "Propose patch."},
        )
        updated = engine.store.get_run(created.id)
        task = updated.state.task_graph[0]

        assert any("edit:evidence | patch_propose:pending:patch-1" in item for item in task.evidence)
        assert task.notes.startswith("Latest edit evidence: edit:evidence | patch_propose")
        assert any("patch:pending:patch-1:app.py" in item for item in updated.state.action_context.edit_evidence_ledger)
        assert updated.state.handoff_summary.action_context.edit_evidence_ledger == updated.state.action_context.edit_evidence_ledger
        assert "edit_evidence=patch:pending:patch-1:app.py" in updated.state.action_context.compact_prompt

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


def test_recovery_plan_act_milestone_executes_instead_of_self_pausing(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run("Execute recovery", "Recovery act", str(tmp_path), [])
        created.state.recovery_plan.status = "active"
        created.state.recovery_plan.tool = "shell"
        created.state.recovery_plan.failure_kind = "timeout"
        created.state.recovery_plan.summary = "Repeated shell timeout."
        created.state.recovery_plan.next_action = "Run narrower diagnostic."
        created.state.recovery_plan.steps = ["Run narrower diagnostic.", "Checkpoint recovery result."]
        created.state.current_plan = created.state.recovery_plan.steps
        created.state.task_graph = engine._tasks_from_plan(created.state.current_plan, [])
        created.state.current_task_id = created.state.task_graph[0].id
        created.state.next_step = created.state.recovery_plan.next_action
        created.state.milestone = "act"
        engine.store.update_run(created.id, status="running", state=created.state)

        async def fake_choose(_run, _memory_text):  # noqa: ANN001
            return {"tool": "shell", "args": {"command": "echo recovery"}, "thought_summary": "Run narrower diagnostic."}

        async def fake_execute(_run, action):  # noqa: ANN001
            return ToolResult(True, action["tool"], "exit 0: recovery", action.get("args", {}))

        engine._choose_action = fake_choose  # type: ignore[method-assign]
        engine._execute_action = fake_execute  # type: ignore[method-assign]

        await engine._run_one_milestone(created.id)
        updated = engine.store.get_run(created.id)

        assert updated.status == "running"
        assert updated.state.milestone == "verify"
        assert updated.state.recovery_plan.status == "resolved"
        assert updated.state.tool_calls[-1].name == "shell"

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


def test_manual_resume_consumes_startup_recovered_handoff_blocker(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Resume after backend restart",
            "Startup resume",
            str(tmp_path),
            ["Tests pass"],
        )
        engine_one.store.update_run(created.id, status="running", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)

        assert report["recovered"] == 1
        assert recovered.status == "paused"
        assert any("resume explicitly from handoff" in blocker for blocker in recovered.state.blockers)

        updated = await engine_two.resume_run(created.id)
        engine_two._cancel_task(created.id)
        resumed = engine_two.store.get_run(created.id)
        events = engine_two.store.list_events(created.id)
        preflight = next(event for event in events if event["kind"] == "resume_preflight")

        assert updated.status == "queued"
        assert not any("resume explicitly from handoff" in blocker for blocker in resumed.state.blockers)
        assert "Manual resume accepted the recovered startup handoff blocker." in resumed.state.facts_learned
        assert preflight["data"]["accepted"] is True
        assert preflight["data"]["source"] == "manual"

    asyncio.run(run())


def test_manual_resume_consumes_orphan_startup_waiting_approval_blocker(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Resume orphan approval state",
            "Orphan approval",
            str(tmp_path),
            ["Tests pass"],
        )
        created.state.blockers.append(
            "Supervisor found waiting_approval status without a pending approval after startup."
        )
        created.state.next_step = "Review replay and replan before continuing."
        engine.store.update_run(created.id, status="paused", state=created.state)

        updated = await engine.resume_run(created.id)
        engine._cancel_task(created.id)
        resumed = engine.store.get_run(created.id)
        events = engine.store.list_events(created.id)
        preflight = next(event for event in events if event["kind"] == "resume_preflight")

        assert updated.status == "queued"
        assert "Supervisor found waiting_approval status without a pending approval after startup." not in resumed.state.blockers
        assert "Manual resume cleared recovered waiting_approval state after confirming no pending approvals." in resumed.state.facts_learned
        assert preflight["data"]["accepted"] is True
        assert preflight["data"]["source"] == "manual"

    asyncio.run(run())


def test_manual_resume_clears_stale_loop_step_limit_after_cap_increase(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path, max_loop_steps=32)
        created = engine.store.create_run(
            "Resume after loop cap increase",
            "Loop cap resume",
            str(tmp_path),
            ["Tests pass"],
        )
        created.state.step_count = 8
        created.state.blockers.append("Reached MAX_LOOP_STEPS.")
        created.state.next_step = "Ask user whether to continue."
        engine.store.update_run(created.id, status="blocked", state=created.state)

        updated = await engine.resume_run(created.id)
        engine._cancel_task(created.id)
        resumed = engine.store.get_run(created.id)
        preflight = next(event for event in engine.store.list_events(created.id) if event["kind"] == "resume_preflight")

        assert updated.status == "queued"
        assert "Reached MAX_LOOP_STEPS." not in resumed.state.blockers
        assert resumed.state.next_step != "Ask user whether to continue."
        assert "Resume cleared stale MAX_LOOP_STEPS blocker after the configured loop cap increased." in resumed.state.facts_learned
        assert preflight["data"]["accepted"] is True

    asyncio.run(run())


def test_approving_objective_readiness_ask_user_resolves_waiting_outcome(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        created = engine.store.create_run(
            "Resolve objective readiness approval",
            "Objective approval",
            str(tmp_path),
            [],
        )
        created.state.objective_readiness_proof_outcomes.append(
            ObjectiveReadinessProofOutcome(
                id="obj-proof-waiting",
                item_id="patch_first_editing",
                tool="ask_user",
                evidence_label="edit",
                strategy="patch_review",
                outcome="waiting_approval",
                ok=False,
                summary="Approval required before patch-first proof.",
            )
        )
        engine.store.update_run(created.id, status="waiting_approval", state=created.state)
        approval = engine.store.create_approval(
            created.id,
            "ask_user",
            {
                "tool_name": "ask_user",
                "args": {
                    "question": "Objective readiness proof for patch_first_editing requires supervised approval.",
                    "reason": "Patch proposal path needs approval.",
                },
            },
            "Objective readiness proof for patch_first_editing requires supervised approval.",
        )

        updated = await engine.approve_action(created.id, int(approval["id"]))
        engine._cancel_task(created.id)
        resolved = engine.store.get_run(created.id)
        latest = resolved.state.objective_readiness_proof_outcomes[-1]

        assert updated.status in {"queued", "paused", "waiting_approval"}
        assert latest.item_id == "patch_first_editing"
        assert latest.tool == "ask_user"
        assert latest.outcome == "verified"
        assert "Objective readiness approval resolved for patch_first_editing." in resolved.state.facts_learned

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

def test_supervisor_queues_promotion_audit_verification_attention(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("old\n", encoding="utf-8")
        (workspace / "README.md").write_text("new\n", encoding="utf-8")
        created = engine_one.store.create_run(
            "Gate source promotion",
            "Promotion audit attention",
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
        await engine_one.request_workspace_promotion(created.id)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        promotion_items = [item for item in queue["items"] if item["reason"].startswith("promotion_audit")]

        assert report["promotion_audit_attention_count"] == 1
        assert entry["promotion_audit_requires_attention"] is True
        assert entry["promotion_audit"]["status"] == "needs_verification"
        assert "promotion_audit" in entry["operator_attention_reasons"]
        assert promotion_items
        assert promotion_items[0]["ui_target"] == "promotion_verification"
        assert promotion_items[0]["endpoint"] == f"/api/runs/{created.id}/promotion-audit/verify"
        assert queue["promotion_count"] == 1
        assert queue["promotion_approval_count"] == 0

    asyncio.run(run())


def test_operator_queue_marks_workspace_promote_approval_as_promotion_gate(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("old\n", encoding="utf-8")
        (workspace / "README.md").write_text("new\n", encoding="utf-8")
        created = engine_one.store.create_run(
            "Approve source promotion",
            "Promotion approval gate",
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
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-promotion-gate-test",
                name="shell",
                args={"command": "python -m pytest backend/tests/test_workspace.py -q"},
                ok=True,
                summary="pytest passed before source promotion.",
                created_at="2026-06-28T08:05:00+00:00",
            )
        )
        engine_one.store.update_run(created.id, status="paused", state=created.state)
        await engine_one.request_workspace_promotion(created.id)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        queue = report["operator_action_queue"]
        item = next(item for item in queue["items"] if item["reason"] == "approval")

        assert item["approval_kind"] == "workspace_promote"
        assert item["promotion_gate"] is True
        assert queue["approval_count"] == 1
        assert queue["promotion_approval_count"] == 1

    asyncio.run(run())

def test_supervisor_queues_promotion_audit_unresolved_approval_history(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("old\n", encoding="utf-8")
        (workspace / "README.md").write_text("new\n", encoding="utf-8")
        created = engine_one.store.create_run(
            "Resolve reviewed source promotion approval",
            "Promotion audit approval history",
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
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-promotion-history-test",
                name="shell",
                args={"command": "python -m pytest backend/tests/test_workspace.py -q"},
                ok=True,
                summary="pytest passed before source promotion.",
                created_at="2026-06-27T08:05:00+00:00",
            )
        )
        engine_one.store.update_run(created.id, status="paused", state=created.state)
        await engine_one.request_workspace_promotion(created.id)
        approval = engine_one.store.list_approvals(created.id, status="pending")[0]
        review_event = engine_one.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator reviewed workspace promotion approval.",
            {
                "decision": "open",
                "operator_action": {
                    "id": f"{created.id}:approval:workspace_promote",
                    "run_id": created.id,
                    "title": created.title,
                    "reason": "approval",
                    "action": "Review pending workspace promotion approval.",
                    "ui_target": "approval",
                    "approval_id": approval["id"],
                },
            },
        )

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        promotion_items = [
            item
            for item in queue["items"]
            if item["reason"] == "promotion_audit_promotion_approval_history_unresolved"
        ]

        assert entry["promotion_audit_requires_attention"] is True
        assert entry["promotion_audit"]["status"] == "ready"
        assert entry["promotion_audit"]["unresolved_approval_history_count"] == 1
        assert "promotion_audit" in entry["operator_attention_reasons"]
        assert promotion_items
        assert len(promotion_items) == 1
        item = promotion_items[0]
        assert item["ui_target"] == "approval"
        assert item["approval_id"] == approval["id"]
        assert item["approval_kind"] == "workspace_promote"
        assert item["promotion_gate"] is True
        assert item["endpoint"] == f"/api/runs/{created.id}/approvals"
        assert f"approval_id={approval['id']}" in item["details"]
        assert queue["promotion_count"] == 1
        assert queue["promotion_approval_count"] == 1

        opened = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="open")
        )
        assert opened.status == "reviewed"
        assert opened.action_taken == "open"
        assert opened.event_kind == "operator_action_reviewed"
        review_events = [
            event
            for event in engine_two.store.list_events(created.id)
            if event["kind"] == "operator_action_reviewed"
        ]
        assert review_events[-1]["data"]["operator_action"]["approval_id"] == approval["id"]
        assert review_events[0]["id"] == review_event["id"]

    asyncio.run(run())

def test_operator_dispatch_runs_promotion_audit_verification(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("old\n", encoding="utf-8")
        (workspace / "README.md").write_text("new\n", encoding="utf-8")
        created = engine_one.store.create_run(
            "Dispatch source promotion verification",
            "Promotion audit dispatch",
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
        await engine_one.request_workspace_promotion(created.id)
        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        item = next(
            item
            for item in report["operator_action_queue"]["items"]
            if item["ui_target"] == "promotion_verification"
        )

        unconfirmed = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=False)
        )
        assert unconfirmed.status == "requires_confirmation"

        dispatched = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=True)
        )
        updated = engine_two.store.get_run(created.id)

        assert dispatched.status == "dispatched"
        assert dispatched.action_taken == "promotion_verification"
        assert updated.state.promotion_audit.status == "ready"
        assert updated.state.promotion_audit.ready_to_promote is True
        assert updated.state.tool_calls[-1].ok is True
        assert updated.state.tool_calls[-1].name == "shell"
        assert "compileall" in str(updated.state.tool_calls[-1].args.get("command"))
        assert dispatched.queue.promotion_count == 0
        event_kinds = [event["kind"] for event in engine_two.store.list_events(created.id)]
        assert "promotion_audit_verification" in event_kinds
        assert "operator_action_dispatched" in event_kinds

    asyncio.run(run())


def test_operator_dispatch_requests_patch_apply_approval_for_active_promotion_repair(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "broken.py").write_text("def broken():\n    return 'old'\n", encoding="utf-8")
        (workspace / "broken.py").write_text("def broken():\n    return 'new'\n", encoding="utf-8")
        created = engine_one.store.create_run(
            "Approve active promotion repair patch",
            "Promotion repair patch approval",
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
        run_record = engine_one.store.get_run(created.id)
        run_record.state.promotion_verification = PromotionVerificationReport(
            run_id=created.id,
            generated_at="2026-06-27T08:00:00+00:00",
            status="needs_retry",
            attempt_count=1,
            failed_count=1,
            latest_failed_command="python -m compileall .",
            latest_failure_kind="syntax_error",
            latest_suspected_file="broken.py",
            latest_repair_hint="Repair the broken Python file.",
            next_command="python -m py_compile broken.py",
            summary="Promotion verification failed for broken.py.",
            recommended_action="Repair broken.py before promotion.",
            latest_attempt=PromotionVerificationAttemptRecord(
                command="python -m compileall .",
                ok=False,
                failure_kind="syntax_error",
                suspected_file="broken.py",
                suspected_line=2,
                repair_hint="Repair the broken Python file.",
                evidence_excerpt="SyntaxError: invalid syntax",
                created_at="2026-06-27T08:00:00+00:00",
            ),
            attempts=[
                PromotionVerificationAttemptRecord(
                    command="python -m compileall .",
                    ok=False,
                    failure_kind="syntax_error",
                    suspected_file="broken.py",
                    suspected_line=2,
                    repair_hint="Repair the broken Python file.",
                    evidence_excerpt="SyntaxError: invalid syntax",
                    created_at="2026-06-27T08:00:00+00:00",
                )
            ],
        )
        run_record.state.patch_proposals.append(
            PatchProposal(
                id="patch-repair",
                title="Repair broken.py",
                summary="Apply the active promotion repair patch.",
                files=["broken.py"],
                diff="--- a/broken.py\n+++ b/broken.py\n@@ -1,2 +1,2 @@\n def broken():\n-    return 'new'\n+    return 'fixed'\n",
            )
        )
        engine_one.store.update_run(created.id, status="paused", state=run_record.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        item = next(
            item
            for item in report["operator_action_queue"]["items"]
            if item["ui_target"] == "patch_apply_approval"
        )

        assert item["endpoint"] == f"/api/runs/{created.id}/patches/patch-repair/apply"
        assert item["method"] == "POST"
        assert item["promotion_gate"] is True
        assert report["operator_action_queue"]["promotion_count"] == 1
        assert report["operator_action_queue"]["promotion_approval_count"] == 1

        unconfirmed = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=False)
        )
        assert unconfirmed.status == "requires_confirmation"

        dispatched = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=True)
        )
        approvals = engine_two.store.list_approvals(created.id, status="pending")
        updated = engine_two.store.get_run(created.id)

        assert dispatched.status == "dispatched"
        assert dispatched.action_taken == "patch_apply_approval"
        assert updated.status == "waiting_approval"
        assert len(approvals) == 1
        assert approvals[0]["action_kind"] == "patch_apply"
        assert approvals[0]["payload"]["args"]["patch_id"] == "patch-repair"
        assert approvals[0]["payload"]["args"]["diff"].startswith("--- a/broken.py")
        assert dispatched.queue.approval_count >= 1
        assert dispatched.queue.promotion_approval_count >= 1
        event_kinds = [event["kind"] for event in engine_two.store.list_events(created.id)]
        assert "approval_required" in event_kinds
        assert "operator_action_dispatched" in event_kinds

    asyncio.run(run())



def test_operator_dispatch_requests_patch_rollback_approval_for_self_scaffold_review(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "app.py").write_text("print('new')\n", encoding="utf-8")
        manifest_path = tmp_path / "rollback-manifest.json"
        manifest_path.write_text("{}\n", encoding="utf-8")
        created = engine_one.store.create_run(
            "Review rollback intent before broad autonomy",
            "Self scaffold rollback approval",
            str(workspace),
            [],
            tool_profile="ornith_self_scaffold",
        )
        created.state.patch_applications.append(
            PatchApplication(
                id="apply-roll-1",
                patch_id="patch-roll-1",
                status="applied",
                files=["app.py"],
                backup_id="backup-roll-1",
                manifest_path=str(manifest_path),
                summary="Applied patch-roll-1 to app.py.",
                applied_at="2026-06-29T00:00:00+00:00",
            )
        )
        engine_one.store.update_run(created.id, status="paused", state=created.state)
        engine_one.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator accepted self-scaffold edit evidence and requested guarded rollback posture.",
            {
                "operator_action": {
                    "ui_target": "self_scaffold",
                    "reason": "self_scaffold",
                    "action": "Review scaffold edit evidence.",
                },
                "self_scaffold_review": {
                    "status": "needs_review",
                    "change_count": 1,
                    "guard_count": 0,
                    "reviewed_change_count": 1,
                    "reviewed_change_ids": ["edit_evidence:0:patch-apply-applied-patch-roll-1-app-py"],
                    "remaining_goal_review": False,
                },
            },
        )

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        item = next(
            item
            for item in queue["items"]
            if item["reason"] == "self_scaffold_rollback"
        )

        assert report["self_scaffold_rollback_attention_count"] == 1
        assert entry["self_scaffold_rollback_requires_attention"] is True
        assert entry["self_scaffold_rollback_patch_count"] == 1
        assert "self_scaffold_rollback" in entry["operator_attention_reasons"]
        assert entry["operator_attention_action"] == entry["self_scaffold_rollback_action"]
        assert queue["self_scaffold_rollback_count"] == 1
        assert item["ui_target"] == "patch_rollback_approval"
        assert item["approval_kind"] == "patch_rollback"
        assert item["method"] == "POST"
        assert item["endpoint"] == f"/api/runs/{created.id}/patches/patch-roll-1/rollback"
        assert "no_auto_mutation=true" in item["details"]

        unconfirmed = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=False)
        )
        assert unconfirmed.status == "requires_confirmation"
        assert engine_two.store.list_approvals(created.id, status="pending") == []

        dispatched = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=True)
        )
        approvals = engine_two.store.list_approvals(created.id, status="pending")
        updated = engine_two.store.get_run(created.id)

        assert dispatched.status == "dispatched"
        assert dispatched.action_taken == "patch_rollback_approval"
        assert dispatched.message == "Patch rollback approval was requested; no rollback was executed."
        assert updated.status == "waiting_approval"
        assert updated.state.active_tool == "patch_rollback"
        assert len(approvals) == 1
        assert approvals[0]["action_kind"] == "patch_rollback"
        assert approvals[0]["payload"]["args"]["patch_id"] == "patch-roll-1"
        assert approvals[0]["payload"]["args"]["backup_id"] == "backup-roll-1"
        assert approvals[0]["payload"]["preview"]["requires_approval"] is True
        assert approvals[0]["payload"]["preview"]["mutation_automatic"] is False
        assert all(application.status != "rolled_back" for application in updated.state.patch_applications)
        assert dispatched.queue.approval_count >= 1
        event_kinds = [event["kind"] for event in engine_two.store.list_events(created.id)]
        assert "operator_action_dispatched" in event_kinds
        assert "approval_required" in event_kinds

    asyncio.run(run())


def test_promotion_audit_verification_uses_alternate_after_failed_attempt(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "README.md").write_text("old\n", encoding="utf-8")
        (workspace / "README.md").write_text("new\n", encoding="utf-8")
        created = engine_one.store.create_run(
            "Retry source promotion verification narrowly",
            "Promotion verification retry",
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
        await engine_one.request_workspace_promotion(created.id)
        prepared = engine_one.store.get_run(created.id)
        prepared.state.repo_map.test_commands = ["python -m py_compile missing_file_for_promotion_retry.py"]
        engine_one.store.update_run(prepared.id, status="paused", state=prepared.state)

        first = await engine_one.run_promotion_audit_verification(created.id)
        assert first.state.promotion_audit.status == "needs_verification"
        assert first.state.promotion_verification.status == "needs_retry"
        assert first.state.promotion_verification.failed_count == 1
        assert first.state.promotion_verification.next_command == "python -m compileall ."
        assert first.state.promotion_verification.latest_failure_kind == "missing_file"
        assert first.state.promotion_verification.latest_suspected_file == "missing_file_for_promotion_retry.py"
        assert "missing_file_for_promotion_retry.py" in first.state.promotion_verification.latest_repair_hint
        assert "missing_file_for_promotion_retry.py" in first.state.next_step

        second = await engine_one.run_promotion_audit_verification(created.id)
        report = second.state.promotion_verification
        events = [
            event
            for event in engine_one.store.list_events(created.id)
            if event["kind"] == "promotion_audit_verification"
        ]

        assert second.state.promotion_audit.status == "ready"
        assert second.state.promotion_audit.ready_to_promote is True
        assert report.status == "ready"
        assert report.attempt_count == 2
        assert report.failed_count == 1
        assert report.success_count == 1
        assert report.attempts[-1].command == "python -m compileall ."
        assert report.attempts[-1].selected_alternate is True
        assert events[0]["data"]["command"] == "python -m py_compile missing_file_for_promotion_retry.py"
        assert events[1]["data"]["command"] == "python -m compileall ."
        assert events[1]["data"]["selected_alternate"] is True

    asyncio.run(run())


def test_promotion_audit_verification_classifies_syntax_error(tmp_path: Path) -> None:
    async def run() -> None:
        engine = make_engine(tmp_path)
        source = tmp_path / "source"
        workspace = tmp_path / "workspace"
        source.mkdir()
        workspace.mkdir()
        (source / "broken.py").write_text("print('old')\n", encoding="utf-8")
        (workspace / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        created = engine.store.create_run(
            "Classify promotion syntax failure",
            "Promotion syntax classifier",
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
        prepared = engine.store.get_run(created.id)
        prepared.state.repo_map.test_commands = ["python -m py_compile broken.py"]
        engine.store.update_run(prepared.id, status="paused", state=prepared.state)

        updated = await engine.run_promotion_audit_verification(created.id)
        attempt = updated.state.promotion_verification.latest_attempt

        assert updated.state.promotion_verification.status == "needs_retry"
        assert attempt.failure_kind == "syntax_error"
        assert attempt.suspected_file.endswith("broken.py")
        assert attempt.suspected_line == 1
        assert "broken.py:1" in attempt.repair_hint
        assert "SyntaxError" in attempt.evidence_excerpt
        assert updated.state.promotion_verification.latest_repair_hint == attempt.repair_hint

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

def test_supervisor_queues_readiness_source_ref_gate_attention(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Improve AgentOrinth into a Codex-like long coding harness",
            "Readiness source refs attention",
            str(tmp_path),
            ["Readiness claim has source-visible proof"],
        )
        created.state.acceptance_evidence.append(
            AcceptanceCriterionEvidence(
                id="source-visible-readiness",
                criterion="Readiness claim has source-visible proof",
                status="verified",
                required_labels=["web", "browser"],
                matched_labels=["web", "browser"],
            )
        )
        created.state.web_sources.append(
            WebSource(
                id="web-source-ref-only",
                title="Source ref proof",
                url="https://example.test/source-ref",
                timestamp="2026-06-28T10:00:00+00:00",
                excerpt="Web source ref exists but browser ref is missing from proof history.",
                citation="[web-source-ref-only]",
            )
        )
        review_event = engine_one.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator accepted self-scaffold review.",
            {"self_scaffold_review": {"reviewed_change_count": 1, "reviewed_change_ids": ["guard-1"]}},
        )
        claim_event = engine_one.store.append_event(
            created.id,
            "readiness_claim",
            "Readiness claim accepted in older source-ref proof.",
            {"readiness_completion": {"can_claim_milestone": True}},
        )
        created.state.readiness_rehearsal = ReadinessRehearsalReport(
            run_id=created.id,
            generated_at="2026-06-28T10:01:00+00:00",
            status="passed",
            summary="Readiness rehearsal passed before browser ref was required.",
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
                    summary="Self-scaffold review was accepted.",
                    event_id=review_event["id"],
                    event_kind="operator_action_reviewed",
                ),
                ReadinessRehearsalStep(
                    id="post_review_handoff_alignment",
                    status="passed",
                    summary="Post-review handoff preserved goal and next action.",
                    evidence=["resume_prompt_next_action=True"],
                ),
                ReadinessRehearsalStep(
                    id="accepted_claim",
                    status="passed",
                    summary="Readiness claim was accepted.",
                    event_id=claim_event["id"],
                    event_kind="readiness_claim",
                ),
            ],
        )
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        source_ref_items = [item for item in queue["items"] if item["reason"] == "readiness_source_refs"]

        assert report["readiness_source_ref_attention_count"] == 1
        assert entry["readiness_source_refs_requires_attention"] is True
        assert entry["readiness_source_refs_missing_labels"] == ["browser"]
        assert entry["readiness_source_refs_count"] == 1
        assert entry["readiness_source_refs_labels"] == ["web"]
        assert entry["readiness_source_ref_preview_status"] == "missing_proof_refs"
        assert entry["readiness_source_ref_preview_missing_evidence_labels"] == ["browser"]
        assert entry["readiness_source_ref_preview_missing_proof_labels"] == ["browser"]
        assert entry["readiness_source_ref_preview_source_labels"] == ["web"]
        assert entry["readiness_source_ref_preview_proof_labels"] == ["web"]
        assert entry["readiness_source_ref_preview_proof_count"] == 1
        assert entry["readiness_source_ref_preview"]["status"] == "missing_proof_refs"
        assert "readiness_source_refs" in entry["operator_attention_reasons"]
        assert queue["readiness_source_ref_count"] == 1
        assert source_ref_items
        assert source_ref_items[0]["ui_target"] == "readiness_source_refs"
        assert source_ref_items[0]["endpoint"] == f"/api/runs/{created.id}/readiness-source-refs/refresh"
        assert source_ref_items[0]["method"] == "POST"
        assert "preview_status=missing_proof_refs" in source_ref_items[0]["details"]
        assert "missing_evidence=browser" in source_ref_items[0]["details"]
        assert "missing_proof=browser" in source_ref_items[0]["details"]
        assert "missing=browser" in source_ref_items[0]["details"]
        assert "proof_source_refs=1" in source_ref_items[0]["details"]
        assert "preview_proof_refs=1" in source_ref_items[0]["details"]

        preview = engine_two.get_readiness_source_ref_preview(created.id)
        assert preview["status"] == "missing_proof_refs"
        assert preview["source_visible_labels"] == ["browser", "web"]
        assert preview["source_evidence_labels"] == ["web"]
        assert preview["proof_ref_labels"] == ["web"]
        assert preview["missing_source_evidence_labels"] == ["browser"]
        assert preview["missing_proof_ref_labels"] == ["browser"]
        browser_row = next(item for item in preview["labels"] if item["label"] == "browser")
        assert browser_row["missing_from_source_evidence"] is True
        assert browser_row["missing_from_proof_history"] is True
        assert browser_row["proof_ref_count"] == 0

        refreshed_input = engine_two.store.get_run(created.id)
        refreshed_input.state.desktop_snapshots.append(
            DesktopSnapshot(
                id="browser-source-ref-now-present",
                title="Browser source ref proof",
                timestamp="2026-06-28T10:02:00+00:00",
                path=str(tmp_path / "browser-source-ref.png"),
                summary="Browser source ref now exists for readiness proof history.",
            )
        )
        engine_two.store.update_run(refreshed_input.id, status="queued", state=refreshed_input.state)
        dispatched = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=source_ref_items[0]["id"], decision="dispatch", confirmed=True)
        )
        refreshed = engine_two.store.get_run(created.id)

        assert dispatched.status == "dispatched"
        assert dispatched.action_taken == "readiness_source_refs_refresh"
        assert refreshed.state.readiness_proof_history.source_evidence_ref_count == 2
        assert refreshed.state.readiness_completion.source_visible_missing_ref_labels == []
        assert refreshed.state.handoff_summary.readiness_proof_history.source_evidence_ref_count == 2
        assert refreshed.state.handoff_summary.readiness_completion.source_visible_missing_ref_labels == []
        assert refreshed.state.readiness_source_ref_preview.status == "ready"
        assert refreshed.state.readiness_source_ref_preview.proof_ref_count == 2
        assert refreshed.state.handoff_summary.readiness_source_ref_preview.status == "ready"
        prompt, snapshot = engine_two.context_compiler.compile(
            refreshed,
            refreshed.state,
            MemoryContext(hits=[], warnings=[]),
            engine_two.store.list_events(created.id, limit=5),
        )
        assert "readiness_source_ref_preview" in snapshot.sections
        assert "Readiness source refs: ready" in prompt
        assert "missing_proof=none" in prompt
        assert dispatched.queue.readiness_source_ref_count == 0
        assert any(event["kind"] == "readiness_source_refs_refreshed" for event in engine_two.store.list_events(created.id))
        refreshed_preview = engine_two.get_readiness_source_ref_preview(created.id)
        assert refreshed_preview["status"] == "ready"
        assert refreshed_preview["source_evidence_labels"] == ["browser", "web"]
        assert refreshed_preview["proof_ref_labels"] == ["browser", "web"]
        assert refreshed_preview["missing_source_evidence_labels"] == []
        assert refreshed_preview["missing_proof_ref_labels"] == []
        assert refreshed_preview["proof_ref_count"] == 2

    asyncio.run(run())
def test_supervisor_auto_resumes_safe_queued_run_when_enabled(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Auto resume me", "Auto resume", str(tmp_path), [])
        created.state.next_step = "Finish the queued run from a valid checkpoint."
        created.state.handoff_summary = engine_one._make_handoff(created, created.state)
        engine_one.memory.append_run_started(created)
        engine_one.memory.append_checkpoint(created, created.state, "queued")
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


def test_supervisor_auto_resume_requires_handoff_action_context(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Improve AgentOrinth auto resume action context safety",
            "Thin action context auto resume",
            str(tmp_path),
            [],
        )
        created.state.next_step = "Finish the queued run from compact handoff evidence."
        created.state.handoff_summary.original_goal = created.goal
        created.state.handoff_summary.current_objective = created.state.goal
        created.state.handoff_summary.next_action = created.state.next_step
        created.state.handoff_summary.resume_prompt = (
            f"Resume AgentOrinth run {created.id}. Read Obsidian first, preserve original goal: {created.goal}. "
            "Do not reload raw logs; use this compact handoff. Next action: finish the queued run from compact evidence."
        )
        engine_one.memory.append_run_started(created)
        engine_one.memory.append_checkpoint(created, created.state, "queued")
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        engine_two = make_engine(tmp_path, auto_resume=True, auto_resume_max_runs=1)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)
        run_entry = next(item for item in report["runs"] if item["run_id"] == created.id)

        assert report["auto_resumed"] == 0
        assert report["recovered"] == 1
        assert run_entry["action"] == "paused_for_resume"
        assert run_entry["ornith_preflight_requires_attention"] is True
        assert "ornith_preflight" in run_entry["operator_attention_reasons"]
        assert "Handoff action context is warn" in run_entry["auto_resume_reason"]
        assert recovered.status == "paused"

    asyncio.run(run())
def test_supervisor_auto_resume_requires_checkpoint_quality(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Improve AgentOrinth auto resume checkpoint safety", "Missing checkpoint auto resume", str(tmp_path), [])
        created.state.next_step = "Continue only after Obsidian checkpoint is valid."
        created.state.handoff_summary = engine_one._make_handoff(created, created.state)
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        engine_two = make_engine(tmp_path, auto_resume=True, auto_resume_max_runs=1)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)
        run_entry = next(item for item in report["runs"] if item["run_id"] == created.id)

        assert report["auto_resumed"] == 0
        assert report["recovered"] == 1
        assert run_entry["action"] == "paused_for_resume"
        assert run_entry["checkpoint_quality_requires_attention"] is True
        assert "checkpoint_quality" in run_entry["operator_attention_reasons"]
        assert "Checkpoint quality is needs_checkpoint" in run_entry["auto_resume_reason"]
        assert recovered.status == "paused"

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
    created.state.next_step = "Resume from a valid checkpoint after preflight."
    created.state.handoff_summary = engine._make_handoff(created, created.state)
    engine.memory.append_run_started(created)
    engine.memory.append_checkpoint(created, created.state, "paused")
    engine.store.update_run(created.id, state=created.state)

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
    assert items["handoff_action_context"].status == "pass"
    assert "task_transitions=1" in items["handoff_action_context"].evidence
    assert "ornith_preflight" in snapshot.sections
    assert "Ornith preflight:" in prompt


def test_ornith_preflight_warns_when_handoff_action_context_is_thin(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    created = engine.store.create_run(
        "Improve AgentOrinth into a Codex-like long coding harness",
        "Thin handoff action context",
        str(tmp_path),
        [],
    )
    created.state.handoff_summary.original_goal = created.goal
    created.state.handoff_summary.current_objective = created.state.goal
    created.state.handoff_summary.resume_prompt = (
        f"Resume AgentOrinth run {created.id}. Read Obsidian first, preserve original goal: {created.goal}. "
        "Do not reload raw logs; use this compact handoff. Next action: consult Obsidian memory."
    )
    engine.store.update_run(created.id, state=created.state)

    report = engine.get_ornith_launch_checklist(created.id)
    items = {item["id"]: item for item in report["items"]}
    item = items["handoff_action_context"]

    assert item["status"] == "warn"
    assert "restart_ledger" in item["summary"]
    assert "generated=False" in item["evidence"]
    assert item["next_action"].startswith("Refresh/checkpoint the run handoff")


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
        assert entry["readiness_smoke_proof_status"] == "missing"
        assert entry["readiness_smoke_self_scaffold_reviewed"] is False
        assert entry["readiness_smoke_post_review_handoff_preserved"] is False
        assert entry["readiness_proof_history_status"] == "missing"
        assert entry["readiness_proof_history_requires_attention"] is False
        assert entry["readiness_proof_history_self_scaffold_review_count"] == 0
        assert "entries=0" in entry["readiness_proof_history_detail"]
        assert report["readiness_proof_history_attention_count"] == 0
        assert "latest=none" in entry["readiness_smoke_proof_detail"]
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
        assert stale_entry["readiness_smoke_proof_status"] == "stale"
        assert stale_entry["readiness_smoke_self_scaffold_reviewed"] is True
        assert stale_entry["readiness_smoke_post_review_handoff_preserved"] is True
        assert stale_entry["readiness_proof_history_status"] == "stale"
        assert stale_entry["readiness_proof_history_requires_attention"] is False
        assert stale_entry["readiness_proof_history_self_scaffold_review_count"] == 1
        assert stale_entry["readiness_proof_history_post_review_handoff_count"] == 1
        assert stale_entry["readiness_proof_history_resume_prompt_preservation_count"] == 1
        assert "source=latest_readiness_smoke" in stale_entry["readiness_proof_history_detail"]
        assert report["readiness_proof_history_attention_count"] == 0
        assert "post-review=yes" in stale_entry["readiness_smoke_proof_detail"]
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
        assert report["checkpoint_quality_attention_count"] == 1
        assert report["operator_attention_count"] == 1
        assert report["operator_attention_blocked_count"] == 1
        assert report["operator_attention_watch_count"] == 0
        assert [item["run_id"] for item in report["runs"]] == [harness.id]
        assert report["runs"][0]["action"] == "operator_attention"
        assert report["runs"][0]["operator_attention_required"] is True
        assert report["runs"][0]["operator_attention_severity"] == "blocked"
        assert "readiness_smoke" in report["runs"][0]["operator_attention_reasons"]
        assert "checkpoint_quality" in report["runs"][0]["operator_attention_reasons"]
        assert "ornith_preflight" in report["runs"][0]["operator_attention_reasons"]
        assert report["runs"][0]["checkpoint_quality_requires_attention"] is True
        assert report["runs"][0]["ornith_preflight_requires_attention"] is True
        assert report["runs"][0]["supervisor_priority"] >= 90

    asyncio.run(run())



def test_operator_action_queue_filters_proof_review_items(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)

    def entry(run_id: str, reason: str, **extra) -> dict:
        base = {
            "run_id": run_id,
            "title": run_id,
            "status": "paused",
            "action": "operator_attention",
            "operator_attention_required": True,
            "operator_attention_reasons": [reason],
            "operator_attention_action": f"Review {reason}.",
            "operator_attention_severity": "watch",
            "supervisor_priority": 10,
        }
        base.update(extra)
        return base

    engine.supervisor_report = {
        "ran_at": "2026-06-28T10:30:00+00:00",
        "runs": [
            entry(
                "proof-history-run",
                "readiness_proof_history",
                readiness_proof_history_action="Inspect proof history.",
                readiness_proof_history_status="partial",
                readiness_proof_history_detail="missing post-review handoff proof",
                readiness_proof_history_self_scaffold_review_count=1,
                readiness_proof_history_post_review_handoff_count=0,
            ),
            entry(
                "source-ref-run",
                "readiness_source_refs",
                readiness_source_refs_action="Refresh source refs.",
                readiness_source_refs_missing_labels=["browser"],
                readiness_source_refs_labels=["web"],
                readiness_source_refs_count=1,
                readiness_proof_history_status="complete",
            ),
            entry(
                "source-evidence-run",
                "source_evidence",
                source_evidence_action="Capture source evidence.",
                source_evidence={"missing_labels": ["web"], "latest_evidence": "none"},
            ),
            entry(
                "desktop-proof-run",
                "desktop_effect_proof",
                desktop_effect_proof_action="Capture desktop screenshot proof.",
                desktop_effect_proof_after_tool="desktop_click",
                desktop_effect_proof_tool="desktop_screenshot",
                desktop_effect_proof_detail="desktop_effect_check_required after desktop_click",
            ),
            entry("approval-run", "approval"),
        ],
    }

    all_queue = engine.get_operator_action_queue(limit=10)
    filtered = engine.get_operator_action_queue(limit=10, queue_filter="proof_reviews")
    limited = engine.get_operator_action_queue(limit=2, queue_filter="proof_reviews")

    assert all_queue.total_count == 5
    assert filtered.total_count == all_queue.total_count
    assert filtered.readiness_proof_history_count == 1
    assert filtered.readiness_source_ref_count == 1
    assert {item.reason for item in filtered.items} == {
        "readiness_proof_history",
        "readiness_source_refs",
        "source_evidence",
        "desktop_effect_proof",
    }
    assert all(item.reason != "approval" for item in filtered.items)
    assert len(limited.items) == 2
    assert all(item.reason in {"readiness_proof_history", "readiness_source_refs", "source_evidence", "desktop_effect_proof"} for item in limited.items)

def test_supervisor_queues_partial_readiness_proof_history_attention(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        smoke = engine_one.store.create_run(
            "Readiness smoke partial proof",
            "Readiness smoke partial proof",
            str(tmp_path),
            [],
            tool_profile="ornith_rehearsal",
        )
        report = ReadinessRehearsalReport(
            run_id=smoke.id,
            generated_at="2026-06-27T08:00:00+00:00",
            status="passed",
            summary="Seeded readiness rehearsal has partial proof history.",
            rehearsal_workspace=str(tmp_path),
            restart_simulated=True,
            refused_event_id=1,
            accepted_event_id=3,
            completed_event_id=4,
            self_scaffold_reviewed=True,
            self_scaffold_review_event_id=2,
            self_scaffold_reviewed_change_count=1,
            post_review_handoff_goal_preserved=False,
            post_review_handoff_next_action_preserved=False,
            post_review_resume_prompt_goal_preserved=False,
            post_review_resume_prompt_next_action_preserved=False,
            compact_context_tokens=1200,
            replay_attached=True,
            handoff_attached=True,
            steps=[
                ReadinessRehearsalStep(
                    id="self_scaffold_review",
                    status="passed",
                    summary="Self-scaffold review was accepted.",
                    evidence=["reviewed=1"],
                    event_id=2,
                    event_kind="operator_action_reviewed",
                ),
                ReadinessRehearsalStep(
                    id="accepted_claim",
                    status="passed",
                    summary="Readiness claim was accepted.",
                    evidence=["claim_event=3"],
                    event_id=3,
                    event_kind="readiness_claim",
                ),
            ],
        )
        smoke.state.readiness_rehearsal = report
        smoke.state.handoff_summary.readiness_rehearsal = report
        engine_one.store.update_run(smoke.id, status="completed", state=smoke.state)
        created = engine_one.store.create_run(
            "Improve AgentOrinth into a Codex-like long coding harness",
            "Harness partial proof history",
            str(tmp_path),
            [],
        )
        engine_one.store.update_run(created.id, status="running", state=created.state)

        engine_two = make_engine(tmp_path)
        supervisor = await engine_two.recover_stale_runs()
        entry = next(item for item in supervisor["runs"] if item["run_id"] == created.id)
        queue = supervisor["operator_action_queue"]
        proof_items = [item for item in queue["items"] if item["reason"] == "readiness_proof_history"]

        assert entry["readiness_smoke_status"] == "incomplete"
        assert entry["readiness_proof_history_status"] == "partial"
        assert entry["readiness_proof_history_requires_attention"] is True
        assert entry["readiness_proof_history_self_scaffold_review_count"] == 1
        assert entry["readiness_proof_history_post_review_handoff_count"] == 0
        assert "readiness_proof_history" in entry["operator_attention_reasons"]
        assert supervisor["readiness_proof_history_attention_count"] == 1
        assert queue["readiness_proof_history_count"] == 1
        assert proof_items
        assert proof_items[0]["endpoint"] == f"/api/runs/{created.id}/readiness-proof-history"
        assert proof_items[0]["method"] == "GET"
        assert proof_items[0]["ui_target"] == "readiness_proof_history"
        assert any("post_review_handoff=0" in detail for detail in proof_items[0]["details"])

    asyncio.run(run())

def test_supervisor_queues_self_scaffold_review_attention(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path, auto_resume=True)
        created = engine_one.store.create_run(
            "Let the local model reshape this run safely",
            "Self scaffold attention",
            str(tmp_path),
            [],
            tool_profile="ornith_self_scaffold",
        )
        created.state.task_graph = [
            TaskNode(
                id="task-self-scaffold",
                title="Review Ornith self-scaffold guard",
                kind="decision",
                status="in_progress",
            )
        ]
        created.state.current_task_id = "task-self-scaffold"
        created.state.action_context.current_task_id = "task-self-scaffold"
        created.state.action_context.model_guard_ledger.append(
            "current_task_mismatch guarded run_tests for task-self-scaffold before broad autonomy"
        )
        engine_one.store.update_run(created.id, status="queued", state=created.state)

        engine_two = make_engine(tmp_path, auto_resume=True)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        scaffold_items = [item for item in queue["items"] if item["reason"] == "self_scaffold"]
        recovered = engine_two.store.get_run(created.id)

        assert report["auto_resumed"] == 0
        assert report["recovered"] == 1
        assert report["self_scaffold_attention_count"] == 1
        assert recovered.status == "paused"
        assert entry["self_scaffold_requires_attention"] is True
        assert entry["self_scaffold"]["status"] == "needs_review"
        assert entry["self_scaffold"]["guard_count"] == 1
        assert entry["auto_resume_reason"] == entry["self_scaffold_action"]
        assert "self_scaffold" in entry["operator_attention_reasons"]
        assert entry["operator_attention_severity"] == "watch"
        assert queue["self_scaffold_count"] == 1
        assert scaffold_items
        item = scaffold_items[0]
        assert item["ui_target"] == "self_scaffold"
        assert item["endpoint"] == f"/api/runs/{created.id}/replay"
        assert any("guards=1" == detail for detail in item["details"])

        reviewed = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(item_id=item["id"], decision="dispatch", confirmed=True)
        )
        assert reviewed.status == "reviewed"
        assert reviewed.action_taken == "self_scaffold_review"
        assert reviewed.event_kind == "operator_action_reviewed"
        assert reviewed.queue.self_scaffold_count == 0
        events = engine_two.store.list_events(created.id)
        assert events[-1]["kind"] == "operator_action_reviewed"
        assert events[-1]["data"]["operator_action"]["ui_target"] == "self_scaffold"
        guard_change_id = next(
            change["id"]
            for change in entry["self_scaffold"]["changes"]
            if change["kind"] == "model_guard"
        )
        review_payload = events[-1]["data"]["self_scaffold_review"]
        assert review_payload["reviewed_change_count"] == 1
        assert review_payload["remaining_goal_review"] is False
        assert review_payload["reviewed_change_ids"] == [guard_change_id]
        stored = engine_two.store.get_run(created.id)
        assert stored.state.self_scaffold.status == "observed"
        assert stored.state.self_scaffold.review_count == 1
        assert stored.state.self_scaffold.reviewed_change_count == 1
        assert stored.state.self_scaffold.latest_review_event_id == events[-1]["id"]
        assert stored.state.self_scaffold_reviews.status == "reviewed"
        assert stored.state.self_scaffold_reviews.accepted_count == 1
        assert stored.state.self_scaffold_reviews.latest_event_id == events[-1]["id"]
        assert stored.state.self_scaffold_reviews.latest_reviewed_change_ids == [guard_change_id]
        assert stored.state.self_scaffold_rollback_intents.status == "available"
        assert stored.state.self_scaffold_rollback_intents.steering_count == 1
        assert stored.state.self_scaffold_rollback_intents.entries[0].mutation_automatic is False
        assert stored.state.handoff_summary.self_scaffold.status == "observed"
        assert stored.state.handoff_summary.self_scaffold_reviews.latest_event_id == events[-1]["id"]
        assert stored.state.handoff_summary.self_scaffold_rollback_intents.steering_count == 1

        refreshed = await engine_two.recover_stale_runs()
        assert refreshed["self_scaffold_attention_count"] == 0
        assert refreshed["operator_action_queue"]["self_scaffold_count"] == 0

    asyncio.run(run())

def test_supervisor_surfaces_goal_confirmation_queue_for_goal_updates(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run(
            "Improve AgentOrinth while preserving Ornith agency",
            "Goal confirmation queue",
            str(tmp_path),
            [],
        )
        proposed_goal = (
            "Improve AgentOrinth with Ornith-preserving self-scaffolding and explicit user-confirmed goal evolution"
        )
        await engine_one.propose_goal(created.id, proposed_goal, "Ornith proposed a safer long-run goal shape.")

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)
        queue = report["operator_action_queue"]
        goal_items = [item for item in queue["items"] if item["reason"] == "goal_confirmation"]

        assert report["goal_confirmation_attention_count"] == 1
        assert report["pending_approval_count"] == 1
        assert entry["goal_confirmation_requires_attention"] is True
        assert entry["goal_confirmation_proposed_goal"] == proposed_goal
        assert entry["goal_confirmation_approval_count"] == 1
        assert "goal_confirmation" in entry["operator_attention_reasons"]
        assert entry["operator_attention_severity"] == "blocked"
        assert queue["goal_confirmation_count"] == 1
        assert queue["approval_count"] == 1
        assert goal_items
        assert goal_items[0]["approval_kind"] == "goal_update"
        assert goal_items[0]["ui_target"] == "approval"
        assert proposed_goal[:80] in goal_items[0]["details"][0]

    asyncio.run(run())

def test_supervisor_surfaces_action_readiness_gate_for_runs(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        created = engine_one.store.create_run("Inspect action gate", "Action gate", str(tmp_path), [])
        created.state.milestone = "act"
        created.state.blockers.append("Needs user decision.")
        engine_one.store.update_run(created.id, status="paused", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        entry = next(item for item in report["runs"] if item["run_id"] == created.id)

        assert report["action_readiness_attention_count"] == 1
        assert report["action_readiness_blocked_count"] == 1
        assert entry["action_readiness_status"] == "blocked"
        assert entry["action_readiness_ready"] is False
        assert entry["action_readiness"]["recommended_action"] == "Resolve blockers or ask the user before acting."
        assert entry["action_readiness_action"] == "Resolve blockers or ask the user before acting."
        assert entry["action_readiness_decisions"]["decision_count"] == 0

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
        assert queue["promotion_approval_count"] == 0
        assert queue["recovery_count"] == 1
        assert queue["blocker_count"] == 1
        assert queue_reasons == {"approval", "recovery", "blocker"}
        approval_item = next(item for item in queue["items"] if item["reason"] == "approval")
        recovery_item = next(item for item in queue["items"] if item["reason"] == "recovery")
        blocker_item = next(item for item in queue["items"] if item["reason"] == "blocker")
        assert approval_item["approval_id"] > 0
        assert approval_item["promotion_gate"] is False
        assert approval_item["endpoint"] == f"/api/runs/{approval_run.id}/approvals"
        assert recovery_item["endpoint"] == f"/api/runs/{recovery_run.id}/recovery/resume"
        assert blocker_item["ui_target"] == "steer"
        initial_reviews = engine_two.get_approval_reviews(approval_run.id, status="pending")
        assert initial_reviews[0]["reviewed"] is False
        assert initial_reviews[0]["review_count"] == 0
        assert initial_reviews[0]["latest_review_event_id"] == 0

        reviewed = await engine_two.dispatch_operator_action(
            OperatorActionDispatchRequest(
                item_id=approval_item["id"],
                decision="open",
                confirmed=False,
            )
        )
        assert reviewed.status == "reviewed"
        assert reviewed.action_taken == "open"
        assert reviewed.event_kind == "operator_action_reviewed"
        assert reviewed.queue.approval_count == 1
        assert engine_two.store.list_approvals(approval_run.id, status="pending")
        reviewed_reviews = engine_two.get_approval_reviews(approval_run.id, status="pending")
        assert reviewed_reviews[0]["reviewed"] is True
        assert reviewed_reviews[0]["review_count"] == 1
        assert reviewed_reviews[0]["latest_review_event_id"] > 0
        assert reviewed_reviews[0]["latest_reviewed_at"]
        reviewed_ledger = engine_two.get_operator_dispatches(approval_run.id)
        assert reviewed_ledger["unresolved_approval_history_count"] == 1
        assert reviewed_ledger["unresolved_approval_histories"][0]["approval_id"] == approval_item["approval_id"]
        assert reviewed_ledger["unresolved_approval_histories"][0]["latest_status"] == "reviewed"

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
        rejected_reviews = engine_two.get_approval_reviews(approval_run.id, status="rejected")
        assert rejected_reviews[0]["reviewed"] is True
        assert rejected_reviews[0]["review_count"] == 1
        event_kinds = [event["kind"] for event in engine_two.store.list_events(approval_run.id)]
        assert "operator_action_reviewed" in event_kinds
        assert "operator_action_confirmation_required" in event_kinds
        assert "operator_action_dispatched" in event_kinds
        ledger = engine_two.get_operator_dispatches(approval_run.id)
        assert ledger["total_count"] == 3
        assert ledger["reviewed_count"] == 1
        assert ledger["confirmation_required_count"] == 1
        assert ledger["dispatched_count"] == 1
        assert ledger["approval_history_count"] == 1
        assert ledger["unresolved_approval_history_count"] == 0
        assert ledger["unresolved_approval_histories"] == []
        history = ledger["approval_histories"][0]
        assert history["approval_id"] == approval_item["approval_id"]
        assert history["event_count"] == 3
        assert history["reviewed_count"] == 1
        assert history["confirmation_required_count"] == 1
        assert history["dispatched_count"] == 1
        assert history["latest_status"] == "dispatched"
        assert history["latest_event_id"] == ledger["entries"][0]["event_id"]
        assert history["sequence"] == [
            f"reviewed#{ledger['entries'][2]['event_id']}:open",
            f"confirmation_required#{ledger['entries'][1]['event_id']}:reject",
            f"dispatched#{ledger['entries'][0]['event_id']}:reject",
        ]
        assert [entry["status"] for entry in ledger["entries"]] == ["dispatched", "confirmation_required", "reviewed"]
        assert ledger["entries"][0]["approval_id"] == approval_item["approval_id"]
        assert ledger["entries"][2]["decision"] == "open"
        assert ledger["entries"][2]["approval_id"] == approval_item["approval_id"]

    asyncio.run(run())


def test_supervisor_auto_resume_respects_max_runs(tmp_path: Path) -> None:
    async def run() -> None:
        engine_one = make_engine(tmp_path)
        first = engine_one.store.create_run("Auto resume one", "Auto one", str(tmp_path), [])
        second = engine_one.store.create_run("Auto resume two", "Auto two", str(tmp_path), [])
        for created in (first, second):
            created.state.next_step = "Finish the queued run from a valid checkpoint."
            created.state.handoff_summary = engine_one._make_handoff(created, created.state)
            engine_one.memory.append_run_started(created)
            engine_one.memory.append_checkpoint(created, created.state, "queued")
            engine_one.store.update_run(created.id, status="queued", state=created.state)

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
        approval = engine_one.store.create_approval(
            created.id,
            "workspace_promote",
            {"tool_name": "workspace_promote", "args": {"source_path": str(tmp_path)}},
            "Promote workspace changes.",
        )
        review_event = engine_one.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator reviewed workspace promotion approval.",
            {
                "operator_action": {
                    "id": f"{created.id}:approval:workspace_promote",
                    "run_id": created.id,
                    "title": created.title,
                    "reason": "approval",
                    "action": "Review pending workspace promotion approval.",
                    "ui_target": "approval",
                    "approval_id": approval["id"],
                },
            },
        )
        engine_one.store.update_run(created.id, status="waiting_approval", state=created.state)

        engine_two = make_engine(tmp_path)
        report = await engine_two.recover_stale_runs()
        recovered = engine_two.store.get_run(created.id)

        assert report["waiting_approval"] == 1
        assert recovered.status == "waiting_approval"
        assert recovered.state.next_step == "Wait for pending dashboard approval."
        assert recovered.state.handoff_summary.approvals == [
            f"workspace_promote:pending:reviewed:x1:event#{review_event['id']}"
        ]
        assert len(recovered.state.handoff_summary.approval_reviews) == 1
        approval_review = recovered.state.handoff_summary.approval_reviews[0]
        assert approval_review.action_kind == "workspace_promote"
        assert approval_review.reviewed is True
        assert approval_review.review_count == 1
        assert approval_review.latest_review_event_id == review_event["id"]
        assert approval_review.high_risk is True

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
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-promotion-test",
                name="shell",
                args={"command": "python -m pytest backend/tests/test_workspace.py -q"},
                ok=True,
                summary="pytest passed before source promotion.",
                created_at="2026-06-27T08:05:00+00:00",
            )
        )
        engine.store.update_run(created.id, status="paused", state=created.state)

        updated = await engine.request_workspace_promotion(created.id)
        approvals = engine.store.list_approvals(created.id, status="pending")

        assert updated.status == "waiting_approval"
        assert approvals[0]["action_kind"] == "workspace_promote"
        assert approvals[0]["payload"]["args"]["source_path"] == str(source)
        assert approvals[0]["payload"]["preview"]["summary"] == "1 workspace change(s): 0 added, 1 modified, 0 deleted."
        assert approvals[0]["payload"]["preview"]["files"][0]["path"] == "README.md"

        review_event = engine.store.append_event(
            created.id,
            "operator_action_reviewed",
            "Operator reviewed workspace promotion approval.",
            {
                "decision": "open",
                "operator_action": {
                    "id": f"{created.id}:approval:workspace_promote",
                    "run_id": created.id,
                    "title": created.title,
                    "reason": "approval",
                    "action": "Review pending workspace promotion approval.",
                    "ui_target": "approval",
                    "approval_id": approvals[0]["id"],
                },
            },
        )
        audit = engine.get_promotion_audit(created.id)
        expected = f"approval#{approvals[0]['id']}:latest=reviewed:events=1:seq=reviewed#{review_event['id']}:open"

        assert audit["unresolved_approval_history_count"] == 1
        assert audit["unresolved_approval_histories"] == [expected]
        assert any(issue["id"] == "promotion_approval_history_unresolved" for issue in audit["issues"])

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
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-promotion-reuse-test",
                name="shell",
                args={"command": "python -m pytest backend/tests/test_workspace.py -q"},
                ok=True,
                summary="pytest passed before source promotion.",
                created_at="2026-06-27T08:05:00+00:00",
            )
        )
        engine.store.update_run(created.id, status="paused", state=created.state)

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
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-promotion-test",
                name="shell",
                args={"command": "python -m pytest backend/tests/test_workspace.py -q"},
                ok=True,
                summary="pytest passed before source promotion.",
                created_at="2026-06-27T08:05:00+00:00",
            )
        )
        engine.store.update_run(created.id, status="paused", state=created.state)

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
        created = engine_one.store.get_run(created.id)
        created.state.tool_calls.append(
            ToolCallRecord(
                id="tool-promotion-test",
                name="shell",
                args={"command": "python -m pytest backend/tests/test_workspace.py -q"},
                ok=True,
                summary="pytest passed before source promotion.",
                created_at="2026-06-27T08:05:00+00:00",
            )
        )
        engine_one.store.update_run(created.id, status="paused", state=created.state)
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
