from __future__ import annotations

import re
from pathlib import Path

from .schemas import RunRecord, RunState


PPTX_STRONG_WORDS = {"ppt", "pptx", "powerpoint", "deck", "presentation"}
HTML_WORDS = {"html", "webpage", "website", "landing page", "single page", "web app", "browser app"}
ARTIFACT_PROOF_WORDS = {
    "artifact",
    "artifacts",
    "check",
    "checks",
    "document",
    "exist",
    "exists",
    "file",
    "files",
    "html",
    "index",
    "load",
    "loads",
    "page",
    "source",
    "sources",
    "verification",
    "verify",
}


def artifact_verification_command(run: RunRecord, state: RunState, criterion: str = "") -> str:
    """Return a narrow artifact existence check when acceptance is about a deliverable file."""
    suffix = _artifact_verification_suffix(run, state, criterion)
    if suffix == ".pptx":
        return _pptx_command(criterion)
    if suffix == ".html":
        return _html_command()
    return ""


def expected_artifact_suffix(run: RunRecord, state: RunState, criterion: str = "") -> str:
    text = " ".join([run.goal, state.goal, criterion, " ".join(state.acceptance_criteria)]).lower()
    return _suffix_from_text(text)


def _artifact_verification_suffix(run: RunRecord, state: RunState, criterion: str = "") -> str:
    suffix = expected_artifact_suffix(run, state, criterion)
    if criterion.strip() and not _criterion_needs_artifact_proof(criterion.lower(), suffix):
        return ""
    return suffix


def _suffix_from_text(text: str) -> str:
    if _has_pptx_intent(text):
        return ".pptx"
    if any(word in text for word in HTML_WORDS):
        return ".html"
    return ""


def _criterion_needs_artifact_proof(text: str, suffix: str = "") -> bool:
    words = set(re.findall(r"[a-z0-9_-]{3,}", text))
    if words.intersection(ARTIFACT_PROOF_WORDS):
        return True
    if suffix == ".pptx":
        return bool(words.intersection({"compare", "compares", "slide", "slides", "tradeoff", "tradeoffs", "use-case"}))
    return False


def _has_pptx_intent(text: str) -> bool:
    words = set(re.findall(r"[a-z0-9_-]{2,}", text))
    return bool(words.intersection(PPTX_STRONG_WORDS))


def expected_artifact_exists(run: RunRecord, state: RunState, criterion: str = "") -> bool:
    suffix = expected_artifact_suffix(run, state, criterion)
    if not suffix or not run.workspace_path:
        return False
    workspace = Path(run.workspace_path)
    if not workspace.exists():
        return False
    return any(
        not {".agentornith", "node_modules"}.intersection(path.parts) and path.is_file() and path.stat().st_size > 0
        for path in workspace.rglob(f"*{suffix}")
    )


def artifact_creation_action(run: RunRecord, state: RunState) -> dict | None:
    """Do not generate deliverables for the model; the harness only verifies artifacts."""
    return None


def _pptx_command(criterion: str = "") -> str:
    lowered = criterion.lower()
    exact_six = "exactly six" in lowered or "six slides" in lowered
    needs_use_cases = "use-case" in lowered or "use case" in lowered
    needs_comparison = "compare" in lowered or "command-line" in lowered or "command line" in lowered
    needs_tradeoffs = "tradeoff" in lowered or "tradeoffs" in lowered or "limitation" in lowered
    slide_check = (
        "assert len(slides) == 6, 'expected exactly 6 slides, got %s' % len(slides); "
        if exact_six
        else "assert len(slides) >= 6, 'expected at least 6 slides, got %s' % len(slides); "
    )
    text_checks = ""
    if needs_use_cases:
        text_checks += "assert all(('use case %s' % i) in text for i in range(1, 6)), 'missing numbered use case text'; "
    if needs_comparison:
        text_checks += "assert 'agentornith harness' in text and 'command-line ornith' in text, 'missing harness vs command-line comparison'; "
    if needs_tradeoffs:
        text_checks += "assert 'tradeoff' in text or 'limitation' in text, 'missing tradeoff or limitation text'; "
    return (
        "python -c \"from pathlib import Path; import zipfile; "
        "files=sorted(p for p in Path('.').rglob('*.pptx') if '.agentornith' not in p.parts and 'node_modules' not in p.parts); "
        "assert files, 'no pptx files found'; "
        "p=files[0]; assert p.stat().st_size > 1000, 'pptx file is too small'; "
        "z=zipfile.ZipFile(p); "
        "slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]; "
        + slide_check
        + "text=' '.join(z.read(n).decode('utf-8', errors='ignore').lower() for n in slides); "
        + text_checks
        + "print(str(p), len(slides), p.stat().st_size)\""
    )


def _html_command() -> str:
    return (
        "python -c \"from pathlib import Path; "
        "files=sorted(p for p in Path('.').rglob('*.html') if '.agentornith' not in p.parts and 'node_modules' not in p.parts); "
        "assert files, 'no html files found'; "
        "p=files[0]; text=p.read_text(encoding='utf-8', errors='replace').lower(); "
        "assert '<html' in text and '</html>' in text, 'html document is incomplete'; "
        "assert p.stat().st_size > 500, 'html file is too small'; "
        "print(str(p), p.stat().st_size)\""
    )
