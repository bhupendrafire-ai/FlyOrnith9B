from pathlib import Path

from app.tools import SafetyGate


def test_allows_read_only_command() -> None:
    decision = SafetyGate().classify_command("git status --short")

    assert decision.allowed
    assert not decision.needs_approval


def test_global_install_needs_approval() -> None:
    decision = SafetyGate().classify_command("winget install Git.Git")

    assert not decision.allowed
    assert decision.needs_approval


def test_destructive_command_needs_approval() -> None:
    decision = SafetyGate().classify_command("git reset --hard HEAD")

    assert not decision.allowed
    assert decision.needs_approval


def test_powershell_recursive_remove_needs_approval() -> None:
    decision = SafetyGate().classify_command(r"Remove-Item -Recurse C:\Windows")

    assert not decision.allowed
    assert decision.needs_approval


def test_python_comparison_operator_is_not_shell_redirection() -> None:
    decision = SafetyGate().classify_command('python -c "assert 2 > 1; print(2)"')

    assert decision.allowed
    assert not decision.needs_approval


def test_stderr_merge_is_not_overwrite_redirection() -> None:
    decision = SafetyGate().classify_command('python -c "print(1)" 2>&1')

    assert decision.allowed
    assert not decision.needs_approval


def test_path_outside_workspace_needs_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.txt"
    workspace.mkdir()

    decision = SafetyGate().classify_path(workspace, outside)

    assert decision.needs_approval
