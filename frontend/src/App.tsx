import { FormEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  Brain,
  Check,
  FileText,
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
  ApprovalRecord,
  AutonomyDecisionReport,
  CompletionAuditReport,
  CompletionVerificationPolicy,
  EventRecord,
  ModelEvalSummary,
  ModelProfileAdaptationProposal,
  ModelProfileAdaptationReview,
  ModelProfile,
  ModelPromptQualityReport,
  ObjectiveReadinessReport,
  OperatorActionDispatchResult,
  OperatorActionQueueItem,
  OperatorActionQueueReport,
  OrnithLaunchChecklistReport,
  OrnithPreflightActionLedgerReport,
  OperatorDispatchLedgerReport,
  OperatorDispatchRestartSmokeLedgerReport,
  OperatorDispatchRestartSmokeReport,
  PolicySimulationReport,
  ReadinessCompletionReport,
  ReadinessRehearsalLedgerReport,
  ReadinessRehearsalReport,
  RecoveryDecisionReport,
  ReplayBundle,
  ReportIntegrityReport,
  ResumeDecisionReport,
  RunRecord,
  RunHealthReport,
  RunProgressReport,
  SourceEvidencePreviewReport,
  SupervisorReport,
  VerificationOutcomeReport,
  api,
} from "./api";

const emptyGoal =
  "Inspect this workspace, check Obsidian first, make a small safe improvement, run checks, and summarize.";

export function App() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [selected, setSelected] = useState<RunRecord | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [replay, setReplay] = useState<ReplayBundle | null>(null);
  const [completionAudit, setCompletionAudit] = useState<CompletionAuditReport | null>(null);
  const [runProgress, setRunProgress] = useState<RunProgressReport | null>(null);
  const [reportIntegrity, setReportIntegrity] = useState<ReportIntegrityReport | null>(null);
  const [objectiveReadiness, setObjectiveReadiness] = useState<ObjectiveReadinessReport | null>(null);
  const [readinessCompletion, setReadinessCompletion] = useState<ReadinessCompletionReport | null>(null);
  const [readinessRehearsal, setReadinessRehearsal] = useState<ReadinessRehearsalReport | null>(null);
  const [readinessRehearsalLedger, setReadinessRehearsalLedger] =
    useState<ReadinessRehearsalLedgerReport | null>(null);
  const [policySimulation, setPolicySimulation] = useState<PolicySimulationReport | null>(null);
  const [resumeDecisions, setResumeDecisions] = useState<ResumeDecisionReport | null>(null);
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
  const [supervisor, setSupervisor] = useState<SupervisorReport | null>(null);
  const [operatorActionQueue, setOperatorActionQueue] = useState<OperatorActionQueueReport | null>(null);
  const [operatorDispatches, setOperatorDispatches] = useState<OperatorDispatchLedgerReport | null>(null);
  const [operatorDispatchRestartSmoke, setOperatorDispatchRestartSmoke] =
    useState<OperatorDispatchRestartSmokeReport | null>(null);
  const [operatorDispatchRestartSmokeLedger, setOperatorDispatchRestartSmokeLedger] =
    useState<OperatorDispatchRestartSmokeLedgerReport | null>(null);
  const [operatorDispatchMessage, setOperatorDispatchMessage] = useState("");
  const [dispatchSmokeBusy, setDispatchSmokeBusy] = useState(false);
  const [modelProfile, setModelProfile] = useState<ModelProfile | null>(null);
  const [modelEval, setModelEval] = useState<ModelEvalSummary | null>(null);
  const [modelQuality, setModelQuality] = useState<ModelPromptQualityReport | null>(null);
  const [modelAdaptation, setModelAdaptation] = useState<ModelProfileAdaptationProposal | null>(null);
  const [modelAdaptationReviews, setModelAdaptationReviews] = useState<ModelProfileAdaptationReview[]>([]);
  const [notes, setNotes] = useState("");
  const [goal, setGoal] = useState(emptyGoal);
  const [criteria, setCriteria] = useState("Dashboard starts locally\nObsidian checkpoint is written");
  const [webEnabled, setWebEnabled] = useState(true);
  const [browserEnabled, setBrowserEnabled] = useState(true);
  const [desktopEnabled, setDesktopEnabled] = useState(true);
  const [goalProposal, setGoalProposal] = useState("");
  const [steer, setSteer] = useState("");
  const [busy, setBusy] = useState(false);
  const [rehearsalBusy, setRehearsalBusy] = useState(false);
  const [showAttentionOnly, setShowAttentionOnly] = useState(false);
  const [error, setError] = useState("");

  const pendingApprovals = approvals.filter((approval) => approval.status === "pending");
  const activeOrnithPreflight = selectedOrnithPreflight ?? ornithPreflight;
  const progress = useMemo(() => {
    const state = selected?.state;
    if (!state || state.current_plan.length === 0) return 0;
    return Math.min(100, Math.round((state.completed_steps.length / state.current_plan.length) * 100));
  }, [selected]);
  const supervisorRunById = useMemo(() => {
    return new globalThis.Map((supervisor?.runs ?? []).map((run) => [run.run_id, run]));
  }, [supervisor]);
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

  async function refreshRuns(nextSelectedId?: string) {
    const list = await api<RunRecord[]>("/api/runs");
    setRuns(list);
    const id = nextSelectedId || selectedId || list[0]?.id || "";
    if (id) setSelectedId(id);
  }

  async function refreshSupervisor() {
    const report = await api<SupervisorReport>("/api/supervisor");
    setSupervisor(report);
    setOperatorActionQueue(report.operator_action_queue);
    setOperatorDispatchRestartSmokeLedger(report.operator_dispatch_restart_smoke_ledger);
  }

  async function refreshOperatorActions() {
    const report = await api<OperatorActionQueueReport>("/api/operator-actions");
    setOperatorActionQueue(report);
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
      objectiveReadinessResult,
      readinessCompletionResult,
      readinessRehearsalResult,
      policyResult,
      resumeDecisionResult,
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
    ] = await Promise.all([
      api<RunRecord>(`/api/runs/${id}`),
      api<EventRecord[]>(`/api/runs/${id}/events`),
      api<ApprovalRecord[]>(`/api/runs/${id}/approvals`),
      api<{ note: string }>(`/api/runs/${id}/notes`),
      api<ReplayBundle>(`/api/runs/${id}/replay`),
      api<CompletionAuditReport>(`/api/runs/${id}/completion-audit`),
      api<RunHealthReport>(`/api/runs/${id}/health`),
      api<RunProgressReport>(`/api/runs/${id}/progress`),
      api<ReportIntegrityReport>(`/api/runs/${id}/report-integrity`),
      api<ObjectiveReadinessReport>(`/api/runs/${id}/objective-readiness`),
      api<ReadinessCompletionReport>(`/api/runs/${id}/readiness-completion`),
      api<ReadinessRehearsalReport>(`/api/runs/${id}/readiness-rehearsal`),
      api<PolicySimulationReport>(`/api/runs/${id}/policy-simulation`),
      api<ResumeDecisionReport>(`/api/runs/${id}/resume-decisions`),
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
    ]);
    setSelected({
      ...run,
      state: {
        ...run.state,
        run_health: healthResult,
        run_progress: progressResult,
        report_integrity: integrityResult,
        objective_readiness: objectiveReadinessResult,
        readiness_completion: readinessCompletionResult,
        readiness_rehearsal: readinessRehearsalResult,
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
      },
    });
    setEvents(eventList);
    setApprovals(approvalList);
    setReplay(replayResult);
    setCompletionAudit(auditResult);
    setRunProgress(progressResult);
    setReportIntegrity(integrityResult);
    setObjectiveReadiness(objectiveReadinessResult);
    setReadinessCompletion(readinessCompletionResult);
    setReadinessRehearsal(readinessRehearsalResult);
    setPolicySimulation(policyResult);
    setResumeDecisions(resumeDecisionResult);
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
    setNotes(noteResult.note);
  }

  useEffect(() => {
    refreshRuns().catch((err: Error) => setError(err.message));
    refreshSupervisor().catch((err: Error) => setError(err.message));
    refreshOperatorActions().catch((err: Error) => setError(err.message));
    refreshOperatorDispatches().catch((err: Error) => setError(err.message));
    refreshOperatorDispatchRestartSmokeLedger().catch((err: Error) => setError(err.message));
    refreshCompletionPolicy().catch((err: Error) => setError(err.message));
    refreshReadinessRehearsalLedger().catch((err: Error) => setError(err.message));
    refreshOrnithPreflight().catch((err: Error) => setError(err.message));
    refreshModelProfile().catch((err: Error) => setError(err.message));
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
          tool_profile: "balanced",
          web_enabled: webEnabled,
          browser_enabled: browserEnabled,
          desktop_enabled: desktopEnabled,
        }),
      });
      await refreshRuns(run.id);
      setSelectedId(run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function control(action: "pause" | "resume" | "cancel") {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api<RunRecord>(`/api/runs/${selectedId}/${action}`, { method: "POST" });
      await refreshSelected();
      await refreshRuns(selectedId);
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
    if (item.ui_target === "context_checkpoint") return "Checkpoint";
    if (item.ui_target === "handoff_refresh") return "Refresh";
    if (item.ui_target === "recovery") return "Resume";
    if (item.ui_target === "resume") return "Resume";
    if (item.ui_target === "goal") return "Review";
    if (item.ui_target === "steer") return "Steer";
    return "Dispatch";
  }

  function queueCanDispatch(item: OperatorActionQueueItem) {
    return [
      "readiness_rehearsal",
      "operator_dispatch_restart_smoke",
      "context_checkpoint",
      "handoff_refresh",
      "recovery",
      "resume",
      "goal",
    ].includes(item.ui_target);
  }

  async function dispatchQueueItem(
    item: OperatorActionQueueItem,
    decision: "dispatch" | "approve" | "reject" = "dispatch",
  ) {
    const label = decision === "dispatch" ? queueDispatchLabel(item) : decision;
    const confirmed = globalThis.confirm(`${label} queued action for ${item.title}?`);
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<OperatorActionDispatchResult>("/api/operator-actions/dispatch", {
        method: "POST",
        body: JSON.stringify({ item_id: item.id, decision, confirmed: true }),
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

  async function openQueueItem(runId: string) {
    setSelectedId(runId);
    await refreshRuns(runId);
    await refreshSelected(runId);
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Brain size={24} />
          <div>
            <strong>AgentOrinth</strong>
            <span>local loop harness</span>
          </div>
        </div>

        <form className="new-run" onSubmit={createRun}>
          <label htmlFor="goal">Goal</label>
          <textarea id="goal" value={goal} onChange={(event) => setGoal(event.target.value)} />
          <label htmlFor="criteria">Acceptance criteria</label>
          <textarea id="criteria" value={criteria} onChange={(event) => setCriteria(event.target.value)} />
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
          <button className="primary" type="submit" disabled={busy}>
            <Play size={16} />
            Start
          </button>
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

        <nav className="run-list" aria-label="Runs">
          {visibleRuns.map((run) => {
            const supervisorRun = supervisorRunById.get(run.id);
            return (
              <button
                className={run.id === selectedId ? "run-item active" : "run-item"}
                key={run.id}
                onClick={() => setSelectedId(run.id)}
                type="button"
              >
                <span>{run.title}</span>
                <small>
                  {run.status}
                  {supervisorRun?.operator_attention_required
                    ? ` / ${supervisorRun.operator_attention_reasons.join(", ")}`
                    : ""}
                </small>
              </button>
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
            </button>
            <button type="button" onClick={() => control("resume")} disabled={!selectedId || busy}>
              <RotateCcw size={16} />
            </button>
            <button type="button" onClick={() => control("cancel")} disabled={!selectedId || busy}>
              <Square size={16} />
            </button>
          </div>
        </header>

        {error && <div className="error">{error}</div>}

        <div className="status-strip">
          <span className={`status ${selected?.status ?? "idle"}`}>{selected?.status ?? "idle"}</span>
          <span className="milestone">{selected?.state.milestone ?? "idle"}</span>
          <div className="meter" aria-label="Progress">
            <span style={{ width: `${progress}%` }} />
          </div>
          <strong>{progress}%</strong>
        </div>

        <div className="attention-strip">
          <span>attention {supervisor?.operator_attention_count ?? 0}</span>
          <span>blocked {supervisor?.operator_attention_blocked_count ?? 0}</span>
          <span>watch {supervisor?.operator_attention_watch_count ?? 0}</span>
          <span>approvals {supervisor?.pending_approval_count ?? pendingApprovals.length}</span>
          <span>smoke {supervisor?.readiness_smoke_attention_count ?? 0}</span>
          <span>dispatch smoke {supervisor?.operator_dispatch_restart_smoke_attention_count ?? 0}</span>
          <span>preflight {supervisor?.ornith_preflight_attention_count ?? 0}</span>
          <span>source evidence {supervisor?.source_evidence_attention_count ?? 0}</span>
          <span>recovery {supervisor?.operator_recovery_count ?? 0}</span>
          <span>blockers {supervisor?.operator_blocker_count ?? 0}</span>
        </div>

        <div className="grid">
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
                operatorActionQueue ? `smoke: ${operatorActionQueue.smoke_count}` : "",
                operatorActionQueue ? `preflight: ${operatorActionQueue.preflight_count}` : "",
                operatorActionQueue ? `recovery: ${operatorActionQueue.recovery_count}` : "",
                operatorActionQueue ? `blockers: ${operatorActionQueue.blocker_count}` : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No queue counts."
            />
            {operatorDispatchMessage && <p className="muted">{operatorDispatchMessage}</p>}
            {(operatorActionQueue?.items ?? []).length === 0 ? (
              <p className="muted">Queue is clear.</p>
            ) : (
              <div className="queue-list">
                {(operatorActionQueue?.items ?? []).slice(0, 6).map((item) => (
                  <div className={`queue-item ${item.severity}`} key={item.id}>
                    <div>
                      <strong>
                        {item.severity} / {item.reason}
                      </strong>
                      <span>{item.title}</span>
                      <p>{item.action}</p>
                      <small>
                        {item.status} / priority {item.priority}
                        {item.approval_id ? ` / approval ${item.approval_id}` : ""}
                      </small>
                    </div>
                    <div className="queue-actions">
                      <button type="button" onClick={() => openQueueItem(item.run_id)}>
                        Open
                      </button>
                      {item.ui_target === "approval" && item.approval_id ? (
                        <>
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
            <List
              items={[
                selected?.state.action_context?.selected_action
                  ? `next: ${selected.state.action_context?.selected_action}`
                  : "",
                selected?.state.action_context?.missing_source_labels.length
                  ? `missing source: ${selected.state.action_context?.missing_source_labels.join(", ")}`
                  : "",
                selected?.state.action_context?.latest_source_evidence
                  ? `latest source: ${selected.state.action_context?.latest_source_evidence}`
                  : "",
                selected?.state.action_context?.context_budget
                  ? `context: ${selected.state.action_context?.context_budget}`
                  : "",
              ].filter((item): item is string => Boolean(item))}
              empty="No packed action details."
            />
            <pre>{selected?.state.action_context?.compact_prompt || "No action context pack yet."}</pre>
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
            <List
              items={(reportIntegrity?.checks ?? [])
                .filter((item) => item.status !== "ok")
                .slice(0, 6)
                .map((item) => `${item.status}: ${item.section} - ${item.summary}`)}
              empty="No missing, stale, or mismatched sections."
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
                readinessRehearsal ? `selected: ${readinessRehearsal.status}` : "",
                readinessRehearsal?.run_id ? `run: ${readinessRehearsal.run_id}` : "",
                readinessRehearsal ? `restart: ${readinessRehearsal.restart_simulated ? "yes" : "no"}` : "",
                readinessRehearsal ? `replay: ${readinessRehearsal.replay_attached ? "yes" : "no"}` : "",
                readinessRehearsal ? `handoff: ${readinessRehearsal.handoff_attached ? "yes" : "no"}` : "",
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
          <Panel title="Run Health" icon={<Gauge size={18} />}>
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
          <Panel title="Supervisor" icon={<Gauge size={18} />}>
            <p className="focus-text">
              {supervisor
                ? `${supervisor.auto_resumed} resumed / ${supervisor.recovered} recovered / ${supervisor.live} live`
                : "No startup pass recorded."}
            </p>
            <p className="muted">
              {supervisor
                ? `auto-resume ${supervisor.auto_resume_enabled ? "on" : "off"} / max ${supervisor.auto_resume_max_runs} / attention ${supervisor.operator_attention_count} / smoke ${supervisor.readiness_smoke_attention_count} / dispatch smoke ${supervisor.operator_dispatch_restart_smoke_attention_count}`
                : ""}
            </p>
            <List
              items={[
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
                .map(
                (item) =>
                    `${item.action}: ${item.title} (priority ${item.supervisor_priority}, ${item.previous_status} -> ${item.status}, attention ${item.operator_attention_severity}/${item.operator_attention_reasons.join(",") || "none"}, progress ${item.run_progress.status}, readiness ${item.objective_readiness.status}, smoke ${item.readiness_smoke_status}, dispatch smoke ${item.operator_dispatch_restart_smoke_status}, source ${item.source_evidence_requires_attention ? "missing" : "ok"}, health ${item.run_health.level}/${item.run_health.recommended_action}, policy ${item.policy_simulation.policy_action}) ${item.operator_attention_required ? item.operator_attention_action : item.readiness_smoke_requires_attention ? item.readiness_smoke_action : item.operator_dispatch_restart_smoke_requires_attention ? item.operator_dispatch_restart_smoke_action : item.objective_readiness_action || item.auto_resume_reason}`,
              )}
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
                .map((item) => `${item.decision}: ${item.proposal.summary} (${item.created_at})`)}
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
                sourceEvidence?.missing_labels.length ? `missing: ${sourceEvidence.missing_labels.join(", ")}` : "",
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
                disabled={!selectedId || busy || (selected?.state.workspace_diff.total_files ?? 0) === 0}
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
            <List
              items={(selected?.state.patch_proposals ?? [])
                .slice(-5)
                .map((patch) => `${patch.status}: ${patch.title}${patch.backup_id ? ` (${patch.backup_id})` : ""}`)}
              empty="No patch proposals yet."
            />
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
                .map((failure) => `${failure.kind}/${failure.tool} x${failure.count}: ${failure.recovery_hint}`)}
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

        <section className="handoff">
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
          <pre>{selected?.state.handoff_summary.resume_prompt || "No handoff yet."}</pre>
          <pre>{selected?.state.context_snapshot.prompt_preview || "No compiled context yet."}</pre>
        </section>

        <section className="approval-band">
          <h2>Approvals</h2>
          {pendingApprovals.length === 0 ? (
            <p>No pending approvals.</p>
          ) : (
            pendingApprovals.map((approval) => (
              <div className="approval" key={approval.id}>
                <div>
                  <strong>{approval.action_kind}</strong>
                  <span>{approval.reason}</span>
                  <ApprovalPreview approval={approval} />
                </div>
                <button type="button" onClick={() => resolveApproval(approval.id, "approve")}>
                  <Check size={16} />
                </button>
                <button type="button" onClick={() => resolveApproval(approval.id, "reject")}>
                  <X size={16} />
                </button>
              </div>
            ))
          )}
        </section>
      </section>

      <aside className="rightbar">
        <section className="steer">
          <h2>Steer</h2>
          <form onSubmit={sendSteering}>
            <textarea value={steer} onChange={(event) => setSteer(event.target.value)} />
            <button type="submit" disabled={!selectedId}>
              <Send size={16} />
              Send
            </button>
          </form>
        </section>

        <section className="log">
          <h2>
            <Terminal size={18} />
            Events
          </h2>
          <div className="event-list">
            {events.map((event) => (
              <article key={event.id}>
                <span>{event.kind}</span>
                <p>{event.message}</p>
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
              </div>
              <a href={`${API_BASE}/api/runs/${replay.run_id}/replay.md`} target="_blank" rel="noreferrer">
                Markdown export
              </a>
              <List
                items={replay.approvals.slice(0, 4).map((approval) => `${approval.status}: ${approval.action_kind}`)}
                empty="No approvals recorded."
              />
              <pre>{replay.markdown.slice(0, 2200)}</pre>
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
          <pre>{notes || "No run note yet."}</pre>
        </section>
      </aside>
    </main>
  );
}

function ApprovalPreview({ approval }: { approval: ApprovalRecord }) {
  const preview = recordValue(approval.payload.preview);
  if (preview) {
    const files = arrayValue(preview.files)
      .map(recordValue)
      .filter((item): item is Record<string, unknown> => Boolean(item))
      .slice(0, 8);
    return (
      <div className="approval-preview">
        <p>{stringValue(preview.summary) || "Review compact action preview."}</p>
        <ul>
          {files.map((file) => (
            <li key={`${stringValue(file.status)}-${stringValue(file.path)}`}>
              <strong>{stringValue(file.status) || "change"}</strong>
              <span>{stringValue(file.path) || "unknown path"}</span>
              {stringValue(file.diff_excerpt) && <pre>{stringValue(file.diff_excerpt)}</pre>}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const args = recordValue(approval.payload.args);
  const diff = stringValue(args?.diff);
  if (diff) {
    return (
      <div className="approval-preview">
        <p>Patch diff preview</p>
        <pre>{diff.slice(0, 1800)}</pre>
      </div>
    );
  }

  return <code>{JSON.stringify(approval.payload)}</code>;
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

function List({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul>
      {items.slice(-8).map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  );
}

function Numbered({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ol>
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ol>
  );
}

