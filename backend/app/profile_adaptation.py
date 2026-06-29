from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .model_profile import ModelProfile
from .schemas import (
    ModelEvalSummary,
    ModelProfileAdaptationAction,
    ModelProfileAdaptationProposal,
    ModelProfileAdaptationReview,
    ModelProfileAdaptationReviewSummary,
    ModelPromptQualityReport,
)


def build_model_profile_adaptation_proposal(
    profile: ModelProfile,
    quality: ModelPromptQualityReport,
    eval_summary: ModelEvalSummary,
) -> ModelProfileAdaptationProposal:
    actions: list[ModelProfileAdaptationAction] = []
    issues = quality.issue_counts

    json_pressure = issues.get("json_parse_failure", 0) + issues.get("json_retry", 0)
    if json_pressure:
        actions.append(
            _action(
                target="json_system",
                change="prompt_append",
                risk="medium",
                title="Tighten JSON-only response contract",
                proposed=(
                    "Append to json_system: If uncertain, return the safest valid fallback JSON object for the "
                    "requested schema; never explain, apologize, or include markdown."
                ),
                rationale="Live records show Ornith needed retries or failed JSON extraction.",
                evidence_counts={
                    "json_parse_failure": issues.get("json_parse_failure", 0),
                    "json_retry": issues.get("json_retry", 0),
                },
            )
        )

    if issues.get("unknown_tool", 0):
        actions.append(
            _action(
                target="action_prompt",
                change="prompt_append",
                risk="medium",
                title="Bias action selection toward declared tools",
                proposed=(
                    "Append to action prompt: Choose exactly one tool from the allowed list. "
                    "For orientation use file_read; for repository state use git_status; for edits use patch_propose."
                ),
                rationale="Live records show at least one unknown or missing tool selection.",
                evidence_counts={"unknown_tool": issues.get("unknown_tool", 0)},
            )
        )

    patch_pressure = issues.get("direct_write_action", 0) + eval_summary.patch_first_fail
    if patch_pressure:
        actions.append(
            _action(
                target="action_prompt",
                change="policy_bias",
                risk="medium",
                title="Strengthen patch-first edit policy",
                proposed=(
                    "Append to action prompt: Do not use file_write for source-code edits. "
                    "Use patch_propose first, then wait for approval before patch_apply."
                ),
                rationale="Live or fixture evidence indicates direct-write edit attempts can bypass reviewable patches.",
                evidence_counts={
                    "direct_write_action": issues.get("direct_write_action", 0),
                    "eval_patch_first_fail": eval_summary.patch_first_fail,
                },
            )
        )

    fallback_pressure = issues.get("fallback_used", 0)
    if fallback_pressure and not issues.get("unknown_tool", 0):
        actions.append(
            _action(
                target="eval_fixture",
                change="eval_fixture",
                risk="low",
                title="Promote repeated fallback shape into eval fixtures",
                proposed=(
                    "Add a compact eval fixture for the repeated fallback pattern before changing prompts, "
                    "then compare fixture score before and after the prompt edit."
                ),
                rationale="Fallbacks occurred without a known unknown-tool signature, so fixture coverage should come first.",
                evidence_counts={"fallback_used": fallback_pressure},
            )
        )

    recovery_failure_pressure = issues.get("recovery_proof_failed", 0)
    recovery_unresolved_pressure = issues.get("recovery_proof_unresolved", 0)
    if recovery_failure_pressure:
        actions.append(
            _action(
                target="policy",
                change="policy_bias",
                risk="medium",
                title="Narrow recovery proof retries after failed outcomes",
                proposed=(
                    "When the latest recovery proof fails, require the next plan to choose a narrower diagnostic "
                    "or a different proof tool before allowing the same recovery tool again."
                ),
                rationale="Verification outcome history shows at least one recovery proof failed.",
                evidence_counts={"recovery_proof_failed": recovery_failure_pressure},
            )
        )

    if recovery_unresolved_pressure >= 2:
        actions.append(
            _action(
                target="action_prompt",
                change="prompt_append",
                risk="medium",
                title="Require explicit evidence labels for unresolved recovery proofs",
                proposed=(
                    "Append to action prompt: For recovery verification, state which acceptance label the tool should "
                    "satisfy and prefer the smallest command or screenshot that can update that label."
                ),
                rationale="Verification outcome history shows repeated recovery proofs ran without resolving evidence.",
                evidence_counts={"recovery_proof_unresolved": recovery_unresolved_pressure},
            )
        )

    objective_failed_pressure = issues.get("objective_proof_strategy_failed", 0)
    objective_partial_pressure = issues.get("objective_proof_strategy_partial", 0)
    objective_verified_pressure = issues.get("objective_proof_strategy_verified", 0)
    objective_failed_runs = _pattern_run_count(quality, "objective_proof_strategy_failed")
    objective_verified_runs = _pattern_run_count(quality, "objective_proof_strategy_verified")
    if objective_failed_pressure >= 2 and objective_failed_runs >= 2:
        actions.append(
            _action(
                target="policy",
                change="policy_bias",
                risk="medium",
                title="Bias objective-readiness proofs away from cross-run failed strategies",
                proposed=(
                    "When an objective-readiness item has repeated failed proof outcomes across runs, promote the "
                    "narrowest alternate proof preference before allowing Ornith to retry the same item/tool/strategy."
                ),
                rationale="Objective-readiness proof outcomes show the same class of strategy failure across multiple runs.",
                evidence_counts={
                    "objective_proof_strategy_failed": objective_failed_pressure,
                    "objective_failed_runs": objective_failed_runs,
                },
            )
        )

    if objective_partial_pressure >= 2:
        actions.append(
            _action(
                target="action_prompt",
                change="prompt_append",
                risk="medium",
                title="Require explicit evidence targets for partial objective proofs",
                proposed=(
                    "Append to action prompt: For objective-readiness proofs, name the readiness item, expected compact "
                    "report section, and exact success signal before selecting a tool."
                ),
                rationale="Objective-readiness proof outcomes repeatedly produced partial evidence instead of verification.",
                evidence_counts={"objective_proof_strategy_partial": objective_partial_pressure},
            )
        )

    if objective_verified_pressure >= 2 and objective_verified_runs >= 2:
        actions.append(
            _action(
                target="eval_fixture",
                change="eval_fixture",
                risk="low",
                title="Preserve verified objective-readiness proof strategies in evals",
                proposed=(
                    "Add or update an Ornith eval fixture covering the verified objective-readiness proof route so future "
                    "prompt or playbook changes keep selecting the known-good narrow strategy."
                ),
                rationale="Objective-readiness proof outcomes show verified proof strategies across multiple runs.",
                evidence_counts={
                    "objective_proof_strategy_verified": objective_verified_pressure,
                    "objective_verified_runs": objective_verified_runs,
                },
            )
        )

    repaired_pressure = issues.get("json_repaired", 0)
    if repaired_pressure >= 3:
        actions.append(
            _action(
                target="normalizer",
                change="manual_review",
                risk="low",
                title="Review repaired JSON shapes for safe normalizer support",
                proposed=(
                    "Inspect compact repaired-output samples and add a normalizer only when the intent is common, "
                    "safe, and already covered by an eval fixture."
                ),
                rationale="Several outputs were rescued by repair; common safe shapes may deserve explicit coverage.",
                evidence_counts={"json_repaired": repaired_pressure},
            )
        )

    status = "needs_confirmation" if actions else "no_change"
    return ModelProfileAdaptationProposal(
        id=f"profile-adapt-{uuid4().hex[:8]}",
        profile_id=profile.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status=status,
        summary=_summary(actions, quality, eval_summary),
        confidence=_confidence(actions, quality),
        confirmation_required=True,
        actions=actions,
        no_change_reason="" if actions else "No live or fixture signals currently justify changing the Ornith profile.",
    )


def compact_adaptation_review(review: ModelProfileAdaptationReview) -> ModelProfileAdaptationReviewSummary:
    return ModelProfileAdaptationReviewSummary(
        id=review.id,
        profile_id=review.profile_id,
        decision=review.decision,
        proposal_summary=review.proposal.summary,
        action_titles=[action.title for action in review.proposal.actions[:5]],
        reviewer_note=review.reviewer_note,
        created_at=review.created_at,
    )


def _action(
    *,
    target: str,
    change: str,
    risk: str,
    title: str,
    proposed: str,
    rationale: str,
    evidence_counts: dict[str, int],
) -> ModelProfileAdaptationAction:
    return ModelProfileAdaptationAction(
        id=f"adapt-{uuid4().hex[:8]}",
        target=target,  # type: ignore[arg-type]
        change=change,  # type: ignore[arg-type]
        risk=risk,  # type: ignore[arg-type]
        title=title,
        proposed=proposed,
        rationale=rationale,
        evidence_counts={key: value for key, value in evidence_counts.items() if value},
        requires_confirmation=True,
    )


def _summary(
    actions: list[ModelProfileAdaptationAction],
    quality: ModelPromptQualityReport,
    eval_summary: ModelEvalSummary,
) -> str:
    if not actions:
        return "No Ornith profile changes proposed."
    return (
        f"Proposed {len(actions)} reviewable Ornith profile adaptation(s) from "
        f"{quality.interaction_count} live interaction(s) and {eval_summary.total} eval fixture(s)."
    )


def _confidence(actions: list[ModelProfileAdaptationAction], quality: ModelPromptQualityReport) -> str:
    if not actions:
        return "low"
    if quality.interaction_count >= 10 and any(action.risk == "medium" for action in actions):
        return "high"
    if quality.interaction_count >= 2:
        return "medium"
    return "low"


def _pattern_run_count(quality: ModelPromptQualityReport, pattern_id: str) -> int:
    for pattern in quality.patterns:
        if pattern.id == pattern_id:
            return len(pattern.run_ids)
    return 0
