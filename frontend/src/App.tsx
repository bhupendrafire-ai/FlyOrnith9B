import { FormEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  Brain,
  Check,
  FileText,
  FolderOpen,
  Gauge,
  GitPullRequest,
  Globe,
  ListChecks,
  Map,
  Monitor,
  Pause,
  Play,
  RotateCcw,
  Send,
  Share,
  Square,
  Target,
  Terminal,
  Wrench,
  X,
} from "lucide-react";
import {
  API_BASE,
  ActionReadinessDecisionReport,
  ActionReadinessReport,
  ApprovalReviewRecord,
  AutonomyDecisionReport,
  CheckpointQualityReport,
  CheckpointQualityResumeReport,
  CompletionAuditReport,
  CompletionVerificationPolicy,
  DesktopEffectProofReport,
  EventRecord,
  ModelConnectionHealth,
  ModelEvalSummary,
  ModelProfileAdaptationProposal,
  ModelProfileAdaptationReview,
  ModelProfile,
  ModelPromptQualityReport,
  ObjectiveReadinessReport,
  OperatorActionDispatchResult,
  OperatorActionQueueItem,
  OperatorApprovalHistory,
  OperatorActionQueueReport,
  OrnithLaunchChecklistReport,
  OrnithPreflightActionLedgerReport,
  OrnithPreflightWarningReport,
  OperatorDispatchLedgerReport,
  OperatorDispatchRestartSmokeLedgerReport,
  OperatorDispatchRestartSmokeReport,
  PolicySimulationReport,
  PromotionAuditReport,
  PromotionRepairReport,
  PromotionVerificationReport,
  ReadinessCompletionReport,
  ReadinessProofHistoryReport,
  ReadinessSourceRefPreviewReport,
  ReadinessRehearsalLedgerReport,
  ReadinessRehearsalReport,
  RecoveryDecisionReport,
  ReplayBundle,
  ReportIntegrityReport,
  ResumeDecisionReport,
  ResumeHandoffDiffReport,
  ResumePromptQualityReport,
  RunRecord,
  RunHealthReport,
  RunProgressReport,
  SourceEvidencePreviewReport,
  SupervisorReport,
  VerificationOutcomeReport,
  api,
} from "./api";
import { buildDesktopApprovalDashboard } from "./desktopApprovalGate";
import { buildDesktopEffectProofGate } from "./desktopEffectProofGate";
import { approvalDecisionLabel, buildGoalConfirmationDashboard } from "./goalConfirmationGate";
import { buildPatchApprovalCards, type PatchApprovalCard } from "./patchApprovalGate";
import { buildReadinessSourceRefGate } from "./readinessSourceRefGate";
import { buildSourcePromotionApprovalDashboard } from "./sourcePromotionApprovalGate";
import {
  buildActivityFeed,
  type ActivityFeedItem,
  type WorkbenchArtifact,
} from "./activityFeed";
import { formatLocalTextTimestamps, formatLocalTimestamp } from "./time";

const emptyGoal =
  "Inspect this workspace, check Obsidian first, make a small safe improvement, run checks, and summarize.";

type QueueFilter = "all" | "promotion_approvals" | "proof_reviews";
type WorkbenchView = "focus" | "activity" | "artifacts" | "runs" | "settings";
type ApprovalMode = "always_ask" | "balanced" | "workspace_autopilot" | "bypass_permissions";

const workbenchViews: WorkbenchView[] = ["focus", "activity", "artifacts", "runs", "settings"];
const approvalModes: Array<{ value: ApprovalMode; label: string; help: string }> = [
  { value: "balanced", label: "Balanced", help: "Ask for high-risk actions, allow normal workspace checks." },
  { value: "always_ask", label: "Always Ask", help: "Require approval for every mutation or active PC interaction." },
  {
    value: "workspace_autopilot",
    label: "Workspace Autopilot",
    help: "Allow isolated workspace patches, still ask for source promotion and risky PC actions.",
  },
  {
    value: "bypass_permissions",
    label: "Bypass Permissions",
    help: "Minimize approval stops while still blocking credentials, downloads, global installs, and destructive commands.",
  },
];

const proofReviewQueueReasons = new Set([
  "readiness_proof_history",
  "readiness_source_refs",
  "source_evidence",
  "desktop_effect_proof",
  "self_scaffold_rollback",
]);

export function App() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [selected, setSelected] = useState<RunRecord | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [approvals, setApprovals] = useState<ApprovalReviewRecord[]>([]);
  const [replay, setReplay] = useState<ReplayBundle | null>(null);
  const [completionAudit, setCompletionAudit] = useState<CompletionAuditReport | null>(null);
  const [runProgress, setRunProgress] = useState<RunProgressReport | null>(null);
  const [reportIntegrity, setReportIntegrity] = useState<ReportIntegrityReport | null>(null);
  const [checkpointQuality, setCheckpointQuality] = useState<CheckpointQualityReport | null>(null);
  const [objectiveReadiness, setObjectiveReadiness] = useState<ObjectiveReadinessReport | null>(null);
  const [readinessCompletion, setReadinessCompletion] = useState<ReadinessCompletionReport | null>(null);
  const [readinessSourceRefs, setReadinessSourceRefs] = useState<ReadinessSourceRefPreviewReport | null>(null);
  const [readinessRehearsal, setReadinessRehearsal] = useState<ReadinessRehearsalReport | null>(null);
  const [readinessRehearsalLedger, setReadinessRehearsalLedger] =
    useState<ReadinessRehearsalLedgerReport | null>(null);
  const [policySimulation, setPolicySimulation] = useState<PolicySimulationReport | null>(null);
  const [resumeDecisions, setResumeDecisions] = useState<ResumeDecisionReport | null>(null);
  const [resumePromptQuality, setResumePromptQuality] = useState<ResumePromptQualityReport | null>(null);
  const [resumeHandoffDiff, setResumeHandoffDiff] = useState<ResumeHandoffDiffReport | null>(null);
  const [promotionAudit, setPromotionAudit] = useState<PromotionAuditReport | null>(null);
  const [promotionVerification, setPromotionVerification] = useState<PromotionVerificationReport | null>(null);
  const [actionReadiness, setActionReadiness] = useState<ActionReadinessReport | null>(null);
  const [actionReadinessDecisions, setActionReadinessDecisions] = useState<ActionReadinessDecisionReport | null>(null);
  const [autonomyDecisions, setAutonomyDecisions] = useState<AutonomyDecisionReport | null>(null);
  const [recoveryDecisions, setRecoveryDecisions] = useState<RecoveryDecisionReport | null>(null);
  const [verificationOutcomes, setVerificationOutcomes] = useState<VerificationOutcomeReport | null>(null);
  const [completionPolicy, setCompletionPolicy] = useState<CompletionVerificationPolicy | null>(null);
  const [ornithPreflight, setOrnithPreflight] = useState<OrnithLaunchChecklistReport | null>(null);
  const [selectedOrnithPreflight, setSelectedOrnithPreflight] = useState<OrnithLaunchChecklistReport | null>(null);
  const [ornithPreflightActions, setOrnithPreflightActions] = useState<OrnithPreflightActionLedgerReport | null>(null);
  const [sourceEvidence, setSourceEvidence] = useState<SourceEvidencePreviewReport | null>(null);
  const [desktopEffectProof, setDesktopEffectProof] = useState<DesktopEffectProofReport | null>(null);
  const [supervisor, setSupervisor] = useState<SupervisorReport | null>(null);
  const [operatorActionQueue, setOperatorActionQueue] = useState<OperatorActionQueueReport | null>(null);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("all");
  const [operatorDispatches, setOperatorDispatches] = useState<OperatorDispatchLedgerReport | null>(null);
  const [operatorDispatchRestartSmoke, setOperatorDispatchRestartSmoke] =
    useState<OperatorDispatchRestartSmokeReport | null>(null);
  const [operatorDispatchRestartSmokeLedger, setOperatorDispatchRestartSmokeLedger] =
    useState<OperatorDispatchRestartSmokeLedgerReport | null>(null);
  const [operatorDispatchMessage, setOperatorDispatchMessage] = useState("");
  const [dispatchSmokeBusy, setDispatchSmokeBusy] = useState(false);
  const [modelProfile, setModelProfile] = useState<ModelProfile | null>(null);
  const [modelHealth, setModelHealth] = useState<ModelConnectionHealth | null>(null);
  const [modelEval, setModelEval] = useState<ModelEvalSummary | null>(null);
  const [modelQuality, setModelQuality] = useState<ModelPromptQualityReport | null>(null);
  const [modelAdaptation, setModelAdaptation] = useState<ModelProfileAdaptationProposal | null>(null);
  const [modelAdaptationReviews, setModelAdaptationReviews] = useState<ModelProfileAdaptationReview[]>([]);
  const [notes, setNotes] = useState("");
  const [goal, setGoal] = useState(emptyGoal);
  const [criteria, setCriteria] = useState("Dashboard starts locally\nObsidian checkpoint is written");
  const [projectPath, setProjectPath] = useState("");
  const [webEnabled, setWebEnabled] = useState(true);
  const [browserEnabled, setBrowserEnabled] = useState(true);
  const [desktopEnabled, setDesktopEnabled] = useState(true);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("balanced");
  const [goalProposal, setGoalProposal] = useState("");
  const [steer, setSteer] = useState("");
  const [busy, setBusy] = useState(false);
  const [creatingRun, setCreatingRun] = useState(false);
  const [rehearsalBusy, setRehearsalBusy] = useState(false);
  const [showAttentionOnly, setShowAttentionOnly] = useState(false);
  const [activeView, setActiveView] = useState<WorkbenchView>("focus");
  const [focusFullscreen, setFocusFullscreen] = useState(false);
  const [error, setError] = useState("");

  const goalConfirmationGate = useMemo(
    () =>
      buildGoalConfirmationDashboard({
        approvals,
        operatorActionQueueItems: operatorActionQueue?.items ?? [],
      }),
    [approvals, operatorActionQueue],
  );
  const sourcePromotionApprovalGate = useMemo(
    () =>
      buildSourcePromotionApprovalDashboard({
        approvals,
        operatorActionQueueItems: operatorActionQueue?.items ?? [],
      }),
    [approvals, operatorActionQueue],
  );
  const desktopApprovalGate = useMemo(
    () =>
      buildDesktopApprovalDashboard({
        approvals,
        operatorActionQueueItems: operatorActionQueue?.items ?? [],
      }),
    [approvals, operatorActionQueue],
  );
  const pendingApprovals = goalConfirmationGate.pendingApprovals;
  const reviewedPendingApprovals = goalConfirmationGate.reviewedPendingApprovals;
  const unreviewedPendingApprovals = goalConfirmationGate.unreviewedPendingApprovals;
  const orderedPendingApprovals = useMemo(() => {
    const seen = new Set<number>();
    return [
      ...goalConfirmationGate.goalApprovals,
      ...desktopApprovalGate.desktopApprovals,
      ...sourcePromotionApprovalGate.sourcePromotionApprovals,
      ...unreviewedPendingApprovals,
      ...reviewedPendingApprovals,
    ].filter((approval) => {
      if (seen.has(approval.id)) return false;
      seen.add(approval.id);
      return true;
    });
  }, [goalConfirmationGate, desktopApprovalGate, sourcePromotionApprovalGate, unreviewedPendingApprovals, reviewedPendingApprovals]);
  const activeOrnithPreflight = selectedOrnithPreflight ?? ornithPreflight;
  const reportIntegrityRefreshes =
    replay?.report_integrity_refreshes ??
    selected?.state.report_integrity_refreshes ??
    selected?.state.handoff_summary.report_integrity_refreshes ??
    [];
  const latestReportIntegrityRefresh = reportIntegrityRefreshes[0];
  const checkpointQualityResumes = selectCheckpointQualityResumes(
    selected?.state.checkpoint_quality_resumes,
    selected?.state.handoff_summary.checkpoint_quality_resumes,
    replay?.checkpoint_quality_resumes,
  );
  const preflightWarnings: OrnithPreflightWarningReport | null =
    replay?.ornith_preflight_warnings ?? selected?.state.handoff_summary.ornith_preflight_warnings ?? null;
  const readinessProofHistory: ReadinessProofHistoryReport | null =
    replay?.readiness_proof_history ?? selected?.state.handoff_summary.readiness_proof_history ?? null;
  const preflightWarningGate = readinessCompletion?.checks.find(
    (check) => check.id === "ornith_preflight_warnings",
  );
  const handoffActionContext = selected?.state.handoff_summary.action_context;
  const selfScaffold = replay?.self_scaffold ?? selected?.state.self_scaffold ?? selected?.state.handoff_summary.self_scaffold;
  const selfScaffoldReviews =
    replay?.self_scaffold_reviews ?? selected?.state.self_scaffold_reviews ?? selected?.state.handoff_summary.self_scaffold_reviews;
  const selfScaffoldRollbackIntents =
    replay?.self_scaffold_rollback_intents ??
    selected?.state.self_scaffold_rollback_intents ??
    selected?.state.handoff_summary.self_scaffold_rollback_intents;
  const displayedQueueItems = useMemo(() => {
    const items = operatorActionQueue?.items ?? [];
    if (queueFilter === "promotion_approvals") return items.filter((item) => item.promotion_gate);
    if (queueFilter === "proof_reviews") return items.filter((item) => proofReviewQueueReasons.has(item.reason));
    return items;
  }, [operatorActionQueue, queueFilter]);
  const readinessSourceRefGate = useMemo(
    () =>
      buildReadinessSourceRefGate({
        selectedId,
        actionReadiness,
        readinessSourceRefs,
        operatorActionQueueItems: operatorActionQueue?.items ?? [],
      }),
    [selectedId, actionReadiness, readinessSourceRefs, operatorActionQueue],
  );
  const selectedSourceRefQueueItem = readinessSourceRefGate.queueItem;
  const desktopEffectProofGate = useMemo(
    () =>
      buildDesktopEffectProofGate({
        selectedId,
        actionContext: selected?.state.action_context ?? handoffActionContext,
        operatorActionQueueItems: operatorActionQueue?.items ?? [],
      }),
    [selectedId, selected, handoffActionContext, operatorActionQueue],
  );
  const selectedDesktopEffectQueueItem = desktopEffectProofGate.queueItem;
  const desktopEffectIntegrityChecks = useMemo(
    () =>
      (reportIntegrity?.checks ?? []).filter(
        (item) => item.status !== "ok" && item.section.startsWith("handoff.desktop_effect_proof"),
      ),
    [reportIntegrity],
  );
  const desktopEffectIntegrityNeedsRepair = desktopEffectIntegrityChecks.length > 0;
  const activeDesktopEffectProofRepairs =
    replay?.desktop_effect_proof_repairs ??
    selected?.state.desktop_effect_proof_repairs ??
    selected?.state.handoff_summary.desktop_effect_proof_repairs ??
    null;
  const patchApprovalCards = useMemo(
    () =>
      buildPatchApprovalCards({
        patchProposals: selected?.state.patch_proposals ?? [],
        promotionRepair: selected?.state.promotion_repair ?? null,
        operatorActionQueueItems: operatorActionQueue?.items ?? [],
      }),
    [selected, operatorActionQueue],
  );
  const progress = useMemo(() => {
    const state = selected?.state;
    if (!state || state.current_plan.length === 0) return 0;
    return Math.min(100, Math.round((state.completed_steps.length / state.current_plan.length) * 100));
  }, [selected]);
  const supervisorRunById = useMemo(() => {
    return new globalThis.Map((supervisor?.runs ?? []).map((run) => [run.run_id, run]));
  }, [supervisor]);
  const selectedSupervisorRun = selectedId ? supervisorRunById.get(selectedId) : undefined;
  const prioritizedRuns = useMemo(() => {
    return [...runs].sort((a, b) => {
      const aSupervisor = supervisorRunById.get(a.id);
      const bSupervisor = supervisorRunById.get(b.id);
      const aPriority = aSupervisor?.supervisor_priority ?? 0;
      const bPriority = bSupervisor?.supervisor_priority ?? 0;
      if (aPriority !== bPriority) return bPriority - aPriority;
      return b.updated_at.localeCompare(a.updated_at);
    });
  }, [runs, supervisorRunById]);
  const visibleRuns = useMemo(() => {
    if (!showAttentionOnly) return prioritizedRuns;
    return prioritizedRuns.filter((run) => supervisorRunById.get(run.id)?.operator_attention_required);
  }, [prioritizedRuns, showAttentionOnly, supervisorRunById]);
  const canResumeRun = (run: RunRecord | null | undefined) =>
    Boolean(run && !["running", "completed", "canceled", "waiting_approval"].includes(run.status));
  const chatThreadById = useMemo(() => {
    return new globalThis.Map(
      prioritizedRuns.map((run) => {
        const supervisorRun = supervisorRunById.get(run.id);
        const artifactCount =
          run.state.web_sources.length +
          run.state.desktop_snapshots.length +
          run.state.patch_proposals.length +
          run.state.patch_applications.length +
          run.state.workspace_diff.files.length +
          (run.state.handoff_summary.resume_prompt ? 1 : 0);
        const messageCount =
          run.state.model_interactions.length +
          run.state.tool_calls.length +
          run.state.commands_run.length +
          run.state.facts_learned.length +
          1;
        return [
          run.id,
          {
            artifactCount,
            messageCount,
            resumeHint:
              run.state.next_step ||
              supervisorRun?.operator_attention_action ||
              run.state.latest_summary ||
              run.state.handoff_summary.next_action ||
              "Open this chat to resume.",
            requiresAttention: Boolean(supervisorRun?.operator_attention_required),
          },
        ];
      }),
    );
  }, [prioritizedRuns, supervisorRunById]);
  const selectedQueueItems = useMemo(
    () => (operatorActionQueue?.items ?? []).filter((item) => !selectedId || item.run_id === selectedId),
    [operatorActionQueue, selectedId],
  );
  const artifactItems = useMemo<WorkbenchArtifact[]>(() => {
    if (!selected) return [];
    const items: WorkbenchArtifact[] = [];
    if (replay) {
      items.push({
        id: "replay-md",
        kind: "replay",
        title: "Replay Markdown",
        summary: `${replay.event_count} events, ${replay.approval_count} approvals, ${replay.context_pressure} context`,
        timestamp: replay.updated_at,
        href: `${API_BASE}/api/runs/${replay.run_id}/replay.md`,
      });
    }
    if (notes) {
      items.push({
        id: "obsidian-note",
        kind: "note",
        title: "Obsidian Run Note",
        summary: `${notes.length} characters of checkpoint context`,
        timestamp: selected.updated_at,
      });
    }
    selected.state.web_sources.slice(-8).forEach((source) => {
      items.push({
        id: `web-${source.id}`,
        kind: "web",
        title: source.title || source.url,
        summary: source.excerpt || source.citation || source.url,
        timestamp: source.timestamp,
        href: source.url,
      });
    });
    selected.state.desktop_snapshots.slice(-8).forEach((snapshot) => {
      items.push({
        id: `desktop-${snapshot.id}`,
        kind: "desktop",
        title: snapshot.title,
        summary: snapshot.summary || snapshot.path,
        timestamp: snapshot.timestamp,
        path: snapshot.path,
      });
    });
    selected.state.patch_proposals.slice(-6).forEach((patch) => {
      items.push({
        id: `patch-${patch.id}`,
        kind: "patch",
        title: patch.title,
        summary: patch.summary,
        timestamp: selected.updated_at,
      });
    });
    selected.state.patch_applications.slice(-6).forEach((patch) => {
      items.push({
        id: `patch-apply-${patch.id}`,
        kind: "patch-app",
        title: patch.status,
        summary: patch.summary,
        timestamp: patch.applied_at || selected.updated_at,
      });
    });
    selected.state.workspace_diff.files.slice(0, 10).forEach((file) => {
      items.push({
        id: `diff-${file.path}`,
        kind: "diff",
        title: file.path,
        summary: `${file.status}${file.truncated ? " / truncated" : ""}`,
        timestamp: selected.updated_at,
      });
    });
    approvals.slice(0, 8).forEach((approval) => {
      items.push({
        id: `approval-${approval.id}`,
        kind: "approval",
        title: `${approval.action_kind} ${approval.status}`,
        summary: approval.summary,
        timestamp: approval.latest_reviewed_at || "",
      });
    });
    return items;
  }, [selected, replay, notes, approvals]);
  const activeConversation = useMemo<ActivityFeedItem[]>(
    () =>
      buildActivityFeed({
        selected,
        events,
        approvals,
        queueItems: selectedQueueItems,
        artifacts: artifactItems,
        actionReadiness,
        recoveryDecisions,
      }),
    [selected, events, approvals, selectedQueueItems, artifactItems, actionReadiness, recoveryDecisions],
  );
  const requiredActionItems = useMemo(
    () => activeConversation.filter((item) => item.kind === "required_action"),
    [activeConversation],
  );
  const timelineItems = useMemo(
    () => activeConversation.filter((item) => item.kind !== "required_action"),
    [activeConversation],
  );
  const firstRequiredAction = requiredActionItems[0];
  const requiredActionLabel =
    requiredActionItems.length > 0 && requiredActionItems.every((item) => item.actionType === "resume")
      ? "Paused"
      : "Needs You";
  const selectedProjectPath =
    selected?.state.workspace_isolation.workspace_path ||
    selected?.workspace_path ||
    selected?.state.workspace_isolation.source_path ||
    "";

  function clearTransientFetchError() {
    setError((current) => (current === "Failed to fetch" || current === "Network request failed" ? "" : current));
  }

  async function refreshRuns(nextSelectedId?: string) {
    const list = await api<RunRecord[]>("/api/runs");
    setRuns(list);
    const id = nextSelectedId || selectedId || list[0]?.id || "";
    if (id) {
      setSelectedId(id);
      const immediate = list.find((run) => run.id === id);
      if (immediate) setSelected(immediate);
    }
    clearTransientFetchError();
  }

  async function refreshSupervisor() {
    const report = await api<SupervisorReport>("/api/supervisor");
    setSupervisor(report);
    if (queueFilter === "all") {
      setOperatorActionQueue(report.operator_action_queue);
    } else {
      await refreshOperatorActions(queueFilter);
    }
    setOperatorDispatchRestartSmokeLedger(report.operator_dispatch_restart_smoke_ledger);
    clearTransientFetchError();
  }

  async function refreshOperatorActions(nextFilter: QueueFilter = queueFilter) {
    const filterParam = nextFilter === "all" ? "" : `?filter=${encodeURIComponent(nextFilter)}`;
    const report = await api<OperatorActionQueueReport>(`/api/operator-actions${filterParam}`);
    setOperatorActionQueue(report);
  }

  function changeQueueFilter(nextFilter: QueueFilter) {
    setQueueFilter(nextFilter);
    if (nextFilter === "all" && supervisor) {
      setOperatorActionQueue(supervisor.operator_action_queue);
      return;
    }
    void refreshOperatorActions(nextFilter);
  }

  async function refreshOperatorDispatches() {
    const report = await api<OperatorDispatchLedgerReport>("/api/operator-actions/dispatches");
    setOperatorDispatches(report);
  }

  async function refreshOperatorDispatchRestartSmokeLedger() {
    const report = await api<OperatorDispatchRestartSmokeLedgerReport>("/api/rehearsals/operator-dispatch-restart");
    setOperatorDispatchRestartSmokeLedger(report);
  }

  async function refreshCompletionPolicy() {
    const policy = await api<CompletionVerificationPolicy>("/api/completion-policy");
    setCompletionPolicy(policy);
  }

  async function refreshReadinessRehearsalLedger() {
    const report = await api<ReadinessRehearsalLedgerReport>("/api/rehearsals/readiness-claim");
    setReadinessRehearsalLedger(report);
  }

  async function refreshOrnithPreflight() {
    const report = await api<OrnithLaunchChecklistReport>("/api/ornith/preflight");
    setOrnithPreflight(report);
  }

  async function refreshModelProfile() {
    const profile = await api<ModelProfile>("/api/model-profile");
    setModelProfile(profile);
  }

  async function refreshModelHealth() {
    const result = await api<ModelConnectionHealth>("/api/model-profile/health");
    setModelHealth(result);
  }

  async function refreshModelEval() {
    const result = await api<ModelEvalSummary>("/api/model-profile/eval");
    setModelEval(result);
  }

  async function refreshModelQuality() {
    const result = await api<ModelPromptQualityReport>("/api/model-profile/quality");
    setModelQuality(result);
  }

  async function refreshModelAdaptation() {
    const result = await api<ModelProfileAdaptationProposal>("/api/model-profile/adaptation");
    setModelAdaptation(result);
  }

  async function refreshModelAdaptationReviews() {
    const result = await api<ModelProfileAdaptationReview[]>("/api/model-profile/adaptation/reviews");
    setModelAdaptationReviews(result);
  }

  async function refreshSelected(id = selectedId) {
    if (!id) return;
    const [
      run,
      eventList,
      approvalList,
      noteResult,
      replayResult,
      auditResult,
      healthResult,
      progressResult,
      integrityResult,
      checkpointQualityResult,
      objectiveReadinessResult,
      readinessCompletionResult,
      readinessSourceRefsResult,
      readinessRehearsalResult,
      policyResult,
      resumeDecisionResult,
      resumePromptQualityResult,
      resumeHandoffDiffResult,
      promotionAuditResult,
      promotionVerificationResult,
      promotionRepairResult,
      actionReadinessResult,
      actionReadinessDecisionResult,
      autonomyDecisionResult,
      recoveryDecisionResult,
      verificationOutcomeResult,
      operatorDispatchResult,
      operatorDispatchRestartSmokeResult,
      ornithPreflightResult,
      ornithPreflightActionResult,
      sourceEvidenceResult,
      desktopEffectProofResult,
    ] = await Promise.all([
      api<RunRecord>(`/api/runs/${id}`),
      api<EventRecord[]>(`/api/runs/${id}/events`),
      api<ApprovalReviewRecord[]>(`/api/runs/${id}/approval-reviews`),
      api<{ note: string }>(`/api/runs/${id}/notes`),
      api<ReplayBundle>(`/api/runs/${id}/replay`),
      api<CompletionAuditReport>(`/api/runs/${id}/completion-audit`),
      api<RunHealthReport>(`/api/runs/${id}/health`),
      api<RunProgressReport>(`/api/runs/${id}/progress`),
      api<ReportIntegrityReport>(`/api/runs/${id}/report-integrity`),
      api<CheckpointQualityReport>(`/api/runs/${id}/checkpoint-quality`),
      api<ObjectiveReadinessReport>(`/api/runs/${id}/objective-readiness`),
      api<ReadinessCompletionReport>(`/api/runs/${id}/readiness-completion`),
      api<ReadinessSourceRefPreviewReport>(`/api/runs/${id}/readiness-source-refs`),
      api<ReadinessRehearsalReport>(`/api/runs/${id}/readiness-rehearsal`),
      api<PolicySimulationReport>(`/api/runs/${id}/policy-simulation`),
      api<ResumeDecisionReport>(`/api/runs/${id}/resume-decisions`),
      api<ResumePromptQualityReport>(`/api/runs/${id}/resume-quality`),
      api<ResumeHandoffDiffReport>(`/api/runs/${id}/resume-handoff-diff`),
      api<PromotionAuditReport>(`/api/runs/${id}/promotion-audit`),
      api<PromotionVerificationReport>(`/api/runs/${id}/promotion-verification`),
      api<PromotionRepairReport>(`/api/runs/${id}/promotion-repair`),
      api<ActionReadinessReport>(`/api/runs/${id}/action-readiness`),
      api<ActionReadinessDecisionReport>(`/api/runs/${id}/action-readiness-decisions`),
      api<AutonomyDecisionReport>(`/api/runs/${id}/autonomy-decisions`),
      api<RecoveryDecisionReport>(`/api/runs/${id}/recovery-decisions`),
      api<VerificationOutcomeReport>(`/api/runs/${id}/verification-outcomes`),
      api<OperatorDispatchLedgerReport>(`/api/runs/${id}/operator-dispatches`),
      api<OperatorDispatchRestartSmokeReport>(`/api/runs/${id}/operator-dispatch-restart-smoke`),
      api<OrnithLaunchChecklistReport>(`/api/runs/${id}/ornith-preflight`),
      api<OrnithPreflightActionLedgerReport>(`/api/runs/${id}/ornith-preflight-actions`),
      api<SourceEvidencePreviewReport>(`/api/runs/${id}/source-evidence`),
      api<DesktopEffectProofReport>(`/api/runs/${id}/desktop-effect-proof`),
    ]);
    setSelected({
      ...run,
      state: {
        ...run.state,
        run_health: healthResult,
        run_progress: progressResult,
        report_integrity: integrityResult,
        checkpoint_quality: checkpointQualityResult,
        checkpoint_quality_resumes: replayResult.checkpoint_quality_resumes,
        objective_readiness: objectiveReadinessResult,
        readiness_completion: readinessCompletionResult,
        readiness_rehearsal: readinessRehearsalResult,
        resume_prompt_quality: resumePromptQualityResult,
        resume_handoff_diff: resumeHandoffDiffResult,
        promotion_audit: promotionAuditResult,
        promotion_verification: promotionVerificationResult,
        promotion_repair: promotionRepairResult,
        action_readiness: actionReadinessResult,
        action_readiness_decisions: actionReadinessDecisionResult,
        autonomy_decisions: autonomyDecisionResult,
        recovery_decisions: recoveryDecisionResult,
        verification_outcomes: verificationOutcomeResult,
        operator_dispatches: operatorDispatchResult,
        operator_dispatch_restart_smoke: operatorDispatchRestartSmokeResult,
        ornith_preflight: ornithPreflightResult,
        ornith_preflight_actions: ornithPreflightActionResult,
        source_evidence: sourceEvidenceResult,
        desktop_effect_proof: desktopEffectProofResult,
        desktop_effect_proof_repairs: replayResult.desktop_effect_proof_repairs,
        self_scaffold_reviews: replayResult.self_scaffold_reviews,
        self_scaffold_rollback_intents: replayResult.self_scaffold_rollback_intents,
        readiness_source_ref_preview: readinessSourceRefsResult,
        handoff_summary: {
          ...run.state.handoff_summary,
          checkpoint_quality: replayResult.handoff.checkpoint_quality,
          checkpoint_quality_resumes: replayResult.handoff.checkpoint_quality_resumes,
          ornith_preflight_warnings: replayResult.handoff.ornith_preflight_warnings,
          readiness_proof_history: replayResult.handoff.readiness_proof_history,
          readiness_source_ref_preview: replayResult.handoff.readiness_source_ref_preview,
          desktop_effect_proof: replayResult.handoff.desktop_effect_proof,
          desktop_effect_proof_repairs: replayResult.handoff.desktop_effect_proof_repairs,
          self_scaffold_reviews: replayResult.handoff.self_scaffold_reviews,
          self_scaffold_rollback_intents: replayResult.handoff.self_scaffold_rollback_intents,
        },
      },
    });
    setEvents(eventList);
    setApprovals(approvalList);
    setReplay(replayResult);
    setCompletionAudit(auditResult);
    setRunProgress(progressResult);
    setReportIntegrity(integrityResult);
    setCheckpointQuality(checkpointQualityResult);
    setObjectiveReadiness(objectiveReadinessResult);
    setReadinessCompletion(readinessCompletionResult);
    setReadinessSourceRefs(readinessSourceRefsResult);
    setReadinessRehearsal(readinessRehearsalResult);
    setPolicySimulation(policyResult);
    setResumeDecisions(resumeDecisionResult);
    setResumePromptQuality(resumePromptQualityResult);
    setResumeHandoffDiff(resumeHandoffDiffResult);
    setPromotionAudit(promotionAuditResult);
    setPromotionVerification(promotionVerificationResult);
    setActionReadiness(actionReadinessResult);
    setActionReadinessDecisions(actionReadinessDecisionResult);
    setAutonomyDecisions(autonomyDecisionResult);
    setRecoveryDecisions(recoveryDecisionResult);
    setVerificationOutcomes(verificationOutcomeResult);
    setOperatorDispatches(operatorDispatchResult);
    setOperatorDispatchRestartSmoke(operatorDispatchRestartSmokeResult);
    setSelectedOrnithPreflight(ornithPreflightResult);
    setOrnithPreflightActions(ornithPreflightActionResult);
    setSourceEvidence(sourceEvidenceResult);
    setDesktopEffectProof(desktopEffectProofResult);
    setNotes(noteResult.note);
    clearTransientFetchError();
  }

  useEffect(() => {
    refreshOperatorActions(queueFilter).catch((err: Error) => setError(err.message));
  }, [queueFilter]);

  useEffect(() => {
    refreshRuns().catch((err: Error) => setError(err.message));
    refreshSupervisor().catch((err: Error) => setError(err.message));
    refreshOperatorDispatches().catch((err: Error) => setError(err.message));
    refreshOperatorDispatchRestartSmokeLedger().catch((err: Error) => setError(err.message));
    refreshCompletionPolicy().catch((err: Error) => setError(err.message));
    refreshReadinessRehearsalLedger().catch((err: Error) => setError(err.message));
    refreshOrnithPreflight().catch((err: Error) => setError(err.message));
    refreshModelProfile().catch((err: Error) => setError(err.message));
    refreshModelHealth().catch((err: Error) => setError(err.message));
    refreshModelEval().catch((err: Error) => setError(err.message));
    refreshModelQuality().catch((err: Error) => setError(err.message));
    refreshModelAdaptation().catch((err: Error) => setError(err.message));
    refreshModelAdaptationReviews().catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    refreshSelected().catch((err: Error) => setError(err.message));
    if (!selectedId) return;
    const source = new EventSource(`${API_BASE}/api/runs/${selectedId}/stream`);
    source.onmessage = () => {
      refreshSelected(selectedId).catch((err: Error) => setError(err.message));
      refreshRuns(selectedId).catch((err: Error) => setError(err.message));
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [selectedId]);

  async function createRun(event: FormEvent) {
    event.preventDefault();
    setCreatingRun(true);
    setBusy(true);
    setError("");
    try {
      const run = await api<RunRecord>("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          goal,
          acceptance_criteria: criteria
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
          workspace_path: projectPath.trim() || undefined,
          tool_profile: "balanced",
          approval_mode: approvalMode,
          web_enabled: webEnabled,
          browser_enabled: browserEnabled,
          desktop_enabled: desktopEnabled,
        }),
      });
      setSelected(run);
      setSelectedId(run.id);
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setEvents([]);
      setApprovals([]);
      setReplay(null);
      setNotes("");
      void Promise.all([
        refreshRuns(run.id),
        refreshSelected(run.id),
        refreshSupervisor(),
        refreshOperatorDispatches(),
      ]).catch((err: Error) => setError(err.message));
      setSelectedId(run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingRun(false);
      setBusy(false);
    }
  }

  async function control(action: "pause" | "resume" | "cancel", runId = selectedId) {
    if (!runId) return;
    setBusy(true);
    try {
      const updatedRun = await api<RunRecord>(`/api/runs/${runId}/${action}`, { method: "POST" });
      if (action === "resume") {
        const blockedReason =
          updatedRun.state.blockers[0] ||
          updatedRun.state.next_step ||
          updatedRun.state.handoff_summary.next_action ||
          `status stayed ${updatedRun.status}`;
        setOperatorDispatchMessage(
          updatedRun.status === "running" || updatedRun.status === "queued"
            ? `Resume started for ${runId}.`
            : `Resume blocked for ${runId}: ${blockedReason}`,
        );
      } else {
        setOperatorDispatchMessage(`${action === "cancel" ? "Stop" : "Pause"} requested for ${runId}.`);
      }
      setSelectedId(runId);
      await refreshSelected(runId);
      await refreshRuns(runId);
      await refreshSupervisor();
    } finally {
      setBusy(false);
    }
  }

  async function sendSteering(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !steer.trim()) return;
    await api<RunRecord>(`/api/runs/${selectedId}/steer`, {
      method: "POST",
      body: JSON.stringify({ message: steer.trim() }),
    });
    setSteer("");
    await refreshSelected();
  }

  async function proposeGoal(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !goalProposal.trim()) return;
    await api<RunRecord>(`/api/runs/${selectedId}/goal`, {
      method: "POST",
      body: JSON.stringify({
        proposed_goal: goalProposal.trim(),
        reason: "Manual /goal refinement from dashboard.",
      }),
    });
    setGoalProposal("");
    await refreshSelected();
  }

  async function reviewGoal() {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api<RunRecord>(`/api/runs/${selectedId}/goal/review`, { method: "POST" });
      await refreshSelected();
      await refreshRuns(selectedId);
    } finally {
      setBusy(false);
    }
  }

  async function resolveApproval(approvalId: number, action: "approve" | "reject") {
    if (!selectedId) return;
    await api<RunRecord>(`/api/runs/${selectedId}/approvals/${approvalId}/${action}`, { method: "POST" });
    await refreshSelected();
    await refreshRuns(selectedId);
    await refreshSupervisor();
  }

  async function refreshWorkspaceDiff() {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api<{ workspace_diff: unknown }>(`/api/runs/${selectedId}/workspace/diff`);
      await refreshSelected();
    } finally {
      setBusy(false);
    }
  }

  async function requestWorkspacePromotion() {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api<RunRecord>(`/api/runs/${selectedId}/workspace/promote`, {
        method: "POST",
        body: JSON.stringify({ files: [], include_deletions: false }),
      });
      await refreshSelected();
    } finally {
      setBusy(false);
    }
  }

  async function requestPatchApplyApproval(patchId: string) {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api<RunRecord>(`/api/runs/${selectedId}/patches/${patchId}/apply`, { method: "POST" });
      await refreshSelected();
      await refreshRuns(selectedId);
      await refreshSupervisor();
    } finally {
      setBusy(false);
    }
  }

  async function requestPatchApprovalFromCard(card: PatchApprovalCard) {
    if (card.queuedOperatorItem) {
      await dispatchQueueItem(card.queuedOperatorItem);
      return;
    }
    await requestPatchApplyApproval(card.patch.id);
  }

  async function recoveryAction(action: "resume" | "replan") {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api<RunRecord>(`/api/runs/${selectedId}/recovery/${action}`, { method: "POST" });
      await refreshSelected();
      await refreshRuns(selectedId);
      await refreshSupervisor();
    } finally {
      setBusy(false);
    }
  }

  async function reviewModelAdaptation(decision: "accepted" | "rejected") {
    if (!modelAdaptation) return;
    setBusy(true);
    try {
      await api<ModelProfileAdaptationReview>("/api/model-profile/adaptation/reviews", {
        method: "POST",
        body: JSON.stringify({
          proposal: modelAdaptation,
          decision,
          reviewer_note:
            decision === "accepted"
              ? "Accepted for future profile tuning review; no runtime mutation applied."
              : "Rejected from dashboard; keep current Ornith profile defaults.",
        }),
      });
      await refreshModelAdaptationReviews();
    } finally {
      setBusy(false);
    }
  }

  async function runReadinessRehearsal() {
    setBusy(true);
    setRehearsalBusy(true);
    setError("");
    try {
      const report = await api<ReadinessRehearsalReport>("/api/rehearsals/readiness-claim", {
        method: "POST",
      });
      setReadinessRehearsal(report);
      await refreshReadinessRehearsalLedger();
      await refreshRuns(report.run_id);
      setSelectedId(report.run_id);
      await refreshSelected(report.run_id);
      await refreshSupervisor();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRehearsalBusy(false);
      setBusy(false);
    }
  }

  async function runOperatorDispatchRestartSmoke() {
    setBusy(true);
    setDispatchSmokeBusy(true);
    setError("");
    try {
      const report = await api<OperatorDispatchRestartSmokeReport>("/api/rehearsals/operator-dispatch-restart", {
        method: "POST",
      });
      setOperatorDispatchRestartSmoke(report);
      await refreshOperatorDispatches();
      await refreshOperatorDispatchRestartSmokeLedger();
      await refreshRuns(report.run_id);
      setSelectedId(report.run_id);
      await refreshSelected(report.run_id);
      await refreshSupervisor();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatchSmokeBusy(false);
      setBusy(false);
    }
  }

  function queueDispatchLabel(item: OperatorActionQueueItem) {
    if (item.ui_target === "readiness_rehearsal") return "Run Smoke";
    if (item.ui_target === "operator_dispatch_restart_smoke") return "Restart Smoke";
    if (item.ui_target === "readiness_proof_history") return "Review";
    if (item.ui_target === "readiness_source_refs") return "Refresh";
    if (item.ui_target === "desktop_effect_proof") return "Capture Proof";
    if (item.ui_target === "context_checkpoint") return "Checkpoint";
    if (item.ui_target === "handoff_refresh") return "Refresh";
    if (item.ui_target === "promotion_verification") return "Verify";
    if (item.ui_target === "patch_apply_approval") return "Request Approval";
    if (item.ui_target === "patch_rollback_approval") return "Request Rollback";
    if (item.ui_target === "recovery") return "Resume";
    if (item.ui_target === "resume") return "Resume";
    if (item.ui_target === "goal") return "Review";
    if (item.ui_target === "self_scaffold") return "Review";
    if (item.ui_target === "steer") return "Steer";
    return "Dispatch";
  }

  function queueCanDispatch(item: OperatorActionQueueItem) {
    return [
      "readiness_rehearsal",
      "operator_dispatch_restart_smoke",
      "readiness_proof_history",
      "readiness_source_refs",
      "desktop_effect_proof",
      "context_checkpoint",
      "handoff_refresh",
      "promotion_verification",
      "patch_apply_approval",
      "patch_rollback_approval",
      "recovery",
      "resume",
      "goal",
      "self_scaffold",
    ].includes(item.ui_target);
  }

  async function dispatchQueueItem(
    item: OperatorActionQueueItem,
    decision: "open" | "dispatch" | "approve" | "reject" = "dispatch",
  ) {
    const label = decision === "dispatch" ? queueDispatchLabel(item) : decision === "open" ? "Review" : decision;
    const confirmed = decision === "open" ? false : globalThis.confirm(`${label} queued action for ${item.title}?`);
    if (decision !== "open" && !confirmed) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<OperatorActionDispatchResult>("/api/operator-actions/dispatch", {
        method: "POST",
        body: JSON.stringify({ item_id: item.id, decision, confirmed }),
      });
      setOperatorDispatchMessage(result.message);
      setOperatorActionQueue(result.queue);
      const resultRunId = result.result_run_id || item.run_id;
      await refreshRuns(resultRunId);
      setSelectedId(resultRunId);
      await refreshSelected(resultRunId);
      await refreshReadinessRehearsalLedger();
      await refreshOperatorDispatches();
      await refreshOperatorDispatchRestartSmokeLedger();
      await refreshSupervisor();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function refreshReadinessSourceRefsFromGate() {
    if (!selectedId) return;
    if (selectedSourceRefQueueItem) {
      await dispatchQueueItem(selectedSourceRefQueueItem);
      return;
    }
    const confirmed = globalThis.confirm(`Refresh readiness source refs for ${selected?.title || selectedId}?`);
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api<RunRecord>(`/api/runs/${selectedId}/readiness-source-refs/refresh`, { method: "POST" });
      setOperatorDispatchMessage("Readiness source refs refreshed from the action readiness gate.");
      await refreshRuns(selectedId);
      await refreshSelected(selectedId);
      await refreshOperatorDispatches();
      await refreshSupervisor();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runDesktopEffectProofFromGate() {
    if (!selectedId) return;
    if (selectedDesktopEffectQueueItem) {
      await dispatchQueueItem(selectedDesktopEffectQueueItem);
      return;
    }
    const confirmed = globalThis.confirm(`Capture or refresh desktop effect proof for ${selected?.title || selectedId}?`);
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api<RunRecord>(`/api/runs/${selectedId}/desktop-effect/verify`, { method: "POST" });
      setOperatorDispatchMessage("Desktop effect proof captured or refreshed.");
      await refreshRuns(selectedId);
      await refreshSelected(selectedId);
      await refreshOperatorDispatches();
      await refreshSupervisor();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  async function openQueueItem(runId: string) {
    setSelectedId(runId);
    await refreshRuns(runId);
    await refreshSelected(runId);
  }

  function findQueueItem(item: ActivityFeedItem) {
    if (!item.queueItemId) return undefined;
    return (operatorActionQueue?.items ?? []).find((queueItem) => queueItem.id === item.queueItemId);
  }

  function renderFeedActions(item: ActivityFeedItem): ReactNode {
    if (item.actionType === "artifact") {
      if (item.artifactHref) {
        return (
          <a className="button-link" href={item.artifactHref} target="_blank" rel="noreferrer">
            Open Artifact
          </a>
        );
      }
      return item.artifactPath ? <code>{item.artifactPath}</code> : null;
    }

    if ((item.actionType === "goal_confirmation" || item.actionType === "approval") && item.approvalId) {
      const isGoal = item.actionType === "goal_confirmation" || item.approvalKind === "goal_update";
      return (
        <>
          <button className="primary" type="button" onClick={() => resolveApproval(item.approvalId!, "approve")} disabled={busy}>
            <Check size={15} />
            {isGoal ? "Accept Goal" : "Approve"}
          </button>
          <button type="button" onClick={() => resolveApproval(item.approvalId!, "reject")} disabled={busy}>
            <X size={15} />
            {isGoal ? "Reject Goal" : "Reject"}
          </button>
        </>
      );
    }

    if (item.actionType === "recovery") {
      return (
        <>
          <button className="primary" type="button" onClick={() => recoveryAction("resume")} disabled={busy || !selectedId}>
            <Play size={15} />
            Resume Recovery
          </button>
          <button type="button" onClick={() => recoveryAction("replan")} disabled={busy || !selectedId}>
            <RotateCcw size={15} />
            Replan
          </button>
        </>
      );
    }

    if (item.actionType === "resume") {
      return (
        <button className="primary" type="button" onClick={() => control("resume")} disabled={busy || !selectedId || !canResumeRun(selected)}>
          <Play size={15} />
          Resume Run
        </button>
      );
    }

    const queueItem = findQueueItem(item);
    if (queueItem) {
      if (queueItem.ui_target === "approval" && queueItem.approval_id) {
        return (
          <>
            <button type="button" onClick={() => dispatchQueueItem(queueItem, "open")} disabled={busy}>
              Review
            </button>
            <button className="primary" type="button" onClick={() => dispatchQueueItem(queueItem, "approve")} disabled={busy}>
              Approve
            </button>
            <button type="button" onClick={() => dispatchQueueItem(queueItem, "reject")} disabled={busy}>
              Reject
            </button>
          </>
        );
      }
      if (queueCanDispatch(queueItem)) {
        return (
          <button className="primary" type="button" onClick={() => dispatchQueueItem(queueItem)} disabled={busy}>
            {item.actionType === "goal_confirmation"
              ? "Review Goal"
              : queueItem.ui_target === "handoff_refresh"
                ? "Refresh Handoff"
                : queueDispatchLabel(queueItem)}
          </button>
        );
      }
    }

    if (item.actionType === "blocker") {
      return (
        <>
          <button type="button" onClick={() => setActiveView("activity")}>
            Resolve Blocker
          </button>
          <button type="button" onClick={() => recoveryAction("replan")} disabled={busy || !selectedId}>
            Replan
          </button>
        </>
      );
    }

    if (item.actionType === "readiness") {
      return (
        <button type="button" onClick={() => setActiveView("activity")}>
          View Details
        </button>
      );
    }

    return null;
  }

  function renderChatItem(message: ActivityFeedItem) {
    return (
      <article className={`chat-message ${message.role} ${message.kind} ${message.severity ?? ""}`} key={message.id}>
        <div>
          <strong>{message.title}</strong>
          <span>{message.role}</span>
        </div>
        <p>{formatLocalTextTimestamps(message.body)}</p>
        {message.meta?.length ? (
          <small>{message.meta.map((item) => formatLocalTextTimestamps(item)).join(" / ")}</small>
        ) : null}
        {message.timestamp ? <small title={message.timestamp}>{formatLocalTimestamp(message.timestamp)}</small> : null}
        <div className="inline-actions">{renderFeedActions(message)}</div>
      </article>
    );
  }

  return (
    <main className={`shell view-${activeView}${focusFullscreen ? " focus-fullscreen" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <Brain size={24} />
          <div>
            <strong>FlyOrnith</strong>
            <span>public workstream harness</span>
          </div>
        </div>

        <form className="new-run" onSubmit={createRun}>
          <label htmlFor="goal">Goal</label>
          <textarea id="goal" value={goal} onChange={(event) => setGoal(event.target.value)} />
          <label htmlFor="criteria">Acceptance criteria</label>
          <textarea id="criteria" value={criteria} onChange={(event) => setCriteria(event.target.value)} />
          <label htmlFor="projectPath">Project folder</label>
          <div className="project-input">
            <FolderOpen size={15} />
            <input
              id="projectPath"
              value={projectPath}
              onChange={(event) => setProjectPath(event.target.value)}
              placeholder="Optional local folder path"
            />
          </div>
          <label htmlFor="approvalMode">Approval mode</label>
          <select
            id="approvalMode"
            value={approvalMode}
            onChange={(event) => setApprovalMode(event.target.value as ApprovalMode)}
            title={approvalModes.find((mode) => mode.value === approvalMode)?.help}
          >
            {approvalModes.map((mode) => (
              <option key={mode.value} value={mode.value}>
                {mode.label}
              </option>
            ))}
          </select>
          <p className="approval-mode-help">{approvalModes.find((mode) => mode.value === approvalMode)?.help}</p>
          <div className="toggles">
            <label>
              <input type="checkbox" checked={webEnabled} onChange={(event) => setWebEnabled(event.target.checked)} />
              Web
            </label>
            <label>
              <input
                type="checkbox"
                checked={browserEnabled}
                onChange={(event) => setBrowserEnabled(event.target.checked)}
              />
              Browser
            </label>
            <label>
              <input
                type="checkbox"
                checked={desktopEnabled}
                onChange={(event) => setDesktopEnabled(event.target.checked)}
              />
              Desktop
            </label>
          </div>
          <button className="primary" type="submit" disabled={busy || creatingRun}>
            <Play size={16} />
            {creatingRun ? "Starting" : "Start"}
          </button>
          {creatingRun ? <p className="muted">Creating persistent chat and scheduling the loop...</p> : null}
        </form>

        <div className="attention-toggle">
          <button
            className={showAttentionOnly ? "primary" : ""}
            type="button"
            onClick={() => setShowAttentionOnly((value) => !value)}
          >
            <AlertTriangle size={16} />
            Attention
          </button>
          <span>{supervisor?.operator_attention_count ?? 0}</span>
        </div>

        <div className="section-label">
          <span>Persistent Chats</span>
          <strong>{visibleRuns.length}</strong>
        </div>
        <nav className="run-list" aria-label="Runs">
          {visibleRuns.map((run) => {
            const supervisorRun = supervisorRunById.get(run.id);
            const chatThread = chatThreadById.get(run.id);
            return (
              <article
                className={run.id === selectedId ? "run-item active" : "run-item"}
                key={run.id}
              >
                <button
                  className="run-open"
                  onClick={() => {
                    setSelected(run);
                    void openQueueItem(run.id);
                  }}
                  type="button"
                >
                  <strong>{run.title}</strong>
                  <span>{chatThread?.resumeHint ?? "Open this chat to resume."}</span>
                </button>
                <div className="run-meta">
                  <span className={`run-status ${run.status}`}>{run.status}</span>
                  {chatThread ? <span>{chatThread.messageCount} msgs</span> : null}
                  {chatThread ? <span>{chatThread.artifactCount} artifacts</span> : null}
                  {supervisorRun?.operator_attention_required ? <span>{supervisorRun.operator_attention_reasons[0]}</span> : null}
                </div>
                <div className="run-actions">
                  <button type="button" onClick={() => openQueueItem(run.id)}>
                    Open
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      setSelected(run);
                      setSelectedId(run.id);
                      await control("resume", run.id);
                    }}
                    disabled={!canResumeRun(run) || busy}
                  >
                    Resume
                  </button>
                </div>
              </article>
            );
          })}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>{selected?.title ?? "No run selected"}</h1>
            <p>{selected?.workspace_path ?? "Start a run to create durable state."}</p>
          </div>
          <div className="controls">
            <button type="button" onClick={() => control("pause")} disabled={!selectedId || busy}>
              <Pause size={16} />
              Pause
            </button>
            <button type="button" onClick={() => control("resume")} disabled={!selectedId || busy || !canResumeRun(selected)}>
              <RotateCcw size={16} />
              Resume
            </button>
            <button type="button" onClick={() => control("cancel")} disabled={!selectedId || busy}>
              <Square size={16} />
              Stop
            </button>
            <button type="button" onClick={() => setFocusFullscreen((value) => !value)}>
              <Monitor size={16} />
              {focusFullscreen ? "Exit Focus" : "Focus Mode"}
            </button>
          </div>
        </header>

        <nav className="workbench-tabs" aria-label="Workbench sections">
          {workbenchViews.map((view) => (
            <button
              className={activeView === view ? "active" : ""}
              key={view}
              onClick={() => setActiveView(view)}
              type="button"
            >
              {view[0].toUpperCase() + view.slice(1)}
            </button>
          ))}
        </nav>

        {error && <div className="error">{error}</div>}
        {operatorDispatchMessage && <div className="notice">{operatorDispatchMessage}</div>}

        <div className="status-strip">
          <span className={`status ${selected?.status ?? "idle"}`}>{selected?.status ?? "idle"}</span>
          <span className="milestone">{selected?.state.milestone ?? "idle"}</span>
          <div className="meter" aria-label="Progress">
            <span style={{ width: `${progress}%` }} />
          </div>
          <strong>{progress}%</strong>
        </div>

        <div className="needs-you-strip">
          <button type="button" onClick={() => setActiveView("focus")} className={requiredActionItems.length ? "active" : ""}>
            <AlertTriangle size={15} />
            {requiredActionLabel}
            <strong>{requiredActionItems.length}</strong>
          </button>
          <span>
            {firstRequiredAction
              ? `${firstRequiredAction.title}: ${firstRequiredAction.body.split("\n")[0]}`
              : "No pending user action in this chat."}
          </span>
          <small>
            {[
              supervisor ? `${supervisor.operator_attention_count} attention` : "",
              pendingApprovals.length ? `${pendingApprovals.length} approvals` : "",
              selected?.status === "waiting_goal_confirmation" ? "goal confirmation" : "",
              selectedProjectPath ? `project ${selectedProjectPath}` : "",
            ]
              .filter(Boolean)
              .join(" / ")}
          </small>
        </div>

        <section className={activeView === "focus" ? "focus-workbench" : "view-hidden"}>
          <div className="focus-status-card">
            <div>
              <span className={`run-status ${selected?.status ?? "idle"}`}>{selected?.status ?? "no chat"}</span>
              <span className="milestone">{selected?.state.milestone ?? "idle"}</span>
            </div>
            <strong>{selected?.state.next_step || "Start or resume a chat to begin work."}</strong>
            <p>{selectedProjectPath ? `Project: ${selectedProjectPath}` : "No project folder selected for this run."}</p>
          </div>

          <div className="focus-chat-shell">
            <section className="focus-chat-main" aria-label="Focus chat timeline">
              <div className="chat-visibility-note">
                Showing public work summaries, tool choices, results, approvals, and recovery decisions. Hidden
                chain-of-thought is not shown.
              </div>

              <div className="required-action-stack">
                <div className="focus-section-heading">
                  <AlertTriangle size={16} />
                  <strong>Required Actions</strong>
                  <span>{requiredActionItems.length}</span>
                </div>
                {requiredActionItems.length === 0 ? (
                  <p className="muted">No approval, goal confirmation, recovery prompt, or blocker is waiting on you.</p>
                ) : (
                  requiredActionItems.map((item) => (
                    <article className={`required-action-card ${item.severity ?? "watch"}`} key={item.id}>
                      <div>
                        <strong>{item.title}</strong>
                        <span>{item.meta?.map((meta) => formatLocalTextTimestamps(meta)).join(" / ")}</span>
                      </div>
                      <p>{formatLocalTextTimestamps(item.body)}</p>
                      <div className="inline-actions">{renderFeedActions(item)}</div>
                    </article>
                  ))
                )}
              </div>

              <div className="conversation-thread focus-timeline">
                {timelineItems.length === 0 ? (
                  <p className="muted">Select an older chat or start a new run.</p>
                ) : (
                  timelineItems.map(renderChatItem)
                )}
              </div>

              <form className="focus-composer" onSubmit={sendSteering}>
                <textarea
                  value={steer}
                  onChange={(event) => setSteer(event.target.value)}
                  placeholder="Steer Ornith, answer a prompt, or add constraints for this run..."
                />
                <button className="primary" type="submit" disabled={!selectedId}>
                  <Send size={16} />
                  Send
                </button>
              </form>
            </section>

            <aside className="focus-artifact-rail" aria-label="Artifacts">
              <div className="focus-section-heading">
                <FileText size={16} />
                <strong>Artifacts</strong>
                <span>{artifactItems.length}</span>
              </div>
              <div className="artifact-strip">
                {artifactItems.length === 0 ? (
                  <p className="muted">Artifacts will appear here as Ornith works.</p>
                ) : (
                  artifactItems.slice(0, 10).map((artifact) => (
                    <article className="artifact-item compact" key={artifact.id}>
                      <div>
                        <span className="artifact-kind">{artifact.kind}</span>
                        {artifact.href ? (
                          <a href={artifact.href} target="_blank" rel="noreferrer">
                            {artifact.title}
                          </a>
                        ) : (
                          <strong>{artifact.title}</strong>
                        )}
                      </div>
                      <p>{formatLocalTextTimestamps(artifact.summary)}</p>
                    </article>
                  ))
                )}
              </div>
            </aside>
          </div>
        </section>

        <section className={activeView === "artifacts" ? "artifacts-workbench" : "view-hidden"}>
          <section className="artifacts">
            <h2>
              <FileText size={18} />
              Artifacts
            </h2>
            <div className="artifact-list expanded">
              {artifactItems.length === 0 ? (
                <p className="muted">No artifacts attached to this chat yet.</p>
              ) : (
                artifactItems.map((artifact) => (
                  <article className="artifact-item" key={artifact.id}>
                    <div>
                      <span className="artifact-kind">{artifact.kind}</span>
                      {artifact.href ? (
                        <a href={artifact.href} target="_blank" rel="noreferrer">
                          {artifact.title}
                        </a>
                      ) : (
                        <strong>{artifact.title}</strong>
                      )}
                    </div>
                    <p>{formatLocalTextTimestamps(artifact.summary)}</p>
                    {artifact.path ? <code>{artifact.path}</code> : null}
                    {artifact.timestamp ? <small title={artifact.timestamp}>{formatLocalTimestamp(artifact.timestamp)}</small> : null}
                  </article>
                ))
              )}
            </div>
          </section>
          <section className="replay">
            <h2>
              <Share size={18} />
              Replay
            </h2>
            {replay ? (
              <>
                <div className="replay-stats">
                  <span>{replay.event_count} events</span>
                  <span>{replay.approval_count} approvals</span>
                  <span>{replay.context_pressure} context</span>
                </div>
                <a href={`${API_BASE}/api/runs/${replay.run_id}/replay.md`} target="_blank" rel="noreferrer">
                  Open replay markdown
                </a>
                <pre>{formatLocalTextTimestamps(replay.handoff.resume_prompt)}</pre>
              </>
            ) : (
              <p>No replay loaded.</p>
            )}
          </section>
          <section className="notes">
            <h2>
              <FileText size={18} />
              Obsidian
            </h2>
            <pre>{formatLocalTextTimestamps(notes || "No run note loaded.")}</pre>
          </section>
        </section>

        <section className={activeView === "runs" ? "runs-workbench" : "view-hidden"}>
          <div className="runs-header">
            <div>
              <h2>Persistent Chats</h2>
              <p className="muted">Open a previous run, resume paused work, or start a new project-bound chat from the left rail.</p>
            </div>
            <button type="button" onClick={() => refreshRuns(selectedId)} disabled={busy}>
              <RotateCcw size={16} />
              Refresh
            </button>
          </div>
          <div className="runs-grid">
            {visibleRuns.map((run) => {
              const chatThread = chatThreadById.get(run.id);
              return (
                <article className={run.id === selectedId ? "run-card active" : "run-card"} key={run.id}>
                  <div>
                    <span className={`run-status ${run.status}`}>{run.status}</span>
                    <strong>{run.title}</strong>
                    <p>{chatThread?.resumeHint ?? run.state.next_step ?? "Open this chat to resume."}</p>
                    <code>{run.workspace_path}</code>
                  </div>
                  <div className="inline-actions">
                    <button type="button" onClick={() => openQueueItem(run.id)}>
                      Open
                    </button>
                    <button type="button" onClick={() => control("resume", run.id)} disabled={!canResumeRun(run) || busy}>
                      Resume
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className={activeView === "settings" ? "settings-workbench" : "view-hidden"}>
          <Panel title="Project Workspace" icon={<FolderOpen size={18} />}>
            <p className="focus-text">{selected?.state.workspace_isolation.summary || "No project workspace loaded."}</p>
            <List
              items={[
                selected?.state.workspace_isolation.source_path
                  ? `source: ${selected.state.workspace_isolation.source_path}`
                  : selected?.workspace_path
                    ? `source: ${selected.workspace_path}`
                    : "",
                selected?.state.workspace_isolation.workspace_path
                  ? `active: ${selected.state.workspace_isolation.workspace_path}`
                  : "",
                selected?.state.workspace_diff.summary || "",
              ].filter((item): item is string => Boolean(item))}
              empty="No workspace details."
            />
          </Panel>
          <Panel title="Model Profile" icon={<Brain size={18} />}>
            <List
              items={[
                modelProfile ? `model: ${modelProfile.configured_model || modelProfile.display_name}` : "",
                modelProfile ? `context target: ${modelProfile.effective_context_target_tokens}` : "",
                modelHealth ? `health: ${modelHealth.status}${modelHealth.latency_ms ? ` / ${modelHealth.latency_ms}ms` : ""}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No model profile loaded."
            />
          </Panel>
          <Panel title="Tool Config" icon={<Wrench size={18} />}>
            <List
              items={[
                selected ? `profile: ${selected.state.tool_profile}` : "",
                selected ? `approval mode: ${selected.state.approval_mode}` : "",
                selected ? `web sources: ${selected.state.web_sources.length}` : "",
                selected ? `desktop snapshots: ${selected.state.desktop_snapshots.length}` : "",
                selected?.state.context_budget
                  ? `context: ${selected.state.context_budget.estimated_tokens}/${selected.state.context_budget.target_tokens} (${selected.state.context_budget.pressure})`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No tool configuration loaded."
            />
          </Panel>
        </section>

        <div className={activeView === "activity" ? "grid" : "grid view-hidden"}>
          <Panel title="Plan" icon={<Check size={18} />}>
            <Numbered items={selected?.state.current_plan ?? []} empty="No plan yet." />
          </Panel>
          <Panel title="Next Action" icon={<Play size={18} />}>
            <p className="focus-text">{selected?.state.next_step || "Waiting for a run."}</p>
          </Panel>
          <Panel title="Operator Queue" icon={<AlertTriangle size={18} />}>
            <p className="focus-text">
              {operatorActionQueue?.summary || "No operator action queue loaded."}
            </p>
            <List
              items={[
                operatorActionQueue ? `blocked: ${operatorActionQueue.blocked_count}` : "",
                operatorActionQueue ? `watch: ${operatorActionQueue.watch_count}` : "",
                operatorActionQueue ? `approvals: ${operatorActionQueue.approval_count}` : "",
                operatorActionQueue ? `goal confirmations: ${operatorActionQueue.goal_confirmation_count}` : "",
                operatorActionQueue ? `smoke: ${operatorActionQueue.smoke_count}` : "",
                operatorActionQueue ? `proof history: ${operatorActionQueue.readiness_proof_history_count}` : "",
                operatorActionQueue ? `source refs: ${operatorActionQueue.readiness_source_ref_count}` : "",
                operatorActionQueue ? `desktop proof: ${operatorActionQueue.desktop_effect_proof_count}` : "",
                operatorActionQueue ? `preflight: ${operatorActionQueue.preflight_count}` : "",
                operatorActionQueue ? `checkpoint quality: ${operatorActionQueue.checkpoint_quality_count}` : "",
                operatorActionQueue ? `promotion: ${operatorActionQueue.promotion_count}` : "",
                operatorActionQueue ? `promotion approvals: ${operatorActionQueue.promotion_approval_count}` : "",
                operatorActionQueue ? `self scaffold: ${operatorActionQueue.self_scaffold_count}` : "",
                operatorActionQueue ? `self scaffold rollback: ${operatorActionQueue.self_scaffold_rollback_count}` : "",
                operatorActionQueue ? `recovery: ${operatorActionQueue.recovery_count}` : "",
                operatorActionQueue ? `blockers: ${operatorActionQueue.blocker_count}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No queue counts."
            />
            <div className="segmented" role="group" aria-label="Operator queue filter">
              <button
                type="button"
                className={queueFilter === "all" ? "active" : ""}
                onClick={() => changeQueueFilter("all")}
              >
                All
              </button>
              <button
                type="button"
                className={queueFilter === "proof_reviews" ? "active" : ""}
                onClick={() => changeQueueFilter("proof_reviews")}
              >
                Proof reviews
              </button>
              <button
                type="button"
                className={queueFilter === "promotion_approvals" ? "active" : ""}
                onClick={() => changeQueueFilter("promotion_approvals")}
              >
                Promotion approvals
              </button>
            </div>
            {operatorDispatchMessage && <p className="muted">{operatorDispatchMessage}</p>}
            {displayedQueueItems.length === 0 ? (
              <p className="muted">Queue is clear.</p>
            ) : (
              <div className="queue-list">
                {displayedQueueItems.slice(0, 6).map((item) => (
                  <div className={`queue-item ${item.severity}`} key={item.id}>
                    <div>
                      <strong>
                        {item.severity} / {item.reason}
                      </strong>
                      <span>{item.title}</span>
                      <p>{formatLocalTextTimestamps(item.action)}</p>
                      <small>
                        {item.status} / priority {item.priority}
                        {item.approval_id ? ` / approval ${item.approval_id}` : ""}
                        {item.promotion_gate ? " / promotion gate" : ""}
                      </small>
                      {item.details.length ? (
                        <small>{item.details.map((detail) => formatLocalTextTimestamps(detail)).join(" / ")}</small>
                      ) : null}
                    </div>
                    <div className="queue-actions">
                      <button type="button" onClick={() => openQueueItem(item.run_id)}>
                        Open
                      </button>
                      {item.ui_target === "approval" && item.approval_id ? (
                        <>
                          <button type="button" onClick={() => dispatchQueueItem(item, "open")} disabled={busy}>
                            Review
                          </button>
                          <button type="button" onClick={() => dispatchQueueItem(item, "approve")} disabled={busy}>
                            Approve
                          </button>
                          <button type="button" onClick={() => dispatchQueueItem(item, "reject")} disabled={busy}>
                            Reject
                          </button>
                        </>
                      ) : queueCanDispatch(item) ? (
                        <button type="button" onClick={() => dispatchQueueItem(item)} disabled={busy}>
                          {queueDispatchLabel(item)}
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Operator Dispatches" icon={<Send size={18} />}>
            <p className="focus-text">
              {operatorDispatches?.summary || "No operator dispatch ledger yet."}
            </p>
            <div className="panel-actions">
              <button
                className="primary"
                type="button"
                onClick={runOperatorDispatchRestartSmoke}
                disabled={busy || dispatchSmokeBusy}
              >
                <RotateCcw size={16} />
                {dispatchSmokeBusy ? "Running" : "Restart Smoke"}
              </button>
            </div>
            <List
              items={[
                operatorDispatches ? `dispatched: ${operatorDispatches.dispatched_count}` : "",
                operatorDispatches ? `confirm: ${operatorDispatches.confirmation_required_count}` : "",
                operatorDispatches ? `reviewed: ${operatorDispatches.reviewed_count}` : "",
                operatorDispatches ? `blocked: ${operatorDispatches.blocked_count}` : "",
                operatorDispatches?.latest_action ? `latest: ${operatorDispatches.latest_action}` : "",
                operatorDispatchRestartSmokeLedger ? `smoke ledger: ${operatorDispatchRestartSmokeLedger.status}` : "",
                operatorDispatchRestartSmokeLedger
                  ? `smoke runs: ${operatorDispatchRestartSmokeLedger.total_count} total / ${operatorDispatchRestartSmokeLedger.passed_count} passed / ${operatorDispatchRestartSmokeLedger.failed_count} failed`
                  : "",
                operatorDispatchRestartSmokeLedger?.latest?.run_id
                  ? `latest smoke: ${operatorDispatchRestartSmokeLedger.latest.run_id}`
                  : "",
                operatorDispatchRestartSmoke ? `selected smoke: ${operatorDispatchRestartSmoke.status}` : "",
                operatorDispatchRestartSmoke ? `restart: ${operatorDispatchRestartSmoke.restart_simulated ? "yes" : "no"}` : "",
                operatorDispatchRestartSmoke ? `handoff: ${operatorDispatchRestartSmoke.handoff_attached ? "yes" : "no"}` : "",
                operatorDispatchRestartSmoke ? `replay: ${operatorDispatchRestartSmoke.replay_attached ? "yes" : "no"}` : "",
                operatorDispatchRestartSmoke ? `context: ${operatorDispatchRestartSmoke.context_attached ? "yes" : "no"}` : "",
                operatorDispatchRestartSmoke?.dispatch_event_id ? `dispatch event: ${operatorDispatchRestartSmoke.dispatch_event_id}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No dispatch counts."
            />
            <List
              items={(operatorDispatchRestartSmokeLedger?.entries ?? []).map(
                (entry) =>
                  `${entry.status}: ${entry.run_id} | steps ${entry.passed_steps}/${entry.step_count}${
                    entry.failed_steps ? `, failed ${entry.failed_steps}` : ""
                  } | handoff ${entry.handoff_attached ? "yes" : "no"} | replay ${
                    entry.replay_attached ? "yes" : "no"
                  } | context ${entry.context_attached ? "yes" : "no"}`,
              )}
              empty="No dispatch restart smoke history."
            />
            <List
              items={(operatorDispatchRestartSmoke?.steps ?? []).map(
                (step) => `${step.status}: ${step.id} - ${step.summary}`,
              )}
              empty="No restart smoke steps."
            />
            <List
              items={(operatorDispatches?.unresolved_approval_histories ?? [])
                .slice(0, 6)
                .map((history) => formatApprovalHistory(history, "unresolved approval"))}
              empty="No unresolved approval histories."
            />
            <List
              items={(operatorDispatches?.approval_histories ?? [])
                .slice(0, 6)
                .map((history) => formatApprovalHistory(history, "approval"))}
              empty="No approval dispatch histories."
            />
            <List
              items={(operatorDispatches?.unresolved_promotion_approval_histories ?? [])
                .slice(0, 6)
                .map((history) => formatApprovalHistory(history, "open promotion approval"))}
              empty="No unresolved promotion approval histories."
            />
            <List
              items={(operatorDispatches?.promotion_approval_histories ?? [])
                .slice(0, 6)
                .map((history) => formatApprovalHistory(history, "promotion approval"))}
              empty="No promotion approval histories."
            />
            <List
              items={(operatorDispatches?.promotion_routes ?? [])
                .slice(0, 6)
                .map(
                  (route) =>
                    `promotion route ${route.event_id}: ${route.status}/${route.decision || "open"} ${route.action_reason} -> ${route.ui_target}${
                      route.approval_id ? ` approval ${route.approval_id}` : ""
                    }${route.approval_kind ? ` (${route.approval_kind})` : ""}`,
                )}
              empty="No promotion dispatch routes."
            />
            <List
              items={(operatorDispatches?.entries ?? [])
                .slice(0, 6)
                .map(
                  (entry) =>
                    `#${entry.event_id} ${entry.status}/${entry.decision || entry.ui_target}: ${entry.message}${
                      entry.approval_id ? ` (approval ${entry.approval_id})` : ""
                    }`,
                )}
              empty="No operator dispatch events."
            />
            <p className="muted">
              {operatorDispatchRestartSmokeLedger?.next_action || operatorDispatchRestartSmoke?.next_action || operatorDispatches?.recommended_action || ""}
            </p>
          </Panel>
          <Panel title="Harness Performance" icon={<Gauge size={18} />}>
            <p className="focus-text">
              {selected
                ? `${selected.title} is ${selected.status} at ${selected.state.milestone}; progress ${progress}%.`
                : "No active run selected."}
            </p>
            <List
              items={[
                selected?.state.run_health
                  ? `health: ${selected.state.run_health.level} / ${selected.state.run_health.recommended_action} (${selected.state.run_health.score}/100)`
                  : "",
                selected?.state.run_progress
                  ? `criteria: ${selected.state.run_progress.acceptance_verified}/${selected.state.run_progress.acceptance_total} verified`
                  : "",
                selected?.state.context_budget
                  ? `context: ${selected.state.context_budget.estimated_tokens}/${selected.state.context_budget.target_tokens} tokens (${selected.state.context_budget.pressure})`
                  : "",
                operatorActionQueue
                  ? `operator queue: ${operatorActionQueue.total_count} total, ${operatorActionQueue.blocked_count} blocked, ${operatorActionQueue.watch_count} watch`
                  : "",
                supervisor ? `pending approvals: ${supervisor.pending_approval_count}` : "",
                supervisor
                  ? `tracking gates: smoke ${supervisor.readiness_smoke_attention_count}, dispatch ${supervisor.operator_dispatch_restart_smoke_attention_count}, preflight ${supervisor.ornith_preflight_attention_count}`
                  : "",
                supervisor
                  ? `scaffold: review ${supervisor.self_scaffold_attention_count}, rollback ${supervisor.self_scaffold_rollback_attention_count}`
                  : "",
                operatorDispatches
                  ? `dispatch ledger: ${operatorDispatches.total_count} events, unresolved approvals ${operatorDispatches.unresolved_approval_history_count}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No harness performance signals yet."
            />
          </Panel>
          <Panel title="Action Readiness" icon={<ListChecks size={18} />}>
            <p className="focus-text">
              {actionReadiness?.summary || "No action readiness report yet."}
            </p>
            <List
              items={[
                actionReadiness?.status ? `status: ${actionReadiness.status}` : "",
                actionReadiness ? `ready: ${actionReadiness.ready_to_act ? "yes" : "no"}` : "",
                actionReadiness?.current_task_id
                  ? `task: ${actionReadiness.current_task_id} ${actionReadiness.current_task_status}`
                  : "",
                actionReadiness?.suggested_tool
                  ? `suggested: ${actionReadiness.suggested_tool} ${actionReadiness.suggested_label}`
                  : "",
                actionReadiness
                  ? `resume match: ${actionReadiness.resume_decision_matches ? "yes" : "no"}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No readiness details."
            />
            {readinessSourceRefGate.needed ? (
              <div className="queue-item blocked">
                <div>
                  <strong>Readiness Source Refs</strong>
                  <p>{formatLocalTextTimestamps(readinessSourceRefGate.action)}</p>
                  <small>{formatLocalTextTimestamps(readinessSourceRefGate.meta)}</small>
                </div>
                <div className="queue-actions">
                  <button type="button" onClick={refreshReadinessSourceRefsFromGate} disabled={busy || !selectedId}>
                    <RotateCcw size={16} />
                    {readinessSourceRefGate.buttonLabel}
                  </button>
                </div>
              </div>
            ) : null}
            <p className="muted">{actionReadiness?.recommended_action ?? ""}</p>
            <List
              items={(actionReadiness?.issues ?? [])
                .slice(0, 5)
                .map((item) => `${item.severity}: ${item.summary}`)}
              empty="No readiness issues."
            />
            <p className="focus-text">
              {actionReadinessDecisions?.summary || "No readiness decision ledger yet."}
            </p>
            <List
              items={[
                actionReadinessDecisions ? `decisions: ${actionReadinessDecisions.decision_count}` : "",
                actionReadinessDecisions ? `satisfied: ${actionReadinessDecisions.satisfied_count}` : "",
                actionReadinessDecisions ? `failed: ${actionReadinessDecisions.failed_count}` : "",
                actionReadinessDecisions
                  ? `sources: harness ${actionReadinessDecisions.harness_selected_count} / model ${actionReadinessDecisions.model_selected_count} / fallback ${actionReadinessDecisions.fallback_selected_count}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No readiness decision counts."
            />
            <List
              items={(actionReadinessDecisions?.decisions ?? [])
                .slice(-5)
                .map(
                  (item) =>
                    `${item.status} ${item.source}: ${item.selected_tool || item.kind}${
                      item.label || item.suggested_label ? ` (${item.label || item.suggested_label})` : ""
                    } - ${item.summary}`,
                )}
              empty="No readiness decisions."
            />
          </Panel>
          <Panel title="Findings" icon={<Brain size={18} />}>
            <List items={selected?.state.facts_learned ?? []} empty="No findings yet." />
          </Panel>
          <Panel title="Risks And Blockers" icon={<AlertTriangle size={18} />}>
            <List items={[...(selected?.state.risks ?? []), ...(selected?.state.blockers ?? [])]} empty="None." />
          </Panel>
          <Panel title="Context Budget" icon={<Gauge size={18} />}>
            <p className="focus-text">
              {selected?.state.context_budget.estimated_tokens ?? 0} /{" "}
              {selected?.state.context_budget.target_tokens ?? 0} tokens
            </p>
            <p className={`pressure ${selected?.state.context_budget.pressure ?? "low"}`}>
              {selected?.state.context_budget.pressure ?? "low"}
            </p>
          </Panel>
          <Panel title="Action Context" icon={<Brain size={18} />}>
            <p className="focus-text">
              {selected?.state.action_context?.selected_tool
                ? `${selected.state.action_context?.selected_tool}:${selected.state.action_context?.selected_label || "none"}`
                : "No action context packed yet."}
            </p>
            {desktopEffectProofGate.needed ? (
              <div className="queue-item watch">
                <div>
                  <strong>Desktop Effect Proof</strong>
                  <p>{formatLocalTextTimestamps(desktopEffectProofGate.action)}</p>
                  <small>{formatLocalTextTimestamps(desktopEffectProofGate.meta)}</small>
                  {desktopEffectProof ? (
                    <small>
                      {desktopEffectProof.requires_attention
                        ? `latest action: ${desktopEffectProof.latest_action_tool || "desktop action"} ${desktopEffectProof.latest_action_summary}`
                        : desktopEffectProof.proof_snapshot
                          ? `latest proof: ${desktopEffectProof.proof_snapshot.title} ${formatLocalTimestamp(
                              desktopEffectProof.proof_snapshot.timestamp,
                            )}`
                          : desktopEffectProof.proof_summary
                            ? `latest proof: ${desktopEffectProof.proof_tool} ${desktopEffectProof.proof_summary}`
                            : desktopEffectProof.recommended_action}
                    </small>
                  ) : null}
                </div>
                <div className="queue-actions">
                  <button type="button" onClick={runDesktopEffectProofFromGate} disabled={busy || !selectedId}>
                    <Monitor size={16} />
                    {desktopEffectProofGate.buttonLabel}
                  </button>
                </div>
              </div>
            ) : null}
            <List
              items={[
                selected?.state.action_context?.selected_action
                  ? `next: ${selected.state.action_context?.selected_action}`
                  : "",
                selected?.state.action_context?.task_transition_ledger?.length
                  ? `task transitions: ${selected.state.action_context?.task_transition_ledger.join("; ")}`
                  : "",
                selected?.state.action_context?.model_guard_ledger?.length
                  ? `model guards: ${selected.state.action_context?.model_guard_ledger.join("; ")}`
                  : "",
                selected?.state.action_context?.edit_evidence_ledger?.length
                  ? `edit evidence: ${selected.state.action_context?.edit_evidence_ledger.join("; ")}`
                  : "",
                selected?.state.action_context?.desktop_supervision_ledger?.length
                  ? `desktop supervision: ${selected.state.action_context?.desktop_supervision_ledger.join("; ")}`
                  : "",
                (selected?.state.action_context?.missing_source_labels ?? []).length
                  ? `missing source: ${(selected?.state.action_context?.missing_source_labels ?? []).join(", ")}`
                  : "",
                selected?.state.action_context?.latest_source_evidence
                  ? `latest source: ${selected.state.action_context?.latest_source_evidence}`
                  : "",
                selected?.state.action_context?.resolved_failure_ledger?.length
                  ? `resolved failures: ${selected.state.action_context?.resolved_failure_ledger.join("; ")}`
                  : "",
                (selected?.state.action_context?.promotion_repair_hints ?? []).length
                  ? `repair hints: ${(selected?.state.action_context?.promotion_repair_hints ?? []).join("; ")}`
                  : "",
                selected?.state.action_context?.context_budget
                  ? `context: ${selected.state.action_context?.context_budget}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No packed action details."
            />
            <pre>{formatLocalTextTimestamps(selected?.state.action_context?.compact_prompt || "No action context pack yet.")}</pre>
          </Panel>
          <Panel title="Self Scaffold" icon={<Wrench size={18} />}>
            <p className="focus-text">{selfScaffold?.summary || "No self-scaffold report yet."}</p>
            <List
              items={[
                selfScaffold ? `status: ${selfScaffold.status}` : "",
                selfScaffold ? `changes: ${selfScaffold.change_count}` : "",
                selfScaffold ? `reversible: ${selfScaffold.reversible_count}` : "",
                selfScaffold ? `guards: ${selfScaffold.guard_count}` : "",
                selfScaffold ? `reviewed: ${selfScaffold.reviewed_change_count}/${selfScaffold.review_count}` : "",
                selfScaffold?.latest_review_event_id ? `review event: #${selfScaffold.latest_review_event_id}` : "",
                selfScaffold?.latest_change ? `latest: ${selfScaffold.latest_change}` : "",
                selfScaffold?.recommended_action ? `next: ${selfScaffold.recommended_action}` : "",
                selectedSupervisorRun?.self_scaffold_requires_attention
                  ? `operator: ${selectedSupervisorRun.self_scaffold_action}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No scaffold counts."
            />
            {selfScaffoldReviews?.total_count ? (
              <>
                <List
                  items={[
                    `reviews: ${selfScaffoldReviews.status} / total ${selfScaffoldReviews.total_count}`,
                    `accepted: ${selfScaffoldReviews.accepted_count} / partial ${selfScaffoldReviews.partial_count} / noop ${selfScaffoldReviews.noop_count}`,
                    `reviewed changes: ${selfScaffoldReviews.reviewed_change_count}`,
                    selfScaffoldReviews.remaining_goal_review_count ? `goal reviews remaining: ${selfScaffoldReviews.remaining_goal_review_count}` : "",
                  ].filter((item): item is string => Boolean(item))}
                  empty="No self-scaffold review outcomes."
                />
                <List
                  items={selfScaffoldReviews.entries.slice(0, 4).map(
                    (entry) =>
                      `review #${entry.event_id} ${entry.status}: ${entry.reviewed_change_count} change(s) / ids ${
                        entry.reviewed_change_ids.slice(0, 3).join(", ") || "none"
                      }${entry.remaining_goal_review ? " / goal review remains" : ""}`,
                  )}
                  empty="No review outcome rows."
                />
                <p className="muted">{selfScaffoldReviews.recommended_action}</p>
              </>
            ) : null}
            {selfScaffoldRollbackIntents?.intent_count ? (
              <>
                <List
                  items={[
                    `rollback intents: ${selfScaffoldRollbackIntents.status} / total ${selfScaffoldRollbackIntents.intent_count}`,
                    `patch rollback candidates: ${selfScaffoldRollbackIntents.patch_rollback_count}`,
                    `steering intents: ${selfScaffoldRollbackIntents.steering_count}`,
                    selfScaffoldRollbackIntents.latest_review_event_id
                      ? `latest review: #${selfScaffoldRollbackIntents.latest_review_event_id}`
                      : "",
                  ].filter((item): item is string => Boolean(item))}
                  empty="No self-scaffold rollback intents."
                />
                <List
                  items={selfScaffoldRollbackIntents.entries.slice(0, 4).map(
                    (entry) =>
                      `intent ${entry.id} ${entry.action_kind}/${entry.status}: tool ${entry.proposed_tool || "none"} / approval ${
                        entry.requires_approval ? "required" : "not required"
                      } / automatic ${entry.mutation_automatic ? "yes" : "no"}${entry.patch_id ? ` / patch ${entry.patch_id}` : ""}`,
                  )}
                  empty="No rollback intent rows."
                />
                <p className="muted">{selfScaffoldRollbackIntents.recommended_action}</p>
              </>
            ) : null}
            <List
              items={(selfScaffold?.changes ?? [])
                .slice(-5)
                .map(
                  (item) =>
                    `${item.kind}/${item.status}: ${item.intent}${item.reversible ? ` / reverse: ${item.reverse_hint}` : ""}`,
                )}
              empty="No scaffold changes."
            />
          </Panel>
          <Panel title="Progress" icon={<Gauge size={18} />}>
            <p className="focus-text">
              {runProgress?.summary || "No progress report yet."}
            </p>
            <List
              items={[
                runProgress ? `status: ${runProgress.status}` : "",
                runProgress ? `tasks: ${runProgress.task_completed}/${runProgress.task_total} (${runProgress.task_progress_percent}%)` : "",
                runProgress
                  ? `acceptance: ${runProgress.acceptance_verified}/${runProgress.acceptance_total} (${runProgress.acceptance_coverage_percent}%)`
                  : "",
                runProgress ? `workspace changes: ${runProgress.workspace_change_count}` : "",
                runProgress ? `pending approvals: ${runProgress.pending_approval_count}` : "",
                runProgress?.latest_autonomy_decision
                  ? `autonomy: ${runProgress.latest_autonomy_decision}`
                  : "",
                runProgress?.latest_verification_outcome
                  ? `verification: ${runProgress.latest_verification_outcome}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No progress details."
            />
            <p className="muted">
              {runProgress
                ? `${runProgress.can_keep_running ? "can keep running" : "do not auto-continue"} / ${
                    runProgress.should_pause ? "pause recommended" : "no pause required"
                  }`
                : ""}
            </p>
            <List items={runProgress?.next_actions ?? []} empty="No progress next actions." />
          </Panel>
          <Panel title="Report Integrity" icon={<ListChecks size={18} />}>
            <p className="focus-text">
              {reportIntegrity?.summary || "No report integrity check yet."}
            </p>
            <List
              items={[
                reportIntegrity ? `status: ${reportIntegrity.status}` : "",
                reportIntegrity ? `checks: ${reportIntegrity.ok_count}/${reportIntegrity.check_count}` : "",
                reportIntegrity ? `missing: ${reportIntegrity.missing_count}` : "",
                reportIntegrity ? `stale: ${reportIntegrity.stale_count}` : "",
                reportIntegrity ? `mismatch: ${reportIntegrity.mismatch_count}` : "",
                reportIntegrity?.latest_event_id ? `latest event: ${reportIntegrity.latest_event_id}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No integrity details."
            />
            <p className="muted">{reportIntegrity?.recommended_action ?? ""}</p>
            {desktopEffectIntegrityNeedsRepair ? (
              <div className="queue-item watch">
                <div>
                  <strong>Desktop Proof Repair</strong>
                  <p>
                    {formatLocalTextTimestamps(
                      desktopEffectProofGate.action || "Repair stale desktop-effect proof handoff metadata.",
                    )}
                  </p>
                  <small>
                    {selectedDesktopEffectQueueItem
                      ? `${selectedDesktopEffectQueueItem.method} ${selectedDesktopEffectQueueItem.endpoint}`
                      : selectedId
                        ? `POST /api/runs/${selectedId}/desktop-effect/verify`
                        : "No selected run."}
                  </small>
                  <small>
                    {desktopEffectIntegrityChecks
                      .slice(0, 2)
                      .map((item) => `${item.status}: ${item.section}`)
                      .join(" / ")}
                  </small>
                </div>
                <div className="queue-actions">
                  <button type="button" onClick={runDesktopEffectProofFromGate} disabled={busy || !selectedId}>
                    <Monitor size={16} />
                    {selectedDesktopEffectQueueItem ? desktopEffectProofGate.buttonLabel : "Repair Proof"}
                  </button>
                </div>
              </div>
            ) : null}
            {activeDesktopEffectProofRepairs?.total_count ? (
              <>
                <List
                  items={[
                    `desktop repairs: ${activeDesktopEffectProofRepairs.latest_outcome || "unknown"} / total ${activeDesktopEffectProofRepairs.total_count}`,
                    `metadata refreshes: ${activeDesktopEffectProofRepairs.metadata_refreshed_count}`,
                    `captures: ${activeDesktopEffectProofRepairs.capture_completed_count} ok / ${activeDesktopEffectProofRepairs.capture_failed_count} failed`,
                    `blocked: ${activeDesktopEffectProofRepairs.blocked_count}`,
                  ]}
                  empty="No desktop proof repair outcomes."
                />
                <List
                  items={activeDesktopEffectProofRepairs.entries.slice(0, 3).map(
                    (entry) =>
                      `repair #${entry.event_id} ${entry.outcome}: proof ${entry.previous_proof_status || "unknown"} -> ${
                        entry.refreshed_proof_status || "unknown"
                      } / integrity ${entry.previous_integrity_status || "unknown"} -> ${entry.refreshed_integrity_status || "unknown"}`,
                  )}
                  empty="No desktop proof repair rows."
                />
                <p className="muted">{activeDesktopEffectProofRepairs.recommended_action}</p>
              </>
            ) : null}
            {latestReportIntegrityRefresh && (
              <>
                <List
                  items={[
                    `refresh #${latestReportIntegrityRefresh.event_id}: ${
                      latestReportIntegrityRefresh.previous_report_status || "unknown"
                    } -> ${latestReportIntegrityRefresh.report_status || "unknown"}`,
                    `reasons: ${latestReportIntegrityRefresh.reason_count}`,
                    latestReportIntegrityRefresh.preflight_event_id
                      ? `preflight #${latestReportIntegrityRefresh.preflight_event_id}: ${
                          latestReportIntegrityRefresh.preflight_event_kind
                        } accepted ${latestReportIntegrityRefresh.preflight_accepted}`
                      : "",
                  ].filter((item): item is string => Boolean(item))}
                  empty="No report integrity refreshes."
                />
                <List
                  items={latestReportIntegrityRefresh.reasons.slice(0, 4).map((reason) => `refresh reason: ${reason}`)}
                  empty="No refresh reasons recorded."
                />
              </>
            )}
            <List
              items={(reportIntegrity?.checks ?? [])
                .filter((item) => item.status !== "ok")
                .slice(0, 6)
                .map((item) => `${item.status}: ${item.section} - ${item.summary}`)}
              empty="No missing, stale, or mismatched sections."
            />
          </Panel>
          <Panel title="Checkpoint Quality" icon={<FileText size={18} />}>
            <p className="focus-text">
              {checkpointQuality?.summary || "No checkpoint quality report yet."}
            </p>
            <List
              items={[
                checkpointQuality ? `status: ${checkpointQuality.status}` : "",
                checkpointQuality ? `run note: ${checkpointQuality.run_note_present ? "present" : "missing"}` : "",
                checkpointQuality ? `note chars: ${checkpointQuality.run_note_chars}` : "",
                checkpointQuality
                  ? `anchors: goal ${checkpointQuality.has_active_goal ? "yes" : "no"}, next ${
                      checkpointQuality.has_next_action ? "yes" : "no"
                    }, resume ${checkpointQuality.has_resume_prompt ? "yes" : "no"}`
                  : "",
                checkpointQuality?.expected_report_integrity_refresh
                  ? `refresh: #${checkpointQuality.expected_refresh_event_id} ${
                      checkpointQuality.has_report_integrity_refresh ? "present" : "missing"
                    }`
                  : "",
                checkpointQuality ? `blockers: ${checkpointQuality.blocker_count}` : "",
                checkpointQuality ? `warnings: ${checkpointQuality.warning_count}` : "",
                ...checkpointQualityResumeLines(checkpointQualityResumes),
              ].filter((item): item is string => Boolean(item))}
              empty="No checkpoint quality details."
            />
            <p className="muted">{checkpointQuality?.recommended_action ?? ""}</p>
            {checkpointQualityResumes && checkpointQualityResumes.status !== "none" && (
              <p className="muted">{checkpointQualityResumes.recommended_action}</p>
            )}
            <List
              items={(checkpointQuality?.issues ?? [])
                .slice(0, 6)
                .map((item) => `${item.severity}: ${item.id} - ${item.summary}`)}
              empty="No checkpoint anchor issues."
            />
          </Panel>
          <Panel title="Objective Readiness" icon={<Target size={18} />}>
            <p className="focus-text">
              {objectiveReadiness?.summary || "No objective readiness matrix yet."}
            </p>
            <List
              items={[
                objectiveReadiness ? `status: ${objectiveReadiness.status}` : "",
                objectiveReadiness ? `verified: ${objectiveReadiness.verified_count}` : "",
                objectiveReadiness ? `partial: ${objectiveReadiness.partial_count}` : "",
                objectiveReadiness ? `missing: ${objectiveReadiness.missing_count}` : "",
                objectiveReadiness ? `failed: ${objectiveReadiness.failed_count}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No readiness counts."
            />
            <p className="muted">{objectiveReadiness?.recommended_action ?? ""}</p>
            <List items={objectiveReadiness?.next_actions ?? []} empty="No objective readiness actions." />
            <List
              items={(objectiveReadiness?.items ?? []).map(
                (item) =>
                  `${item.status}: ${item.id} - ${item.requirement} | proof ${item.proof.tool_kind}/${item.proof.evidence_label}${
                    item.proof.strategy ? `/${item.proof.strategy}` : ""
                  }: ${item.proof.action}${
                    item.preferred_proof.tool_kind
                      ? ` | prefer ${item.preferred_proof.tool_kind}/${item.preferred_proof.strategy} (${item.preferred_proof.confidence}): ${item.preferred_proof.action}`
                      : ""
                  }${
                    item.latest_outcome.id
                      ? ` | outcome ${item.latest_outcome.outcome} via ${item.latest_outcome.tool}${
                          item.latest_outcome.strategy ? `/${item.latest_outcome.strategy}` : ""
                        }: ${item.latest_outcome.summary}`
                      : ""
                  }`,
              )}
              empty="No objective readiness items."
            />
          </Panel>
          <Panel title="Readiness Claim" icon={<Check size={18} />}>
            <p className="focus-text">
              {readinessCompletion?.summary || "No readiness completion gate yet."}
            </p>
            <List
              items={[
                readinessCompletion ? `status: ${readinessCompletion.status}` : "",
                readinessCompletion ? `claim: ${readinessCompletion.can_claim_milestone}` : "",
                readinessCompletion ? `confidence: ${readinessCompletion.confidence}` : "",
                readinessCompletion
                  ? `verified: ${readinessCompletion.verified_count}/${readinessCompletion.required_verified_count}`
                  : "",
                readinessCompletion ? `blockers: ${readinessCompletion.blocking_count}` : "",
                readinessCompletion ? `warnings: ${readinessCompletion.warning_count}` : "",
                readinessCompletion ? `open preferences: ${readinessCompletion.open_preference_count}` : "",
                readinessCompletion?.self_scaffold_status
                  ? `self scaffold: ${readinessCompletion.self_scaffold_status} pending ${readinessCompletion.self_scaffold_pending_review_count}`
                  : "",
                readinessCompletion?.self_scaffold_review_count
                  ? `scaffold reviews: ${readinessCompletion.self_scaffold_reviewed_change_count}/${readinessCompletion.self_scaffold_review_count}`
                  : "",
                readinessCompletion && (readinessCompletion.source_visible_required_label_count || readinessCompletion.source_visible_matched_label_count)
                  ? `source-visible labels: ${readinessCompletion.source_visible_matched_label_count}/${readinessCompletion.source_visible_required_label_count}`
                  : "",
                readinessCompletion && readinessCompletion.readiness_proof_source_ref_count
                  ? `proof source refs: ${readinessCompletion.readiness_proof_source_ref_count} (${readinessCompletion.readiness_proof_source_ref_labels.join(", ") || "unlabeled"})`
                  : "",
                readinessCompletion && readinessCompletion.source_visible_missing_ref_labels.length
                  ? `missing proof refs: ${readinessCompletion.source_visible_missing_ref_labels.join(", ")}`
                  : "",
                readinessCompletion?.rehearsal_ledger_status
                  ? `rehearsal: ${readinessCompletion.rehearsal_ledger_status}`
                  : "",
                readinessCompletion?.rehearsal_latest_run_id
                  ? `rehearsal latest: ${readinessCompletion.rehearsal_latest_run_id}`
                  : "",
                readinessCompletion?.dispatch_restart_smoke_ledger_status
                  ? `dispatch smoke: ${readinessCompletion.dispatch_restart_smoke_ledger_status}`
                  : "",
                readinessCompletion?.dispatch_restart_smoke_latest_run_id
                  ? `dispatch smoke latest: ${readinessCompletion.dispatch_restart_smoke_latest_run_id}`
                  : "",
                readinessCompletion
                  ? `dispatch smoke history: ${readinessCompletion.dispatch_restart_smoke_passed_count} passed / ${readinessCompletion.dispatch_restart_smoke_failed_count} failed`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No readiness claim details."
            />
            <List
              items={(readinessCompletion?.checks ?? []).map(
                (item) => `${item.status}: ${item.id} - ${item.summary}`,
              )}
              empty="No readiness completion checks."
            />
            <List items={readinessCompletion?.next_actions ?? []} empty="No readiness claim actions." />
          </Panel>
          <Panel title="Readiness Source Refs" icon={<Share size={18} />}>
            <p className="focus-text">
              {readinessSourceRefs?.summary || "No readiness source-ref preview yet."}
            </p>
            <List
              items={[
                readinessSourceRefs ? `status: ${readinessSourceRefs.status}` : "",
                readinessSourceRefs?.readiness_completion_status
                  ? `completion: ${readinessSourceRefs.readiness_completion_status}`
                  : "",
                readinessSourceRefs?.readiness_proof_history_status
                  ? `proof history: ${readinessSourceRefs.readiness_proof_history_status}`
                  : "",
                (readinessSourceRefs?.source_visible_labels ?? []).length
                  ? `source-visible: ${(readinessSourceRefs?.source_visible_labels ?? []).join(", ")}`
                  : "",
                (readinessSourceRefs?.source_evidence_labels ?? []).length
                  ? `source evidence: ${(readinessSourceRefs?.source_evidence_labels ?? []).join(", ")}`
                  : "",
                (readinessSourceRefs?.proof_ref_labels ?? []).length
                  ? `proof refs: ${(readinessSourceRefs?.proof_ref_labels ?? []).join(", ")}`
                  : "",
                (readinessSourceRefs?.missing_source_evidence_labels ?? []).length
                  ? `missing evidence: ${(readinessSourceRefs?.missing_source_evidence_labels ?? []).join(", ")}`
                  : "",
                (readinessSourceRefs?.missing_proof_ref_labels ?? []).length
                  ? `missing proof refs: ${(readinessSourceRefs?.missing_proof_ref_labels ?? []).join(", ")}`
                  : "",
                readinessSourceRefs ? `entries: ${readinessSourceRefs.source_evidence_entry_count}` : "",
                readinessSourceRefs ? `refs: ${readinessSourceRefs.proof_ref_count}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No source-ref counts."
            />
            <List
              items={(readinessSourceRefs?.labels ?? []).map((item) => {
                const state = item.missing_from_proof_history
                  ? "missing proof"
                  : item.missing_from_source_evidence
                    ? "missing evidence"
                    : item.present_in_proof_history
                      ? "ready"
                      : "observed";
                const criteria = item.linked_criteria.length ? ` criteria: ${item.linked_criteria.slice(0, 2).join("; ")}` : "";
                return `${state}: ${item.label} | evidence ${item.source_evidence_count} | proof ${item.proof_ref_count}${criteria}`;
              })}
              empty="No source-ref label rows."
            />
            <List
              items={(readinessSourceRefs?.proof_refs ?? []).slice(0, 6).map(
                (ref) => `${ref.evidence_label}:${ref.kind}:${ref.id || ref.title || ref.target}`,
              )}
              empty="No readiness proof refs linked yet."
            />
            <p className="muted">{readinessSourceRefs?.recommended_action ?? ""}</p>
          </Panel>
          <Panel title="Readiness Rehearsal" icon={<RotateCcw size={18} />}>
            <p className="focus-text">
              {readinessRehearsalLedger?.summary || "No readiness rehearsal recorded."}
            </p>
            <div className="panel-actions">
              <button
                className="primary"
                type="button"
                onClick={runReadinessRehearsal}
                disabled={busy || rehearsalBusy}
              >
                <RotateCcw size={16} />
                {rehearsalBusy ? "Running" : "Run Smoke"}
              </button>
            </div>
            <List
              items={[
                readinessRehearsalLedger ? `ledger: ${readinessRehearsalLedger.status}` : "",
                readinessRehearsalLedger
                  ? `runs: ${readinessRehearsalLedger.total_count} total / ${readinessRehearsalLedger.passed_count} passed / ${readinessRehearsalLedger.failed_count} failed`
                  : "",
                readinessRehearsalLedger?.running_count
                  ? `running: ${readinessRehearsalLedger.running_count}`
                  : "",
                readinessRehearsalLedger?.latest
                  ? `latest: ${readinessRehearsalLedger.latest.status} ${readinessRehearsalLedger.latest.run_id}`
                  : "",
                readinessRehearsalLedger?.latest?.compact_context_tokens
                  ? `latest context: ${readinessRehearsalLedger.latest.compact_context_tokens} tokens`
                  : "",
                readinessRehearsalLedger?.latest
                  ? `latest scaffold review: ${readinessRehearsalLedger.latest.self_scaffold_reviewed ? "yes" : "no"} / event ${
                      readinessRehearsalLedger.latest.self_scaffold_review_event_id || "none"
                    } / changes ${readinessRehearsalLedger.latest.self_scaffold_reviewed_change_count}`
                  : "",
                readinessRehearsal ? `selected: ${readinessRehearsal.status}` : "",
                readinessRehearsal?.run_id ? `run: ${readinessRehearsal.run_id}` : "",
                readinessRehearsal ? `restart: ${readinessRehearsal.restart_simulated ? "yes" : "no"}` : "",
                readinessRehearsal ? `replay: ${readinessRehearsal.replay_attached ? "yes" : "no"}` : "",
                readinessRehearsal ? `handoff: ${readinessRehearsal.handoff_attached ? "yes" : "no"}` : "",
                readinessRehearsal ? `scaffold review: ${readinessRehearsal.self_scaffold_reviewed ? "yes" : "no"}` : "",
                readinessRehearsal?.self_scaffold_review_event_id
                  ? `scaffold review event: ${readinessRehearsal.self_scaffold_review_event_id}`
                  : "",
                readinessRehearsal
                  ? `scaffold reviewed changes: ${readinessRehearsal.self_scaffold_reviewed_change_count}`
                  : "",
                readinessRehearsal
                  ? `post-review handoff: goal ${readinessRehearsal.post_review_handoff_goal_preserved ? "yes" : "no"} / next ${
                      readinessRehearsal.post_review_handoff_next_action_preserved ? "yes" : "no"
                    }`
                  : "",
                readinessRehearsal
                  ? `post-review resume prompt: goal ${readinessRehearsal.post_review_resume_prompt_goal_preserved ? "yes" : "no"} / next ${
                      readinessRehearsal.post_review_resume_prompt_next_action_preserved ? "yes" : "no"
                    }`
                  : "",
                readinessRehearsal?.accepted_event_id ? `accepted event: ${readinessRehearsal.accepted_event_id}` : "",
                readinessRehearsal?.completed_event_id ? `completed event: ${readinessRehearsal.completed_event_id}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No rehearsal details."
            />
            <List
              items={(readinessRehearsalLedger?.entries ?? []).map(
                (entry) =>
                  `${entry.status}: ${entry.run_id} | steps ${entry.passed_steps}/${entry.step_count}${
                    entry.failed_steps ? `, failed ${entry.failed_steps}` : ""
                  } | replay ${entry.replay_attached ? "yes" : "no"} | handoff ${
                    entry.handoff_attached ? "yes" : "no"
                  } | scaffold ${entry.self_scaffold_reviewed ? "yes" : "no"} | post-review ${
                    entry.post_review_handoff_goal_preserved &&
                    entry.post_review_handoff_next_action_preserved &&
                    entry.post_review_resume_prompt_goal_preserved &&
                    entry.post_review_resume_prompt_next_action_preserved
                      ? "yes"
                      : "no"
                  }`,
              )}
              empty="No rehearsal history."
            />
            <List
              items={(readinessRehearsal?.steps ?? []).map(
                (step) =>
                  `${step.status}: ${step.id} - ${step.summary}${
                    step.event_kind ? ` | ${step.event_kind} #${step.event_id}` : ""
                  }`,
              )}
              empty="No rehearsal steps."
            />
            <p className="muted">{readinessRehearsalLedger?.next_action || readinessRehearsal?.next_action || ""}</p>
          </Panel>
          <Panel title="Readiness Proof History" icon={<ListChecks size={18} />}>
            <p className="focus-text">
              {readinessProofHistory?.summary || "No readiness proof history yet."}
            </p>
            <List
              items={[
                readinessProofHistory ? `status: ${readinessProofHistory.status}` : "",
                readinessProofHistory ? `self-scaffold reviews: ${readinessProofHistory.self_scaffold_review_count}` : "",
                readinessProofHistory ? `post-review handoff: ${readinessProofHistory.post_review_handoff_count}` : "",
                readinessProofHistory ? `resume prompt preservation: ${readinessProofHistory.resume_prompt_preservation_count}` : "",
                readinessProofHistory ? `readiness claims: ${readinessProofHistory.readiness_claim_count}` : "",
                readinessProofHistory?.source_evidence_ref_count ? `source refs: ${readinessProofHistory.source_evidence_ref_count}` : "",
                (readinessProofHistory?.source_evidence_labels ?? []).length ? `source labels: ${(readinessProofHistory?.source_evidence_labels ?? []).join(", ")}` : "",
                readinessProofHistory?.blocking_count ? `blocks: ${readinessProofHistory.blocking_count}` : "",
                readinessProofHistory?.latest_event_id ? `latest event: #${readinessProofHistory.latest_event_id}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No readiness proof counts."
            />
            <List
              items={(readinessProofHistory?.entries ?? []).slice(-8).map((entry) => {
                const event = entry.event_id ? `#${entry.event_id}` : "report";
                const step = entry.step_id ? ` / ${entry.step_id}` : "";
                const evidence = entry.evidence.length ? ` [${entry.evidence.slice(0, 3).join("; ")}]` : "";
                const sources = entry.source_refs.length
                  ? ` sources: ${entry.source_refs
                      .slice(0, 2)
                      .map((ref) => `${ref.evidence_label}:${ref.kind}:${ref.id || ref.title || ref.target}`)
                      .join("; ")}`
                  : "";
                return `${event} ${entry.status}: ${entry.proof_type}/${entry.source}${step} - ${entry.summary}${evidence}${sources}`;
              })}
              empty="No filtered proof history entries."
            />
            <p className="muted">{readinessProofHistory?.source_evidence_summary ?? ""}</p>
            <p className="muted">{readinessProofHistory?.recommended_action ?? ""}</p>
          </Panel>          <Panel title="Run Health" icon={<Gauge size={18} />}>
            <p className="focus-text">
              {selected?.state.run_health.summary || "No health score yet."}
            </p>
            <List
              items={[
                selected?.state.run_health.level ? `level: ${selected.state.run_health.level}` : "",
                selected?.state.run_health.recommended_action
                  ? `action: ${selected.state.run_health.recommended_action}`
                  : "",
                selected?.state.run_health.score !== undefined
                  ? `score: ${selected.state.run_health.score}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No health summary."
            />
            <List
              items={(selected?.state.run_health.signals ?? [])
                .slice(0, 5)
                .map((item) => `${item.severity}: ${item.summary}`)}
              empty="No health signals."
            />
          </Panel>
          <Panel title="Policy Preview" icon={<ListChecks size={18} />}>
            <p className="focus-text">
              {policySimulation?.summary || "No policy simulation yet."}
            </p>
            <List
              items={[
                policySimulation?.policy_action ? `action: ${policySimulation.policy_action}` : "",
                policySimulation?.predicted_status
                  ? `status: ${policySimulation.current_status} -> ${policySimulation.predicted_status}`
                  : "",
                policySimulation?.predicted_milestone
                  ? `milestone: ${policySimulation.current_milestone} -> ${policySimulation.predicted_milestone}`
                  : "",
                policySimulation ? `safe resume: ${policySimulation.safe_to_resume ? "yes" : "no"}` : "",
                policySimulation ? `auto resume: ${policySimulation.auto_resume_eligible ? "eligible" : "gated"}` : "",
                policySimulation?.recommended_tool
                  ? `recommendation: ${policySimulation.recommended_label} via ${policySimulation.recommended_tool}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No policy prediction."
            />
            <p className="muted">{policySimulation?.next_action ?? ""}</p>
            <List items={policySimulation?.effects ?? []} empty="No predicted effects." />
          </Panel>
          <Panel title="Autonomy" icon={<Target size={18} />}>
            <p className="focus-text">
              {autonomyDecisions?.summary || "No autonomy decision ledger yet."}
            </p>
            <List
              items={[
                autonomyDecisions ? `decisions: ${autonomyDecisions.decision_count}` : "",
                autonomyDecisions ? `continue: ${autonomyDecisions.continue_count}` : "",
                autonomyDecisions ? `recover: ${autonomyDecisions.recover_count}` : "",
                autonomyDecisions ? `wait: ${autonomyDecisions.wait_count}` : "",
                autonomyDecisions ? `complete: ${autonomyDecisions.complete_count}` : "",
                autonomyDecisions ? `blocked: ${autonomyDecisions.blocked_count}` : "",
                autonomyDecisions?.current_policy_action
                  ? `current policy: ${autonomyDecisions.current_policy_action}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No autonomy counts."
            />
            <p className="muted">{autonomyDecisions?.recommended_action ?? ""}</p>
            <List
              items={(autonomyDecisions?.decisions ?? [])
                .slice(-5)
                .map(
                  (item) =>
                    `${item.decision} ${item.source}: ${
                      item.health_action
                        ? `${item.health_level}/${item.health_action}/${item.health_score}`
                        : item.kind
                    } - ${item.reason}`,
                )}
              empty="No autonomy decisions."
            />
          </Panel>
          <Panel title="Resume Decisions" icon={<RotateCcw size={18} />}>
            <p className="focus-text">
              {resumeDecisions?.comparison_summary || "No resume decisions yet."}
            </p>
            <List
              items={[
                resumeDecisions ? `decisions: ${resumeDecisions.decision_count}` : "",
                resumeDecisions ? `accepted: ${resumeDecisions.accepted_count}` : "",
                resumeDecisions ? `blocked: ${resumeDecisions.blocked_count}` : "",
                resumeDecisions
                  ? `current vs accepted: ${resumeDecisions.current_matches_last_accepted ? "matches" : "differs"}`
                  : "",
                resumeDecisions?.latest_decision?.id
                  ? `latest: ${resumeDecisions.latest_decision.accepted ? "accepted" : "blocked"} ${resumeDecisions.latest_decision.source} ${resumeDecisions.latest_decision.policy_action}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No resume ledger yet."
            />
            <p className="muted">{resumeDecisions?.recommended_action ?? ""}</p>
            <List
              items={(resumeDecisions?.decisions ?? [])
                .slice(-5)
                .map(
                  (item) =>
                    `${item.accepted ? "accepted" : "blocked"} ${item.source}: ${item.policy_action} -> ${item.predicted_status}/${item.predicted_milestone}`,
                )}
              empty="No compact preflight decisions."
            />
          </Panel>
          <Panel title="Resume Quality" icon={<Brain size={18} />}>
            <p className="focus-text">
              {resumePromptQuality?.summary || "No resume prompt quality report yet."}
            </p>
            <List
              items={[
                resumePromptQuality ? `status: ${resumePromptQuality.status}` : "",
                resumePromptQuality ? `score: ${resumePromptQuality.score}` : "",
                resumePromptQuality ? `ready: ${resumePromptQuality.ready_to_resume ? "yes" : "no"}` : "",
                resumePromptQuality ? `concrete next: ${resumePromptQuality.concrete_next_action ? "yes" : "no"}` : "",
                resumePromptQuality?.context_coverage_status
                  ? `context: ${resumePromptQuality.context_coverage_status}`
                  : "",
                resumePromptQuality?.prompt_chars ? `prompt chars: ${resumePromptQuality.prompt_chars}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No resume quality counts."
            />
            <p className="muted">{resumePromptQuality?.recommended_action ?? ""}</p>
            <List
              items={(resumePromptQuality?.issues ?? [])
                .slice(0, 8)
                .map((issue) => `${issue.severity}: ${issue.id} - ${issue.summary}`)}
              empty="No resume prompt quality issues."
            />
          </Panel>
          <Panel title="Resume Drift" icon={<RotateCcw size={18} />}>
            <p className="focus-text">
              {resumeHandoffDiff?.summary || "No resume handoff drift report yet."}
            </p>
            <List
              items={[
                resumeHandoffDiff ? `status: ${resumeHandoffDiff.status}` : "",
                resumeHandoffDiff ? `ready: ${resumeHandoffDiff.ready_to_continue ? "yes" : "no"}` : "",
                resumeHandoffDiff ? `baseline: ${resumeHandoffDiff.latest_accepted_event_id || "none"}` : "",
                resumeHandoffDiff ? `changes: ${resumeHandoffDiff.changed_count}` : "",
                resumeHandoffDiff ? `blockers: ${resumeHandoffDiff.blocker_count}` : "",
                resumeHandoffDiff ? `warnings: ${resumeHandoffDiff.warning_count}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No resume drift counts."
            />
            <p className="muted">{resumeHandoffDiff?.recommended_action ?? ""}</p>
            <List
              items={(resumeHandoffDiff?.changes ?? [])
                .slice(0, 8)
                .map((change) => `${change.severity}: ${change.field} - ${change.summary}`)}
              empty="No resume handoff drift changes."
            />
          </Panel>
          <Panel title="Ornith Preflight" icon={<ListChecks size={18} />}>
            <p className="focus-text">
              {activeOrnithPreflight?.summary || "No Ornith preflight loaded."}
            </p>
            <List
              items={[
                ornithPreflight ? `launch: ${ornithPreflight.status} / ready ${ornithPreflight.ready_to_start}` : "",
                selectedOrnithPreflight
                  ? `selected: ${selectedOrnithPreflight.status} / resume ${selectedOrnithPreflight.ready_to_resume}`
                  : "",
                activeOrnithPreflight ? `profile: ${activeOrnithPreflight.model_profile_id}` : "",
                activeOrnithPreflight ? `model: ${activeOrnithPreflight.model_name}` : "",
                activeOrnithPreflight
                  ? `tools: web ${activeOrnithPreflight.web_enabled} / browser ${activeOrnithPreflight.browser_enabled} / desktop ${activeOrnithPreflight.desktop_enabled}`
                  : "",
                activeOrnithPreflight?.context_pressure
                  ? `context: ${activeOrnithPreflight.context_pressure} ${activeOrnithPreflight.context_tokens}/${activeOrnithPreflight.context_target_tokens}`
                  : "",
                activeOrnithPreflight?.resume_prompt_quality
                  ? `resume quality: ${activeOrnithPreflight.resume_prompt_quality.status} ${activeOrnithPreflight.resume_prompt_quality.score}`
                  : "",
                activeOrnithPreflight?.resume_handoff_diff
                  ? `resume drift: ${activeOrnithPreflight.resume_handoff_diff.status} ${activeOrnithPreflight.resume_handoff_diff.changed_count}`
                  : "",
                activeOrnithPreflight?.checkpoint_quality
                  ? `checkpoint: ${activeOrnithPreflight.checkpoint_quality.status} blockers ${activeOrnithPreflight.checkpoint_quality.blocker_count}`
                  : "",
                activeOrnithPreflight
                  ? `smoke: ${activeOrnithPreflight.readiness_smoke_status} / dispatch ${activeOrnithPreflight.dispatch_restart_smoke_status}`
                  : "",
                activeOrnithPreflight
                  ? `approvals: ${activeOrnithPreflight.pending_approval_count} / attention ${activeOrnithPreflight.supervisor_attention_count}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No preflight details."
            />
            <List
              items={(activeOrnithPreflight?.items ?? [])
                .slice(0, 9)
                .map((item) => `${item.status}: ${item.category}/${item.id} - ${item.summary}`)}
              empty="No preflight checklist items."
            />
            <List items={activeOrnithPreflight?.next_actions ?? []} empty="No preflight actions." />
          </Panel>
          <Panel title="Preflight Actions" icon={<Send size={18} />}>
            <p className="focus-text">
              {ornithPreflightActions?.summary || "No Ornith preflight action ledger yet."}
            </p>
            <List
              items={[
                ornithPreflightActions ? `completed: ${ornithPreflightActions.completed_count}` : "",
                ornithPreflightActions ? `dispatched: ${ornithPreflightActions.dispatched_count}` : "",
                ornithPreflightActions ? `context checkpoints: ${ornithPreflightActions.context_checkpoint_count}` : "",
                ornithPreflightActions ? `handoff refreshes: ${ornithPreflightActions.handoff_refresh_count}` : "",
                ornithPreflightActions ? `smokes: ${ornithPreflightActions.smoke_count}` : "",
                ornithPreflightActions?.latest_action ? `latest: ${ornithPreflightActions.latest_action}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No preflight action counts."
            />
            <List
              items={(ornithPreflightActions?.entries ?? [])
                .slice(0, 8)
                .map((entry) => {
                  const context = entry.context_pressure
                    ? ` context ${entry.context_pressure} ${entry.context_tokens}/${entry.context_target_tokens}`
                    : "";
                  return `#${entry.event_id} ${entry.status}: ${entry.item_id}/${entry.ui_target}${context} - ${entry.message}`;
                })}
              empty="No preflight action events."
            />
            <p className="muted">{ornithPreflightActions?.recommended_action ?? ""}</p>
          </Panel>
          <Panel title="Preflight Warnings" icon={<AlertTriangle size={18} />}>
            <p className="focus-text">
              {preflightWarnings?.summary || "No Ornith preflight warning history yet."}
            </p>
            <List
              items={[
                preflightWarnings ? `warnings: ${preflightWarnings.warning_count}` : "",
                preflightWarnings ? `blocks: ${preflightWarnings.block_count}` : "",
                preflightWarnings ? `reorients: ${preflightWarnings.action_context_reorient_count}` : "",
                preflightWarnings?.latest_reorient_event_id
                  ? `latest reorient: #${preflightWarnings.latest_reorient_event_id}`
                  : "",
                readinessCompletion
                  ? `readiness gate: ${readinessCompletion.ornith_preflight_warning_count} warning(s), ${readinessCompletion.ornith_preflight_block_count} block(s)`
                  : "",
                preflightWarningGate ? `gate check: ${preflightWarningGate.status} - ${preflightWarningGate.summary}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No preflight warning counts."
            />
            <List
              items={(preflightWarnings?.entries ?? [])
                .slice(-8)
                .map((entry) => {
                  const event = entry.event_id ? `#${entry.event_id} ` : "";
                  const evidence = entry.evidence.length ? ` [${entry.evidence.slice(0, 3).join("; ")}]` : "";
                  return `${event}${entry.status}: ${entry.source}/${entry.item_id} - ${entry.summary}${evidence}`;
                })}
              empty="No preflight warning entries."
            />
            <p className="muted">
              {preflightWarnings?.recommended_action || preflightWarningGate?.next_action || ""}
            </p>
          </Panel>
          <Panel title="Supervisor" icon={<Gauge size={18} />}>
            <p className="focus-text">
              {supervisor
                ? `${supervisor.auto_resumed} resumed / ${supervisor.recovered} recovered / ${supervisor.live} live`
                : "No startup pass recorded."}
            </p>
            <p className="muted">
              {supervisor
                ? `auto-resume ${supervisor.auto_resume_enabled ? "on" : "off"} / max ${supervisor.auto_resume_max_runs} / attention ${supervisor.operator_attention_count} / goal ${supervisor.goal_confirmation_attention_count} / scaffold ${supervisor.self_scaffold_attention_count} / scaffold rollback ${supervisor.self_scaffold_rollback_attention_count} / action gate ${supervisor.action_readiness_attention_count} / smoke ${supervisor.readiness_smoke_attention_count} / proof ${supervisor.readiness_proof_history_attention_count} / desktop proof ${supervisor.desktop_effect_proof_attention_count} / source refs ${supervisor.readiness_source_ref_attention_count} / dispatch smoke ${supervisor.operator_dispatch_restart_smoke_attention_count} / checkpoint ${supervisor.checkpoint_quality_attention_count}`
                : ""}
            </p>
            <List
              items={[
                selectedSupervisorRun?.readiness_source_ref_preview_status
                  ? `source-ref preview: ${selectedSupervisorRun.readiness_source_ref_preview_status}`
                  : "",
                (selectedSupervisorRun?.readiness_source_ref_preview_missing_evidence_labels ?? []).length
                  ? `missing source evidence: ${(selectedSupervisorRun?.readiness_source_ref_preview_missing_evidence_labels ?? []).join(", ")}`
                  : "",
                (selectedSupervisorRun?.readiness_source_ref_preview_missing_proof_labels ?? []).length
                  ? `missing proof refs: ${(selectedSupervisorRun?.readiness_source_ref_preview_missing_proof_labels ?? []).join(", ")}`
                  : "",
                selectedSupervisorRun?.readiness_source_ref_preview_action
                  ? `source-ref action: ${selectedSupervisorRun.readiness_source_ref_preview_action}`
                  : "",
                selected?.state.run_lease.status ? `lease: ${selected.state.run_lease.status}` : "",
                selected?.state.run_lease.owner_id ? `owner: ${selected.state.run_lease.owner_id}` : "",
                selected?.state.run_lease.heartbeat_at ? `heartbeat: ${selected.state.run_lease.heartbeat_at}` : "",
                selected?.state.run_lease.expires_at ? `expires: ${selected.state.run_lease.expires_at}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No lease recorded for this run."
            />
            <List
              items={[
                supervisor?.readiness_rehearsal_ledger?.status
                  ? `smoke ledger: ${supervisor.readiness_rehearsal_ledger.status}`
                  : "",
                supervisor?.readiness_rehearsal_ledger?.latest?.run_id
                  ? `latest smoke: ${supervisor.readiness_rehearsal_ledger.latest.run_id}`
                  : "",
                supervisor?.readiness_rehearsal_ledger
                  ? `smoke history: ${supervisor.readiness_rehearsal_ledger.passed_count} passed / ${supervisor.readiness_rehearsal_ledger.failed_count} failed`
                  : "",
                supervisor?.operator_dispatch_restart_smoke_ledger?.status
                  ? `dispatch smoke ledger: ${supervisor.operator_dispatch_restart_smoke_ledger.status}`
                  : "",
                supervisor?.operator_dispatch_restart_smoke_ledger?.latest?.run_id
                  ? `latest dispatch smoke: ${supervisor.operator_dispatch_restart_smoke_ledger.latest.run_id}`
                  : "",
                supervisor?.operator_dispatch_restart_smoke_ledger
                  ? `dispatch smoke history: ${supervisor.operator_dispatch_restart_smoke_ledger.passed_count} passed / ${supervisor.operator_dispatch_restart_smoke_ledger.failed_count} failed`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No smoke ledgers."
            />
            <List
              items={(supervisor?.runs ?? [])
                .slice(0, 5)
                .map(supervisorRunSummary)}
              empty="No startup recovery actions."
            />
          </Panel>
          <Panel title="Model Profile" icon={<Brain size={18} />}>
            <p className="focus-text">{modelProfile?.display_name ?? "No model profile loaded."}</p>
            <List
              items={[
                modelProfile?.configured_model ? `model: ${modelProfile.configured_model}` : "",
                modelProfile?.id ? `profile: ${modelProfile.id}` : "",
                modelProfile ? `context target: ${modelProfile.effective_context_target_tokens}` : "",
                modelProfile ? `json retries: ${modelProfile.json_retries}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No model profile details."
            />
            <List
              items={[
                modelHealth
                  ? `connection: ${
                      modelHealth.ok
                        ? "ok"
                        : modelHealth.status === "timeout"
                          ? "timeout / warming or not responding"
                          : "error / not responding"
                    }`
                  : "",
                modelHealth ? `endpoint: ${modelHealth.base_url}` : "",
                modelHealth?.latency_ms ? `latency: ${modelHealth.latency_ms}ms` : "",
                modelHealth?.error ? `error: ${modelHealth.error}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="Model connection health not checked yet."
            />
            <List items={modelProfile?.weaknesses ?? []} empty="No model-specific guardrails." />
            <List
              items={[
                modelEval ? `eval score: ${modelEval.ok}/${modelEval.total} (${Math.round(modelEval.score * 100)}%)` : "",
                modelEval ? `fallback fixtures: ${modelEval.fallback_needed}` : "",
                modelEval ? `patch-first failures: ${modelEval.patch_first_fail}` : "",
                modelEval ? `repaired outputs: ${modelEval.repaired}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No Ornith eval fixture summary."
            />
            <List
              items={(modelEval?.cases ?? [])
                .filter((item) => !item.ok || item.fallback_needed || item.patch_first_ok === false)
                .map(
                  (item) =>
                    `${item.id}: ${item.fallback_needed ? "fallback" : item.ok ? "ok" : "risk"}${
                      item.normalized_tool ? ` / ${item.normalized_tool}` : ""
                    } - ${item.error || item.summary}`,
                )}
              empty="No eval risks in fixture set."
            />
            <List
              items={[
                modelQuality
                  ? `live quality: ${modelQuality.ok_count}/${modelQuality.interaction_count} ok across ${modelQuality.run_count} runs`
                  : "",
                modelQuality ? `live fallbacks: ${modelQuality.fallback_count}` : "",
                modelQuality ? `live repairs: ${modelQuality.repaired_count}` : "",
                modelQuality ? `live retries: ${modelQuality.retry_count}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No live model quality report."
            />
            <List
              items={(modelQuality?.patterns ?? [])
                .slice(0, 5)
                .map((item) => `${item.severity}: ${item.label} (${item.count}) - ${item.recommendation}`)}
              empty="No live prompt-quality patterns."
            />
            <List
              items={(modelQuality?.samples ?? [])
                .slice(0, 4)
                .map(
                  (item) =>
                    `${item.title}: ${item.error_type} / ${item.kind} / attempts ${item.attempts} - ${
                      item.error || item.summary
                    }`,
                )}
              empty="No compact quality samples."
            />
            <p className="focus-text">{modelAdaptation?.summary || "No profile adaptation proposal loaded."}</p>
            <List
              items={[
                modelAdaptation ? `status: ${modelAdaptation.status}` : "",
                modelAdaptation ? `confidence: ${modelAdaptation.confidence}` : "",
                modelAdaptation?.confirmation_required ? "confirmation required before profile changes" : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No adaptation metadata."
            />
            <List
              items={(modelAdaptation?.actions ?? [])
                .slice(0, 5)
                .map((item) => `${item.risk}: ${item.title} / ${item.target} - ${item.proposed}`)}
              empty={modelAdaptation?.no_change_reason || "No profile adaptation actions."}
            />
            <div className="panel-actions">
              <button
                type="button"
                onClick={() => reviewModelAdaptation("accepted")}
                disabled={busy || !modelAdaptation || modelAdaptation.status === "no_change"}
              >
                <Check size={16} />
                Accept
              </button>
              <button
                type="button"
                onClick={() => reviewModelAdaptation("rejected")}
                disabled={busy || !modelAdaptation || modelAdaptation.status === "no_change"}
              >
                <X size={16} />
                Reject
              </button>
            </div>
            <List
              items={modelAdaptationReviews
                .slice(0, 5)
                .map((item) => `${item.decision}: ${item.proposal.summary} (${formatLocalTimestamp(item.created_at)})`)}
              empty="No reviewed adaptation history."
            />
            <List
              items={(selected?.state.model_interactions ?? [])
                .slice(-5)
                .map(
                  (item) =>
                    `${item.kind}: ${item.ok ? "ok" : "fallback"} / attempts ${item.attempts}${
                      item.repaired ? " / repaired" : ""
                    }${item.fallback_used ? " / fallback" : ""} - ${item.summary}`,
                )}
              empty="No model interactions recorded."
            />
          </Panel>
          <Panel title="Tools" icon={<Wrench size={18} />}>
            <p className="focus-text">{selected?.state.active_tool || "No active tool."}</p>
            <List
              items={(selected?.state.tool_calls ?? []).slice(-6).map((call) => `${call.name}: ${call.summary}`)}
              empty="No tool calls yet."
            />
          </Panel>
          <Panel title="Source Evidence" icon={<Globe size={18} />}>
            <p className="focus-text">
              {sourceEvidence?.summary || "No source evidence preview yet."}
            </p>
            <List
              items={[
                sourceEvidence ? `web: ${sourceEvidence.web_source_count}` : "",
                sourceEvidence ? `browser shots: ${sourceEvidence.browser_snapshot_count}` : "",
                sourceEvidence ? `desktop shots: ${sourceEvidence.desktop_snapshot_count}` : "",
                sourceEvidence ? `criteria linked: ${sourceEvidence.linked_criterion_count}` : "",
                sourceEvidence ? `matched labels: ${sourceEvidence.matched_label_count}/${sourceEvidence.required_label_count}` : "",
                (sourceEvidence?.missing_labels ?? []).length ? `missing: ${(sourceEvidence?.missing_labels ?? []).join(", ")}` : "",
                sourceEvidence?.latest_evidence ? `latest: ${sourceEvidence.latest_evidence}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No source evidence counts."
            />
            <List
              items={(sourceEvidence?.entries ?? []).slice(0, 6).map((entry) => {
                const target = entry.url || entry.path;
                const linked = entry.linked_criteria.length ? ` criteria: ${entry.linked_criteria.slice(0, 2).join("; ")}` : "";
                return `${entry.kind}/${entry.evidence_label}: ${entry.title || target}${linked}`;
              })}
              empty="No compact source evidence entries."
            />
            <p className="muted">{sourceEvidence?.recommended_action ?? ""}</p>
          </Panel>
          <Panel title="Web Sources" icon={<Globe size={18} />}>
            {(selected?.state.web_sources ?? []).length === 0 ? (
              <p className="muted">No web sources yet.</p>
            ) : (
              <ul>
                {(selected?.state.web_sources ?? []).slice(-5).map((source) => (
                  <li key={source.id}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.title}
                    </a>
                    <p>{source.excerpt}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Desktop" icon={<Monitor size={18} />}>
            <p className="focus-text">
              {desktopEffectProof
                ? `${desktopEffectProof.status}${desktopEffectProof.proof_tool ? ` via ${desktopEffectProof.proof_tool}` : ""}`
                : "No desktop effect proof preview yet."}
            </p>
            <List
              items={[
                desktopEffectProof?.latest_action_tool
                  ? `latest action: ${desktopEffectProof.latest_action_tool} ${desktopEffectProof.latest_action_summary}`
                  : "",
                desktopEffectProof?.proof_snapshot
                  ? `proof snapshot: ${desktopEffectProof.proof_snapshot.title} ${formatLocalTimestamp(
                      desktopEffectProof.proof_snapshot.timestamp,
                    )} ${desktopEffectProof.proof_snapshot.path}`
                  : "",
                desktopEffectProof?.proof_summary
                  ? `proof result: ${desktopEffectProof.proof_tool} ${desktopEffectProof.proof_summary}`
                  : "",
                ...(desktopEffectProof?.ledger ?? []),
              ].filter((item): item is string => Boolean(item)).slice(0, 6)}
              empty="No desktop proof ledger yet."
            />
            {activeDesktopEffectProofRepairs?.total_count ? (
              <List
                items={[
                  activeDesktopEffectProofRepairs.summary,
                  ...activeDesktopEffectProofRepairs.entries.slice(0, 4).map(
                    (entry) =>
                      `repair #${entry.event_id} ${entry.outcome}: ${entry.summary || "no summary"}${
                        entry.proof_snapshot_id ? ` / snapshot ${entry.proof_snapshot_id}` : ""
                      }`,
                  ),
                ]}
                empty="No desktop proof repair outcomes."
              />
            ) : null}
            <p className="muted">{desktopEffectProof?.recommended_action ?? ""}</p>
            <List
              items={(selected?.state.desktop_snapshots ?? []).slice(-5).map((shot) => `${shot.title}: ${shot.summary}`)}
              empty="No desktop snapshots yet."
            />
          </Panel>
          <Panel title="Task Graph" icon={<ListChecks size={18} />}>
            <List
              items={(selected?.state.task_graph ?? [])
                .slice(0, 8)
                .map((task) => `${task.status} / ${task.kind}: ${task.title}`)}
              empty="No task graph yet."
            />
          </Panel>
          <Panel title="Repo Map" icon={<Map size={18} />}>
            <p className="focus-text">{selected?.state.repo_map.summary || "No repo map yet."}</p>
            <List items={selected?.state.repo_map.test_commands ?? []} empty="No known commands." />
          </Panel>
          <Panel title="Workspace Isolation" icon={<Map size={18} />}>
            <p className="focus-text">{selected?.state.workspace_isolation.summary || "No workspace isolation yet."}</p>
            <div className="panel-actions">
              <button type="button" onClick={refreshWorkspaceDiff} disabled={!selectedId || busy}>
                <GitPullRequest size={16} />
                Diff
              </button>
              <button
                type="button"
                onClick={requestWorkspacePromotion}
                disabled={
                  !selectedId ||
                  busy ||
                  (selected?.state.workspace_diff.total_files ?? 0) === 0 ||
                  Boolean(promotionAudit && promotionAudit.status !== "ready")
                }
              >
                <Check size={16} />
                Promote
              </button>
            </div>
            <List
              items={[
                selected?.state.workspace_isolation.source_path
                  ? `source: ${selected.state.workspace_isolation.source_path}`
                  : "",
                selected?.state.workspace_isolation.workspace_path
                  ? `active: ${selected.state.workspace_isolation.workspace_path}`
                  : "",
                selected?.state.workspace_isolation.copied_files
                  ? `copied files: ${selected.state.workspace_isolation.copied_files}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No workspace metadata."
            />
            <p className="focus-text">{selected?.state.workspace_diff.summary || "No workspace diff yet."}</p>
            <p className="focus-text">{promotionAudit?.summary || "No promotion audit yet."}</p>
            <List
              items={[
                promotionAudit ? `audit: ${promotionAudit.status}` : "",
                promotionAudit ? `ready: ${promotionAudit.ready_to_promote ? "yes" : "no"}` : "",
                promotionAudit ? `changed: ${promotionAudit.changed_file_count}` : "",
                promotionAudit ? `patches: ${promotionAudit.patch_proposal_count}/${promotionAudit.patch_application_count}` : "",
                promotionAudit ? `approval histories: ${promotionAudit.unresolved_approval_history_count}` : "",
                promotionAudit?.latest_verification ? `verified: ${promotionAudit.latest_verification}` : "",
                promotionAudit ? `drift: ${promotionAudit.resume_drift_status || "unknown"}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No promotion audit status."
            />
            <List
              items={(promotionAudit?.unresolved_approval_histories ?? []).slice(0, 4)}
              empty="No unresolved promotion approval histories."
            />
            <List
              items={(promotionAudit?.issues ?? [])
                .slice(0, 5)
                .map((issue) => `${issue.severity}: ${issue.summary}`)}
              empty="No promotion audit issues."
            />
            <p className="muted">{promotionAudit?.recommended_action ?? ""}</p>
            <p className="focus-text">{promotionVerification?.summary || "No promotion verification attempts yet."}</p>
            <List
              items={[
                promotionVerification ? `verification: ${promotionVerification.status}` : "",
                promotionVerification ? `attempts: ${promotionVerification.attempt_count}` : "",
                promotionVerification ? `failed: ${promotionVerification.failed_count}` : "",
                promotionVerification ? `hints: ${promotionVerification.repair_hint_count}` : "",
                promotionVerification?.latest_failure_kind ? `failure: ${promotionVerification.latest_failure_kind}` : "",
                promotionVerification?.latest_suspected_file ? `file: ${promotionVerification.latest_suspected_file}` : "",
                promotionVerification?.next_command ? `next: ${promotionVerification.next_command}` : "",
                promotionVerification?.should_use_alternate ? "alternate diagnostic selected" : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No promotion verification status."
            />
            <List
              items={[
                selected?.state.promotion_repair?.phase
                  ? `repair phase: ${selected.state.promotion_repair.phase}`
                  : "",
                selected?.state.promotion_repair?.target_file
                  ? `target: ${selected.state.promotion_repair.target_file}${
                      selected.state.promotion_repair.target_line ? `:${selected.state.promotion_repair.target_line}` : ""
                    }`
                  : "",
                selected?.state.promotion_repair?.next_tool
                  ? `next tool: ${selected.state.promotion_repair.next_tool}`
                  : "",
                selected?.state.promotion_repair?.patch_proposal_id
                  ? `patch: ${selected.state.promotion_repair.patch_status || "pending"} ${selected.state.promotion_repair.patch_proposal_id}`
                  : "",
                selected?.state.promotion_repair?.next_action
                  ? selected.state.promotion_repair.next_action
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No active promotion repair phase."
            />
            <List
              items={(promotionVerification?.attempts ?? [])
                .slice(-4)
                .map((attempt) => {
                  const target = attempt.suspected_file
                    ? `${attempt.suspected_file}${attempt.suspected_line ? `:${attempt.suspected_line}` : ""}`
                    : "";
                  return `${attempt.ok ? "ok" : "failed"}: ${attempt.command}${
                    attempt.selected_alternate ? " / alternate" : ""
                  }${attempt.failure_kind ? ` / ${attempt.failure_kind}` : ""}${target ? ` / ${target}` : ""}${
                    attempt.repair_hint ? ` - ${attempt.repair_hint}` : ""
                  }`;
                })}
              empty="No promotion verification attempts."
            />
            <List
              items={(selected?.state.workspace_diff.files ?? [])
                .slice(0, 6)
                .map((file) => `${file.status}: ${file.path}${file.truncated ? " (truncated)" : ""}`)}
              empty="No changed files."
            />
            <List
              items={(selected?.state.workspace_promotions ?? [])
                .slice(-3)
                .map((promotion) => `${promotion.status}: ${promotion.summary}`)}
              empty="No workspace promotions."
            />
          </Panel>
          <Panel title="Patch Proposals" icon={<GitPullRequest size={18} />}>
            {patchApprovalCards.length === 0 ? (
              <p>No patch proposals yet.</p>
            ) : (
              <div className="queue-list">
                {patchApprovalCards.map((card) => (
                  <div className="queue-item" key={card.patch.id}>
                    <div>
                      <strong>{card.patch.title}</strong>
                      <span>{card.statusText}</span>
                      <small>{formatLocalTextTimestamps(card.meta)}</small>
                    </div>
                    <button
                      type="button"
                      onClick={() => requestPatchApprovalFromCard(card)}
                      disabled={!card.canRequestApply || busy}
                      title={card.disabledReason || card.buttonLabel}
                      aria-label={`${card.buttonLabel}: ${card.patch.title}`}
                    >
                      <Check size={14} />
                      {card.buttonLabel}
                    </button>
                  </div>
                ))}
              </div>
            )}
            <List
              items={(selected?.state.patch_applications ?? [])
                .slice(-5)
                .map((patch) => `${patch.status}: ${patch.summary}`)}
              empty="No patch applications yet."
            />
          </Panel>
          <Panel title="Failures" icon={<AlertTriangle size={18} />}>
            <List
              items={(selected?.state.failure_records ?? [])
                .slice(-5)
                .map((failure) => {
                  const detail = [
                    failure.command ? `cmd ${failure.command}` : "",
                    failure.target ? `target ${failure.target}` : "",
                    failure.returncode !== null ? `rc ${failure.returncode}` : "",
                  ]
                    .filter(Boolean)
                    .join(" / ");
                  return `${failure.kind}/${failure.tool} x${failure.count}${detail ? ` (${detail})` : ""}: ${failure.recovery_hint}${
                    failure.evidence_excerpt ? ` - ${failure.evidence_excerpt}` : ""
                  }`;
                })}
              empty="No classified failures."
            />
          </Panel>
          <Panel title="Recovery" icon={<RotateCcw size={18} />}>
            <p className="focus-text">
              {selected?.state.recovery_plan.status === "active"
                ? selected.state.recovery_plan.summary
                : "No active recovery plan."}
            </p>
            <div className="panel-actions">
              <button
                type="button"
                onClick={() => recoveryAction("resume")}
                disabled={!selectedId || busy || selected?.state.recovery_plan.status !== "active"}
              >
                <Play size={16} />
                Resume
              </button>
              <button
                type="button"
                onClick={() => recoveryAction("replan")}
                disabled={!selectedId || busy || selected?.state.recovery_plan.status !== "active"}
              >
                <RotateCcw size={16} />
                Replan
              </button>
            </div>
            <List items={selected?.state.recovery_plan.steps ?? []} empty="No recovery steps." />
            <p className="focus-text">
              {recoveryDecisions?.summary || "No recovery decision report yet."}
            </p>
            <List
              items={[
                recoveryDecisions ? `decisions: ${recoveryDecisions.decision_count}` : "",
                recoveryDecisions ? `readiness recoveries: ${recoveryDecisions.readiness_recovery_count}` : "",
                recoveryDecisions ? `resolved: ${recoveryDecisions.resolved_count}` : "",
                recoveryDecisions ? `unresolved: ${recoveryDecisions.unresolved_count}` : "",
                recoveryDecisions?.active_decision?.id
                  ? `active: ${recoveryDecisions.active_decision.tool} ${recoveryDecisions.active_decision.proof_label}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No recovery decision counts."
            />
            <p className="muted">{recoveryDecisions?.recommended_action ?? ""}</p>
            <List
              items={(recoveryDecisions?.decisions ?? [])
                .slice(-4)
                .map(
                  (item) =>
                    `${item.status} ${item.trigger}: ${item.tool}${
                      item.proof_label ? ` (${item.proof_label})` : ""
                    } - ${item.selected_strategy || item.summary}`,
                )}
              empty="No recovery decisions."
            />
            <p className="focus-text">
              {selected?.state.post_action_retries?.summary || "No post-action retry lane activity."}
            </p>
            <List
              items={[
                selected?.state.post_action_retries
                  ? `Post-action retries: ${selected.state.post_action_retries.decision_count}`
                  : "",
                selected?.state.post_action_retries
                  ? `pending: ${selected.state.post_action_retries.pending_count}`
                  : "",
                selected?.state.post_action_retries
                  ? `resolved: ${selected.state.post_action_retries.resolved_count}`
                  : "",
                selected?.state.post_action_retries
                  ? `failed: ${selected.state.post_action_retries.failed_count}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No post-action retry counts."
            />
            <List
              items={(selected?.state.post_action_retries?.decisions ?? [])
                .slice(-4)
                .map(
                  (decision) =>
                    `${decision.status}: ${decision.trigger_tool} -> ${decision.selected_tool} - ${decision.selected_action}`,
                )}
              empty="No post-action retry decisions."
            />            <p className="focus-text">
              {verificationOutcomes?.summary || "No verification outcome ledger yet."}
            </p>
            <List
              items={[
                verificationOutcomes ? `outcomes: ${verificationOutcomes.outcome_count}` : "",
                verificationOutcomes ? `verified: ${verificationOutcomes.verified_count}` : "",
                verificationOutcomes ? `failed: ${verificationOutcomes.failed_count}` : "",
                verificationOutcomes ? `recovery closed: ${verificationOutcomes.recovery_resolved_count}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No verification outcome counts."
            />
            <List
              items={(verificationOutcomes?.outcomes ?? [])
                .slice(-4)
                .map(
                  (item) =>
                    `${item.outcome} ${item.tool}${
                      item.proof_label ? ` (${item.proof_label})` : ""
                    }${item.recovery_id ? ` / ${item.recovery_id}` : ""}: ${item.summary}`,
                )}
              empty="No verification outcomes."
            />
            <List
              items={(selected?.state.recovery_history ?? [])
                .slice(-3)
                .map((plan) => `${plan.status}: ${plan.summary}`)}
              empty="No recovery history."
            />
          </Panel>
        </div>

        <section className={activeView === "activity" ? "handoff" : "handoff view-hidden"}>
          <h2>
            <Target size={18} />
            Goal And Handoff
          </h2>
          <div className="goal-box">
            <strong>Original</strong>
            <p>{selected?.goal ?? "No run selected."}</p>
            <strong>Active</strong>
            <p>{selected?.state.goal ?? "No active goal."}</p>
            {selected?.state.proposed_goal && (
              <>
                <strong>Proposed</strong>
                <p>{selected.state.proposed_goal}</p>
              </>
            )}
          </div>
          <div className="goal-box">
            <strong>Goal Evolution</strong>
            <p>{selected?.state.goal_evolution?.summary || "No goal evolution reviews recorded."}</p>
            {selected?.state.goal_evolution?.pending_count ? (
              <p className="muted">Pending /goal confirmation: accept or reject the proposed goal before resuming.</p>
            ) : null}
            <List
              items={
                selected?.state.goal_evolution
                  ? [
                      `reviews: ${selected.state.goal_evolution.decision_count}`,
                      `pending: ${selected.state.goal_evolution.pending_count}`,
                      `accepted: ${selected.state.goal_evolution.accepted_count}`,
                      `rejected: ${selected.state.goal_evolution.rejected_count}`,
                      `unchanged: ${selected.state.goal_evolution.unchanged_count}`,
                    ]
                  : []
              }
              empty="No goal evolution counts."
            />
            <List
              items={(selected?.state.goal_evolution?.decisions ?? [])
                .slice(-5)
                .map(
                  (item) =>
                    `${item.status}: ${item.source}${item.proposed_goal ? ` -> ${item.proposed_goal}` : ""} - ${
                      item.reason || item.material_change
                    }`,
                )}
              empty="No goal evolution decisions."
            />
          </div>
          <div className="goal-box">
            <strong>Git Checkpoint</strong>
            <p>{selected?.state.git_checkpoint?.summary || "No Git checkpoint report recorded."}</p>
            <List
              items={
                selected?.state.git_checkpoint
                  ? [
                      `status: ${selected.state.git_checkpoint.status}`,
                      `changed: ${selected.state.git_checkpoint.changed_count}`,
                      `ahead: ${selected.state.git_checkpoint.ahead_count}`,
                      `remotes: ${selected.state.git_checkpoint.remote_count}`,
                      `github: ${selected.state.git_checkpoint.github_remote_count}`,
                    ]
                  : []
              }
              empty="No Git checkpoint counts."
            />
            <List
              items={
                selected?.state.git_checkpoint
                  ? [
                      selected.state.git_checkpoint.recommended_action,
                      selected.state.git_checkpoint.recent_verification
                        ? `verified: ${selected.state.git_checkpoint.recent_verification}`
                        : "verification: none recorded",
                      selected.state.git_checkpoint.last_commit
                        ? `last: ${selected.state.git_checkpoint.last_commit}`
                        : "last: none",
                    ]
                  : []
              }
              empty="No Git checkpoint recommendation."
            />
          </div>
          <form className="goal-form" onSubmit={proposeGoal}>
            <textarea
              value={goalProposal}
              onChange={(event) => setGoalProposal(event.target.value)}
              placeholder="Refine /goal for this run"
            />
            <button type="submit" disabled={!selectedId}>
              <Target size={16} />
              /goal
            </button>
            <button type="button" onClick={reviewGoal} disabled={!selectedId || busy}>
              <Brain size={16} />
              Review
            </button>
          </form>
          <List
            items={(selected?.state.handoff_summary.approval_reviews ?? []).map(
              (item) =>
                `${item.action_kind}#${item.id}: ${item.reviewed ? `reviewed x${item.review_count}` : "unreviewed"}${
                  item.high_risk ? " / high risk" : ""
                } - ${item.summary}`,
            )}
            empty="No pending approval review summaries in handoff."
          />
          <List
            items={(selected?.state.handoff_summary.model_profile_adaptation_reviews ?? [])
              .slice(0, 5)
              .map(
                (item) =>
                  `${item.decision}: ${item.proposal_summary}${
                    item.reviewer_note ? ` - ${item.reviewer_note}` : ""
                  }`,
              )}
            empty="No Ornith profile review decisions in handoff."
          />
          <div className="goal-box">
            <strong>Restart Evidence</strong>
            <p>
              {handoffActionContext?.selected_tool
                ? `${handoffActionContext.selected_tool}:${handoffActionContext.selected_label || "none"}`
                : "No packed handoff action context."}
            </p>
            <List
              items={[
                handoffActionContext?.selected_action ? `next: ${handoffActionContext.selected_action}` : "",
                handoffActionContext?.task_transition_ledger?.length
                  ? `task transitions: ${handoffActionContext.task_transition_ledger.join("; ")}`
                  : "",
                handoffActionContext?.model_guard_ledger?.length
                  ? `model guards: ${handoffActionContext.model_guard_ledger.join("; ")}`
                  : "",
                handoffActionContext?.edit_evidence_ledger?.length
                  ? `edit evidence: ${handoffActionContext.edit_evidence_ledger.join("; ")}`
                  : "",
                handoffActionContext?.desktop_supervision_ledger?.length
                  ? `desktop supervision: ${handoffActionContext.desktop_supervision_ledger.join("; ")}`
                  : "",
                handoffActionContext?.failure_ledger?.length
                  ? `open failures: ${handoffActionContext.failure_ledger.join("; ")}`
                  : "",
                handoffActionContext?.resolved_failure_ledger?.length
                  ? `resolved failures: ${handoffActionContext.resolved_failure_ledger.join("; ")}`
                  : "",
                handoffActionContext?.context_budget ? `context: ${handoffActionContext.context_budget}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No restart evidence packed into the handoff."
            />
          </div>
          <div className="goal-box">
            <strong>Readiness Proof History</strong>
            <p>{readinessProofHistory?.summary || "No readiness proof history in the handoff."}</p>
            <List
              items={[
                readinessProofHistory ? `status: ${readinessProofHistory.status}` : "",
                readinessProofHistory ? `self-scaffold: ${readinessProofHistory.self_scaffold_review_count}` : "",
                readinessProofHistory ? `post-review handoff: ${readinessProofHistory.post_review_handoff_count}` : "",
                readinessProofHistory ? `resume prompt: ${readinessProofHistory.resume_prompt_preservation_count}` : "",
                readinessProofHistory?.source_evidence_ref_count ? `source refs: ${readinessProofHistory.source_evidence_ref_count}` : "",
                readinessProofHistory?.latest_summary ? `latest: ${readinessProofHistory.latest_summary}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No compact readiness proof counts."
            />
          </div>
          <div className="goal-box">
            <strong>Preflight Warning History</strong>
            <p>{preflightWarnings?.summary || "No preflight warning history in the handoff."}</p>
            <List
              items={[
                preflightWarnings ? `warnings: ${preflightWarnings.warning_count}` : "",
                preflightWarnings ? `blocks: ${preflightWarnings.block_count}` : "",
                preflightWarnings ? `action-context reorients: ${preflightWarnings.action_context_reorient_count}` : "",
                preflightWarnings?.latest_warning ? `latest: ${preflightWarnings.latest_warning}` : "",
                preflightWarningGate
                  ? `readiness completion gate: ${preflightWarningGate.status} (${readinessCompletion?.can_claim_milestone ? "claim allowed" : "claim held"})`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No compact preflight warning counts."
            />
          </div>
          <List
            items={(selected?.state.acceptance_evidence ?? []).map(
              (item) => {
                const labelProgress = item.required_labels
                  .map((label) => `${label}=${item.matched_labels.includes(label) ? "ok" : "open"}`)
                  .join(", ");
                return `${item.status}: ${item.criterion}${
                  labelProgress ? ` [${labelProgress}]` : ""
                }${
                  item.evidence.length ? ` - ${item.evidence[item.evidence.length - 1]}` : ""
                }`;
              },
            )}
            empty="No acceptance evidence tracked."
          />
          <List
            items={(selected?.state.acceptance_recommendations ?? []).map(
              (item) =>
                `${item.available ? "next" : "blocked"}: ${item.label} via ${item.tool_kind} - ${item.action}${
                  item.command_hint ? ` (${item.command_hint})` : ""
                }`,
            )}
            empty="No acceptance recommendations."
          />
          <List
            items={(selected?.state.acceptance_recommendation_traces ?? []).map(
              (item) =>
                `${item.status}: ${item.label} ${item.recommended_tool} -> ${item.selected_tool}${
                  item.result_summary ? ` - ${item.result_summary}` : ""
                }`,
            )}
            empty="No recommendation trace yet."
          />
          <List
            items={[
              completionAudit
                ? `completion: ${completionAudit.status} / ${completionAudit.acceptance_verified}/${completionAudit.acceptance_total} criteria verified`
                : "",
              completionAudit ? `pending approvals: ${completionAudit.pending_approvals}` : "",
              completionAudit ? `blockers: ${completionAudit.blocker_count}` : "",
              completionAudit ? `stale evidence: ${completionAudit.stale_evidence_count}` : "",
            ].filter((item): item is string => Boolean(item))}
            empty="No completion audit loaded."
          />
          <List
            items={[
              completionPolicy
                ? `strict stale evidence: ${completionPolicy.strict_stale_evidence ? "on" : "off"}`
                : "",
              completionPolicy ? `stale edit tools: ${completionPolicy.stale_edit_tools.join(", ")}` : "",
              completionPolicy ? `verification tools: ${completionPolicy.verification_tools.join(", ")}` : "",
              completionPolicy ? `checkpoint tools: ${completionPolicy.checkpoint_tools.join(", ")}` : "",
              completionPolicy
                ? `evidence labels: ${Object.keys(completionPolicy.evidence_labels).join(", ")}`
                : "",
              completionPolicy
                ? `web/browser tools: ${[
                    ...completionPolicy.web_tools,
                    ...completionPolicy.browser_tools,
                  ].join(", ")}`
                : "",
            ].filter((item): item is string => Boolean(item))}
            empty="No completion policy loaded."
          />
          <List
            items={(completionAudit?.issues ?? [])
              .slice(0, 6)
              .map((item) => `${item.severity}: ${item.summary}`)}
            empty="No completion audit issues."
          />
          <pre>{formatLocalTextTimestamps(selected?.state.handoff_summary.resume_prompt || "No handoff yet.")}</pre>
          <p className="focus-text">
            {selected?.state.context_snapshot?.generated_at
              ? `Context coverage ${selected.state.context_snapshot.coverage_status}: ${selected.state.context_snapshot.selected_section_count} selected, ${selected.state.context_snapshot.dropped_section_count} dropped.`
              : "No context coverage report yet."}
          </p>
          <List
            items={[
              selected?.state.context_snapshot?.required_sections_missing?.length
                ? `required missing: ${selected.state.context_snapshot.required_sections_missing.join(", ")}`
                : "required missing: none",
              selected?.state.context_snapshot?.dropped_sections?.length
                ? `dropped: ${selected.state.context_snapshot.dropped_sections.slice(0, 10).join(", ")}`
                : "dropped: none",
              selected?.state.context_snapshot?.recommended_action || "",
            ].filter((item): item is string => Boolean(item))}
            empty="No context coverage details."
          />
          <pre>{formatLocalTextTimestamps(selected?.state.context_snapshot.prompt_preview || "No compiled context yet.")}</pre>
        </section>

        <section className={activeView === "activity" ? "approval-band" : "approval-band view-hidden"}>
          <h2>Approvals</h2>
          <p className="muted">
            pending {pendingApprovals.length} / unreviewed {unreviewedPendingApprovals.length} / reviewed {reviewedPendingApprovals.length}
          </p>
          {goalConfirmationGate.needsConfirmation ? (
            <div className="queue-item blocked">
              <div>
                <strong>Goal Confirmation</strong>
                <p>{formatLocalTextTimestamps(goalConfirmationGate.action)}</p>
                <small>{formatLocalTextTimestamps(goalConfirmationGate.meta)}</small>
              </div>
            </div>
          ) : null}
          {desktopApprovalGate.needsApproval ? (
            <div className="queue-item blocked">
              <div>
                <strong>Desktop Approval</strong>
                <p>{formatLocalTextTimestamps(desktopApprovalGate.action)}</p>
                <small>{formatLocalTextTimestamps(desktopApprovalGate.meta)}</small>
              </div>
            </div>
          ) : null}
          {sourcePromotionApprovalGate.needsApproval ? (
            <div className="queue-item blocked">
              <div>
                <strong>Source Promotion Approval</strong>
                <p>{formatLocalTextTimestamps(sourcePromotionApprovalGate.action)}</p>
                <small>{formatLocalTextTimestamps(sourcePromotionApprovalGate.meta)}</small>
              </div>
            </div>
          ) : null}
          {pendingApprovals.length === 0 ? (
            <p>No pending approvals.</p>
          ) : (
            orderedPendingApprovals.map((approval) => {
              const approveLabel = approvalDecisionLabel(approval, "approve");
              const rejectLabel = approvalDecisionLabel(approval, "reject");
              return (
                <div className="approval" key={approval.id}>
                  <div>
                    <strong>{approval.action_kind}</strong>
                    <span>{approval.reason}</span>
                    <ApprovalPreview approval={approval} />
                  </div>
                  <button
                    type="button"
                    onClick={() => resolveApproval(approval.id, "approve")}
                    title={approveLabel}
                    aria-label={approveLabel}
                  >
                    <Check size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={() => resolveApproval(approval.id, "reject")}
                    title={rejectLabel}
                    aria-label={rejectLabel}
                  >
                    <X size={16} />
                  </button>
                </div>
              );
            })
          )}
        </section>
      </section>

      <aside className="rightbar">
        <section className="conversation steer">
          <h2>
            <Brain size={18} />
            Conversation
          </h2>
          <div className="conversation-toolbar">
            <span className={`run-status ${selected?.status ?? "idle"}`}>{selected?.status ?? "no chat"}</span>
            <span>{selected?.state.milestone ?? "idle"}</span>
            <button type="button" onClick={() => control("resume")} disabled={!selectedId || busy || !canResumeRun(selected)}>
              <Play size={14} />
              Resume Chat
            </button>
          </div>
          <div className="conversation-thread">
            {activeConversation.length === 0 ? (
              <p className="muted">Select an older chat or start a new run.</p>
            ) : (
              activeConversation.map((message) => (
                <article className={`chat-message ${message.role}`} key={message.id}>
                  <div>
                    <strong>{message.title}</strong>
                    <span>{message.role}</span>
                  </div>
                  <p>{formatLocalTextTimestamps(message.body)}</p>
                  {message.timestamp ? <small title={message.timestamp}>{formatLocalTimestamp(message.timestamp)}</small> : null}
                </article>
              ))
            )}
          </div>
          <form onSubmit={sendSteering}>
            <textarea
              value={steer}
              onChange={(event) => setSteer(event.target.value)}
              placeholder="Send a follow-up to this persistent Ornith chat..."
            />
            <button type="submit" disabled={!selectedId}>
              <Send size={16} />
              Send
            </button>
          </form>
        </section>

        <section className="artifacts">
          <h2>
            <FileText size={18} />
            Artifacts
          </h2>
          <div className="artifact-list">
            {artifactItems.length === 0 ? (
              <p className="muted">No artifacts attached to this chat yet.</p>
            ) : (
              artifactItems.slice(0, 28).map((artifact) => (
                <article className="artifact-item" key={artifact.id}>
                  <div>
                    <span className="artifact-kind">{artifact.kind}</span>
                    {artifact.href ? (
                      <a href={artifact.href} target="_blank" rel="noreferrer">
                        {artifact.title}
                      </a>
                    ) : (
                      <strong>{artifact.title}</strong>
                    )}
                  </div>
                  <p>{formatLocalTextTimestamps(artifact.summary)}</p>
                  {artifact.path ? <code>{artifact.path}</code> : null}
                  {artifact.timestamp ? (
                    <small title={artifact.timestamp}>{formatLocalTimestamp(artifact.timestamp)}</small>
                  ) : null}
                </article>
              ))
            )}
          </div>
        </section>

        <section className="log">
          <h2>
            <Terminal size={18} />
            Terminal
          </h2>
          <div className="event-list">
            {events.map((event) => (
              <article key={event.id}>
                <span>{event.kind}</span>
                <p>{formatLocalTextTimestamps(event.message)}</p>
                <small title={event.timestamp}>{formatLocalTimestamp(event.timestamp)}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="replay">
          <h2>
            <Share size={18} />
            Replay
          </h2>
          {replay ? (
            <>
              <div className="replay-stats">
                <span>{replay.event_count} events</span>
                <span>{replay.approval_count} approvals</span>
                <span>{replay.context_pressure}</span>
                <span>{checkpointQualityResumeBadge(replay.checkpoint_quality_resumes)}</span>
              </div>
              <a href={`${API_BASE}/api/runs/${replay.run_id}/replay.md`} target="_blank" rel="noreferrer">
                Markdown export
              </a>
              <List
                items={replay.approvals.slice(0, 4).map((approval) => {
                  const reviewState = approval.reviewed ? `reviewed x${approval.review_count}` : "unreviewed";
                  return `${approval.status}: ${approval.action_kind} (${reviewState})`;
                })}
                empty="No approvals recorded."
              />
              <pre>{formatLocalTextTimestamps(replay.markdown.slice(0, 2200))}</pre>
            </>
          ) : (
            <p className="muted">No replay bundle yet.</p>
          )}
        </section>

        <section className="notes">
          <h2>
            <FileText size={18} />
            Obsidian
          </h2>
          <pre>{formatLocalTextTimestamps(notes || "No run note yet.")}</pre>
        </section>
      </aside>
    </main>
  );
}

function ApprovalPreview({ approval }: { approval: ApprovalReviewRecord }) {
  const preview = recordValue(approval.preview);
  const files = arrayValue(preview?.files)
    .map(recordValue)
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .slice(0, 8);
  const fields = arrayValue(preview?.fields)
    .map(recordValue)
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .slice(0, 8);
  const diffExcerpt = stringValue(preview?.diff_excerpt);
  const hasFileDiff = files.some((file) => Boolean(stringValue(file.diff_excerpt)));

  return (
    <div className="approval-preview">
      <p>{formatLocalTextTimestamps(approval.summary || stringValue(preview?.summary) || "Review compact approval preview.")}</p>
      {approval.high_risk && <small>high risk approval</small>}
      <small>
        {approval.reviewed
          ? `reviewed ${approval.review_count} time${approval.review_count === 1 ? "" : "s"}${
              approval.latest_reviewed_at ? ` at ${formatLocalTimestamp(approval.latest_reviewed_at)}` : ""
            }`
          : "not reviewed yet"}
      </small>
      {fields.length > 0 && (
        <ul>
          {fields.map((field) => (
            <li key={stringValue(field.label) || stringValue(field.value)}>
              <strong>{stringValue(field.label) || "field"}</strong>
              <span>{formatLocalTextTimestamps(stringValue(field.value) || "present")}</span>
            </li>
          ))}
        </ul>
      )}
      {files.length > 0 ? (
        <ul>
          {files.map((file, index) => (
            <li key={`${stringValue(file.status)}-${stringValue(file.path)}-${index}`}>
              <strong>{stringValue(file.status) || "change"}</strong>
              <span>{stringValue(file.path) || "unknown path"}</span>
              {stringValue(file.diff_excerpt) && <pre>{stringValue(file.diff_excerpt)}</pre>}
            </li>
          ))}
        </ul>
      ) : approval.files.length > 0 ? (
        <ul>
          {approval.files.slice(0, 8).map((file) => (
            <li key={file}>
              <strong>file</strong>
              <span>{file}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {diffExcerpt && !hasFileDiff && <pre>{diffExcerpt}</pre>}
      {approval.payload_keys.length > 0 && <small>payload keys: {approval.payload_keys.join(", ")}</small>}
    </div>
  );
}

function formatApprovalHistory(history: OperatorApprovalHistory, label: string) {
  const kind = history.approval_kind ? ` (${history.approval_kind})` : "";
  const summary = history.action_summary ? ` | ${history.action_summary}` : "";
  const sequence = history.sequence.length ? ` | ${history.sequence.join(" -> ")}` : "";
  return `${label} ${history.approval_id}${kind}: ${history.latest_status} #${history.latest_event_id} | reviewed ${history.reviewed_count}, confirm ${history.confirmation_required_count}, dispatched ${history.dispatched_count}, blocked ${history.blocked_count}${summary}${sequence}`;
}
function supervisorRunSummary(item: SupervisorReport["runs"][number]): string {
  const suggested = item.action_readiness_suggested_tool
    ? ` ${item.action_readiness_suggested_tool}:${item.action_readiness_suggested_label || "none"}`
    : "";
  const actionGate = `${item.action_readiness_status}${item.action_readiness_ready ? "" : "/held"}${suggested}`;
  const nextAction =
    item.operator_attention_action ||
    item.goal_confirmation_action ||
    item.action_readiness_action ||
    (item.checkpoint_quality_requires_attention ? item.checkpoint_quality_action : "") ||
    (item.promotion_audit_requires_attention ? item.promotion_audit_action : "") ||
    (item.self_scaffold_requires_attention ? item.self_scaffold_action : "") ||
    (item.self_scaffold_rollback_requires_attention ? item.self_scaffold_rollback_action : "") ||
    (item.readiness_proof_history_requires_attention ? item.readiness_proof_history_action : "") ||
    (item.readiness_smoke_requires_attention ? item.readiness_smoke_action : "") ||
    (item.operator_dispatch_restart_smoke_requires_attention ? item.operator_dispatch_restart_smoke_action : "") ||
    item.objective_readiness_action ||
    item.auto_resume_reason;
  return `${item.action}: ${item.title} (priority ${item.supervisor_priority}, ${item.previous_status} -> ${item.status}, attention ${item.operator_attention_severity}/${item.operator_attention_reasons.join(",") || "none"}, goal ${item.goal_confirmation_requires_attention ? "pending" : "ok"}, action ${actionGate}, progress ${item.run_progress.status}, readiness ${item.objective_readiness.status}, smoke ${item.readiness_smoke_status}/${item.readiness_smoke_proof_status}, proof ${item.readiness_proof_history_status}, source refs ${item.readiness_source_ref_preview_status}, dispatch smoke ${item.operator_dispatch_restart_smoke_status}, checkpoint ${item.checkpoint_quality_requires_attention ? item.checkpoint_quality.status : "ok"}, source ${item.source_evidence_requires_attention ? "missing" : "ok"}, promotion ${item.promotion_audit_requires_attention ? item.promotion_audit.status : "ok"}, scaffold ${item.self_scaffold_requires_attention ? item.self_scaffold_status : "ok"} / rollback ${item.self_scaffold_rollback_requires_attention ? item.self_scaffold_rollback_intents.status : "ok"}, health ${item.run_health.level}/${item.run_health.recommended_action}, policy ${item.policy_simulation.policy_action}) ${nextAction}`;
}
function Panel({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      <h2>
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function selectCheckpointQualityResumes(
  stateReport?: CheckpointQualityResumeReport,
  handoffReport?: CheckpointQualityResumeReport,
  replayReport?: CheckpointQualityResumeReport,
): CheckpointQualityResumeReport | null {
  if (stateReport?.run_id) return stateReport;
  if (handoffReport?.run_id) return handoffReport;
  if (replayReport?.run_id) return replayReport;
  return null;
}

function checkpointQualityResumeLines(report: CheckpointQualityResumeReport | null): string[] {
  if (!report) return [];
  const latest = report.latest;
  const repair = latest.repair_completed_event_id
    ? `repair #${latest.repair_completed_event_id}: ${latest.repair_reason || "unknown"} -> ${
        latest.repair_ui_target || "unknown"
      }`
    : "repair: none";
  const resume = latest.resume_event_id
    ? `resume #${latest.resume_event_id}: ${latest.resume_policy_action || "unknown"} ${
        latest.resume_accepted === null ? "unknown" : latest.resume_accepted ? "accepted" : "blocked"
      }`
    : "resume: awaiting";
  return [
    `resume repair: ${report.status}`,
    `repair counts: ${report.repair_count} total, ${report.resumed_after_repair_count} resumed, ${
      report.blocked_after_repair_count
    } blocked, ${report.awaiting_resume_count} awaiting`,
    repair,
    resume,
    latest.checkpoint_quality_status
      ? `checkpoint after repair: ${latest.checkpoint_quality_status} / ${
          latest.checkpoint_quality_ready ? "ready" : "not ready"
        }`
      : "",
  ];
}

function checkpointQualityResumeBadge(report: CheckpointQualityResumeReport): string {
  if (!report.run_id || report.status === "none") return "checkpoint repairs none";
  return `checkpoint repair ${report.status} (${report.repair_count})`;
}
function List({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul>
      {items.slice(-8).map((item, index) => (
        <li key={`${item}-${index}`}>{formatLocalTextTimestamps(item)}</li>
      ))}
    </ul>
  );
}

function Numbered({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ol>
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{formatLocalTextTimestamps(item)}</li>
      ))}
    </ol>
  );
}
