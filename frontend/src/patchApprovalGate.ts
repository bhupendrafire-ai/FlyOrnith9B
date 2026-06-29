import type { OperatorActionQueueItem, PatchProposal, PromotionRepairReport } from "./api";

export type PatchApprovalCard = {
  patch: PatchProposal;
  activeRepairPatch: boolean;
  canRequestApply: boolean;
  queuedOperatorItem?: OperatorActionQueueItem;
  buttonLabel: string;
  statusText: string;
  meta: string;
  disabledReason: string;
};

export function buildPatchApprovalCards(input: {
  patchProposals: PatchProposal[];
  promotionRepair: PromotionRepairReport | null;
  operatorActionQueueItems: OperatorActionQueueItem[];
  limit?: number;
}): PatchApprovalCard[] {
  const limit = input.limit ?? 5;
  return input.patchProposals.slice(-limit).map((patch) => {
    const queuedOperatorItem = input.operatorActionQueueItems.find(
      (item) => item.ui_target === "patch_apply_approval" && item.endpoint.includes(`/patches/${patch.id}/apply`),
    );
    const activeRepairPatch = input.promotionRepair?.patch_proposal_id === patch.id;
    const canRequestApply = patch.status === "pending" || patch.status === "approved";
    const statusText = `${patch.status}${activeRepairPatch ? " / promotion repair" : ""}`;
    const metaParts = [
      patch.files.length ? patch.files.join(", ") : patch.id,
      queuedOperatorItem ? `queued ${queuedOperatorItem.method} ${queuedOperatorItem.endpoint}` : "",
    ].filter(Boolean);
    const disabledReason = canRequestApply ? "" : `Patch is ${patch.status}; apply approval is not available.`;

    return {
      patch,
      activeRepairPatch,
      canRequestApply,
      queuedOperatorItem,
      buttonLabel: queuedOperatorItem ? "Dispatch Approval" : "Request Approval",
      statusText,
      meta: metaParts.join(" / "),
      disabledReason,
    };
  });
}