from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .schemas import RepoMap


IGNORE_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "data"}
MANIFEST_NAMES = {
    "README.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "vite.config.ts",
    "tsconfig.json",
}
LANG_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript-react",
    ".js": "javascript",
    ".jsx": "javascript-react",
    ".json": "json",
    ".md": "markdown",
    ".css": "css",
    ".html": "html",
}


def build_repo_map(workspace: Path, limit: int = 500) -> RepoMap:
    workspace = workspace.resolve()
    files = _iter_files(workspace, limit=limit)
    relative_files = [str(path.relative_to(workspace)) for path in files]
    manifests = [path for path in relative_files if Path(path).name in MANIFEST_NAMES]
    languages = Counter(LANG_BY_SUFFIX.get(Path(path).suffix.lower(), Path(path).suffix.lower() or "other") for path in relative_files)
    package_scripts, package_dir = _discover_package_scripts(workspace)
    test_commands = _test_commands(package_scripts, manifests, package_dir)
    key_files = _key_files(relative_files)

    summary = (
        f"{len(relative_files)} mapped files; manifests: {', '.join(manifests[:8]) or 'none'}; "
        f"main languages: {', '.join(f'{name}:{count}' for name, count in languages.most_common(5))}."
    )
    return RepoMap(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        root=str(workspace),
        manifests=manifests,
        package_scripts=package_scripts,
        test_commands=test_commands,
        key_files=key_files,
        languages=dict(languages.most_common()),
        summary=summary,
    )


def _iter_files(workspace: Path, limit: int) -> list[Path]:
    files: list[Path] = []
    for path in sorted(workspace.rglob("*")):
        try:
            relative_parts = path.relative_to(workspace).parts
        except ValueError:
            relative_parts = path.parts
        if any(part in IGNORE_PARTS for part in relative_parts):
            continue
        if path.is_file():
            files.append(path)
        if len(files) >= limit:
            break
    return files


def _package_scripts(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items()}


def _discover_package_scripts(workspace: Path) -> tuple[dict[str, str], str]:
    for relative in ("frontend", "."):
        scripts = _package_scripts(workspace / relative / "package.json")
        if scripts:
            return scripts, "" if relative == "." else relative
    return {}, ""


def _npm_command(package_dir: str, script: str) -> str:
    if package_dir:
        return f"npm --prefix {package_dir} run {script}"
    return f"npm run {script}"


def _test_commands(package_scripts: dict[str, str], manifests: list[str], package_dir: str = "") -> list[str]:
    commands: list[str] = []
    for name in ("test", "build", "lint", "typecheck"):
        if name in package_scripts:
            commands.append(_npm_command(package_dir, name))
    if "pyproject.toml" in manifests or "requirements.txt" in manifests:
        commands.append("python -m pytest")
    if not commands and package_scripts:
        commands.append(_npm_command(package_dir, "build"))
    return commands[:8]


def _key_files(relative_files: list[str]) -> list[str]:
    preferred_names = {
        "README.md",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "api.py",
        "engine.py",
        "tools.py",
        "schemas.py",
        "App.tsx",
    }
    preferred = [path for path in relative_files if Path(path).name in preferred_names]
    return preferred[:40]
