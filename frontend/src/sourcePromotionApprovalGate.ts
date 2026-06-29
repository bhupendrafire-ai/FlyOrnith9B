import type { ApprovalReviewRecord, OperatorActionQueueItem } from "./api";

export type SourcePromotionApprovalDashboard = {
  needsApproval: boolean;
  sourcePromotionApprovals: ApprovalReviewRecord[];
  queueItems: OperatorActionQueueItem[];
  action: string;
  meta: string;
};

export function buildSourcePromotionApprovalDashboard(input: {
  approvals: ApprovalReviewRecord[];
  operatorActionQueueItems: OperatorActionQueueItem[];
}): SourcePromotionApprovalDashboard {
  const sourcePromotionApprovals = input.approvals.filter(
    (approval) => approval.status === "pending" && approval.action_kind === "workspace_promote",
  );
  const queueItems = input.operatorActionQueueItems.filter(
    (item) => item.approval_kind === "workspace_promote" || (item.promotion_gate && item.ui_target === "approval"),
  );
  const firstApproval = sourcePromotionApprovals[0];
  const firstQueueItem = queueItems[0];
  const needsApproval = sourcePromotionApprovals.length > 0 || queueItems.length > 0;
  const action =
    firstQueueItem?.action ||
    firstApproval?.reason ||
    "Approve or reject source promotion before copying isolated workspace changes back to source.";
  const metaParts = [
    firstApproval ? `approval ${firstApproval.id}` : "",
    firstApproval ? (firstApproval.reviewed ? "reviewed" : "unreviewed") : "",
    firstQueueItem ? `queue ${firstQueueItem.method} ${firstQueueItem.endpoint}` : "",
    firstQueueItem?.promotion_gate ? "promotion gate" : "",
  ].filter(Boolean);

  return {
    needsApproval,
    sourcePromotionApprovals,
    queueItems,
    action,
    meta: metaParts.join(" / "),
  };
}