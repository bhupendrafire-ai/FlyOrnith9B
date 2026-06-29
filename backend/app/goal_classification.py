from __future__ import annotations


HARNESS_GOAL_MARKERS = (
    "agentorinth",
    "agent orinth",
    "ornith",
    "orinth",
    "orint",
    "coding harness",
    "agent harness",
    "agentic harness",
    "codex-like",
    "codex like",
    "long coding",
    "long-running",
    "long running",
)

MODEL_NAME_ONLY_MARKERS = {"ornith", "orinth", "orint"}

HARNESS_WORK_MARKERS = (
    "add",
    "build",
    "create",
    "debug",
    "extend",
    "fix",
    "harden",
    "implement",
    "improve",
    "integrate",
    "patch",
    "refactor",
    "repair",
    "support",
    "upgrade",
    "wire",
)

HARNESS_CODE_TARGET_MARKERS = (
    "api",
    "backend",
    "dashboard",
    "frontend",
    "harness",
    "loop",
    "memory",
    "model profile",
    "orchestration",
    "policy",
    "resume",
    "runner",
    "sqlite",
    "tool",
    "workbench",
)

CONCRETE_CODE_TARGET_MARKERS = tuple(marker for marker in HARNESS_CODE_TARGET_MARKERS if marker != "harness")

CONTENT_DELIVERABLE_MARKERS = (
    ".html",
    ".pptx",
    "article",
    "deck",
    "explain",
    "landing page",
    "one page",
    "page explaining",
    "browser app",
    "powerpoint",
    "presentation",
    "single page",
    "slide",
    "web app",
    "web page",
    "webpage",
)


def is_harness_improvement_goal(goal: str, active_goal: str = "") -> bool:
    text = _normalize(f"{goal} {active_goal}")
    matched_markers = {marker for marker in HARNESS_GOAL_MARKERS if marker in text}
    if not matched_markers:
        return False
    if matched_markers.issubset(MODEL_NAME_ONLY_MARKERS) and not _looks_like_concrete_code_work(text):
        return False
    if _looks_like_content_deliverable(text) and not _looks_like_concrete_code_work(text):
        return False
    return any(marker in text for marker in HARNESS_WORK_MARKERS)


def _looks_like_content_deliverable(text: str) -> bool:
    return any(marker in text for marker in CONTENT_DELIVERABLE_MARKERS)


def _looks_like_concrete_code_work(text: str) -> bool:
    return any(marker in text for marker in CONCRETE_CODE_TARGET_MARKERS)


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())
