from pathlib import Path

from app.persistence import RunStore, make_run_id
from app.workspace import WorkspaceManager, build_workspace_diff, promote_workspace_changes


def test_workspace_manager_creates_isolated_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("hello\n", encoding="utf-8")
    (source / "node_modules").mkdir()
    (source / "node_modules" / "skip.js").write_text("skip\n", encoding="utf-8")
    manager = WorkspaceManager(enabled=True, mode="copy", root=tmp_path / "workspaces", copy_limit_files=20)

    isolation = manager.prepare_run_workspace("run-test", source)

    isolated = Path(isolation.workspace_path)
    assert isolation.enabled
    assert isolation.mode == "copy"
    assert (isolated / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert not (isolated / "node_modules" / "skip.js").exists()


def test_store_records_workspace_isolation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
    manager = WorkspaceManager(enabled=True, mode="copy", root=tmp_path / "workspaces", copy_limit_files=20)
    run_id = make_run_id()
    isolation = manager.prepare_run_workspace(run_id, source)
    store = RunStore(tmp_path / "runs.sqlite3")

    run = store.create_run(
        "Use isolated workspace",
        "Workspace run",
        isolation.workspace_path,
        [],
        run_id=run_id,
        workspace_isolation=isolation,
    )

    assert run.workspace_path == isolation.workspace_path
    assert run.state.workspace_isolation.source_path == str(source.resolve())
    assert run.state.handoff_summary.workspace_summary == isolation.summary


def test_workspace_diff_detects_added_modified_and_deleted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "modified.txt").write_text("alpha\n", encoding="utf-8")
    (workspace / "modified.txt").write_text("beta\n", encoding="utf-8")
    (workspace / "added.txt").write_text("new\n", encoding="utf-8")
    (source / "deleted.txt").write_text("old\n", encoding="utf-8")

    diff = build_workspace_diff(source, workspace)
    statuses = {item.path: item.status for item in diff.files}

    assert diff.total_files == 3
    assert statuses == {
        "added.txt": "added",
        "deleted.txt": "deleted",
        "modified.txt": "modified",
    }
    assert "beta" in next(item.diff for item in diff.files if item.path == "modified.txt")


def test_promote_workspace_changes_writes_source_and_backup(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "app.py").write_text("print('old')\n", encoding="utf-8")
    (workspace / "app.py").write_text("print('new')\n", encoding="utf-8")
    (workspace / "new.py").write_text("print('added')\n", encoding="utf-8")

    promotion = promote_workspace_changes(source, workspace, tmp_path / "promotion_backups")

    assert promotion.status == "promoted"
    assert sorted(promotion.files) == ["app.py", "new.py"]
    assert (source / "app.py").read_text(encoding="utf-8") == "print('new')\n"
    assert (source / "new.py").read_text(encoding="utf-8") == "print('added')\n"
    assert Path(promotion.manifest_path).exists()
