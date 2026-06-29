from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .acceptance import EVIDENCE_LABEL_WORDS


def _parse_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


@dataclass(frozen=True)
class AppConfig:
    model_name: str
    model_profile: str
    model_base_url: str
    model_api_key: str | None
    model_timeout_seconds: int
    model_health_timeout_seconds: int
    context_window: int
    max_loop_steps: int
    enable_web_tools: bool
    search_provider: str
    web_timeout_seconds: int
    enable_browser_tools: bool
    browser_executable_path: str | None
    enable_desktop_control: bool
    desktop_mode: str
    loop_wall_clock_limit_minutes: int
    checkpoint_every_steps: int
    context_target_tokens: int
    run_heartbeat_interval_seconds: int
    run_lease_ttl_seconds: int
    enable_supervisor_auto_resume: bool
    supervisor_auto_resume_max_runs: int
    approval_mode: str
    enable_workspace_isolation: bool
    workspace_isolation_mode: str
    workspace_root: Path
    workspace_copy_limit_files: int
    workspace_path: Path
    obsidian_vault_path: Path
    sqlite_path: Path
    cors_origins: tuple[str, ...]
    completion_strict_stale_evidence: bool = True
    completion_stale_edit_tools: tuple[str, ...] = (
        "file_write",
        "patch_apply",
        "patch_rollback",
        "workspace_promote",
    )
    completion_verification_tools: tuple[str, ...] = ("run_tests", "shell", "git_diff")
    completion_checkpoint_tools: tuple[str, ...] = ("checkpoint", "obsidian_checkpoint")
    completion_browser_tools: tuple[str, ...] = ("browser_open", "browser_screenshot", "desktop_screenshot")
    completion_edit_tools: tuple[str, ...] = ("patch_apply", "patch_propose", "file_write", "workspace_promote")
    completion_web_tools: tuple[str, ...] = ("web_search", "web_fetch")

    @classmethod
    def from_env(cls) -> "AppConfig":
        project_root = Path(__file__).resolve().parents[2]
        try:
            from dotenv import load_dotenv

            load_dotenv(project_root / ".env")
        except ImportError:
            pass

        default_workspace = project_root.parent
        default_vault = Path(r"C:\Users\Piculiar\Documents\second-brain")
        sqlite_path = Path(os.getenv("SQLITE_PATH", str(project_root / "data" / "agent_runs.sqlite3")))
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

        return cls(
            model_name=os.getenv("MODEL_NAME", "ornith-9b-q4-96k"),
            model_profile=os.getenv("MODEL_PROFILE", "ornith"),
            model_base_url=os.getenv("MODEL_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
            model_api_key=os.getenv("MODEL_API_KEY") or None,
            model_timeout_seconds=max(5, _parse_int("MODEL_TIMEOUT_SECONDS", 60)),
            model_health_timeout_seconds=max(5, _parse_int("MODEL_HEALTH_TIMEOUT_SECONDS", 20)),
            context_window=_parse_int("CONTEXT_WINDOW", 96000),
            max_loop_steps=max(1, _parse_int("MAX_LOOP_STEPS", 8)),
            enable_web_tools=_parse_bool("ENABLE_WEB_TOOLS", True),
            search_provider=os.getenv("SEARCH_PROVIDER", "browser"),
            web_timeout_seconds=max(5, _parse_int("WEB_TIMEOUT_SECONDS", 30)),
            enable_browser_tools=_parse_bool("ENABLE_BROWSER_TOOLS", True),
            browser_executable_path=os.getenv("BROWSER_EXECUTABLE_PATH") or cls._default_browser_path(),
            enable_desktop_control=_parse_bool("ENABLE_DESKTOP_CONTROL", True),
            desktop_mode=os.getenv("DESKTOP_MODE", "visible_supervised"),
            loop_wall_clock_limit_minutes=max(1, _parse_int("LOOP_WALL_CLOCK_LIMIT_MINUTES", 90)),
            checkpoint_every_steps=max(1, _parse_int("CHECKPOINT_EVERY_STEPS", 3)),
            context_target_tokens=max(1000, _parse_int("CONTEXT_TARGET_TOKENS", 24000)),
            run_heartbeat_interval_seconds=max(1, _parse_int("RUN_HEARTBEAT_INTERVAL_SECONDS", 15)),
            run_lease_ttl_seconds=max(5, _parse_int("RUN_LEASE_TTL_SECONDS", 90)),
            enable_supervisor_auto_resume=_parse_bool("ENABLE_SUPERVISOR_AUTO_RESUME", False),
            supervisor_auto_resume_max_runs=max(0, _parse_int("SUPERVISOR_AUTO_RESUME_MAX_RUNS", 1)),
            approval_mode=os.getenv("APPROVAL_MODE", "balanced"),
            enable_workspace_isolation=_parse_bool("ENABLE_WORKSPACE_ISOLATION", True),
            workspace_isolation_mode=os.getenv("WORKSPACE_ISOLATION_MODE", "copy"),
            workspace_root=Path(os.getenv("WORKSPACE_ROOT", str(project_root / "data" / "workspaces"))).resolve(),
            workspace_copy_limit_files=max(1, _parse_int("WORKSPACE_COPY_LIMIT_FILES", 3000)),
            workspace_path=Path(os.getenv("WORKSPACE_PATH", str(default_workspace))).resolve(),
            obsidian_vault_path=Path(os.getenv("OBSIDIAN_VAULT_PATH", str(default_vault))).resolve(),
            sqlite_path=sqlite_path.resolve(),
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
            completion_strict_stale_evidence=_parse_bool("COMPLETION_STRICT_STALE_EVIDENCE", True),
            completion_stale_edit_tools=_parse_csv(
                "COMPLETION_STALE_EDIT_TOOLS",
                ("file_write", "patch_apply", "patch_rollback", "workspace_promote"),
            ),
            completion_verification_tools=_parse_csv("COMPLETION_VERIFICATION_TOOLS", ("run_tests", "shell", "git_diff")),
            completion_checkpoint_tools=_parse_csv(
                "COMPLETION_CHECKPOINT_TOOLS",
                ("checkpoint", "obsidian_checkpoint"),
            ),
            completion_browser_tools=_parse_csv(
                "COMPLETION_BROWSER_TOOLS",
                ("browser_open", "browser_screenshot", "desktop_screenshot"),
            ),
            completion_edit_tools=_parse_csv(
                "COMPLETION_EDIT_TOOLS",
                ("patch_apply", "patch_propose", "file_write", "workspace_promote"),
            ),
            completion_web_tools=_parse_csv("COMPLETION_WEB_TOOLS", ("web_search", "web_fetch")),
        )

    def public_dict(self) -> dict[str, str | int | bool | list[str] | dict[str, list[str]]]:
        return {
            "model_name": self.model_name,
            "model_profile": self.model_profile,
            "model_base_url": self.model_base_url,
            "model_api_key_configured": bool(self.model_api_key),
            "model_timeout_seconds": self.model_timeout_seconds,
            "model_health_timeout_seconds": self.model_health_timeout_seconds,
            "context_window": self.context_window,
            "max_loop_steps": self.max_loop_steps,
            "enable_web_tools": self.enable_web_tools,
            "search_provider": self.search_provider,
            "web_timeout_seconds": self.web_timeout_seconds,
            "enable_browser_tools": self.enable_browser_tools,
            "browser_executable_path": self.browser_executable_path or "",
            "enable_desktop_control": self.enable_desktop_control,
            "desktop_mode": self.desktop_mode,
            "loop_wall_clock_limit_minutes": self.loop_wall_clock_limit_minutes,
            "checkpoint_every_steps": self.checkpoint_every_steps,
            "context_target_tokens": self.context_target_tokens,
            "run_heartbeat_interval_seconds": self.run_heartbeat_interval_seconds,
            "run_lease_ttl_seconds": self.run_lease_ttl_seconds,
            "enable_supervisor_auto_resume": self.enable_supervisor_auto_resume,
            "supervisor_auto_resume_max_runs": self.supervisor_auto_resume_max_runs,
            "approval_mode": self.approval_mode,
            "approval_modes": ["always_ask", "balanced", "workspace_autopilot", "bypass_permissions"],
            "enable_workspace_isolation": self.enable_workspace_isolation,
            "workspace_isolation_mode": self.workspace_isolation_mode,
            "workspace_root": str(self.workspace_root),
            "workspace_copy_limit_files": self.workspace_copy_limit_files,
            "workspace_path": str(self.workspace_path),
            "obsidian_vault_path": str(self.obsidian_vault_path),
            "sqlite_path": str(self.sqlite_path),
            "cors_origins": list(self.cors_origins),
            "completion_evidence_labels": {
                label: sorted(words)
                for label, words in EVIDENCE_LABEL_WORDS.items()
            },
            "completion_strict_stale_evidence": self.completion_strict_stale_evidence,
            "completion_stale_edit_tools": list(self.completion_stale_edit_tools),
            "completion_verification_tools": list(self.completion_verification_tools),
            "completion_checkpoint_tools": list(self.completion_checkpoint_tools),
            "completion_browser_tools": list(self.completion_browser_tools),
            "completion_edit_tools": list(self.completion_edit_tools),
            "completion_web_tools": list(self.completion_web_tools),
        }

    def completion_policy_dict(self) -> dict[str, bool | list[str] | dict[str, list[str]]]:
        return {
            "strict_stale_evidence": self.completion_strict_stale_evidence,
            "evidence_labels": {
                label: sorted(words)
                for label, words in EVIDENCE_LABEL_WORDS.items()
            },
            "stale_edit_tools": list(self.completion_stale_edit_tools),
            "verification_tools": list(self.completion_verification_tools),
            "checkpoint_tools": list(self.completion_checkpoint_tools),
            "browser_tools": list(self.completion_browser_tools),
            "edit_tools": list(self.completion_edit_tools),
            "web_tools": list(self.completion_web_tools),
        }

    @staticmethod
    def _default_browser_path() -> str | None:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None
