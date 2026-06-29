from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tools import TOOL_NAMES


@dataclass(frozen=True)
class NormalizedAction:
    action: dict[str, Any] | None
    message: str
    repaired: bool = False


def normalize_model_action(action: dict[str, Any]) -> NormalizedAction:
    repairs: list[str] = []
    tool_name = str(action.get("tool") or action.get("action") or action.get("name") or "").strip()
    if not action.get("tool") and tool_name:
        repairs.append("repaired tool key")
    if tool_name == "inspect_workspace":
        tool_name = "file_read"
        repairs.append("mapped inspect_workspace to file_read")
    if tool_name not in TOOL_NAMES:
        return NormalizedAction(None, f"Unknown or missing tool: {tool_name or 'none'}")
    args = action.get("args")
    if not isinstance(args, dict):
        args = {}
        repairs.append("repaired args to empty object")
    if tool_name == "file_read" and not args:
        args = {"path": "."}
        repairs.append("added default file_read path")
    normalized = {
        "tool": tool_name,
        "args": args,
        "thought_summary": str(action.get("thought_summary") or action.get("summary") or "").strip(),
    }
    return NormalizedAction(normalized, "; ".join(repairs), bool(repairs))
