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

const sourceHelperPath = join(frontendRoot, "src", "sourcePromotionApprovalGate.ts");
const approvalHelperPath = join(frontendRoot, "src", "goalConfirmationGate.ts");
const appPath = join(frontendRoot, "src", "App.tsx");
const sourceHelper = await readFile(sourceHelperPath, "utf8");
const approvalHelper = await readFile(approvalHelperPath, "utf8");
const appSource = await readFile(appPath, "utf8");
const tmp = await mkdtemp(join(tmpdir(), "agentorinth-source-promotion-"));

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
  const sourceModulePath = join(tmp, "sourcePromotionApprovalGate.mjs");
  const approvalModulePath = join(tmp, "goalConfirmationGate.mjs");
  await writeFile(sourceModulePath, transpile(sourceHelper, sourceHelperPath), "utf8");
  await writeFile(approvalModulePath, transpile(approvalHelper, approvalHelperPath), "utf8");
  const { buildSourcePromotionApprovalDashboard } = await import(pathToFileURL(sourceModulePath).href);
  const { approvalDecisionLabel } = await import(pathToFileURL(approvalModulePath).href);

  const promotionApproval = approval({
    id: 11,
    action_kind: "workspace_promote",
    reason: "Promote isolated workspace changes to source.",
    summary: "Source promotion requires reviewed diff and verification.",
    preview: {
      summary: "2 workspace changes: README.md, src/app.py",
      files: [
        { status: "modified", path: "README.md" },
        { status: "modified", path: "src/app.py" },
      ],
    },
    files: ["README.md", "src/app.py"],
    payload_keys: ["tool_name", "args", "preview"],
    high_risk: true,
    reviewed: true,
    review_count: 1,
  });
  const shellApproval = approval({ id: 12, action_kind: "shell", reason: "Run broad tests." });
  const queueItem = {
    id: "run-1:approval:workspace_promote",
    run_id: "run-1",
    title: "Source promotion run",
    severity: "blocked",
    reason: "approval",
    action: "Review pending workspace promotion approval.",
    status: "waiting_approval",
    supervisor_action: "Resolve source promotion approval.",
    priority: 140,
    approval_id: 11,
    approval_kind: "workspace_promote",
    endpoint: "/api/runs/run-1/approvals",
    method: "GET",
    ui_target: "approval",
    promotion_gate: true,
    details: ["workspace_promote", "promotion gate"],
  };

  const view = buildSourcePromotionApprovalDashboard({
    approvals: [shellApproval, promotionApproval],
    operatorActionQueueItems: [queueItem],
  });
  assert.equal(view.needsApproval, true);
  assert.equal(view.sourcePromotionApprovals.length, 1);
  assert.equal(view.sourcePromotionApprovals[0].id, 11);
  assert.equal(view.queueItems.length, 1);
  assert.equal(view.queueItems[0].promotion_gate, true);
  assert.equal(view.action, queueItem.action);
  assert.match(view.meta, /approval 11/);
  assert.match(view.meta, /reviewed/);
  assert.match(view.meta, /queue GET \/api\/runs\/run-1\/approvals/);
  assert.match(view.meta, /promotion gate/);
  assert.equal(approvalDecisionLabel(promotionApproval, "approve"), "Approve source promotion");
  assert.equal(approvalDecisionLabel(promotionApproval, "reject"), "Reject source promotion");
  assert.equal(approvalDecisionLabel(shellApproval, "approve"), "Approve");

  const queueOnly = buildSourcePromotionApprovalDashboard({ approvals: [], operatorActionQueueItems: [queueItem] });
  assert.equal(queueOnly.needsApproval, true);
  assert.equal(queueOnly.sourcePromotionApprovals.length, 0);
  assert.match(queueOnly.meta, /queue GET \/api\/runs\/run-1\/approvals/);

  const normalOnly = buildSourcePromotionApprovalDashboard({ approvals: [shellApproval], operatorActionQueueItems: [] });
  assert.equal(normalOnly.needsApproval, false);
  assert.equal(normalOnly.queueItems.length, 0);

  assert.match(appSource, /buildSourcePromotionApprovalDashboard/);
  assert.match(appSource, /sourcePromotionApprovalGate\.needsApproval/);
  assert.match(appSource, /<strong>Source Promotion Approval<\/strong>/);
  assert.match(appSource, /sourcePromotionApprovalGate\.sourcePromotionApprovals/);
  assert.match(appSource, /orderedPendingApprovals\.map/);
  assert.match(appSource, /approvalDecisionLabel\(approval, "approve"\)/);
  assert.match(appSource, /approvalDecisionLabel\(approval, "reject"\)/);
  assert.match(appSource, /className=\{queueFilter === "promotion_approvals" \? "active" : ""\}/);

  const goalIndex = appSource.indexOf("...goalConfirmationGate.goalApprovals");
  const promotionIndex = appSource.indexOf("...sourcePromotionApprovalGate.sourcePromotionApprovals");
  const unreviewedIndex = appSource.indexOf("...unreviewedPendingApprovals");
  assert.ok(goalIndex > -1, "goal approval ordering anchor is missing");
  assert.ok(promotionIndex > -1, "source promotion approval ordering anchor is missing");
  assert.ok(unreviewedIndex > -1, "unreviewed approval ordering anchor is missing");
  assert.ok(goalIndex < promotionIndex, "goal confirmations should remain before source promotion approvals");
  assert.ok(promotionIndex < unreviewedIndex, "source promotion approvals should be before ordinary approvals");

  console.log("source promotion dashboard smoke passed");
} finally {
  await rm(tmp, { recursive: true, force: true });
}