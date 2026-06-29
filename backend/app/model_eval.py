from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .action_normalizer import normalize_model_action
from .model_profile import ModelProfile, extract_json_object_result
from .schemas import ModelEvalCaseResult, ModelEvalSummary


DEFAULT_ORNITH_EVAL_FIXTURE = Path(__file__).parent / "fixtures" / "ornith_eval.json"
PATCH_FIRST_EDIT_TOOLS = {"file_write", "patch_apply"}


def run_ornith_fixture_eval(
    profile: ModelProfile,
    fixture_path: Path = DEFAULT_ORNITH_EVAL_FIXTURE,
) -> ModelEvalSummary:
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = [_evaluate_case(item) for item in fixtures]
    total = len(cases)
    ok = sum(1 for case in cases if case.ok)
    summary = ModelEvalSummary(
        profile_id=profile.id,
        fixture_path=str(fixture_path),
        total=total,
        parsed=sum(1 for case in cases if case.parsed),
        ok=ok,
        repaired=sum(1 for case in cases if case.repaired),
        fallback_needed=sum(1 for case in cases if case.fallback_needed),
        valid_actions=sum(1 for case in cases if case.kind == "action" and case.ok and not case.fallback_needed),
        invalid_actions=sum(1 for case in cases if case.kind == "action" and case.fallback_needed),
        patch_first_pass=sum(1 for case in cases if case.patch_first_ok is True),
        patch_first_fail=sum(1 for case in cases if case.patch_first_ok is False),
        score=round(ok / total, 3) if total else 0.0,
        cases=cases,
    )
    return summary


def _evaluate_case(item: dict[str, Any]) -> ModelEvalCaseResult:
    case_id = str(item.get("id") or "unnamed")
    kind = str(item.get("kind") or "action")
    try:
        extracted = extract_json_object_result(str(item.get("text") or ""))
    except ValueError as exc:
        return ModelEvalCaseResult(
            id=case_id,
            kind=kind,
            error=str(exc),
            summary="Model output did not parse as a JSON object.",
        )

    payload = extracted.payload
    base = {
        "id": case_id,
        "kind": kind,
        "parsed": True,
        "repaired": extracted.repaired,
        "repair_strategy": extracted.strategy,
        "output_keys": sorted(str(key) for key in payload.keys()),
    }
    if kind == "action":
        return _evaluate_action_case(item, payload, base)
    expected_key = item.get("expected_key")
    expected_value = item.get("expected_value")
    if expected_key:
        value = payload.get(str(expected_key))
        ok = value == expected_value
        return ModelEvalCaseResult(
            **base,
            ok=ok,
            summary=f"Parsed {kind} JSON with expected key {expected_key}.",
            error="" if ok else f"Expected {expected_key}={expected_value!r}, got {value!r}.",
        )
    return ModelEvalCaseResult(**base, ok=True, summary=f"Parsed {kind} JSON.")


def _evaluate_action_case(
    item: dict[str, Any],
    payload: dict[str, Any],
    base: dict[str, Any],
) -> ModelEvalCaseResult:
    normalized = normalize_model_action(payload)
    expect_fallback = bool(item.get("expect_fallback"))
    if not normalized.action:
        return ModelEvalCaseResult(
            **base,
            ok=expect_fallback,
            fallback_needed=True,
            summary="Action requires harness fallback.",
            error=normalized.message,
        )

    tool = str(normalized.action["tool"])
    expect_tool = str(item.get("expect_tool") or tool)
    tool_ok = tool == expect_tool
    patch_first_ok = _patch_first_result(item, tool)
    ok = tool_ok and patch_first_ok is not False and not expect_fallback
    error = ""
    if not tool_ok:
        error = f"Expected tool {expect_tool}, got {tool}."
    elif patch_first_ok is False:
        error = "Edit-intent action bypassed patch_propose."
    result = dict(base)
    result["repaired"] = bool(base["repaired"]) or normalized.repaired
    return ModelEvalCaseResult(
        **result,
        ok=ok,
        fallback_needed=False,
        normalized_tool=tool,
        patch_first_ok=patch_first_ok,
        summary=f"Action normalized to {tool}.{(' ' + normalized.message) if normalized.message else ''}",
        error=error,
    )


def _patch_first_result(item: dict[str, Any], tool: str) -> bool | None:
    if not item.get("edit_intent"):
        return None
    expected = item.get("expect_patch_first_ok")
    if expected is not None:
        return bool(expected)
    return tool not in PATCH_FIRST_EDIT_TOOLS
