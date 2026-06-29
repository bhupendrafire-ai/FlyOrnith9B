import type {
  ActionReadinessReport,
  OperatorActionQueueItem,
  ReadinessSourceRefPreviewReport,
} from "./api";

export type ReadinessSourceRefGateView = {
  needed: boolean;
  mode: "none" | "queued" | "direct";
  queueItem?: OperatorActionQueueItem;
  action: string;
  meta: string;
  buttonLabel: string;
};

export function buildReadinessSourceRefGate(input: {
  selectedId: string;
  actionReadiness: ActionReadinessReport | null;
  readinessSourceRefs: ReadinessSourceRefPreviewReport | null;
  operatorActionQueueItems: OperatorActionQueueItem[];
}): ReadinessSourceRefGateView {
  const queueItem = input.selectedId
    ? input.operatorActionQueueItems.find(
        (item) => item.run_id === input.selectedId && item.ui_target === "readiness_source_refs",
      )
    : undefined;
  const issue = input.actionReadiness?.issues.find(
    (item) => item.id === "readiness_source_ref_refresh_required",
  );
  const staleProofOnly = Boolean(
    input.readinessSourceRefs?.status === "missing_proof_refs" &&
      input.readinessSourceRefs.missing_proof_ref_labels.length > 0 &&
      input.readinessSourceRefs.missing_source_evidence_labels.length === 0,
  );
  const needed = Boolean(queueItem) || Boolean(issue) || staleProofOnly;
  const mode = !needed ? "none" : queueItem ? "queued" : "direct";
  const action =
    queueItem?.action ||
    input.actionReadiness?.recommended_action ||
    input.readinessSourceRefs?.recommended_action ||
    "Refresh readiness source refs before continuing.";
  const meta = queueItem
    ? `queued ${queueItem.method} ${queueItem.endpoint}`
    : input.selectedId
      ? `direct POST /api/runs/${input.selectedId}/readiness-source-refs/refresh`
      : "";

  return {
    needed,
    mode,
    queueItem,
    action,
    meta,
    buttonLabel: queueItem ? "Dispatch Refresh" : "Refresh",
  };
}