import type { ApprovalReviewRecord, OperatorActionQueueItem } from "./api";

export type GoalConfirmationDashboard = {
  needsConfirmation: boolean;
  pendingApprovals: ApprovalReviewRecord[];
  unreviewedPendingApprovals: ApprovalReviewRecord[];
  reviewedPendingApprovals: ApprovalReviewRecord[];
  orderedPendingApprovals: ApprovalReviewRecord[];
  goalApprovals: ApprovalReviewRecord[];
  queueItems: OperatorActionQueueItem[];
  action: string;
  meta: string;
};

export function buildGoalConfirmationDashboard(input: {
  approvals: ApprovalReviewRecord[];
  operatorActionQueueItems: OperatorActionQueueItem[];
}): GoalConfirmationDashboard {
  const pendingApprovals = input.approvals.filter((approval) => approval.status === "pending");
  const goalApprovals = pendingApprovals.filter((approval) => approval.action_kind === "goal_update");
  const queueItems = input.operatorActionQueueItems.filter(
    (item) => item.reason === "goal_confirmation" || item.approval_kind === "goal_update",
  );
  const unreviewedPendingApprovals = pendingApprovals.filter((approval) => !approval.reviewed);
  const reviewedPendingApprovals = pendingApprovals.filter((approval) => approval.reviewed);
  const seen = new Set<number>();
  const orderedPendingApprovals = [
    ...goalApprovals,
    ...unreviewedPendingApprovals,
    ...reviewedPendingApprovals,
  ].filter((approval) => {
    if (seen.has(approval.id)) return false;
    seen.add(approval.id);
    return true;
  });
  const firstGoalApproval = goalApprovals[0];
  const firstQueueItem = queueItems[0];
  const needsConfirmation = goalApprovals.length > 0 || queueItems.length > 0;
  const action =
    firstQueueItem?.action ||
    firstGoalApproval?.reason ||
    "Accept or reject the proposed /goal update before resuming.";
  const metaParts = [
    firstGoalApproval ? `approval ${firstGoalApproval.id}` : "",
    firstGoalApproval ? (firstGoalApproval.reviewed ? "reviewed" : "unreviewed") : "",
    firstQueueItem ? `queue ${firstQueueItem.method} ${firstQueueItem.endpoint}` : "",
  ].filter(Boolean);

  return {
    needsConfirmation,
    pendingApprovals,
    unreviewedPendingApprovals,
    reviewedPendingApprovals,
    orderedPendingApprovals,
    goalApprovals,
    queueItems,
    action,
    meta: metaParts.join(" / "),
  };
}

export function approvalDecisionLabel(approval: ApprovalReviewRecord, action: "approve" | "reject"): string {
  if (approval.action_kind === "goal_update") {
    return action === "approve" ? "Accept goal update" : "Reject goal update";
  }
  if (approval.action_kind === "workspace_promote") {
    return action === "approve" ? "Approve source promotion" : "Reject source promotion";
  }
  if (approval.action_kind === "desktop_click") {
    return action === "approve" ? "Approve desktop click" : "Reject desktop click";
  }
  if (approval.action_kind === "desktop_type") {
    return action === "approve" ? "Approve desktop typing" : "Reject desktop typing";
  }
  return action === "approve" ? "Approve" : "Reject";
}