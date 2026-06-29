import type { ApprovalReviewRecord, OperatorActionQueueItem } from "./api";

const desktopApprovalKinds = new Set(["desktop_click", "desktop_type"]);

export type DesktopApprovalDashboard = {
  needsApproval: boolean;
  desktopApprovals: ApprovalReviewRecord[];
  queueItems: OperatorActionQueueItem[];
  action: string;
  meta: string;
};

export function isDesktopApprovalKind(kind: string): boolean {
  return desktopApprovalKinds.has(kind);
}

export function buildDesktopApprovalDashboard(input: {
  approvals: ApprovalReviewRecord[];
  operatorActionQueueItems: OperatorActionQueueItem[];
}): DesktopApprovalDashboard {
  const desktopApprovals = input.approvals.filter(
    (approval) => approval.status === "pending" && isDesktopApprovalKind(approval.action_kind),
  );
  const queueItems = input.operatorActionQueueItems.filter((item) => isDesktopApprovalKind(item.approval_kind));
  const firstApproval = desktopApprovals[0];
  const firstQueueItem = queueItems[0];
  const needsApproval = desktopApprovals.length > 0 || queueItems.length > 0;
  const action =
    firstQueueItem?.action ||
    firstApproval?.reason ||
    "Approve or reject the supervised desktop action before Ornith controls the visible PC.";
  const metaParts = [
    firstApproval ? `approval ${firstApproval.id}` : "",
    firstApproval ? (firstApproval.reviewed ? "reviewed" : "unreviewed") : "",
    firstApproval ? firstApproval.action_kind.replace("_", " ") : "",
    firstQueueItem ? `queue ${firstQueueItem.method} ${firstQueueItem.endpoint}` : "",
    ...((firstQueueItem?.details ?? []).slice(0, 2)),
  ].filter(Boolean);

  return {
    needsApproval,
    desktopApprovals,
    queueItems,
    action,
    meta: metaParts.join(" / "),
  };
}