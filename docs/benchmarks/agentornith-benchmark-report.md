# AgentOrinth Harness Benchmark Report

Generated: 2026-06-29

Final evidence run: `data/benchmarks/benchmark-suite-20260629-093934`

This benchmark compares the same local Ornith model in two modes:

- **AgentOrinth harness**: Ornith runs inside the milestone loop with audited tools, isolated workspace state, browser/web evidence, safety gates, checkpoints, replay, and dashboard supervision.
- **Raw command-line Ornith**: Ornith is called through the OpenAI-compatible chat endpoint with no filesystem API, no browser, no tool calls, no durable memory, and no checkpoint system.

## Headline Result

| System | Score | Result |
| --- | ---: | --- |
| AgentOrinth harness | 94/95 | Passed 8 of 9 harness probes completely; long-loop handoff scored 9/10 because context coverage still reported one critical omitted section on the older completed run. |
| Raw command-line Ornith | 6/15 | Produced useful instructions and a script, but created no artifact and had no durable tool evidence. |

## Benchmark Evidence

Live AgentOrinth run under test: `run-20260629-082817-b5e61c`

Benchmark deliverable: create `AgentOrnith_use_cases.pptx` with one overview slide plus five use-case slides explaining where AgentOrnith helps Ornith outperform simple command-line usage.

The harness run produced:

- A real `.pptx` artifact at `data/workspaces/run-20260629-082817-b5e61c/workspace/AgentOrnith_use_cases.pptx`.
- 6 verified slide XML files inside the PowerPoint package.
- 5/5 acceptance criteria verified.
- 38 recorded tool calls.
- 17 checkpoint events.
- 0 pending approvals at completion.

The raw Ornith baseline produced:

- 4,162 response characters.
- A useful Python script for a human to run.
- No `AgentOrnith_use_cases.pptx` artifact in the baseline workspace.
- No tool calls, acceptance evidence, browser evidence, checkpoint, or replay.

## Probe Results

| Probe | Score | Result |
| --- | ---: | --- |
| Live AgentOrinth artifact run | 15/15 | Real PPTX artifact created, validated, and tied to acceptance evidence. |
| Tool-gated bugfix loop | 12/12 | Harness wrote files, observed failing tests, applied a patch, cleared stale bytecode, and verified green tests. |
| Web, source, and browser tools | 12/12 | Web fetch/search returned source records and browser screenshot evidence was captured. |
| Safety gate and approval modes | 12/12 | Destructive/global/desktop/credential paths were classified correctly across approval modes. |
| Workspace isolation and diff proof | 10/10 | Isolated workspace diff was produced while the source project stayed unchanged. |
| Long-loop handoff and compact resume context | 9/10 | Handoff and Obsidian checkpoint are present; context coverage still reports one critical omitted section. |
| Tool failure capture and narrow recovery proof | 9/9 | Failed command return code and stderr/stdout were captured, then a narrow diagnostic succeeded. |
| Dashboard and persistent-run observability | 8/8 | API exposed persistent runs, enabled tool policy, and live frontend availability. |
| Multi-artifact delivery | 7/7 | Harness created and validated multiple coordinated workspace artifacts. |

## Bugs Found During Benchmarking

Separate log: `docs/benchmarks/benchmark-bugfix-log.md`

Fixed during benchmark execution:

- PowerShell destructive command detection missed `Remove-Item -Recurse`.
- Resume/checkpoint quality endpoints returned stale default reports for older runs.
- Resume goal-anchor matching failed when the goal contained filenames such as `AgentOrnith_use_cases.pptx`.
- The benchmark runner itself had a stale Python bytecode false negative in the tiny bugfix fixture.

## Current Interpretation

The proof is not that Ornith became smarter in isolation. The proof is that AgentOrinth gives Ornith the missing operating system around it: tools, safety, memory, verification, artifacts, and a supervised loop. Raw Ornith can often explain the work, but the harness can actually do the work and preserve evidence.

## Reproduce

```powershell
cd H:\AgentOrinth\agentic-coding-system
.\.venv\Scripts\python.exe tools\run_agentornith_benchmark_suite.py
```
