import re
from pathlib import Path

from app.memory import ObsidianMemory
from app.persistence import RunStore
from app.schemas import CheckpointQualityResumeRecord, CheckpointQualityResumeReport, FailureRecord, ReportIntegrityRefreshRecord, SelfScaffoldChangeRecord, SelfScaffoldReport


def test_consult_prioritizes_workflow_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    resources = vault / "30-Resources"
    areas = vault / "20-Areas"
    resources.mkdir(parents=True)
    areas.mkdir(parents=True)
    (areas / "Coding Projects.md").write_text("Ornith local-ai coding workflow checkpoint", encoding="utf-8")
    (resources / "Agentic Coding Workflow.md").write_text("Read Obsidian before code.", encoding="utf-8")

    context = ObsidianMemory(vault).consult("Build Ornith agentic harness")

    assert context.hits
    assert any("Coding Projects.md" in hit.path for hit in context.hits)


def test_run_notes_redact_secret_like_values(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Use api_key=super-secret-value while testing redaction",
        title="Secret test",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    note = memory.read_run_note(run.id)

    assert "super-secret-value" not in note
    assert "[REDACTED]" in note


def test_daily_checkpoint_formats_run_started_in_local_time(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Keep human timestamps local",
        title="Local timestamp checkpoint",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    ).model_copy(update={"created_at": "2026-06-29T10:26:20+00:00"})

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    assert "- Started: 2026-06-29T10:26:20+00:00" not in daily
    assert re.search(r"- Started: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", daily)


def test_checkpoint_notes_include_report_integrity_refresh_reason(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Resume with compact refresh reason",
        title="Refresh reason checkpoint",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )
    reason = "stale:handoff.current_objective | expected=New api_key=secret-value | actual=Old"
    run.state.report_integrity_refreshes = [
        ReportIntegrityRefreshRecord(
            event_id=7,
            report_status="ok",
            previous_report_status="needs_refresh",
            reason_count=1,
            reasons=[reason],
            preflight_event_id=8,
            preflight_event_kind="resume_preflight_blocked",
            preflight_accepted=False,
        )
    ]

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    note = memory.read_run_note(run.id)
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    assert "Report integrity refresh: #7 needs_refresh->ok reasons=1 preflight=#8:resume_preflight_blocked" in note
    assert "stale:handoff.current_objective" in note
    assert "secret-value" not in note
    assert "[REDACTED]" in note
    assert "Report integrity refresh: #7 needs_refresh->ok reasons=1" in daily


def test_checkpoint_notes_include_checkpoint_quality_resume_repair(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Resume after checkpoint-quality repair",
        title="Checkpoint repair resume",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )
    run.state.checkpoint_quality_resumes = CheckpointQualityResumeReport(
        run_id=run.id,
        generated_at="2026-06-28T13:00:00+00:00",
        status="resumed",
        repair_count=1,
        resumed_after_repair_count=1,
        blocked_after_repair_count=0,
        awaiting_resume_count=0,
        latest=CheckpointQualityResumeRecord(
            repair_event_id=7,
            repair_completed_event_id=7,
            repair_reason="checkpoint_quality",
            repair_ui_target="handoff_refresh",
            resume_event_id=9,
            resume_accepted=True,
            resume_policy_action="verify",
            checkpoint_quality_status="ready",
            checkpoint_quality_ready=True,
        ),
    )

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    memory.append_final(run, run.state)
    note = memory.read_run_note(run.id)
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    expected = (
        "Checkpoint-quality resume repair: resumed repairs=1 resumed=1 blocked=0 awaiting=0 "
        "repair=#7:checkpoint_quality:handoff_refresh resume=#9:verify:accepted checkpoint=ready:True"
    )
    assert expected in note
    assert note.count(expected) == 2
    assert expected in daily


def test_checkpoint_notes_include_redacted_compact_failure_context(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Resume after a syntax failure",
        title="Failure context checkpoint",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )
    run.state.failure_records.append(
        FailureRecord(
            id="failure-1",
            kind="syntax_error",
            tool="shell",
            summary="exit 1: python broken.py",
            count=2,
            last_seen="2026-06-28T13:00:00+00:00",
            recovery_hint="Read the syntax excerpt, patch the smallest affected file, then run a compile check.",
            command="python broken.py",
            target="broken.py",
            returncode=1,
            evidence_excerpt="SyntaxError: invalid syntax api_key=super-secret",
        )
    )

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    memory.append_final(run, run.state)
    note = memory.read_run_note(run.id)
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    expected = "Failure context: latest=syntax_error:shell:x2 cmd=python broken.py target=broken.py rc=1"
    assert expected in note
    assert note.count("Failure context: latest=syntax_error:shell:x2") == 2
    assert expected in daily
    assert "super-secret" not in note
    assert "super-secret" not in daily
    assert "[REDACTED]" in note


def test_checkpoint_notes_include_task_transition_ledger(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Resume after task transition",
        title="Task transition checkpoint",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )
    run.state.action_context.task_transition_ledger = [
        "completed:task-1:Patch app.py safely; evidence=verification:ok:shell | cmd=python -m py_compile app.py",
        "current:pending:task-2:Run focused acceptance verification",
    ]

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    memory.append_final(run, run.state)
    note = memory.read_run_note(run.id)
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    assert "Task transitions: [completed:task-1:Patch app.py safely" in note
    assert "verification:ok:shell" in note
    assert "current:pending:task-2:Run focused acceptance verification" in note
    assert note.count("Task transitions: [completed:task-1:Patch app.py safely") == 2
    assert "Task transitions: [completed:task-1:Patch app.py safely" in daily


def test_checkpoint_notes_include_model_guard_and_edit_evidence_ledgers(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Resume with guard and edit evidence",
        title="Guard edit evidence checkpoint",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )
    run.state.action_context.model_guard_ledger = [
        "current_task_mismatch; tool=file_read; from=run_tests; current=task-edit; kind=edit; reason=edit_task_selected_proof_tool_without_evidence"
    ]
    run.state.action_context.edit_evidence_ledger = [
        "patch:pending:patch-1:app.py; Patch app.py safely",
        "touched:app.py",
    ]

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    memory.append_final(run, run.state)
    note = memory.read_run_note(run.id)
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    assert "Model guards: [current_task_mismatch; tool=file_read; from=run_tests" in note
    assert "reason=edit_task_selected_proof_tool_without_evidence" in note
    assert "Edit evidence: [patch:pending:patch-1:app.py; Patch app.py safely; touched:app.py]" in note
    assert note.count("Model guards: [current_task_mismatch") == 2
    assert "Model guards: [current_task_mismatch; tool=file_read; from=run_tests" in daily
    assert "Edit evidence: [patch:pending:patch-1:app.py; Patch app.py safely; touched:app.py]" in daily


def test_checkpoint_notes_include_self_scaffold_intent(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Resume with self scaffold intent",
        title="Self scaffold checkpoint",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )
    run.state.self_scaffold = SelfScaffoldReport(
        run_id=run.id,
        generated_at="2026-06-27T08:00:00+00:00",
        status="needs_review",
        change_count=1,
        reversible_count=1,
        summary="1 self-scaffold change needs review.",
        changes=[
            SelfScaffoldChangeRecord(
                id="guard-1",
                kind="model_guard",
                status="needs_review",
                summary="A model guard changed the selected action.",
                intent="Protect Ornith from stale task/tool mismatch.",
                reverse_hint="Steer or replan to choose a different task/tool.",
            )
        ],
    )

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    memory.append_final(run, run.state)
    note = memory.read_run_note(run.id)
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    assert "Self scaffold: needs_review changes=1 reversible=1" in note
    assert "model_guard:needs_review:A model guard changed the selected action" in note
    assert "reverse=Steer or replan to choose a different task/tool." in note
    assert "Self scaffold: needs_review changes=1 reversible=1" in daily

def test_checkpoint_notes_report_no_checkpoint_quality_resume_repair_for_ordinary_run(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        goal="Ordinary checkpoint without checkpoint-quality repair",
        title="Ordinary checkpoint",
        workspace_path=str(tmp_path),
        acceptance_criteria=[],
    )

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")
    note = memory.read_run_note(run.id)
    daily = next((vault / "Daily").glob("*.md")).read_text(encoding="utf-8")

    assert "Checkpoint-quality resume repair: []" in note
    assert "Checkpoint-quality resume repair: []" in daily
    assert "Failure context: []" in note
    assert "Failure context: []" in daily
    assert "Task transitions: [current:pending:task-orient" in note
    assert "Task transitions: [current:pending:task-orient" in daily
    assert "repair=#" not in note
    assert "repair=#" not in daily
