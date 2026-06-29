from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from app.tools import SafetyGate, ToolRunner, redact_secrets

from conftest import make_config


def test_credential_browser_type_is_blocked(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    decision = SafetyGate(config).classify_tool(
        "browser_type",
        {"selector": "input[name=password]", "text": "hunter2"},
        tmp_path,
    )

    assert not decision.allowed
    assert not decision.needs_approval


def test_desktop_click_needs_supervised_approval(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    decision = SafetyGate(config).classify_tool("desktop_click", {"x": 10, "y": 10}, tmp_path)

    assert not decision.allowed
    assert decision.needs_approval


def test_redacts_secret_like_values() -> None:
    assert "super-secret" not in redact_secrets("api_key=super-secret")
    assert "[REDACTED]" in redact_secrets("api_key=super-secret")


def test_duckduckgo_result_parser_creates_sources(tmp_path: Path) -> None:
    runner = ToolRunner(tmp_path, make_config(tmp_path))
    html = """
    <a rel="nofollow" class="result__a" href="https://example.com">Example <b>Title</b></a>
    <a class="result__snippet">Useful result <b>snippet</b>.</a>
    """

    sources = runner._parse_duckduckgo(html, limit=3)

    assert len(sources) == 1
    assert sources[0].title == "Example Title"
    assert sources[0].url == "https://example.com"


def test_desktop_click_execution_returns_approval(tmp_path: Path) -> None:
    async def run() -> None:
        result = await ToolRunner(tmp_path, make_config(tmp_path)).execute("desktop_click", {"x": 1, "y": 2})
        assert result.needs_approval

    asyncio.run(run())


def test_workspace_autopilot_allows_patch_apply_without_approval(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    decision = SafetyGate(config, approval_mode="workspace_autopilot").classify_tool(
        "patch_apply",
        {"patch_id": "patch-demo", "files": [{"path": "demo.txt", "new": "hello\n"}]},
        tmp_path,
    )

    assert decision.allowed
    assert not decision.needs_approval


def test_bypass_permissions_still_blocks_credential_typing(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    decision = SafetyGate(config, approval_mode="bypass_permissions").classify_tool(
        "desktop_type",
        {"selector": "input[name=password]", "text": "hunter2"},
        tmp_path,
    )

    assert not decision.allowed
    assert not decision.needs_approval


def test_patch_propose_returns_patch_record(tmp_path: Path) -> None:
    async def run() -> None:
        result = await ToolRunner(tmp_path, make_config(tmp_path)).execute(
            "patch_propose",
            {"title": "Edit README", "files": ["README.md"], "diff": "--- a/README.md"},
        )
        assert result.ok
        assert result.patch_proposals[0].title == "Edit README"
        assert result.patch_proposals[0].files == ["README.md"]

    asyncio.run(run())


def test_patch_apply_requires_approval(tmp_path: Path) -> None:
    async def run() -> None:
        result = await ToolRunner(tmp_path, make_config(tmp_path)).execute(
            "patch_apply",
            {"patch_id": "patch-demo", "files": [{"path": "demo.txt", "new": "hello\n"}]},
        )
        assert result.needs_approval

    asyncio.run(run())


def test_patch_apply_and_rollback_restore_file(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")

    async def run() -> None:
        runner = ToolRunner(tmp_path, make_config(tmp_path))
        applied = await runner.execute(
            "patch_apply",
            {
                "patch_id": "patch-demo",
                "title": "Update demo",
                "files": [{"path": "demo.txt", "old": "hello\n", "new": "hello world\n"}],
            },
            approved=True,
        )
        assert applied.ok
        assert target.read_text(encoding="utf-8") == "hello world\n"
        assert applied.patch_applications[0].backup_id

        rolled_back = await runner.execute(
            "patch_rollback",
            {"backup_id": applied.patch_applications[0].backup_id},
            approved=True,
        )
        assert rolled_back.ok
        assert target.read_text(encoding="utf-8") == "hello\n"

    asyncio.run(run())


def test_patch_apply_accepts_simple_unified_diff(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    diff = """--- a/demo.txt
+++ b/demo.txt
@@ -1,2 +1,2 @@
 alpha
-beta
+gamma
"""

    async def run() -> None:
        result = await ToolRunner(tmp_path, make_config(tmp_path)).execute(
            "patch_apply",
            {"patch_id": "patch-diff", "diff": diff},
            approved=True,
        )
        assert result.ok
        assert target.read_text(encoding="utf-8") == "alpha\ngamma\n"

    asyncio.run(run())


def test_workspace_diff_against_source_needs_approval(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    config = make_config(tmp_path)

    decision = SafetyGate(config).classify_tool("workspace_diff", {"source_path": str(source)}, workspace)

    assert not decision.allowed
    assert decision.needs_approval


def test_workspace_promote_tool_requires_approval_and_promotes_when_approved(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "README.md").write_text("old\n", encoding="utf-8")
    (workspace / "README.md").write_text("new\n", encoding="utf-8")

    async def run() -> None:
        runner = ToolRunner(workspace, make_config(tmp_path))
        pending = await runner.execute("workspace_promote", {"source_path": str(source)})
        assert pending.needs_approval

        promoted = await runner.execute("workspace_promote", {"source_path": str(source)}, approved=True)
        assert promoted.ok
        assert promoted.workspace_promotions[0].files == ["README.md"]
        assert (source / "README.md").read_text(encoding="utf-8") == "new\n"

    asyncio.run(run())

def test_git_checkpoint_tool_reports_commit_posture(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    async def run() -> None:
        runner = ToolRunner(tmp_path, make_config(tmp_path))
        decision = runner.safety.classify_tool("git_checkpoint", {}, tmp_path)
        assert decision.allowed
        assert not decision.needs_approval

        result = await runner.execute("git_checkpoint")

        assert result.ok
        assert result.kind == "git_checkpoint"
        assert result.git_checkpoint is not None
        assert result.git_checkpoint.untracked_count == 1
        assert result.git_checkpoint.status == "verify_first"
        assert "git_checkpoint" in result.data

    asyncio.run(run())
