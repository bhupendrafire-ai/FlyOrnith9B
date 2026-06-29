from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .schemas import GitCheckpointReport, RunRecord, RunState


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_git_checkpoint_report(run: RunRecord, *, workspace: Path | None = None) -> GitCheckpointReport:
    return build_git_checkpoint_for_workspace(
        Path(workspace or run.workspace_path),
        run_id=run.id,
        state=run.state,
    )


def build_git_checkpoint_for_workspace(
    workspace: Path,
    *,
    run_id: str = "",
    state: RunState | None = None,
) -> GitCheckpointReport:
    workspace_path = workspace.resolve()
    generated_at = utc_stamp()
    base = {
        "run_id": run_id,
        "generated_at": generated_at,
        "workspace_path": str(workspace_path),
    }
    git_dir = _git(workspace_path, "rev-parse", "--git-dir")
    if git_dir.returncode != 0:
        return GitCheckpointReport(
            **base,
            status="not_repo",
            summary="Workspace is not inside a Git repository.",
            recommended_action="Use an initialized Git workspace before expecting local commits or GitHub pushes.",
        )

    repo_root = _git_text(workspace_path, "rev-parse", "--show-toplevel")
    branch = _git_text(workspace_path, "branch", "--show-current") or "detached"
    head_sha = _git_text(workspace_path, "rev-parse", "--short", "HEAD")
    last_commit = _git_text(workspace_path, "log", "-1", "--oneline")
    status_lines = _git_lines(workspace_path, "status", "--short")
    status_branch = _git_text(workspace_path, "status", "-sb")
    remote_lines = _git_lines(workspace_path, "remote", "-v")
    remote_names = sorted({line.split()[0] for line in remote_lines if line.strip()})
    github_remote_count = sum(1 for line in remote_lines if "github.com" in line.lower())
    staged, modified, untracked = _porcelain_counts(status_lines)
    changed = staged + modified + untracked
    ahead_count, behind_count = _ahead_behind(status_branch)
    recent_verification = _recent_verification(state) if state else ""

    if changed:
        if recent_verification:
            status = "commit_recommended"
            recommended = "Commit a scoped local checkpoint, then push once a GitHub remote is configured."
        else:
            status = "verify_first"
            recommended = "Run the narrowest relevant verification before committing this checkpoint."
    elif ahead_count and remote_names:
        status = "push_recommended"
        recommended = "Push the existing local commit(s) to the configured remote."
    elif changed == 0 and remote_names:
        status = "clean"
        recommended = "No commit is needed right now; continue the next verified harness action."
    else:
        status = "needs_remote"
        recommended = "Add a GitHub remote before expecting push-ready checkpoints; local commits can still be made."

    if not remote_names and status == "commit_recommended":
        recommended = "Commit a scoped local checkpoint, then configure a GitHub remote before pushing."
    summary = (
        f"Git checkpoint {status}: changed={changed}, staged={staged}, modified={modified}, "
        f"untracked={untracked}, ahead={ahead_count}, remotes={len(remote_names)}."
    )
    return GitCheckpointReport(
        **base,
        status=status,
        repo_root=repo_root,
        branch=branch,
        head_sha=head_sha,
        last_commit=last_commit,
        remote_names=remote_names,
        remote_count=len(remote_names),
        github_remote_count=github_remote_count,
        staged_count=staged,
        modified_count=modified,
        untracked_count=untracked,
        changed_count=changed,
        ahead_count=ahead_count,
        behind_count=behind_count,
        recent_verification=recent_verification,
        summary=summary,
        recommended_action=recommended,
    )


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(workspace),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _git_text(workspace: Path, *args: str) -> str:
    proc = _git(workspace, *args)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _git_lines(workspace: Path, *args: str) -> list[str]:
    text = _git_text(workspace, *args)
    return [line for line in text.splitlines() if line.strip()]


def _porcelain_counts(lines: list[str]) -> tuple[int, int, int]:
    staged = 0
    modified = 0
    untracked = 0
    for line in lines:
        if line.startswith("??"):
            untracked += 1
            continue
        index = line[0] if line else " "
        worktree = line[1] if len(line) > 1 else " "
        if index != " ":
            staged += 1
        if worktree != " ":
            modified += 1
    return staged, modified, untracked


def _ahead_behind(status_branch: str) -> tuple[int, int]:
    ahead = 0
    behind = 0
    marker = status_branch.split("[", 1)[1].split("]", 1)[0] if "[" in status_branch and "]" in status_branch else ""
    for part in marker.split(","):
        text = part.strip()
        if text.startswith("ahead "):
            ahead = _safe_int(text.removeprefix("ahead "))
        if text.startswith("behind "):
            behind = _safe_int(text.removeprefix("behind "))
    return ahead, behind


def _safe_int(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        return 0


def _recent_verification(state: RunState) -> str:
    for call in reversed(state.tool_calls[-12:]):
        if call.ok and call.name in {"run_tests", "git_diff", "git_status", "shell"}:
            return f"{call.name}: {call.summary[:180]}"
    return ""

