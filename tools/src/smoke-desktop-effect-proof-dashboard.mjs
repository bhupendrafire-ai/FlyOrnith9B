import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const frontendRoot = join(repoRoot, "frontend");
const requireFromFrontend = createRequire(join(frontendRoot, "package.json"));
const ts = requireFromFrontend("typescript");

const helperPath = join(frontendRoot, "src", "desktopEffectProofGate.ts");
const appPath = join(frontendRoot, "src", "App.tsx");
const helperSource = await readFile(helperPath, "utf8");
const appSource = await readFile(appPath, "utf8");
const tmp = await mkdtemp(join(tmpdir(), "agentorinth-desktop-effect-proof-"));

try {
  const transpiled = ts.transpileModule(helperSource, {
    compilerOptions: {
      module: ts.ModuleKind.ES2020,
      target: ts.ScriptTarget.ES2020,
      importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove,
      verbatimModuleSyntax: false,
    },
    fileName: helperPath,
  }).outputText;
  const modulePath = join(tmp, "desktopEffectProofGate.mjs");
  await writeFile(modulePath, transpiled, "utf8");
  const { buildDesktopEffectProofGate } = await import(pathToFileURL(modulePath).href);

  const queueItem = {
    id: "run-1:desktop-effect-proof",
    run_id: "run-1",
    title: "Desktop proof run",
    severity: "watch",
    reason: "desktop_effect_proof",
    action: "Capture desktop screenshot proof through the operator queue.",
    status: "paused",
    supervisor_action: "Capture desktop screenshot proof.",
    priority: 80,
    approval_id: 0,
    approval_kind: "",
    endpoint: "/api/runs/run-1/desktop-effect/verify",
    method: "POST",
    ui_target: "desktop_effect_proof",
    promotion_gate: false,
    details: ["after=desktop_click", "proof_tool=desktop_screenshot"],
  };
  const actionContext = {
    desktop_supervision_ledger: [
      "desktop_effect_check_required after desktop_click id=desktop-click-1",
    ],
  };

  const queued = buildDesktopEffectProofGate({
    selectedId: "run-1",
    actionContext,
    operatorActionQueueItems: [queueItem],
  });
  assert.equal(queued.needed, true);
  assert.equal(queued.mode, "queued");
  assert.equal(queued.queueItem.id, queueItem.id);
  assert.equal(queued.action, queueItem.action);
  assert.ok(queued.meta.startsWith("queued POST /api/runs/run-1/desktop-effect/verify"));
  assert.equal(queued.buttonLabel, "Dispatch Proof");

  const direct = buildDesktopEffectProofGate({
    selectedId: "run-1",
    actionContext,
    operatorActionQueueItems: [],
  });
  assert.equal(direct.needed, true);
  assert.equal(direct.mode, "direct");
  assert.equal(direct.queueItem, undefined);
  assert.ok(direct.meta.startsWith("direct POST /api/runs/run-1/desktop-effect/verify"));
  assert.equal(direct.buttonLabel, "Capture Proof");

  const none = buildDesktopEffectProofGate({
    selectedId: "run-1",
    actionContext: { desktop_supervision_ledger: ["desktop_approval_required for desktop_click"] },
    operatorActionQueueItems: [],
  });
  assert.equal(none.needed, false);
  assert.equal(none.mode, "none");

  assert.match(appSource, /buildDesktopEffectProofGate/);
  assert.match(appSource, /desktopEffectProofGate\.needed/);
  assert.ok(appSource.includes("<strong>Desktop Effect Proof</strong>"));
  assert.match(appSource, /desktopEffectProofGate\.buttonLabel/);
  assert.ok(appSource.includes("dispatchQueueItem(selectedDesktopEffectQueueItem)"));
  assert.match(appSource, /desktop_effect_proof/);
  assert.match(appSource, /DesktopEffectProofReport/);
  assert.match(appSource, /desktop-effect-proof/);
  assert.match(appSource, /desktopEffectProof\?\.ledger/);
  assert.match(appSource, /proof_snapshot/);
  assert.ok(appSource.includes("Desktop Proof Repair"));
  assert.match(appSource, /activeDesktopEffectProofRepairs/);
  assert.match(appSource, /desktop_effect_proof_repairs/);
  assert.ok(appSource.includes("desktop repairs:"));
  assert.ok(appSource.includes("metadata refreshes:"));
  assert.ok(appSource.includes("captures:"));
  assert.match(appSource, /repair #\$\{entry\.event_id\} \$\{entry\.outcome\}/);
  assert.match(appSource, /previous_proof_status/);
  assert.match(appSource, /refreshed_proof_status/);
  assert.match(appSource, /proof_snapshot_id/);
  assert.match(appSource, /desktopEffectIntegrityChecks/);
  assert.match(appSource, /handoff\.desktop_effect_proof/);
  assert.match(appSource, /desktop_effect_proof_count/);
  assert.match(appSource, /desktop_effect_proof_attention_count/);
  const queuedIndex = appSource.indexOf("dispatchQueueItem(selectedDesktopEffectQueueItem)");
  const directIndex = appSource.indexOf("/desktop-effect/verify`, { method: \"POST\" }");
  assert.ok(queuedIndex > -1, "queued dispatch path is missing");
  assert.ok(directIndex > -1, "direct desktop proof fallback is missing");
  assert.ok(queuedIndex < directIndex, "queued operator dispatch must be tried before direct desktop proof fallback");

  console.log("desktop effect proof dashboard smoke passed");
} finally {
  await rm(tmp, { recursive: true, force: true });
}
