from __future__ import annotations

import re


EVIDENCE_LABEL_WORDS: dict[str, set[str]] = {
    "verification": {
        "build",
        "check",
        "checks",
        "compile",
        "contains",
        "deck",
        "exist",
        "exists",
        "lint",
        "limitation",
        "limitations",
        "powerpoint",
        "pptx",
        "slide",
        "slides",
        "test",
        "tests",
        "tradeoff",
        "tradeoffs",
        "valid",
        "verification",
        "verify",
    },
    "checkpoint": {"checkpoint", "obsidian", "handoff", "note", "notes", "memory"},
    "browser": {"dashboard", "browser", "page", "localhost", "local", "start", "starts", "load", "loads", "screenshot"},
    "edit": {"edit", "code", "write", "implement", "implemented", "patch", "change"},
    "web": {"web", "internet", "source", "sources", "search", "citation", "citations", "latest"},
}

EVIDENCE_LABEL_ORDER = ("verification", "checkpoint", "browser", "edit", "web")
LOCAL_WEB_APP_WORDS = {
    "app",
    "browser",
    "dashboard",
    "load",
    "loads",
    "local",
    "locally",
    "localhost",
    "page",
    "run",
    "runs",
    "start",
    "starts",
}
WEB_SOURCE_WORDS = EVIDENCE_LABEL_WORDS["web"] - {"web"}
SOURCE_FILE_CONTEXT_WORDS = {
    "code",
    "css",
    "file",
    "files",
    "html",
    "implemented",
    "index",
    "javascript",
    "package",
    "project",
    "workspace",
}
WEB_CITATION_WORDS = {"internet", "latest", "search", "citation", "citations", "web"}


def text_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_-]{3,}", text.lower())


def infer_required_labels(criterion: str) -> list[str]:
    words = set(text_words(criterion))
    return [
        label
        for label in EVIDENCE_LABEL_ORDER
        if words.intersection(EVIDENCE_LABEL_WORDS[label])
        and not _web_label_is_false_positive(label, words)
    ]


def _web_label_is_false_positive(label: str, words: set[str]) -> bool:
    if label != "web":
        return False
    if "web" in words and not words.intersection(WEB_SOURCE_WORDS) and words.intersection(LOCAL_WEB_APP_WORDS):
        return True
    if words.intersection({"source", "sources"}) and not words.intersection(WEB_CITATION_WORDS):
        return bool(words.intersection(SOURCE_FILE_CONTEXT_WORDS))
    return False


def compact_label_progress(required: list[str], matched: list[str]) -> str:
    if not required:
        return ""
    matched_set = set(matched)
    parts = [f"{label}=ok" if label in matched_set else f"{label}=open" for label in required]
    return ",".join(parts)
