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

const desktopHelperPath = join(frontendRoot, "src", "desktopApprovalGate.ts");
const approvalHelperPath = join(frontendRoot, "src", "goalConfirmationGate.ts");
const appPath = join(frontendRoot, "src", "App.tsx");
const desktopHelper = await readFile(desktopHelperPath, "utf8");
const approvalHelper = await readFile(approvalHelperPath, "utf8");
const appSource = await readFile(appPath, "utf8");
const tmp = await mkdtemp(join(tmpdir(), "agentorinth-desktop-approval-"));

function transpile(source, fileName) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2020,
      target: ts.ScriptTarget.ES2020,
      importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove,
      verbatimModuleSyntax: false,
    },
    fileName,
  }).outputText;
}

function approval(overrides) {
  return {
    id: 1,
    run_id: "run-1",
    status: "pending",
    action_kind: "shell",
    reason: "Run a command.",
    created_at: "2026-06-29T00:00:00+00:00",
    resolved_at: null,
    summary: "Approval summary.",
    preview: {},
    files: [],
    payload_keys: [],
    high_risk: false,
    reviewed: false,
    review_count: 0,
    latest_reviewed_at: "",
    latest_review_event_id: 0,
    ...overrides,
  };
}

try {
  const desktopModulePath = join(tmp, "desktopApprovalGate.mjs");
  const approvalModulePath = join(tmp, "goalConfirmationGate.mjs");
  await writeFile(desktopModulePath, transpile(desktopHelper, desktopHelperPath), "utf8");
  await writeFile(approvalModulePath, transpile(approvalHelper, approvalHelperPath), "utf8");
  const { buildDesktopApprovalDashboard, isDesktopApprovalKind } = await import(pathToFileURL(desktopModulePath).href);
  const { approvalDecisionLabel } = await import(pathToFileURL(approvalModulePath).href);

  const desktopClickApproval = approval({
    id: 21,
    action_kind: "desktop_click",
    reason: "Click the visible Confirm button at x=240 y=540.",
    summary: "Supervised desktop click requires operator approval.",
    preview: { x: 240, y: 540, window_title: "AgentOrinth Dashboard" },
    payload_keys: ["tool_name", "args"],
    high_risk: true,
  });
  const desktopTypeApproval = approval({
    id: 22,
    action_kind: "desktop_type",
    reason: "Type non-secret text into the focused visible window.",
    reviewed: true,
    review_count: 1,
  });
  const shellApproval = approval({ id: 23, action_kind: "shell", reason: "Run broad tests." });
  const queueItem = {
    id: "run-1:approval:21",
    run_id: "run-1",
    title: "Supervised desktop action",
    severity: "blocked",
    reason: "approval",
    action: "Review desktop_click approval, then approve or reject it in the dashboard.",
    status: "waiting_approval",
    supervisor_action: "Resolve pending desktop approval.",
    priority: 155,
    approval_id: 21,
    approval_kind: "desktop_click",
    endpoint: "/api/runs/run-1/approvals",
    method: "GET",
    ui_target: "approval",
    promotion_gate: false,
    details: ["Click the visible Confirm button.", "approval_id=21"],
  };

  assert.equal(isDesktopApprovalKind("desktop_click"), true);
  assert.equal(isDesktopApprovalKind("desktop_type"), true);
  assert.equal(isDesktopApprovalKind("browser_click"), false);

  const view = buildDesktopApprovalDashboard({
    approvals: [shellApproval, desktopClickApproval],
    operatorActionQueueItems: [queueItem],
  });
  assert.equal(view.needsApproval, true);
  assert.equal(view.desktopApprovals.length, 1);
  assert.equal(view.desktopApprovals[0].id, 21);
  assert.equal(view.queueItems.length, 1);
  assert.equal(view.action, queueItem.action);
  assert.match(view.meta, /approval 21/);
  assert.match(view.meta, /unreviewed/);
  assert.match(view.meta, /desktop click/);
  assert.match(view.meta, /queue GET \/api\/runs\/run-1\/approvals/);
  assert.match(view.meta, /Click the visible Confirm button\./);
  assert.equal(approvalDecisionLabel(desktopClickApproval, "approve"), "Approve desktop click");
  assert.equal(approvalDecisionLabel(desktopClickApproval, "reject"), "Reject desktop click");
  assert.equal(approvalDecisionLabel(desktopTypeApproval, "approve"), "Approve desktop typing");
  assert.equal(approvalDecisionLabel(desktopTypeApproval, "reject"), "Reject desktop typing");
  assert.equal(approvalDecisionLabel(shellApproval, "approve"), "Approve");

  const queueOnly = buildDesktopApprovalDashboard({ approvals: [], operatorActionQueueItems: [queueItem] });
  assert.equal(queueOnly.needsApproval, true);
  assert.equal(queueOnly.desktopApprovals.length, 0);
  assert.match(queueOnly.meta, /queue GET \/api\/runs\/run-1\/approvals/);

  const normalOnly = buildDesktopApprovalDashboard({ approvals: [shellApproval], operatorActionQueueItems: [] });
  assert.equal(normalOnly.needsApproval, false);
  assert.equal(normalOnly.queueItems.length, 0);

  assert.match(appSource, /buildDesktopApprovalDashboard/);
  assert.match(appSource, /desktopApprovalGate\.needsApproval/);
  assert.match(appSource, /<strong>Desktop Approval<\/strong>/);
  assert.match(appSource, /desktopApprovalGate\.desktopApprovals/);
  assert.match(appSource, /approvalDecisionLabel\(approval, "approve"\)/);
  assert.match(appSource, /approvalDecisionLabel\(approval, "reject"\)/);

  const goalIndex = appSource.indexOf("...goalConfirmationGate.goalApprovals");
  const desktopIndex = appSource.indexOf("...desktopApprovalGate.desktopApprovals");
  const promotionIndex = appSource.indexOf("...sourcePromotionApprovalGate.sourcePromotionApprovals");
  const unreviewedIndex = appSource.indexOf("...unreviewedPendingApprovals");
  assert.ok(goalIndex > -1, "goal approval ordering anchor is missing");
  assert.ok(desktopIndex > -1, "desktop approval ordering anchor is missing");
  assert.ok(promotionIndex > -1, "source promotion approval ordering anchor is missing");
  assert.ok(unreviewedIndex > -1, "unreviewed approval ordering anchor is missing");
  assert.ok(goalIndex < desktopIndex, "goal confirmations should remain before desktop approvals");
  assert.ok(desktopIndex < promotionIndex, "desktop approvals should be before source promotion approvals");
  assert.ok(promotionIndex < unreviewedIndex, "source promotion approvals should be before ordinary approvals");

  console.log("desktop approval dashboard smoke passed");
} finally {
  await rm(tmp, { recursive: true, force: true });
}