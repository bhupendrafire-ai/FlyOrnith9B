from __future__ import annotations

import asyncio
import base64
import html
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from uuid import uuid4

import httpx

from .config import AppConfig
from .git_checkpoints import build_git_checkpoint_for_workspace
from .schemas import DesktopSnapshot, GitCheckpointReport, PatchApplication, PatchProposal, WebSource, WorkspaceDiffSummary, WorkspacePromotion
from .workspace import build_workspace_diff, promote_workspace_changes


TOOL_NAMES = [
    "web_search",
    "web_fetch",
    "browser_open",
    "browser_screenshot",
    "browser_click",
    "browser_type",
    "desktop_screenshot",
    "desktop_window_list",
    "desktop_click",
    "desktop_type",
    "shell",
    "file_read",
    "file_write",
    "git_status",
    "git_diff",
    "git_checkpoint",
    "run_tests",
    "obsidian_search",
    "obsidian_checkpoint",
    "ask_user",
    "patch_propose",
    "patch_apply",
    "patch_rollback",
    "workspace_diff",
    "workspace_promote",
]


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
]
CREDENTIAL_FIELD_PATTERN = re.compile(r"(?i)(password|token|secret|api[_-]?key|credential|otp|2fa)")
DOWNLOAD_PATTERN = re.compile(r"(?i)\.(exe|msi|bat|cmd|ps1|zip|7z|rar|dll)(\?|$)")


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    needs_approval: bool
    reason: str


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    kind: str
    summary: str
    data: dict[str, Any]
    needs_approval: bool = False
    web_sources: list[WebSource] = field(default_factory=list)
    desktop_snapshots: list[DesktopSnapshot] = field(default_factory=list)
    patch_proposals: list[PatchProposal] = field(default_factory=list)
    patch_applications: list[PatchApplication] = field(default_factory=list)
    workspace_diff: WorkspaceDiffSummary | None = None
    workspace_promotions: list[WorkspacePromotion] = field(default_factory=list)
    git_checkpoint: GitCheckpointReport | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_secrets(value: str) -> str:
    sanitized = value or ""
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(lambda match: f"{match.group(1) if match.groups() else 'secret'}=[REDACTED]", sanitized)
    return sanitized


def compact_text(text: str, limit: int = 5000) -> str:
    text = re.sub(r"\s+", " ", html.unescape(text or "")).strip()
    return redact_secrets(text[:limit])


class ToolRegistry:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def public_config(self) -> dict[str, Any]:
        disabled: set[str] = set()
        if not self.config.enable_web_tools:
            disabled.update({"web_search", "web_fetch"})
        if not self.config.enable_browser_tools:
            disabled.update({"browser_open", "browser_screenshot", "browser_click", "browser_type"})
        if not self.config.enable_desktop_control:
            disabled.update({"desktop_screenshot", "desktop_window_list", "desktop_click", "desktop_type"})
        return {
            "tools": [{"name": name, "enabled": name not in disabled} for name in TOOL_NAMES],
            "policy": {
                "web": "tool-gated",
                "search_provider": self.config.search_provider,
                "desktop_mode": self.config.desktop_mode,
                "approval_mode": self.config.approval_mode,
                "approval_modes": ["always_ask", "balanced", "workspace_autopilot", "bypass_permissions"],
                "destructive_actions_need_approval": True,
                "credential_typing_blocked": True,
            },
        }


class SafetyGate:
    GLOBAL_COMMAND_PATTERNS = [
        r"\bwinget\s+install\b",
        r"\bchoco\s+install\b",
        r"\bscoop\s+install\b",
        r"\bnpm\s+install\s+-g\b",
        r"\bpip\s+install\s+--user\b",
        r"\bSet-ExecutionPolicy\b",
        r"\bwsl\s+--install\b",
        r"\breg\s+(add|delete|import)\b",
    ]
    DESTRUCTIVE_COMMAND_PATTERNS = [
        r"\brm\s+-rf\b",
        r"\bRemove-Item\b.*(?:^|\s)-Recurse\b",
        r"\bdel\s+/s\b",
        r"\brmdir\s+/s\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+clean\b.*-f",
        r"\bformat\b",
    ]

    def __init__(self, config: AppConfig | None = None, approval_mode: str | None = None) -> None:
        self.config = config
        self.approval_mode = approval_mode or (config.approval_mode if config else "balanced")

    def classify_tool(self, tool_name: str, args: dict[str, Any], workspace: Path) -> SafetyDecision:
        if self.approval_mode == "always_ask" and tool_name in {
            "shell",
            "run_tests",
            "file_write",
            "web_fetch",
            "browser_click",
            "browser_type",
            "desktop_click",
            "desktop_type",
            "patch_apply",
            "patch_rollback",
            "workspace_diff",
            "workspace_promote",
        }:
            if tool_name in {"browser_type", "desktop_type"} and self._looks_like_credential_entry(args):
                return SafetyDecision(False, False, "Credential or secret entry is blocked.")
            return SafetyDecision(False, True, f"Approval mode always_ask requires approval for {tool_name}.")
        if tool_name in {"shell", "git_status", "git_diff", "git_checkpoint", "run_tests"}:
            command = self._command_for_tool(tool_name, args)
            return self.classify_command(command)
        if tool_name in {"file_read", "file_write"}:
            target = (workspace / str(args.get("path", ""))).resolve()
            return self.classify_path(workspace, target)
        if tool_name in {"web_search", "web_fetch"}:
            if self.config and not self.config.enable_web_tools:
                return SafetyDecision(False, False, "Web tools are disabled.")
            url = str(args.get("url", ""))
            if tool_name == "web_fetch" and DOWNLOAD_PATTERN.search(urlparse(url).path):
                return SafetyDecision(False, True, "Fetching executable/downloadable files needs approval.")
            return SafetyDecision(True, False, "Allowed web tool.")
        if tool_name.startswith("browser_"):
            if self.config and not self.config.enable_browser_tools:
                return SafetyDecision(False, False, "Browser tools are disabled.")
            if tool_name == "browser_type" and self._looks_like_credential_entry(args):
                return SafetyDecision(False, False, "Credential or secret entry is blocked.")
            return SafetyDecision(True, False, "Allowed browser tool.")
        if tool_name.startswith("desktop_"):
            if self.config and not self.config.enable_desktop_control:
                return SafetyDecision(False, False, "Desktop control is disabled.")
            if tool_name == "desktop_type" and self._looks_like_credential_entry(args):
                return SafetyDecision(False, False, "Credential or secret entry is blocked.")
            if tool_name in {"desktop_click", "desktop_type"}:
                return self._mode_decision(tool_name, SafetyDecision(False, True, "Supervised desktop click/type needs user approval."))
            return SafetyDecision(True, False, "Allowed desktop inspection.")
        if tool_name in {"obsidian_search", "obsidian_checkpoint", "ask_user"}:
            return SafetyDecision(True, False, "Allowed control tool.")
        if tool_name == "patch_propose":
            return SafetyDecision(True, False, "Allowed patch proposal.")
        if tool_name in {"patch_apply", "patch_rollback"}:
            return self._mode_decision(tool_name, SafetyDecision(False, True, "Patch apply/rollback changes files and needs approval."))
        if tool_name == "workspace_diff":
            source_path = str(args.get("source_path") or "").strip()
            if source_path:
                source = Path(source_path).resolve()
                try:
                    source.relative_to(workspace.resolve())
                    return SafetyDecision(True, False, "Allowed same-workspace diff.")
                except ValueError:
                    return self._mode_decision(tool_name, SafetyDecision(False, True, "Diffing against the source workspace needs approval."))
            return SafetyDecision(True, False, "Allowed workspace diff.")
        if tool_name == "workspace_promote":
            return self._mode_decision(tool_name, SafetyDecision(False, True, "Promoting isolated workspace changes to source needs approval."))
        return SafetyDecision(False, False, f"Unknown tool: {tool_name}")

    def classify_command(self, command: str) -> SafetyDecision:
        lowered = command.lower()
        for pattern in self.DESTRUCTIVE_COMMAND_PATTERNS:
            if re.search(pattern, command, flags=re.IGNORECASE):
                return SafetyDecision(False, True, "Command looks destructive and needs explicit approval.")
        for pattern in self.GLOBAL_COMMAND_PATTERNS:
            if re.search(pattern, command, flags=re.IGNORECASE):
                return SafetyDecision(False, True, "Command affects global machine state and needs approval.")
        redirection_scan = self._strip_quoted_segments(command)
        redirection_scan = re.sub(r"\b\d?>&\d\b", "", redirection_scan)
        if ">" in redirection_scan and not re.search(r"\b(out-file|tee-object)\b", lowered):
            return self._mode_decision("shell", SafetyDecision(False, True, "Shell redirection can overwrite files; use the file tool or approve it."))
        return SafetyDecision(True, False, "Allowed workspace command.")

    def classify_path(self, workspace: Path, target: Path) -> SafetyDecision:
        try:
            workspace_resolved = workspace.resolve()
            target_resolved = target.resolve()
            target_resolved.relative_to(workspace_resolved)
        except (ValueError, OSError):
            return self._mode_decision("file_path", SafetyDecision(False, True, "Path is outside WORKSPACE_PATH and needs approval."))
        return SafetyDecision(True, False, "Path is inside WORKSPACE_PATH.")

    def _mode_decision(self, tool_name: str, decision: SafetyDecision) -> SafetyDecision:
        if not decision.needs_approval:
            return decision
        mode = self.approval_mode
        if mode == "workspace_autopilot" and tool_name in {"patch_apply", "patch_rollback", "workspace_diff"}:
            return SafetyDecision(True, False, f"Approval mode workspace_autopilot allowed {tool_name}.")
        if mode == "bypass_permissions" and tool_name in {
            "desktop_click",
            "desktop_type",
            "patch_apply",
            "patch_rollback",
            "workspace_diff",
            "workspace_promote",
            "shell",
            "file_path",
        }:
            return SafetyDecision(True, False, f"Approval mode bypass_permissions allowed {tool_name}.")
        return decision

    def _command_for_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "git_status":
            return "git status --short"
        if tool_name == "git_diff":
            return "git diff --stat"
        if tool_name == "git_checkpoint":
            return "git status --short"
        if tool_name == "run_tests":
            return str(args.get("command") or "python -m pytest")
        return str(args.get("command", ""))

    def _looks_like_credential_entry(self, args: dict[str, Any]) -> bool:
        haystack = " ".join(str(value) for value in args.values())
        return bool(CREDENTIAL_FIELD_PATTERN.search(haystack) or any(pattern.search(haystack) for pattern in SECRET_PATTERNS))

    def _strip_quoted_segments(self, command: str) -> str:
        return re.sub(r"(['\"]).*?\1", "", command)


class ToolRunner:
    def __init__(
        self,
        workspace: Path,
        config: AppConfig,
        safety: SafetyGate | None = None,
        approval_mode: str | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.config = config
        self.safety = safety or SafetyGate(config, approval_mode=approval_mode)
        self.artifact_dir = (Path(__file__).resolve().parents[2] / "data" / "artifacts").resolve()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.patch_backup_dir = (Path(__file__).resolve().parents[2] / "data" / "patch_backups").resolve()
        self.patch_backup_dir.mkdir(parents=True, exist_ok=True)
        self.promotion_backup_dir = (Path(__file__).resolve().parents[2] / "data" / "promotion_backups").resolve()
        self.promotion_backup_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, tool_name: str, args: dict[str, Any] | None = None, *, approved: bool = False) -> ToolResult:
        args = args or {}
        decision = self.safety.classify_tool(tool_name, args, self.workspace)
        if decision.needs_approval and not approved:
            return ToolResult(False, tool_name, decision.reason, args, needs_approval=True)
        if not decision.allowed and not approved:
            return ToolResult(False, tool_name, decision.reason, args)

        if tool_name == "shell":
            return await self.run_command(str(args.get("command", "")), timeout=int(args.get("timeout", 60)), approved=True)
        if tool_name == "git_status":
            return await self.run_command("git status --short", timeout=30, approved=True)
        if tool_name == "git_diff":
            return await self.run_command(str(args.get("command") or "git diff --stat"), timeout=30, approved=True)
        if tool_name == "git_checkpoint":
            checkpoint = build_git_checkpoint_for_workspace(self.workspace)
            return ToolResult(
                True,
                "git_checkpoint",
                checkpoint.summary,
                {"git_checkpoint": checkpoint.model_dump()},
                git_checkpoint=checkpoint,
            )
        if tool_name == "run_tests":
            return await self.run_command(str(args.get("command") or "python -m pytest"), timeout=int(args.get("timeout", 120)), approved=True)
        if tool_name == "file_read":
            return self.read_file(str(args.get("path", "")), limit=int(args.get("limit", 20000)))
        if tool_name == "file_write":
            return self.write_file(str(args.get("path", "")), str(args.get("content", "")), approved=True)
        if tool_name == "web_search":
            return await self.web_search(str(args.get("query", "")), limit=int(args.get("limit", 5)))
        if tool_name == "web_fetch":
            return await self.web_fetch(str(args.get("url", "")))
        if tool_name == "browser_open":
            return await self.browser_open(str(args.get("url", "")))
        if tool_name == "browser_screenshot":
            return await self.browser_screenshot(str(args.get("url", "about:blank")))
        if tool_name in {"browser_click", "browser_type"}:
            return ToolResult(True, tool_name, "Browser interaction recorded; live session execution is reserved for supervised mode.", args)
        if tool_name == "desktop_window_list":
            return await self.desktop_window_list()
        if tool_name == "desktop_screenshot":
            return await self.desktop_screenshot()
        if tool_name in {"desktop_click", "desktop_type"}:
            return ToolResult(True, tool_name, "Approved supervised desktop action recorded.", args)
        if tool_name == "obsidian_search":
            return ToolResult(True, tool_name, "Obsidian search is handled by the memory adapter before each milestone.", args)
        if tool_name == "obsidian_checkpoint":
            return ToolResult(True, tool_name, "Checkpoint requested for the current milestone.", args)
        if tool_name == "ask_user":
            return ToolResult(False, tool_name, str(args.get("question", "User input requested.")), args, needs_approval=True)
        if tool_name == "patch_propose":
            proposal = PatchProposal(
                id=f"patch-{uuid4().hex[:8]}",
                title=str(args.get("title") or "Patch proposal"),
                summary=str(args.get("summary") or ""),
                files=[str(item) for item in args.get("files", [])] if isinstance(args.get("files"), list) else [],
                diff=str(args.get("diff") or ""),
                created_at=utc_now(),
            )
            return ToolResult(
                True,
                "patch_propose",
                f"Proposed patch: {proposal.title}",
                proposal.model_dump(),
                patch_proposals=[proposal],
            )
        if tool_name == "patch_apply":
            return self.apply_patch_payload(args)
        if tool_name == "patch_rollback":
            return self.rollback_patch(args)
        if tool_name == "workspace_diff":
            return self.workspace_diff(args)
        if tool_name == "workspace_promote":
            return self.workspace_promote(args)
        return ToolResult(False, tool_name, f"Unknown tool: {tool_name}", args)

    async def run_command(self, command: str, *, timeout: int = 60, approved: bool = False) -> ToolResult:
        decision = self.safety.classify_command(command)
        if decision.needs_approval and not approved:
            return ToolResult(False, "shell", decision.reason, {"command": command, "timeout": timeout}, needs_approval=True)
        if not decision.allowed and not approved:
            return ToolResult(False, "shell", decision.reason, {"command": command})

        env = os.environ.copy()
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(False, "shell", f"Command timed out after {timeout}s.", {"command": command})

        stdout = redact_secrets(stdout_raw.decode("utf-8", errors="replace")[-6000:])
        stderr = redact_secrets(stderr_raw.decode("utf-8", errors="replace")[-6000:])
        ok = proc.returncode == 0
        return ToolResult(
            ok=ok,
            kind="shell",
            summary=f"exit {proc.returncode}: {command}",
            data={"command": command, "returncode": proc.returncode, "stdout": stdout, "stderr": stderr},
        )

    def list_files(self, limit: int = 200) -> ToolResult:
        paths: list[str] = []
        for path in sorted(self.workspace.rglob("*")):
            if any(part in {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            if path.is_file():
                paths.append(str(path.relative_to(self.workspace)))
            if len(paths) >= limit:
                break
        return ToolResult(True, "file_read", f"Found {len(paths)} files.", {"files": paths})

    def read_file(self, relative_path: str, limit: int = 20000) -> ToolResult:
        if relative_path in {"", ".", "*"}:
            return self.list_files(limit=min(limit, 500))
        target = (self.workspace / relative_path).resolve()
        decision = self.safety.classify_path(self.workspace, target)
        if decision.needs_approval:
            return ToolResult(False, "file_read", decision.reason, {"path": str(target)}, True)
        try:
            text = target.read_text(encoding="utf-8", errors="replace")[:limit]
        except OSError as exc:
            return ToolResult(False, "file_read", str(exc), {"path": str(target)})
        return ToolResult(True, "file_read", f"Read {relative_path}.", {"path": relative_path, "content": redact_secrets(text)})

    def write_file(self, relative_path: str, content: str, *, approved: bool = False) -> ToolResult:
        target = (self.workspace / relative_path).resolve()
        decision = self.safety.classify_path(self.workspace, target)
        if decision.needs_approval and not approved:
            return ToolResult(False, "file_write", decision.reason, {"path": str(target)}, True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(True, "file_write", f"Wrote {relative_path}.", {"path": relative_path})

    def apply_patch_payload(self, args: dict[str, Any]) -> ToolResult:
        patch_id = str(args.get("patch_id") or args.get("id") or f"patch-{uuid4().hex[:8]}")
        try:
            changes = self._changes_from_payload(args)
            if not changes:
                return ToolResult(False, "patch_apply", "Patch payload did not include any changes.", args)
            backup_id = f"backup-{uuid4().hex[:8]}"
            backup_dir = self._backup_scope_dir() / backup_id
            manifest_files: list[dict[str, Any]] = []
            applied_files: list[str] = []

            for change in changes:
                relative_path = str(change["path"])
                target = self._resolve_workspace_path(relative_path)
                before = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
                after = str(change["new"])
                self._backup_file(target, relative_path, backup_dir, manifest_files)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(after, encoding="utf-8")
                applied_files.append(relative_path)
                manifest_files[-1]["before_chars"] = len(before)
                manifest_files[-1]["after_chars"] = len(after)

            manifest = {
                "backup_id": backup_id,
                "patch_id": patch_id,
                "workspace": str(self.workspace),
                "created_at": utc_now(),
                "files": manifest_files,
            }
            manifest_path = backup_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
        except ValueError as exc:
            return ToolResult(False, "patch_apply", str(exc), args)
        except OSError as exc:
            return ToolResult(False, "patch_apply", f"Patch apply failed: {exc}", args)

        application = PatchApplication(
            id=f"apply-{uuid4().hex[:8]}",
            patch_id=patch_id,
            status="applied",
            files=applied_files,
            backup_id=backup_id,
            manifest_path=str(manifest_path),
            summary=f"Applied patch {patch_id} to {len(applied_files)} file(s).",
            applied_at=utc_now(),
        )
        proposal = PatchProposal(
            id=patch_id,
            title=str(args.get("title") or "Applied patch"),
            summary=application.summary,
            files=applied_files,
            diff=str(args.get("diff") or ""),
            status="applied",
            backup_id=backup_id,
            applied_at=application.applied_at,
            rollback_manifest_path=str(manifest_path),
            created_at=str(args.get("created_at") or application.applied_at),
        )
        return ToolResult(
            True,
            "patch_apply",
            application.summary,
            {"patch_id": patch_id, "backup_id": backup_id, "manifest_path": str(manifest_path), "files": applied_files},
            patch_proposals=[proposal],
            patch_applications=[application],
        )

    def rollback_patch(self, args: dict[str, Any]) -> ToolResult:
        backup_id = str(args.get("backup_id") or "").strip()
        manifest_path = self._manifest_path_from_args(args, backup_id)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
            restored: list[str] = []
            for item in files:
                if not isinstance(item, dict):
                    continue
                relative_path = str(item.get("path") or "")
                target = self._resolve_workspace_path(relative_path)
                existed = bool(item.get("existed"))
                if existed:
                    backup_path = Path(str(item.get("backup_path") or ""))
                    if not backup_path.exists():
                        raise ValueError(f"Backup file missing for {relative_path}.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_path, target)
                elif target.exists():
                    target.unlink()
                restored.append(relative_path)
            manifest["rolled_back_at"] = utc_now()
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return ToolResult(False, "patch_rollback", f"Patch rollback failed: {exc}", args)

        application = PatchApplication(
            id=f"rollback-{uuid4().hex[:8]}",
            patch_id=str(manifest.get("patch_id") or ""),
            status="rolled_back",
            files=restored,
            backup_id=str(manifest.get("backup_id") or backup_id),
            manifest_path=str(manifest_path),
            summary=f"Rolled back patch backup {manifest.get('backup_id') or backup_id} for {len(restored)} file(s).",
            rolled_back_at=str(manifest.get("rolled_back_at") or utc_now()),
        )
        proposal = PatchProposal(
            id=application.patch_id or f"patch-{uuid4().hex[:8]}",
            title="Rolled back patch",
            summary=application.summary,
            files=restored,
            status="rolled_back",
            backup_id=application.backup_id,
            rollback_manifest_path=str(manifest_path),
            created_at=application.rolled_back_at,
        )
        return ToolResult(
            True,
            "patch_rollback",
            application.summary,
            {"patch_id": application.patch_id, "backup_id": application.backup_id, "manifest_path": str(manifest_path), "files": restored},
            patch_proposals=[proposal],
            patch_applications=[application],
        )

    def workspace_diff(self, args: dict[str, Any]) -> ToolResult:
        source_path = Path(str(args.get("source_path") or self.workspace)).resolve()
        try:
            files = [str(item) for item in args.get("files", [])] if isinstance(args.get("files"), list) else []
            diff = build_workspace_diff(source_path, self.workspace, files=files or None)
        except (OSError, ValueError) as exc:
            return ToolResult(False, "workspace_diff", f"Workspace diff failed: {exc}", args)
        return ToolResult(
            True,
            "workspace_diff",
            diff.summary,
            {"source_path": str(source_path), "workspace_path": str(self.workspace), "total_files": diff.total_files},
            workspace_diff=diff,
        )

    def workspace_promote(self, args: dict[str, Any]) -> ToolResult:
        source_path = str(args.get("source_path") or "").strip()
        if not source_path:
            return ToolResult(False, "workspace_promote", "Workspace promotion requires source_path.", args)
        try:
            files = [str(item) for item in args.get("files", [])] if isinstance(args.get("files"), list) else []
            promotion = promote_workspace_changes(
                Path(source_path),
                self.workspace,
                self.promotion_backup_dir,
                files=files or None,
                include_deletions=bool(args.get("include_deletions")),
            )
            diff = build_workspace_diff(Path(source_path), self.workspace)
        except (OSError, ValueError) as exc:
            return ToolResult(False, "workspace_promote", f"Workspace promotion failed: {exc}", args)
        return ToolResult(
            True,
            "workspace_promote",
            promotion.summary,
            {
                "source_path": source_path,
                "workspace_path": str(self.workspace),
                "files": promotion.files,
                "backup_id": promotion.backup_id,
                "manifest_path": promotion.manifest_path,
            },
            workspace_diff=diff,
            workspace_promotions=[promotion],
        )

    def _changes_from_payload(self, args: dict[str, Any]) -> list[dict[str, str]]:
        raw_files = args.get("files")
        if isinstance(raw_files, list) and raw_files and all(isinstance(item, dict) for item in raw_files):
            return self._structured_changes(raw_files)
        diff = str(args.get("diff") or "")
        if diff.strip():
            return self._unified_diff_changes(diff)
        return []

    def _structured_changes(self, files: list[Any]) -> list[dict[str, str]]:
        changes: list[dict[str, str]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            relative_path = str(item.get("path") or item.get("file") or "").strip()
            if not relative_path:
                raise ValueError("Structured patch file entry is missing a path.")
            target = self._resolve_workspace_path(relative_path)
            current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
            old = item.get("old")
            if old is not None and str(old) not in current:
                raise ValueError(f"Expected text was not found in {relative_path}.")
            if "new" in item:
                replacement = str(item["new"])
            elif "content" in item:
                replacement = str(item["content"])
            else:
                raise ValueError(f"Structured patch file entry for {relative_path} is missing new content.")
            if old is None:
                new_content = replacement
            else:
                new_content = current.replace(str(old), replacement, 1)
            changes.append({"path": relative_path, "new": new_content})
        return changes

    def _unified_diff_changes(self, diff: str) -> list[dict[str, str]]:
        file_patches = self._parse_unified_diff(diff)
        changes: list[dict[str, str]] = []
        for relative_path, hunks in file_patches:
            target = self._resolve_workspace_path(relative_path)
            current_lines = target.read_text(encoding="utf-8", errors="replace").splitlines() if target.exists() else []
            next_lines = current_lines[:]
            search_from = 0
            for hunk in hunks:
                old_lines = [line[1:] for line in hunk if line[:1] in {" ", "-"}]
                new_lines = [line[1:] for line in hunk if line[:1] in {" ", "+"}]
                index = self._find_sequence(next_lines, old_lines, search_from)
                if index < 0:
                    raise ValueError(f"Unified diff context did not match {relative_path}.")
                next_lines[index : index + len(old_lines)] = new_lines
                search_from = index + len(new_lines)
            changes.append({"path": relative_path, "new": "\n".join(next_lines) + ("\n" if next_lines else "")})
        return changes

    def _parse_unified_diff(self, diff: str) -> list[tuple[str, list[list[str]]]]:
        patches: list[tuple[str, list[list[str]]]] = []
        current_path = ""
        current_hunks: list[list[str]] = []
        current_hunk: list[str] | None = None
        for line in diff.splitlines():
            if line.startswith("+++ "):
                if current_path:
                    if current_hunk is not None:
                        current_hunks.append(current_hunk)
                    patches.append((current_path, current_hunks))
                current_path = self._clean_patch_path(line[4:].strip())
                current_hunks = []
                current_hunk = None
                continue
            if line.startswith("@@"):
                if current_hunk is not None:
                    current_hunks.append(current_hunk)
                current_hunk = []
                continue
            if current_hunk is not None and line[:1] in {" ", "-", "+"}:
                current_hunk.append(line)
        if current_path:
            if current_hunk is not None:
                current_hunks.append(current_hunk)
            patches.append((current_path, current_hunks))
        return [(path, hunks) for path, hunks in patches if path and path != "/dev/null" and hunks]

    def _clean_patch_path(self, raw_path: str) -> str:
        path = raw_path.split("\t", 1)[0].split(" ", 1)[0]
        if path.startswith("a/") or path.startswith("b/"):
            path = path[2:]
        return path

    def _find_sequence(self, haystack: list[str], needle: list[str], start: int = 0) -> int:
        if not needle:
            return len(haystack)
        for index in range(max(0, start), len(haystack) - len(needle) + 1):
            if haystack[index : index + len(needle)] == needle:
                return index
        for index in range(0, len(haystack) - len(needle) + 1):
            if haystack[index : index + len(needle)] == needle:
                return index
        return -1

    def _backup_file(self, target: Path, relative_path: str, backup_dir: Path, manifest_files: list[dict[str, Any]]) -> None:
        backup_path = backup_dir / relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        if existed:
            shutil.copy2(target, backup_path)
        manifest_files.append(
            {
                "path": relative_path,
                "existed": existed,
                "backup_path": str(backup_path),
            }
        )

    def _resolve_workspace_path(self, relative_path: str) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute():
            raise ValueError("Patch paths must be relative to the run workspace.")
        target = (self.workspace / raw).resolve()
        decision = self.safety.classify_path(self.workspace, target)
        if decision.needs_approval:
            raise ValueError(decision.reason)
        return target

    def _backup_scope_dir(self) -> Path:
        if self.workspace.name == "workspace" and self.workspace.parent.name.startswith("run-"):
            scope = self.workspace.parent.name
        else:
            scope = f"workspace-{abs(hash(str(self.workspace))) % 10_000_000:07d}"
        path = self.patch_backup_dir / scope
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _manifest_path_from_args(self, args: dict[str, Any], backup_id: str) -> Path:
        raw_manifest = str(args.get("manifest_path") or "").strip()
        if raw_manifest:
            candidate = Path(raw_manifest).resolve()
            try:
                candidate.relative_to(self.patch_backup_dir)
            except ValueError as exc:
                raise ValueError("Rollback manifest must live under the patch backup directory.") from exc
            return candidate
        if not backup_id:
            raise ValueError("Rollback requires backup_id or manifest_path.")
        candidate = self._backup_scope_dir() / backup_id / "manifest.json"
        if not candidate.exists():
            matches = list(self.patch_backup_dir.glob(f"*/{backup_id}/manifest.json"))
            if matches:
                candidate = matches[0]
        if not candidate.exists():
            raise ValueError(f"Rollback manifest not found for {backup_id}.")
        return candidate.resolve()

    async def web_search(self, query: str, limit: int = 5) -> ToolResult:
        if not query.strip():
            return ToolResult(False, "web_search", "Search query is empty.", {"query": query})
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            async with httpx.AsyncClient(timeout=self.config.web_timeout_seconds, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "AgentOrinth/0.1"})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return ToolResult(False, "web_search", f"Search failed: {exc}", {"query": query})

        sources = self._parse_duckduckgo(response.text, limit=limit)
        return ToolResult(
            ok=bool(sources),
            kind="web_search",
            summary=f"Found {len(sources)} web result(s) for {query!r}.",
            data={"query": query, "provider": self.config.search_provider},
            web_sources=sources,
        )

    async def web_fetch(self, url: str) -> ToolResult:
        if not urlparse(url).scheme:
            return ToolResult(False, "web_fetch", "URL must include http:// or https://.", {"url": url})
        try:
            async with httpx.AsyncClient(timeout=self.config.web_timeout_seconds, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "AgentOrinth/0.1"})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return ToolResult(False, "web_fetch", f"Fetch failed: {exc}", {"url": url})

        title = self._extract_title(response.text) or url
        excerpt = self._html_to_excerpt(response.text)
        source = WebSource(
            id=f"web-{uuid4().hex[:8]}",
            title=title,
            url=str(response.url),
            timestamp=utc_now(),
            excerpt=excerpt,
            citation=f"[{title}]({response.url})",
        )
        return ToolResult(
            True,
            "web_fetch",
            f"Fetched {title}.",
            {"url": str(response.url), "excerpt": excerpt},
            web_sources=[source],
        )

    async def browser_open(self, url: str) -> ToolResult:
        if not urlparse(url).scheme:
            return ToolResult(False, "browser_open", "URL must include http:// or https://.", {"url": url})
        return ToolResult(True, "browser_open", f"Browser target opened: {url}", {"url": url})

    async def browser_screenshot(self, url: str) -> ToolResult:
        if not self.config.browser_executable_path:
            return ToolResult(False, "browser_screenshot", "No Chrome/Edge executable configured.", {"url": url})
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ToolResult(False, "browser_screenshot", "Playwright is not installed.", {"url": url})

        shot_path = self.artifact_dir / f"browser-{uuid4().hex[:8]}.png"
        visible_text = ""
        console_errors: list[str] = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, executable_path=self.config.browser_executable_path)
                page = await browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("console", lambda msg: console_errors.append(msg.text[:500]) if msg.type == "error" else None)
                await page.goto(url, wait_until="domcontentloaded", timeout=self.config.web_timeout_seconds * 1000)
                await page.wait_for_timeout(300)
                try:
                    visible_text = (await page.locator("body").inner_text(timeout=1000))[:4000]
                except Exception:
                    visible_text = ""
                await page.screenshot(path=str(shot_path), full_page=True)
                await browser.close()
        except Exception as exc:
            return ToolResult(False, "browser_screenshot", f"Browser screenshot failed: {exc}", {"url": url})

        snapshot = DesktopSnapshot(
            id=f"browser-{uuid4().hex[:8]}",
            timestamp=utc_now(),
            title=f"Browser screenshot: {url}",
            path=str(shot_path),
            summary=f"Captured browser screenshot for {url}.",
        )
        return ToolResult(
            True,
            "browser_screenshot",
            snapshot.summary,
            {"url": url, "path": str(shot_path), "visible_text": visible_text, "console_errors": console_errors[-8:]},
            desktop_snapshots=[snapshot],
        )

    async def desktop_window_list(self) -> ToolResult:
        command = (
            "Get-Process | Where-Object { $_.MainWindowTitle } | "
            "Select-Object -First 25 ProcessName,Id,MainWindowTitle | ConvertTo-Json"
        )
        result = await self.run_command(f"powershell -NoProfile -Command \"{command}\"", timeout=20, approved=True)
        return ToolResult(result.ok, "desktop_window_list", "Listed visible desktop windows.", result.data)

    async def desktop_screenshot(self) -> ToolResult:
        shot_path = self.artifact_dir / f"desktop-{uuid4().hex[:8]}.png"
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; "
            "$g=[System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
            f"$bmp.Save('{shot_path}'); "
            "$g.Dispose(); $bmp.Dispose();"
        )
        result = await self.run_command(f"powershell -NoProfile -Command \"{ps}\"", timeout=20, approved=True)
        if not result.ok:
            return ToolResult(False, "desktop_screenshot", "Desktop screenshot failed.", result.data)
        snapshot = DesktopSnapshot(
            id=f"desktop-{uuid4().hex[:8]}",
            timestamp=utc_now(),
            title="Desktop screenshot",
            path=str(shot_path),
            summary="Captured supervised desktop screenshot.",
        )
        return ToolResult(True, "desktop_screenshot", snapshot.summary, {"path": str(shot_path)}, desktop_snapshots=[snapshot])

    def _parse_duckduckgo(self, body: str, limit: int) -> list[WebSource]:
        sources: list[WebSource] = []
        pattern = re.compile(
            r'<a rel="nofollow" class="result__a" href="(?P<url>.*?)".*?>(?P<title>.*?)</a>.*?<a class="result__snippet".*?>(?P<snippet>.*?)</a>',
            re.DOTALL,
        )
        for match in pattern.finditer(body):
            title = compact_text(re.sub(r"<.*?>", "", match.group("title")), 160)
            excerpt = compact_text(re.sub(r"<.*?>", "", match.group("snippet")), 700)
            url = html.unescape(match.group("url"))
            source = WebSource(
                id=f"web-{uuid4().hex[:8]}",
                title=title or url,
                url=url,
                timestamp=utc_now(),
                excerpt=excerpt,
                citation=f"[{title or url}]({url})",
            )
            sources.append(source)
            if len(sources) >= limit:
                break
        return sources

    def _extract_title(self, body: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        return compact_text(match.group(1), 180) if match else ""

    def _html_to_excerpt(self, body: str) -> str:
        body = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", body)
        body = re.sub(r"(?s)<.*?>", " ", body)
        return compact_text(body, 2500)

