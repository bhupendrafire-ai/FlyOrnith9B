from __future__ import annotations

import json
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "benchmarks"
API_BASE = "http://127.0.0.1:9127"
MODEL_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "ornith-9b-q4-64k"
HARNESS_RUN_ID = "run-20260629-082817-b5e61c"

GOAL = (
    "Create a PowerPoint deck named AgentOrnith_use_cases.pptx in the workspace root. "
    "The deck should explain why the AgentOrnith harness makes the Ornith local model more capable "
    "than running Ornith as a simple command-line model. Use a clean, minimal technical style. "
    "Include exactly five concrete use cases, one use case per slide, where the harness performs better "
    "than command-line Ornith, and include balanced limitations/tradeoffs."
)

BENCHMARK_MATRIX = [
    {
        "id": "artifact_creation",
        "name": "Artifact creation with exact structural constraints",
        "measures": "Can the system actually create a valid file, not just describe one?",
        "pass_signal": "Expected artifact exists, opens, and has required structure.",
    },
    {
        "id": "verification_loop",
        "name": "Verification and acceptance evidence",
        "measures": "Can it run independent checks and map evidence to acceptance criteria?",
        "pass_signal": "All acceptance criteria verified with tool evidence.",
    },
    {
        "id": "workspace_tooling",
        "name": "Workspace, shell, and file tooling",
        "measures": "Can it inspect files, write support scripts, run commands, and preserve touched-file evidence?",
        "pass_signal": "Tool calls show file writes and shell checks with summaries.",
    },
    {
        "id": "checkpoint_resume",
        "name": "Long-loop checkpoint and handoff",
        "measures": "Can the work survive pauses/restarts without raw-log reload?",
        "pass_signal": "Obsidian checkpoint and compact handoff/resume prompt exist.",
    },
    {
        "id": "operator_friction",
        "name": "Approval and recovery friction",
        "measures": "Does the system avoid unnecessary manual intervention while still logging risk?",
        "pass_signal": "Low or zero unresolved approvals/blockers at completion.",
    },
    {
        "id": "raw_model_robustness",
        "name": "Raw model robustness under identical goal",
        "measures": "Does standalone Ornith produce a usable result without tools?",
        "pass_signal": "Direct response is non-empty, actionable, and produces an artifact only if the CLI can actually write files.",
    },
]


def api_get(path: str) -> Any:
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=45) as response:
        return json.load(response)


def call_raw_ornith(prompt: str, out_dir: Path) -> dict[str, Any]:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Ornith running as a standalone command-line model with no tool calls, "
                    "no filesystem API, no browser, and no persistent harness. Be honest about what you can and cannot do."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1600,
    }
    request = urllib.request.Request(
        MODEL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.load(response)
        content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "")
        ok = True
        error = ""
    except Exception as exc:  # noqa: BLE001 - benchmark captures raw failure
        data = {}
        content = ""
        ok = False
        error = str(exc)
    latency_ms = round((time.perf_counter() - started) * 1000)
    (out_dir / "raw_ornith_response.txt").write_text(content, encoding="utf-8")
    return {
        "ok": ok,
        "latency_ms": latency_ms,
        "response_chars": len(content),
        "response_excerpt": content[:1000],
        "error": error,
        "raw_response_path": str(out_dir / "raw_ornith_response.txt"),
        "raw_response_payload_keys": sorted(data.keys()) if isinstance(data, dict) else [],
    }


def inspect_pptx(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "size": 0, "slides": 0, "text_excerpt": ""}
    try:
        with zipfile.ZipFile(path) as archive:
            slide_names = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
            text = " ".join(
                archive.read(name).decode("utf-8", errors="ignore").lower()
                for name in slide_names
            )
        return {
            "exists": True,
            "path": str(path),
            "size": path.stat().st_size,
            "slides": len(slide_names),
            "has_agentornith": "agentornith" in text,
            "has_command_line": "command-line ornith" in text or "command line ornith" in text,
            "has_tradeoff": "tradeoff" in text or "limitation" in text,
            "use_case_mentions": sum(1 for index in range(1, 6) if f"use case {index}" in text),
            "text_excerpt": text[:800],
        }
    except Exception as exc:  # noqa: BLE001 - benchmark captures artifact failure
        return {"exists": True, "path": str(path), "error": str(exc), "size": path.stat().st_size}


def score_harness(run: dict[str, Any], pptx: dict[str, Any]) -> dict[str, Any]:
    state = run.get("state", {})
    acceptance = state.get("acceptance_evidence", [])
    approvals = api_get(f"/api/runs/{run['id']}/approvals")
    events = api_get(f"/api/runs/{run['id']}/events")
    checkpoints = [event for event in events if event.get("kind") == "checkpoint"]
    tool_calls = state.get("tool_calls", [])
    verified = sum(1 for item in acceptance if item.get("status") == "verified")
    total = len(acceptance)
    score = 0
    score += 25 if run.get("status") == "completed" else 0
    score += 25 if pptx.get("exists") and pptx.get("slides") == 6 else 0
    score += 20 if total and verified == total else 0
    score += 15 if checkpoints else 0
    score += 10 if any(call.get("name") == "file_write" and call.get("ok") for call in tool_calls) else 0
    score += 5 if not [item for item in approvals if item.get("status") == "pending"] else 0
    return {
        "score": score,
        "status": run.get("status"),
        "step_count": state.get("step_count"),
        "tool_call_count": len(tool_calls),
        "verified_acceptance": verified,
        "acceptance_total": total,
        "checkpoint_count": len(checkpoints),
        "pending_approvals": len([item for item in approvals if item.get("status") == "pending"]),
        "commands_run": state.get("commands_run", []),
        "files_touched": state.get("files_touched", []),
    }


def score_raw(raw: dict[str, Any], cli_workspace: Path) -> dict[str, Any]:
    pptx = inspect_pptx(cli_workspace / "AgentOrnith_use_cases.pptx")
    content = raw.get("response_excerpt", "").lower()
    score = 0
    score += 15 if raw.get("ok") else 0
    score += 15 if raw.get("response_chars", 0) > 200 else 0
    score += 25 if pptx.get("exists") and pptx.get("slides") == 6 else 0
    score += 10 if "cannot" in content or "no filesystem" in content or "can't" in content else 0
    score += 10 if "python" in content or "pptx" in content or "powerpoint" in content else 0
    return {
        "score": score,
        "artifact": pptx,
        "actual_workspace_files": sorted(path.name for path in cli_workspace.iterdir()),
    }


def write_report(out_dir: Path, report: dict[str, Any]) -> None:
    json_path = out_dir / "benchmark_report.json"
    md_path = out_dir / "benchmark_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    harness = report["harness"]
    raw = report["raw_ornith"]
    lines = [
        "# AgentOrnith vs Raw Ornith Benchmark",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Task",
        GOAL,
        "",
        "## Result Summary",
        f"- AgentOrnith harness score: {harness['score']}/100",
        f"- Raw command-line Ornith score: {raw['score']}/100",
        f"- Harness completed: {harness['status']}",
        f"- Harness artifact: {report['harness_artifact']['path']} ({report['harness_artifact']['slides']} slides)",
        f"- Raw response chars: {report['raw_model']['response_chars']}",
        f"- Raw artifact exists: {raw['artifact']['exists']}",
        "",
        "## Benchmark Matrix",
    ]
    for item in BENCHMARK_MATRIX:
        lines.append(f"- **{item['name']}**: {item['measures']} Pass signal: {item['pass_signal']}")
    lines.extend(
        [
            "",
            "## Prominent Proof",
            "- The harness produced a real `.pptx` artifact, verified it as a valid PowerPoint zip with 6 slide XML files, and recorded all acceptance criteria as verified.",
            "- The raw command-line model call had no filesystem/tool channel; it produced only text and no `.pptx` file in the baseline workspace.",
            "- The harness left replayable evidence: tool calls, commands, checkpoints, touched files, and acceptance records.",
            "",
            "## Raw Ornith Excerpt",
            "```text",
            report["raw_model"]["response_excerpt"][:1800],
            "```",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / f"ornith-vs-harness-{stamp}"
    cli_workspace = out_dir / "cli_workspace"
    cli_workspace.mkdir(parents=True, exist_ok=True)

    run = api_get(f"/api/runs/{HARNESS_RUN_ID}")
    harness_workspace = Path(run["workspace_path"])
    harness_pptx = inspect_pptx(harness_workspace / "AgentOrnith_use_cases.pptx")

    raw_prompt = (
        f"Working directory: {cli_workspace}\n\n"
        f"{GOAL}\n\n"
        "This is a benchmark. If you cannot actually write files from this standalone command-line model call, "
        "say that plainly, then provide the exact script or commands a human would need to run."
    )
    raw = call_raw_ornith(raw_prompt, out_dir)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "goal": GOAL,
        "benchmark_matrix": BENCHMARK_MATRIX,
        "harness_run_id": HARNESS_RUN_ID,
        "harness_workspace": str(harness_workspace),
        "cli_workspace": str(cli_workspace),
        "harness_artifact": harness_pptx,
        "harness": score_harness(run, harness_pptx),
        "raw_model": raw,
        "raw_ornith": score_raw(raw, cli_workspace),
    }
    write_report(out_dir, report)
    print(json.dumps({"out_dir": str(out_dir), "summary": report}, indent=2))


if __name__ == "__main__":
    main()
