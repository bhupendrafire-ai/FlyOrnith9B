import type {
  ActionReadinessReport,
  ApprovalReviewRecord,
  EventRecord,
  OperatorActionQueueItem,
  RecoveryDecisionReport,
  RunRecord,
} from "./api";

export type ActivityFeedRole = "user" | "ornith" | "harness" | "tool" | "operator" | "system";

export type ActivityFeedKind = "timeline" | "required_action" | "artifact";

export type ActivityFeedActionType =
  | "approval"
  | "goal_confirmation"
  | "queue"
  | "recovery"
  | "artifact"
  | "handoff"
  | "blocker"
  | "readiness";

export type WorkbenchArtifact = {
  id: string;
  kind: string;
  title: string;
  summary: string;
  timestamp?: string;
  href?: string;
  path?: string;
};

export type ActivityFeedItem = {
  id: string;
  role: ActivityFeedRole;
  kind: ActivityFeedKind;
  title: string;
  body: string;
  timestamp: string;
  severity?: "normal" | "watch" | "blocked";
  actionType?: ActivityFeedActionType;
  approvalId?: number;
  approvalKind?: string;
  queueItemId?: string;
  queueDecision?: "open" | "dispatch" | "approve" | "reject";
  artifactHref?: string;
  artifactPath?: string;
  meta?: string[];
};

export type ActivityFeedInput = {
  selected: RunRecord | null;
  events: EventRecord[];
  approvals: ApprovalReviewRecord[];
  queueItems: OperatorActionQueueItem[];
  artifacts: WorkbenchArtifact[];
  actionReadiness: ActionReadinessReport | null;
  recoveryDecisions: RecoveryDecisionReport | null;
};

export function buildActivityFeed(input: ActivityFeedInput): ActivityFeedItem[] {
  const { selected } = input;
  if (!selected) return [];

  const required: ActivityFeedItem[] = [];
  const timeline: ActivityFeedItem[] = [];
  const nowish = selected.updated_at || selected.created_at;

  timeline.push({
    id: "goal",
    role: "user",
    kind: "timeline",
    title: "Original Goal",
    body: selected.goal,
    timestamp: selected.created_at,
  });

  const activeProject =
    selected.state.workspace_isolation?.workspace_path || selected.workspace_path || selected.state.workspace_isolation?.source_path;
  if (activeProject) {
    timeline.push({
      id: "project-workspace",
      role: "system",
      kind: "timeline",
      title: "Project Workspace",
      body: workspaceSummary(selected),
      timestamp: nowish,
    });
  }

  if (selected.state.goal && selected.state.goal !== selected.goal) {
    timeline.push({
      id: "active-goal",
      role: "ornith",
      kind: "timeline",
      title: "Active Goal",
      body: selected.state.goal,
      timestamp: selected.updated_at,
    });
  }

  if (selected.state.next_step) {
    timeline.push({
      id: "next-step",
      role: "ornith",
      kind: "timeline",
      title: "Next Action",
      body: selected.state.next_step,
      timestamp: selected.updated_at,
    });
  }

  input.approvals
    .filter((approval) => approval.status === "pending" && approval.action_kind === "goal_update")
    .forEach((approval) => {
      required.push({
        id: `required-goal-${approval.id}`,
        role: "operator",
        kind: "required_action",
        title: "Confirm Updated Goal",
        body: goalApprovalBody(approval),
        timestamp: approval.created_at,
        severity: "blocked",
        actionType: "goal_confirmation",
        approvalId: approval.id,
        approvalKind: approval.action_kind,
        meta: [`approval ${approval.id}`, approval.reviewed ? "reviewed" : "needs review"],
      });
    });

  input.approvals
    .filter((approval) => approval.status === "pending" && approval.action_kind !== "goal_update")
    .forEach((approval) => {
      required.push({
        id: `required-approval-${approval.id}`,
        role: "operator",
        kind: "required_action",
        title: approvalTitle(approval),
        body: approval.summary || approval.reason || "Review this approval before Ornith continues.",
        timestamp: approval.created_at,
        severity: approval.high_risk ? "blocked" : "watch",
        actionType: "approval",
        approvalId: approval.id,
        approvalKind: approval.action_kind,
        meta: [
          `approval ${approval.id}`,
          approval.high_risk ? "high risk" : "standard",
          approval.reviewed ? "reviewed" : "needs review",
        ],
      });
    });

  input.queueItems.forEach((item) => {
    if (item.approval_id && input.approvals.some((approval) => approval.id === item.approval_id && approval.status === "pending")) {
      return;
    }
    const actionType = queueActionType(item);
    required.push({
      id: `required-queue-${item.id}`,
      role: "operator",
      kind: "required_action",
      title: actionType === "goal_confirmation" ? "Goal Confirmation" : item.title || item.reason,
      body:
        actionType === "goal_confirmation"
          ? [
              "Ornith proposed an updated goal. Confirm before continuing.",
              item.action || item.supervisor_action || "Review the proposed goal update.",
            ].join("\n")
          : item.action || item.supervisor_action || "Review this queued operator action.",
      timestamp: nowish,
      severity: item.severity,
      actionType,
      queueItemId: item.id,
      queueDecision: actionType === "approval" ? "open" : "dispatch",
      approvalId: item.approval_id || undefined,
      approvalKind: item.approval_kind || undefined,
      meta: [
        item.reason,
        item.status,
        item.ui_target ? `target ${item.ui_target}` : "",
        item.details.slice(0, 2).join(" / "),
      ].filter(Boolean),
    });
  });

  if (selected.status === "waiting_goal_confirmation" && !required.some((item) => item.actionType === "goal_confirmation")) {
    required.push({
      id: "required-status-goal-confirmation",
      role: "operator",
      kind: "required_action",
      title: "Goal Confirmation Needed",
      body: "Ornith proposed an updated goal. Confirm before continuing. If no approval id is shown, refresh the run or Activity tab because the status and approval ledger are out of sync.",
      timestamp: nowish,
      severity: "blocked",
      actionType: "goal_confirmation",
      meta: ["waiting_goal_confirmation"],
    });
  }

  if (input.recoveryDecisions?.active_recovery) {
    required.push({
      id: "required-recovery",
      role: "operator",
      kind: "required_action",
      title: "Recovery Decision",
      body:
        input.recoveryDecisions.active_decision?.next_action ||
        input.recoveryDecisions.latest_decision?.next_action ||
        input.recoveryDecisions.active_decision?.summary ||
        input.recoveryDecisions.latest_decision?.summary ||
        "Resume recovery or replan before continuing.",
      timestamp: input.recoveryDecisions.generated_at,
      severity: "blocked",
      actionType: "recovery",
      meta: ["active recovery"],
    });
  }

  if (input.actionReadiness && !input.actionReadiness.ready_to_act) {
    required.push({
      id: "required-action-readiness",
      role: "operator",
      kind: "required_action",
      title: "Action Readiness",
      body: input.actionReadiness.recommended_action || input.actionReadiness.summary || "Resolve readiness before acting.",
      timestamp: input.actionReadiness.generated_at,
      severity: input.actionReadiness.status === "blocked" ? "blocked" : "watch",
      actionType: "readiness",
      meta: [input.actionReadiness.status, input.actionReadiness.suggested_label].filter(Boolean),
    });
  }

  (selected.state.handoff_summary?.unresolved_blockers ?? []).slice(0, 4).forEach((blocker, index) => {
    required.push({
      id: `required-blocker-${index}`,
      role: "operator",
      kind: "required_action",
      title: "Resolve Blocker",
      body: blocker,
      timestamp: nowish,
      severity: "blocked",
      actionType: "blocker",
      meta: ["handoff blocker"],
    });
  });

  const hasWorkstream = input.events.some((event) => event.kind === "workstream");
  const modelInteractionWindow = hasWorkstream ? selected.state.model_interactions.slice(-4) : selected.state.model_interactions.slice(-14);
  const toolCallWindow = hasWorkstream ? selected.state.tool_calls.slice(-6) : selected.state.tool_calls.slice(-18);
  const commandWindow = hasWorkstream ? selected.state.commands_run.slice(-4) : selected.state.commands_run.slice(-10);
  const eventWindow = hasWorkstream
    ? input.events.filter((event) => event.kind === "workstream").slice(-48)
    : input.events.slice(-24);

  modelInteractionWindow.forEach((interaction) => {
    timeline.push({
      id: `model-${interaction.id}`,
      role: "ornith",
      kind: "timeline",
      title: `${hasWorkstream ? "Model detail: " : ""}${interaction.kind}${interaction.fallback_used ? " fallback" : ""}`,
      body:
        interaction.summary ||
        interaction.error ||
        interaction.raw_excerpt ||
        `attempts ${interaction.attempts}${interaction.repaired ? ", repaired" : ""}`,
      timestamp: interaction.created_at,
      severity: interaction.ok ? "normal" : "watch",
    });
  });

  toolCallWindow.forEach((toolCall) => {
    timeline.push({
      id: `tool-${toolCall.id}`,
      role: "tool",
      kind: "timeline",
      title: `${hasWorkstream ? "Tool detail: " : ""}${toolCall.name}${toolCall.ok ? "" : " failed"}`,
      body: toolCall.summary || compactJson(toolCall.args),
      timestamp: toolCall.created_at,
      severity: toolCall.ok ? "normal" : "watch",
    });
  });

  commandWindow.forEach((command, index) => {
    timeline.push({
      id: `command-${index}-${hashText(command)}`,
      role: "tool",
      kind: "timeline",
      title: hasWorkstream ? "Command detail" : "command",
      body: command,
      timestamp: selected.updated_at,
    });
  });

  eventWindow.forEach((event) => {
    timeline.push(event.kind === "workstream" ? workstreamItem(event) : legacyEventItem(event));
  });

  input.artifacts.slice(0, 18).forEach((artifact) => {
    timeline.push({
      id: `artifact-${artifact.id}`,
      role: "system",
      kind: "artifact",
      title: artifact.title,
      body: artifact.summary,
      timestamp: artifact.timestamp || selected.updated_at,
      actionType: "artifact",
      artifactHref: artifact.href,
      artifactPath: artifact.path,
      meta: [artifact.kind],
    });
  });

  return dedupe([
    ...required.sort(requiredActionSort),
    ...timeline.sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
  ]);
}

function workstreamItem(event: EventRecord): ActivityFeedItem {
  const data = asRecord(event.data);
  const summary = dataString(data, "summary") || event.message;
  const rationale = dataString(data, "rationale");
  const result = dataString(data, "result");
  const nextAction = dataString(data, "next_action");
  const body = [
    summary,
    rationale ? `Why: ${rationale}` : "",
    result && result !== summary ? `Result: ${result}` : "",
    nextAction ? `Next: ${nextAction}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  return {
    id: `workstream-${event.id}`,
    role: workstreamRole(dataString(data, "role")),
    kind: "timeline",
    title: dataString(data, "title") || "Workstream Update",
    body,
    timestamp: event.timestamp,
    severity: workstreamSeverity(dataString(data, "severity")),
    meta: workstreamMeta(data),
  };
}

function legacyEventItem(event: EventRecord): ActivityFeedItem {
  return {
    id: `event-${event.id}`,
    role: eventRole(event.kind),
    kind: "timeline",
    title: event.kind,
    body: event.message,
    timestamp: event.timestamp,
  };
}

function approvalTitle(approval: ApprovalReviewRecord): string {
  if (approval.action_kind === "workspace_promote") return "Approve Project Promotion";
  if (approval.action_kind.startsWith("desktop_")) return "Approve Desktop Action";
  if (approval.action_kind === "patch_apply") return "Approve Patch";
  return "Approval Required";
}

function goalApprovalBody(approval: ApprovalReviewRecord): string {
  const proposed = previewText(approval.preview, ["proposed_goal", "goal", "updated_goal", "summary"]);
  const reason = approval.reason || previewText(approval.preview, ["reason"]);
  return [
    "Ornith proposed an updated goal. Confirm before continuing.",
    proposed ? `Proposed goal: ${proposed}` : approval.summary,
    reason ? `Reason: ${reason}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function queueActionType(item: OperatorActionQueueItem): ActivityFeedActionType {
  if (
    item.reason === "goal_confirmation" ||
    item.reason.includes("goal") ||
    item.status === "waiting_goal_confirmation" ||
    item.ui_target === "goal" ||
    item.approval_kind === "goal_update"
  ) {
    return "goal_confirmation";
  }
  if (item.ui_target === "approval" || item.approval_id) return "approval";
  if (item.ui_target === "recovery" || item.ui_target === "resume") return "recovery";
  if (item.ui_target === "handoff_refresh" || item.ui_target === "context_checkpoint") return "handoff";
  if (item.reason.includes("blocker")) return "blocker";
  return "queue";
}

function requiredActionSort(a: ActivityFeedItem, b: ActivityFeedItem): number {
  const actionRank: Record<ActivityFeedActionType, number> = {
    goal_confirmation: 0,
    approval: 1,
    recovery: 2,
    blocker: 3,
    readiness: 4,
    handoff: 5,
    queue: 6,
    artifact: 7,
  };
  const severityRank = { blocked: 0, watch: 1, normal: 2 };
  return (
    (actionRank[a.actionType ?? "queue"] ?? 6) - (actionRank[b.actionType ?? "queue"] ?? 6) ||
    (severityRank[a.severity ?? "normal"] ?? 2) - (severityRank[b.severity ?? "normal"] ?? 2) ||
    a.timestamp.localeCompare(b.timestamp)
  );
}

function eventRole(kind: string): ActivityFeedRole {
  const lowered = kind.toLowerCase();
  if (lowered.includes("workstream")) return "harness";
  if (lowered.includes("tool") || lowered.includes("command")) return "tool";
  if (lowered.includes("approval") || lowered.includes("operator") || lowered.includes("block")) return "operator";
  if (lowered.includes("user") || lowered.includes("steer")) return "user";
  if (lowered.includes("model") || lowered.includes("plan") || lowered.includes("goal")) return "ornith";
  return "system";
}

function workstreamRole(role: string): ActivityFeedRole {
  if (role === "ornith" || role === "harness" || role === "tool" || role === "operator" || role === "system") {
    return role;
  }
  return "system";
}

function workstreamSeverity(severity: string): ActivityFeedItem["severity"] {
  if (severity === "blocked" || severity === "watch" || severity === "normal") return severity;
  return "normal";
}

function workstreamMeta(data: Record<string, unknown>): string[] {
  const refs = asRecord(data.refs);
  const refPairs = Object.entries(refs)
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return [dataString(data, "phase"), dataString(data, "tool"), ...refPairs].filter(Boolean);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function dataString(data: Record<string, unknown>, key: string): string {
  const value = data[key];
  if (typeof value === "string") return value.trim();
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function workspaceSummary(selected: RunRecord): string {
  const isolation = selected.state.workspace_isolation;
  const source = isolation?.source_path || selected.workspace_path;
  const active = isolation?.workspace_path || selected.workspace_path;
  const summary = isolation?.summary || "Using the selected project folder as the run workspace.";
  return [`Source: ${source}`, `Active: ${active}`, summary].filter(Boolean).join("\n");
}

function previewText(preview: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = preview[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function compactJson(value: unknown): string {
  try {
    const rendered = JSON.stringify(value);
    return rendered.length > 360 ? `${rendered.slice(0, 357)}...` : rendered;
  } catch {
    return String(value);
  }
}

function hashText(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash.toString(16);
}

function dedupe(items: ActivityFeedItem[]): ActivityFeedItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}
