from __future__ import annotations

from pathlib import Path

from app.action_context import build_action_context_pack
from app.acceptance import infer_required_labels
from app.artifact_verification import artifact_verification_command, expected_artifact_suffix
from app.context_compiler import ContextCompiler
from app.memory import MemoryContext
from app.persistence import RunStore
from app.promotion_repair import build_promotion_repair_report
from app.repo_map import build_repo_map
from app.schemas import (
    ActionContextPack,
    ActionReadinessDecisionRecord,
    ActionReadinessDecisionReport,
    ActionReadinessReport,
    ApprovalReviewSummary,
    CheckpointQualityReport,
    CheckpointQualityResumeRecord,
    CheckpointQualityResumeReport,
    OperatorApprovalHistory,
    AcceptanceCriterionEvidence,
    AcceptanceEvidenceRecommendation,
    GoalEvolutionDecisionRecord,
    GoalEvolutionReport,
    GitCheckpointReport,
    OperatorDispatchLedgerEntry,
    OperatorDispatchLedgerReport,
    OrnithLaunchChecklistReport,
    OrnithPreflightActionLedgerEntry,
    OrnithPreflightActionLedgerReport,
    PostActionRetryDecisionRecord,
    PostActionRetryReport,
    PatchApplication,
    PatchProposal,
    PromotionAuditReport,
    PromotionVerificationAttemptRecord,
    PromotionVerificationReport,
    AcceptanceRecommendationTrace,
    RecoveryDecisionRecord,
    RecoveryDecisionReport,
    ReportIntegrityRefreshRecord,
    ReportIntegrityReport,
    ResumeDecisionRecord,
    ResumeDecisionReport,
    ReadinessSourceRefPreviewReport,
    SourceEvidencePreviewEntry,
    SourceEvidencePreviewReport,
    RunHealthReport,
    ToolCallRecord,
    VerificationOutcomeRecord,
    VerificationOutcomeReport,
)


def test_repo_map_discovers_manifests_and_commands(tmp_path: Path) -> None:
    (tmp_path / "frontend").mkdir()
    (tmp_path / "README.md").write_text("# Demo", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest", encoding="utf-8")
    (tmp_path / "frontend" / "package.json").write_text(
        '{"scripts":{"build":"vite build","test":"vitest"}}',
        encoding="utf-8",
    )

    repo_map = build_repo_map(tmp_path)

    assert "README.md" in repo_map.manifests
    assert repo_map.package_scripts["build"] == "vite build"
    assert "npm --prefix frontend run test" in repo_map.test_commands
    assert "python -m pytest" in repo_map.test_commands


def test_repo_map_ignores_data_only_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "data" / "workspaces" / "run-1" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("# Demo", encoding="utf-8")
    (workspace / "app.py").write_text("print('ok')\n", encoding="utf-8")

    repo_map = build_repo_map(workspace)

    assert "README.md" in repo_map.manifests
    assert repo_map.languages["markdown"] == 1
    assert repo_map.languages["python"] == 1


def test_artifact_verification_prefers_pptx_existence_check(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        "Create a PPT deck explaining AgentOrinth with five use cases.",
        "Deck",
        str(tmp_path),
        ["A PowerPoint deck exists with one title slide and five use-case slides."],
    )

    command = artifact_verification_command(run, run.state, run.state.acceptance_criteria[0])

    assert "*.pptx" in command
    assert "ppt/slides/slide" in command
    assert "npm run build" not in command


def test_artifact_verification_checks_pptx_content_when_criterion_requires_it(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        "Create AgentOrnith_use_cases.pptx.",
        "Deck",
        str(tmp_path),
        ["Each use-case slide compares AgentOrnith harness behavior against simple command-line Ornith and includes tradeoffs."],
    )

    command = artifact_verification_command(run, run.state, run.state.acceptance_criteria[0])

    assert "use case %s" in command
    assert "agentornith harness" in command
    assert "command-line ornith" in command
    assert "tradeoff" in command


def test_artifact_acceptance_words_require_verification() -> None:
    assert infer_required_labels("The deck contains exactly six slides.") == ["verification"]
    assert infer_required_labels("The deck includes honest tradeoffs.") == ["verification"]


def test_local_web_app_acceptance_uses_browser_not_internet_search() -> None:
    assert infer_required_labels("Web app runs locally in the browser with one command and loads without errors.") == ["browser"]
    assert infer_required_labels("Latest web source and dashboard screenshot") == ["browser", "web"]


def test_runner_slide_controls_do_not_trigger_pptx_artifact_detection(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        "Build an original Subway Surfers-style endless runner web app called Metro Dash.",
        "Metro Dash",
        str(tmp_path),
        ["Player can move left/right between 3 lanes, jump, and slide using keyboard controls."],
    )

    assert expected_artifact_suffix(run, run.state, run.state.acceptance_criteria[0]) == ""
    assert artifact_verification_command(run, run.state, run.state.acceptance_criteria[0]) == ""


def test_context_compiler_uses_compact_sections(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Improve harness", "Harness", str(tmp_path), ["verify"])
    run.state.repo_map.summary = "Tiny repo map"
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "Original goal" in prompt
    assert "repo_map" in snapshot.sections
    assert snapshot.estimated_tokens < 2000
    assert snapshot.prompt_preview


def test_context_compiler_includes_acceptance_recommendations(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Verify dashboard", "Harness", str(tmp_path), ["Dashboard starts"])
    run.state.acceptance_recommendations = [
        AcceptanceEvidenceRecommendation(
            id="criterion-1-browser",
            criterion_id="criterion-1",
            criterion="Dashboard starts",
            label="browser",
            tool_kind="browser_screenshot",
            action="Capture a browser screenshot.",
            command_hint="url=http://127.0.0.1:5173",
        )
    ]
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "acceptance_recommendations" in snapshot.sections
    assert "browser_screenshot" in prompt
    assert "Next evidence actions" in prompt


def test_context_compiler_includes_acceptance_recommendation_traces(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Verify tests", "Harness", str(tmp_path), ["Tests pass"])
    run.state.acceptance_recommendation_traces = [
        AcceptanceRecommendationTrace(
            id="rec-trace-1",
            recommendation_id="criterion-1-verification",
            criterion_id="criterion-1",
            criterion="Tests pass",
            label="verification",
            recommended_tool="run_tests",
            selected_tool="run_tests",
            status="satisfied",
            result_ok=True,
            result_summary="All tests passed.",
        )
    ]
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "acceptance_recommendation_traces" in snapshot.sections
    assert "Evidence action traces" in prompt
    assert "satisfied:verification:run_tests" in prompt


def test_context_compiler_includes_run_health(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Watch health", "Harness", str(tmp_path), [])
    run.state.run_health = RunHealthReport(
        run_id=run.id,
        score=35,
        level="watch",
        recommended_action="pause",
        summary="watch: pause (35/100)",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "run_health" in snapshot.sections
    assert "Run health: watch:pause:35" in prompt

def test_context_compiler_includes_ornith_preflight(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume Ornith safely", "Harness", str(tmp_path), [])
    run.state.ornith_preflight = OrnithLaunchChecklistReport(
        run_id=run.id,
        generated_at="2026-06-27T12:15:00+00:00",
        mode="resume",
        status="attention",
        ready_to_resume=True,
        summary="Ornith can resume after dispatch smoke is refreshed.",
        readiness_smoke_status="passed",
        dispatch_restart_smoke_status="stale",
        run_health_level="watch",
        run_health_action="continue",
        next_actions=["Run operator-dispatch restart smoke before the final claim."],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "ornith_preflight" in snapshot.sections
    assert "Ornith preflight: attention" in prompt
    assert "dispatch=stale" in prompt
    assert "Run operator-dispatch restart smoke" in prompt


def test_context_compiler_includes_ornith_preflight_actions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume Ornith with action evidence", "Harness", str(tmp_path), [])
    latest = OrnithPreflightActionLedgerEntry(
        event_id=12,
        run_id=run.id,
        timestamp="2026-06-27T12:30:00+00:00",
        kind="ornith_preflight_action",
        status="completed",
        item_id="context_budget",
        action_reason="ornith_preflight_context_budget",
        action_summary="Refresh compact context before resuming Ornith.",
        ui_target="context_checkpoint",
        context_pressure="high",
        context_tokens=26000,
        context_target_tokens=18000,
        message="Completed Ornith preflight context checkpoint.",
    )
    run.state.ornith_preflight_actions = OrnithPreflightActionLedgerReport(
        run_id=run.id,
        generated_at="2026-06-27T12:30:00+00:00",
        total_count=1,
        completed_count=1,
        context_checkpoint_count=1,
        latest_action="completed:context_checkpoint",
        recommended_action="Use completed preflight actions as compact resume evidence.",
        approval_history_count=2,
        unresolved_approval_history_count=1,
        approval_histories=[
            OperatorApprovalHistory(
                approval_id=7,
                run_id=run.id,
                event_count=3,
                reviewed_count=1,
                confirmation_required_count=1,
                dispatched_count=1,
                latest_event_id=13,
                latest_status="dispatched",
                latest_decision="reject",
                ui_target="approval",
                sequence=["reviewed#11:open", "confirmation_required#12:reject", "dispatched#13:reject"],
            ),
            OperatorApprovalHistory(
                approval_id=8,
                run_id=run.id,
                event_count=1,
                reviewed_count=1,
                latest_event_id=12,
                latest_status="reviewed",
                latest_decision="open",
                ui_target="approval",
                sequence=["reviewed#12:open"],
            ),
        ],
        unresolved_approval_histories=[
            OperatorApprovalHistory(
                approval_id=8,
                run_id=run.id,
                event_count=1,
                reviewed_count=1,
                latest_event_id=12,
                latest_status="reviewed",
                latest_decision="open",
                ui_target="approval",
                sequence=["reviewed#12:open"],
            )
        ],
        entries=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "ornith_preflight_actions" in snapshot.sections
    assert "Ornith preflight actions: latest=completed:context_budget:context_checkpoint" in prompt
    assert "completed=1" in prompt
    assert "context=1" in prompt


def test_context_compiler_includes_resume_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume carefully", "Harness", str(tmp_path), [])
    decision = ResumeDecisionRecord(
        id=42,
        source="manual",
        accepted=True,
        policy_action="continue",
        predicted_status="running",
        predicted_milestone="act",
    )
    run.state.handoff_summary.resume_decisions = ResumeDecisionReport(
        run_id=run.id,
        decision_count=1,
        accepted_count=1,
        latest_decision=decision,
        latest_accepted=decision,
        current_policy_action="continue",
        current_predicted_status="running",
        current_predicted_milestone="act",
        current_matches_last_accepted=True,
        comparison_summary="Current policy simulation matches the latest accepted resume snapshot.",
        recommended_action="Continue under the accepted resume context.",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "resume_decisions" in snapshot.sections
    assert "Resume decision: latest=accepted:manual:continue" in prompt
    assert "Continue under the accepted resume context." in prompt



def test_promotion_repair_report_tracks_file_read_patch_and_verify_phases(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run = store.create_run("Repair promotion", "Promotion repair", str(workspace), [])
    latest = PromotionVerificationAttemptRecord(
        event_id=44,
        timestamp="2026-06-28T12:00:00+00:00",
        command="python -m py_compile broken.py",
        ok=False,
        audit_status="needs_verification",
        summary="Promotion verification failed.",
        returncode=1,
        failure_kind="syntax_error",
        suspected_file="broken.py",
        suspected_line=1,
        repair_hint="Open `broken.py:1` and fix invalid syntax before rerunning promotion verification.",
        evidence_excerpt="SyntaxError: invalid syntax",
    )
    run.state.promotion_verification = PromotionVerificationReport(
        run_id=run.id,
        generated_at="2026-06-28T12:00:00+00:00",
        status="needs_retry",
        attempt_count=1,
        failed_count=1,
        repeated_failure_count=1,
        repair_hint_count=1,
        latest_attempt=latest,
        latest_failed_command=latest.command,
        latest_failure_kind=latest.failure_kind,
        latest_suspected_file=latest.suspected_file,
        latest_repair_hint=latest.repair_hint,
        next_command="python -m compileall .",
        should_use_alternate=True,
        recommended_action=latest.repair_hint,
        attempts=[latest],
    )
    run.state.tool_calls.append(ToolCallRecord(id="proof", name="run_tests", args={"command": latest.command}, ok=False))

    report = build_promotion_repair_report(run)

    assert report.phase == "needs_file_read"
    assert report.target_file == "broken.py"
    assert report.next_tool == "file_read"

    run.state.tool_calls.append(
        ToolCallRecord(
            id="read-target",
            name="file_read",
            args={"path": "broken.py", "content": "def broken(:\n    pass\n"},
            ok=True,
        )
    )
    report = build_promotion_repair_report(run)

    assert report.phase == "needs_patch_proposal"
    assert report.file_read is True
    assert report.file_read_tool_id == "read-target"
    assert report.file_excerpt_chars > 0
    assert report.next_tool == "patch_propose"

    run.state.patch_proposals.append(
        PatchProposal(id="patch-1", title="Repair broken.py", files=["broken.py"], status="pending")
    )
    report = build_promotion_repair_report(run)

    assert report.phase == "patch_proposed"
    assert report.patch_proposal_id == "patch-1"
    assert report.next_tool == "patch_apply"

    run.state.patch_applications.append(
        PatchApplication(id="apply-1", patch_id="patch-1", status="applied", files=["broken.py"])
    )
    report = build_promotion_repair_report(run)

    assert report.phase == "ready_to_verify"
    assert report.patch_application_id == "apply-1"
    assert report.next_tool == "run_tests"
    assert report.next_verification_command == "python -m compileall ."


def test_context_compiler_includes_promotion_repair_phase(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Repair promotion", "Promotion repair context", str(tmp_path), [])
    run.state.promotion_repair = build_promotion_repair_report(run)
    run.state.promotion_repair.phase = "needs_patch_proposal"
    run.state.promotion_repair.active = True
    run.state.promotion_repair.target_file = "broken.py"
    run.state.promotion_repair.target_line = 1
    run.state.promotion_repair.file_read = True
    run.state.promotion_repair.next_tool = "patch_propose"
    run.state.promotion_repair.next_action = "Propose a minimal patch for `broken.py`."
    run.state.handoff_summary.promotion_repair = run.state.promotion_repair
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "promotion_repair" in snapshot.sections
    assert "Promotion repair: needs_patch_proposal" in prompt
    assert "target=broken.py:1" in prompt
    assert "next_tool=patch_propose" in prompt

def test_context_compiler_includes_promotion_verification(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Promote safely", "Harness", str(tmp_path), [])
    latest = PromotionVerificationAttemptRecord(
        event_id=12,
        timestamp="2026-06-27T12:00:00+00:00",
        command="python -m py_compile missing.py",
        ok=False,
        audit_status="needs_verification",
        summary="Promotion audit still needs verification.",
        failure_kind="missing_file",
        suspected_file="missing.py",
        repair_hint="Check whether `missing.py` exists before rerunning promotion verification.",
        evidence_excerpt="No such file or directory: 'missing.py'",
    )
    report = PromotionVerificationReport(
        run_id=run.id,
        generated_at="2026-06-27T12:00:00+00:00",
        status="needs_retry",
        attempt_count=1,
        failed_count=1,
        repeated_failure_count=1,
        latest_attempt=latest,
        latest_failed_command=latest.command,
        latest_failure_kind="missing_file",
        latest_suspected_file="missing.py",
        latest_repair_hint=latest.repair_hint,
        next_command="python -m compileall .",
        should_use_alternate=True,
        recommended_action="Run the alternate promotion verification diagnostic: python -m compileall .",
        attempts=[latest],
    )
    run.state.promotion_verification = report
    run.state.handoff_summary.promotion_verification = report
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "promotion_verification" in snapshot.sections
    assert "Promotion verification: needs_retry" in prompt
    assert "next=python -m compileall ." in prompt
    assert "failure=missing_file" in prompt
    assert "file=missing.py" in prompt
    assert "repair=Check whether `missing.py` exists" in prompt
    assert "alternate=True" in prompt



def test_action_context_pack_includes_promotion_verification_repair_hints(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Repair promotion failure", "Harness", str(tmp_path), [])
    latest = PromotionVerificationAttemptRecord(
        event_id=15,
        timestamp="2026-06-28T12:00:00+00:00",
        command="python -m py_compile broken.py",
        ok=False,
        audit_status="needs_verification",
        summary="Promotion verification failed.",
        returncode=1,
        failure_kind="syntax_error",
        suspected_file="broken.py",
        suspected_line=1,
        repair_hint="Open `broken.py:1` and fix invalid syntax before rerunning promotion verification.",
        evidence_excerpt="SyntaxError: invalid syntax",
    )
    run.state.promotion_verification = PromotionVerificationReport(
        run_id=run.id,
        generated_at="2026-06-28T12:00:00+00:00",
        status="needs_retry",
        attempt_count=1,
        failed_count=1,
        repeated_failure_count=1,
        repair_hint_count=1,
        latest_attempt=latest,
        latest_failed_command=latest.command,
        latest_failure_kind=latest.failure_kind,
        latest_suspected_file=latest.suspected_file,
        latest_repair_hint=latest.repair_hint,
        next_command="python -m compileall .",
        should_use_alternate=True,
        recommended_action=latest.repair_hint,
        attempts=[latest],
    )

    pack = build_action_context_pack(run)

    assert pack.promotion_repair_hints
    assert "syntax_error:broken.py:1:rc=1" in pack.promotion_repair_hints[0]
    assert "Open `broken.py:1`" in pack.promotion_repair_hints[0]
    assert "next_promotion_verification=python -m compileall ." in pack.promotion_repair_hints
    assert "promotion_repair_hints=syntax_error:broken.py:1:rc=1" in pack.compact_prompt
    assert "next_promotion_verification=python -m compileall ." in pack.compact_prompt



def test_action_context_pack_includes_readiness_source_ref_posture(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Refresh readiness proof refs", "Source refs", str(tmp_path), [])
    run.state.readiness_source_ref_preview = ReadinessSourceRefPreviewReport(
        run_id=run.id,
        generated_at="2026-06-29T10:10:00+00:00",
        status="missing_proof_refs",
        summary="Source evidence exists, but proof refs are stale.",
        recommended_action="Dispatch the readiness source-ref refresh.",
        source_visible_labels=["browser", "web"],
        source_evidence_labels=["browser", "web"],
        proof_ref_labels=["web"],
        missing_proof_ref_labels=["browser"],
    )

    pack = build_action_context_pack(run)

    assert pack.readiness_source_ref_status == "missing_proof_refs"
    assert pack.readiness_source_ref_missing_proof_labels == ["browser"]
    assert pack.readiness_source_ref_source_labels == ["browser", "web"]
    assert "source_refs status=missing_proof_refs" in pack.compact_prompt
    assert "missing_proof=browser" in pack.compact_prompt
    assert "Dispatch readiness source-ref refresh before broad coding" in pack.compact_prompt


def test_action_context_pack_requires_desktop_effect_check_until_visual_proof(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Verify desktop effect", "Desktop effect", str(tmp_path), [])
    run.state.tool_calls.append(
        ToolCallRecord(
            id="desktop-click-1",
            name="desktop_click",
            ok=True,
            summary="Approved supervised desktop click recorded.",
        )
    )

    pack = build_action_context_pack(run)

    assert any("desktop_effect_check_required" in item for item in pack.desktop_supervision_ledger)
    assert "after=desktop_click" in pack.compact_prompt
    assert "capture_desktop_screenshot_or_window_list_before_next_click_type" in pack.compact_prompt

    run.state.tool_calls.append(
        ToolCallRecord(
            id="desktop-shot-1",
            name="desktop_screenshot",
            ok=True,
            summary="Captured supervised desktop screenshot.",
        )
    )
    refreshed = build_action_context_pack(run)

    assert not any("desktop_effect_check_required" in item for item in refreshed.desktop_supervision_ledger)
    assert "desktop_effect_check_required" not in refreshed.compact_prompt

def test_action_context_pack_includes_desktop_supervision_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Remember supervised desktop decisions", "Desktop supervision", str(tmp_path), [])
    run.state.operator_dispatches = OperatorDispatchLedgerReport(
        run_id=run.id,
        generated_at="2026-06-29T12:00:00+00:00",
        approval_history_count=2,
        approval_histories=[
            OperatorApprovalHistory(
                approval_id=7,
                run_id=run.id,
                event_count=3,
                latest_event_id=30,
                latest_status="dispatched",
                latest_decision="approve",
                action_summary="Review desktop_click approval for AgentOrinth Dashboard.",
                approval_kind="desktop_click",
                ui_target="approval",
                sequence=["reviewed#28:open", "confirmation_required#29:approve", "dispatched#30:approve"],
            ),
            OperatorApprovalHistory(
                approval_id=8,
                run_id=run.id,
                event_count=3,
                latest_event_id=27,
                latest_status="dispatched",
                latest_decision="reject",
                action_summary="Review desktop_type approval with api_key=super-secret.",
                approval_kind="desktop_type",
                ui_target="approval",
                sequence=["reviewed#25:open", "confirmation_required#26:reject", "dispatched#27:reject"],
            ),
        ],
    )

    pack = build_action_context_pack(run)
    run.state.action_context = pack
    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert any("approval#7" in item and "human_approved_supervised_action" in item for item in pack.desktop_supervision_ledger)
    assert any("approval#8" in item and "human_rejected_do_not_repeat_without_new_evidence" in item for item in pack.desktop_supervision_ledger)
    assert "desktop_supervision=approval#7:kind=desktop_click" in pack.compact_prompt
    assert "decision=reject" in pack.compact_prompt
    assert "api_key=[REDACTED]" in pack.compact_prompt
    assert "super-secret" not in pack.compact_prompt
    assert "action_context" in snapshot.sections
    assert "desktop_supervision=approval#7:kind=desktop_click" in prompt
    assert "human_rejected_do_not_repeat_without_new_evidence" in prompt

def test_context_compiler_includes_operator_dispatches(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Supervise carefully", "Harness", str(tmp_path), [])
    latest = OperatorDispatchLedgerEntry(
        event_id=11,
        run_id=run.id,
        timestamp="2026-06-27T12:00:00+00:00",
        kind="operator_action_dispatched",
        status="dispatched",
        decision="dispatch",
        confirmed=True,
        action_reason="recovery",
        action_title="Recovery attention",
        action_summary="Resume active recovery.",
        ui_target="recovery",
        message="Operator dispatched recovery resume.",
    )
    run.state.operator_dispatches = OperatorDispatchLedgerReport(
        run_id=run.id,
        generated_at="2026-06-27T12:00:00+00:00",
        total_count=1,
        dispatched_count=1,
        latest_action="dispatched:dispatch",
        recommended_action="Use dispatched operator actions as compact supervision evidence.",
        approval_history_count=2,
        unresolved_approval_history_count=1,
        approval_histories=[
            OperatorApprovalHistory(
                approval_id=7,
                run_id=run.id,
                event_count=3,
                reviewed_count=1,
                confirmation_required_count=1,
                dispatched_count=1,
                latest_event_id=13,
                latest_status="dispatched",
                latest_decision="reject",
                ui_target="approval",
                sequence=["reviewed#11:open", "confirmation_required#12:reject", "dispatched#13:reject"],
            ),
            OperatorApprovalHistory(
                approval_id=8,
                run_id=run.id,
                event_count=1,
                reviewed_count=1,
                latest_event_id=12,
                latest_status="reviewed",
                latest_decision="open",
                ui_target="approval",
                sequence=["reviewed#12:open"],
            ),
        ],
        unresolved_approval_histories=[
            OperatorApprovalHistory(
                approval_id=8,
                run_id=run.id,
                event_count=1,
                reviewed_count=1,
                latest_event_id=12,
                latest_status="reviewed",
                latest_decision="open",
                ui_target="approval",
                sequence=["reviewed#12:open"],
            )
        ],
        promotion_route_count=1,
        promotion_approval_route_count=1,
        promotion_approval_history_count=1,
        unresolved_promotion_approval_history_count=1,
        promotion_approval_histories=[
            OperatorApprovalHistory(
                approval_id=8,
                run_id=run.id,
                event_count=1,
                reviewed_count=1,
                latest_event_id=12,
                latest_status="reviewed",
                latest_decision="open",
                ui_target="approval",
                sequence=["reviewed#12:open"],
            )
        ],
        unresolved_promotion_approval_histories=[
            OperatorApprovalHistory(
                approval_id=8,
                run_id=run.id,
                event_count=1,
                reviewed_count=1,
                latest_event_id=12,
                latest_status="reviewed",
                latest_decision="open",
                ui_target="approval",
                sequence=["reviewed#12:open"],
            )
        ],
        promotion_routes=[
            OperatorDispatchLedgerEntry(
                event_id=14,
                run_id=run.id,
                timestamp="2026-06-27T12:05:00+00:00",
                kind="operator_action_reviewed",
                status="reviewed",
                decision="open",
                action_reason="promotion_audit_promotion_approval_history_unresolved",
                action_title="Promotion audit approval history",
                action_summary="Resolve reviewed workspace_promote approval before source promotion.",
                ui_target="approval",
                approval_id=8,
                approval_kind="workspace_promote",
                endpoint=f"/api/runs/{run.id}/approvals",
                details=["audit_status=ready", "issue=promotion_approval_history_unresolved", "approval_id=8"],
                message="Operator opened queued action promotion_audit_promotion_approval_history_unresolved.",
            )
        ],
        entries=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "operator_dispatches" in snapshot.sections
    assert "Operator dispatches: latest=dispatched:dispatch:recovery" in prompt
    assert "dispatched=1" in prompt
    assert "approval_histories=2" in prompt
    assert "unresolved_approval_histories=1" in prompt
    assert "promotion_routes=1" in prompt
    assert "promotion_approval_routes=1" in prompt
    assert "promotion_approval_histories=1" in prompt
    assert "unresolved_promotion_approval_histories=1" in prompt
    assert "approval_history=approval#8:latest=reviewed:events=1" in prompt
    assert "promotion_route=event#14:promotion_audit_promotion_approval_history_unresolved->approval:approval#8" in prompt
    assert "promotion_approval_history=approval#8:latest=reviewed:events=1" in prompt
    assert "reviewed#12:open" in prompt


def test_context_compiler_includes_promotion_audit_approval_history(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume promotion audit", "Harness", str(tmp_path), [])
    run.state.promotion_audit = PromotionAuditReport(
        run_id=run.id,
        generated_at="2026-06-28T00:00:00+00:00",
        status="ready",
        ready_to_promote=True,
        changed_file_count=1,
        patch_proposal_count=1,
        patch_application_count=0,
        pending_approval_count=1,
        unresolved_approval_history_count=1,
        unresolved_approval_histories=["approval#5:latest=reviewed:events=1:seq=reviewed#9:open"],
        resume_drift_status="unchanged",
        recommended_action="Resolve the existing source-promotion approval in the dashboard.",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=3000).compile(run, run.state, memory, [])

    assert "promotion_audit" in snapshot.sections
    assert "Promotion audit: ready" in prompt
    assert "pending_approvals=1" in prompt
    assert "unresolved_approval_histories=1" in prompt
    assert "approval_history=approval#5:latest=reviewed:events=1:seq=reviewed#9:open" in prompt

def test_context_compiler_includes_action_readiness(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Act carefully", "Harness", str(tmp_path), [])
    run.state.action_readiness = ActionReadinessReport(
        run_id=run.id,
        status="needs_proof",
        ready_to_act=True,
        recommended_action="Run the smallest relevant verification command.",
        suggested_tool="run_tests",
        suggested_label="verification",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=2000).compile(run, run.state, memory, [])

    assert "action_readiness" in snapshot.sections
    assert "Action readiness: needs_proof; ready=True" in prompt
    assert "tool=run_tests:verification" in prompt


def test_context_compiler_includes_action_readiness_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Trace readiness", "Harness", str(tmp_path), [])
    latest = ActionReadinessDecisionRecord(
        id=7,
        status="satisfied",
        source="harness",
        selected_tool="run_tests",
        label="verification",
        summary="harness selected run_tests for verification; intended proof was satisfied.",
    )
    run.state.action_readiness_decisions = ActionReadinessDecisionReport(
        run_id=run.id,
        decision_count=1,
        selected_count=1,
        satisfied_count=1,
        latest_decision=latest,
        latest_tool_decision=latest,
        summary=latest.summary,
        recommended_action="Continue with the next milestone using the compact satisfied-proof context.",
        decisions=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "action_readiness_decisions" in snapshot.sections
    assert "Action readiness decisions: latest=satisfied:harness:run_tests" in prompt
    assert "satisfied=1" in prompt


def test_context_compiler_includes_recovery_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Recover carefully", "Harness", str(tmp_path), [])
    latest = RecoveryDecisionRecord(
        id="recovery-1",
        status="active",
        trigger="readiness_decision_loop",
        tool="run_tests",
        proof_label="verification",
        selected_strategy="Run a narrower diagnostic than the repeated test command.",
        next_action="Review readiness decisions.",
        summary="active recovery for verification: Run a narrower diagnostic.",
    )
    run.state.recovery_decisions = RecoveryDecisionReport(
        run_id=run.id,
        decision_count=1,
        active_recovery=True,
        readiness_recovery_count=1,
        latest_decision=latest,
        active_decision=latest,
        latest_readiness_decision=latest,
        summary=latest.summary,
        recommended_action="Resume or replan active recovery: Review readiness decisions.",
        decisions=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "recovery_decisions" in snapshot.sections
    assert "Recovery decisions: latest=active:readiness_decision_loop:run_tests:verification" in prompt
    assert "active=True" in prompt

def test_context_compiler_includes_action_context_pack(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Use packed action context", "Harness", str(tmp_path), ["Tests pass"])
    run.state.action_context = ActionContextPack(
        run_id=run.id,
        generated_at="2026-06-28T12:05:00+00:00",
        milestone="act",
        current_task_id="task-1",
        current_task_title="Run focused proof",
        action_readiness_status="needs_proof",
        selected_tool="run_tests",
        selected_label="verification",
        selected_action="Run the smallest relevant verification command: python -m pytest",
        selected_reason="Criterion still needs test proof.",
        selected_command_hint="python -m pytest",
        selected_criterion="Tests pass",
        missing_source_labels=[],
        recent_verified_commands=["python -m compileall backend\\app"],
        recent_verified_files=["backend/app/engine.py"],
        recent_successes=["shell: compile passed"],
        failure_ledger=["timeout:shell:x2:Reduce command scope"],
        context_budget="1200/24000:low",
        compact_prompt=(
            "Action context pack:\n"
            "- selected_proof=run_tests:verification; action=Run the smallest relevant verification command: python -m pytest\n"
            "- failure_ledger=timeout:shell:x2:Reduce command scope"
        ),
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "action_context" in snapshot.sections
    assert "Action context pack:" in prompt
    assert "selected_proof=run_tests:verification" in prompt
    assert "failure_ledger=timeout:shell:x2" in prompt

def test_context_compiler_includes_source_evidence_preview(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Use compact source evidence", "Harness", str(tmp_path), [])
    run.state.source_evidence = SourceEvidencePreviewReport(
        run_id=run.id,
        generated_at="2026-06-28T12:00:00+00:00",
        total_count=2,
        web_source_count=1,
        browser_snapshot_count=1,
        linked_criterion_count=1,
        required_label_count=2,
        matched_label_count=1,
        missing_labels=["browser"],
        latest_evidence="browser_snapshot:Browser screenshot",
        recommended_action="Capture missing source evidence labels before claiming related criteria: browser",
        entries=[
            SourceEvidencePreviewEntry(
                id="browser-1",
                kind="browser_snapshot",
                title="Browser screenshot",
                tool_kind="browser_screenshot",
                evidence_label="browser",
                linked_criteria=["Dashboard visible"],
                summary="Captured browser screenshot.",
            )
        ],
    )
    run.state.readiness_source_ref_preview = ReadinessSourceRefPreviewReport(
        run_id=run.id,
        generated_at="2026-06-28T12:01:00+00:00",
        status="missing_proof_refs",
        source_visible_labels=["browser", "web"],
        source_evidence_labels=["web"],
        proof_ref_labels=["web"],
        missing_source_evidence_labels=["browser"],
        missing_proof_ref_labels=["browser"],
        recommended_action="Refresh readiness source refs before claiming readiness.",
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "source_evidence" in snapshot.sections
    assert "readiness_source_ref_preview" in snapshot.sections
    assert "Readiness source refs: missing_proof_refs" in prompt
    assert "missing_evidence=browser" in prompt
    assert "Source evidence: total=2; web=1; browser=1" in prompt
    assert "missing=browser" in prompt

def test_context_compiler_includes_report_integrity_refresh_reason(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume with refresh reason", "Refresh context", str(tmp_path), [])
    reason = "stale:handoff.approval_reviews.review_count | expected=1:2 | actual=1:1"
    run.state.report_integrity = ReportIntegrityReport(
        run_id=run.id,
        status="ok",
        check_count=12,
        ok_count=12,
        recommended_action="Resume from the current compact handoff.",
    )
    run.state.report_integrity_refreshes = [
        ReportIntegrityRefreshRecord(
            event_id=8,
            report_status="ok",
            previous_report_status="needs_refresh",
            reason_count=1,
            reasons=[reason],
            preflight_event_id=9,
            preflight_event_kind="resume_preflight_blocked",
            preflight_accepted=False,
        )
    ]

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "report_integrity" in snapshot.sections
    assert "refresh=#8:needs_refresh->ok reasons=1" in prompt
    assert "preflight=#9:resume_preflight_blocked" in prompt
    assert "refresh_reason=stale:handoff.approval_reviews.review_count" in prompt

def test_context_compiler_includes_checkpoint_quality(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume with checkpoint quality", "Checkpoint context", str(tmp_path), [])
    run.state.checkpoint_quality = CheckpointQualityReport(
        run_id=run.id,
        generated_at="2026-06-28T12:30:00+00:00",
        status="needs_checkpoint",
        run_note_present=True,
        run_note_chars=1200,
        has_active_goal=True,
        has_next_action=False,
        has_resume_prompt=True,
        has_report_integrity_refresh=False,
        expected_report_integrity_refresh=True,
        expected_refresh_event_id=8,
        blocker_count=1,
        warning_count=0,
        summary="Obsidian checkpoint is missing one anchor.",
        recommended_action="Write or refresh the Obsidian checkpoint before resume.",
    )

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "checkpoint_quality" in snapshot.sections
    assert "Checkpoint quality: needs_checkpoint" in prompt
    assert "anchors=goal:True,next:False,resume:True,refresh:False" in prompt
    assert "expected_refresh=#8" in prompt

def test_context_compiler_includes_checkpoint_quality_resume_breadcrumb(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume after checkpoint repair", "Checkpoint resume", str(tmp_path), [])
    run.state.checkpoint_quality_resumes = CheckpointQualityResumeReport(
        run_id=run.id,
        generated_at="2026-06-28T12:45:00+00:00",
        status="resumed",
        repair_count=1,
        resumed_after_repair_count=1,
        blocked_after_repair_count=0,
        awaiting_resume_count=0,
        latest=CheckpointQualityResumeRecord(
            repair_event_id=7,
            repair_completed_event_id=7,
            repair_reason="checkpoint_quality",
            repair_ui_target="handoff_refresh",
            repair_action="Write refreshed Obsidian checkpoint.",
            resume_event_id=9,
            resume_source="manual",
            resume_accepted=True,
            resume_policy_action="verify",
            checkpoint_quality_status="ready",
            checkpoint_quality_ready=True,
        ),
        recommended_action="Continue from the accepted resume preflight and repaired checkpoint-quality handoff.",
    )

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "checkpoint_quality_resumes" in snapshot.sections
    assert "Checkpoint-quality resume repairs: resumed" in prompt
    assert "repair=#7:checkpoint_quality:handoff_refresh" in prompt
    assert "resume=#9:verify:accepted" in prompt
    assert "checkpoint_ready=True:ready" in prompt
    assert "accepted resume preflight" in prompt


def test_context_compiler_reports_no_checkpoint_quality_resume_breadcrumb_for_ordinary_run(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Ordinary resume", "Checkpoint resume", str(tmp_path), [])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "checkpoint_quality_resumes" in snapshot.sections
    assert "Checkpoint-quality resume repairs: none" in prompt
    assert "repair=#" not in prompt
    assert "resume=#" not in prompt

def test_context_compiler_includes_post_action_retries(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Retry compactly", "Post retry context", str(tmp_path), [])
    decision = PostActionRetryDecisionRecord(
        id="post-retry-1",
        status="pending",
        trigger_tool="run_tests",
        failure_kind="command_failure",
        selected_tool="shell",
        selected_action="Run a focused compile diagnostic before repeating broad tests.",
        command_hint="python -m compileall backend\\app",
        reason="Broad test proof failed.",
    )
    run.state.post_action_retries = PostActionRetryReport(
        run_id=run.id,
        generated_at="2026-06-28T12:10:00+00:00",
        decision_count=1,
        pending_count=1,
        latest_decision=decision,
        summary="Post-action retry pending.",
        recommended_action=decision.selected_action,
        decisions=[decision],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "post_action_retries" in snapshot.sections
    assert "Post-action retries: latest=pending:run_tests->shell" in prompt
    assert "pending=1" in prompt

def test_context_compiler_includes_approval_review_summaries(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Resume through approval", "Approval Context", str(tmp_path), [])
    run.state.handoff_summary.approval_reviews = [
        ApprovalReviewSummary(
            id=9,
            status="pending",
            action_kind="workspace_promote",
            summary="Promote isolated workspace changes.",
            reviewed=True,
            review_count=1,
            latest_review_event_id=42,
            high_risk=True,
            files=["modified: main.py"],
        )
    ]

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "approval_reviews" in snapshot.sections
    assert "Approval gates: pending=1; unreviewed=0; reviewed=1; high_risk=1" in prompt
    assert "latest=workspace_promote#9:event#42" in prompt
    assert "workspace_promote#9:reviewed:Promote isolated workspace changes." in prompt


def test_context_compiler_includes_verification_outcomes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Verify after recovery", "Harness", str(tmp_path), [])
    latest = VerificationOutcomeRecord(
        id="outcome-tool-run-tests",
        tool_call_id="tool-run-tests",
        tool="run_tests",
        outcome="recovery_resolved",
        summary="All tests passed.",
        during_recovery=True,
        recovery_id="recovery-1",
        closed_recovery=True,
        resolved_recovery_evidence=True,
        proof_label="verification",
        evidence_status="verified",
        labels_satisfied=["verification"],
    )
    run.state.verification_outcomes = VerificationOutcomeReport(
        run_id=run.id,
        outcome_count=1,
        verified_count=1,
        recovery_outcome_count=1,
        recovery_resolved_count=1,
        latest_outcome=latest,
        latest_recovery_outcome=latest,
        summary="Recovery proof closed by run_tests: All tests passed.",
        recommended_action="Continue from the next milestone with the verified recovery evidence.",
        outcomes=[latest],
    )
    memory = MemoryContext(hits=[], warnings=[])

    prompt, snapshot = ContextCompiler(target_tokens=4000).compile(run, run.state, memory, [])

    assert "verification_outcomes" in snapshot.sections
    assert "Verification outcomes: latest=recovery_resolved:run_tests:verification" in prompt
    assert "recovery_resolved=1" in prompt

def test_context_compiler_includes_goal_evolution(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Original goal", "Goal Context", str(tmp_path), [])
    decision = GoalEvolutionDecisionRecord(
        id="goal-context-1",
        status="pending",
        source="scheduled_review",
        previous_goal="Original goal",
        proposed_goal="Sharper context goal",
        reason="The objective narrowed after verification.",
        material_change="next=verify focused proof",
        step_count=3,
        milestone="decide",
        approval_id=7,
        created_at="2026-06-27T08:00:00+00:00",
    )
    run.state.proposed_goal = "Sharper context goal"
    run.state.goal_evolution = GoalEvolutionReport(
        run_id=run.id,
        generated_at="2026-06-27T08:01:00+00:00",
        active_goal=run.state.goal,
        proposed_goal="Sharper context goal",
        decision_count=1,
        pending_count=1,
        latest_decision=decision,
        summary="Goal update pending confirmation: Sharper context goal",
        recommended_action="Ask the operator to approve or reject the pending /goal update before resuming.",
        decisions=[decision],
    )

    prompt, snapshot = ContextCompiler(4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "goal_evolution" in snapshot.sections
    assert "Goal evolution: latest=pending:scheduled_review" in prompt
    assert "proposed=Sharper context goal" in prompt


def test_context_compiler_includes_git_checkpoint(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Audit git posture", "Git Context", str(tmp_path), [])
    run.state.git_checkpoint = GitCheckpointReport(
        run_id=run.id,
        generated_at="2026-06-27T08:01:00+00:00",
        status="commit_recommended",
        branch="main",
        remote_names=["origin"],
        remote_count=1,
        github_remote_count=1,
        changed_count=2,
        staged_count=1,
        modified_count=1,
        untracked_count=0,
        ahead_count=0,
        summary="Git checkpoint commit_recommended: changed=2.",
        recommended_action="Commit a scoped local checkpoint.",
    )

    prompt, snapshot = ContextCompiler(4000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert "git_checkpoint" in snapshot.sections
    assert "Git checkpoint: commit_recommended" in prompt
    assert "remotes=origin" in prompt
    assert "Commit a scoped local checkpoint." in prompt

def test_context_compiler_reports_dropped_optional_sections(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Track compact coverage", "Coverage", str(tmp_path), [])
    run.state.acceptance_evidence = [
        AcceptanceCriterionEvidence(
            id="huge-evidence",
            criterion="Huge optional evidence",
            evidence=["large optional evidence " * 2000],
        )
    ]

    prompt, snapshot = ContextCompiler(3000).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert prompt
    assert snapshot.run_id == run.id
    assert snapshot.coverage_status == "degraded"
    assert "acceptance_evidence" in snapshot.dropped_sections
    assert snapshot.dropped_section_count >= 1
    assert snapshot.required_sections_missing == []
    assert snapshot.section_token_estimates["acceptance_evidence"] > snapshot.section_token_estimates["goal"]
    assert "omitted optional sections" in snapshot.recommended_action


def test_context_compiler_reports_critical_required_omissions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Track compact coverage", "Coverage", str(tmp_path), [])

    _prompt, snapshot = ContextCompiler(5).compile(run, run.state, MemoryContext(hits=[], warnings=[]), [])

    assert snapshot.coverage_status == "critical"
    assert "goal" in snapshot.required_sections_missing
    assert snapshot.dropped_section_count >= len(snapshot.required_sections_missing)
    assert "re-orient" in snapshot.recommended_action
