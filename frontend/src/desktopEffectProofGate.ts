import type { ActionContextPack, OperatorActionQueueItem } from "./api";

const desktopEffectMarker = "desktop_effect_check_required";

export type DesktopEffectProofGateView = {
  needed: boolean;
  mode: "none" | "queued" | "direct";
  queueItem?: OperatorActionQueueItem;
  action: string;
  meta: string;
  buttonLabel: string;
  effectEntry: string;
};

export function buildDesktopEffectProofGate(input: {
  selectedId: string;
  actionContext: ActionContextPack | null | undefined;
  operatorActionQueueItems: OperatorActionQueueItem[];
}): DesktopEffectProofGateView {
  const queueItem = input.selectedId
    ? input.operatorActionQueueItems.find(
        (item) => item.run_id === input.selectedId && item.ui_target === "desktop_effect_proof",
      )
    : undefined;
  const effectEntry =
    input.actionContext?.desktop_supervision_ledger.find((item) => item.includes(desktopEffectMarker)) || "";
  const needed = Boolean(queueItem) || Boolean(effectEntry);
  const mode = !needed ? "none" : queueItem ? "queued" : "direct";
  const action =
    queueItem?.action || "Capture desktop screenshot proof before another supervised desktop click/type.";
  const detailMeta = queueItem?.details.slice(0, 2).filter(Boolean).join(" / ") || effectEntry;
  const meta = queueItem
    ? [`queued ${queueItem.method} ${queueItem.endpoint}`, detailMeta].filter(Boolean).join(" / ")
    : input.selectedId
      ? [`direct POST /api/runs/${input.selectedId}/desktop-effect/verify`, detailMeta].filter(Boolean).join(" / ")
      : detailMeta;

  return {
    needed,
    mode,
    queueItem,
    action,
    meta,
    buttonLabel: queueItem ? "Dispatch Proof" : "Capture Proof",
    effectEntry,
  };
}
