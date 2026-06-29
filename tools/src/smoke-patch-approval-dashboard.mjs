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

const helperPath = join(frontendRoot, "src", "patchApprovalGate.ts");
const appPath = join(frontendRoot, "src", "App.tsx");
const helperSource = await readFile(helperPath, "utf8");
const appSource = await readFile(appPath, "utf8");
const tmp = await mkdtemp(join(tmpdir(), "agentorinth-patch-approval-"));

function patch(id, status, files = ["src/app.py"]) {
  return {
    id,
    title: `Patch ${id}`,
    summary: `Summary for ${id}`,
    files,
    diff: "--- a/src/app.py\n+++ b/src/app.py\n@@\n-old\n+new\n",
    status,
    backup_id: "",
    applied_at: "",
    rollback_manifest_path: "",
    created_at: "2026-06-29T00:00:00+00:00",
  };
}

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
  const modulePath = join(tmp, "patchApprovalGate.mjs");
  await writeFile(modulePath, transpiled, "utf8");
  const { buildPatchApprovalCards } = await import(pathToFileURL(modulePath).href);

  const queuedItem = {
    id: "run-1:patch-apply:p-repair",
    run_id: "run-1",
    title: "Promotion repair patch approval",
    severity: "blocked",
    reason: "promotion_audit_pending_patch_review",
    action: "Request approval to apply promotion repair patch p-repair.",
    status: "paused",
    supervisor_action: "Request patch apply approval.",
    priority: 150,
    approval_id: 0,
    approval_kind: "patch_apply",
    endpoint: "/api/runs/run-1/patches/p-repair/apply",
    method: "POST",
    ui_target: "patch_apply_approval",
    promotion_gate: true,
    details: ["patch_id=p-repair"],
  };
  const cards = buildPatchApprovalCards({
    patchProposals: [
      patch("old-1", "pending"),
      patch("old-2", "pending"),
      patch("p-direct", "approved", ["src/direct.py"]),
      patch("p-repair", "pending", ["src/broken.py"]),
      patch("p-applied", "applied", ["src/done.py"]),
      patch("p-rejected", "rejected", ["src/rejected.py"]),
    ],
    promotionRepair: { patch_proposal_id: "p-repair" },
    operatorActionQueueItems: [queuedItem],
    limit: 5,
  });

  assert.deepEqual(cards.map((card) => card.patch.id), ["old-2", "p-direct", "p-repair", "p-applied", "p-rejected"]);

  const direct = cards.find((card) => card.patch.id === "p-direct");
  assert.equal(direct.canRequestApply, true);
  assert.equal(direct.buttonLabel, "Request Approval");
  assert.equal(direct.queuedOperatorItem, undefined);
  assert.equal(direct.meta, "src/direct.py");

  const repair = cards.find((card) => card.patch.id === "p-repair");
  assert.equal(repair.canRequestApply, true);
  assert.equal(repair.activeRepairPatch, true);
  assert.equal(repair.statusText, "pending / promotion repair");
  assert.equal(repair.queuedOperatorItem.id, queuedItem.id);
  assert.equal(repair.buttonLabel, "Dispatch Approval");
  assert.match(repair.meta, /src\/broken\.py/);
  assert.match(repair.meta, /queued POST \/api\/runs\/run-1\/patches\/p-repair\/apply/);

  const applied = cards.find((card) => card.patch.id === "p-applied");
  assert.equal(applied.canRequestApply, false);
  assert.equal(applied.disabledReason, "Patch is applied; apply approval is not available.");

  const rejected = cards.find((card) => card.patch.id === "p-rejected");
  assert.equal(rejected.canRequestApply, false);
  assert.equal(rejected.disabledReason, "Patch is rejected; apply approval is not available.");

  assert.match(appSource, /buildPatchApprovalCards/);
  assert.match(appSource, /patchApprovalCards\.map/);
  assert.match(appSource, /requestPatchApprovalFromCard\(card\)/);
  assert.match(appSource, /dispatchQueueItem\(card\.queuedOperatorItem\)/);
  assert.match(appSource, /requestPatchApplyApproval\(card\.patch\.id\)/);
  assert.match(appSource, /aria-label=\{`\$\{card\.buttonLabel\}: \$\{card\.patch\.title\}`\}/);
  assert.match(appSource, /title=\{card\.disabledReason \|\| card\.buttonLabel\}/);
  const queuedIndex = appSource.indexOf("dispatchQueueItem(card.queuedOperatorItem)");
  const directIndex = appSource.indexOf("requestPatchApplyApproval(card.patch.id)");
  assert.ok(queuedIndex > -1, "queued patch apply approval dispatch is missing");
  assert.ok(directIndex > -1, "direct patch apply approval fallback is missing");
  assert.ok(queuedIndex < directIndex, "queued patch apply approval must be tried before direct fallback");

  console.log("patch approval dashboard smoke passed");
} finally {
  await rm(tmp, { recursive: true, force: true });
}