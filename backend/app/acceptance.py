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


def text_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_-]{3,}", text.lower())


def infer_required_labels(criterion: str) -> list[str]:
    words = set(text_words(criterion))
    return [
        label
        for label in EVIDENCE_LABEL_ORDER
        if words.intersection(EVIDENCE_LABEL_WORDS[label])
    ]


def compact_label_progress(required: list[str], matched: list[str]) -> str:
    if not required:
        return ""
    matched_set = set(matched)
    parts = [f"{label}=ok" if label in matched_set else f"{label}=open" for label in required]
    return ",".join(parts)
