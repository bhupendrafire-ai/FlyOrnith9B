from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RunStatus = Literal[
    "queued",
    "running",
    "paused",
    "waiting_approval",
    "waiting_goal_confirmation",
    "completed",
    "blocked",
    "canceled",
    "error",
]


class ToolCallRecord(BaseModel):
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool = False
    summary: str = ""
    needs_approval: bool = False
    created_at: str = ""


class AcceptanceCriterionEvidence(BaseModel):
    id: str
    criterion: str
    status: Literal["open", "verified", "failed", "blocked"] = "open"
    required_labels: list[str] = Field(default_factory=list)
    matched_labels: list[str] = Field(default_factory=list)
    label_checked_at: dict[str, str] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    last_tool: str = ""
    last_checked: str = ""
    notes: str = ""


class AcceptanceEvidenceRecommendation(BaseModel):
    id: str
    criterion_id: str
    criterion: str
    label: str
    tool_kind: str
    action: str
    command_hint: str = ""
    reason: str = ""
    available: bool = True


class AcceptanceRecommendationTrace(BaseModel):
    id: str
    recommendation_id: str
    criterion_id: str
    criterion: str
    label: str
    recommended_tool: str
    selected_tool: str
    source: Literal["harness", "model", "fallback"] = "harness"
    status: Literal["selected", "executed", "satisfied", "failed", "waiting_approval"] = "selected"
    action_summary: str = ""
    selected_at: str = ""
    resolved_at: str = ""
    result_ok: bool | None = None
    result_summary: str = ""
    evidence_status: str = ""
    notes: str = ""


class CompletionAuditIssue(BaseModel):
    id: str
    severity: Literal["info", "warning", "blocker"] = "info"
    summary: str
    evidence: list[str] = Field(default_factory=list)


class CompletionAuditReport(BaseModel):
    run_id: str
    generated_at: str = ""
    status: Literal["ready", "not_ready"] = "not_ready"
    can_finish: bool = False
    acceptance_total: int = 0
    acceptance_verified: int = 0
    acceptance_open: int = 0
    acceptance_failed: int = 0
    acceptance_blocked: int = 0
    pending_approvals: int = 0
    blocker_count: int = 0
    recent_failure_count: int = 0
    stale_evidence_count: int = 0
    issues: list[CompletionAuditIssue] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class CompletionVerificationPolicy(BaseModel):
    strict_stale_evidence: bool = True
    evidence_labels: dict[str, list[str]] = Field(default_factory=dict)
    stale_edit_tools: list[str] = Field(default_factory=list)
    verification_tools: list[str] = Field(default_factory=list)
    checkpoint_tools: list[str] = Field(default_factory=list)
    browser_tools: list[str] = Field(default_factory=list)
    edit_tools: list[str] = Field(default_factory=list)
    web_tools: list[str] = Field(default_factory=list)


class ModelInteractionRecord(BaseModel):
    id: str
    kind: Literal["plan", "action", "critic", "goal"] = "action"
    ok: bool = False
    attempts: int = 0
    repaired: bool = False
    fallback_used: bool = False
    summary: str = ""
    error: str = ""
    raw_excerpt: str = ""
    output_keys: list[str] = Field(default_factory=list)
    created_at: str = ""


class ModelEvalCaseResult(BaseModel):
    id: str
    kind: str
    ok: bool = False
    parsed: bool = False
    repaired: bool = False
    repair_strategy: str = ""
    fallback_needed: bool = False
    normalized_tool: str = ""
    patch_first_ok: bool | None = None
    summary: str = ""
    error: str = ""
    output_keys: list[str] = Field(default_factory=list)


class ModelEvalSummary(BaseModel):
    profile_id: str
    fixture_path: str
    total: int = 0
    parsed: int = 0
    ok: int = 0
    repaired: int = 0
    fallback_needed: int = 0
    valid_actions: int = 0
    invalid_actions: int = 0
    patch_first_pass: int = 0
    patch_first_fail: int = 0
    score: float = 0.0
    cases: list[ModelEvalCaseResult] = Field(default_factory=list)


class ModelQualitySample(BaseModel):
    run_id: str
    title: str
    kind: str
    ok: bool = False
    repaired: bool = False
    fallback_used: bool = False
    attempts: int = 0
    error_type: str = ""
    summary: str = ""
    error: str = ""
    created_at: str = ""


class ModelQualityPattern(BaseModel):
    id: str
    severity: Literal["info", "warning", "action"] = "info"
    label: str
    count: int = 0
    recommendation: str = ""
    run_ids: list[str] = Field(default_factory=list)


class ModelPromptQualityReport(BaseModel):
    profile_id: str
    generated_at: str
    run_count: int = 0
    interaction_count: int = 0
    ok_count: int = 0
    failure_count: int = 0
    repaired_count: int = 0
    fallback_count: int = 0
    retry_count: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    patterns: list[ModelQualityPattern] = Field(default_factory=list)
    samples: list[ModelQualitySample] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ModelProfileAdaptationAction(BaseModel):
    id: str
    target: Literal["json_system", "planner_system", "action_prompt", "normalizer", "eval_fixture", "policy"] = "action_prompt"
    change: Literal["prompt_append", "normalizer_alias", "eval_fixture", "policy_bias", "manual_review"] = "manual_review"
    risk: Literal["low", "medium", "high"] = "medium"
    title: str
    proposed: str
    rationale: str = ""
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    requires_confirmation: bool = True


class ModelProfileAdaptationProposal(BaseModel):
    id: str
    profile_id: str
    generated_at: str
    status: Literal["no_change", "needs_confirmation"] = "no_change"
    source: str = "live_quality_and_eval"
    summary: str = ""
    confidence: Literal["low", "medium", "high"] = "low"
    confirmation_required: bool = True
    actions: list[ModelProfileAdaptationAction] = Field(default_factory=list)
    no_change_reason: str = ""


class ModelProfileAdaptationReview(BaseModel):
    id: str
    profile_id: str
    proposal: ModelProfileAdaptationProposal
    decision: Literal["accepted", "rejected"]
    reviewer_note: str = ""
    created_at: str = ""


class ModelProfileAdaptationReviewRequest(BaseModel):
    proposal: ModelProfileAdaptationProposal
    decision: Literal["accepted", "rejected"]
    reviewer_note: str = ""


class ModelProfileAdaptationReviewSummary(BaseModel):
    id: str
    profile_id: str
    decision: Literal["accepted", "rejected"]
    proposal_summary: str = ""
    action_titles: list[str] = Field(default_factory=list)
    reviewer_note: str = ""
    created_at: str = ""


class WebSource(BaseModel):
    id: str
    title: str
    url: str
    timestamp: str
    excerpt: str
    citation: str


class DesktopSnapshot(BaseModel):
    id: str
    timestamp: str
    title: str
    path: str = ""
    summary: str = ""


class DesktopEffectProofReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["not_required", "needs_proof", "proof_available"] = "not_required"
    requires_attention: bool = False
    latest_action_id: str = ""
    latest_action_tool: str = ""
    latest_action_created_at: str = ""
    latest_action_summary: str = ""
    proof_call_id: str = ""
    proof_tool: str = ""
    proof_created_at: str = ""
    proof_summary: str = ""
    proof_snapshot: DesktopSnapshot | None = None
    proof_snapshot_count: int = 0
    ledger: list[str] = Field(default_factory=list)
    recommended_action: str = ""



class DesktopEffectProofRepairRecord(BaseModel):
    event_id: int = 0
    timestamp: str = ""
    outcome: Literal["metadata_refreshed", "capture_completed", "capture_failed", "blocked", "skipped_noop"] = "skipped_noop"
    previous_integrity_status: str = ""
    refreshed_integrity_status: str = ""
    previous_proof_status: str = ""
    refreshed_proof_status: str = ""
    latest_action_id: str = ""
    proof_call_id: str = ""
    proof_snapshot_id: str = ""
    reason_count: int = 0
    reasons: list[str] = Field(default_factory=list)
    summary: str = ""


class DesktopEffectProofRepairReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    total_count: int = 0
    metadata_refreshed_count: int = 0
    capture_completed_count: int = 0
    capture_failed_count: int = 0
    blocked_count: int = 0
    skipped_noop_count: int = 0
    latest_outcome: str = ""
    summary: str = "No desktop effect proof repair outcomes recorded."
    recommended_action: str = ""
    entries: list[DesktopEffectProofRepairRecord] = Field(default_factory=list)

class SourceEvidencePreviewEntry(BaseModel):
    id: str = ""
    kind: Literal["web_source", "browser_snapshot", "desktop_snapshot"] = "web_source"
    timestamp: str = ""
    title: str = ""
    url: str = ""
    path: str = ""
    tool_kind: str = ""
    evidence_label: str = ""
    linked_criteria: list[str] = Field(default_factory=list)
    excerpt: str = ""
    summary: str = ""
    citation: str = ""


class SourceEvidencePreviewReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    total_count: int = 0
    web_source_count: int = 0
    browser_snapshot_count: int = 0
    desktop_snapshot_count: int = 0
    linked_criterion_count: int = 0
    required_label_count: int = 0
    matched_label_count: int = 0
    missing_labels: list[str] = Field(default_factory=list)
    latest_evidence: str = ""
    summary: str = ""
    recommended_action: str = ""
    entries: list[SourceEvidencePreviewEntry] = Field(default_factory=list)

class TaskNode(BaseModel):
    id: str
    title: str
    status: Literal["pending", "in_progress", "completed", "blocked", "failed", "skipped"] = "pending"
    kind: Literal["investigate", "edit", "verify", "summarize", "decision", "blocked"] = "investigate"
    depends_on: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    notes: str = ""


class RepoMap(BaseModel):
    generated_at: str = ""
    root: str = ""
    manifests: list[str] = Field(default_factory=list)
    package_scripts: dict[str, str] = Field(default_factory=dict)
    test_commands: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)
    summary: str = ""


class WorkspaceIsolation(BaseModel):
    enabled: bool = False
    mode: Literal["source", "copy", "git_worktree"] = "source"
    source_path: str = ""
    workspace_path: str = ""
    created_at: str = ""
    copied_files: int = 0
    skipped_paths: list[str] = Field(default_factory=list)
    summary: str = ""


class WorkspaceDiffFile(BaseModel):
    path: str
    status: Literal["added", "modified", "deleted"] = "modified"
    source_size: int = 0
    workspace_size: int = 0
    source_sha256: str = ""
    workspace_sha256: str = ""
    diff: str = ""
    binary: bool = False
    truncated: bool = False


class WorkspaceDiffSummary(BaseModel):
    generated_at: str = ""
    source_path: str = ""
    workspace_path: str = ""
    files: list[WorkspaceDiffFile] = Field(default_factory=list)
    total_files: int = 0
    added: int = 0
    modified: int = 0
    deleted: int = 0
    truncated: bool = False
    summary: str = ""


class WorkspacePromotion(BaseModel):
    id: str
    status: Literal["promoted", "rolled_back", "failed"] = "promoted"
    files: list[str] = Field(default_factory=list)
    backup_id: str = ""
    manifest_path: str = ""
    summary: str = ""
    promoted_at: str = ""
    rolled_back_at: str = ""


class PatchProposal(BaseModel):
    id: str
    title: str
    summary: str = ""
    files: list[str] = Field(default_factory=list)
    diff: str = ""
    status: Literal["pending", "approved", "rejected", "applied", "rolled_back"] = "pending"
    backup_id: str = ""
    applied_at: str = ""
    rollback_manifest_path: str = ""
    created_at: str = ""


class PatchApplication(BaseModel):
    id: str
    patch_id: str = ""
    status: Literal["applied", "rolled_back", "failed"] = "applied"
    files: list[str] = Field(default_factory=list)
    backup_id: str = ""
    manifest_path: str = ""
    summary: str = ""
    applied_at: str = ""
    rolled_back_at: str = ""


class PromotionAuditIssue(BaseModel):
    id: str
    severity: Literal["info", "warning", "blocker"] = "info"
    summary: str
    evidence: list[str] = Field(default_factory=list)
    next_action: str = ""


class PromotionAuditReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["ready", "needs_verification", "blocked", "not_applicable"] = "not_applicable"
    ready_to_promote: bool = False
    changed_file_count: int = 0
    patch_proposal_count: int = 0
    patch_application_count: int = 0
    promotion_count: int = 0
    pending_patch_count: int = 0
    pending_approval_count: int = 0
    unresolved_approval_history_count: int = 0
    unresolved_approval_histories: list[str] = Field(default_factory=list)
    latest_verification: str = ""
    workspace_diff_status: str = ""
    workspace_diff_summary: str = ""
    resume_drift_status: str = ""
    git_checkpoint_status: str = ""
    summary: str = ""
    recommended_action: str = ""
    issues: list[PromotionAuditIssue] = Field(default_factory=list)


class PromotionVerificationAttemptRecord(BaseModel):
    event_id: int = 0
    timestamp: str = ""
    command: str = ""
    ok: bool = False
    audit_status: str = ""
    summary: str = ""
    tool_ok: bool = False
    selected_alternate: bool = False
    returncode: int = 0
    failure_kind: str = ""
    suspected_file: str = ""
    suspected_line: int = 0
    repair_hint: str = ""
    evidence_excerpt: str = ""


class PromotionVerificationReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["none", "ready", "needs_retry", "repeated_failure"] = "none"
    attempt_count: int = 0
    failed_count: int = 0
    success_count: int = 0
    repeated_failure_count: int = 0
    repair_hint_count: int = 0
    latest_attempt: PromotionVerificationAttemptRecord = Field(default_factory=PromotionVerificationAttemptRecord)
    latest_failed_command: str = ""
    latest_failure_kind: str = ""
    latest_suspected_file: str = ""
    latest_repair_hint: str = ""
    next_command: str = ""
    should_use_alternate: bool = False
    failure_kinds: list[str] = Field(default_factory=list)
    summary: str = ""
    recommended_action: str = ""
    attempts: list[PromotionVerificationAttemptRecord] = Field(default_factory=list)

class PromotionRepairReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    phase: Literal["none", "needs_file_read", "needs_patch_proposal", "patch_proposed", "ready_to_verify"] = "none"
    active: bool = False
    target_file: str = ""
    target_line: int = 0
    failure_kind: str = ""
    repair_hint: str = ""
    evidence_excerpt: str = ""
    latest_failed_command: str = ""
    file_read: bool = False
    file_read_tool_id: str = ""
    file_excerpt_chars: int = 0
    patch_proposal_id: str = ""
    patch_status: str = ""
    patch_application_id: str = ""
    next_tool: str = ""
    next_action: str = ""
    next_verification_command: str = ""
    summary: str = ""
class FailureRecord(BaseModel):
    id: str
    kind: str
    tool: str = ""
    summary: str
    count: int = 1
    last_seen: str = ""
    recovery_hint: str = ""
    command: str = ""
    target: str = ""
    returncode: int | None = None
    evidence_excerpt: str = ""


class RecoveryPlan(BaseModel):
    id: str = ""
    status: Literal["none", "active", "resolved", "superseded"] = "none"
    trigger: str = ""
    failure_kind: str = ""
    tool: str = ""
    attempts: int = 0
    summary: str = ""
    next_action: str = ""
    steps: list[str] = Field(default_factory=list)
    created_at: str = ""
    resolved_at: str = ""



class PostActionRetryDecisionRecord(BaseModel):
    id: str = ""
    status: Literal["pending", "selected", "resolved", "failed", "skipped"] = "pending"
    trigger_tool: str = ""
    trigger_summary: str = ""
    failure_kind: str = ""
    attempt_count: int = 0
    selected_tool: str = ""
    selected_action: str = ""
    command_hint: str = ""
    reason: str = ""
    action_context_summary: str = ""
    verification_outcome: str = ""
    resolution_tool: str = ""
    resolution_ok: bool = False
    resolution_summary: str = ""
    created_at: str = ""
    resolved_at: str = ""


class PostActionRetryReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    decision_count: int = 0
    pending_count: int = 0
    resolved_count: int = 0
    failed_count: int = 0
    latest_decision: PostActionRetryDecisionRecord = Field(default_factory=PostActionRetryDecisionRecord)
    summary: str = ""
    recommended_action: str = ""
    decisions: list[PostActionRetryDecisionRecord] = Field(default_factory=list)


class GoalEvolutionDecisionRecord(BaseModel):
    id: str = ""
    status: Literal["pending", "accepted", "rejected", "unchanged"] = "unchanged"
    source: str = ""
    previous_goal: str = ""
    proposed_goal: str = ""
    reason: str = ""
    material_change: str = ""
    step_count: int = 0
    milestone: str = ""
    approval_id: int = 0
    created_at: str = ""
    resolved_at: str = ""


class GoalEvolutionReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    active_goal: str = ""
    proposed_goal: str = ""
    decision_count: int = 0
    pending_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    unchanged_count: int = 0
    latest_decision: GoalEvolutionDecisionRecord = Field(default_factory=GoalEvolutionDecisionRecord)
    summary: str = ""
    recommended_action: str = ""
    decisions: list[GoalEvolutionDecisionRecord] = Field(default_factory=list)



class GitCheckpointReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["unknown", "not_repo", "needs_remote", "verify_first", "commit_recommended", "push_recommended", "clean"] = "unknown"
    workspace_path: str = ""
    repo_root: str = ""
    branch: str = ""
    head_sha: str = ""
    last_commit: str = ""
    remote_names: list[str] = Field(default_factory=list)
    remote_count: int = 0
    github_remote_count: int = 0
    staged_count: int = 0
    modified_count: int = 0
    untracked_count: int = 0
    changed_count: int = 0
    ahead_count: int = 0
    behind_count: int = 0
    recent_verification: str = ""
    summary: str = ""
    recommended_action: str = ""


class RecoveryDecisionRecord(BaseModel):
    id: str = ""
    status: Literal["none", "active", "resolved", "superseded"] = "none"
    trigger: str = ""
    failure_kind: str = ""
    tool: str = ""
    attempts: int = 0
    created_at: str = ""
    resolved_at: str = ""
    proof_label: str = ""
    proof_status: str = ""
    criterion_id: str = ""
    criterion: str = ""
    evidence_status: str = ""
    readiness_decision_id: int = 0
    readiness_decision_status: str = ""
    activation_reason: str = ""
    selected_strategy: str = ""
    next_action: str = ""
    resolved_by_evidence: bool = False
    summary: str = ""


class RecoveryDecisionReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    decision_count: int = 0
    active_recovery: bool = False
    readiness_recovery_count: int = 0
    resolved_count: int = 0
    unresolved_count: int = 0
    latest_decision: RecoveryDecisionRecord = Field(default_factory=RecoveryDecisionRecord)
    active_decision: RecoveryDecisionRecord = Field(default_factory=RecoveryDecisionRecord)
    latest_readiness_decision: RecoveryDecisionRecord = Field(default_factory=RecoveryDecisionRecord)
    summary: str = ""
    recommended_action: str = ""
    decisions: list[RecoveryDecisionRecord] = Field(default_factory=list)


class VerificationOutcomeRecord(BaseModel):
    id: str = ""
    timestamp: str = ""
    tool_call_id: str = ""
    tool: str = ""
    ok: bool = False
    needs_approval: bool = False
    outcome: Literal[
        "verified",
        "partial",
        "failed",
        "waiting_approval",
        "recovery_resolved",
        "recovery_tool_succeeded",
        "executed",
    ] = "executed"
    summary: str = ""
    during_recovery: bool = False
    recovery_id: str = ""
    recovery_trigger: str = ""
    recovery_status: str = ""
    recovery_resume_event_id: int = 0
    recovery_resume_timestamp: str = ""
    closed_recovery: bool = False
    resolved_recovery_evidence: bool = False
    proof_label: str = ""
    criterion_id: str = ""
    criterion: str = ""
    evidence_status: str = ""
    required_labels: list[str] = Field(default_factory=list)
    matched_labels: list[str] = Field(default_factory=list)
    labels_satisfied: list[str] = Field(default_factory=list)
    recommendation_trace_id: str = ""
    recommendation_status: str = ""
    readiness_decision_id: int = 0
    selected_strategy: str = ""


class VerificationOutcomeReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    outcome_count: int = 0
    verified_count: int = 0
    failed_count: int = 0
    recovery_outcome_count: int = 0
    recovery_resolved_count: int = 0
    recovery_unresolved_count: int = 0
    latest_outcome: VerificationOutcomeRecord = Field(default_factory=VerificationOutcomeRecord)
    latest_recovery_outcome: VerificationOutcomeRecord = Field(default_factory=VerificationOutcomeRecord)
    summary: str = ""
    recommended_action: str = ""
    outcomes: list[VerificationOutcomeRecord] = Field(default_factory=list)


class RunLease(BaseModel):
    id: str = ""
    owner_id: str = ""
    status: Literal["none", "active", "released", "stale"] = "none"
    acquired_at: str = ""
    heartbeat_at: str = ""
    expires_at: str = ""
    heartbeat_count: int = 0
    heartbeat_interval_seconds: int = 0
    ttl_seconds: int = 0
    last_milestone: str = ""
    last_event: str = ""


class ContextBudget(BaseModel):
    target_tokens: int = 24000
    estimated_tokens: int = 0
    last_compaction: str = ""
    pressure: Literal["low", "medium", "high"] = "low"


class ContextSnapshot(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    estimated_tokens: int = 0
    sections: list[str] = Field(default_factory=list)
    selected_section_count: int = 0
    dropped_sections: list[str] = Field(default_factory=list)
    dropped_section_count: int = 0
    required_sections_missing: list[str] = Field(default_factory=list)
    section_token_estimates: dict[str, int] = Field(default_factory=dict)
    coverage_status: Literal["ok", "degraded", "critical"] = "ok"
    recommended_action: str = ""
    prompt_preview: str = ""


class ResumePromptQualityIssue(BaseModel):
    id: str
    severity: Literal["info", "warning", "blocker"] = "info"
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    next_action: str = ""


class ResumePromptQualityReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["ready", "needs_refresh", "blocked"] = "needs_refresh"
    ready_to_resume: bool = False
    score: int = 0
    summary: str = ""
    prompt_chars: int = 0
    next_action: str = ""
    concrete_next_action: bool = False
    has_goal_anchor: bool = False
    has_context_anchor: bool = False
    has_action_context: bool = False
    has_evidence_refs: bool = False
    context_coverage_status: str = ""
    recommended_action: str = ""
    issues: list[ResumePromptQualityIssue] = Field(default_factory=list)



class ResumeHandoffDiffChange(BaseModel):
    id: str
    severity: Literal["info", "warning", "blocker"] = "info"
    field: str = ""
    accepted: str = ""
    current: str = ""
    summary: str = ""


class ResumeHandoffDiffReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["no_baseline", "stable", "changed", "blocked"] = "no_baseline"
    ready_to_continue: bool = True
    latest_accepted_event_id: int = 0
    latest_accepted_at: str = ""
    latest_accepted_source: str = ""
    changed_count: int = 0
    blocker_count: int = 0
    warning_count: int = 0
    summary: str = ""
    recommended_action: str = ""
    changes: list[ResumeHandoffDiffChange] = Field(default_factory=list)

class SelfScaffoldChangeRecord(BaseModel):
    id: str = ""
    kind: Literal["task_graph", "action_context", "tool_posture", "model_guard", "edit_evidence", "goal_evolution", "checkpoint", "event"] = "event"
    status: Literal["observed", "active", "needs_review"] = "observed"
    source: str = ""
    structure_ref: str = ""
    summary: str = ""
    intent: str = ""
    reversible: bool = True
    reverse_hint: str = ""
    evidence: list[str] = Field(default_factory=list)
    event_id: int = 0
    created_at: str = ""


class SelfScaffoldReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["empty", "observed", "needs_review"] = "empty"
    change_count: int = 0
    task_graph_count: int = 0
    action_context_count: int = 0
    tool_posture_count: int = 0
    guard_count: int = 0
    reversible_count: int = 0
    review_count: int = 0
    reviewed_change_count: int = 0
    latest_reviewed_at: str = ""
    latest_review_event_id: int = 0
    latest_reviewed_change_ids: list[str] = Field(default_factory=list)
    latest_change: str = ""
    summary: str = "No self-scaffold change intent recorded."
    recommended_action: str = ""
    changes: list[SelfScaffoldChangeRecord] = Field(default_factory=list)


class SelfScaffoldReviewRecord(BaseModel):
    event_id: int = 0
    timestamp: str = ""
    status: Literal["accepted", "partial", "noop"] = "noop"
    change_count: int = 0
    guard_count: int = 0
    reviewed_change_count: int = 0
    reviewed_change_ids: list[str] = Field(default_factory=list)
    remaining_goal_review: bool = False
    action_reason: str = ""
    action_summary: str = ""
    summary: str = ""


class SelfScaffoldReviewReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["none", "reviewed", "needs_goal_review"] = "none"
    total_count: int = 0
    accepted_count: int = 0
    partial_count: int = 0
    noop_count: int = 0
    reviewed_change_count: int = 0
    remaining_goal_review_count: int = 0
    latest_event_id: int = 0
    latest_reviewed_change_ids: list[str] = Field(default_factory=list)
    summary: str = "No self-scaffold review outcomes recorded."
    recommended_action: str = ""
    entries: list[SelfScaffoldReviewRecord] = Field(default_factory=list)


class SelfScaffoldRollbackIntentRecord(BaseModel):
    id: str = ""
    source_review_event_id: int = 0
    reviewed_change_id: str = ""
    change_kind: str = ""
    action_kind: Literal["steer", "patch_rollback", "patch_review", "handoff_refresh", "goal_review"] = "steer"
    status: Literal["suggested", "needs_approval", "resolved", "stale"] = "suggested"
    proposed_tool: str = ""
    requires_approval: bool = False
    mutation_automatic: bool = False
    patch_id: str = ""
    backup_id: str = ""
    rollback_manifest_path: str = ""
    files: list[str] = Field(default_factory=list)
    reverse_hint: str = ""
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)


class SelfScaffoldRollbackIntentReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["none", "available", "needs_approval", "resolved"] = "none"
    intent_count: int = 0
    patch_rollback_count: int = 0
    steering_count: int = 0
    latest_review_event_id: int = 0
    summary: str = "No accepted self-scaffold reverse hints have produced rollback or steering intent yet."
    recommended_action: str = "Continue; use self-scaffold reverse hints if accepted guard posture proves wrong."
    entries: list[SelfScaffoldRollbackIntentRecord] = Field(default_factory=list)

class ActionContextPack(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    milestone: str = ""
    current_task_id: str = ""
    current_task_title: str = ""
    task_transition_ledger: list[str] = Field(default_factory=list)
    model_guard_ledger: list[str] = Field(default_factory=list)
    edit_evidence_ledger: list[str] = Field(default_factory=list)
    desktop_supervision_ledger: list[str] = Field(default_factory=list)
    action_readiness_status: str = ""
    selected_tool: str = ""
    selected_label: str = ""
    selected_action: str = ""
    selected_reason: str = ""
    selected_command_hint: str = ""
    selected_criterion: str = ""
    source_evidence_summary: str = ""
    missing_source_labels: list[str] = Field(default_factory=list)
    latest_source_evidence: str = ""
    readiness_source_ref_status: str = ""
    readiness_source_ref_action: str = ""
    readiness_source_ref_missing_evidence_labels: list[str] = Field(default_factory=list)
    readiness_source_ref_missing_proof_labels: list[str] = Field(default_factory=list)
    readiness_source_ref_source_labels: list[str] = Field(default_factory=list)
    readiness_source_ref_proof_labels: list[str] = Field(default_factory=list)
    recent_verified_commands: list[str] = Field(default_factory=list)
    recent_verified_files: list[str] = Field(default_factory=list)
    recent_successes: list[str] = Field(default_factory=list)
    failure_ledger: list[str] = Field(default_factory=list)
    resolved_failure_ledger: list[str] = Field(default_factory=list)
    promotion_repair_hints: list[str] = Field(default_factory=list)
    recovery_hint: str = ""
    context_budget: str = ""
    compact_prompt: str = ""
class RunHealthSignal(BaseModel):
    id: str
    severity: Literal["info", "warning", "critical"] = "info"
    summary: str
    evidence: list[str] = Field(default_factory=list)


class RunHealthReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    score: int = 0
    level: Literal["healthy", "watch", "stuck", "blocked"] = "healthy"
    recommended_action: Literal["continue", "verify", "recover", "pause", "wait_approval", "ask_user"] = "continue"
    summary: str = ""
    signals: list[RunHealthSignal] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class CheckpointQualityIssue(BaseModel):
    id: str = ""
    severity: Literal["warning", "blocker"] = "warning"
    summary: str = ""
    evidence: str = ""
    recommended_action: str = ""


class CheckpointQualityReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["unknown", "ready", "needs_checkpoint", "blocked"] = "unknown"
    run_note_present: bool = False
    run_note_path: str = ""
    run_note_chars: int = 0
    has_checkpoint_heading: bool = False
    has_active_goal: bool = False
    has_current_step: bool = False
    has_next_action: bool = False
    has_resume_prompt: bool = False
    has_no_raw_logs_instruction: bool = False
    expected_report_integrity_refresh: bool = False
    has_report_integrity_refresh: bool = False
    expected_refresh_event_id: int = 0
    expected_refresh_reason: str = ""
    issue_count: int = 0
    blocker_count: int = 0
    warning_count: int = 0
    summary: str = ""
    recommended_action: str = ""
    issues: list[CheckpointQualityIssue] = Field(default_factory=list)


class CheckpointQualityResumeRecord(BaseModel):
    repair_event_id: int = 0
    repair_completed_event_id: int = 0
    repair_timestamp: str = ""
    repair_reason: str = ""
    repair_ui_target: str = ""
    repair_action: str = ""
    resume_event_id: int = 0
    resume_timestamp: str = ""
    resume_source: str = ""
    resume_accepted: bool | None = None
    resume_policy_action: str = ""
    resume_reason: str = ""
    checkpoint_quality_status: str = ""
    checkpoint_quality_ready: bool = False
    summary: str = ""


class CheckpointQualityResumeReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["none", "awaiting_resume", "resumed", "blocked"] = "none"
    repair_count: int = 0
    resumed_after_repair_count: int = 0
    blocked_after_repair_count: int = 0
    awaiting_resume_count: int = 0
    latest: CheckpointQualityResumeRecord = Field(default_factory=CheckpointQualityResumeRecord)
    summary: str = ""
    recommended_action: str = ""
    entries: list[CheckpointQualityResumeRecord] = Field(default_factory=list)


class OrnithLaunchChecklistItem(BaseModel):
    id: str
    category: str = ""
    status: Literal["pass", "warn", "block"] = "pass"
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    next_action: str = ""


class OrnithLaunchChecklistReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    mode: Literal["launch", "resume"] = "launch"
    status: Literal["ready", "attention", "blocked"] = "attention"
    ready_to_start: bool = False
    ready_to_resume: bool = False
    summary: str = ""
    model_profile_id: str = ""
    model_name: str = ""
    tool_profile: str = ""
    web_enabled: bool = False
    browser_enabled: bool = False
    desktop_enabled: bool = False
    context_pressure: str = ""
    context_snapshot: ContextSnapshot = Field(default_factory=ContextSnapshot)
    resume_prompt_quality: ResumePromptQualityReport = Field(default_factory=ResumePromptQualityReport)
    resume_handoff_diff: ResumeHandoffDiffReport = Field(default_factory=ResumeHandoffDiffReport)
    checkpoint_quality: CheckpointQualityReport = Field(default_factory=CheckpointQualityReport)
    context_tokens: int = 0
    context_target_tokens: int = 0
    pending_approval_count: int = 0
    readiness_smoke_status: str = ""
    dispatch_restart_smoke_status: str = ""
    run_health_level: str = ""
    run_health_action: str = ""
    supervisor_attention_count: int = 0
    items: list[OrnithLaunchChecklistItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)

class PolicySimulationReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    current_status: str = ""
    current_milestone: str = ""
    predicted_status: str = ""
    predicted_milestone: str = ""
    policy_action: Literal["continue", "verify", "recover", "pause", "wait_approval", "ask_user", "complete"] = "continue"
    safe_to_resume: bool = True
    auto_resume_eligible: bool = True
    summary: str = ""
    reason: str = ""
    next_action: str = ""
    recommended_tool: str = ""
    recommended_label: str = ""
    effects: list[str] = Field(default_factory=list)
    blocking_signals: list[str] = Field(default_factory=list)
    run_health: RunHealthReport = Field(default_factory=RunHealthReport)
    completion_audit: CompletionAuditReport = Field(default_factory=lambda: CompletionAuditReport(run_id=""))


class ResumeDecisionRecord(BaseModel):
    id: int = 0
    timestamp: str = ""
    kind: str = ""
    source: str = ""
    accepted: bool = False
    reason: str = ""
    policy_action: str = ""
    predicted_status: str = ""
    predicted_milestone: str = ""
    safe_to_resume: bool = False
    auto_resume_eligible: bool = False
    recommended_tool: str = ""
    recommended_label: str = ""
    health_level: str = ""
    health_action: str = ""
    health_score: int = 0
    summary: str = ""


class ResumeDecisionReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    decision_count: int = 0
    accepted_count: int = 0
    blocked_count: int = 0
    latest_decision: ResumeDecisionRecord = Field(default_factory=ResumeDecisionRecord)
    latest_accepted: ResumeDecisionRecord = Field(default_factory=ResumeDecisionRecord)
    latest_blocked: ResumeDecisionRecord = Field(default_factory=ResumeDecisionRecord)
    current_policy_action: str = ""
    current_predicted_status: str = ""
    current_predicted_milestone: str = ""
    current_recommended_tool: str = ""
    current_recommended_label: str = ""
    current_matches_last_accepted: bool = False
    comparison_summary: str = ""
    recommended_action: str = ""
    decisions: list[ResumeDecisionRecord] = Field(default_factory=list)




class ActionReadinessIssue(BaseModel):
    id: str
    severity: Literal["info", "warning", "blocker"] = "info"
    summary: str
    evidence: list[str] = Field(default_factory=list)


class ActionReadinessReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["ready", "needs_proof", "needs_replan", "reorient", "waiting_approval", "recover", "blocked"] = "ready"
    ready_to_act: bool = True
    summary: str = ""
    recommended_action: str = ""
    suggested_tool: str = ""
    suggested_label: str = ""
    milestone: str = ""
    current_task_id: str = ""
    current_task_status: str = ""
    active_tool: str = ""
    run_health_level: str = ""
    run_health_action: str = ""
    resume_decision_matches: bool = False
    latest_resume_decision_id: int = 0
    act_preflight_checked_decision_id: int = 0
    issues: list[ActionReadinessIssue] = Field(default_factory=list)


class ActionReadinessDecisionRecord(BaseModel):
    id: int = 0
    timestamp: str = ""
    kind: str = ""
    status: Literal[
        "selected",
        "executed",
        "satisfied",
        "failed",
        "waiting_approval",
        "blocked",
        "replanned",
        "reoriented",
        "recover",
    ] = "selected"
    readiness_status: str = ""
    ready_to_act: bool = False
    source: str = ""
    selected_tool: str = ""
    suggested_tool: str = ""
    suggested_label: str = ""
    recommendation_trace_id: str = ""
    recommendation_id: str = ""
    criterion_id: str = ""
    criterion: str = ""
    label: str = ""
    result_ok: bool | None = None
    result_summary: str = ""
    evidence_status: str = ""
    summary: str = ""
    reason: str = ""


class ActionReadinessDecisionReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    decision_count: int = 0
    selected_count: int = 0
    satisfied_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    policy_gate_count: int = 0
    harness_selected_count: int = 0
    model_selected_count: int = 0
    fallback_selected_count: int = 0
    latest_decision: ActionReadinessDecisionRecord = Field(default_factory=ActionReadinessDecisionRecord)
    latest_tool_decision: ActionReadinessDecisionRecord = Field(default_factory=ActionReadinessDecisionRecord)
    latest_policy_decision: ActionReadinessDecisionRecord = Field(default_factory=ActionReadinessDecisionRecord)
    summary: str = ""
    recommended_action: str = ""
    decisions: list[ActionReadinessDecisionRecord] = Field(default_factory=list)


class AutonomyDecisionRecord(BaseModel):
    id: int = 0
    timestamp: str = ""
    kind: str = ""
    milestone: str = ""
    decision: Literal[
        "continue",
        "verify",
        "recover",
        "pause",
        "wait_approval",
        "ask_user",
        "complete",
        "reorient",
        "replan",
        "blocked",
        "resume",
        "wait_goal",
    ] = "continue"
    source: str = ""
    policy_action: str = ""
    predicted_status: str = ""
    predicted_milestone: str = ""
    health_level: str = ""
    health_action: str = ""
    health_score: int = 0
    safe_to_resume: bool = False
    auto_resume_eligible: bool = False
    reason: str = ""
    next_action: str = ""
    blocking_signals: list[str] = Field(default_factory=list)
    summary: str = ""


class AutonomyDecisionReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    decision_count: int = 0
    continue_count: int = 0
    pause_count: int = 0
    recover_count: int = 0
    wait_count: int = 0
    complete_count: int = 0
    blocked_count: int = 0
    latest_decision: AutonomyDecisionRecord = Field(default_factory=AutonomyDecisionRecord)
    latest_stop_decision: AutonomyDecisionRecord = Field(default_factory=AutonomyDecisionRecord)
    latest_continue_decision: AutonomyDecisionRecord = Field(default_factory=AutonomyDecisionRecord)
    current_policy_action: str = ""
    current_safe_to_resume: bool = False
    current_next_action: str = ""
    summary: str = ""
    recommended_action: str = ""
    decisions: list[AutonomyDecisionRecord] = Field(default_factory=list)


class RunProgressReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["on_track", "needs_verification", "needs_recovery", "waiting", "near_completion", "blocked"] = "on_track"
    summary: str = ""
    can_keep_running: bool = True
    should_pause: bool = False
    near_completion: bool = False
    task_total: int = 0
    task_completed: int = 0
    task_blocked: int = 0
    task_failed: int = 0
    task_progress_percent: int = 0
    acceptance_total: int = 0
    acceptance_verified: int = 0
    acceptance_open: int = 0
    acceptance_failed: int = 0
    acceptance_blocked: int = 0
    acceptance_coverage_percent: int = 0
    workspace_change_count: int = 0
    pending_patch_count: int = 0
    pending_approval_count: int = 0
    latest_autonomy_decision: str = ""
    latest_verification_outcome: str = ""
    current_policy_action: str = ""
    next_actions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ReportIntegrityCheck(BaseModel):
    section: str
    status: Literal["ok", "missing", "stale", "mismatch"] = "ok"
    summary: str = ""
    expected: str = ""
    actual: str = ""
    generated_at: str = ""


class ReportIntegrityReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["ok", "needs_refresh"] = "ok"
    check_count: int = 0
    ok_count: int = 0
    missing_count: int = 0
    stale_count: int = 0
    mismatch_count: int = 0
    latest_event_id: int = 0
    latest_event_timestamp: str = ""
    summary: str = ""
    recommended_action: str = ""
    checks: list[ReportIntegrityCheck] = Field(default_factory=list)


class ReportIntegrityRefreshRecord(BaseModel):
    event_id: int = 0
    timestamp: str = ""
    report_status: str = ""
    previous_report_status: str = ""
    reason_count: int = 0
    reasons: list[str] = Field(default_factory=list)
    preflight_event_id: int = 0
    preflight_event_kind: str = ""
    preflight_accepted: bool | None = None
    preflight_reason: str = ""


class ObjectiveReadinessProof(BaseModel):
    tool_kind: str = ""
    evidence_label: str = ""
    strategy: str = ""
    action: str = ""
    command_hint: str = ""
    success_signal: str = ""
    requires_approval: bool = False


class ObjectiveReadinessProofOutcome(BaseModel):
    id: str = ""
    item_id: str = ""
    tool: str = ""
    evidence_label: str = ""
    strategy: str = ""
    outcome: Literal["verified", "partial", "failed", "waiting_approval"] = "partial"
    ok: bool = False
    summary: str = ""
    proof_action: str = ""
    created_at: str = ""


class ObjectiveReadinessProofPreference(BaseModel):
    item_id: str = ""
    tool_kind: str = ""
    evidence_label: str = ""
    strategy: str = ""
    action: str = ""
    command_hint: str = ""
    reason: str = ""
    confidence: Literal["low", "medium", "high"] = "low"
    verified_count: int = 0
    partial_count: int = 0
    failed_count: int = 0
    last_outcome: str = ""


class ObjectiveReadinessItem(BaseModel):
    id: str
    requirement: str
    status: Literal["verified", "partial", "missing", "failed"] = "missing"
    evidence: list[str] = Field(default_factory=list)
    next_action: str = ""
    proof: ObjectiveReadinessProof = Field(default_factory=ObjectiveReadinessProof)
    latest_outcome: ObjectiveReadinessProofOutcome = Field(default_factory=ObjectiveReadinessProofOutcome)
    preferred_proof: ObjectiveReadinessProofPreference = Field(default_factory=ObjectiveReadinessProofPreference)


class ObjectiveReadinessReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["ready", "partial", "not_ready"] = "partial"
    verified_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    failed_count: int = 0
    summary: str = ""
    recommended_action: str = ""
    next_actions: list[str] = Field(default_factory=list)
    proof_preferences: list[ObjectiveReadinessProofPreference] = Field(default_factory=list)
    items: list[ObjectiveReadinessItem] = Field(default_factory=list)


class ReadinessCompletionCheck(BaseModel):
    id: str
    status: Literal["pass", "warn", "block"] = "pass"
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    next_action: str = ""


class ReadinessCompletionReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["ready", "needs_more_evidence", "blocked", "not_applicable"] = "needs_more_evidence"
    can_claim_milestone: bool = False
    confidence: Literal["low", "medium", "high"] = "low"
    summary: str = ""
    objective_status: str = ""
    run_progress_status: str = ""
    completion_status: str = ""
    rehearsal_ledger_status: str = ""
    rehearsal_latest_run_id: str = ""
    rehearsal_passed_count: int = 0
    rehearsal_failed_count: int = 0
    dispatch_restart_smoke_ledger_status: str = ""
    dispatch_restart_smoke_latest_run_id: str = ""
    dispatch_restart_smoke_passed_count: int = 0
    dispatch_restart_smoke_failed_count: int = 0
    ornith_preflight_warning_count: int = 0
    ornith_preflight_block_count: int = 0
    ornith_preflight_reorient_count: int = 0
    self_scaffold_status: str = ""
    self_scaffold_pending_review_count: int = 0
    self_scaffold_review_count: int = 0
    self_scaffold_reviewed_change_count: int = 0
    self_scaffold_latest_review_event_id: int = 0
    source_visible_required_label_count: int = 0
    source_visible_matched_label_count: int = 0
    readiness_proof_source_ref_count: int = 0
    readiness_proof_source_ref_labels: list[str] = Field(default_factory=list)
    source_visible_missing_ref_labels: list[str] = Field(default_factory=list)
    required_verified_count: int = 9
    verified_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    failed_count: int = 0
    proof_preference_count: int = 0
    open_preference_count: int = 0
    blocking_count: int = 0
    warning_count: int = 0
    checks: list[ReadinessCompletionCheck] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class ReadinessRehearsalStep(BaseModel):
    id: str
    status: Literal["pending", "passed", "failed", "skipped"] = "pending"
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    event_id: int = 0
    event_kind: str = ""
    run_status: str = ""
    milestone: str = ""


class ReadinessRehearsalReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["not_run", "running", "passed", "failed"] = "not_run"
    scenario: str = "readiness_claim_restart"
    summary: str = ""
    rehearsal_workspace: str = ""
    restart_simulated: bool = False
    refused_event_id: int = 0
    accepted_event_id: int = 0
    completed_event_id: int = 0
    self_scaffold_reviewed: bool = False
    self_scaffold_review_event_id: int = 0
    self_scaffold_reviewed_change_count: int = 0
    post_review_handoff_goal_preserved: bool = False
    post_review_handoff_next_action_preserved: bool = False
    post_review_resume_prompt_goal_preserved: bool = False
    post_review_resume_prompt_next_action_preserved: bool = False
    compact_context_tokens: int = 0
    compact_context_sections: list[str] = Field(default_factory=list)
    replay_attached: bool = False
    handoff_attached: bool = False
    next_action: str = ""
    steps: list[ReadinessRehearsalStep] = Field(default_factory=list)


class ReadinessRehearsalLedgerEntry(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["running", "passed", "failed"] = "running"
    scenario: str = "readiness_claim_restart"
    summary: str = ""
    rehearsal_workspace: str = ""
    restart_simulated: bool = False
    replay_attached: bool = False
    handoff_attached: bool = False
    compact_context_tokens: int = 0
    refused_event_id: int = 0
    accepted_event_id: int = 0
    completed_event_id: int = 0
    self_scaffold_reviewed: bool = False
    self_scaffold_review_event_id: int = 0
    self_scaffold_reviewed_change_count: int = 0
    post_review_handoff_goal_preserved: bool = False
    post_review_handoff_next_action_preserved: bool = False
    post_review_resume_prompt_goal_preserved: bool = False
    post_review_resume_prompt_next_action_preserved: bool = False
    step_count: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    next_action: str = ""


class ReadinessRehearsalLedgerReport(BaseModel):
    generated_at: str = ""
    status: Literal["never_run", "running", "passed", "failed", "mixed"] = "never_run"
    summary: str = "No readiness rehearsal has run yet."
    total_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    running_count: int = 0
    latest: ReadinessRehearsalLedgerEntry | None = None
    entries: list[ReadinessRehearsalLedgerEntry] = Field(default_factory=list)
    next_action: str = "Run the readiness-claim rehearsal smoke before trusting a milestone claim."


class OperatorDispatchLedgerEntry(BaseModel):
    event_id: int
    run_id: str
    timestamp: str
    kind: str
    status: Literal["confirmation_required", "reviewed", "dispatched", "blocked"]
    decision: str = ""
    confirmed: bool = False
    action_reason: str = ""
    action_title: str = ""
    action_summary: str = ""
    ui_target: str = ""
    approval_id: int = 0
    approval_kind: str = ""
    endpoint: str = ""
    details: list[str] = Field(default_factory=list)
    message: str = ""
    note_supplied: bool = False


class OperatorApprovalHistory(BaseModel):
    approval_id: int = 0
    run_id: str = ""
    event_count: int = 0
    reviewed_count: int = 0
    confirmation_required_count: int = 0
    dispatched_count: int = 0
    blocked_count: int = 0
    latest_event_id: int = 0
    latest_timestamp: str = ""
    latest_status: str = ""
    latest_decision: str = ""
    action_reason: str = ""
    action_title: str = ""
    action_summary: str = ""
    approval_kind: str = ""
    ui_target: str = ""
    sequence: list[str] = Field(default_factory=list)


class OperatorDispatchLedgerReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    total_count: int = 0
    dispatched_count: int = 0
    confirmation_required_count: int = 0
    reviewed_count: int = 0
    blocked_count: int = 0
    latest_action: str = ""
    summary: str = ""
    recommended_action: str = ""
    approval_history_count: int = 0
    unresolved_approval_history_count: int = 0
    promotion_route_count: int = 0
    promotion_approval_route_count: int = 0
    promotion_approval_history_count: int = 0
    unresolved_promotion_approval_history_count: int = 0
    approval_histories: list[OperatorApprovalHistory] = Field(default_factory=list)
    unresolved_approval_histories: list[OperatorApprovalHistory] = Field(default_factory=list)
    promotion_approval_histories: list[OperatorApprovalHistory] = Field(default_factory=list)
    unresolved_promotion_approval_histories: list[OperatorApprovalHistory] = Field(default_factory=list)
    promotion_routes: list[OperatorDispatchLedgerEntry] = Field(default_factory=list)
    entries: list[OperatorDispatchLedgerEntry] = Field(default_factory=list)


class OrnithPreflightActionLedgerEntry(BaseModel):
    event_id: int = 0
    run_id: str = ""
    timestamp: str = ""
    kind: str = ""
    status: Literal["completed", "dispatched"] = "completed"
    item_id: str = ""
    action_reason: str = ""
    action_summary: str = ""
    ui_target: str = ""
    context_pressure: str = ""
    context_tokens: int = 0
    context_target_tokens: int = 0
    message: str = ""
    details: list[str] = Field(default_factory=list)


class OrnithPreflightActionLedgerReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    total_count: int = 0
    completed_count: int = 0
    dispatched_count: int = 0
    context_checkpoint_count: int = 0
    handoff_refresh_count: int = 0
    smoke_count: int = 0
    latest_action: str = ""
    summary: str = ""
    recommended_action: str = ""
    entries: list[OrnithPreflightActionLedgerEntry] = Field(default_factory=list)

class OrnithPreflightWarningRecord(BaseModel):
    event_id: int = 0
    timestamp: str = ""
    source: str = "checklist"
    item_id: str = ""
    status: Literal["warn", "block"] = "warn"
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    next_action: str = ""
    message: str = ""


class OrnithPreflightWarningReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    total_count: int = 0
    warning_count: int = 0
    block_count: int = 0
    action_context_reorient_count: int = 0
    latest_reorient_event_id: int = 0
    latest_warning: str = ""
    summary: str = "No Ornith preflight warnings recorded."
    recommended_action: str = ""
    entries: list[OrnithPreflightWarningRecord] = Field(default_factory=list)

class ReadinessProofSourceRef(BaseModel):
    id: str = ""
    kind: Literal["web_source", "browser_snapshot", "desktop_snapshot"] = "web_source"
    evidence_label: str = ""
    title: str = ""
    target: str = ""
    linked_criteria: list[str] = Field(default_factory=list)
    citation: str = ""


class ReadinessProofHistoryRecord(BaseModel):
    event_id: int = 0
    timestamp: str = ""
    source: Literal["rehearsal_step", "operator_event", "claim_event", "report"] = "report"
    proof_type: Literal["self_scaffold_review", "post_review_handoff", "resume_prompt_preservation", "readiness_claim", "readiness_rehearsal"] = "readiness_rehearsal"
    status: Literal["pass", "warn", "block", "info"] = "info"
    step_id: str = ""
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    run_status: str = ""
    milestone: str = ""
    source_refs: list[ReadinessProofSourceRef] = Field(default_factory=list)


class ReadinessProofHistoryReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["empty", "partial", "complete", "needs_attention"] = "empty"
    total_count: int = 0
    self_scaffold_review_count: int = 0
    post_review_handoff_count: int = 0
    resume_prompt_preservation_count: int = 0
    readiness_claim_count: int = 0
    blocking_count: int = 0
    source_evidence_ref_count: int = 0
    source_evidence_labels: list[str] = Field(default_factory=list)
    source_evidence_summary: str = ""
    latest_event_id: int = 0
    latest_summary: str = ""
    summary: str = "No readiness proof history recorded."
    recommended_action: str = "Run the readiness rehearsal before trusting long-run readiness proof."
    entries: list[ReadinessProofHistoryRecord] = Field(default_factory=list)

class ReadinessSourceRefLabelPreview(BaseModel):
    label: str = ""
    source_visible: bool = False
    acceptance_required: bool = False
    acceptance_matched: bool = False
    present_in_source_evidence: bool = False
    present_in_proof_history: bool = False
    missing_from_source_evidence: bool = False
    missing_from_proof_history: bool = False
    source_evidence_count: int = 0
    proof_ref_count: int = 0
    linked_criteria: list[str] = Field(default_factory=list)
    source_evidence_titles: list[str] = Field(default_factory=list)
    proof_ref_titles: list[str] = Field(default_factory=list)


class ReadinessSourceRefPreviewReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["not_applicable", "ready", "missing_source_evidence", "missing_proof_refs"] = "not_applicable"
    summary: str = "No source-visible readiness refs required."
    recommended_action: str = ""
    readiness_completion_status: str = ""
    readiness_proof_history_status: str = ""
    source_visible_labels: list[str] = Field(default_factory=list)
    acceptance_required_labels: list[str] = Field(default_factory=list)
    acceptance_matched_labels: list[str] = Field(default_factory=list)
    source_evidence_labels: list[str] = Field(default_factory=list)
    proof_ref_labels: list[str] = Field(default_factory=list)
    missing_source_evidence_labels: list[str] = Field(default_factory=list)
    missing_proof_ref_labels: list[str] = Field(default_factory=list)
    source_evidence_entry_count: int = 0
    proof_ref_count: int = 0
    labels: list[ReadinessSourceRefLabelPreview] = Field(default_factory=list)
    source_evidence_entries: list[SourceEvidencePreviewEntry] = Field(default_factory=list)
    proof_refs: list[ReadinessProofSourceRef] = Field(default_factory=list)

class OperatorDispatchRestartSmokeReport(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["not_run", "running", "passed", "failed"] = "not_run"
    scenario: str = "operator_dispatch_restart"
    summary: str = ""
    restart_simulated: bool = False
    dispatch_event_id: int = 0
    compact_context_tokens: int = 0
    compact_context_sections: list[str] = Field(default_factory=list)
    ledger_attached: bool = False
    handoff_attached: bool = False
    replay_attached: bool = False
    context_attached: bool = False
    next_action: str = ""
    steps: list[ReadinessRehearsalStep] = Field(default_factory=list)


class OperatorDispatchRestartSmokeLedgerEntry(BaseModel):
    run_id: str = ""
    generated_at: str = ""
    status: Literal["running", "passed", "failed"] = "running"
    scenario: str = "operator_dispatch_restart"
    summary: str = ""
    restart_simulated: bool = False
    dispatch_event_id: int = 0
    compact_context_tokens: int = 0
    ledger_attached: bool = False
    handoff_attached: bool = False
    replay_attached: bool = False
    context_attached: bool = False
    step_count: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    next_action: str = ""


class OperatorDispatchRestartSmokeLedgerReport(BaseModel):
    generated_at: str = ""
    status: Literal["never_run", "running", "passed", "failed", "mixed"] = "never_run"
    summary: str = "No operator-dispatch restart smoke has run yet."
    total_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    running_count: int = 0
    latest: OperatorDispatchRestartSmokeLedgerEntry | None = None
    entries: list[OperatorDispatchRestartSmokeLedgerEntry] = Field(default_factory=list)
    next_action: str = "Run the operator-dispatch restart smoke before trusting dispatch handoff evidence after restart."


class ApprovalReviewSummary(BaseModel):
    id: int
    status: Literal["pending", "approved", "rejected"] = "pending"
    action_kind: str = ""
    summary: str = ""
    reviewed: bool = False
    review_count: int = 0
    latest_reviewed_at: str = ""
    latest_review_event_id: int = 0
    high_risk: bool = False
    files: list[str] = Field(default_factory=list)


class HandoffBundle(BaseModel):
    original_goal: str = ""
    current_objective: str = ""
    goal_evolution: GoalEvolutionReport = Field(default_factory=GoalEvolutionReport)
    git_checkpoint: GitCheckpointReport = Field(default_factory=GitCheckpointReport)
    plan: list[str] = Field(default_factory=list)
    completed_work: list[str] = Field(default_factory=list)
    next_action: str = ""
    files_touched: list[str] = Field(default_factory=list)
    commands_and_tests: list[str] = Field(default_factory=list)
    web_sources: list[WebSource] = Field(default_factory=list)
    desktop_state: list[DesktopSnapshot] = Field(default_factory=list)
    source_evidence: SourceEvidencePreviewReport = Field(default_factory=SourceEvidencePreviewReport)
    readiness_source_ref_preview: ReadinessSourceRefPreviewReport = Field(
        default_factory=ReadinessSourceRefPreviewReport
    )
    desktop_effect_proof: DesktopEffectProofReport = Field(default_factory=DesktopEffectProofReport)
    desktop_effect_proof_repairs: DesktopEffectProofRepairReport = Field(default_factory=DesktopEffectProofRepairReport)
    action_context: ActionContextPack = Field(default_factory=ActionContextPack)
    self_scaffold: SelfScaffoldReport = Field(default_factory=SelfScaffoldReport)
    self_scaffold_reviews: SelfScaffoldReviewReport = Field(default_factory=SelfScaffoldReviewReport)
    self_scaffold_rollback_intents: SelfScaffoldRollbackIntentReport = Field(default_factory=SelfScaffoldRollbackIntentReport)
    context_snapshot: ContextSnapshot = Field(default_factory=ContextSnapshot)
    resume_prompt_quality: ResumePromptQualityReport = Field(default_factory=ResumePromptQualityReport)
    promotion_audit: PromotionAuditReport = Field(default_factory=PromotionAuditReport)
    promotion_verification: PromotionVerificationReport = Field(default_factory=PromotionVerificationReport)
    promotion_repair: PromotionRepairReport = Field(default_factory=PromotionRepairReport)
    current_task_id: str = ""
    task_graph: list[TaskNode] = Field(default_factory=list)
    repo_map_summary: str = ""
    workspace_summary: str = ""
    workspace_diff_summary: str = ""
    workspace_promotions: list[WorkspacePromotion] = Field(default_factory=list)
    patch_proposals: list[PatchProposal] = Field(default_factory=list)
    patch_applications: list[PatchApplication] = Field(default_factory=list)
    failure_records: list[FailureRecord] = Field(default_factory=list)
    recovery_summary: str = ""
    recovery_steps: list[str] = Field(default_factory=list)
    model_profile_adaptation_reviews: list[ModelProfileAdaptationReviewSummary] = Field(default_factory=list)
    unresolved_blockers: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    approval_reviews: list[ApprovalReviewSummary] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    acceptance_evidence: list[AcceptanceCriterionEvidence] = Field(default_factory=list)
    acceptance_recommendations: list[AcceptanceEvidenceRecommendation] = Field(default_factory=list)
    acceptance_recommendation_traces: list[AcceptanceRecommendationTrace] = Field(default_factory=list)
    run_health: RunHealthReport = Field(default_factory=RunHealthReport)
    completion_audit: CompletionAuditReport = Field(default_factory=lambda: CompletionAuditReport(run_id=""))
    policy_simulation: PolicySimulationReport = Field(default_factory=PolicySimulationReport)
    resume_decisions: ResumeDecisionReport = Field(default_factory=ResumeDecisionReport)
    resume_handoff_diff: ResumeHandoffDiffReport = Field(default_factory=ResumeHandoffDiffReport)
    run_progress: RunProgressReport = Field(default_factory=RunProgressReport)
    report_integrity: ReportIntegrityReport = Field(default_factory=ReportIntegrityReport)
    report_integrity_refreshes: list[ReportIntegrityRefreshRecord] = Field(default_factory=list)
    checkpoint_quality: CheckpointQualityReport = Field(default_factory=CheckpointQualityReport)
    checkpoint_quality_resumes: CheckpointQualityResumeReport = Field(default_factory=CheckpointQualityResumeReport)
    objective_readiness: ObjectiveReadinessReport = Field(default_factory=ObjectiveReadinessReport)
    objective_readiness_proof_outcomes: list[ObjectiveReadinessProofOutcome] = Field(default_factory=list)
    readiness_completion: ReadinessCompletionReport = Field(default_factory=ReadinessCompletionReport)
    readiness_rehearsal: ReadinessRehearsalReport = Field(default_factory=ReadinessRehearsalReport)
    action_readiness: ActionReadinessReport = Field(default_factory=ActionReadinessReport)
    action_readiness_decisions: ActionReadinessDecisionReport = Field(default_factory=ActionReadinessDecisionReport)
    autonomy_decisions: AutonomyDecisionReport = Field(default_factory=AutonomyDecisionReport)
    recovery_decisions: RecoveryDecisionReport = Field(default_factory=RecoveryDecisionReport)
    verification_outcomes: VerificationOutcomeReport = Field(default_factory=VerificationOutcomeReport)
    post_action_retries: PostActionRetryReport = Field(default_factory=PostActionRetryReport)
    operator_dispatches: OperatorDispatchLedgerReport = Field(default_factory=OperatorDispatchLedgerReport)
    operator_dispatch_restart_smoke: OperatorDispatchRestartSmokeReport = Field(default_factory=OperatorDispatchRestartSmokeReport)
    ornith_preflight: OrnithLaunchChecklistReport = Field(default_factory=OrnithLaunchChecklistReport)
    ornith_preflight_actions: OrnithPreflightActionLedgerReport = Field(default_factory=OrnithPreflightActionLedgerReport)
    ornith_preflight_warnings: OrnithPreflightWarningReport = Field(default_factory=OrnithPreflightWarningReport)
    readiness_proof_history: ReadinessProofHistoryReport = Field(default_factory=ReadinessProofHistoryReport)
    resume_prompt: str = ""


class ReplayEvent(BaseModel):
    id: int
    timestamp: str
    kind: str
    message: str
    ok: bool | None = None
    data_keys: list[str] = Field(default_factory=list)


class ReplayApproval(BaseModel):
    id: int
    status: str
    action_kind: str
    reason: str
    created_at: str
    resolved_at: str | None = None
    reviewed: bool = False
    review_count: int = 0
    latest_reviewed_at: str = ""
    latest_review_event_id: int = 0
    preview_summary: str = ""
    preview_files: list[str] = Field(default_factory=list)


class ReplayBundle(BaseModel):
    run_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    workspace_path: str
    original_goal: str
    active_goal: str
    goal_evolution: GoalEvolutionReport = Field(default_factory=GoalEvolutionReport)
    git_checkpoint: GitCheckpointReport = Field(default_factory=GitCheckpointReport)
    milestone: str
    next_action: str
    context_pressure: str
    context_snapshot: ContextSnapshot = Field(default_factory=ContextSnapshot)
    resume_prompt_quality: ResumePromptQualityReport = Field(default_factory=ResumePromptQualityReport)
    resume_handoff_diff: ResumeHandoffDiffReport = Field(default_factory=ResumeHandoffDiffReport)
    promotion_audit: PromotionAuditReport = Field(default_factory=PromotionAuditReport)
    promotion_verification: PromotionVerificationReport = Field(default_factory=PromotionVerificationReport)
    promotion_repair: PromotionRepairReport = Field(default_factory=PromotionRepairReport)
    handoff: HandoffBundle = Field(default_factory=HandoffBundle)
    event_count: int = 0
    approval_count: int = 0
    source_evidence: SourceEvidencePreviewReport = Field(default_factory=SourceEvidencePreviewReport)
    readiness_source_ref_preview: ReadinessSourceRefPreviewReport = Field(
        default_factory=ReadinessSourceRefPreviewReport
    )
    desktop_effect_proof: DesktopEffectProofReport = Field(default_factory=DesktopEffectProofReport)
    desktop_effect_proof_repairs: DesktopEffectProofRepairReport = Field(default_factory=DesktopEffectProofRepairReport)
    action_context: ActionContextPack = Field(default_factory=ActionContextPack)
    self_scaffold: SelfScaffoldReport = Field(default_factory=SelfScaffoldReport)
    self_scaffold_reviews: SelfScaffoldReviewReport = Field(default_factory=SelfScaffoldReviewReport)
    self_scaffold_rollback_intents: SelfScaffoldRollbackIntentReport = Field(default_factory=SelfScaffoldRollbackIntentReport)
    events: list[ReplayEvent] = Field(default_factory=list)
    approvals: list[ReplayApproval] = Field(default_factory=list)
    acceptance_evidence: list[AcceptanceCriterionEvidence] = Field(default_factory=list)
    acceptance_recommendations: list[AcceptanceEvidenceRecommendation] = Field(default_factory=list)
    acceptance_recommendation_traces: list[AcceptanceRecommendationTrace] = Field(default_factory=list)
    run_health: RunHealthReport = Field(default_factory=RunHealthReport)
    completion_audit: CompletionAuditReport = Field(default_factory=lambda: CompletionAuditReport(run_id=""))
    policy_simulation: PolicySimulationReport = Field(default_factory=PolicySimulationReport)
    resume_decisions: ResumeDecisionReport = Field(default_factory=ResumeDecisionReport)
    resume_handoff_diff: ResumeHandoffDiffReport = Field(default_factory=ResumeHandoffDiffReport)
    run_progress: RunProgressReport = Field(default_factory=RunProgressReport)
    report_integrity: ReportIntegrityReport = Field(default_factory=ReportIntegrityReport)
    report_integrity_refreshes: list[ReportIntegrityRefreshRecord] = Field(default_factory=list)
    checkpoint_quality: CheckpointQualityReport = Field(default_factory=CheckpointQualityReport)
    checkpoint_quality_resumes: CheckpointQualityResumeReport = Field(default_factory=CheckpointQualityResumeReport)
    objective_readiness: ObjectiveReadinessReport = Field(default_factory=ObjectiveReadinessReport)
    objective_readiness_proof_outcomes: list[ObjectiveReadinessProofOutcome] = Field(default_factory=list)
    readiness_completion: ReadinessCompletionReport = Field(default_factory=ReadinessCompletionReport)
    readiness_rehearsal: ReadinessRehearsalReport = Field(default_factory=ReadinessRehearsalReport)
    action_readiness: ActionReadinessReport = Field(default_factory=ActionReadinessReport)
    action_readiness_decisions: ActionReadinessDecisionReport = Field(default_factory=ActionReadinessDecisionReport)
    autonomy_decisions: AutonomyDecisionReport = Field(default_factory=AutonomyDecisionReport)
    recovery_decisions: RecoveryDecisionReport = Field(default_factory=RecoveryDecisionReport)
    verification_outcomes: VerificationOutcomeReport = Field(default_factory=VerificationOutcomeReport)
    post_action_retries: PostActionRetryReport = Field(default_factory=PostActionRetryReport)
    operator_dispatches: OperatorDispatchLedgerReport = Field(default_factory=OperatorDispatchLedgerReport)
    operator_dispatch_restart_smoke: OperatorDispatchRestartSmokeReport = Field(default_factory=OperatorDispatchRestartSmokeReport)
    ornith_preflight: OrnithLaunchChecklistReport = Field(default_factory=OrnithLaunchChecklistReport)
    ornith_preflight_actions: OrnithPreflightActionLedgerReport = Field(default_factory=OrnithPreflightActionLedgerReport)
    ornith_preflight_warnings: OrnithPreflightWarningReport = Field(default_factory=OrnithPreflightWarningReport)
    readiness_proof_history: ReadinessProofHistoryReport = Field(default_factory=ReadinessProofHistoryReport)
    task_graph: list[TaskNode] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    model_interactions: list[ModelInteractionRecord] = Field(default_factory=list)
    failure_records: list[FailureRecord] = Field(default_factory=list)
    recovery_plan: RecoveryPlan = Field(default_factory=RecoveryPlan)
    recovery_history: list[RecoveryPlan] = Field(default_factory=list)
    model_profile_adaptation_reviews: list[ModelProfileAdaptationReviewSummary] = Field(default_factory=list)
    run_lease: RunLease = Field(default_factory=RunLease)
    workspace_diff_summary: str = ""
    workspace_promotions: list[WorkspacePromotion] = Field(default_factory=list)
    patch_applications: list[PatchApplication] = Field(default_factory=list)
    markdown: str = ""


class RunState(BaseModel):
    goal: str
    proposed_goal: str | None = None
    goal_revision_reason: str = ""
    goal_evolution: GoalEvolutionReport = Field(default_factory=GoalEvolutionReport)
    git_checkpoint: GitCheckpointReport = Field(default_factory=GitCheckpointReport)
    current_plan: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    next_step: str = ""
    files_touched: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    facts_learned: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    acceptance_evidence: list[AcceptanceCriterionEvidence] = Field(default_factory=list)
    acceptance_recommendations: list[AcceptanceEvidenceRecommendation] = Field(default_factory=list)
    acceptance_recommendation_traces: list[AcceptanceRecommendationTrace] = Field(default_factory=list)
    run_health: RunHealthReport = Field(default_factory=RunHealthReport)
    run_progress: RunProgressReport = Field(default_factory=RunProgressReport)
    report_integrity: ReportIntegrityReport = Field(default_factory=ReportIntegrityReport)
    report_integrity_refreshes: list[ReportIntegrityRefreshRecord] = Field(default_factory=list)
    checkpoint_quality: CheckpointQualityReport = Field(default_factory=CheckpointQualityReport)
    checkpoint_quality_resumes: CheckpointQualityResumeReport = Field(default_factory=CheckpointQualityResumeReport)
    objective_readiness: ObjectiveReadinessReport = Field(default_factory=ObjectiveReadinessReport)
    objective_readiness_proof_outcomes: list[ObjectiveReadinessProofOutcome] = Field(default_factory=list)
    readiness_completion: ReadinessCompletionReport = Field(default_factory=ReadinessCompletionReport)
    readiness_rehearsal: ReadinessRehearsalReport = Field(default_factory=ReadinessRehearsalReport)
    readiness_proof_history: ReadinessProofHistoryReport = Field(default_factory=ReadinessProofHistoryReport)
    action_readiness: ActionReadinessReport = Field(default_factory=ActionReadinessReport)
    action_readiness_decisions: ActionReadinessDecisionReport = Field(default_factory=ActionReadinessDecisionReport)
    autonomy_decisions: AutonomyDecisionReport = Field(default_factory=AutonomyDecisionReport)
    recovery_decisions: RecoveryDecisionReport = Field(default_factory=RecoveryDecisionReport)
    verification_outcomes: VerificationOutcomeReport = Field(default_factory=VerificationOutcomeReport)
    post_action_retries: PostActionRetryReport = Field(default_factory=PostActionRetryReport)
    operator_dispatches: OperatorDispatchLedgerReport = Field(default_factory=OperatorDispatchLedgerReport)
    operator_dispatch_restart_smoke: OperatorDispatchRestartSmokeReport = Field(default_factory=OperatorDispatchRestartSmokeReport)
    ornith_preflight: OrnithLaunchChecklistReport = Field(default_factory=OrnithLaunchChecklistReport)
    ornith_preflight_actions: OrnithPreflightActionLedgerReport = Field(default_factory=OrnithPreflightActionLedgerReport)
    latest_summary: str = ""
    open_questions: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    tool_profile: str = "balanced"
    approval_mode: str = "balanced"
    web_enabled: bool = True
    browser_enabled: bool = True
    desktop_enabled: bool = True
    wall_clock_limit_minutes: int = 90
    checkpoint_every_steps: int = 3
    active_tool: str = ""
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    model_interactions: list[ModelInteractionRecord] = Field(default_factory=list)
    web_sources: list[WebSource] = Field(default_factory=list)
    desktop_snapshots: list[DesktopSnapshot] = Field(default_factory=list)
    source_evidence: SourceEvidencePreviewReport = Field(default_factory=SourceEvidencePreviewReport)
    readiness_source_ref_preview: ReadinessSourceRefPreviewReport = Field(
        default_factory=ReadinessSourceRefPreviewReport
    )
    desktop_effect_proof: DesktopEffectProofReport = Field(default_factory=DesktopEffectProofReport)
    desktop_effect_proof_repairs: DesktopEffectProofRepairReport = Field(default_factory=DesktopEffectProofRepairReport)
    action_context: ActionContextPack = Field(default_factory=ActionContextPack)
    self_scaffold: SelfScaffoldReport = Field(default_factory=SelfScaffoldReport)
    self_scaffold_reviews: SelfScaffoldReviewReport = Field(default_factory=SelfScaffoldReviewReport)
    self_scaffold_rollback_intents: SelfScaffoldRollbackIntentReport = Field(default_factory=SelfScaffoldRollbackIntentReport)
    context_budget: ContextBudget = Field(default_factory=ContextBudget)
    context_snapshot: ContextSnapshot = Field(default_factory=ContextSnapshot)
    resume_prompt_quality: ResumePromptQualityReport = Field(default_factory=ResumePromptQualityReport)
    resume_handoff_diff: ResumeHandoffDiffReport = Field(default_factory=ResumeHandoffDiffReport)
    promotion_audit: PromotionAuditReport = Field(default_factory=PromotionAuditReport)
    promotion_verification: PromotionVerificationReport = Field(default_factory=PromotionVerificationReport)
    promotion_repair: PromotionRepairReport = Field(default_factory=PromotionRepairReport)
    handoff_summary: HandoffBundle = Field(default_factory=HandoffBundle)
    repo_map: RepoMap = Field(default_factory=RepoMap)
    workspace_isolation: WorkspaceIsolation = Field(default_factory=WorkspaceIsolation)
    workspace_diff: WorkspaceDiffSummary = Field(default_factory=WorkspaceDiffSummary)
    workspace_promotions: list[WorkspacePromotion] = Field(default_factory=list)
    task_graph: list[TaskNode] = Field(default_factory=list)
    current_task_id: str = ""
    patch_proposals: list[PatchProposal] = Field(default_factory=list)
    patch_applications: list[PatchApplication] = Field(default_factory=list)
    failure_records: list[FailureRecord] = Field(default_factory=list)
    recovery_plan: RecoveryPlan = Field(default_factory=RecoveryPlan)
    recovery_history: list[RecoveryPlan] = Field(default_factory=list)
    run_lease: RunLease = Field(default_factory=RunLease)
    act_preflight_checked_decision_id: int = 0
    failure_counts: dict[str, int] = Field(default_factory=dict)
    milestone: Literal["orient", "plan", "act", "verify", "checkpoint", "decide"] = "orient"
    step_count: int = 0


class CreateRunRequest(BaseModel):
    goal: str = Field(min_length=3)
    title: str | None = None
    workspace_path: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    tool_profile: str = "balanced"
    approval_mode: str = "balanced"
    web_enabled: bool = True
    browser_enabled: bool = True
    desktop_enabled: bool = True
    wall_clock_limit_minutes: int | None = None
    checkpoint_every_steps: int | None = None


class SteerRunRequest(BaseModel):
    message: str = Field(min_length=1)


class GoalProposalRequest(BaseModel):
    proposed_goal: str = Field(min_length=3)
    reason: str = ""


class PromoteWorkspaceRequest(BaseModel):
    files: list[str] = Field(default_factory=list)
    include_deletions: bool = False


class RunRecord(BaseModel):
    id: str
    title: str
    goal: str
    status: RunStatus
    workspace_path: str
    state: RunState
    created_at: str
    updated_at: str


class EventRecord(BaseModel):
    id: int
    run_id: str
    timestamp: str
    kind: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ApprovalRecord(BaseModel):
    id: int
    run_id: str
    status: Literal["pending", "approved", "rejected"]
    action_kind: str
    payload: dict[str, Any]
    reason: str
    created_at: str
    resolved_at: str | None = None


class ApprovalReviewRecord(BaseModel):
    id: int
    run_id: str
    status: Literal["pending", "approved", "rejected"]
    action_kind: str
    reason: str
    created_at: str
    resolved_at: str | None = None
    summary: str = ""
    preview: dict[str, Any] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)
    payload_keys: list[str] = Field(default_factory=list)
    high_risk: bool = False
    reviewed: bool = False
    review_count: int = 0
    latest_reviewed_at: str = ""
    latest_review_event_id: int = 0


class OperatorActionQueueItem(BaseModel):
    id: str
    run_id: str
    title: str
    severity: Literal["watch", "blocked"] = "watch"
    reason: str
    action: str
    status: str
    supervisor_action: str = ""
    priority: int = 0
    approval_id: int = 0
    approval_kind: str = ""
    endpoint: str = ""
    method: str = ""
    ui_target: str = ""
    promotion_gate: bool = False
    details: list[str] = Field(default_factory=list)


class OperatorActionQueueReport(BaseModel):
    generated_at: str = ""
    total_count: int = 0
    blocked_count: int = 0
    watch_count: int = 0
    approval_count: int = 0
    smoke_count: int = 0
    readiness_proof_history_count: int = 0
    readiness_source_ref_count: int = 0
    desktop_effect_proof_count: int = 0
    preflight_count: int = 0
    checkpoint_quality_count: int = 0
    promotion_count: int = 0
    promotion_approval_count: int = 0
    self_scaffold_count: int = 0
    self_scaffold_rollback_count: int = 0
    goal_confirmation_count: int = 0
    recovery_count: int = 0
    blocker_count: int = 0
    summary: str = ""
    items: list[OperatorActionQueueItem] = Field(default_factory=list)


class OperatorActionDispatchRequest(BaseModel):
    item_id: str = Field(min_length=3)
    decision: Literal["open", "dispatch", "approve", "reject"] = "dispatch"
    confirmed: bool = False
    note: str = ""


class OperatorActionDispatchResult(BaseModel):
    item_id: str
    run_id: str = ""
    status: Literal["requires_confirmation", "dispatched", "reviewed", "blocked", "not_found"]
    message: str
    action_taken: str = ""
    result_run_id: str = ""
    event_kind: str = ""
    queue: OperatorActionQueueReport = Field(default_factory=OperatorActionQueueReport)


