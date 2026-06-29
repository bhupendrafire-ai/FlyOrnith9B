from pathlib import Path

from app.persistence import RunStore
from app.resume_quality import build_resume_prompt_quality


def test_resume_quality_goal_anchor_handles_filename_punctuation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    goal = "Create AgentOrnith_use_cases.pptx in the workspace root with five use cases."
    run = store.create_run(goal, "Filename goal", str(tmp_path), [])
    run.state.next_step = "Run the PowerPoint verification script."
    run.state.handoff_summary.next_action = run.state.next_step
    run.state.handoff_summary.original_goal = goal
    run.state.handoff_summary.resume_prompt = (
        f"Resume AgentOrinth run {run.id}. Read Obsidian first, preserve original goal: {goal} "
        "Do not reload raw logs; use this compact handoff. "
        f"Next action: {run.state.next_step}"
    )

    report = build_resume_prompt_quality(run)

    assert report.has_goal_anchor is True
    assert not any(issue.id == "missing_goal_anchor" for issue in report.issues)
