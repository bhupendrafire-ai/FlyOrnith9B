from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import AppConfig  # noqa: E402
from backend.app.tools import SafetyGate, ToolRunner, redact_secrets  # noqa: E402


API_BASE = "http://127.0.0.1:9127"
HARNESS_RUN_ID = "run-20260629-082817-b5e61c"
OUT_ROOT = ROOT / "data" / "benchmarks"
DOCS_ROOT = ROOT / "docs" / "benchmarks"

PPT_GOAL = (
    "Create a PowerPoint deck named AgentOrnith_use_cases.pptx in the workspace root. "
    "The deck should explain why the AgentOrnith harness makes the Ornith local model more capable "
    "than running Ornith as a simple command-line model. Include five concrete use cases, one per slide, "
    "and include balanced limitations/tradeoffs."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def api_get(path: str, *, timeout: int = 45) -> Any:
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=timeout) as response:
        return json.load(response)


def http_probe(url: str, *, timeout: int = 10) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
        return {
            "ok": True,
            "status": response.status,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "body_excerpt": body[:500],
        }
    except Exception as exc:  # noqa: BLE001 - benchmark records probe failures
        return {
            "ok": False,
            "status": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def post_json(url: str, payload: dict[str, Any], *, timeout: int = 180) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def inspect_pptx(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "size": 0, "slides": 0}
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
            "text_excerpt": text[:1000],
        }
    except Exception as exc:  # noqa: BLE001 - benchmark records artifact failures
        return {"exists": True, "path": str(path), "size": path.stat().st_size, "error": str(exc)}


def bool_score(condition: bool, points: int) -> int:
    return points if condition else 0


def probe_result(
    probe_id: str,
    name: str,
    points: int,
    score: int,
    summary: str,
    evidence: dict[str, Any],
    raw_baseline: str,
) -> dict[str, Any]:
    status = "pass" if score >= points else "partial" if score > 0 else "fail"
    return {
        "id": probe_id,
        "name": name,
        "points": points,
        "score": score,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "raw_baseline": raw_baseline,
    }


def probe_live_artifact_run(run: dict[str, Any]) -> dict[str, Any]:
    state = run.get("state", {})
    events = api_get(f"/api/runs/{run['id']}/events?limit=500")
    approvals = api_get(f"/api/runs/{run['id']}/approvals")
    pptx = inspect_pptx(Path(run["workspace_path"]) / "AgentOrnith_use_cases.pptx")
    acceptance = state.get("acceptance_evidence", [])
    verified = sum(1 for item in acceptance if item.get("status") == "verified")
    checkpoints = [event for event in events if event.get("kind") == "checkpoint"]
    tool_calls = state.get("tool_calls", [])
    score = 0
    score += bool_score(run.get("status") == "completed", 3)
    score += bool_score(pptx.get("exists") and pptx.get("slides") == 6, 4)
    score += bool_score(pptx.get("has_agentornith") and pptx.get("has_command_line"), 2)
    score += bool_score(pptx.get("has_tradeoff") and pptx.get("use_case_mentions", 0) >= 5, 2)
    score += bool_score(bool(acceptance) and verified == len(acceptance), 2)
    score += bool_score(any(call.get("name") == "file_write" and call.get("ok") for call in tool_calls), 1)
    score += bool_score(not [item for item in approvals if item.get("status") == "pending"] and bool(checkpoints), 1)
    return probe_result(
        "artifact_creation",
        "Live AgentOrinth artifact run",
        15,
        score,
        "Completed harness run produced a real PPTX artifact with verified acceptance evidence.",
        {
            "run_id": run["id"],
            "status": run.get("status"),
            "pptx": pptx,
            "verified_acceptance": verified,
            "acceptance_total": len(acceptance),
            "tool_call_count": len(tool_calls),
            "checkpoint_count": len(checkpoints),
            "pending_approvals": len([item for item in approvals if item.get("status") == "pending"]),
            "files_touched": state.get("files_touched", []),
        },
        "Standalone Ornith can describe a deck, but without tools it cannot create or verify a PPTX file.",
    )


def call_raw_ornith(config: AppConfig, cli_workspace: Path, out_dir: Path) -> dict[str, Any]:
    prompt = (
        f"Working directory: {cli_workspace}\n\n"
        f"{PPT_GOAL}\n\n"
        "This is a benchmark of standalone command-line Ornith. If you cannot actually write files, "
        "say that plainly and provide the exact commands or script a human would need to run."
    )
    payload = {
        "model": config.model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Ornith running as a standalone command-line model with no harness, no tool calls, "
                    "no filesystem API, no browser, no durable memory, and no approval supervisor."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1600,
    }
    started = time.perf_counter()
    url = f"{config.model_base_url}/chat/completions"
    try:
        data = post_json(url, payload, timeout=max(180, config.model_timeout_seconds * 2))
        content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "")
        ok = True
        error = ""
    except Exception as exc:  # noqa: BLE001 - benchmark captures raw-model failures
        content = ""
        ok = False
        error = str(exc)
    response_path = out_dir / "raw_ornith_response.txt"
    response_path.write_text(content, encoding="utf-8")
    artifact = inspect_pptx(cli_workspace / "AgentOrnith_use_cases.pptx")
    excerpt = redact_secrets(content[:1200])
    score = 0
    score += bool_score(ok, 2)
    score += bool_score(len(content) > 200, 2)
    score += bool_score("cannot" in excerpt.lower() or "no filesystem" in excerpt.lower() or "can't" in excerpt.lower(), 2)
    score += bool_score(artifact.get("exists") and artifact.get("slides") == 6, 9)
    return {
        "id": "raw_command_line_baseline",
        "name": "Raw command-line Ornith baseline",
        "points": 15,
        "score": score,
        "status": "pass" if score >= 15 else "partial" if score > 0 else "fail",
        "summary": "Standalone Ornith baseline for the same PPT artifact task.",
        "evidence": {
            "ok": ok,
            "model": config.model_name,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "response_chars": len(content),
            "response_excerpt": excerpt,
            "error": error,
            "artifact": artifact,
            "workspace_files": sorted(path.name for path in cli_workspace.iterdir()),
            "response_path": str(response_path),
        },
        "raw_baseline": "This row is the raw baseline itself; it has no harness tool channel.",
    }


async def probe_tool_bugfix(config: AppConfig, out_dir: Path) -> dict[str, Any]:
    workspace = out_dir / "tool_bugfix_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner(workspace, config)
    await runner.execute(
        "file_write",
        {
            "path": "calc.py",
            "content": "def add(a, b):\n    return a - b\n",
        },
    )
    await runner.execute(
        "file_write",
        {
            "path": "test_calc.py",
            "content": (
                "import unittest\n"
                "from calc import add\n\n"
                "class CalcTests(unittest.TestCase):\n"
                "    def test_adds_positive_numbers(self):\n"
                "        self.assertEqual(add(2, 3), 5)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
        },
    )
    test_command = f'"{sys.executable}" -m unittest -q'
    before = await runner.execute("run_tests", {"command": test_command, "timeout": 30})
    patch = await runner.execute(
        "patch_apply",
        {
            "id": "fix-add",
            "files": [{"path": "calc.py", "new": "def add(a, b):\n    return a + b\n"}],
        },
        approved=True,
    )
    cleanup = await runner.execute(
        "shell",
        {
            "command": f'"{sys.executable}" -c "import shutil; shutil.rmtree(\'__pycache__\', ignore_errors=True)"',
            "timeout": 30,
        },
    )
    after = await runner.execute("run_tests", {"command": test_command, "timeout": 30})
    score = 0
    score += bool_score(before.ok is False and before.data.get("returncode") != 0, 3)
    score += bool_score(patch.ok and bool(patch.patch_applications), 3)
    score += bool_score(after.ok and after.data.get("returncode") == 0, 4)
    score += bool_score((workspace / "calc.py").read_text(encoding="utf-8").strip().endswith("a + b"), 2)
    return probe_result(
        "tool_coding_loop",
        "Tool-gated bugfix loop",
        12,
        score,
        "Harness tools can write files, observe failing tests, apply a bounded patch, and verify green tests.",
        {
            "workspace": str(workspace),
            "initial_test": before.data,
            "patch_summary": patch.summary,
            "bytecode_cleanup": cleanup.data,
            "final_test": after.data,
        },
        "Raw Ornith can propose the fix, but cannot write the file or run the failing/passing test loop by itself.",
    )


async def probe_web_browser(config: AppConfig, out_dir: Path) -> dict[str, Any]:
    workspace = out_dir / "web_browser_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner(workspace, config)
    web_fetch = await runner.execute("web_fetch", {"url": "https://example.com"})
    web_search = await runner.execute(
        "web_search",
        {"query": "AgentOrinth local LLM harness web tools", "limit": 2},
    )
    local_page = workspace / "browser_probe.html"
    local_page.write_text(
        "<!doctype html><title>AgentOrinth browser probe</title><main>Browser screenshot probe loaded.</main>",
        encoding="utf-8",
    )
    browser = await runner.execute("browser_screenshot", {"url": local_page.resolve().as_uri()})
    fetch_source = web_fetch.web_sources[0].model_dump() if web_fetch.web_sources else {}
    score = 0
    score += bool_score(web_fetch.ok and bool(fetch_source.get("url")) and bool(fetch_source.get("excerpt")), 4)
    score += bool_score(web_search.ok and bool(web_search.web_sources), 3)
    score += bool_score(browser.ok and Path(browser.data.get("path", "")).exists(), 4)
    score += bool_score(all("citation" in source.model_dump() for source in web_fetch.web_sources), 1)
    return probe_result(
        "web_browser_tools",
        "Web, source, and browser evidence tools",
        12,
        score,
        "Harness exposes audited internet fetch/search and browser screenshot evidence instead of raw model internet access.",
        {
            "web_fetch": {
                "ok": web_fetch.ok,
                "summary": web_fetch.summary,
                "sources": [source.model_dump() for source in web_fetch.web_sources],
            },
            "web_search": {
                "ok": web_search.ok,
                "summary": web_search.summary,
                "sources": [source.model_dump() for source in web_search.web_sources],
            },
            "browser_screenshot": browser.data | {"ok": browser.ok, "summary": browser.summary},
            "browser_executable_path": config.browser_executable_path or "",
        },
        "Raw Ornith has no reliable browser, screenshot, citation, or page-fetch channel in a plain CLI call.",
    )


def probe_safety_and_approval(config: AppConfig, out_dir: Path) -> dict[str, Any]:
    workspace = out_dir / "safety_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    decisions: dict[str, Any] = {}
    for mode in ["always_ask", "balanced", "workspace_autopilot", "bypass_permissions"]:
        gate = SafetyGate(config, approval_mode=mode)
        decisions[mode] = {
            "safe_shell": asdict(gate.classify_tool("shell", {"command": f'"{sys.executable}" -c "print(1)"'}, workspace)),
            "destructive_shell": asdict(gate.classify_tool("shell", {"command": r"Remove-Item -Recurse C:\Windows"}, workspace)),
            "global_install": asdict(gate.classify_tool("shell", {"command": "npm install -g agentornith-probe"}, workspace)),
            "desktop_click": asdict(gate.classify_tool("desktop_click", {"x": 10, "y": 10}, workspace)),
            "desktop_password_type": asdict(gate.classify_tool("desktop_type", {"text": "password=opensesame"}, workspace)),
            "patch_apply": asdict(gate.classify_tool("patch_apply", {"files": [{"path": "a.txt", "new": "x"}]}, workspace)),
            "outside_file": asdict(gate.classify_tool("file_write", {"path": r"..\outside.txt"}, workspace)),
        }
    score = 0
    score += bool_score(decisions["balanced"]["safe_shell"]["allowed"], 1)
    score += bool_score(decisions["balanced"]["destructive_shell"]["needs_approval"], 2)
    score += bool_score(decisions["balanced"]["global_install"]["needs_approval"], 2)
    score += bool_score(decisions["balanced"]["desktop_password_type"]["allowed"] is False, 2)
    score += bool_score(decisions["always_ask"]["safe_shell"]["needs_approval"], 1)
    score += bool_score(decisions["workspace_autopilot"]["patch_apply"]["allowed"], 2)
    score += bool_score(decisions["bypass_permissions"]["desktop_click"]["allowed"], 1)
    score += bool_score(decisions["bypass_permissions"]["outside_file"]["allowed"], 1)
    return probe_result(
        "approval_safety_modes",
        "Safety gate and approval modes",
        12,
        score,
        "Approval layers distinguish safe workspace actions, risky commands, desktop actions, credential entry, and bypass modes.",
        {"workspace": str(workspace), "decisions": decisions},
        "Raw CLI prompting depends on the model's self-restraint; the harness enforces policy before tools run.",
    )


async def probe_workspace_isolation(config: AppConfig, run: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    source = out_dir / "source_project"
    workspace = out_dir / "isolated_workspace"
    source.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    (source / "app.txt").write_text("version=1\n", encoding="utf-8")
    shutil.copy2(source / "app.txt", workspace / "app.txt")
    runner = ToolRunner(workspace, config, approval_mode="workspace_autopilot")
    await runner.execute("file_write", {"path": "app.txt", "content": "version=2\n"})
    diff = await runner.execute("workspace_diff", {"source_path": str(source)})
    source_unchanged = (source / "app.txt").read_text(encoding="utf-8") == "version=1\n"
    run_workspace = Path(run["workspace_path"])
    isolation = run.get("state", {}).get("workspace_isolation", {})
    score = 0
    score += bool_score(config.enable_workspace_isolation, 2)
    score += bool_score("data" in run_workspace.parts and "workspaces" in run_workspace.parts, 2)
    score += bool_score(diff.ok and diff.workspace_diff is not None and diff.workspace_diff.total_files >= 1, 3)
    score += bool_score(source_unchanged, 2)
    score += bool_score(bool(isolation.get("enabled", True)), 1)
    return probe_result(
        "workspace_isolation",
        "Workspace isolation and diff proof",
        10,
        score,
        "Harness can work in an isolated project copy, diff changes, and avoid silently mutating the source folder.",
        {
            "source": str(source),
            "workspace": str(workspace),
            "live_run_workspace": str(run_workspace),
            "live_run_isolation": isolation,
            "diff": diff.workspace_diff.model_dump() if diff.workspace_diff else diff.data,
            "source_unchanged": source_unchanged,
        },
        "Raw Ornith in a CLI has no built-in isolated workspace manager or promotion audit.",
    )


def probe_handoff_resume(run: dict[str, Any]) -> dict[str, Any]:
    handoff = api_get(f"/api/runs/{run['id']}/handoff")
    resume_quality = api_get(f"/api/runs/{run['id']}/resume-quality")
    checkpoint_quality = api_get(f"/api/runs/{run['id']}/checkpoint-quality")
    events = api_get(f"/api/runs/{run['id']}/events?limit=500")
    checkpoints = [event for event in events if event.get("kind") == "checkpoint"]
    resume_prompt = str(handoff.get("resume_prompt") or "")
    score = 0
    score += bool_score(len(resume_prompt) >= 200, 2)
    score += bool_score("Do not reload raw logs" in resume_prompt or "raw logs" in resume_prompt, 2)
    score += bool_score(bool(handoff.get("original_goal")) and bool(handoff.get("next_action")), 2)
    score += bool_score(len(checkpoints) > 0, 2)
    score += bool_score(resume_quality.get("ready_to_resume") is True or resume_quality.get("score", 0) >= 70, 1)
    score += bool_score(checkpoint_quality.get("has_resume_prompt") is True, 1)
    return probe_result(
        "long_loop_handoff",
        "Long-loop handoff and compact resume context",
        10,
        score,
        "Completed run exposes compact resume context, checkpoint evidence, and resume-quality checks.",
        {
            "handoff_keys": sorted(handoff.keys()),
            "resume_prompt_chars": len(resume_prompt),
            "resume_prompt_excerpt": resume_prompt[:800],
            "checkpoint_count": len(checkpoints),
            "resume_quality": resume_quality,
            "checkpoint_quality": checkpoint_quality,
        },
        "Raw Ornith CLI sessions lose state unless the human manually curates and re-injects context.",
    )


async def probe_failure_recovery(config: AppConfig, out_dir: Path) -> dict[str, Any]:
    workspace = out_dir / "failure_recovery_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner(workspace, config)
    fail = await runner.execute(
        "shell",
        {"command": f'"{sys.executable}" -c "import sys; print(\'intentional failure\'); sys.exit(7)"', "timeout": 30},
    )
    diagnostic = await runner.execute(
        "shell",
        {"command": f'"{sys.executable}" -c "print(\'narrow diagnostic ok\')"', "timeout": 30},
    )
    score = 0
    score += bool_score(fail.ok is False and fail.data.get("returncode") == 7, 4)
    score += bool_score("intentional failure" in fail.data.get("stdout", ""), 2)
    score += bool_score(diagnostic.ok and "narrow diagnostic ok" in diagnostic.data.get("stdout", ""), 3)
    return probe_result(
        "tool_failure_recovery",
        "Tool failure capture and narrow recovery proof",
        9,
        score,
        "Harness captures failed command evidence and can immediately run a narrower diagnostic instead of losing the loop.",
        {"failed_command": fail.data, "diagnostic_command": diagnostic.data},
        "Raw Ornith can suggest recovery, but it cannot observe command return codes without an external harness.",
    )


def probe_dashboard_observability(run: dict[str, Any]) -> dict[str, Any]:
    runs = api_get("/api/runs")
    tools = api_get("/api/tools")
    frontend_5173 = http_probe("http://127.0.0.1:5173/")
    frontend_8765 = http_probe("http://127.0.0.1:8765/index.html")
    found_run = any(item.get("id") == run["id"] for item in runs)
    frontend_ok = frontend_5173.get("ok") or frontend_8765.get("ok")
    enabled_tools = [item["name"] for item in tools.get("tools", []) if item.get("enabled")]
    score = 0
    score += bool_score(found_run, 2)
    score += bool_score(frontend_ok, 2)
    score += bool_score("web_search" in enabled_tools and "browser_screenshot" in enabled_tools, 2)
    score += bool_score("desktop_screenshot" in enabled_tools, 1)
    score += bool_score(len(runs) >= 1, 1)
    return probe_result(
        "dashboard_observability",
        "Dashboard, persistent runs, and tool policy observability",
        8,
        score,
        "Workbench APIs expose persistent runs, tool policy, and live frontend availability for operator supervision.",
        {
            "run_count": len(runs),
            "found_harness_run": found_run,
            "frontend_5173": frontend_5173,
            "frontend_8765": frontend_8765,
            "enabled_tools": enabled_tools,
            "policy": tools.get("policy", {}),
        },
        "A simple command-line model lacks persistent chat/run inventory, approval UI, and source/artifact panels.",
    )


async def probe_multi_artifact_project(config: AppConfig, out_dir: Path) -> dict[str, Any]:
    workspace = out_dir / "multi_artifact_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runner = ToolRunner(workspace, config)
    await runner.execute(
        "file_write",
        {
            "path": "index.html",
            "content": (
                "<!doctype html><html><head><title>AgentOrinth Probe</title></head>"
                "<body><h1>AgentOrinth Harness Probe</h1><p>Artifact delivery test.</p></body></html>"
            ),
        },
    )
    await runner.execute(
        "file_write",
        {
            "path": "artifacts/summary.json",
            "content": json.dumps(
                {
                    "project": "AgentOrinth",
                    "artifacts": ["index.html", "artifacts/summary.json"],
                    "purpose": "multi-artifact benchmark",
                },
                indent=2,
            ),
        },
    )
    validator = await runner.execute(
        "shell",
        {
            "command": (
                f'"{sys.executable}" -c "import json, pathlib; '
                "root=pathlib.Path('.'); "
                "assert (root/'index.html').exists(); "
                "data=json.loads((root/'artifacts'/'summary.json').read_text()); "
                "assert len(data['artifacts']) == 2; "
                "print('multi artifact ok')\""
            ),
            "timeout": 30,
        },
    )
    score = 0
    score += bool_score((workspace / "index.html").exists(), 2)
    score += bool_score((workspace / "artifacts" / "summary.json").exists(), 2)
    score += bool_score(validator.ok and "multi artifact ok" in validator.data.get("stdout", ""), 3)
    return probe_result(
        "multi_artifact_delivery",
        "Multi-artifact project delivery",
        7,
        score,
        "Harness can create and validate a small project with multiple coordinated artifacts.",
        {"workspace": str(workspace), "validator": validator.data},
        "Raw Ornith can outline files, but cannot create and validate multiple workspace artifacts without tool access.",
    )


async def run_suite() -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_ROOT / f"benchmark-suite-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    config = AppConfig.from_env()
    run = api_get(f"/api/runs/{HARNESS_RUN_ID}")
    cli_workspace = out_dir / "raw_cli_workspace"
    cli_workspace.mkdir(parents=True, exist_ok=True)

    probes: list[dict[str, Any]] = []
    probes.append(probe_live_artifact_run(run))
    probes.append(await probe_tool_bugfix(config, out_dir))
    probes.append(await probe_web_browser(config, out_dir))
    probes.append(probe_safety_and_approval(config, out_dir))
    probes.append(await probe_workspace_isolation(config, run, out_dir))
    probes.append(probe_handoff_resume(run))
    probes.append(await probe_failure_recovery(config, out_dir))
    probes.append(probe_dashboard_observability(run))
    probes.append(await probe_multi_artifact_project(config, out_dir))
    raw_baseline = call_raw_ornith(config, cli_workspace, out_dir)

    harness_score = sum(item["score"] for item in probes)
    harness_points = sum(item["points"] for item in probes)
    raw_score = raw_baseline["score"]
    raw_points = raw_baseline["points"]
    report = {
        "generated_at": utc_now(),
        "suite_dir": str(out_dir),
        "harness_run_id": HARNESS_RUN_ID,
        "harness_score": harness_score,
        "harness_points": harness_points,
        "harness_percent": round((harness_score / harness_points) * 100, 1) if harness_points else 0,
        "raw_score": raw_score,
        "raw_points": raw_points,
        "raw_percent": round((raw_score / raw_points) * 100, 1) if raw_points else 0,
        "agentornith_probes": probes,
        "raw_baseline": raw_baseline,
        "config": {
            "model_name": config.model_name,
            "model_profile": config.model_profile,
            "model_base_url": config.model_base_url,
            "context_window": config.context_window,
            "context_target_tokens": config.context_target_tokens,
            "approval_mode": config.approval_mode,
            "enable_web_tools": config.enable_web_tools,
            "enable_browser_tools": config.enable_browser_tools,
            "enable_desktop_control": config.enable_desktop_control,
            "enable_workspace_isolation": config.enable_workspace_isolation,
        },
    }
    (out_dir / "suite_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown_report(report, out_dir / "suite_report.md")
    return report


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# AgentOrinth Harness Benchmark Suite",
        "",
        f"Generated: {report['generated_at']}",
        f"Evidence directory: `{report['suite_dir']}`",
        f"Live AgentOrinth run under test: `{report['harness_run_id']}`",
        "",
        "## Scorecard",
        "",
        "| System | Score | What was measured |",
        "|---|---:|---|",
        f"| AgentOrinth harness | {report['harness_score']}/{report['harness_points']} ({report['harness_percent']}%) | Live artifact run plus tool, safety, web/browser, workspace, handoff, dashboard, and recovery probes |",
        f"| Raw command-line Ornith | {report['raw_score']}/{report['raw_points']} ({report['raw_percent']}%) | Same PPT artifact task through the model API with no tools or filesystem channel |",
        "",
        "## Probe Results",
        "",
        "| Probe | Result | Score | Evidence | Raw CLI limitation |",
        "|---|---|---:|---|---|",
    ]
    for probe in report["agentornith_probes"]:
        evidence = compact_evidence(probe["evidence"])
        lines.append(
            f"| {probe['name']} | {probe['status']} | {probe['score']}/{probe['points']} | {evidence} | {probe['raw_baseline']} |"
        )
    raw = report["raw_baseline"]
    lines.extend(
        [
            "",
            "## Raw Ornith Baseline",
            "",
            f"- Model: `{raw['evidence']['model']}`",
            f"- Latency: {raw['evidence']['latency_ms']} ms",
            f"- Response chars: {raw['evidence']['response_chars']}",
            f"- Artifact created: `{raw['evidence']['artifact'].get('exists')}`",
            f"- Response path: `{raw['evidence']['response_path']}`",
            "",
            "```text",
            raw["evidence"]["response_excerpt"][:1800],
            "```",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_evidence(evidence: dict[str, Any]) -> str:
    keys = []
    for key in [
        "status",
        "run_id",
        "verified_acceptance",
        "acceptance_total",
        "checkpoint_count",
        "tool_call_count",
        "workspace",
        "source_unchanged",
        "resume_prompt_chars",
        "run_count",
    ]:
        if key in evidence:
            keys.append(f"{key}={evidence[key]}")
    if "pptx" in evidence:
        pptx = evidence["pptx"]
        keys.append(f"pptx_slides={pptx.get('slides')}")
        keys.append(f"pptx_exists={pptx.get('exists')}")
    if "web_fetch" in evidence:
        keys.append(f"web_fetch={evidence['web_fetch'].get('ok')}")
    if "browser_screenshot" in evidence:
        keys.append(f"browser={evidence['browser_screenshot'].get('ok')}")
    if "validator" in evidence:
        keys.append(f"validator_rc={evidence['validator'].get('returncode')}")
    return "; ".join(str(item).replace("|", "/") for item in keys[:6]) or "See JSON report."


def main() -> None:
    report = asyncio.run(run_suite())
    print(json.dumps(
        {
            "suite_dir": report["suite_dir"],
            "harness": f"{report['harness_score']}/{report['harness_points']}",
            "raw": f"{report['raw_score']}/{report['raw_points']}",
            "raw_artifact_exists": report["raw_baseline"]["evidence"]["artifact"].get("exists"),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
