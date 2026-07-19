from __future__ import annotations

import difflib
import hashlib
import json
import shutil
from pathlib import Path

from .persistence import utc_now
from .schemas import WorkspaceDiffFile, WorkspaceDiffSummary, WorkspaceIsolation, WorkspacePromotion


SKIP_DIRS = {
    ".agentornith",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "coverage",
    "data",
    "dist",
    "node_modules",
}


class WorkspaceManager:
    def __init__(
        self,
        *,
        enabled: bool,
        mode: str,
        root: Path,
        copy_limit_files: int,
    ) -> None:
        self.enabled = enabled
        self.mode = mode
        self.root = root.resolve()
        self.copy_limit_files = max(1, copy_limit_files)

    def prepare_run_workspace(self, run_id: str, source_path: Path) -> WorkspaceIsolation:
        source = source_path.resolve()
        if not self.enabled:
            return WorkspaceIsolation(
                enabled=False,
                mode="source",
                source_path=str(source),
                workspace_path=str(source),
                created_at=utc_now(),
                summary="Workspace isolation disabled; using the configured source workspace directly.",
            )

        if self.mode == "source":
            return WorkspaceIsolation(
                enabled=False,
                mode="source",
                source_path=str(source),
                workspace_path=str(source),
                created_at=utc_now(),
                summary="Workspace isolation source mode; using the configured source workspace directly.",
            )

        if self.mode not in {"copy", "git_worktree"}:
            mode = "copy"
            mode_note = f"Unsupported isolation mode {self.mode!r}; used copy mode."
        elif self.mode == "git_worktree":
            mode = "copy"
            mode_note = "git_worktree mode is reserved for a later explicit implementation; used copy mode."
        else:
            mode = "copy"
            mode_note = "Created isolated copy workspace."

        target = (self.root / run_id / "workspace").resolve()
        copied, skipped = self._copy_workspace(source, target)
        return WorkspaceIsolation(
            enabled=True,
            mode=mode,
            source_path=str(source),
            workspace_path=str(target),
            created_at=utc_now(),
            copied_files=copied,
            skipped_paths=skipped[:30],
            summary=f"{mode_note} Copied {copied} file(s) to {target}.",
        )

    def _copy_workspace(self, source: Path, target: Path) -> tuple[int, list[str]]:
        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        skipped: list[str] = []

        for path in sorted(source.rglob("*")):
            try:
                relative = path.relative_to(source)
            except ValueError:
                continue
            relative_parts = set(relative.parts)
            if relative_parts & SKIP_DIRS:
                if len(skipped) < 60:
                    skipped.append(str(relative))
                continue
            if self._is_inside(path, self.root):
                if len(skipped) < 60:
                    skipped.append(str(relative))
                continue
            if path.is_dir():
                continue
            if copied >= self.copy_limit_files:
                if len(skipped) < 60:
                    skipped.append(f"{relative} (copy limit reached)")
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied += 1

        return copied, skipped

    def _is_inside(self, path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent)
            return True
        except ValueError:
            return False


def build_workspace_diff(
    source_path: Path,
    workspace_path: Path,
    *,
    files: list[str] | None = None,
    max_files: int = 120,
    max_diff_chars: int = 12000,
) -> WorkspaceDiffSummary:
    source = source_path.resolve()
    workspace = workspace_path.resolve()
    selected = {normalize_relative_path(item) for item in files or [] if item.strip()}
    source_files = collect_workspace_files(source)
    workspace_files = collect_workspace_files(workspace)
    changed: list[WorkspaceDiffFile] = []

    for relative_path in sorted(source_files | workspace_files):
        if selected and relative_path not in selected:
            continue
        source_file = source / relative_path
        workspace_file = workspace / relative_path
        source_exists = source_file.exists()
        workspace_exists = workspace_file.exists()
        if source_exists and workspace_exists and file_sha256(source_file) == file_sha256(workspace_file):
            continue
        if source_exists and workspace_exists:
            status = "modified"
        elif workspace_exists:
            status = "added"
        else:
            status = "deleted"
        changed.append(diff_file(source, workspace, relative_path, status, max_diff_chars=max_diff_chars))

    truncated = len(changed) > max_files
    files_out = changed[:max_files]
    added = sum(1 for item in changed if item.status == "added")
    modified = sum(1 for item in changed if item.status == "modified")
    deleted = sum(1 for item in changed if item.status == "deleted")
    total = len(changed)
    return WorkspaceDiffSummary(
        generated_at=utc_now(),
        source_path=str(source),
        workspace_path=str(workspace),
        files=files_out,
        total_files=total,
        added=added,
        modified=modified,
        deleted=deleted,
        truncated=truncated,
        summary=f"{total} workspace change(s): {added} added, {modified} modified, {deleted} deleted.",
    )


def promote_workspace_changes(
    source_path: Path,
    workspace_path: Path,
    backup_root: Path,
    *,
    files: list[str] | None = None,
    include_deletions: bool = False,
) -> WorkspacePromotion:
    source = source_path.resolve()
    workspace = workspace_path.resolve()
    diff = build_workspace_diff(source, workspace, files=files, max_files=10_000, max_diff_chars=0)
    selected_changes = [
        item
        for item in diff.files
        if item.status in {"added", "modified"} or (include_deletions and item.status == "deleted")
    ]
    if not selected_changes:
        raise ValueError("No workspace changes selected for promotion.")

    promotion_id = f"promotion-{hashlib.sha256((str(source) + str(workspace) + utc_now()).encode()).hexdigest()[:8]}"
    backup_id = f"promotion-backup-{promotion_id.removeprefix('promotion-')}"
    backup_dir = (backup_root.resolve() / backup_id).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest_files: list[dict[str, object]] = []
    promoted_files: list[str] = []

    for item in selected_changes:
        relative_path = normalize_relative_path(item.path)
        source_file = resolve_under(source, relative_path)
        workspace_file = resolve_under(workspace, relative_path)
        backup_file = backup_dir / relative_path
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        existed = source_file.exists()
        if existed:
            shutil.copy2(source_file, backup_file)
        if item.status == "deleted":
            if source_file.exists():
                source_file.unlink()
        else:
            if not workspace_file.exists():
                raise ValueError(f"Workspace file missing for promotion: {relative_path}")
            source_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace_file, source_file)
        promoted_files.append(relative_path)
        manifest_files.append(
            {
                "path": relative_path,
                "status": item.status,
                "existed": existed,
                "backup_path": str(backup_file),
            }
        )

    manifest = {
        "promotion_id": promotion_id,
        "backup_id": backup_id,
        "source_path": str(source),
        "workspace_path": str(workspace),
        "created_at": utc_now(),
        "files": manifest_files,
    }
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    return WorkspacePromotion(
        id=promotion_id,
        status="promoted",
        files=promoted_files,
        backup_id=backup_id,
        manifest_path=str(manifest_path),
        summary=f"Promoted {len(promoted_files)} isolated workspace change(s) to source.",
        promoted_at=utc_now(),
    )


def collect_workspace_files(root: Path) -> set[str]:
    paths: set[str] = set()
    if not root.exists():
        return paths
    for path in root.rglob("*"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if path.is_dir() or set(relative.parts) & SKIP_DIRS:
            continue
        paths.add(str(relative).replace("\\", "/"))
    return paths


def diff_file(source: Path, workspace: Path, relative_path: str, status: str, *, max_diff_chars: int) -> WorkspaceDiffFile:
    source_file = source / relative_path
    workspace_file = workspace / relative_path
    source_bytes = source_file.read_bytes() if source_file.exists() else b""
    workspace_bytes = workspace_file.read_bytes() if workspace_file.exists() else b""
    binary = is_binary(source_bytes) or is_binary(workspace_bytes)
    text_diff = ""
    truncated = False
    if not binary and max_diff_chars > 0:
        source_text = source_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
        workspace_text = workspace_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
        text_diff = "".join(
            difflib.unified_diff(
                source_text,
                workspace_text,
                fromfile=f"source/{relative_path}",
                tofile=f"workspace/{relative_path}",
                lineterm="",
            )
        )
        if len(text_diff) > max_diff_chars:
            text_diff = text_diff[:max_diff_chars]
            truncated = True
    return WorkspaceDiffFile(
        path=relative_path,
        status=status,  # type: ignore[arg-type]
        source_size=len(source_bytes),
        workspace_size=len(workspace_bytes),
        source_sha256=sha256_bytes(source_bytes) if source_bytes else "",
        workspace_sha256=sha256_bytes(workspace_bytes) if workspace_bytes else "",
        diff=text_diff,
        binary=binary,
        truncated=truncated,
    )


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_binary(value: bytes) -> bool:
    return b"\0" in value[:4096]


def normalize_relative_path(path: str) -> str:
    raw = Path(path)
    if raw.is_absolute():
        raise ValueError("Workspace promotion paths must be relative.")
    normalized = str(raw).replace("\\", "/").strip("/")
    if (
        not normalized
        or normalized in {".", ".."}
        or normalized.startswith("../")
        or normalized.endswith("/..")
        or "/../" in normalized
    ):
        raise ValueError("Workspace promotion path escapes the workspace.")
    return normalized


def resolve_under(root: Path, relative_path: str) -> Path:
    target = (root / normalize_relative_path(relative_path)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Resolved path escapes the workspace boundary.") from exc
    return target
