export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:9127";

export type RunState = {
  goal: string;
  proposed_goal: string | null;
  goal_revision_reason: string;
  goal_evolution: GoalEvolutionReport;
  git_checkpoint: GitCheckpointReport;
  promotion_audit: PromotionAuditReport;
  promotion_verification: PromotionVerificationReport;
  promotion_repair: PromotionRepairReport;
  current_plan: string[];
  completed_steps: string[];
  next_step: string;
  files_touched: string[];
  commands_run: string[];
  facts_learned: string[];
  risks: string[];
  blockers: string[];
  acceptance_criteria: string[];
  acceptance_evidence: AcceptanceCriterionEvidence[];
  acceptance_recommendations: AcceptanceEvidenceRecommendation[];
  acceptance_recommendation_traces: AcceptanceRecommendationTrace[];
  run_health: RunHealthReport;
  run_progress: RunProgressReport;
  report_integrity: ReportIntegrityReport;
  report_integrity_refreshes: ReportIntegrityRefreshRecord[];
  checkpoint_quality: CheckpointQualityReport;
  checkpoint_quality_resumes: CheckpointQualityResumeReport;
  objective_readiness: ObjectiveReadinessReport;
  objective_readiness_proof_outcomes: ObjectiveReadinessProofOutcome[];
  readiness_completion: ReadinessCompletionReport;
  readiness_rehearsal: ReadinessRehearsalReport;
  action_readiness: ActionReadinessReport;
  action_readiness_decisions: ActionReadinessDecisionReport;
  autonomy_decisions: AutonomyDecisionReport;
  recovery_decisions: RecoveryDecisionReport;
  verification_outcomes: VerificationOutcomeReport;
  post_action_retries: PostActionRetryReport;
  operator_dispatches: OperatorDispatchLedgerReport;
  operator_dispatch_restart_smoke: OperatorDispatchRestartSmokeReport;
  ornith_preflight: OrnithLaunchChecklistReport;
  ornith_preflight_actions: OrnithPreflightActionLedgerReport;
  latest_summary: string;
  open_questions: string[];
  memory_refs: string[];
  tool_profile: string;
  approval_mode: string;
  web_enabled: boolean;
  browser_enabled: boolean;
  desktop_enabled: boolean;
  wall_clock_limit_minutes: number;
  checkpoint_every_steps: number;
  active_tool: string;
  tool_calls: ToolCallRecord[];
  model_interactions: ModelInteractionRecord[];
  web_sources: WebSource[];
  desktop_snapshots: DesktopSnapshot[];
  source_evidence: SourceEvidencePreviewReport;
  readiness_source_ref_preview: ReadinessSourceRefPreviewReport;
  desktop_effect_proof: DesktopEffectProofReport;
  desktop_effect_proof_repairs: DesktopEffectProofRepairReport;
  action_context: ActionContextPack;
  self_scaffold: SelfScaffoldReport;
  self_scaffold_reviews: SelfScaffoldReviewReport;
  self_scaffold_rollback_intents: SelfScaffoldRollbackIntentReport;
  context_snapshot: ContextSnapshot;
  resume_prompt_quality: ResumePromptQualityReport;
  resume_handoff_diff: ResumeHandoffDiffReport;
  context_budget: ContextBudget;
  handoff_summary: HandoffBundle;
  repo_map: RepoMap;
  workspace_isolation: WorkspaceIsolation;
  workspace_diff: WorkspaceDiffSummary;
  workspace_promotions: WorkspacePromotion[];
  task_graph: TaskNode[];
  current_task_id: string;
  patch_proposals: PatchProposal[];
  patch_applications: PatchApplication[];
  failure_records: FailureRecord[];
  recovery_plan: RecoveryPlan;
  recovery_history: RecoveryPlan[];
  run_lease: RunLease;
  act_preflight_checked_decision_id: number;
  failure_counts: Record<string, number>;
  milestone: "orient" | "plan" | "act" | "verify" | "checkpoint" | "decide";
  step_count: number;
};

export type ToolCallRecord = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  ok: boolean;
  summary: string;
  needs_approval: boolean;
  created_at: string;
};

export type AcceptanceCriterionEvidence = {
  id: string;
  criterion: string;
  status: "open" | "verified" | "failed" | "blocked";
  required_labels: string[];
  matched_labels: string[];
  label_checked_at: Record<string, string>;
  evidence: string[];
  last_tool: string;
  last_checked: string;
  notes: string;
};

export type AcceptanceEvidenceRecommendation = {
  id: string;
  criterion_id: string;
  criterion: string;
  label: string;
  tool_kind: string;
  action: string;
  command_hint: string;
  reason: string;
  available: boolean;
};

export type AcceptanceRecommendationTrace = {
  id: string;
  recommendation_id: string;
  criterion_id: string;
  criterion: string;
  label: string;
  recommended_tool: string;
  selected_tool: string;
  source: "harness" | "model" | "fallback";
  status: "selected" | "executed" | "satisfied" | "failed" | "waiting_approval";
  action_summary: string;
  selected_at: string;
  resolved_at: string;
  result_ok: boolean | null;
  result_summary: string;
  evidence_status: string;
  notes: string;
};

export type CompletionAuditIssue = {
  id: string;
  severity: "info" | "warning" | "blocker";
  summary: string;
  evidence: string[];
};

export type CompletionAuditReport = {
  run_id: string;
  generated_at: string;
  status: "ready" | "not_ready";
  can_finish: boolean;
  acceptance_total: number;
  acceptance_verified: number;
  acceptance_open: number;
  acceptance_failed: number;
  acceptance_blocked: number;
  pending_approvals: number;
  blocker_count: number;
  recent_failure_count: number;
  stale_evidence_count: number;
  issues: CompletionAuditIssue[];
  next_actions: string[];
};

export type CompletionVerificationPolicy = {
  strict_stale_evidence: boolean;
  evidence_labels: Record<string, string[]>;
  stale_edit_tools: string[];
  verification_tools: string[];
  checkpoint_tools: string[];
  browser_tools: string[];
  edit_tools: string[];
  web_tools: string[];
};

export type ModelInteractionRecord = {
  id: string;
  kind: "plan" | "action" | "critic" | "goal";
  ok: boolean;
  attempts: number;
  repaired: boolean;
  fallback_used: boolean;
  summary: string;
  error: string;
  raw_excerpt: string;
  output_keys: string[];
  created_at: string;
};

export type WebSource = {
  id: string;
  title: string;
  url: string;
  timestamp: string;
  excerpt: string;
  citation: string;
};

export type DesktopSnapshot = {
  id: string;
  timestamp: string;
  title: string;
  path: string;
  summary: string;
};

export type DesktopEffectProofReport = {
  run_id: string;
  generated_at: string;
  status: "not_required" | "needs_proof" | "proof_available";
  requires_attention: boolean;
  latest_action_id: string;
  latest_action_tool: string;
  latest_action_created_at: string;
  latest_action_summary: string;
  proof_call_id: string;
  proof_tool: string;
  proof_created_at: string;
  proof_summary: string;
  proof_snapshot: DesktopSnapshot | null;
  proof_snapshot_count: number;
  ledger: string[];
  recommended_action: string;
};

export type DesktopEffectProofRepairRecord = {
  event_id: number;
  timestamp: string;
  outcome: "metadata_refreshed" | "capture_completed" | "capture_failed" | "blocked" | "skipped_noop";
  previous_integrity_status: string;
  refreshed_integrity_status: string;
  previous_proof_status: string;
  refreshed_proof_status: string;
  latest_action_id: string;
  proof_call_id: string;
  proof_snapshot_id: string;
  reason_count: number;
  reasons: string[];
  summary: string;
};

export type DesktopEffectProofRepairReport = {
  run_id: string;
  generated_at: string;
  total_count: number;
  metadata_refreshed_count: number;
  capture_completed_count: number;
  capture_failed_count: number;
  blocked_count: number;
  skipped_noop_count: number;
  latest_outcome: string;
  summary: string;
  recommended_action: string;
  entries: DesktopEffectProofRepairRecord[];
};

export type SourceEvidencePreviewEntry = {
  id: string;
  kind: "web_source" | "browser_snapshot" | "desktop_snapshot";
  timestamp: string;
  title: string;
  url: string;
  path: string;
  tool_kind: string;
  evidence_label: string;
  linked_criteria: string[];
  excerpt: string;
  summary: string;
  citation: string;
};

export type SourceEvidencePreviewReport = {
  run_id: string;
  generated_at: string;
  total_count: number;
  web_source_count: number;
  browser_snapshot_count: number;
  desktop_snapshot_count: number;
  linked_criterion_count: number;
  required_label_count: number;
  matched_label_count: number;
  missing_labels: string[];
  latest_evidence: string;
  summary: string;
  recommended_action: string;
  entries: SourceEvidencePreviewEntry[];
};
export type SelfScaffoldChangeRecord = {
  id: string;
  kind: "task_graph" | "action_context" | "tool_posture" | "model_guard" | "edit_evidence" | "goal_evolution" | "checkpoint" | "event";
  status: "observed" | "active" | "needs_review";
  source: string;
  structure_ref: string;
  summary: string;
  intent: string;
  reversible: boolean;
  reverse_hint: string;
  evidence: string[];
  event_id: number;
  created_at: string;
};

export type SelfScaffoldReport = {
  run_id: string;
  generated_at: string;
  status: "empty" | "observed" | "needs_review";
  change_count: number;
  task_graph_count: number;
  action_context_count: number;
  tool_posture_count: number;
  guard_count: number;
  reversible_count: number;
  review_count: number;
  reviewed_change_count: number;
  latest_reviewed_at: string;
  latest_review_event_id: number;
  latest_reviewed_change_ids: string[];
  latest_change: string;
  summary: string;
  recommended_action: string;
  changes: SelfScaffoldChangeRecord[];
};
export type SelfScaffoldReviewRecord = {
  event_id: number;
  timestamp: string;
  status: "accepted" | "partial" | "noop";
  change_count: number;
  guard_count: number;
  reviewed_change_count: number;
  reviewed_change_ids: string[];
  remaining_goal_review: boolean;
  action_reason: string;
  action_summary: string;
  summary: string;
};

export type SelfScaffoldReviewReport = {
  run_id: string;
  generated_at: string;
  status: "none" | "reviewed" | "needs_goal_review";
  total_count: number;
  accepted_count: number;
  partial_count: number;
  noop_count: number;
  reviewed_change_count: number;
  remaining_goal_review_count: number;
  latest_event_id: number;
  latest_reviewed_change_ids: string[];
  summary: string;
  recommended_action: string;
  entries: SelfScaffoldReviewRecord[];
};


export type SelfScaffoldRollbackIntentRecord = {
  id: string;
  source_review_event_id: number;
  reviewed_change_id: string;
  change_kind: string;
  action_kind: "steer" | "patch_rollback" | "patch_review" | "handoff_refresh" | "goal_review";
  status: "suggested" | "needs_approval" | "resolved" | "stale";
  proposed_tool: string;
  requires_approval: boolean;
  mutation_automatic: boolean;
  patch_id: string;
  backup_id: string;
  rollback_manifest_path: string;
  files: string[];
  reverse_hint: string;
  summary: string;
  evidence: string[];
};

export type SelfScaffoldRollbackIntentReport = {
  run_id: string;
  generated_at: string;
  status: "none" | "available" | "needs_approval" | "resolved";
  intent_count: number;
  patch_rollback_count: number;
  steering_count: number;
  latest_review_event_id: number;
  summary: string;
  recommended_action: string;
  entries: SelfScaffoldRollbackIntentRecord[];
};
export type ActionContextPack = {
  run_id: string;
  generated_at: string;
  milestone: string;
  current_task_id: string;
  current_task_title: string;
  task_transition_ledger: string[];
  model_guard_ledger: string[];
  edit_evidence_ledger: string[];
  desktop_supervision_ledger: string[];
  action_readiness_status: string;
  selected_tool: string;
  selected_label: string;
  selected_action: string;
  selected_reason: string;
  selected_command_hint: string;
  selected_criterion: string;
  source_evidence_summary: string;
  missing_source_labels: string[];
  latest_source_evidence: string;
  readiness_source_ref_status: string;
  readiness_source_ref_action: string;
  readiness_source_ref_missing_evidence_labels: string[];
  readiness_source_ref_missing_proof_labels: string[];
  readiness_source_ref_source_labels: string[];
  readiness_source_ref_proof_labels: string[];
  recent_verified_commands: string[];
  recent_verified_files: string[];
  recent_successes: string[];
  failure_ledger: string[];
  resolved_failure_ledger: string[];
  promotion_repair_hints: string[];
  recovery_hint: string;
  context_budget: string;
  compact_prompt: string;
};
export type ContextBudget = {
  target_tokens: number;
  estimated_tokens: number;
  last_compaction: string;
  pressure: "low" | "medium" | "high";
};

export type ContextSnapshot = {
  run_id: string;
  generated_at: string;
  estimated_tokens: number;
  sections: string[];
  selected_section_count: number;
  dropped_sections: string[];
  dropped_section_count: number;
  required_sections_missing: string[];
  section_token_estimates: Record<string, number>;
  coverage_status: "ok" | "degraded" | "critical";
  recommended_action: string;
  prompt_preview: string;
};

export type TaskNode = {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "blocked" | "failed" | "skipped";
  kind: "investigate" | "edit" | "verify" | "summarize" | "decision" | "blocked";
  depends_on: string[];
  evidence: string[];
  notes: string;
};

export type RepoMap = {
  generated_at: string;
  root: string;
  manifests: string[];
  package_scripts: Record<string, string>;
  test_commands: string[];
  key_files: string[];
  languages: Record<string, number>;
  summary: string;
};

export type WorkspaceIsolation = {
  enabled: boolean;
  mode: "source" | "copy" | "git_worktree";
  source_path: string;
  workspace_path: string;
  created_at: string;
  copied_files: number;
  skipped_paths: string[];
  summary: string;
};

export type WorkspaceDiffFile = {
  path: string;
  status: "added" | "modified" | "deleted";
  source_size: number;
  workspace_size: number;
  source_sha256: string;
  workspace_sha256: string;
  diff: string;
  binary: boolean;
  truncated: boolean;
};

export type WorkspaceDiffSummary = {
  generated_at: string;
  source_path: string;
  workspace_path: string;
  files: WorkspaceDiffFile[];
  total_files: number;
  added: number;
  modified: number;
  deleted: number;
  truncated: boolean;
  summary: string;
};

export type WorkspacePromotion = {
  id: string;
  status: "promoted" | "rolled_back" | "failed";
  files: string[];
  backup_id: string;
  manifest_path: string;
  summary: string;
  promoted_at: string;
  rolled_back_at: string;
};

export type PatchProposal = {
  id: string;
  title: string;
  summary: string;
  files: string[];
  diff: string;
  status: "pending" | "approved" | "rejected" | "applied" | "rolled_back";
  backup_id: string;
  applied_at: string;
  rollback_manifest_path: string;
  created_at: string;
};

export type PatchApplication = {
  id: string;
  patch_id: string;
  status: "applied" | "rolled_back" | "failed";
  files: string[];
  backup_id: string;
  manifest_path: string;
  summary: string;
  applied_at: string;
  rolled_back_at: string;
};

export type PromotionAuditIssue = {
  id: string;
  severity: "info" | "warning" | "blocker";
  summary: string;
  evidence: string[];
  next_action: string;
};

export type PromotionAuditReport = {
  run_id: string;
  generated_at: string;
  status: "ready" | "needs_verification" | "blocked" | "not_applicable";
  ready_to_promote: boolean;
  changed_file_count: number;
  patch_proposal_count: number;
  patch_application_count: number;
  promotion_count: number;
  pending_patch_count: number;
  pending_approval_count: number;
  unresolved_approval_history_count: number;
  unresolved_approval_histories: string[];
  latest_verification: string;
  workspace_diff_status: string;
  workspace_diff_summary: string;
  resume_drift_status: string;
  git_checkpoint_status: string;
  summary: string;
  recommended_action: string;
  issues: PromotionAuditIssue[];
};

export type PromotionVerificationAttemptRecord = {
  event_id: number;
  timestamp: string;
  command: string;
  ok: boolean;
  audit_status: string;
  summary: string;
  tool_ok: boolean;
  selected_alternate: boolean;
  returncode: number;
  failure_kind: string;
  suspected_file: string;
  suspected_line: number;
  repair_hint: string;
  evidence_excerpt: string;
};

export type PromotionVerificationReport = {
  run_id: string;
  generated_at: string;
  status: "none" | "ready" | "needs_retry" | "repeated_failure";
  attempt_count: number;
  failed_count: number;
  success_count: number;
  repeated_failure_count: number;
  repair_hint_count: number;
  latest_attempt: PromotionVerificationAttemptRecord;
  latest_failed_command: string;
  latest_failure_kind: string;
  latest_suspected_file: string;
  latest_repair_hint: string;
  next_command: string;
  should_use_alternate: boolean;
  failure_kinds: string[];
  summary: string;
  recommended_action: string;
  attempts: PromotionVerificationAttemptRecord[];
};

export type PromotionRepairReport = {
  run_id: string;
  generated_at: string;
  phase: "none" | "needs_file_read" | "needs_patch_proposal" | "patch_proposed" | "ready_to_verify";
  active: boolean;
  target_file: string;
  target_line: number;
  failure_kind: string;
  repair_hint: string;
  evidence_excerpt: string;
  latest_failed_command: string;
  file_read: boolean;
  file_read_tool_id: string;
  file_excerpt_chars: number;
  patch_proposal_id: string;
  patch_status: string;
  patch_application_id: string;
  next_tool: string;
  next_action: string;
  next_verification_command: string;
  summary: string;
};
export type FailureRecord = {
  id: string;
  kind: string;
  tool: string;
  summary: string;
  count: number;
  last_seen: string;
  recovery_hint: string;
  command: string;
  target: string;
  returncode: number | null;
  evidence_excerpt: string;
};

export type RecoveryPlan = {
  id: string;
  status: "none" | "active" | "resolved" | "superseded";
  trigger: string;
  failure_kind: string;
  tool: string;
  attempts: number;
  summary: string;
  next_action: string;
  steps: string[];
  created_at: string;
  resolved_at: string;
};

export type RecoveryDecisionRecord = {
  id: string;
  status: "none" | "active" | "resolved" | "superseded";
  trigger: string;
  failure_kind: string;
  tool: string;
  attempts: number;
  created_at: string;
  resolved_at: string;
  proof_label: string;
  proof_status: string;
  criterion_id: string;
  criterion: string;
  evidence_status: string;
  readiness_decision_id: number;
  readiness_decision_status: string;
  activation_reason: string;
  selected_strategy: string;
  next_action: string;
  resolved_by_evidence: boolean;
  summary: string;
};

export type RecoveryDecisionReport = {
  run_id: string;
  generated_at: string;
  decision_count: number;
  active_recovery: boolean;
  readiness_recovery_count: number;
  resolved_count: number;
  unresolved_count: number;
  latest_decision: RecoveryDecisionRecord;
  active_decision: RecoveryDecisionRecord;
  latest_readiness_decision: RecoveryDecisionRecord;
  summary: string;
  recommended_action: string;
  decisions: RecoveryDecisionRecord[];
};

export type VerificationOutcomeRecord = {
  id: string;
  timestamp: string;
  tool_call_id: string;
  tool: string;
  ok: boolean;
  needs_approval: boolean;
  outcome:
    | "verified"
    | "partial"
    | "failed"
    | "waiting_approval"
    | "recovery_resolved"
    | "recovery_tool_succeeded"
    | "executed";
  summary: string;
  during_recovery: boolean;
  recovery_id: string;
  recovery_trigger: string;
  recovery_status: string;
  recovery_resume_event_id: number;
  recovery_resume_timestamp: string;
  closed_recovery: boolean;
  resolved_recovery_evidence: boolean;
  proof_label: string;
  criterion_id: string;
  criterion: string;
  evidence_status: string;
  required_labels: string[];
  matched_labels: string[];
  labels_satisfied: string[];
  recommendation_trace_id: string;
  recommendation_status: string;
  readiness_decision_id: number;
  selected_strategy: string;
};

export type VerificationOutcomeReport = {
  run_id: string;
  generated_at: string;
  outcome_count: number;
  verified_count: number;
  failed_count: number;
  recovery_outcome_count: number;
  recovery_resolved_count: number;
  recovery_unresolved_count: number;
  latest_outcome: VerificationOutcomeRecord;
  latest_recovery_outcome: VerificationOutcomeRecord;
  summary: string;
  recommended_action: string;
  outcomes: VerificationOutcomeRecord[];
};

export type RunLease = {
  id: string;
  owner_id: string;
  status: "none" | "active" | "released" | "stale";
  acquired_at: string;
  heartbeat_at: string;
  expires_at: string;
  heartbeat_count: number;
  heartbeat_interval_seconds: number;
  ttl_seconds: number;
  last_milestone: string;
  last_event: string;
};

export type RunHealthSignal = {
  id: string;
  severity: "info" | "warning" | "critical";
  summary: string;
  evidence: string[];
};

export type RunHealthReport = {
  run_id: string;
  generated_at: string;
  score: number;
  level: "healthy" | "watch" | "stuck" | "blocked";
  recommended_action: "continue" | "verify" | "recover" | "pause" | "wait_approval" | "ask_user";
  summary: string;
  signals: RunHealthSignal[];
  next_actions: string[];
};

export type RunProgressReport = {
  run_id: string;
  generated_at: string;
  status: "on_track" | "needs_verification" | "needs_recovery" | "waiting" | "near_completion" | "blocked";
  summary: string;
  can_keep_running: boolean;
  should_pause: boolean;
  near_completion: boolean;
  task_total: number;
  task_completed: number;
  task_blocked: number;
  task_failed: number;
  task_progress_percent: number;
  acceptance_total: number;
  acceptance_verified: number;
  acceptance_open: number;
  acceptance_failed: number;
  acceptance_blocked: number;
  acceptance_coverage_percent: number;
  workspace_change_count: number;
  pending_patch_count: number;
  pending_approval_count: number;
  latest_autonomy_decision: string;
  latest_verification_outcome: string;
  current_policy_action: string;
  next_actions: string[];
  evidence: string[];
};

export type ReportIntegrityCheck = {
  section: string;
  status: "ok" | "missing" | "stale" | "mismatch";
  summary: string;
  expected: string;
  actual: string;
  generated_at: string;
};

export type ReportIntegrityReport = {
  run_id: string;
  generated_at: string;
  status: "ok" | "needs_refresh";
  check_count: number;
  ok_count: number;
  missing_count: number;
  stale_count: number;
  mismatch_count: number;
  latest_event_id: number;
  latest_event_timestamp: string;
  summary: string;
  recommended_action: string;
  checks: ReportIntegrityCheck[];
};

export type ReportIntegrityRefreshRecord = {
  event_id: number;
  timestamp: string;
  report_status: string;
  previous_report_status: string;
  reason_count: number;
  reasons: string[];
  preflight_event_id: number;
  preflight_event_kind: string;
  preflight_accepted: boolean | null;
  preflight_reason: string;
};

export type CheckpointQualityIssue = {
  id: string;
  severity: "warning" | "blocker";
  summary: string;
  evidence: string;
  recommended_action: string;
};

export type CheckpointQualityReport = {
  run_id: string;
  generated_at: string;
  status: "unknown" | "ready" | "needs_checkpoint" | "blocked";
  run_note_present: boolean;
  run_note_path: string;
  run_note_chars: number;
  has_checkpoint_heading: boolean;
  has_active_goal: boolean;
  has_current_step: boolean;
  has_next_action: boolean;
  has_resume_prompt: boolean;
  has_no_raw_logs_instruction: boolean;
  expected_report_integrity_refresh: boolean;
  has_report_integrity_refresh: boolean;
  expected_refresh_event_id: number;
  expected_refresh_reason: string;
  issue_count: number;
  blocker_count: number;
  warning_count: number;
  summary: string;
  recommended_action: string;
  issues: CheckpointQualityIssue[];
};

export type CheckpointQualityResumeRecord = {
  repair_event_id: number;
  repair_completed_event_id: number;
  repair_timestamp: string;
  repair_reason: string;
  repair_ui_target: string;
  repair_action: string;
  resume_event_id: number;
  resume_timestamp: string;
  resume_source: string;
  resume_accepted: boolean | null;
  resume_policy_action: string;
  resume_reason: string;
  checkpoint_quality_status: string;
  checkpoint_quality_ready: boolean;
  summary: string;
};

export type CheckpointQualityResumeReport = {
  run_id: string;
  generated_at: string;
  status: "none" | "awaiting_resume" | "resumed" | "blocked";
  repair_count: number;
  resumed_after_repair_count: number;
  blocked_after_repair_count: number;
  awaiting_resume_count: number;
  latest: CheckpointQualityResumeRecord;
  summary: string;
  recommended_action: string;
  entries: CheckpointQualityResumeRecord[];
};

export type ObjectiveReadinessProof = {
  tool_kind: string;
  evidence_label: string;
  strategy: string;
  action: string;
  command_hint: string;
  success_signal: string;
  requires_approval: boolean;
};

export type ObjectiveReadinessProofOutcome = {
  id: string;
  item_id: string;
  tool: string;
  evidence_label: string;
  strategy: string;
  outcome: "verified" | "partial" | "failed" | "waiting_approval";
  ok: boolean;
  summary: string;
  proof_action: string;
  created_at: string;
};

export type ObjectiveReadinessProofPreference = {
  item_id: string;
  tool_kind: string;
  evidence_label: string;
  strategy: string;
  action: string;
  command_hint: string;
  reason: string;
  confidence: "low" | "medium" | "high";
  verified_count: number;
  partial_count: number;
  failed_count: number;
  last_outcome: string;
};

export type ObjectiveReadinessItem = {
  id: string;
  requirement: string;
  status: "verified" | "partial" | "missing" | "failed";
  evidence: string[];
  next_action: string;
  proof: ObjectiveReadinessProof;
  latest_outcome: ObjectiveReadinessProofOutcome;
  preferred_proof: ObjectiveReadinessProofPreference;
};

export type ObjectiveReadinessReport = {
  run_id: string;
  generated_at: string;
  status: "ready" | "partial" | "not_ready";
  verified_count: number;
  partial_count: number;
  missing_count: number;
  failed_count: number;
  summary: string;
  recommended_action: string;
  next_actions: string[];
  proof_preferences: ObjectiveReadinessProofPreference[];
  items: ObjectiveReadinessItem[];
};

export type ReadinessCompletionCheck = {
  id: string;
  status: "pass" | "warn" | "block";
  summary: string;
  evidence: string[];
  next_action: string;
};

export type ReadinessCompletionReport = {
  run_id: string;
  generated_at: string;
  status: "ready" | "needs_more_evidence" | "blocked" | "not_applicable";
  can_claim_milestone: boolean;
  confidence: "low" | "medium" | "high";
  summary: string;
  objective_status: string;
  run_progress_status: string;
  completion_status: string;
  rehearsal_ledger_status: string;
  rehearsal_latest_run_id: string;
  rehearsal_passed_count: number;
  rehearsal_failed_count: number;
  dispatch_restart_smoke_ledger_status: string;
  dispatch_restart_smoke_latest_run_id: string;
  dispatch_restart_smoke_passed_count: number;
  dispatch_restart_smoke_failed_count: number;
  ornith_preflight_warning_count: number;
  ornith_preflight_block_count: number;
  ornith_preflight_reorient_count: number;
  self_scaffold_status: string;
  self_scaffold_pending_review_count: number;
  self_scaffold_review_count: number;
  self_scaffold_reviewed_change_count: number;
  self_scaffold_latest_review_event_id: number;
  source_visible_required_label_count: number;
  source_visible_matched_label_count: number;
  readiness_proof_source_ref_count: number;
  readiness_proof_source_ref_labels: string[];
  source_visible_missing_ref_labels: string[];
  required_verified_count: number;
  verified_count: number;
  partial_count: number;
  missing_count: number;
  failed_count: number;
  proof_preference_count: number;
  open_preference_count: number;
  blocking_count: number;
  warning_count: number;
  checks: ReadinessCompletionCheck[];
  next_actions: string[];
};

export type ReadinessRehearsalStep = {
  id: string;
  status: "pending" | "passed" | "failed" | "skipped";
  summary: string;
  evidence: string[];
  event_id: number;
  event_kind: string;
  run_status: string;
  milestone: string;
};

export type ReadinessRehearsalReport = {
  run_id: string;
  generated_at: string;
  status: "not_run" | "running" | "passed" | "failed";
  scenario: string;
  summary: string;
  rehearsal_workspace: string;
  restart_simulated: boolean;
  refused_event_id: number;
  accepted_event_id: number;
  completed_event_id: number;
  self_scaffold_reviewed: boolean;
  self_scaffold_review_event_id: number;
  self_scaffold_reviewed_change_count: number;
  post_review_handoff_goal_preserved: boolean;
  post_review_handoff_next_action_preserved: boolean;
  post_review_resume_prompt_goal_preserved: boolean;
  post_review_resume_prompt_next_action_preserved: boolean;
  compact_context_tokens: number;
  compact_context_sections: string[];
  replay_attached: boolean;
  handoff_attached: boolean;
  next_action: string;
  steps: ReadinessRehearsalStep[];
};

export type ReadinessRehearsalLedgerEntry = {
  run_id: string;
  generated_at: string;
  status: "running" | "passed" | "failed";
  scenario: string;
  summary: string;
  rehearsal_workspace: string;
  restart_simulated: boolean;
  replay_attached: boolean;
  handoff_attached: boolean;
  compact_context_tokens: number;
  refused_event_id: number;
  accepted_event_id: number;
  completed_event_id: number;
  self_scaffold_reviewed: boolean;
  self_scaffold_review_event_id: number;
  self_scaffold_reviewed_change_count: number;
  post_review_handoff_goal_preserved: boolean;
  post_review_handoff_next_action_preserved: boolean;
  post_review_resume_prompt_goal_preserved: boolean;
  post_review_resume_prompt_next_action_preserved: boolean;
  step_count: number;
  passed_steps: number;
  failed_steps: number;
  next_action: string;
};

export type ReadinessRehearsalLedgerReport = {
  generated_at: string;
  status: "never_run" | "running" | "passed" | "failed" | "mixed";
  summary: string;
  total_count: number;
  passed_count: number;
  failed_count: number;
  running_count: number;
  latest: ReadinessRehearsalLedgerEntry | null;
  entries: ReadinessRehearsalLedgerEntry[];
  next_action: string;
};

export type ReadinessProofSourceRef = {
  id: string;
  kind: "web_source" | "browser_snapshot" | "desktop_snapshot";
  evidence_label: string;
  title: string;
  target: string;
  linked_criteria: string[];
  citation: string;
};

export type ReadinessProofHistoryRecord = {
  event_id: number;
  timestamp: string;
  source: "rehearsal_step" | "operator_event" | "claim_event" | "report";
  proof_type:
    | "self_scaffold_review"
    | "post_review_handoff"
    | "resume_prompt_preservation"
    | "readiness_claim"
    | "readiness_rehearsal";
  status: "pass" | "warn" | "block" | "info";
  step_id: string;
  summary: string;
  evidence: string[];
  run_status: string;
  milestone: string;
  source_refs: ReadinessProofSourceRef[];
};

export type ReadinessProofHistoryReport = {
  run_id: string;
  generated_at: string;
  status: "empty" | "partial" | "complete" | "needs_attention";
  total_count: number;
  self_scaffold_review_count: number;
  post_review_handoff_count: number;
  resume_prompt_preservation_count: number;
  readiness_claim_count: number;
  blocking_count: number;
  source_evidence_ref_count: number;
  source_evidence_labels: string[];
  source_evidence_summary: string;
  latest_event_id: number;
  latest_summary: string;
  summary: string;
  recommended_action: string;
  entries: ReadinessProofHistoryRecord[];
};
export type ReadinessSourceRefLabelPreview = {
  label: string;
  source_visible: boolean;
  acceptance_required: boolean;
  acceptance_matched: boolean;
  present_in_source_evidence: boolean;
  present_in_proof_history: boolean;
  missing_from_source_evidence: boolean;
  missing_from_proof_history: boolean;
  source_evidence_count: number;
  proof_ref_count: number;
  linked_criteria: string[];
  source_evidence_titles: string[];
  proof_ref_titles: string[];
};

export type ReadinessSourceRefPreviewReport = {
  run_id: string;
  generated_at: string;
  status: "not_applicable" | "ready" | "missing_source_evidence" | "missing_proof_refs";
  summary: string;
  recommended_action: string;
  readiness_completion_status: string;
  readiness_proof_history_status: string;
  source_visible_labels: string[];
  acceptance_required_labels: string[];
  acceptance_matched_labels: string[];
  source_evidence_labels: string[];
  proof_ref_labels: string[];
  missing_source_evidence_labels: string[];
  missing_proof_ref_labels: string[];
  source_evidence_entry_count: number;
  proof_ref_count: number;
  labels: ReadinessSourceRefLabelPreview[];
  source_evidence_entries: SourceEvidencePreviewEntry[];
  proof_refs: ReadinessProofSourceRef[];
};
export type OrnithLaunchChecklistItem = {
  id: string;
  category: string;
  status: "pass" | "warn" | "block";
  summary: string;
  evidence: string[];
  next_action: string;
};

export type OrnithLaunchChecklistReport = {
  run_id: string;
  generated_at: string;
  mode: "launch" | "resume";
  status: "ready" | "attention" | "blocked";
  ready_to_start: boolean;
  ready_to_resume: boolean;
  summary: string;
  model_profile_id: string;
  model_name: string;
  tool_profile: string;
  web_enabled: boolean;
  browser_enabled: boolean;
  desktop_enabled: boolean;
  context_pressure: string;
  context_snapshot: ContextSnapshot;
  resume_prompt_quality: ResumePromptQualityReport;
  resume_handoff_diff: ResumeHandoffDiffReport;
  checkpoint_quality: CheckpointQualityReport;
  context_tokens: number;
  context_target_tokens: number;
  pending_approval_count: number;
  readiness_smoke_status: string;
  dispatch_restart_smoke_status: string;
  run_health_level: string;
  run_health_action: string;
  supervisor_attention_count: number;
  items: OrnithLaunchChecklistItem[];
  next_actions: string[];
};
export type PolicySimulationReport = {
  run_id: string;
  generated_at: string;
  current_status: string;
  current_milestone: string;
  predicted_status: string;
  predicted_milestone: string;
  policy_action: "continue" | "verify" | "recover" | "pause" | "wait_approval" | "ask_user" | "complete";
  safe_to_resume: boolean;
  auto_resume_eligible: boolean;
  summary: string;
  reason: string;
  next_action: string;
  recommended_tool: string;
  recommended_label: string;
  effects: string[];
  blocking_signals: string[];
  run_health: RunHealthReport;
  completion_audit: CompletionAuditReport;
};

export type ResumePromptQualityIssue = {
  id: string;
  severity: "info" | "warning" | "blocker";
  summary: string;
  evidence: string[];
  next_action: string;
};

export type ResumePromptQualityReport = {
  run_id: string;
  generated_at: string;
  status: "ready" | "needs_refresh" | "blocked";
  ready_to_resume: boolean;
  score: number;
  summary: string;
  prompt_chars: number;
  next_action: string;
  concrete_next_action: boolean;
  has_goal_anchor: boolean;
  has_context_anchor: boolean;
  has_action_context: boolean;
  has_evidence_refs: boolean;
  context_coverage_status: string;
  recommended_action: string;
  issues: ResumePromptQualityIssue[];
};

export type ResumeHandoffDiffChange = {
  id: string;
  severity: "info" | "warning" | "blocker";
  field: string;
  accepted: string;
  current: string;
  summary: string;
};

export type ResumeHandoffDiffReport = {
  run_id: string;
  generated_at: string;
  status: "no_baseline" | "stable" | "changed" | "blocked";
  ready_to_continue: boolean;
  latest_accepted_event_id: number;
  latest_accepted_at: string;
  latest_accepted_source: string;
  changed_count: number;
  blocker_count: number;
  warning_count: number;
  summary: string;
  recommended_action: string;
  changes: ResumeHandoffDiffChange[];
};

export type ResumeDecisionRecord = {
  id: number;
  timestamp: string;
  kind: string;
  source: string;
  accepted: boolean;
  reason: string;
  policy_action: string;
  predicted_status: string;
  predicted_milestone: string;
  safe_to_resume: boolean;
  auto_resume_eligible: boolean;
  recommended_tool: string;
  recommended_label: string;
  health_level: string;
  health_action: string;
  health_score: number;
  summary: string;
};

export type ResumeDecisionReport = {
  run_id: string;
  generated_at: string;
  decision_count: number;
  accepted_count: number;
  blocked_count: number;
  latest_decision: ResumeDecisionRecord;
  latest_accepted: ResumeDecisionRecord;
  latest_blocked: ResumeDecisionRecord;
  current_policy_action: string;
  current_predicted_status: string;
  current_predicted_milestone: string;
  current_recommended_tool: string;
  current_recommended_label: string;
  current_matches_last_accepted: boolean;
  comparison_summary: string;
  recommended_action: string;
  decisions: ResumeDecisionRecord[];
};

export type ActionReadinessIssue = {
  id: string;
  severity: "info" | "warning" | "blocker";
  summary: string;
  evidence: string[];
};

export type ActionReadinessReport = {
  run_id: string;
  generated_at: string;
  status: "ready" | "needs_proof" | "needs_replan" | "reorient" | "waiting_approval" | "recover" | "blocked";
  ready_to_act: boolean;
  summary: string;
  recommended_action: string;
  suggested_tool: string;
  suggested_label: string;
  milestone: string;
  current_task_id: string;
  current_task_status: string;
  active_tool: string;
  run_health_level: string;
  run_health_action: string;
  resume_decision_matches: boolean;
  latest_resume_decision_id: number;
  act_preflight_checked_decision_id: number;
  issues: ActionReadinessIssue[];
};

export type ActionReadinessDecisionRecord = {
  id: number;
  timestamp: string;
  kind: string;
  status:
    | "selected"
    | "executed"
    | "satisfied"
    | "failed"
    | "waiting_approval"
    | "blocked"
    | "replanned"
    | "reoriented"
    | "recover";
  readiness_status: string;
  ready_to_act: boolean;
  source: string;
  selected_tool: string;
  suggested_tool: string;
  suggested_label: string;
  recommendation_trace_id: string;
  recommendation_id: string;
  criterion_id: string;
  criterion: string;
  label: string;
  result_ok: boolean | null;
  result_summary: string;
  evidence_status: string;
  summary: string;
  reason: string;
};

export type ActionReadinessDecisionReport = {
  run_id: string;
  generated_at: string;
  decision_count: number;
  selected_count: number;
  satisfied_count: number;
  failed_count: number;
  blocked_count: number;
  policy_gate_count: number;
  harness_selected_count: number;
  model_selected_count: number;
  fallback_selected_count: number;
  latest_decision: ActionReadinessDecisionRecord;
  latest_tool_decision: ActionReadinessDecisionRecord;
  latest_policy_decision: ActionReadinessDecisionRecord;
  summary: string;
  recommended_action: string;
  decisions: ActionReadinessDecisionRecord[];
};

export type AutonomyDecisionRecord = {
  id: number;
  timestamp: string;
  kind: string;
  milestone: string;
  decision:
    | "continue"
    | "verify"
    | "recover"
    | "pause"
    | "wait_approval"
    | "ask_user"
    | "complete"
    | "reorient"
    | "replan"
    | "blocked"
    | "resume"
    | "wait_goal";
  source: string;
  policy_action: string;
  predicted_status: string;
  predicted_milestone: string;
  health_level: string;
  health_action: string;
  health_score: number;
  safe_to_resume: boolean;
  auto_resume_eligible: boolean;
  reason: string;
  next_action: string;
  blocking_signals: string[];
  summary: string;
};

export type AutonomyDecisionReport = {
  run_id: string;
  generated_at: string;
  decision_count: number;
  continue_count: number;
  pause_count: number;
  recover_count: number;
  wait_count: number;
  complete_count: number;
  blocked_count: number;
  latest_decision: AutonomyDecisionRecord;
  latest_stop_decision: AutonomyDecisionRecord;
  latest_continue_decision: AutonomyDecisionRecord;
  current_policy_action: string;
  current_safe_to_resume: boolean;
  current_next_action: string;
  summary: string;
  recommended_action: string;
  decisions: AutonomyDecisionRecord[];
};

export type GitCheckpointReport = {
  run_id: string;
  generated_at: string;
  status: "unknown" | "not_repo" | "needs_remote" | "verify_first" | "commit_recommended" | "push_recommended" | "clean";
  workspace_path: string;
  repo_root: string;
  branch: string;
  head_sha: string;
  last_commit: string;
  remote_names: string[];
  remote_count: number;
  github_remote_count: number;
  staged_count: number;
  modified_count: number;
  untracked_count: number;
  changed_count: number;
  ahead_count: number;
  behind_count: number;
  recent_verification: string;
  summary: string;
  recommended_action: string;
};

export type GoalEvolutionDecisionRecord = {
  id: string;
  status: "pending" | "accepted" | "rejected" | "unchanged";
  source: string;
  previous_goal: string;
  proposed_goal: string;
  reason: string;
  material_change: string;
  step_count: number;
  milestone: string;
  approval_id: number;
  created_at: string;
  resolved_at: string;
};

export type GoalEvolutionReport = {
  run_id: string;
  generated_at: string;
  active_goal: string;
  proposed_goal: string;
  decision_count: number;
  pending_count: number;
  accepted_count: number;
  rejected_count: number;
  unchanged_count: number;
  latest_decision: GoalEvolutionDecisionRecord;
  summary: string;
  recommended_action: string;
  decisions: GoalEvolutionDecisionRecord[];
};

export type PostActionRetryDecisionRecord = {
  id: string;
  status: "pending" | "selected" | "resolved" | "failed" | "skipped";
  trigger_tool: string;
  trigger_summary: string;
  failure_kind: string;
  attempt_count: number;
  selected_tool: string;
  selected_action: string;
  command_hint: string;
  reason: string;
  action_context_summary: string;
  verification_outcome: string;
  resolution_tool: string;
  resolution_ok: boolean;
  resolution_summary: string;
  created_at: string;
  resolved_at: string;
};

export type PostActionRetryReport = {
  run_id: string;
  generated_at: string;
  decision_count: number;
  pending_count: number;
  resolved_count: number;
  failed_count: number;
  latest_decision: PostActionRetryDecisionRecord;
  summary: string;
  recommended_action: string;
  decisions: PostActionRetryDecisionRecord[];
};
export type OperatorDispatchLedgerEntry = {
  event_id: number;
  run_id: string;
  timestamp: string;
  kind: string;
  status: "confirmation_required" | "reviewed" | "dispatched" | "blocked";
  decision: string;
  confirmed: boolean;
  action_reason: string;
  action_title: string;
  action_summary: string;
  ui_target: string;
  approval_id: number;
  approval_kind: string;
  endpoint: string;
  details: string[];
  message: string;
  note_supplied: boolean;
};

export type OperatorApprovalHistory = {
  approval_id: number;
  run_id: string;
  event_count: number;
  reviewed_count: number;
  confirmation_required_count: number;
  dispatched_count: number;
  blocked_count: number;
  latest_event_id: number;
  latest_timestamp: string;
  latest_status: string;
  latest_decision: string;
  action_reason: string;
  action_title: string;
  action_summary: string;
  approval_kind: string;
  ui_target: string;
  sequence: string[];
};

export type OperatorDispatchLedgerReport = {
  run_id: string;
  generated_at: string;
  total_count: number;
  dispatched_count: number;
  confirmation_required_count: number;
  reviewed_count: number;
  blocked_count: number;
  latest_action: string;
  summary: string;
  recommended_action: string;
  approval_history_count: number;
  unresolved_approval_history_count: number;
  promotion_route_count: number;
  promotion_approval_route_count: number;
  promotion_approval_history_count: number;
  unresolved_promotion_approval_history_count: number;
  approval_histories: OperatorApprovalHistory[];
  unresolved_approval_histories: OperatorApprovalHistory[];
  promotion_approval_histories: OperatorApprovalHistory[];
  unresolved_promotion_approval_histories: OperatorApprovalHistory[];
  promotion_routes: OperatorDispatchLedgerEntry[];
  entries: OperatorDispatchLedgerEntry[];
};

export type OrnithPreflightActionLedgerEntry = {
  event_id: number;
  run_id: string;
  timestamp: string;
  kind: string;
  status: "completed" | "dispatched";
  item_id: string;
  action_reason: string;
  action_summary: string;
  ui_target: string;
  context_pressure: string;
  context_tokens: number;
  context_target_tokens: number;
  message: string;
  details: string[];
};

export type OrnithPreflightActionLedgerReport = {
  run_id: string;
  generated_at: string;
  total_count: number;
  completed_count: number;
  dispatched_count: number;
  context_checkpoint_count: number;
  handoff_refresh_count: number;
  smoke_count: number;
  latest_action: string;
  summary: string;
  recommended_action: string;
  entries: OrnithPreflightActionLedgerEntry[];
};
export type OrnithPreflightWarningRecord = {
  event_id: number;
  timestamp: string;
  source: string;
  item_id: string;
  status: "warn" | "block";
  summary: string;
  evidence: string[];
  next_action: string;
  message: string;
};

export type OrnithPreflightWarningReport = {
  run_id: string;
  generated_at: string;
  total_count: number;
  warning_count: number;
  block_count: number;
  action_context_reorient_count: number;
  latest_reorient_event_id: number;
  latest_warning: string;
  summary: string;
  recommended_action: string;
  entries: OrnithPreflightWarningRecord[];
};
export type OperatorDispatchRestartSmokeReport = {
  run_id: string;
  generated_at: string;
  status: "not_run" | "running" | "passed" | "failed";
  scenario: string;
  summary: string;
  restart_simulated: boolean;
  dispatch_event_id: number;
  compact_context_tokens: number;
  compact_context_sections: string[];
  ledger_attached: boolean;
  handoff_attached: boolean;
  replay_attached: boolean;
  context_attached: boolean;
  next_action: string;
  steps: ReadinessRehearsalStep[];
};

export type OperatorDispatchRestartSmokeLedgerEntry = {
  run_id: string;
  generated_at: string;
  status: "running" | "passed" | "failed";
  scenario: string;
  summary: string;
  restart_simulated: boolean;
  dispatch_event_id: number;
  compact_context_tokens: number;
  ledger_attached: boolean;
  handoff_attached: boolean;
  replay_attached: boolean;
  context_attached: boolean;
  step_count: number;
  passed_steps: number;
  failed_steps: number;
  next_action: string;
};

export type OperatorDispatchRestartSmokeLedgerReport = {
  generated_at: string;
  status: "never_run" | "running" | "passed" | "failed" | "mixed";
  summary: string;
  total_count: number;
  passed_count: number;
  failed_count: number;
  running_count: number;
  latest: OperatorDispatchRestartSmokeLedgerEntry | null;
  entries: OperatorDispatchRestartSmokeLedgerEntry[];
  next_action: string;
};

export type ApprovalReviewSummary = {
  id: number;
  status: "pending" | "approved" | "rejected";
  action_kind: string;
  summary: string;
  reviewed: boolean;
  review_count: number;
  latest_reviewed_at: string;
  latest_review_event_id: number;
  high_risk: boolean;
  files: string[];
};

export type HandoffBundle = {
  original_goal: string;
  current_objective: string;
  goal_evolution: GoalEvolutionReport;
  git_checkpoint: GitCheckpointReport;
  plan: string[];
  completed_work: string[];
  next_action: string;
  files_touched: string[];
  commands_and_tests: string[];
  web_sources: WebSource[];
  desktop_state: DesktopSnapshot[];
  source_evidence: SourceEvidencePreviewReport;
  readiness_source_ref_preview: ReadinessSourceRefPreviewReport;
  desktop_effect_proof: DesktopEffectProofReport;
  desktop_effect_proof_repairs: DesktopEffectProofRepairReport;
  action_context: ActionContextPack;
  self_scaffold: SelfScaffoldReport;
  self_scaffold_reviews: SelfScaffoldReviewReport;
  self_scaffold_rollback_intents: SelfScaffoldRollbackIntentReport;
  context_snapshot: ContextSnapshot;
  resume_prompt_quality: ResumePromptQualityReport;
  resume_handoff_diff: ResumeHandoffDiffReport;
  checkpoint_quality: CheckpointQualityReport;
  checkpoint_quality_resumes: CheckpointQualityResumeReport;
  promotion_audit: PromotionAuditReport;
  promotion_verification: PromotionVerificationReport;
  promotion_repair: PromotionRepairReport;
  current_task_id: string;
  task_graph: TaskNode[];
  repo_map_summary: string;
  workspace_summary: string;
  workspace_diff_summary: string;
  workspace_promotions: WorkspacePromotion[];
  patch_proposals: PatchProposal[];
  patch_applications: PatchApplication[];
  recovery_summary: string;
  recovery_steps: string[];
  model_profile_adaptation_reviews: ModelProfileAdaptationReviewSummary[];
  unresolved_blockers: string[];
  approvals: string[];
  approval_reviews: ApprovalReviewSummary[];
  acceptance_criteria: string[];
  acceptance_evidence: AcceptanceCriterionEvidence[];
  acceptance_recommendations: AcceptanceEvidenceRecommendation[];
  acceptance_recommendation_traces: AcceptanceRecommendationTrace[];
  run_health: RunHealthReport;
  completion_audit: CompletionAuditReport;
  policy_simulation: PolicySimulationReport;
  resume_decisions: ResumeDecisionReport;
  run_progress: RunProgressReport;
  report_integrity: ReportIntegrityReport;
  report_integrity_refreshes: ReportIntegrityRefreshRecord[];
  objective_readiness: ObjectiveReadinessReport;
  objective_readiness_proof_outcomes: ObjectiveReadinessProofOutcome[];
  readiness_completion: ReadinessCompletionReport;
  readiness_rehearsal: ReadinessRehearsalReport;
  action_readiness: ActionReadinessReport;
  action_readiness_decisions: ActionReadinessDecisionReport;
  autonomy_decisions: AutonomyDecisionReport;
  recovery_decisions: RecoveryDecisionReport;
  verification_outcomes: VerificationOutcomeReport;
  post_action_retries: PostActionRetryReport;
  operator_dispatches: OperatorDispatchLedgerReport;
  operator_dispatch_restart_smoke: OperatorDispatchRestartSmokeReport;
  ornith_preflight: OrnithLaunchChecklistReport;
  ornith_preflight_actions: OrnithPreflightActionLedgerReport;
  ornith_preflight_warnings: OrnithPreflightWarningReport;
  readiness_proof_history: ReadinessProofHistoryReport;
  resume_prompt: string;
};

export type ReplayEvent = {
  id: number;
  timestamp: string;
  kind: string;
  message: string;
  ok: boolean | null;
  data_keys: string[];
};

export type ReplayApproval = {
  id: number;
  status: string;
  action_kind: string;
  reason: string;
  created_at: string;
  resolved_at: string | null;
  reviewed: boolean;
  review_count: number;
  latest_reviewed_at: string;
  latest_review_event_id: number;
  preview_summary: string;
  preview_files: string[];
};

export type ReplayBundle = {
  run_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  workspace_path: string;
  original_goal: string;
  active_goal: string;
  goal_evolution: GoalEvolutionReport;
  git_checkpoint: GitCheckpointReport;
  milestone: string;
  next_action: string;
  context_pressure: string;
  context_snapshot: ContextSnapshot;
  resume_prompt_quality: ResumePromptQualityReport;
  resume_handoff_diff: ResumeHandoffDiffReport;
  checkpoint_quality: CheckpointQualityReport;
  checkpoint_quality_resumes: CheckpointQualityResumeReport;
  promotion_audit: PromotionAuditReport;
  promotion_verification: PromotionVerificationReport;
  promotion_repair: PromotionRepairReport;
  handoff: HandoffBundle;
  event_count: number;
  approval_count: number;
  source_evidence: SourceEvidencePreviewReport;
  readiness_source_ref_preview: ReadinessSourceRefPreviewReport;
  desktop_effect_proof: DesktopEffectProofReport;
  desktop_effect_proof_repairs: DesktopEffectProofRepairReport;
  action_context: ActionContextPack;
  self_scaffold: SelfScaffoldReport;
  self_scaffold_reviews: SelfScaffoldReviewReport;
  self_scaffold_rollback_intents: SelfScaffoldRollbackIntentReport;
  events: ReplayEvent[];
  approvals: ReplayApproval[];
  acceptance_evidence: AcceptanceCriterionEvidence[];
  acceptance_recommendations: AcceptanceEvidenceRecommendation[];
  acceptance_recommendation_traces: AcceptanceRecommendationTrace[];
  run_health: RunHealthReport;
  completion_audit: CompletionAuditReport;
  policy_simulation: PolicySimulationReport;
  resume_decisions: ResumeDecisionReport;
  run_progress: RunProgressReport;
  report_integrity: ReportIntegrityReport;
  report_integrity_refreshes: ReportIntegrityRefreshRecord[];
  objective_readiness: ObjectiveReadinessReport;
  objective_readiness_proof_outcomes: ObjectiveReadinessProofOutcome[];
  readiness_completion: ReadinessCompletionReport;
  readiness_rehearsal: ReadinessRehearsalReport;
  action_readiness: ActionReadinessReport;
  action_readiness_decisions: ActionReadinessDecisionReport;
  autonomy_decisions: AutonomyDecisionReport;
  recovery_decisions: RecoveryDecisionReport;
  verification_outcomes: VerificationOutcomeReport;
  post_action_retries: PostActionRetryReport;
  operator_dispatches: OperatorDispatchLedgerReport;
  operator_dispatch_restart_smoke: OperatorDispatchRestartSmokeReport;
  ornith_preflight: OrnithLaunchChecklistReport;
  ornith_preflight_actions: OrnithPreflightActionLedgerReport;
  ornith_preflight_warnings: OrnithPreflightWarningReport;
  readiness_proof_history: ReadinessProofHistoryReport;
  task_graph: TaskNode[];
  tool_calls: ToolCallRecord[];
  model_interactions: ModelInteractionRecord[];
  failure_records: FailureRecord[];
  recovery_plan: RecoveryPlan;
  recovery_history: RecoveryPlan[];
  model_profile_adaptation_reviews: ModelProfileAdaptationReviewSummary[];
  run_lease: RunLease;
  workspace_diff_summary: string;
  workspace_promotions: WorkspacePromotion[];
  patch_applications: PatchApplication[];
  markdown: string;
};

export type RunRecord = {
  id: string;
  title: string;
  goal: string;
  status: string;
  workspace_path: string;
  state: RunState;
  created_at: string;
  updated_at: string;
};

export type EventRecord = {
  id: number;
  run_id: string;
  timestamp: string;
  kind: string;
  message: string;
  data: Record<string, unknown>;
};

export type ApprovalRecord = {
  id: number;
  run_id: string;
  status: "pending" | "approved" | "rejected";
  action_kind: string;
  payload: Record<string, unknown>;
  reason: string;
  created_at: string;
  resolved_at: string | null;
};

export type ApprovalReviewRecord = {
  id: number;
  run_id: string;
  status: "pending" | "approved" | "rejected";
  action_kind: string;
  reason: string;
  created_at: string;
  resolved_at: string | null;
  summary: string;
  preview: Record<string, unknown>;
  files: string[];
  payload_keys: string[];
  high_risk: boolean;
  reviewed: boolean;
  review_count: number;
  latest_reviewed_at: string;
  latest_review_event_id: number;
};

export type OperatorActionQueueItem = {
  id: string;
  run_id: string;
  title: string;
  severity: "watch" | "blocked";
  reason: string;
  action: string;
  status: string;
  supervisor_action: string;
  priority: number;
  approval_id: number;
  approval_kind: string;
  endpoint: string;
  method: string;
  ui_target: string;
  promotion_gate: boolean;
  details: string[];
};

export type OperatorActionQueueReport = {
  generated_at: string;
  total_count: number;
  blocked_count: number;
  watch_count: number;
  approval_count: number;
  smoke_count: number;
  readiness_proof_history_count: number;
  readiness_source_ref_count: number;
  desktop_effect_proof_count: number;
  preflight_count: number;
  checkpoint_quality_count: number;
  promotion_count: number;
  promotion_approval_count: number;
  self_scaffold_count: number;
  self_scaffold_rollback_count: number;
  goal_confirmation_count: number;
  recovery_count: number;
  blocker_count: number;
  summary: string;
  items: OperatorActionQueueItem[];
};

export type OperatorActionDispatchRequest = {
  item_id: string;
  decision: "open" | "dispatch" | "approve" | "reject";
  confirmed: boolean;
  note?: string;
};

export type OperatorActionDispatchResult = {
  item_id: string;
  run_id: string;
  status: "requires_confirmation" | "dispatched" | "reviewed" | "blocked" | "not_found";
  message: string;
  action_taken: string;
  result_run_id: string;
  event_kind: string;
  queue: OperatorActionQueueReport;
};

export type SupervisorRunRecord = {
  run_id: string;
  title: string;
  previous_status: string;
  status: string;
  action: string;
  recovery_plan: string;
  pending_approvals: number;
  auto_resume_eligible: boolean;
  auto_resume_reason: string;
  lease_status: string;
  lease_owner: string;
  lease_live: boolean;
  lease_expires_at: string;
  run_health: RunHealthReport;
  report_integrity: ReportIntegrityReport;
  report_integrity_status: string;
  report_integrity_desktop_effect_proof_requires_attention: boolean;
  report_integrity_desktop_effect_proof_detail: string;
  policy_simulation: PolicySimulationReport;
  run_progress: RunProgressReport;
  goal_evolution: GoalEvolutionReport;
  goal_confirmation_requires_attention: boolean;
  goal_confirmation_action: string;
  goal_confirmation_proposed_goal: string;
  goal_confirmation_reason: string;
  goal_confirmation_approval_count: number;
  objective_readiness: ObjectiveReadinessReport;
  objective_readiness_action: string;
  action_readiness: ActionReadinessReport;
  action_readiness_decisions: ActionReadinessDecisionReport;
  action_readiness_status: string;
  action_readiness_ready: boolean;
  action_readiness_action: string;
  action_readiness_suggested_tool: string;
  action_readiness_suggested_label: string;
  desktop_effect_proof_requires_attention: boolean;
  desktop_effect_proof_action: string;
  desktop_effect_proof_after_tool: string;
  desktop_effect_proof_tool: string;
  desktop_effect_proof_detail: string;
  source_evidence: SourceEvidencePreviewReport;
  source_evidence_requires_attention: boolean;
  source_evidence_action: string;
  promotion_audit: PromotionAuditReport;
  promotion_audit_requires_attention: boolean;
  promotion_audit_action: string;
  self_scaffold: SelfScaffoldReport;
  self_scaffold_reviews: SelfScaffoldReviewReport;
  self_scaffold_rollback_intents: SelfScaffoldRollbackIntentReport;
  self_scaffold_rollback_requires_attention: boolean;
  self_scaffold_rollback_action: string;
  self_scaffold_rollback_patch_count: number;
  self_scaffold_rollback_latest_review_event_id: number;
  self_scaffold_status: string;
  self_scaffold_requires_attention: boolean;
  self_scaffold_action: string;
  self_scaffold_latest_change: string;
  readiness_smoke_required: boolean;
  readiness_smoke_status: string;
  readiness_smoke_action: string;
  readiness_smoke_latest_run_id: string;
  readiness_smoke_requires_attention: boolean;
  readiness_smoke_proof_status: string;
  readiness_smoke_proof_detail: string;
  readiness_smoke_self_scaffold_reviewed: boolean;
  readiness_smoke_post_review_handoff_preserved: boolean;
  readiness_proof_history: ReadinessProofHistoryReport;
  readiness_proof_history_status: string;
  readiness_proof_history_detail: string;
  readiness_proof_history_action: string;
  readiness_proof_history_requires_attention: boolean;
  readiness_proof_history_self_scaffold_review_count: number;
  readiness_proof_history_post_review_handoff_count: number;
  readiness_proof_history_resume_prompt_preservation_count: number;
  readiness_proof_history_readiness_claim_count: number;
  readiness_completion: ReadinessCompletionReport;
  readiness_source_refs_requires_attention: boolean;
  readiness_source_refs_action: string;
  readiness_source_refs_missing_labels: string[];
  readiness_source_refs_count: number;
  readiness_source_refs_labels: string[];
  readiness_source_ref_preview: ReadinessSourceRefPreviewReport;
  readiness_source_ref_preview_status: string;
  readiness_source_ref_preview_action: string;
  readiness_source_ref_preview_missing_evidence_labels: string[];
  readiness_source_ref_preview_missing_proof_labels: string[];
  readiness_source_ref_preview_source_labels: string[];
  readiness_source_ref_preview_proof_labels: string[];
  readiness_source_ref_preview_source_count: number;
  readiness_source_ref_preview_proof_count: number;
  operator_dispatch_restart_smoke_required: boolean;
  operator_dispatch_restart_smoke_status: string;
  operator_dispatch_restart_smoke_action: string;
  operator_dispatch_restart_smoke_latest_run_id: string;
  operator_dispatch_restart_smoke_requires_attention: boolean;
  ornith_preflight: OrnithLaunchChecklistReport;
  ornith_preflight_status: string;
  ornith_preflight_requires_attention: boolean;
  checkpoint_quality: CheckpointQualityReport;
  checkpoint_quality_requires_attention: boolean;
  checkpoint_quality_action: string;
  operator_attention_required: boolean;
  operator_attention_reasons: string[];
  operator_attention_action: string;
  operator_attention_severity: "none" | "watch" | "blocked";
  supervisor_priority: number;
};

export type SupervisorReport = {
  status: string;
  ran_at: string;
  checked: number;
  recovered: number;
  auto_resumed: number;
  waiting_approval: number;
  live: number;
  stale: number;
  auto_resume_enabled: boolean;
  auto_resume_max_runs: number;
  readiness_rehearsal_ledger: ReadinessRehearsalLedgerReport;
  operator_dispatch_restart_smoke_ledger: OperatorDispatchRestartSmokeLedgerReport;
  readiness_smoke_attention_count: number;
  readiness_proof_history_attention_count: number;
  readiness_source_ref_attention_count: number;
  desktop_effect_proof_attention_count: number;
  operator_dispatch_restart_smoke_attention_count: number;
  ornith_preflight_attention_count: number;
  checkpoint_quality_attention_count: number;
  source_evidence_attention_count: number;
  promotion_audit_attention_count: number;
  self_scaffold_attention_count: number;
  self_scaffold_rollback_attention_count: number;
  action_readiness_attention_count: number;
  action_readiness_blocked_count: number;
  goal_confirmation_attention_count: number;
  pending_approval_count: number;
  operator_recovery_count: number;
  operator_blocker_count: number;
  operator_attention_count: number;
  operator_attention_blocked_count: number;
  operator_attention_watch_count: number;
  operator_action_queue: OperatorActionQueueReport;
  runs: SupervisorRunRecord[];
};

export type ModelProfile = {
  id: string;
  display_name: string;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  context_target_tokens: number;
  memory_chars: number;
  handoff_chars: number;
  action_context_chars: number;
  critic_context_chars: number;
  goal_context_chars: number;
  plan_max_steps: number;
  json_retries: number;
  default_temperature: number;
  configured_model: string;
  effective_context_target_tokens: number;
};

export type ModelConnectionHealth = {
  ok: boolean;
  status: "ok" | "error" | "timeout";
  model: string;
  base_url: string;
  endpoint: string;
  timeout_seconds: number;
  latency_ms: number;
  response_excerpt: string;
  error: string;
};

export type ModelEvalCaseResult = {
  id: string;
  kind: string;
  ok: boolean;
  parsed: boolean;
  repaired: boolean;
  repair_strategy: string;
  fallback_needed: boolean;
  normalized_tool: string;
  patch_first_ok: boolean | null;
  summary: string;
  error: string;
  output_keys: string[];
};

export type ModelEvalSummary = {
  profile_id: string;
  fixture_path: string;
  total: number;
  parsed: number;
  ok: number;
  repaired: number;
  fallback_needed: number;
  valid_actions: number;
  invalid_actions: number;
  patch_first_pass: number;
  patch_first_fail: number;
  score: number;
  cases: ModelEvalCaseResult[];
};

export type ModelQualitySample = {
  run_id: string;
  title: string;
  kind: string;
  ok: boolean;
  repaired: boolean;
  fallback_used: boolean;
  attempts: number;
  error_type: string;
  summary: string;
  error: string;
  created_at: string;
};

export type ModelQualityPattern = {
  id: string;
  severity: "info" | "warning" | "action";
  label: string;
  count: number;
  recommendation: string;
  run_ids: string[];
};

export type ModelPromptQualityReport = {
  profile_id: string;
  generated_at: string;
  run_count: number;
  interaction_count: number;
  ok_count: number;
  failure_count: number;
  repaired_count: number;
  fallback_count: number;
  retry_count: number;
  by_kind: Record<string, number>;
  issue_counts: Record<string, number>;
  patterns: ModelQualityPattern[];
  samples: ModelQualitySample[];
  recommendations: string[];
};

export type ModelProfileAdaptationAction = {
  id: string;
  target: "json_system" | "planner_system" | "action_prompt" | "normalizer" | "eval_fixture" | "policy";
  change: "prompt_append" | "normalizer_alias" | "eval_fixture" | "policy_bias" | "manual_review";
  risk: "low" | "medium" | "high";
  title: string;
  proposed: string;
  rationale: string;
  evidence_counts: Record<string, number>;
  requires_confirmation: boolean;
};

export type ModelProfileAdaptationProposal = {
  id: string;
  profile_id: string;
  generated_at: string;
  status: "no_change" | "needs_confirmation";
  source: string;
  summary: string;
  confidence: "low" | "medium" | "high";
  confirmation_required: boolean;
  actions: ModelProfileAdaptationAction[];
  no_change_reason: string;
};

export type ModelProfileAdaptationReview = {
  id: string;
  profile_id: string;
  proposal: ModelProfileAdaptationProposal;
  decision: "accepted" | "rejected";
  reviewer_note: string;
  created_at: string;
};

export type ModelProfileAdaptationReviewSummary = {
  id: string;
  profile_id: string;
  decision: "accepted" | "rejected";
  proposal_summary: string;
  action_titles: string[];
  reviewer_note: string;
  created_at: string;
};

function requestHeaders(headers?: HeadersInit): Record<string, string> {
  const normalized: Record<string, string> = { "Content-Type": "application/json" };
  if (!headers) return normalized;
  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      normalized[key] = value;
    });
    return normalized;
  }
  if (Array.isArray(headers)) {
    headers.forEach(([key, value]) => {
      normalized[key] = value;
    });
    return normalized;
  }
  return { ...normalized, ...headers };
}

function apiViaXhr<T>(path: string, init?: RequestInit): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(init?.method ?? "GET", `${API_BASE}${path}`);
    Object.entries(requestHeaders(init?.headers)).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`${xhr.status} ${xhr.statusText || xhr.responseText}`));
        return;
      }
      try {
        resolve(xhr.responseText ? (JSON.parse(xhr.responseText) as T) : (undefined as T));
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => reject(new Error("Network request failed"));
    const body = init?.body ?? null;
    if (body && typeof body !== "string") {
      reject(new Error("XHR fallback only supports string request bodies."));
      return;
    }
    xhr.send(body);
  });
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (typeof fetch !== "function") {
    return apiViaXhr<T>(path, init);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: requestHeaders(init?.headers),
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}
