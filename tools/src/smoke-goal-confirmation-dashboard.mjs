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

const helperPath = join(frontendRoot, "src", "goalConfirmationGate.ts");
const appPath = join(frontendRoot, "src", "App.tsx");
const helperSource = await readFile(helperPath, "utf8");
const appSource = await readFile(appPath, "utf8");
const tmp = await mkdtemp(join(tmpdir(), "agentorinth-goal-confirmation-"));

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
  const transpiled = ts.transpileModule(helperSource, {
    compilerOptions: {
      module: ts.ModuleKind.ES2020,
      target: ts.ScriptTarget.ES2020,
      importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove,
      verbatimModuleSyntax: false,
    },
    fileName: helperPath,
  }).outputText;
  const modulePath = join(tmp, "goalConfirmationGate.mjs");
  await writeFile(modulePath, transpiled, "utf8");
  const { approvalDecisionLabel, buildGoalConfirmationDashboard } = await import(pathToFileURL(modulePath).href);

  const goalApproval = approval({
    id: 7,
    action_kind: "goal_update",
    reason: "Accept a revised long-run /goal statement.",
    summary: "Proposed goal keeps Ornith agency and narrows acceptance criteria.",
    preview: {
      fields: [
        { label: "proposed_goal", value: "Improve AgentOrinth with confirmed goal evolution." },
        { label: "reason", value: "The run discovered clearer acceptance criteria." },
      ],
    },
    payload_keys: ["proposed_goal", "reason"],
    high_risk: true,
  });
  const shellApproval = approval({ id: 8, action_kind: "shell", reason: "Run broad tests." });
  const queueItem = {
    id: "run-1:goal-confirmation:7",
    run_id: "run-1",
    title: "Goal confirmation run",
    severity: "blocked",
    reason: "goal_confirmation",
    action: "Accept or reject the proposed /goal update before resuming.",
    status: "waiting_goal_confirmation",
    supervisor_action: "Resolve goal confirmation.",
    priority: 150,
    approval_id: 7,
    approval_kind: "goal_update",
    endpoint: "/api/runs/run-1/approvals",
    method: "GET",
    ui_target: "approval",
    promotion_gate: false,
    details: ["proposed_goal=Improve AgentOrinth", "reason=scope changed"],
  };

  const view = buildGoalConfirmationDashboard({
    approvals: [shellApproval, goalApproval],
    operatorActionQueueItems: [queueItem],
  });
  assert.equal(view.needsConfirmation, true);
  assert.equal(view.goalApprovals.length, 1);
  assert.equal(view.goalApprovals[0].id, 7);
  assert.equal(view.queueItems[0].id, queueItem.id);
  assert.equal(view.orderedPendingApprovals[0].id, 7, "goal update approval must be first");
  assert.equal(view.orderedPendingApprovals[1].id, 8);
  assert.equal(view.action, queueItem.action);
  assert.match(view.meta, /approval 7/);
  assert.match(view.meta, /unreviewed/);
  assert.match(view.meta, /queue GET \/api\/runs\/run-1\/approvals/);
  assert.equal(approvalDecisionLabel(goalApproval, "approve"), "Accept goal update");
  assert.equal(approvalDecisionLabel(goalApproval, "reject"), "Reject goal update");
  assert.equal(approvalDecisionLabel(shellApproval, "approve"), "Approve");
  assert.equal(approvalDecisionLabel(shellApproval, "reject"), "Reject");

  const normalOnly = buildGoalConfirmationDashboard({
    approvals: [shellApproval],
    operatorActionQueueItems: [],
  });
  assert.equal(normalOnly.needsConfirmation, false);
  assert.equal(normalOnly.goalApprovals.length, 0);
  assert.equal(normalOnly.orderedPendingApprovals[0].id, 8);

  const queueOnly = buildGoalConfirmationDashboard({
    approvals: [],
    operatorActionQueueItems: [queueItem],
  });
  assert.equal(queueOnly.needsConfirmation, true);
  assert.equal(queueOnly.action, queueItem.action);
  assert.match(queueOnly.meta, /queue GET \/api\/runs\/run-1\/approvals/);

  assert.match(appSource, /buildGoalConfirmationDashboard/);
  assert.match(appSource, /goalConfirmationGate\.needsConfirmation/);
  assert.match(appSource, /<strong>Goal Confirmation<\/strong>/);
  assert.match(appSource, /orderedPendingApprovals\.map/);
  assert.match(appSource, /approvalDecisionLabel\(approval, "approve"\)/);
  assert.match(appSource, /approvalDecisionLabel\(approval, "reject"\)/);
  assert.match(appSource, /aria-label=\{approveLabel\}/);
  assert.match(appSource, /aria-label=\{rejectLabel\}/);
  assert.match(appSource, /resolveApproval\(approval\.id, "approve"\)/);
  assert.match(appSource, /resolveApproval\(approval\.id, "reject"\)/);
  const goalIndex = appSource.indexOf("...goalConfirmationGate.goalApprovals");
  const promotionIndex = appSource.indexOf("...sourcePromotionApprovalGate.sourcePromotionApprovals");
  const unreviewedIndex = appSource.indexOf("...unreviewedPendingApprovals");
  assert.ok(goalIndex > -1, "goal approval ordering anchor is missing");
  assert.ok(promotionIndex > -1, "source promotion ordering anchor is missing");
  assert.ok(unreviewedIndex > -1, "unreviewed approval ordering anchor is missing");
  assert.ok(goalIndex < promotionIndex, "goal confirmations must remain the first approval class");
  assert.ok(goalIndex < unreviewedIndex, "goal confirmations must come before ordinary approvals");

  console.log("goal confirmation dashboard smoke passed");
} finally {
  await rm(tmp, { recursive: true, force: true });
}