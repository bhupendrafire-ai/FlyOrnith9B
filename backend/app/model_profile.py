from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ModelProfile:
    id: str
    display_name: str
    summary: str
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    context_target_tokens: int
    memory_chars: int
    handoff_chars: int
    action_context_chars: int
    critic_context_chars: int
    goal_context_chars: int
    plan_max_steps: int
    json_retries: int
    default_temperature: float
    planner_system: str
    json_system: str

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["strengths"] = list(self.strengths)
        data["weaknesses"] = list(self.weaknesses)
        return data


@dataclass(frozen=True)
class JsonExtractionResult:
    payload: dict[str, Any]
    repaired: bool
    strategy: str


ORNITH_PROFILE = ModelProfile(
    id="ornith",
    display_name="Ornith local coding model",
    summary=(
        "Optimized for a local Ornith/Orinth coding model: keep prompts compact, make tool choices "
        "schema-first, verify every action externally, and let the harness carry long-run memory."
    ),
    strengths=(
        "Good at short, explicit coding plans when repo and task context are already curated.",
        "Works well with deterministic tool loops and concrete file/test feedback.",
        "Benefits from Obsidian and SQLite handoffs instead of raw chat history.",
    ),
    weaknesses=(
        "May wrap JSON in prose or code fences unless the harness extracts and validates it.",
        "Can drift when asked to reason over large raw logs or broad context dumps.",
        "Needs external verification and recovery loops for long multi-step coding tasks.",
    ),
    context_target_tokens=18000,
    memory_chars=4500,
    handoff_chars=3500,
    action_context_chars=6500,
    critic_context_chars=3500,
    goal_context_chars=3500,
    plan_max_steps=6,
    json_retries=1,
    default_temperature=0.15,
    planner_system=(
        "You are Ornith inside AgentOrinth. Produce short, concrete coding-agent steps. "
        "Do not narrate. Do not include hidden reasoning. Prefer inspect -> edit -> verify -> checkpoint."
    ),
    json_system=(
        "You are Ornith inside AgentOrinth. Return one valid JSON object only. "
        "No markdown fences, no prose, no comments, no trailing commas."
    ),
)


GENERIC_PROFILE = ModelProfile(
    id="generic",
    display_name="Generic OpenAI-compatible model",
    summary="Generic local/remote chat-completions profile.",
    strengths=("Can follow ordinary chat-completions prompts.",),
    weaknesses=("No model-specific harness assumptions are enabled.",),
    context_target_tokens=24000,
    memory_chars=6000,
    handoff_chars=4500,
    action_context_chars=9000,
    critic_context_chars=4000,
    goal_context_chars=4500,
    plan_max_steps=7,
    json_retries=0,
    default_temperature=0.2,
    planner_system="Return only a concise numbered plan.",
    json_system="Return only JSON.",
)


def profile_for(model_name: str, requested: str = "ornith") -> ModelProfile:
    value = (requested or "").strip().lower()
    model = model_name.lower()
    if value in {"ornith", "orinth", "orint"} or "ornith" in model or "orinth" in model or "orint" in model:
        return ORNITH_PROFILE
    return GENERIC_PROFILE


def extract_json_object(text: str) -> dict[str, Any]:
    return extract_json_object_result(text).payload


def extract_json_object_result(text: str) -> JsonExtractionResult:
    raw = text.strip()
    cleaned = _strip_json_fence(raw)
    candidates: list[tuple[str, str, bool]] = [(cleaned, "direct", cleaned != raw)]
    balanced = _first_balanced_object(cleaned)
    if balanced and balanced != cleaned:
        candidates.append((balanced, "balanced_object", True))
    for candidate, strategy, repaired in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return JsonExtractionResult(payload=payload, repaired=repaired, strategy=strategy)
    raise ValueError("No valid JSON object found in model output.")


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _first_balanced_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""
