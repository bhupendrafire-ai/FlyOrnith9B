from __future__ import annotations

from datetime import datetime, timezone

from .schemas import (
    ObjectiveReadinessItem,
    ObjectiveReadinessProof,
    ObjectiveReadinessProofOutcome,
    ObjectiveReadinessProofPreference,
    ObjectiveReadinessReport,
    RunRecord,
)


def build_objective_readiness(
    run: RunRecord,
    *,
    tool_names: set[str],
) -> ObjectiveReadinessReport:
    state = run.state
    items = [
        _workspace_item(run),
        _patch_item(run, tool_names),
        _task_graph_item(run),
        _context_item(run),
        _resume_quality_item(run),
        _repo_map_item(run),
        _verification_item(run),
        _failure_recovery_item(run),
        _replay_audit_item(run),
        _obsidian_handoff_item(run),
        _goal_evolution_item(run),
        _git_checkpoint_item(run),
        _promotion_audit_item(run),
        _resume_handoff_diff_item(run),
    ]
    outcomes = getattr(state, "objective_readiness_proof_outcomes", [])
    _apply_proof_outcomes(items, outcomes)
    proof_preferences = _proof_preferences(items, outcomes)
    _apply_proof_preferences(items, proof_preferences)
    verified = sum(1 for item in items if item.status == "verified")
    partial = sum(1 for item in items if item.status == "partial")
    missing = sum(1 for item in items if item.status == "missing")
    failed = sum(1 for item in items if item.status == "failed")
    status = "ready" if failed == 0 and missing == 0 and partial <= 1 else "not_ready" if failed or missing >= 3 else "partial"
    weakest = next((item for item in items if item.status == "failed"), None) or next(
        (item for item in items if item.status == "missing"),
        None,
    ) or next(
        (item for item in items if item.status == "partial"),
        None,
    )
    next_actions = [
        _next_action_with_proof(item)
        for item in items
        if item.status != "verified" and item.next_action
    ][:8]
    return ObjectiveReadinessReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status=status,
        verified_count=verified,
        partial_count=partial,
        missing_count=missing,
        failed_count=failed,
        summary=f"{status}: {verified}/{len(items)} major harness requirements verified for this run; {failed} proof failure(s).",
        recommended_action=weakest.next_action if weakest else "Continue verifying the harness with real long coding runs.",
        next_actions=next_actions,
        proof_preferences=proof_preferences,
        items=items,
    )


def _apply_proof_outcomes(
    items: list[ObjectiveReadinessItem],
    outcomes: list[ObjectiveReadinessProofOutcome],
) -> None:
    latest: dict[str, ObjectiveReadinessProofOutcome] = {}
    for outcome in outcomes:
        if outcome.item_id:
            latest[outcome.item_id] = outcome
    for item in items:
        outcome = latest.get(item.id)
        if not outcome:
            continue
        item.latest_outcome = outcome
        evidence = f"proof:{outcome.outcome}:{outcome.tool}:{outcome.summary}"
        if evidence not in item.evidence:
            item.evidence.append(evidence)
            item.evidence = item.evidence[-8:]
        if outcome.outcome == "verified":
            item.status = "verified"
            item.next_action = ""
            continue
        if outcome.outcome == "failed":
            item.status = "failed"
            item.next_action = f"Choose an alternate proof for {item.id} before retrying {outcome.tool}."
            continue
        if outcome.outcome == "waiting_approval":
            item.status = "partial" if item.status != "verified" else item.status
            item.next_action = f"Resolve approval for {item.id} proof before continuing."
            continue
        if item.status == "missing":
            item.status = "partial"


def _next_action_with_proof(item: ObjectiveReadinessItem) -> str:
    proof = _preferred_or_static_proof(item)
    proof_text = ""
    if proof.tool_kind or proof.evidence_label:
        strategy = f" ({proof.strategy})" if proof.strategy else ""
        proof_text = f" Proof: {proof.tool_kind or 'tool'} / {proof.evidence_label or 'evidence'}{strategy}."
    return f"{item.next_action}{proof_text}"


def _preferred_or_static_proof(item: ObjectiveReadinessItem) -> ObjectiveReadinessProof:
    preferred = item.preferred_proof
    if preferred.tool_kind or preferred.action:
        return ObjectiveReadinessProof(
            tool_kind=preferred.tool_kind,
            evidence_label=preferred.evidence_label,
            strategy=preferred.strategy,
            action=preferred.action,
            command_hint=preferred.command_hint,
            success_signal=preferred.reason,
        )
    return item.proof


def _apply_proof_preferences(
    items: list[ObjectiveReadinessItem],
    preferences: list[ObjectiveReadinessProofPreference],
) -> None:
    by_item = {preference.item_id: preference for preference in preferences}
    for item in items:
        preference = by_item.get(item.id)
        if preference:
            item.preferred_proof = preference


def _proof_preferences(
    items: list[ObjectiveReadinessItem],
    outcomes: list[ObjectiveReadinessProofOutcome],
) -> list[ObjectiveReadinessProofPreference]:
    item_by_id = {item.id: item for item in items}
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    latest_for_item: dict[str, ObjectiveReadinessProofOutcome] = {}
    for outcome in outcomes[-40:]:
        if not outcome.item_id or outcome.item_id not in item_by_id:
            continue
        strategy = outcome.strategy or _strategy_for_outcome(outcome)
        key = (outcome.item_id, outcome.tool, strategy)
        bucket = grouped.setdefault(
            key,
            {
                "verified": 0,
                "partial": 0,
                "failed": 0,
                "latest": outcome,
            },
        )
        if outcome.outcome == "verified":
            bucket["verified"] = int(bucket["verified"]) + 1
        elif outcome.outcome == "partial":
            bucket["partial"] = int(bucket["partial"]) + 1
        elif outcome.outcome == "failed":
            bucket["failed"] = int(bucket["failed"]) + 1
        bucket["latest"] = outcome
        latest_for_item[outcome.item_id] = outcome

    preferences: list[ObjectiveReadinessProofPreference] = []
    for item in items:
        candidates = [
            (key, bucket)
            for key, bucket in grouped.items()
            if key[0] == item.id
        ]
        verified_candidates = [
            (key, bucket)
            for key, bucket in candidates
            if int(bucket["verified"]) > 0
        ]
        if verified_candidates:
            key, bucket = sorted(
                verified_candidates,
                key=lambda entry: (
                    int(entry[1]["verified"]),
                    int(entry[1]["partial"]),
                    -int(entry[1]["failed"]),
                ),
            )[-1]
            preferences.append(_preference_from_bucket(item, key, bucket, confidence="high"))
            continue
        latest = latest_for_item.get(item.id)
        if latest and latest.outcome in {"failed", "partial"}:
            latest_strategy = latest.strategy or _strategy_for_outcome(latest)
            bucket = grouped.get((item.id, latest.tool, latest_strategy))
            fallback = _fallback_preference(item, latest, bucket)
            if fallback:
                preferences.append(fallback)
    return preferences


def _preference_from_bucket(
    item: ObjectiveReadinessItem,
    key: tuple[str, str, str],
    bucket: dict[str, object],
    *,
    confidence: str,
) -> ObjectiveReadinessProofPreference:
    _item_id, tool, strategy = key
    latest = bucket["latest"]
    assert isinstance(latest, ObjectiveReadinessProofOutcome)
    return ObjectiveReadinessProofPreference(
        item_id=item.id,
        tool_kind=tool,
        evidence_label=latest.evidence_label or item.proof.evidence_label,
        strategy=strategy,
        action=latest.proof_action or item.proof.action,
        command_hint=_command_hint_for_strategy(item.id, tool, strategy) or item.proof.command_hint,
        reason=f"Learned from verified objective-readiness proof via {tool}/{strategy}.",
        confidence=confidence,  # type: ignore[arg-type]
        verified_count=int(bucket["verified"]),
        partial_count=int(bucket["partial"]),
        failed_count=int(bucket["failed"]),
        last_outcome=latest.outcome,
    )


def _fallback_preference(
    item: ObjectiveReadinessItem,
    latest: ObjectiveReadinessProofOutcome,
    bucket: dict[str, object] | None = None,
) -> ObjectiveReadinessProofPreference | None:
    if latest.outcome == "waiting_approval":
        return None
    strategy = _fallback_strategy_for(item.id, latest.tool)
    if not strategy:
        return None
    tool = _tool_for_strategy(strategy, latest.tool)
    return ObjectiveReadinessProofPreference(
        item_id=item.id,
        tool_kind=tool,
        evidence_label=latest.evidence_label or item.proof.evidence_label,
        strategy=strategy,
        action=_action_for_strategy(item.id, tool, strategy),
        command_hint=_command_hint_for_strategy(item.id, tool, strategy),
        reason=f"Bias away from repeated {latest.outcome} proof via {latest.tool}: {latest.summary}",
        confidence="medium" if latest.outcome == "failed" else "low",
        failed_count=int(bucket["failed"]) if bucket else (1 if latest.outcome == "failed" else 0),
        partial_count=int(bucket["partial"]) if bucket else (1 if latest.outcome == "partial" else 0),
        verified_count=int(bucket["verified"]) if bucket else 0,
        last_outcome=latest.outcome,
    )


def _strategy_for_outcome(outcome: ObjectiveReadinessProofOutcome) -> str:
    text = f"{outcome.strategy} {outcome.proof_action} {outcome.summary}".lower()
    if "compile" in text:
        return "compile_check"
    if "import" in text:
        return "import_check"
    if "single" in text and "test" in text:
        return "single_test"
    if "dashboard" in text or "api" in text or "timeline" in text or "replay" in text:
        return "dashboard_api_check"
    if "obsidian" in text or "handoff" in text or "resume_prompt" in text:
        return "handoff_refresh"
    if outcome.tool:
        return f"{outcome.tool}_proof"
    return "static_playbook"


def _fallback_strategy_for(item_id: str, tool: str) -> str:
    if tool == "run_tests":
        return "compile_check"
    if tool == "workspace_diff":
        return "workspace_metadata_check"
    if tool == "obsidian_checkpoint":
        return "handoff_refresh"
    if tool == "file_read":
        if item_id in {"durable_task_graph", "compact_context", "repo_map", "replay_audit_trails"}:
            return "dashboard_api_check"
    if tool == "ask_user":
        return "approval_resolution"
    return ""


def _tool_for_strategy(strategy: str, previous_tool: str) -> str:
    if strategy in {"compile_check", "import_check", "single_test"}:
        return "shell" if previous_tool == "run_tests" else "run_tests"
    if strategy in {"workspace_metadata_check", "dashboard_api_check"}:
        return "file_read"
    if strategy == "handoff_refresh":
        return "obsidian_checkpoint"
    if strategy == "approval_resolution":
        return "ask_user"
    return previous_tool


def _action_for_strategy(item_id: str, tool: str, strategy: str) -> str:
    if strategy == "compile_check":
        return "Run a focused compile check as the next smallest objective-readiness proof before broad tests."
    if strategy == "import_check":
        return "Run a focused import check for the touched backend modules before broad tests."
    if strategy == "single_test":
        return "Run the narrowest single relevant test target before broad tests."
    if strategy == "workspace_metadata_check":
        return "Inspect run workspace metadata and confirm source/active workspace separation before retrying a diff."
    if strategy == "dashboard_api_check":
        return f"Inspect the compact API or replay section that directly proves {item_id} instead of rereading broad files."
    if strategy == "handoff_refresh":
        return "Refresh the Obsidian checkpoint and verify memory refs plus resume prompt in the handoff."
    if strategy == "approval_resolution":
        return "Ask the operator to resolve the pending readiness proof approval or choose a non-approval proof."
    return f"Use {tool} with the smallest proof strategy for {item_id}."


def _command_hint_for_strategy(item_id: str, tool: str, strategy: str) -> str:
    if strategy == "compile_check":
        return "python -m compileall backend\\app"
    if strategy == "import_check":
        return "python -c \"import app.engine; import app.objective_readiness\""
    if strategy == "single_test":
        return "python -m pytest backend\\tests\\test_engine_long_loop.py -q"
    if strategy == "workspace_metadata_check":
        return "GET /api/runs/{run_id}/handoff workspace_summary"
    if strategy == "dashboard_api_check":
        return f"GET /api/runs/{{run_id}}/timeline {item_id}"
    if strategy == "handoff_refresh":
        return "obsidian_checkpoint with label objective_readiness"
    return ""


def _workspace_item(run: RunRecord) -> ObjectiveReadinessItem:
    isolation = run.state.workspace_isolation
    if isolation.enabled and isolation.workspace_path:
        return _item(
            "isolated_workspaces",
            "Per-run workspace isolation keeps long-running edits separate from the source workspace.",
            "verified",
            [isolation.summary, f"workspace={isolation.workspace_path}", f"source={isolation.source_path}"],
        )
    return _item(
        "isolated_workspaces",
        "Per-run workspace isolation keeps long-running edits separate from the source workspace.",
        "partial",
        [f"mode={isolation.mode}", isolation.summary or "No isolated workspace summary recorded."],
        "Enable isolated copy/worktree mode for runs that may edit code.",
    )


def _patch_item(run: RunRecord, tool_names: set[str]) -> ObjectiveReadinessItem:
    direct_source_writes = [
        call for call in run.state.tool_calls if call.name == "file_write" and call.ok
    ]
    if {"patch_propose", "patch_apply"}.issubset(tool_names) and not direct_source_writes:
        status = "verified" if run.state.patch_proposals or run.state.patch_applications else "partial"
        return _item(
            "patch_first_editing",
            "Code edits should flow through reviewable patch proposals and approval-gated applications.",
            status,
            [
                "patch_propose and patch_apply are registered.",
                f"patches={len(run.state.patch_proposals)} proposals/{len(run.state.patch_applications)} applications",
            ],
            "Exercise patch_propose on a real edit and verify approval-gated patch_apply." if status == "partial" else "",
        )
    return _item(
        "patch_first_editing",
        "Code edits should flow through reviewable patch proposals and approval-gated applications.",
        "missing",
        [f"direct_file_writes={len(direct_source_writes)}", f"tools={','.join(sorted(tool_names & {'patch_propose', 'patch_apply'}))}"],
        "Route source edits through patch_propose and approval-gated patch_apply.",
    )


def _task_graph_item(run: RunRecord) -> ObjectiveReadinessItem:
    tasks = run.state.task_graph
    if tasks:
        return _item(
            "durable_task_graph",
            "Plans should become durable task nodes with status and evidence.",
            "verified",
            [f"tasks={len(tasks)}", f"current={run.state.current_task_id}"],
        )
    return _item(
        "durable_task_graph",
        "Plans should become durable task nodes with status and evidence.",
        "missing",
        ["No task graph nodes recorded."],
        "Create task graph nodes when planning the next milestone.",
    )


def _context_item(run: RunRecord) -> ObjectiveReadinessItem:
    budget = run.state.context_budget
    snapshot = run.state.context_snapshot
    if snapshot.generated_at and budget.pressure != "high" and snapshot.coverage_status != "critical":
        return _item(
            "compact_context",
            "Prompts should use compact reports and second-brain context instead of raw history.",
            "verified",
            [
                f"snapshot_tokens={snapshot.estimated_tokens}",
                f"target={budget.target_tokens}",
                f"pressure={budget.pressure}",
                f"coverage={snapshot.coverage_status}",
                f"dropped={snapshot.dropped_section_count}",
            ],
        )
    return _item(
        "compact_context",
        "Prompts should use compact reports and second-brain context instead of raw history.",
        "partial",
        [
            f"snapshot={snapshot.generated_at or 'missing'}",
            f"pressure={budget.pressure}",
            f"coverage={snapshot.coverage_status}",
            f"required_missing={','.join(snapshot.required_sections_missing) if snapshot.required_sections_missing else 'none'}",
        ],
        snapshot.recommended_action or "Compile a fresh context snapshot before the next model action.",
    )


def _resume_quality_item(run: RunRecord) -> ObjectiveReadinessItem:
    report = run.state.resume_prompt_quality
    if not report.generated_at:
        report = run.state.handoff_summary.resume_prompt_quality
    if report.generated_at and report.status == "ready":
        return _item(
            "resume_prompt_quality",
            "Resume prompts should give Ornith a concrete next action and compact-context guardrails after compaction.",
            "verified",
            [
                report.summary,
                f"score={report.score}",
                f"concrete_next={report.concrete_next_action}",
                f"context={report.context_coverage_status}",
            ],
        )
    if report.generated_at:
        status = "missing" if report.status == "blocked" else "partial"
        return _item(
            "resume_prompt_quality",
            "Resume prompts should give Ornith a concrete next action and compact-context guardrails after compaction.",
            status,
            [
                report.summary,
                f"score={report.score}",
                f"issues={len(report.issues)}",
                f"context={report.context_coverage_status}",
            ],
            report.recommended_action,
        )
    return _item(
        "resume_prompt_quality",
        "Resume prompts should give Ornith a concrete next action and compact-context guardrails after compaction.",
        "partial",
        ["No resume prompt quality report has been generated."],
        "Generate a resume prompt quality report before trusting resume or auto-resume.",
    )


def _resume_handoff_diff_item(run: RunRecord) -> ObjectiveReadinessItem:
    report = run.state.resume_handoff_diff
    if not report.generated_at:
        report = run.state.handoff_summary.resume_handoff_diff
    if report.generated_at and report.status in {"stable", "no_baseline"}:
        return _item(
            "resume_handoff_diff",
            "Resume preflight baselines should be compared against current handoff quality and context coverage before acting.",
            "verified" if report.status == "stable" else "partial",
            [
                report.summary,
                f"baseline={report.latest_accepted_event_id or 'none'}",
                f"changes={report.changed_count}",
                f"blockers={report.blocker_count}",
            ],
            report.recommended_action if report.status == "no_baseline" else "",
        )
    if report.generated_at:
        status = "missing" if report.status == "blocked" else "partial"
        return _item(
            "resume_handoff_diff",
            "Resume preflight baselines should be compared against current handoff quality and context coverage before acting.",
            status,
            [report.summary, f"changes={report.changed_count}", f"blockers={report.blocker_count}"],
            report.recommended_action,
        )
    return _item(
        "resume_handoff_diff",
        "Resume preflight baselines should be compared against current handoff quality and context coverage before acting.",
        "partial",
        ["No resume handoff drift report has been generated."],
        "Generate a resume handoff drift report before trusting a resumed long loop.",
    )


def _repo_map_item(run: RunRecord) -> ObjectiveReadinessItem:
    repo_map = run.state.repo_map
    if repo_map.summary and repo_map.generated_at:
        return _item(
            "repo_map",
            "Each run should carry a compact repository map with manifests, scripts, tests, and key files.",
            "verified",
            [repo_map.summary, f"tests={len(repo_map.test_commands)}", f"files={len(repo_map.key_files)}"],
        )
    return _item(
        "repo_map",
        "Each run should carry a compact repository map with manifests, scripts, tests, and key files.",
        "missing",
        ["No generated repo map recorded."],
        "Re-orient and rebuild the repository map.",
    )


def _verification_item(run: RunRecord) -> ObjectiveReadinessItem:
    outcomes = run.state.verification_outcomes
    has_evidence = any(item.status == "verified" for item in run.state.acceptance_evidence)
    if outcomes.outcome_count or has_evidence:
        return _item(
            "verification_critic_loop",
            "Long tasks need explicit verification outcomes and critic/risk feedback.",
            "verified",
            [f"outcomes={outcomes.outcome_count}", f"verified_acceptance={sum(1 for item in run.state.acceptance_evidence if item.status == 'verified')}", f"risks={len(run.state.risks)}"],
        )
    return _item(
        "verification_critic_loop",
        "Long tasks need explicit verification outcomes and critic/risk feedback.",
        "partial",
        [f"recommendations={len(run.state.acceptance_recommendations)}", f"criteria={len(run.state.acceptance_criteria)}"],
        "Run the smallest verification action and record the outcome.",
    )


def _failure_recovery_item(run: RunRecord) -> ObjectiveReadinessItem:
    recovery = run.state.recovery_decisions
    if recovery.decision_count or run.state.failure_records:
        return _item(
            "failure_recovery",
            "Failures should be classified and routed through recovery decisions.",
            "verified",
            [f"failures={len(run.state.failure_records)}", f"recovery_decisions={recovery.decision_count}", f"active={recovery.active_recovery}"],
        )
    return _item(
        "failure_recovery",
        "Failures should be classified and routed through recovery decisions.",
        "partial",
        ["No failures observed in this run yet."],
        "Keep failure classification and recovery decisions in handoff when failures occur.",
    )


def _replay_audit_item(run: RunRecord) -> ObjectiveReadinessItem:
    integrity = run.state.report_integrity
    autonomy = run.state.autonomy_decisions
    if integrity.status == "ok" and autonomy.decision_count:
        return _item(
            "replay_audit_trails",
            "Replay and audit trails should explain tool, policy, autonomy, and handoff decisions.",
            "verified",
            [f"integrity={integrity.status}", f"autonomy_decisions={autonomy.decision_count}", f"tool_calls={len(run.state.tool_calls)}"],
        )
    status = "partial" if integrity.run_id or autonomy.decision_count else "missing"
    return _item(
        "replay_audit_trails",
        "Replay and audit trails should explain tool, policy, autonomy, and handoff decisions.",
        status,
        [f"integrity={integrity.status or 'missing'}", f"autonomy_decisions={autonomy.decision_count}"],
        "Refresh report integrity and record autonomy decisions before relying on replay.",
    )


def _obsidian_handoff_item(run: RunRecord) -> ObjectiveReadinessItem:
    handoff = run.state.handoff_summary
    checkpoint_recorded = any(call.name == "obsidian_checkpoint" and call.ok for call in run.state.tool_calls)
    if handoff.resume_prompt and run.state.memory_refs and checkpoint_recorded:
        return _item(
            "obsidian_handoffs",
            "Obsidian-backed handoffs should preserve compact resume context across compaction.",
            "verified",
            [f"memory_refs={len(run.state.memory_refs)}", "checkpoint_tool=ok", handoff.resume_prompt[:160]],
        )
    return _item(
        "obsidian_handoffs",
        "Obsidian-backed handoffs should preserve compact resume context across compaction.",
        "partial",
        [
            f"resume_prompt={'yes' if handoff.resume_prompt else 'no'}",
            f"memory_refs={len(run.state.memory_refs)}",
            f"checkpoint_tool={'yes' if checkpoint_recorded else 'no'}",
        ],
        "Write or refresh the Obsidian checkpoint and memory references.",
    )


def _goal_evolution_item(run: RunRecord) -> ObjectiveReadinessItem:
    goal_interactions = [item for item in run.state.model_interactions if item.kind == "goal"]
    report = run.state.goal_evolution
    if report.decision_count or run.state.proposed_goal or goal_interactions:
        return _item(
            "goal_evolution",
            "The active goal can evolve through Ornith proposals while staying user-confirmed.",
            "verified",
            [
                f"proposed_goal={'yes' if run.state.proposed_goal else 'no'}",
                f"goal_reviews={len(goal_interactions)}",
                f"ledger_decisions={report.decision_count}",
                f"pending={report.pending_count}",
                f"accepted={report.accepted_count}",
                f"rejected={report.rejected_count}",
            ],
        )
    return _item(
        "goal_evolution",
        "The active goal can evolve through Ornith proposals while staying user-confirmed.",
        "partial",
        ["No goal review has occurred in this run yet."],
        "Use /goal review when scope, blockers, or acceptance criteria materially change.",
    )



def _promotion_audit_item(run: RunRecord) -> ObjectiveReadinessItem:
    report = run.state.promotion_audit
    if not report.generated_at:
        report = run.state.handoff_summary.promotion_audit
    if report.generated_at and report.status in {"ready", "not_applicable"}:
        return _item(
            "source_promotion_audit",
            "Source workspace promotion should be gated by a compact audit tying diff, patches, verification, and resume drift together.",
            "verified",
            [
                report.summary,
                f"ready={report.ready_to_promote}",
                f"changed={report.changed_file_count}",
                f"verification={report.latest_verification or 'none'}",
                f"drift={report.resume_drift_status}",
            ],
        )
    if report.generated_at:
        status = "missing" if report.status == "blocked" else "partial"
        return _item(
            "source_promotion_audit",
            "Source workspace promotion should be gated by a compact audit tying diff, patches, verification, and resume drift together.",
            status,
            [
                report.summary,
                f"status={report.status}",
                f"changed={report.changed_file_count}",
                f"issues={len(report.issues)}",
            ],
            report.recommended_action,
        )
    return _item(
        "source_promotion_audit",
        "Source workspace promotion should be gated by a compact audit tying diff, patches, verification, and resume drift together.",
        "partial",
        ["No source promotion audit has been generated."],
        "Generate a promotion audit before requesting source workspace promotion.",
    )


def _git_checkpoint_item(run: RunRecord) -> ObjectiveReadinessItem:
    report = run.state.git_checkpoint
    if not report.generated_at:
        return _item(
            "git_checkpoint_cadence",
            "Long coding runs maintain frequent scoped Git checkpoints and surface GitHub push readiness.",
            "partial",
            ["No Git checkpoint report has been generated for this run yet."],
            "Run git_checkpoint so Ornith and the operator can see commit and push posture.",
        )
    if report.status == "not_repo":
        return _item(
            "git_checkpoint_cadence",
            "Long coding runs maintain frequent scoped Git checkpoints and surface GitHub push readiness.",
            "missing",
            [report.summary],
            "Use a Git-backed workspace before claiming commit cadence readiness.",
        )
    if report.remote_count == 0:
        return _item(
            "git_checkpoint_cadence",
            "Long coding runs maintain frequent scoped Git checkpoints and surface GitHub push readiness.",
            "partial",
            [report.summary, "No remote is configured for GitHub push readiness."],
            "Configure a GitHub remote; continue making scoped local commits meanwhile.",
        )
    if report.status in {"verify_first", "commit_recommended", "push_recommended"}:
        return _item(
            "git_checkpoint_cadence",
            "Long coding runs maintain frequent scoped Git checkpoints and surface GitHub push readiness.",
            "partial",
            [report.summary, report.recommended_action],
            report.recommended_action,
        )
    return _item(
        "git_checkpoint_cadence",
        "Long coding runs maintain frequent scoped Git checkpoints and surface GitHub push readiness.",
        "verified",
        [report.summary, f"remote_count={report.remote_count}", f"github_remote_count={report.github_remote_count}"],
    )

def _item(
    item_id: str,
    requirement: str,
    status: str,
    evidence: list[str],
    next_action: str = "",
) -> ObjectiveReadinessItem:
    return ObjectiveReadinessItem(
        id=item_id,
        requirement=requirement,
        status=status,  # type: ignore[arg-type]
        evidence=[item for item in evidence if item],
        next_action=next_action,
        proof=_proof_for(item_id),
    )


def _proof_for(item_id: str) -> ObjectiveReadinessProof:
    return _PLAYBOOK.get(item_id, ObjectiveReadinessProof(
        tool_kind="ask_user",
        evidence_label="objective",
        action="Ask the operator which proof should satisfy this readiness item.",
        success_signal="The readiness item has an explicit proof method recorded.",
    ))


_PLAYBOOK: dict[str, ObjectiveReadinessProof] = {
    "isolated_workspaces": ObjectiveReadinessProof(
        tool_kind="workspace_diff",
        evidence_label="workspace",
        strategy="workspace_diff",
        action="Inspect workspace isolation metadata and confirm active/source paths are separate before promoting edits.",
        command_hint="Dashboard Workspace Isolation panel or GET /api/runs/{run_id}/handoff",
        success_signal="Run state records enabled isolation with distinct source and active workspace paths.",
    ),
    "patch_first_editing": ObjectiveReadinessProof(
        tool_kind="patch_propose",
        evidence_label="edit",
        strategy="patch_review",
        action="Propose a tiny reviewed patch, then verify the patch proposal/application ledger instead of writing source directly.",
        command_hint="patch_propose with a minimal diff; patch_apply only after approval",
        success_signal="Patch proposal or application exists and no successful direct file_write bypass is present.",
        requires_approval=True,
    ),
    "durable_task_graph": ObjectiveReadinessProof(
        tool_kind="file_read",
        evidence_label="task_graph",
        strategy="dashboard_api_check",
        action="Read the run state or timeline and confirm current plan steps have durable task nodes with status and evidence.",
        command_hint="GET /api/runs/{run_id}/timeline",
        success_signal="Task graph contains task nodes and a current_task_id for the active unit of work.",
    ),
    "compact_context": ObjectiveReadinessProof(
        tool_kind="file_read",
        evidence_label="context",
        strategy="dashboard_api_check",
        action="Inspect the compiled context snapshot and confirm compact sections fit under the configured token target.",
        command_hint="GET /api/runs/{run_id}/timeline context_snapshot",
        success_signal="Context snapshot has generated_at, estimated_tokens, and low or medium pressure.",
    ),
    "resume_prompt_quality": ObjectiveReadinessProof(
        tool_kind="file_read",
        evidence_label="resume",
        strategy="dashboard_api_check",
        action="Inspect resume-quality output and confirm the handoff has a concrete next action plus compact-context guardrails.",
        command_hint="GET /api/runs/{run_id}/resume-quality",
        success_signal="Resume prompt quality report is ready with concrete_next_action=true and no blockers.",
    ),
    "source_promotion_audit": ObjectiveReadinessProof(
        tool_kind="file_read",
        evidence_label="promotion",
        strategy="dashboard_api_check",
        action="Inspect promotion-audit output and confirm source promotion is ready or has a concrete verification/drift blocker.",
        command_hint="GET /api/runs/{run_id}/promotion-audit",
        success_signal="Promotion audit is ready/not applicable or explains the exact verification/drift action required before source promotion.",
    ),
    "resume_handoff_diff": ObjectiveReadinessProof(
        tool_kind="file_read",
        evidence_label="resume",
        strategy="dashboard_api_check",
        action="Inspect resume-handoff drift output and confirm current context is stable against the accepted preflight baseline.",
        command_hint="GET /api/runs/{run_id}/resume-handoff-diff",
        success_signal="Resume handoff drift report is stable or explains why a fresh preflight is required before acting.",
    ),
    "repo_map": ObjectiveReadinessProof(
        tool_kind="file_read",
        evidence_label="repo_map",
        strategy="dashboard_api_check",
        action="Inspect the repo map for manifests, scripts, test commands, key files, and language mix.",
        command_hint="GET /api/runs/{run_id}/timeline repo_map",
        success_signal="Repo map has generated_at, summary, and at least one useful manifest/script/key-file signal when present.",
    ),
    "verification_critic_loop": ObjectiveReadinessProof(
        tool_kind="run_tests",
        evidence_label="verification",
        strategy="smallest_test",
        action="Run the smallest relevant verification command and ensure the result updates verification outcomes or acceptance evidence.",
        command_hint="run_tests with the narrowest available test command",
        success_signal="Verification outcomes or acceptance evidence record a verified proof label for the run.",
    ),
    "failure_recovery": ObjectiveReadinessProof(
        tool_kind="run_tests",
        evidence_label="recovery",
        strategy="focused_failure_recovery",
        action="Exercise or inspect a failing proof path and confirm failures become recovery decisions with an alternate strategy.",
        command_hint="Use a focused failing verification in tests, then inspect /recovery-decisions",
        success_signal="Recovery decision report records active or historical recovery evidence for the failure.",
    ),
    "replay_audit_trails": ObjectiveReadinessProof(
        tool_kind="file_read",
        evidence_label="replay",
        strategy="dashboard_api_check",
        action="Open replay or timeline output and confirm report integrity, autonomy decisions, tools, and handoff sections are present.",
        command_hint="GET /api/runs/{run_id}/replay or /api/runs/{run_id}/replay.md",
        success_signal="Report integrity is ok and replay includes compact policy, autonomy, tool, and handoff evidence.",
    ),
    "obsidian_handoffs": ObjectiveReadinessProof(
        tool_kind="obsidian_checkpoint",
        evidence_label="checkpoint",
        strategy="handoff_refresh",
        action="Write or refresh an Obsidian checkpoint and confirm memory refs plus resume prompt survive in the handoff.",
        command_hint="obsidian_checkpoint with label objective_readiness",
        success_signal="Run state has memory_refs and handoff resume_prompt populated after checkpoint.",
    ),
    "goal_evolution": ObjectiveReadinessProof(
        tool_kind="ask_user",
        evidence_label="goal",
        strategy="goal_review",
        action="Trigger /goal review only when scope, blockers, acceptance criteria, or stop conditions materially changed.",
        command_hint="POST /api/runs/{run_id}/goal/review or dashboard Review",
        success_signal="Goal review produces a model interaction or pending goal proposal, and active goal changes only after user confirmation.",
        requires_approval=True,
    ),
    "git_checkpoint_cadence": ObjectiveReadinessProof(
        tool_kind="git_checkpoint",
        evidence_label="git",
        strategy="commit_readiness",
        action="Inspect Git checkpoint posture before handoff and after verified changes.",
        command_hint="git_checkpoint or GET /api/runs/{run_id}/git-checkpoint",
        success_signal="Git checkpoint report shows repository status, changed files, remotes, and commit/push recommendation.",
    ),
}

