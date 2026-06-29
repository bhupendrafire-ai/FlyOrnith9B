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

const helperPath = join(frontendRoot, "src", "readinessSourceRefGate.ts");
const appPath = join(frontendRoot, "src", "App.tsx");
const helperSource = await readFile(helperPath, "utf8");
const appSource = await readFile(appPath, "utf8");
const tmp = await mkdtemp(join(tmpdir(), "agentorinth-source-ref-gate-"));

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
  const modulePath = join(tmp, "readinessSourceRefGate.mjs");
  await writeFile(modulePath, transpiled, "utf8");
  const { buildReadinessSourceRefGate } = await import(pathToFileURL(modulePath).href);

  const queueItem = {
    id: "run-1:readiness-source-refs",
    run_id: "run-1",
    title: "Source ref run",
    severity: "blocked",
    reason: "readiness_source_refs",
    action: "Refresh source refs through the operator queue.",
    status: "paused",
    supervisor_action: "Refresh source refs.",
    priority: 100,
    approval_id: 0,
    approval_kind: "",
    endpoint: "/api/runs/run-1/readiness-source-refs/refresh",
    method: "POST",
    ui_target: "readiness_source_refs",
    promotion_gate: false,
    details: ["preview_status=missing_proof_refs", "missing_proof=browser"],
  };
  const actionReadiness = {
    issues: [
      {
        id: "readiness_source_ref_refresh_required",
        severity: "blocker",
        summary: "Readiness source evidence exists, but proof refs are stale.",
        evidence: ["missing_proof=browser"],
      },
    ],
    recommended_action: "Dispatch confirmed readiness source-ref refresh before asking Ornith for another model tool.",
  };
  const staleProofPreview = {
    status: "missing_proof_refs",
    missing_proof_ref_labels: ["browser"],
    missing_source_evidence_labels: [],
    recommended_action: "Dispatch readiness source-ref refresh before broad coding.",
  };

  const queued = buildReadinessSourceRefGate({
    selectedId: "run-1",
    actionReadiness,
    readinessSourceRefs: staleProofPreview,
    operatorActionQueueItems: [queueItem],
  });
  assert.equal(queued.needed, true);
  assert.equal(queued.mode, "queued");
  assert.equal(queued.queueItem.id, queueItem.id);
  assert.equal(queued.action, queueItem.action);
  assert.equal(queued.meta, "queued POST /api/runs/run-1/readiness-source-refs/refresh");
  assert.equal(queued.buttonLabel, "Dispatch Refresh");

  const direct = buildReadinessSourceRefGate({
    selectedId: "run-1",
    actionReadiness,
    readinessSourceRefs: staleProofPreview,
    operatorActionQueueItems: [],
  });
  assert.equal(direct.needed, true);
  assert.equal(direct.mode, "direct");
  assert.equal(direct.queueItem, undefined);
  assert.equal(direct.meta, "direct POST /api/runs/run-1/readiness-source-refs/refresh");
  assert.equal(direct.buttonLabel, "Refresh");

  const missingEvidenceFirst = buildReadinessSourceRefGate({
    selectedId: "run-1",
    actionReadiness: { issues: [], recommended_action: "Capture browser evidence first." },
    readinessSourceRefs: {
      status: "missing_source_evidence",
      missing_proof_ref_labels: ["browser"],
      missing_source_evidence_labels: ["browser"],
      recommended_action: "Capture browser source evidence first.",
    },
    operatorActionQueueItems: [],
  });
  assert.equal(missingEvidenceFirst.needed, false);
  assert.equal(missingEvidenceFirst.mode, "none");

  assert.match(appSource, /buildReadinessSourceRefGate/);
  assert.match(appSource, /readinessSourceRefGate\.needed/);
  assert.match(appSource, /<strong>Readiness Source Refs<\/strong>/);
  assert.match(appSource, /readinessSourceRefGate\.buttonLabel/);
  assert.match(appSource, /dispatchQueueItem\(selectedSourceRefQueueItem\)/);
  const queuedIndex = appSource.indexOf("dispatchQueueItem(selectedSourceRefQueueItem)");
  const directIndex = appSource.indexOf("/readiness-source-refs/refresh`, { method: \"POST\" }");
  assert.ok(queuedIndex > -1, "queued dispatch path is missing");
  assert.ok(directIndex > -1, "direct refresh fallback is missing");
  assert.ok(queuedIndex < directIndex, "queued operator dispatch must be tried before direct refresh fallback");

  console.log("readiness source-ref dashboard smoke passed");
} finally {
  await rm(tmp, { recursive: true, force: true });
}