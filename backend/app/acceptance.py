from __future__ import annotations

import re


EVIDENCE_LABEL_WORDS: dict[str, set[str]] = {
    "verification": {
        "build",
        "check",
        "checks",
        "audio",
        "arpeggiator",
        "attack",
        "bonus",
        "characters",
        "chord",
        "coin",
        "coins",
        "collision",
        "compile",
        "contains",
        "control",
        "controls",
        "deck",
        "distance",
        "exist",
        "exists",
        "feedback",
        "filter",
        "highlighted",
        "jump",
        "keyboard",
        "lane",
        "lanes",
        "latency",
        "lint",
        "limitation",
        "limitations",
        "logo",
        "logos",
        "mapping",
        "metronome",
        "movement",
        "note",
        "notes",
        "obstacle",
        "obstacles",
        "octave",
        "original",
        "copyrighted",
        "play",
        "playback",
        "powerpoint",
        "preset",
        "presets",
        "pressed",
        "pptx",
        "recording",
        "release",
        "restart",
        "scale",
        "score",
        "slide",
        "slides",
        "sound",
        "speed",
        "sustain",
        "synth",
        "test",
        "tests",
        "tradeoff",
        "tradeoffs",
        "valid",
        "verification",
        "verify",
    },
    "checkpoint": {"checkpoint", "obsidian", "handoff", "note", "notes", "memory"},
    "browser": {
        "arcade",
        "browser",
        "controls",
        "dashboard",
        "design",
        "desktop",
        "hud",
        "highlighted",
        "layout",
        "load",
        "loads",
        "local",
        "localhost",
        "mapping",
        "page",
        "responsive",
        "screen",
        "screenshot",
        "start",
        "starts",
        "ui",
        "visual",
        "visualizer",
    },
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
CHECKPOINT_CONTEXT_WORDS = {"checkpoint", "handoff", "memory", "obsidian"}
MUSIC_NOTE_CONTEXT_WORDS = {
    "audio",
    "keyboard",
    "keys",
    "mapping",
    "music",
    "musical",
    "play",
    "synth",
    "synthesizer",
}
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
        and not _evidence_label_is_false_positive(label, words)
    ]


def _evidence_label_is_false_positive(label: str, words: set[str]) -> bool:
    if label == "checkpoint":
        return _checkpoint_label_is_false_positive(words)
    if label == "web":
        return _web_label_is_false_positive(words)
    return False


def _checkpoint_label_is_false_positive(words: set[str]) -> bool:
    if not words.intersection({"note", "notes"}):
        return False
    if words.intersection(CHECKPOINT_CONTEXT_WORDS):
        return False
    return bool(words.intersection(MUSIC_NOTE_CONTEXT_WORDS))


def _web_label_is_false_positive(words: set[str]) -> bool:
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
