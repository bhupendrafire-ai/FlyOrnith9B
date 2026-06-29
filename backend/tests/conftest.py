from __future__ import annotations

from pathlib import Path

from app.config import AppConfig


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        model_name="test-model",
        model_profile="ornith",
        model_base_url="http://localhost:11434/v1",
        model_api_key=None,
        model_timeout_seconds=5,
        model_health_timeout_seconds=5,
        context_window=96000,
        max_loop_steps=6,
        enable_web_tools=True,
        search_provider="browser",
        web_timeout_seconds=5,
        enable_browser_tools=True,
        browser_executable_path=None,
        enable_desktop_control=True,
        desktop_mode="visible_supervised",
        loop_wall_clock_limit_minutes=15,
        checkpoint_every_steps=2,
        context_target_tokens=12000,
        run_heartbeat_interval_seconds=1,
        run_lease_ttl_seconds=5,
        enable_supervisor_auto_resume=False,
        supervisor_auto_resume_max_runs=1,
        approval_mode="balanced",
        enable_workspace_isolation=True,
        workspace_isolation_mode="copy",
        workspace_root=tmp_path / "workspaces",
        workspace_copy_limit_files=3000,
        workspace_path=tmp_path,
        obsidian_vault_path=tmp_path / "vault",
        sqlite_path=tmp_path / "runs.sqlite3",
        cors_origins=("http://127.0.0.1:5173",),
    )
