from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from .schemas import (
    ModelInteractionRecord,
    ModelPromptQualityReport,
    ModelQualityPattern,
    ModelQualitySample,
    RunRecord,
)
from .tools import redact_secrets


PATTERN_INFO = {
    "json_repaired": (
        "info",
        "JSON needed harness repair",
        "Keep compact JSON-only prompts and add fixture coverage for any new repaired shape.",
    ),
    "json_retry": (
        "warning",
        "JSON retry was needed",
        "Move the required JSON shape closer to the action request and keep max output short.",
    ),
    "json_parse_failure": (
        "action",
        "JSON parse failed",
        "Tighten the JSON system prompt or add a targeted repair path for this output family.",
    ),
    "unknown_tool": (
        "action",
        "Unknown tool selected",
        "Add an alias only if the intent is safe and common; otherwise strengthen the allowed-tool prompt.",
    ),
    "fallback_used": (
        "warning",
        "Harness fallback was used",
        "Review the failed action prompt and add a fixture if this fallback repeats.",
    ),
    "direct_write_action": (
        "action",
        "Direct file write selected",
        "Bias Ornith toward patch_propose for edits and reserve file_write for explicitly safe generated artifacts.",
    ),
    "model_failure": (
        "warning",
        "Model interaction failed",
        "Inspect the compact error pattern and prefer harness repair over adding raw context.",
    ),
    "recovery_proof_failed": (
        "action",
        "Recovery proof failed",
        "Make the recovery strategy narrower before retrying the same proof tool.",
    ),
    "recovery_proof_unresolved": (
        "warning",
        "Recovery proof did not resolve evidence",
        "Require the next recovery proof to name the acceptance label and expected evidence update.",
    ),
    "recovery_proof_resolved": (
        "info",
        "Recovery proof resolved evidence",
        "Preserve this recovery path as a known-good proof strategy for similar runs.",
    ),
    "verification_tool_failed": (
        "warning",
        "Verification tool failed",
        "Inspect whether the selected proof tool was too broad and add a narrower recommendation if this repeats.",
    ),
    "objective_proof_strategy_failed": (
        "action",
        "Objective-readiness proof strategy failed",
        "Bias the objective-readiness playbook toward a narrower alternate proof before repeating this item/tool/strategy.",
    ),
    "objective_proof_strategy_partial": (
        "warning",
        "Objective-readiness proof strategy only produced partial evidence",
        "Require the next objective-readiness proof to name the exact compact report or evidence update it should verify.",
    ),
    "objective_proof_strategy_verified": (
        "info",
        "Objective-readiness proof strategy verified",
        "Consider preserving this item/tool/strategy as a known-good Ornith proof route.",
    ),
}


def build_model_prompt_quality_report(
    runs: list[RunRecord],
    *,
    profile_id: str,
    limit: int = 80,
) -> ModelPromptQualityReport:
    interactions = _recent_interactions(runs, limit)
    outcomes = _recent_verification_outcomes(runs, limit)
    objective_outcomes = _recent_objective_proof_outcomes(runs, limit)
    by_kind: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    pattern_runs: dict[str, set[str]] = defaultdict(set)
    samples: list[ModelQualitySample] = []

    for run, interaction in interactions:
        by_kind[interaction.kind] += 1
        issues = _classify_interaction(interaction)
        for issue in issues:
            issue_counts[issue] += 1
            pattern_runs[issue].add(run.id)
        if issues and len(samples) < 12:
            samples.append(_sample(run, interaction, issues[0]))

    for run, outcome in outcomes:
        issues = _classify_verification_outcome(outcome)
        for issue in issues:
            issue_counts[issue] += 1
            pattern_runs[issue].add(run.id)
        if issues and len(samples) < 12:
            samples.append(_verification_sample(run, outcome, issues[0]))

    for run, outcome in objective_outcomes:
        issues = _classify_objective_proof_outcome(outcome)
        for issue in issues:
            issue_counts[issue] += 1
            pattern_runs[issue].add(run.id)
        if issues and len(samples) < 12:
            samples.append(_objective_proof_sample(run, outcome, issues[0]))

    patterns = [
        _pattern(issue, count, sorted(pattern_runs[issue])[:6])
        for issue, count in issue_counts.most_common()
        if issue in PATTERN_INFO
    ]
    return ModelPromptQualityReport(
        profile_id=profile_id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        run_count=sum(
            1
            for run in runs
            if run.state.model_interactions
            or run.state.verification_outcomes.outcomes
            or run.state.objective_readiness_proof_outcomes
        ),
        interaction_count=len(interactions),
        ok_count=sum(1 for _run, item in interactions if item.ok),
        failure_count=sum(1 for _run, item in interactions if not item.ok),
        repaired_count=sum(1 for _run, item in interactions if item.repaired),
        fallback_count=sum(1 for _run, item in interactions if item.fallback_used),
        retry_count=sum(1 for _run, item in interactions if item.attempts > 1),
        by_kind=dict(sorted(by_kind.items())),
        issue_counts=dict(sorted(issue_counts.items())),
        patterns=patterns,
        samples=samples,
        recommendations=[pattern.recommendation for pattern in patterns if pattern.severity in {"action", "warning"}][:6],
    )


def _recent_interactions(
    runs: list[RunRecord],
    limit: int,
) -> list[tuple[RunRecord, ModelInteractionRecord]]:
    pairs: list[tuple[RunRecord, ModelInteractionRecord]] = []
    for run in runs:
        for interaction in run.state.model_interactions:
            pairs.append((run, interaction))
    pairs.sort(key=lambda item: item[1].created_at or "", reverse=True)
    return pairs[:limit]


def _recent_verification_outcomes(
    runs: list[RunRecord],
    limit: int,
) -> list[tuple[RunRecord, object]]:
    pairs: list[tuple[RunRecord, object]] = []
    for run in runs:
        for outcome in run.state.verification_outcomes.outcomes:
            pairs.append((run, outcome))
    pairs.sort(key=lambda item: getattr(item[1], "timestamp", "") or "", reverse=True)
    return pairs[:limit]


def _recent_objective_proof_outcomes(
    runs: list[RunRecord],
    limit: int,
) -> list[tuple[RunRecord, object]]:
    pairs: list[tuple[RunRecord, object]] = []
    for run in runs:
        for outcome in run.state.objective_readiness_proof_outcomes:
            pairs.append((run, outcome))
    pairs.sort(key=lambda item: getattr(item[1], "created_at", "") or "", reverse=True)
    return pairs[:limit]


def _classify_interaction(interaction: ModelInteractionRecord) -> list[str]:
    issues: list[str] = []
    error = interaction.error.lower()
    summary = interaction.summary.lower()
    if interaction.repaired:
        issues.append("json_repaired")
    if interaction.attempts > 1:
        issues.append("json_retry")
    if "no valid json" in error or ("json" in error and "valid" in error):
        issues.append("json_parse_failure")
    if "unknown or missing tool" in error:
        issues.append("unknown_tool")
    if interaction.fallback_used:
        issues.append("fallback_used")
    if interaction.kind == "action" and "file_write" in summary:
        issues.append("direct_write_action")
    if not interaction.ok and not any(issue in issues for issue in ("json_parse_failure", "unknown_tool", "fallback_used")):
        issues.append("model_failure")
    return list(dict.fromkeys(issues))


def _classify_verification_outcome(outcome: object) -> list[str]:
    issues: list[str] = []
    outcome_kind = str(getattr(outcome, "outcome", ""))
    during_recovery = bool(getattr(outcome, "during_recovery", False))
    closed_recovery = bool(getattr(outcome, "closed_recovery", False))
    resolved_recovery = bool(getattr(outcome, "resolved_recovery_evidence", False))
    if outcome_kind == "failed" and (during_recovery or closed_recovery):
        issues.append("recovery_proof_failed")
    elif outcome_kind == "failed":
        issues.append("verification_tool_failed")
    if (during_recovery or closed_recovery) and outcome_kind in {"executed", "recovery_tool_succeeded"} and not resolved_recovery:
        issues.append("recovery_proof_unresolved")
    if outcome_kind == "recovery_resolved":
        issues.append("recovery_proof_resolved")
    return list(dict.fromkeys(issues))


def _classify_objective_proof_outcome(outcome: object) -> list[str]:
    outcome_kind = str(getattr(outcome, "outcome", ""))
    if outcome_kind == "verified":
        return ["objective_proof_strategy_verified"]
    if outcome_kind == "failed":
        return ["objective_proof_strategy_failed"]
    if outcome_kind == "partial":
        return ["objective_proof_strategy_partial"]
    return []


def _pattern(issue: str, count: int, run_ids: list[str]) -> ModelQualityPattern:
    severity, label, recommendation = PATTERN_INFO[issue]
    return ModelQualityPattern(
        id=issue,
        severity=severity,  # type: ignore[arg-type]
        label=label,
        count=count,
        recommendation=recommendation,
        run_ids=run_ids,
    )


def _sample(run: RunRecord, interaction: ModelInteractionRecord, error_type: str) -> ModelQualitySample:
    return ModelQualitySample(
        run_id=run.id,
        title=run.title,
        kind=interaction.kind,
        ok=interaction.ok,
        repaired=interaction.repaired,
        fallback_used=interaction.fallback_used,
        attempts=interaction.attempts,
        error_type=error_type,
        summary=redact_secrets(interaction.summary)[:240],
        error=redact_secrets(interaction.error)[:240],
        created_at=interaction.created_at,
    )


def _verification_sample(run: RunRecord, outcome: object, error_type: str) -> ModelQualitySample:
    recovery_id = str(getattr(outcome, "recovery_id", ""))
    recovery_status = str(getattr(outcome, "recovery_status", ""))
    proof_label = str(getattr(outcome, "proof_label", ""))
    error = " ".join(
        part
        for part in [
            f"recovery={recovery_id}" if recovery_id else "",
            f"status={recovery_status}" if recovery_status else "",
            f"label={proof_label}" if proof_label else "",
        ]
        if part
    )
    return ModelQualitySample(
        run_id=run.id,
        title=run.title,
        kind="verification",
        ok=bool(getattr(outcome, "ok", False)),
        error_type=error_type,
        summary=redact_secrets(str(getattr(outcome, "summary", "")))[:240],
        error=redact_secrets(error)[:240],
        created_at=str(getattr(outcome, "timestamp", "")),
    )


def _objective_proof_sample(run: RunRecord, outcome: object, error_type: str) -> ModelQualitySample:
    item_id = str(getattr(outcome, "item_id", ""))
    tool = str(getattr(outcome, "tool", ""))
    strategy = str(getattr(outcome, "strategy", ""))
    label = str(getattr(outcome, "evidence_label", ""))
    error = " ".join(
        part
        for part in [
            f"item={item_id}" if item_id else "",
            f"tool={tool}" if tool else "",
            f"strategy={strategy}" if strategy else "",
            f"label={label}" if label else "",
        ]
        if part
    )
    return ModelQualitySample(
        run_id=run.id,
        title=run.title,
        kind="objective_readiness",
        ok=bool(getattr(outcome, "ok", False)),
        error_type=error_type,
        summary=redact_secrets(str(getattr(outcome, "summary", "")))[:240],
        error=redact_secrets(error)[:240],
        created_at=str(getattr(outcome, "created_at", "")),
    )
