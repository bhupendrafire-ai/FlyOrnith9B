from pathlib import Path

from app.checkpoint_quality import build_checkpoint_quality
from app.memory import ObsidianMemory
from app.persistence import RunStore
from app.schemas import ReportIntegrityRefreshRecord


def test_checkpoint_quality_blocks_missing_run_note(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume from Obsidian", "Missing note", str(tmp_path), [])

    report = build_checkpoint_quality(
        run,
        run.state,
        note_text="",
        run_note_path=str(tmp_path / "vault" / "Agent Runs" / f"{run.id}.md"),
    )

    assert report.status == "needs_checkpoint"
    assert report.run_note_present is False
    assert report.blocker_count == 1
    assert report.issues[0].id == "run_note_missing"


def test_checkpoint_quality_accepts_checkpoint_with_refresh_anchor(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume with checkpoint quality", "Ready note", str(tmp_path), [])
    run.state.next_step = "Run the checkpoint-quality tests."
    run.state.handoff_summary.resume_prompt = (
        f"Resume AgentOrinth run {run.id}. Active goal: {run.state.goal}. "
        "Next action: Run the checkpoint-quality tests. "
        "Do not reload raw logs; use this handoff and latest compact events."
    )
    run.state.report_integrity_refreshes = [
        ReportIntegrityRefreshRecord(
            event_id=12,
            report_status="ok",
            previous_report_status="needs_refresh",
            reason_count=1,
            reasons=["stale:handoff.next_action | expected=Run tests | actual=Old action"],
        )
    ]

    memory = ObsidianMemory(vault)
    memory.append_run_started(run)
    memory.append_checkpoint(run, run.state, "paused")

    report = build_checkpoint_quality(
        run,
        run.state,
        note_text=memory.read_run_note(run.id),
        run_note_path=str(vault / "Agent Runs" / f"{run.id}.md"),
    )

    assert report.status == "ready"
    assert report.run_note_present is True
    assert report.has_active_goal is True
    assert report.has_next_action is True
    assert report.has_resume_prompt is True
    assert report.has_no_raw_logs_instruction is True
    assert report.expected_report_integrity_refresh is True
    assert report.has_report_integrity_refresh is True
    assert report.expected_refresh_event_id == 12
    assert report.issues == []


def test_checkpoint_quality_flags_missing_refresh_breadcrumb(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume with refresh guard", "Missing refresh", str(tmp_path), [])
    run.state.handoff_summary.resume_prompt = (
        f"Resume AgentOrinth run {run.id}. Do not reload raw logs; use this handoff and latest compact events."
    )
    run.state.report_integrity_refreshes = [
        ReportIntegrityRefreshRecord(
            event_id=21,
            report_status="ok",
            previous_report_status="needs_refresh",
            reason_count=1,
            reasons=["stale:handoff.approval_reviews.review_count | expected=1:2 | actual=1:1"],
        )
    ]
    note = (
        "### Checkpoint: now\n"
        "- Active goal: Resume with refresh guard\n"
        "- Current step: Inspect checkpoint quality\n"
        "- Next action: Inspect checkpoint quality\n"
        f"- Resume prompt: Resume AgentOrinth run {run.id}. Do not reload raw logs; use this handoff.\n"
    )

    report = build_checkpoint_quality(run, run.state, note_text=note)

    assert report.status == "needs_checkpoint"
    assert report.expected_report_integrity_refresh is True
    assert any(issue.id == "report_integrity_refresh_missing" for issue in report.issues)
