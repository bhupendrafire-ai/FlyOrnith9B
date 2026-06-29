# FlyOrnith Benchmark Bug-Fix Log

Generated: 2026-06-29

This log records bugs found while running the FlyOrnith benchmark suite, plus the fix and verification for each one. The underlying benchmark evidence was captured before the visible-brand rename from AgentOrinth to FlyOrnith.

## BENCH-001: PowerShell Recursive Delete Was Not Flagged

Benchmark run: `data/benchmarks/benchmark-suite-20260629-092828`

Probe: `approval_safety_modes`

Symptom: `Remove-Item -Recurse C:\Windows` was classified as an allowed workspace command in non-`always_ask` modes.

Root cause: the destructive-command regex used `\b-Recurse\b`, but `-` is not a word character, so the word-boundary check failed before the dash.

Fix:

- Updated `backend/app/tools.py` to match `-Recurse` after start/whitespace.
- Added `test_powershell_recursive_remove_needs_approval` in `backend/tests/test_safety.py`.

Verification:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_safety.py -q
.\.venv\Scripts\python.exe tools\run_agentornith_benchmark_suite.py
```

Result: the safety probe passed `12/12` in the final benchmark.

## BENCH-002: Quality Endpoints Returned Stale Default Reports

Benchmark run: `data/benchmarks/benchmark-suite-20260629-092828`

Probe: `long_loop_handoff`

Symptom: `/api/runs/{run_id}/resume-quality` and `/api/runs/{run_id}/checkpoint-quality` returned empty/default report objects for the completed PPT run, even though the handoff and Obsidian checkpoint existed.

Root cause: the engine getters returned the stored report object directly. Older runs created before the quality reports were populated kept default state forever unless another path recomputed it.

Fix:

- Updated `AgentLoopEngine.get_resume_prompt_quality` to build and persist a fresh report from the current handoff.
- Updated `AgentLoopEngine.get_checkpoint_quality` to read the run note, build a fresh checkpoint-quality report, and persist it into run state/handoff.

Verification:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_api_restart.py::test_resume_quality_endpoint_scores_compact_handoff backend\tests\test_api_restart.py::test_checkpoint_quality_flows_into_handoff_timeline_and_replay -q
```

Result: checkpoint quality now reports `ready` for the final benchmark run.

## BENCH-003: Resume Goal Anchor Failed On Filenames

Benchmark run: live endpoint check after BENCH-002

Probe: `long_loop_handoff`

Symptom: resume quality reported `missing_goal_anchor` for a prompt that clearly contained the original goal `AgentOrnith_use_cases.pptx`.

Root cause: goal-anchor matching tokenized the goal, turning `AgentOrnith_use_cases.pptx` into `AgentOrnith_use_cases pptx`, then searched that normalized fragment inside the raw prompt text where the filename still contained a dot.

Fix:

- Updated `backend/app/resume_quality.py` so both prompt and goal are normalized before matching.
- Added `backend/tests/test_resume_quality.py` with a filename-punctuation regression.

Verification:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_resume_quality.py backend\tests\test_safety.py -q
```

Result: `has_goal_anchor` is now `true` for the completed PPT run.

## BENCH-004: Benchmark Fixture Reused Stale Python Bytecode

Benchmark run: `data/benchmarks/benchmark-suite-20260629-093755`

Probe: `tool_coding_loop`

Symptom: the benchmark patch changed `calc.py` from `return a - b` to `return a + b`, but the immediate second test run still returned the old behavior.

Root cause: the tiny fixture edited a same-size Python file inside the same timestamp window, letting Python reuse stale `__pycache__` bytecode.

Fix:

- Updated `tools/run_agentornith_benchmark_suite.py` to clear `__pycache__` after applying the patch and before rerunning tests.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile tools\run_agentornith_benchmark_suite.py
.\.venv\Scripts\python.exe tools\run_agentornith_benchmark_suite.py
```

Result: the tool-gated bugfix probe passed `12/12` in final run `data/benchmarks/benchmark-suite-20260629-093934`.

## Residual Finding

The final suite still leaves one intentional visible gap: `long_loop_handoff` scored `9/10` because resume-quality reports `critical_context_coverage` for the older completed run. The artifact run has a valid handoff and Obsidian checkpoint, but the context snapshot says required sections such as recent tools/events were omitted. This is useful evidence for the next harness improvement instead of a number to hide.

