export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:9127";

export type RunState = {
  goal: string;
  proposed_goal: string | null;
  goal_revision_reason: string;
  goal_evolution: GoalEvolutionReport;
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
  action_context: ActionContextPack;
  context_budget: ContextBudget;
  context_snapshot: ContextSnapshot;
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
export type ActionContextPack = {
  run_id: string;
  generated_at: string;
  milestone: string;
  current_task_id: string;
  current_task_title: string;
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
  recent_verified_commands: string[];
  recent_verified_files: string[];
  recent_successes: string[];
  failure_ledger: string[];
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
  generated_at: string;
  estimated_tokens: number;
  sections: string[];
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

export type FailureRecord = {
  id: string;
  kind: string;
  tool: string;
  summary: string;
  count: number;
  last_seen: string;
  recovery_hint: string;
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
  message: string;
  note_supplied: boolean;
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

export type HandoffBundle = {
  original_goal: string;
  current_objective: string;
  goal_evolution: GoalEvolutionReport;
  plan: string[];
  completed_work: string[];
  next_action: string;
  files_touched: string[];
  commands_and_tests: string[];
  web_sources: WebSource[];
  desktop_state: DesktopSnapshot[];
  source_evidence: SourceEvidencePreviewReport;
  action_context: ActionContextPack;
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
  milestone: string;
  next_action: string;
  context_pressure: string;
  handoff: HandoffBundle;
  event_count: number;
  approval_count: number;
  source_evidence: SourceEvidencePreviewReport;
  action_context: ActionContextPack;
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
  details: string[];
};

export type OperatorActionQueueReport = {
  generated_at: string;
  total_count: number;
  blocked_count: number;
  watch_count: number;
  approval_count: number;
  smoke_count: number;
  preflight_count: number;
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
  policy_simulation: PolicySimulationReport;
  run_progress: RunProgressReport;
  objective_readiness: ObjectiveReadinessReport;
  objective_readiness_action: string;
  source_evidence: SourceEvidencePreviewReport;
  source_evidence_requires_attention: boolean;
  source_evidence_action: string;
  readiness_smoke_required: boolean;
  readiness_smoke_status: string;
  readiness_smoke_action: string;
  readiness_smoke_latest_run_id: string;
  readiness_smoke_requires_attention: boolean;
  operator_dispatch_restart_smoke_required: boolean;
  operator_dispatch_restart_smoke_status: string;
  operator_dispatch_restart_smoke_action: string;
  operator_dispatch_restart_smoke_latest_run_id: string;
  operator_dispatch_restart_smoke_requires_attention: boolean;
  ornith_preflight: OrnithLaunchChecklistReport;
  ornith_preflight_status: string;
  ornith_preflight_requires_attention: boolean;
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
  operator_dispatch_restart_smoke_attention_count: number;
  ornith_preflight_attention_count: number;
  source_evidence_attention_count: number;
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

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}
