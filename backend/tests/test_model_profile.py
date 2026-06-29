from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.model_eval import run_ornith_fixture_eval
from app.model_profile import extract_json_object, profile_for
from app.model_quality import build_model_prompt_quality_report
from app.profile_adaptation import build_model_profile_adaptation_proposal
from app.schemas import FailureRecord, ModelInteractionRecord, ObjectiveReadinessProofOutcome, TaskNode, VerificationOutcomeRecord

from test_engine_long_loop import make_engine


def test_profile_for_defaults_to_ornith() -> None:
    profile = profile_for("ornith-9b-q4-96k", "ornith")

    assert profile.id == "ornith"
    assert profile.json_retries == 1
    assert profile.context_target_tokens < 24000
    assert "JSON" in profile.json_system


def test_extract_json_object_handles_fences_and_prose() -> None:
    assert extract_json_object('```json\n{"tool":"git_status","args":{}}\n```')["tool"] == "git_status"
    assert extract_json_object('Here is the action: {"risk": ""} trailing text')["risk"] == ""


def test_ornith_output_fixture_parses() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "ornith_outputs.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))

    for fixture in fixtures:
        payload = extract_json_object(str(fixture["text"]))
        assert payload[fixture["expected_key"]] == fixture["expected_value"], fixture["name"]


def test_ornith_eval_reports_fallback_and_patch_first_metrics() -> None:
    summary = run_ornith_fixture_eval(profile_for("ornith-9b-q4-96k", "ornith"))

    assert summary.profile_id == "ornith"
    assert summary.total >= 6
    assert summary.parsed == summary.total
    assert summary.fallback_needed == 1
    assert summary.patch_first_pass == 1
    assert summary.patch_first_fail == 1
    assert any(case.id == "patch_first_file_write_violation" and case.patch_first_ok is False for case in summary.cases)


def test_prompt_quality_report_classifies_live_model_interactions(tmp_path) -> None:  # noqa: ANN001
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Quality report", "Quality", str(tmp_path), [])
    run.state.model_interactions.extend(
        [
            ModelInteractionRecord(
                id="model-good",
                kind="action",
                ok=True,
                attempts=1,
                summary="Model selected tool git_status.",
                created_at="2026-06-27T08:00:00+00:00",
            ),
            ModelInteractionRecord(
                id="model-unknown",
                kind="action",
                ok=False,
                attempts=2,
                repaired=True,
                fallback_used=True,
                summary="Model action fallback used: git_status.",
                error="Unknown or missing tool: invent_magic",
                raw_excerpt="raw model text should stay out of report",
                created_at="2026-06-27T08:01:00+00:00",
            ),
            ModelInteractionRecord(
                id="model-write",
                kind="action",
                ok=True,
                attempts=1,
                summary="Model selected tool file_write.",
                created_at="2026-06-27T08:02:00+00:00",
            ),
        ]
    )

    report = build_model_prompt_quality_report([run], profile_id="ornith")

    assert report.interaction_count == 3
    assert report.issue_counts["unknown_tool"] == 1
    assert report.issue_counts["fallback_used"] == 1
    assert report.issue_counts["json_repaired"] == 1
    assert report.issue_counts["json_retry"] == 1
    assert report.issue_counts["direct_write_action"] == 1
    assert report.samples[0].error_type == "direct_write_action"
    assert "raw model text" not in report.model_dump_json()


def test_prompt_quality_report_classifies_verification_outcome_patterns(tmp_path) -> None:  # noqa: ANN001
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Outcome quality", "Outcome quality", str(tmp_path), [])
    run.state.verification_outcomes.outcomes = [
        VerificationOutcomeRecord(
            id="outcome-failed",
            timestamp="2026-06-27T08:03:00+00:00",
            tool="run_tests",
            ok=False,
            outcome="failed",
            summary="Tests failed during recovery.",
            during_recovery=True,
            recovery_id="recovery-1",
            recovery_status="active",
            proof_label="verification",
        ),
        VerificationOutcomeRecord(
            id="outcome-unresolved",
            timestamp="2026-06-27T08:02:00+00:00",
            tool="run_tests",
            ok=True,
            outcome="recovery_tool_succeeded",
            summary="Command ran but criterion stayed open.",
            closed_recovery=True,
            recovery_id="recovery-2",
            recovery_status="resolved",
            proof_label="verification",
        ),
        VerificationOutcomeRecord(
            id="outcome-resolved",
            timestamp="2026-06-27T08:01:00+00:00",
            tool="run_tests",
            ok=True,
            outcome="recovery_resolved",
            summary="All tests passed.",
            closed_recovery=True,
            resolved_recovery_evidence=True,
            recovery_id="recovery-3",
            recovery_status="resolved",
            proof_label="verification",
        ),
    ]

    report = build_model_prompt_quality_report([run], profile_id="ornith")

    assert report.run_count == 1
    assert report.issue_counts["recovery_proof_failed"] == 1
    assert report.issue_counts["recovery_proof_unresolved"] == 1
    assert report.issue_counts["recovery_proof_resolved"] == 1
    assert {pattern.id for pattern in report.patterns} >= {
        "recovery_proof_failed",
        "recovery_proof_unresolved",
        "recovery_proof_resolved",
    }
    assert report.samples[0].kind == "verification"
    assert report.samples[0].error_type == "recovery_proof_failed"


def test_prompt_quality_report_classifies_objective_proof_strategy_patterns(tmp_path) -> None:  # noqa: ANN001
    engine = make_engine(tmp_path)
    run_one = engine.store.create_run("Objective proof failed", "Objective failed", str(tmp_path), [])
    run_two = engine.store.create_run("Objective proof verified", "Objective verified", str(tmp_path), [])
    run_one.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-failed-1",
            item_id="verification_critic_loop",
            tool="run_tests",
            evidence_label="verification",
            strategy="smallest_test",
            outcome="failed",
            ok=False,
            summary="Broad tests failed.",
            created_at="2026-06-27T08:04:00+00:00",
        ),
        ObjectiveReadinessProofOutcome(
            id="obj-partial-1",
            item_id="compact_context",
            tool="file_read",
            evidence_label="context",
            strategy="dashboard_api_check",
            outcome="partial",
            ok=True,
            summary="Context section existed but pressure stayed high.",
            created_at="2026-06-27T08:03:00+00:00",
        ),
    ]
    run_two.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-verified-1",
            item_id="verification_critic_loop",
            tool="shell",
            evidence_label="verification",
            strategy="compile_check",
            outcome="verified",
            ok=True,
            summary="Compile check passed and readiness item verified.",
            created_at="2026-06-27T08:02:00+00:00",
        )
    ]

    report = build_model_prompt_quality_report([run_one, run_two], profile_id="ornith")

    assert report.run_count == 2
    assert report.issue_counts["objective_proof_strategy_failed"] == 1
    assert report.issue_counts["objective_proof_strategy_partial"] == 1
    assert report.issue_counts["objective_proof_strategy_verified"] == 1
    assert {pattern.id for pattern in report.patterns} >= {
        "objective_proof_strategy_failed",
        "objective_proof_strategy_partial",
        "objective_proof_strategy_verified",
    }
    assert any(sample.kind == "objective_readiness" and "strategy=smallest_test" in sample.error for sample in report.samples)


def test_profile_adaptation_proposal_requires_confirmation(tmp_path) -> None:  # noqa: ANN001
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Adapt profile", "Adapt", str(tmp_path), [])
    run.state.model_interactions.extend(
        [
            ModelInteractionRecord(
                id="model-unknown",
                kind="action",
                ok=False,
                attempts=2,
                fallback_used=True,
                error="Unknown or missing tool: invent_magic",
                summary="Model action fallback used: git_status.",
                created_at="2026-06-27T08:01:00+00:00",
            ),
            ModelInteractionRecord(
                id="model-write",
                kind="action",
                ok=True,
                attempts=1,
                summary="Model selected tool file_write.",
                created_at="2026-06-27T08:02:00+00:00",
            ),
        ]
    )
    quality = build_model_prompt_quality_report([run], profile_id="ornith")
    eval_summary = run_ornith_fixture_eval(profile_for("ornith-9b-q4-96k", "ornith"))

    proposal = build_model_profile_adaptation_proposal(engine.model_profile, quality, eval_summary)

    assert proposal.status == "needs_confirmation"
    assert proposal.confirmation_required
    assert all(action.requires_confirmation for action in proposal.actions)
    assert {action.target for action in proposal.actions} >= {"action_prompt"}
    assert any(action.change == "policy_bias" for action in proposal.actions)
    assert "invent_magic" not in proposal.model_dump_json()


def test_profile_adaptation_uses_recovery_outcome_patterns(tmp_path) -> None:  # noqa: ANN001
    engine = make_engine(tmp_path)
    run = engine.store.create_run("Adapt recovery profile", "Adapt recovery", str(tmp_path), [])
    run.state.verification_outcomes.outcomes = [
        VerificationOutcomeRecord(
            id="outcome-failed",
            timestamp="2026-06-27T08:03:00+00:00",
            tool="run_tests",
            ok=False,
            outcome="failed",
            summary="Tests failed during recovery.",
            during_recovery=True,
            recovery_id="recovery-1",
            proof_label="verification",
        ),
        VerificationOutcomeRecord(
            id="outcome-unresolved-1",
            timestamp="2026-06-27T08:02:00+00:00",
            tool="run_tests",
            ok=True,
            outcome="recovery_tool_succeeded",
            summary="Command ran but criterion stayed open.",
            closed_recovery=True,
            recovery_id="recovery-2",
            proof_label="verification",
        ),
        VerificationOutcomeRecord(
            id="outcome-unresolved-2",
            timestamp="2026-06-27T08:01:00+00:00",
            tool="browser_screenshot",
            ok=True,
            outcome="executed",
            summary="Screenshot captured but criterion stayed open.",
            during_recovery=True,
            recovery_id="recovery-3",
            proof_label="browser",
        ),
    ]
    quality = build_model_prompt_quality_report([run], profile_id="ornith")
    eval_summary = run_ornith_fixture_eval(profile_for("ornith-9b-q4-96k", "ornith"))

    proposal = build_model_profile_adaptation_proposal(engine.model_profile, quality, eval_summary)

    assert proposal.status == "needs_confirmation"
    assert any(action.target == "policy" and action.evidence_counts.get("recovery_proof_failed") == 1 for action in proposal.actions)
    assert any(action.evidence_counts.get("recovery_proof_unresolved") == 2 for action in proposal.actions)


def test_profile_adaptation_uses_cross_run_objective_proof_strategy_patterns(tmp_path) -> None:  # noqa: ANN001
    engine = make_engine(tmp_path)
    failed_one = engine.store.create_run("Failed proof one", "Failed one", str(tmp_path), [])
    failed_two = engine.store.create_run("Failed proof two", "Failed two", str(tmp_path), [])
    verified_one = engine.store.create_run("Verified proof one", "Verified one", str(tmp_path), [])
    verified_two = engine.store.create_run("Verified proof two", "Verified two", str(tmp_path), [])
    failed_one.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-failed-1",
            item_id="verification_critic_loop",
            tool="run_tests",
            evidence_label="verification",
            strategy="smallest_test",
            outcome="failed",
            ok=False,
            summary="Broad tests failed.",
            created_at="2026-06-27T08:04:00+00:00",
        )
    ]
    failed_two.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-failed-2",
            item_id="verification_critic_loop",
            tool="run_tests",
            evidence_label="verification",
            strategy="smallest_test",
            outcome="failed",
            ok=False,
            summary="Broad tests failed again.",
            created_at="2026-06-27T08:03:00+00:00",
        )
    ]
    verified_one.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-verified-1",
            item_id="verification_critic_loop",
            tool="shell",
            evidence_label="verification",
            strategy="compile_check",
            outcome="verified",
            ok=True,
            summary="Compile check verified readiness.",
            created_at="2026-06-27T08:02:00+00:00",
        )
    ]
    verified_two.state.objective_readiness_proof_outcomes = [
        ObjectiveReadinessProofOutcome(
            id="obj-verified-2",
            item_id="verification_critic_loop",
            tool="shell",
            evidence_label="verification",
            strategy="compile_check",
            outcome="verified",
            ok=True,
            summary="Compile check verified readiness again.",
            created_at="2026-06-27T08:01:00+00:00",
        )
    ]
    quality = build_model_prompt_quality_report(
        [failed_one, failed_two, verified_one, verified_two],
        profile_id="ornith",
    )
    eval_summary = run_ornith_fixture_eval(profile_for("ornith-9b-q4-96k", "ornith"))

    proposal = build_model_profile_adaptation_proposal(engine.model_profile, quality, eval_summary)

    assert proposal.status == "needs_confirmation"
    assert any(
        action.target == "policy"
        and action.evidence_counts.get("objective_proof_strategy_failed") == 2
        and action.evidence_counts.get("objective_failed_runs") == 2
        for action in proposal.actions
    )
    assert any(
        action.target == "eval_fixture"
        and action.evidence_counts.get("objective_proof_strategy_verified") == 2
        and action.evidence_counts.get("objective_verified_runs") == 2
        for action in proposal.actions
    )


def test_engine_chat_json_retries_for_ornith_style_prose(tmp_path) -> None:  # noqa: ANN001
    class RetryModel:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                return "I will do it with JSON soon."
            return '{"tool":"git_status","args":{},"thought_summary":"Check repo."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = RetryModel()  # type: ignore[assignment]
        payload = await engine._chat_json("Choose a tool.", max_tokens=200, schema_hint='{"tool":"git_status","args":{}}')

        assert payload["tool"] == "git_status"
        assert engine.model.calls == 2  # type: ignore[attr-defined]

    asyncio.run(run())


def test_engine_exposes_ornith_profile(tmp_path) -> None:  # noqa: ANN001
    engine = make_engine(tmp_path)
    profile = engine.get_model_profile()

    assert profile["id"] == "ornith"
    assert profile["configured_model"] == "test-model"
    assert profile["effective_context_target_tokens"] == 12000


def test_choose_action_repairs_ornith_tool_shape(tmp_path) -> None:  # noqa: ANN001
    class ActionModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            return 'Here is JSON: {"action":"inspect_workspace","args":null,"summary":"Look around."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = ActionModel()  # type: ignore[assignment]
        created = engine.store.create_run("Inspect repo", "Inspect", str(tmp_path), [])
        created.state.step_count = 1

        action = await engine._choose_action(created, "tiny context")

        assert action == {"tool": "file_read", "args": {"path": "."}, "thought_summary": "Look around."}
        assert created.state.model_interactions[-1].ok
        assert created.state.model_interactions[-1].repaired
        assert created.state.model_interactions[-1].kind == "action"

    asyncio.run(run())


def test_choose_action_records_fallback_for_unknown_tool(tmp_path) -> None:  # noqa: ANN001
    class BadActionModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            return '{"tool":"invent_magic","args":{},"thought_summary":"Try impossible tool."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = BadActionModel()  # type: ignore[assignment]
        created = engine.store.create_run("Inspect repo", "Inspect", str(tmp_path), [])
        created.state.step_count = 1

        action = await engine._choose_action(created, "tiny context")

        assert action == {"tool": "git_status", "args": {}}
        assert created.state.model_interactions[-1].fallback_used
        assert "Unknown or missing tool" in created.state.model_interactions[-1].error

    asyncio.run(run())


def test_choose_action_guards_direct_source_file_write_for_ornith(tmp_path) -> None:  # noqa: ANN001
    class DirectWriteModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            prompt = messages[-1]["content"]
            assert "Do not use file_write for source-code edits" in prompt
            return json.dumps(
                {
                    "tool": "file_write",
                    "args": {"path": "app.py", "content": "print(\"hello\")\n"},
                    "thought_summary": "Write source directly.",
                }
            )

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = DirectWriteModel()  # type: ignore[assignment]
        (tmp_path / "app.py").write_text("print(\"hi\")\n", encoding="utf-8")
        created = engine.store.create_run("Patch source safely", "Patch first", str(tmp_path), [])
        created.state.step_count = 1

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "file_read"
        assert action["args"] == {"path": "app.py"}
        assert action["model_guard"] == "patch_first_source_write"
        assert action["guarded_tool"] == "file_write"
        assert created.state.model_interactions[-1].fallback_used
        assert "direct source write" in created.state.model_interactions[-1].summary.lower()
        assert "patch-first" in created.state.model_interactions[-1].error
        assert created.state.action_context.selected_tool == "file_read"
        assert created.state.action_context.selected_action.startswith("Inspect app.py")

    asyncio.run(run())
def test_choose_action_guards_repeated_failed_command_for_ornith(tmp_path) -> None:  # noqa: ANN001
    class RepeatFailedCommandModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            prompt = messages[-1]["content"]
            assert "failure_ledger" in prompt
            assert "do not repeat that exact command" in prompt
            return '{"tool":"shell","args":{"command":"python broken.py"},"thought_summary":"Try the same command again."}'

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = RepeatFailedCommandModel()  # type: ignore[assignment]
        created = engine.store.create_run("Recover syntax failure", "Repeat guard", str(tmp_path), [])
        created.state.step_count = 1
        created.state.failure_records.append(
            FailureRecord(
                id="failure-1",
                kind="syntax_error",
                tool="shell",
                summary="SyntaxError in broken.py",
                count=1,
                last_seen="2026-06-28T13:00:00+00:00",
                recovery_hint="Read the syntax excerpt, patch the smallest affected file, then run a compile check.",
                command="python broken.py",
                target="broken.py",
                returncode=1,
                evidence_excerpt="SyntaxError: invalid syntax",
            )
        )

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "file_read"
        assert action["args"] == {"path": "broken.py"}
        assert action["model_guard"] == "repeat_failure_command"
        assert action["guarded_failure_id"] == "failure-1"
        assert created.state.model_interactions[-1].fallback_used
        assert "repeated latest failed command" in created.state.model_interactions[-1].summary.lower()
        assert created.state.action_context.selected_tool == "file_read"
        assert any("cmd=python broken.py" in item for item in created.state.action_context.failure_ledger)

    asyncio.run(run())


def test_choose_action_guards_completed_task_repeat_for_ornith(tmp_path) -> None:  # noqa: ANN001
    class CompletedTaskModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            prompt = messages[-1]["content"]
            assert "task_transitions" in prompt
            assert "do not choose an action that repeats that completed task" in prompt
            return json.dumps(
                {
                    "tool": "shell",
                    "args": {"command": "python -m py_compile app.py"},
                    "thought_summary": "Patch app.py safely",
                }
            )

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = CompletedTaskModel()  # type: ignore[assignment]
        created = engine.store.create_run("Continue after source patch", "Task repeat guard", str(tmp_path), [])
        created.state.step_count = 1
        created.state.task_graph = [
            TaskNode(
                id="task-1",
                title="Patch app.py safely",
                status="completed",
                kind="edit",
                evidence=["verification:ok:shell | cmd=python -m py_compile app.py"],
            ),
            TaskNode(
                id="task-2",
                title="Run focused acceptance verification",
                status="pending",
                kind="verify",
            ),
        ]
        created.state.current_task_id = "task-2"
        created.state.repo_map.test_commands = ["pytest -q"]

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "run_tests"
        assert action["args"] == {"command": "pytest -q"}
        assert action["model_guard"] == "completed_task_repeat"
        assert action["guarded_task_id"] == "task-1"
        assert action["current_task_id"] == "task-2"
        assert created.state.model_interactions[-1].fallback_used
        assert "completed task task-1" in created.state.model_interactions[-1].summary
        assert created.state.action_context.selected_tool == "run_tests"
        assert any("completed:task-1:Patch app.py safely" in item for item in created.state.action_context.task_transition_ledger)

    asyncio.run(run())


def test_choose_action_guards_verify_task_edit_tool_for_ornith(tmp_path) -> None:  # noqa: ANN001
    class VerifyTaskPatchModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            prompt = messages[-1]["content"]
            assert "If the current task is verify, choose proof tools" in prompt
            return json.dumps(
                {
                    "tool": "patch_propose",
                    "args": {
                        "title": "Keep editing during verification",
                        "summary": "This should be guarded because the active task is verification.",
                        "files": ["app.py"],
                        "diff": "--- a/app.py\n+++ b/app.py\n@@\n-old\n+new\n",
                    },
                    "thought_summary": "Make another edit before proving the current task.",
                }
            )

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = VerifyTaskPatchModel()  # type: ignore[assignment]
        created = engine.store.create_run("Verify before editing more", "Verify task guard", str(tmp_path), [])
        created.state.step_count = 1
        created.state.task_graph = [
            TaskNode(
                id="task-verify",
                title="Run focused acceptance verification",
                status="pending",
                kind="verify",
            )
        ]
        created.state.current_task_id = "task-verify"
        created.state.repo_map.test_commands = ["pytest -q"]

        action = await engine._choose_action(created, "tiny context")

        assert action["tool"] == "run_tests"
        assert action["args"] == {"command": "pytest -q"}
        assert action["model_guard"] == "current_task_mismatch"
        assert action["guarded_tool"] == "patch_propose"
        assert action["current_task_id"] == "task-verify"
        assert action["current_task_kind"] == "verify"
        assert created.state.model_interactions[-1].fallback_used
        assert "during current verify task" in created.state.model_interactions[-1].summary
        assert created.state.action_context.selected_tool == "run_tests"
        assert created.state.action_context.selected_action.startswith("Re-anchor on current verify task")

    asyncio.run(run())


def test_choose_action_guards_edit_task_proof_tool_for_ornith(tmp_path) -> None:  # noqa: ANN001
    class EditTaskProofModel:
        async def chat(self, messages, *, temperature=0.2, max_tokens=1200):  # noqa: ANN001
            prompt = messages[-1]["content"]
            assert "If the current task is edit and no patch" in prompt
            return json.dumps(
                {
                    "tool": "run_tests",
                    "args": {"command": "pytest -q"},
                    "thought_summary": "Run proof before editing the current task.",
                }
            )

    async def run() -> None:
        engine = make_engine(tmp_path)
        engine.model = EditTaskProofModel()  # type: ignore[assignment]
        created = engine.store.create_run("Edit before verifying", "Edit task guard", str(tmp_path), [])
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
        assert action["current_task_id"] == "task-edit"
        assert action["current_task_kind"] == "edit"
        assert action["guard_reason"] == "edit_task_selected_proof_tool_without_evidence"
        assert created.state.model_interactions[-1].fallback_used
        assert "during current edit task" in created.state.model_interactions[-1].summary
        assert created.state.action_context.selected_tool == "file_read"
        assert created.state.action_context.selected_action.startswith("Re-anchor on current edit task")

    asyncio.run(run())