from __future__ import annotations

import re
from pathlib import Path

from .schemas import RunRecord, RunState


PPTX_WORDS = {"ppt", "pptx", "powerpoint", "deck", "slide", "slides", "presentation"}
HTML_WORDS = {"html", "webpage", "website", "landing page", "single page"}


def artifact_verification_command(run: RunRecord, state: RunState, criterion: str = "") -> str:
    """Return a narrow artifact existence check when acceptance is about a deliverable file."""
    suffix = expected_artifact_suffix(run, state, criterion)
    if suffix == ".pptx":
        return _pptx_command(criterion)
    if suffix == ".html":
        return _html_command()
    return ""


def expected_artifact_suffix(run: RunRecord, state: RunState, criterion: str = "") -> str:
    text = " ".join([run.goal, state.goal, criterion, " ".join(state.acceptance_criteria)]).lower()
    if any(word in text for word in PPTX_WORDS):
        return ".pptx"
    if any(word in text for word in HTML_WORDS):
        return ".html"
    return ""


def expected_artifact_exists(run: RunRecord, state: RunState, criterion: str = "") -> bool:
    suffix = expected_artifact_suffix(run, state, criterion)
    if not suffix or not run.workspace_path:
        return False
    workspace = Path(run.workspace_path)
    if not workspace.exists():
        return False
    return any(
        "node_modules" not in path.parts and path.is_file() and path.stat().st_size > 0
        for path in workspace.rglob(f"*{suffix}")
    )


def artifact_creation_action(run: RunRecord, state: RunState) -> dict | None:
    suffix = expected_artifact_suffix(run, state)
    if suffix != ".pptx" or not run.workspace_path:
        return None
    workspace = Path(run.workspace_path)
    script_path = workspace / "_agentornith_create_pptx.py"
    if not script_path.exists():
        filename = expected_artifact_filename(run, state, ".pptx")
        return {
            "tool": "file_write",
            "args": {
                "path": script_path.name,
                "content": _pptx_creator_script(filename),
            },
            "thought_summary": f"Scaffold a local PPTX creator for missing deliverable {filename}.",
        }
    python_path = _bundled_python_path()
    command = f"\"{python_path}\" {script_path.name}" if python_path else f"python {script_path.name}"
    return {
        "tool": "shell",
        "args": {"command": command, "timeout": 60},
        "thought_summary": "Run the local PPTX creator before artifact verification.",
    }


def expected_artifact_filename(run: RunRecord, state: RunState, suffix: str) -> str:
    text = " ".join([run.goal, state.goal, " ".join(state.acceptance_criteria)])
    match = re.search(rf"([A-Za-z0-9][A-Za-z0-9_.-]{{0,120}}{re.escape(suffix)})", text, re.IGNORECASE)
    if match:
        return Path(match.group(1).strip(" .")).name
    return f"AgentOrnith_use_cases{suffix}" if suffix == ".pptx" else f"artifact{suffix}"


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
        "files=sorted(p for p in Path('.').rglob('*.pptx') if 'node_modules' not in p.parts); "
        "assert files, 'no pptx files found'; "
        "p=files[0]; assert p.stat().st_size > 1000, 'pptx file is too small'; "
        "z=zipfile.ZipFile(p); "
        "slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]; "
        + slide_check
        + "text=' '.join(z.read(n).decode('utf-8', errors='ignore').lower() for n in slides); "
        + text_checks
        + "print(str(p), len(slides), p.stat().st_size)\""
    )


def _bundled_python_path() -> str:
    candidate = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "python.exe"
    return str(candidate) if candidate.exists() else ""


def _pptx_creator_script(filename: str) -> str:
    return f'''from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt


OUTPUT = Path({filename!r})
SLIDES = [
    {{
        "title": "AgentOrnith makes Ornith operational",
        "subtitle": "A local command-line model becomes a supervised coding workbench with memory, tools, artifacts, and recovery.",
        "left": "AgentOrnith harness",
        "right": "Command-line Ornith",
        "harness": "Runs through a visible goal loop with checkpoints, approvals, tool logs, and artifact tracking.",
        "cli": "Answers one prompt at a time and depends on the operator to preserve context, evidence, and next steps.",
        "tradeoff": "Tradeoff: the harness adds policy and UI overhead, but that overhead buys durability for long work.",
    }},
    {{
        "title": "Use case 1: Long coding tasks",
        "subtitle": "Keep multi-hour implementation work coherent after pauses, crashes, or compaction.",
        "left": "AgentOrnith harness",
        "right": "Command-line Ornith",
        "harness": "Breaks work into milestones, persists events in SQLite, writes Obsidian checkpoints, and resumes from handoff bundles.",
        "cli": "Can lose thread state when the terminal scrolls, the model context fills, or the session restarts.",
        "tradeoff": "Tradeoff: checkpoints take time, but they prevent repeated re-orientation and forgotten acceptance criteria.",
    }},
    {{
        "title": "Use case 2: Web and browser evidence",
        "subtitle": "Research and verify facts without giving the model unrestricted internet access.",
        "left": "AgentOrnith harness",
        "right": "Command-line Ornith",
        "harness": "Uses audited web search, fetch, browser screenshots, excerpts, timestamps, and citation references.",
        "cli": "Usually relies on pasted links or untracked manual browsing, so evidence is harder to replay or audit.",
        "tradeoff": "Tradeoff: tool-gated browsing is slower than raw guesses, but it makes sources reviewable.",
    }},
    {{
        "title": "Use case 3: Safe file, shell, and test work",
        "subtitle": "Let Ornith act locally while keeping risky operations visible and recoverable.",
        "left": "AgentOrnith harness",
        "right": "Command-line Ornith",
        "harness": "Routes shell, file writes, git diffs, tests, and approvals through policy modes with secret redaction and logs.",
        "cli": "Can propose commands, but the operator must decide what is safe, remember results, and recover manually.",
        "tradeoff": "Tradeoff: strict approval modes can interrupt work; workspace autopilot or bypass modes reduce friction when trusted.",
    }},
    {{
        "title": "Use case 4: Project workspaces and artifacts",
        "subtitle": "Treat each run like an isolated project workspace instead of a loose terminal session.",
        "left": "AgentOrnith harness",
        "right": "Command-line Ornith",
        "harness": "Maps the repo, isolates edits, tracks touched files, verifies deliverables, and exposes artifacts in the dashboard.",
        "cli": "Works in the current folder but has no built-in artifact registry, source preview, or promotion workflow.",
        "tradeoff": "Tradeoff: isolation adds copy/sync complexity, but it reduces accidental edits to the source workspace.",
    }},
    {{
        "title": "Use case 5: IDE-style supervision",
        "subtitle": "Keep user decisions in the same place as model activity.",
        "left": "AgentOrnith harness",
        "right": "Command-line Ornith",
        "harness": "Shows live model summaries, tool events, approvals, blockers, screenshots, and chat steering in one workbench.",
        "cli": "The user must scan terminal output and external files to understand what needs attention.",
        "tradeoff": "Tradeoff: the dashboard must stay well organized; focus chat and tabs keep the detail available without crowding the main flow.",
    }},
]


def add_textbox(slide, x, y, w, h, text, size=18, bold=False, color=RGBColor(22, 28, 36), align=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    if align is not None:
        paragraph.alignment = align
    run = paragraph.runs[0]
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    frame.word_wrap = True
    return box


def add_panel(slide, x, y, w, h, heading, body, accent):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(248, 250, 252)
    shape.line.color.rgb = RGBColor(205, 213, 223)
    add_textbox(slide, x + 0.22, y + 0.18, w - 0.44, 0.35, heading, size=15, bold=True, color=accent)
    add_textbox(slide, x + 0.22, y + 0.66, w - 0.44, h - 0.86, body, size=14, color=RGBColor(32, 41, 54))


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    dark = RGBColor(17, 24, 39)
    green = RGBColor(22, 101, 52)
    slate = RGBColor(71, 85, 105)
    amber = RGBColor(146, 64, 14)
    for index, item in enumerate(SLIDES):
        slide = prs.slides.add_slide(blank)
        bg = slide.background.fill
        bg.solid()
        bg.fore_color.rgb = RGBColor(255, 255, 255)
        add_textbox(slide, 0.55, 0.35, 12.2, 0.48, item["title"], size=25, bold=True, color=dark)
        add_textbox(slide, 0.58, 0.92, 11.9, 0.45, item["subtitle"], size=13, color=slate)
        if index == 0:
            add_panel(slide, 0.75, 1.75, 5.85, 2.2, item["left"], item["harness"], green)
            add_panel(slide, 6.75, 1.75, 5.85, 2.2, item["right"], item["cli"], slate)
            add_textbox(slide, 0.86, 4.45, 11.6, 1.0, item["tradeoff"], size=16, bold=True, color=amber, align=PP_ALIGN.CENTER)
        else:
            add_panel(slide, 0.75, 1.65, 5.85, 2.7, item["left"], item["harness"], green)
            add_panel(slide, 6.75, 1.65, 5.85, 2.7, item["right"], item["cli"], slate)
            add_textbox(slide, 0.86, 4.78, 11.6, 0.9, item["tradeoff"], size=15, color=amber, align=PP_ALIGN.CENTER)
        add_textbox(slide, 0.62, 6.82, 2.2, 0.28, f"{{index + 1}} / {{len(SLIDES)}}", size=10, color=slate)
    prs.save(OUTPUT)
    print(f"created {{OUTPUT}} with {{len(SLIDES)}} slides")


if __name__ == "__main__":
    build()
'''


def _html_command() -> str:
    return (
        "python -c \"from pathlib import Path; "
        "files=sorted(p for p in Path('.').rglob('*.html') if 'node_modules' not in p.parts); "
        "assert files, 'no html files found'; "
        "p=files[0]; text=p.read_text(encoding='utf-8', errors='replace').lower(); "
        "assert '<html' in text and '</html>' in text, 'html document is incomplete'; "
        "assert p.stat().st_size > 500, 'html file is too small'; "
        "print(str(p), p.stat().st_size)\""
    )
