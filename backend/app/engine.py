from __future__ import annotations

import asyncio
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .action_context import build_action_context_pack
from .action_normalizer import normalize_model_action
from .action_readiness import build_action_readiness, rank_acceptance_recommendations
from .action_readiness_decisions import build_action_readiness_decision_report
from .artifact_verification import (
    artifact_creation_action,
    artifact_verification_command,
    expected_artifact_exists,
    expected_artifact_suffix,
)
from .acceptance import compact_label_progress, infer_required_labels
from .autonomy_decisions import build_autonomy_decision_report
from .checkpoint_quality import build_checkpoint_quality
from .completion_audit import build_completion_audit
from .config import AppConfig
from .context_compiler import ContextCompiler
from .events import EventBroker
from .goal_evolution import (
    build_goal_evolution_report,
    record_goal_proposal,
    record_goal_unchanged,
    resolve_goal_proposal,
)
from .goal_classification import is_harness_improvement_goal
from .memory import MemoryContext, ObsidianMemory
from .model_eval import run_ornith_fixture_eval
from .model_client import ModelError, OpenAICompatibleModel
from .model_profile import extract_json_object_result, profile_for
from .model_quality import build_model_prompt_quality_report
from .objective_readiness import build_objective_readiness
from .operator_dispatches import build_operator_dispatch_ledger
from .ornith_preflight_actions import build_ornith_preflight_action_ledger
from .persistence import RunStore, make_run_id, utc_now
from .post_action_retry import (
    build_post_action_retry_report,
    mark_post_action_retry_selected,
    propose_post_action_retry,
    resolve_post_action_retry,
    retry_action_from_decision,
)
from .policy_simulation import build_policy_simulation
from .profile_adaptation import build_model_profile_adaptation_proposal, compact_adaptation_review
from .readiness_completion import build_readiness_completion
from .repo_map import build_repo_map
from .recovery_decisions import build_recovery_decision_report
from .replay import build_replay_bundle
from .report_integrity import build_report_integrity
from .resume_decisions import build_resume_decision_report
from .resume_quality import build_resume_prompt_quality
from .run_health import build_run_health
from .run_progress import build_run_progress
from .self_scaffold import build_self_scaffold_report, build_self_scaffold_review_report, build_self_scaffold_rollback_intent_report
from .source_evidence import build_source_evidence_preview
from .verification_outcomes import build_verification_outcome_report
from .schemas import (
    AcceptanceCriterionEvidence,
    AcceptanceEvidenceRecommendation,
    AcceptanceRecommendationTrace,
    ActionReadinessDecisionRecord,
    ContextBudget,
    FailureRecord,
    HandoffBundle,
    ModelInteractionRecord,
    OperatorActionDispatchRequest,
    OperatorActionDispatchResult,
    OperatorActionQueueItem,
    OrnithLaunchChecklistItem,
    OrnithLaunchChecklistReport,
    OrnithPreflightActionLedgerReport,
    OperatorDispatchLedgerReport,
    OperatorDispatchRestartSmokeLedgerEntry,
    OperatorDispatchRestartSmokeLedgerReport,
    OperatorDispatchRestartSmokeReport,
    OperatorActionQueueReport,
    PatchApplication,
    PatchProposal,
    ObjectiveReadinessProof,
    ObjectiveReadinessProofOutcome,
    ReadinessRehearsalLedgerEntry,
    ReadinessRehearsalLedgerReport,
    ReadinessRehearsalReport,
    ReadinessRehearsalStep,
    RecoveryPlan,
    RunHealthReport,
    RunHealthSignal,
    RunLease,
    RunRecord,
    RunState,
    SourceEvidencePreviewReport,
    TaskNode,
    ToolCallRecord,
    WorkspaceIsolation,
)
from .tools import TOOL_NAMES, ToolRegistry, ToolResult, ToolRunner, redact_secrets
from .workspace import WorkspaceManager, build_workspace_diff


MILESTONES = ("orient", "plan", "act", "verify", "checkpoint", "decide")
STARTUP_RESUME_BLOCKER_PREFIX = "Supervisor recovered stale "
STARTUP_RESUME_BLOCKER_ACTION = "resume explicitly from handoff"
STARTUP_ORPHAN_APPROVAL_BLOCKER = "Supervisor found waiting_approval status without a pending approval after startup."
LOOP_STEP_LIMIT_BLOCKER = "Reached MAX_LOOP_STEPS."
READINESS_REHEARSAL_OBJECTIVE_ITEMS = (
    "isolated_workspaces",
    "patch_first_editing",
    "durable_task_graph",
    "compact_context",
    "resume_prompt_quality",
    "repo_map",
    "verification_critic_loop",
    "failure_recovery",
    "replay_audit_trails",
    "obsidian_handoffs",
    "goal_evolution",
    "git_checkpoint_cadence",
    "source_promotion_audit",
    "resume_handoff_diff",
)


class AgentLoopEngine:
    def __init__(
        self,
        config: AppConfig,
        store: RunStore,
        memory: ObsidianMemory,
        model: OpenAICompatibleModel,
        broker: EventBroker,
    ) -> None:
        self.config = config
        self.store = store
        self.memory = memory
        self.model = model
        self.broker = broker
        self.registry = ToolRegistry(config)
        self.model_profile = profile_for(config.model_name, config.model_profile)
        self.context_compiler = ContextCompiler(
            min(config.context_target_tokens, self.model_profile.context_target_tokens),
            self.model_profile,
        )
        self.workspace_manager = WorkspaceManager(
            enabled=config.enable_workspace_isolation,
            mode=config.workspace_isolation_mode,
            root=config.workspace_root,
            copy_limit_files=config.workspace_copy_limit_files,
        )
        self.engine_id = f"engine-{uuid4().hex[:8]}"
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._heartbeat_tasks: dict[str, asyncio.Task[None]] = {}
        self.supervisor_report: dict[str, Any] = {
            "status": "not_run",
            "ran_at": "",
            "checked": 0,
            "recovered": 0,
            "auto_resumed": 0,
            "waiting_approval": 0,
            "live": 0,
            "stale": 0,
            "auto_resume_enabled": config.enable_supervisor_auto_resume,
            "auto_resume_max_runs": config.supervisor_auto_resume_max_runs,
            "readiness_rehearsal_ledger": ReadinessRehearsalLedgerReport().model_dump(),
            "operator_dispatch_restart_smoke_ledger": OperatorDispatchRestartSmokeLedgerReport().model_dump(),
            "readiness_smoke_attention_count": 0,
            "operator_dispatch_restart_smoke_attention_count": 0,
            "ornith_preflight_attention_count": 0,
            "source_evidence_attention_count": 0,
            "self_scaffold_attention_count": 0,
            "self_scaffold_rollback_attention_count": 0,
            "pending_approval_count": 0,
            "operator_recovery_count": 0,
            "operator_blocker_count": 0,
            "operator_attention_count": 0,
            "operator_attention_blocked_count": 0,
            "operator_attention_watch_count": 0,
            "operator_action_queue": OperatorActionQueueReport().model_dump(),
            "runs": [],
        }

    async def create_run(
        self,
        *,
        goal: str,
        title: str | None = None,
        workspace_path: str | None = None,
        acceptance_criteria: list[str] | None = None,
        tool_profile: str = "balanced",
        approval_mode: str | None = None,
        web_enabled: bool = True,
        browser_enabled: bool = True,
        desktop_enabled: bool = True,
        wall_clock_limit_minutes: int | None = None,
        checkpoint_every_steps: int | None = None,
    ) -> RunRecord:
        source_workspace = Path(workspace_path).resolve() if workspace_path else self.config.workspace_path
        run_id = make_run_id()
        workspace_isolation = self.workspace_manager.prepare_run_workspace(run_id, source_workspace)
        workspace = workspace_isolation.workspace_path or str(source_workspace)
        run = self.store.create_run(
            goal=goal,
            title=title or self._title_from_goal(goal),
            workspace_path=workspace,
            acceptance_criteria=acceptance_criteria or [],
            tool_profile=tool_profile,
            approval_mode=approval_mode or self.config.approval_mode,
            web_enabled=web_enabled and self.config.enable_web_tools,
            browser_enabled=browser_enabled and self.config.enable_browser_tools,
            desktop_enabled=desktop_enabled and self.config.enable_desktop_control,
            wall_clock_limit_minutes=wall_clock_limit_minutes or self.config.loop_wall_clock_limit_minutes,
            checkpoint_every_steps=checkpoint_every_steps or self.config.checkpoint_every_steps,
            context_target_tokens=self.config.context_target_tokens,
            run_id=run_id,
            workspace_isolation=workspace_isolation,
        )
        self.memory.append_run_started(run)
        await self._event(run.id, "run_started", "Run created and Obsidian start checkpoint written.")
        self._ensure_task(run.id)
        return self.store.get_run(run.id)

    async def pause_run(self, run_id: str) -> RunRecord:
        run = self.store.update_run(run_id, status="paused")
        await self._event(run_id, "control", "Run paused.")
        self._cancel_task(run_id)
        self._release_run_lease(run_id, "pause")
        run = self.store.get_run(run_id)
        self.memory.append_checkpoint(run, run.state, "paused")
        return run

    async def resume_run(self, run_id: str) -> RunRecord:
        return await self._resume_run_with_preflight(run_id, source="manual")

    async def _resume_run_with_preflight(
        self,
        run_id: str,
        *,
        source: str,
        allow_recovery: bool = False,
        allow_user_attention: bool = False,
        start_task: bool = True,
    ) -> RunRecord:
        run = self.store.get_run(run_id)
        initial_integrity = self._build_report_integrity(run, run.state)
        integrity_refresh_needed = initial_integrity.status != "ok"
        if run.status not in {"completed", "canceled"}:
            state = run.state
            self._reload_anchor_context(run, state)
            cleared_approval_wait = False
            cleared_blocked_state = False
            if source == "manual" and self._clear_startup_resume_blocker(state):
                self._append_unique(
                    state.facts_learned,
                    "Manual resume accepted the recovered startup handoff blocker.",
                )
            if source == "manual" and self._clear_orphan_startup_approval_blocker(run_id, state):
                cleared_approval_wait = True
                self._append_unique(
                    state.facts_learned,
                    "Manual resume cleared recovered waiting_approval state after confirming no pending approvals.",
                )
            if source == "manual" and self._clear_resolved_approval_wait_state(run_id, state):
                cleared_approval_wait = True
                self._append_unique(
                    state.facts_learned,
                    "Manual resume cleared resolved approval wait state after confirming no pending approvals.",
                )
            if source in {"manual", "recovery"} and self._clear_loop_step_limit_blocker(state):
                cleared_blocked_state = True
                self._append_unique(
                    state.facts_learned,
                    "Resume cleared stale MAX_LOOP_STEPS blocker after the configured loop cap increased.",
                )
            self._reconcile_approved_objective_readiness_approvals(run_id, state)
            status_update = run.status
            if cleared_approval_wait and run.status == "waiting_approval":
                status_update = "paused"
            if cleared_blocked_state and run.status == "blocked" and not state.blockers:
                status_update = "paused"
            run = self.store.update_run(run_id, status=status_update, state=state)
        integrity = self._build_report_integrity(run, run.state)
        if integrity.status != "ok":
            state = run.state
            state.report_integrity = integrity
            state.handoff_summary = self._make_handoff(run, state)
            run = self.store.update_run(run_id, state=state)
            await self._event(
                run_id,
                "report_integrity_refresh",
                integrity.summary,
                {
                    "report_integrity": integrity.model_dump(),
                    "previous_report_integrity": initial_integrity.model_dump(),
                },
            )
        elif integrity_refresh_needed:
            state = run.state
            state.report_integrity = integrity
            state.handoff_summary.report_integrity = integrity
            run = self.store.update_run(run_id, state=state)
            await self._event(
                run_id,
                "report_integrity_refresh",
                "Refreshed compact handoff and report integrity before resume preflight.",
                {
                    "report_integrity": integrity.model_dump(),
                    "previous_report_integrity": initial_integrity.model_dump(),
                },
            )
        simulation = self._build_policy_simulation(run, run.state)
        accepted, reason = self._resume_preflight_decision(
            run,
            simulation,
            source=source,
            allow_recovery=allow_recovery,
            allow_user_attention=allow_user_attention,
        )
        await self._record_resume_preflight(run.id, source, simulation, accepted, reason)
        if not accepted:
            state = run.state
            state.next_step = simulation.next_action or state.next_step
            state.handoff_summary = self._make_handoff(run, state)
            return self.store.update_run(run_id, state=state)

        run = self.store.update_run(run_id, status="queued")
        await self._event(
            run_id,
            "control",
            f"Run resumed after {source} preflight.",
            {"source": source, "preflight_reason": reason},
        )
        if start_task:
            self._ensure_task(run_id)
        return run

    def _resume_preflight_decision(
        self,
        run: RunRecord,
        simulation: Any,
        *,
        source: str,
        allow_recovery: bool = False,
        allow_user_attention: bool = False,
    ) -> tuple[bool, str]:
        state = run.state
        if run.status in {"completed", "canceled"}:
            return False, f"Run is {run.status}; create a new run to continue."
        if (state.proposed_goal or run.status == "waiting_goal_confirmation") and source != "goal_confirmation":
            return False, "Pending goal proposal requires confirmation before resume."
        if simulation.safe_to_resume:
            return True, f"Policy simulation accepted resume: {simulation.summary}"
        if allow_recovery and simulation.policy_action == "recover" and state.recovery_plan.status == "active":
            return True, "Explicit recovery resume accepted the active recovery simulation."
        if allow_user_attention and simulation.policy_action in {"ask_user", "pause"}:
            return True, f"User steering accepted policy action {simulation.policy_action}."
        if source == "manual" and simulation.policy_action == "recover" and state.recovery_plan.status != "active":
            return True, "Manual resume accepted recover policy because no active recovery plan exists."
        return False, f"Resume preflight blocked by policy simulation: {simulation.summary} {simulation.reason}".strip()

    def _clear_startup_resume_blocker(self, state: RunState) -> bool:
        original_count = len(state.blockers)
        state.blockers = [
            blocker
            for blocker in state.blockers
            if not (
                blocker.startswith(STARTUP_RESUME_BLOCKER_PREFIX)
                and STARTUP_RESUME_BLOCKER_ACTION in blocker
            )
        ]
        return len(state.blockers) != original_count

    def _clear_orphan_startup_approval_blocker(self, run_id: str, state: RunState) -> bool:
        if self.store.list_approvals(run_id, status="pending"):
            return False
        original_count = len(state.blockers)
        state.blockers = [
            blocker
            for blocker in state.blockers
            if blocker != STARTUP_ORPHAN_APPROVAL_BLOCKER
        ]
        return len(state.blockers) != original_count

    def _clear_loop_step_limit_blocker(self, state: RunState) -> bool:
        if state.step_count >= self.config.max_loop_steps:
            return False
        original_count = len(state.blockers)
        state.blockers = [blocker for blocker in state.blockers if blocker != LOOP_STEP_LIMIT_BLOCKER]
        changed = len(state.blockers) != original_count
        if changed and state.next_step == "Ask user whether to continue.":
            state.next_step = "Resume from compact handoff under the updated loop step budget."
        return changed

    def _clear_resolved_approval_wait_state(self, run_id: str, state: RunState) -> bool:
        if self.store.list_approvals(run_id, status="pending"):
            return False
        changed = False
        if state.active_tool == "ask_user":
            state.active_tool = ""
            changed = True
        if "approval" in state.next_step.lower() or "active tool" in state.next_step.lower():
            state.next_step = "Resume from the compact handoff after resolved approval state."
            changed = True
        return changed

    async def _record_resume_preflight(
        self,
        run_id: str,
        source: str,
        simulation: Any,
        accepted: bool,
        reason: str,
    ) -> None:
        kind = "resume_preflight" if accepted else "resume_preflight_blocked"
        outcome = "accepted" if accepted else "blocked"
        await self._event(
            run_id,
            kind,
            f"Resume preflight {outcome} for {source}: {reason}",
            {
                "source": source,
                "accepted": accepted,
                "reason": reason,
                "policy_simulation": simulation.model_dump(),
            },
        )

    async def cancel_run(self, run_id: str) -> RunRecord:
        run = self.store.update_run(run_id, status="canceled")
        await self._event(run_id, "control", "Run canceled.")
        self._cancel_task(run_id)
        self._release_run_lease(run_id, "cancel")
        run = self.store.get_run(run_id)
        self.memory.append_final(run, run.state)
        return run

    async def steer_run(self, run_id: str, message: str) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        state.facts_learned.append(f"User steering: {message}")
        state.next_step = "Apply latest user steering at the next loop step."
        state.milestone = "orient"
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, state=state)
        await self._event(run_id, "user_steer", message)
        if run.status in {"paused", "blocked", "waiting_approval", "waiting_goal_confirmation"}:
            await self._resume_run_with_preflight(run_id, source="steer", allow_user_attention=True)
        return self.store.get_run(run_id)

    async def propose_goal(self, run_id: str, proposed_goal: str, reason: str = "") -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        state.proposed_goal = proposed_goal
        state.goal_revision_reason = reason or "User requested goal refinement."
        state.next_step = "Wait for goal revision confirmation."
        approval = self.store.create_approval(
            run_id,
            "goal_update",
            {"proposed_goal": proposed_goal, "reason": state.goal_revision_reason},
            f"Confirm updated goal: {proposed_goal}",
        )
        record_goal_proposal(
            state,
            run,
            proposed_goal=proposed_goal,
            reason=state.goal_revision_reason,
            source="manual",
            approval_id=int(approval.get("id") or 0),
        )
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, status="waiting_goal_confirmation", state=state)
        await self._event(
            run_id,
            "goal_proposed",
            state.goal_revision_reason,
            {**approval, "goal_evolution": state.goal_evolution.model_dump()},
        )
        await self._workstream(
            run_id,
            phase="approval",
            role="operator",
            title="Goal Confirmation Needed",
            summary="Ornith proposed an updated goal and needs confirmation before continuing.",
            rationale=state.goal_revision_reason,
            next_action=state.next_step,
            severity="blocked",
            refs={"approval_id": approval.get("id"), "approval_kind": "goal_update"},
        )
        return run

    async def review_goal(self, run_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        pending_goal_approvals = [
            approval
            for approval in self.store.list_approvals(run_id, status="pending")
            if approval["action_kind"] == "goal_update"
        ]
        if state.proposed_goal or pending_goal_approvals:
            state.next_step = "Wait for goal revision confirmation."
            state.handoff_summary = self._make_handoff(run, state)
            return self.store.update_run(run_id, status="waiting_goal_confirmation", state=state)

        goal_proposal = await self._maybe_propose_goal_update(run, state, force=True)
        if goal_proposal:
            state.proposed_goal = goal_proposal["proposed_goal"]
            state.goal_revision_reason = goal_proposal["reason"]
            state.next_step = "Wait for goal revision confirmation."
            approval = self.store.create_approval(run_id, "goal_update", goal_proposal, goal_proposal["reason"])
            record_goal_proposal(
                state,
                run,
                proposed_goal=goal_proposal["proposed_goal"],
                reason=goal_proposal["reason"],
                source="manual_review",
                approval_id=int(approval.get("id") or 0),
            )
            state.handoff_summary = self._make_handoff(run, state)
            run = self.store.update_run(run_id, status="waiting_goal_confirmation", state=state)
            self.memory.append_checkpoint(run, state, "waiting_goal_confirmation")
            await self._event(
                run_id,
                "goal_proposed",
                goal_proposal["reason"],
                {**approval, "goal_evolution": state.goal_evolution.model_dump()},
            )
            await self._workstream(
                run_id,
                phase="approval",
                role="operator",
                title="Goal Confirmation Needed",
                summary="Ornith proposed an updated goal and needs confirmation before continuing.",
                rationale=goal_proposal["reason"],
                next_action=state.next_step,
                severity="blocked",
                refs={"approval_id": approval.get("id"), "approval_kind": "goal_update"},
            )
            return run

        self._append_unique(state.facts_learned, "Manual /goal review kept the active goal unchanged.")
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, state=state)
        await self._event(
            run_id,
            "goal_review",
            "Ornith goal review kept the active goal unchanged.",
            {"goal_evolution": state.goal_evolution.model_dump()},
        )
        return run

    async def refresh_workspace_diff(self, run_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        source_path = run.state.workspace_isolation.source_path or run.workspace_path
        runner = ToolRunner(Path(run.workspace_path), self.config)
        result = await runner.execute("workspace_diff", {"source_path": source_path}, approved=True)
        await self._record_tool_result(run_id, result)
        return self.store.get_run(run_id)

    async def request_workspace_promotion(
        self,
        run_id: str,
        *,
        files: list[str] | None = None,
        include_deletions: bool = False,
    ) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        source_path = state.workspace_isolation.source_path
        if not source_path or source_path == run.workspace_path:
            state.blockers.append("No separate source workspace is available for promotion.")
            state.next_step = "Continue inside the active workspace or configure workspace isolation."
            state.handoff_summary = self._make_handoff(run, state)
            return self.store.update_run(run_id, status="paused", state=state)
        diff = build_workspace_diff(Path(source_path), Path(run.workspace_path), files=files or None, max_files=20, max_diff_chars=1200)
        state.workspace_diff = diff
        if diff.total_files == 0:
            state.facts_learned.append("No isolated workspace changes are available to promote.")
            state.next_step = "Continue work in the isolated workspace or refresh the diff after changes."
            state.handoff_summary = self._make_handoff(run, state)
            return self.store.update_run(run_id, status="paused", state=state)
        pending = [
            approval
            for approval in self.store.list_approvals(run_id, status="pending")
            if approval["action_kind"] == "workspace_promote"
        ]
        if pending:
            state.active_tool = "workspace_promote"
            state.next_step = "Wait for existing workspace promotion approval in the dashboard."
            self._append_unique(
                state.facts_learned,
                "Reused existing pending workspace promotion approval instead of creating a duplicate.",
            )
            state.handoff_summary = self._make_handoff(run, state)
            run = self.store.update_run(run_id, status="waiting_approval", state=state)
            await self._event(
                run_id,
                "approval_required",
                "Existing pending workspace promotion approval is still waiting.",
                pending[0],
            )
            return run
        preview = self._workspace_diff_preview(diff)
        approval = self.store.create_approval(
            run_id,
            "workspace_promote",
            {
                "tool_name": "workspace_promote",
                "args": {
                    "source_path": source_path,
                    "files": files or [],
                    "include_deletions": include_deletions,
                },
                "preview": preview,
            },
            f"Promote isolated workspace changes back to the source workspace: {diff.summary}",
        )
        state.active_tool = "workspace_promote"
        state.next_step = "Wait for user approval before promoting isolated workspace changes to source."
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, status="waiting_approval", state=state)
        await self._event(run_id, "approval_required", "Workspace promotion requires approval.", approval)
        return run

    def get_approval_reviews(self, run_id: str, status: str | None = None) -> list[dict[str, Any]]:
        self.store.get_run(run_id)
        if status is not None and status not in {"pending", "approved", "rejected"}:
            raise ValueError("Approval status must be pending, approved, or rejected.")
        approvals = self.store.list_approvals(run_id, status=status)
        reviews: list[dict[str, Any]] = []
        for approval in approvals:
            payload = approval.get("payload") if isinstance(approval.get("payload"), dict) else {}
            preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
            reviews.append(
                {
                    "id": int(approval.get("id") or 0),
                    "run_id": str(approval.get("run_id") or run_id),
                    "action_kind": str(approval.get("action_kind") or "steer"),
                    "status": str(approval.get("status") or "pending"),
                    "reason": redact_secrets(str(approval.get("reason") or "")),
                    "created_at": str(approval.get("created_at") or ""),
                    "resolved_at": str(approval.get("resolved_at") or ""),
                    "preview": preview,
                    "files": [str(item) for item in payload.get("files", [])] if isinstance(payload.get("files"), list) else [],
                    "payload_keys": sorted(str(key) for key in payload.keys() if str(key) != "high_risk"),
                    "high_risk": bool(payload.get("high_risk")) or self._approval_is_high_risk(str(approval.get("action_kind") or "")),
                    "reviewed": bool(approval.get("status") in {"approved", "rejected"}),
                    "review_count": 1 if approval.get("status") in {"approved", "rejected"} else 0,
                    "latest_reviewed_at": str(approval.get("resolved_at") or ""),
                    "latest_review_event_id": 0,
                }
            )
        return reviews

    async def request_patch_apply_approval(self, run_id: str, patch_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        proposal = next((item for item in reversed(state.patch_proposals) if item.id == patch_id), None)
        if proposal is None:
            raise ValueError(f"Patch proposal {patch_id} was not found.")
        if proposal.status not in {"pending", "approved"}:
            raise ValueError(f"Patch proposal {patch_id} is not pending review.")
        pending = [
            approval
            for approval in self.store.list_approvals(run_id, status="pending")
            if approval.get("action_kind") == "patch_apply"
            and isinstance(approval.get("payload"), dict)
            and isinstance(approval["payload"].get("args"), dict)
            and str(approval["payload"]["args"].get("patch_id") or "") == proposal.id
        ]
        if pending:
            state.active_tool = "patch_apply"
            state.next_step = f"Wait for existing patch apply approval for `{proposal.id}`."
            self._append_unique(state.facts_learned, f"Reused existing pending patch apply approval for {proposal.id}.")
            state.handoff_summary = self._make_handoff(run, state)
            run = self.store.update_run(run_id, status="waiting_approval", state=state)
            await self._event(run_id, "approval_required", f"Existing pending patch apply approval for {proposal.id} is still waiting.", pending[0])
            return run
        approval = self.store.create_approval(
            run_id,
            "patch_apply",
            {
                "tool_name": "patch_apply",
                "args": {"patch_id": proposal.id, "diff": proposal.diff},
                "preview": self._patch_apply_approval_preview(proposal),
                "files": proposal.files,
                "summary": proposal.summary,
                "high_risk": True,
            },
            f"Apply patch proposal {proposal.id}: {proposal.title}",
        )
        state.active_tool = "patch_apply"
        state.next_step = f"Wait for approval to apply patch proposal `{proposal.id}`."
        self._append_unique(state.facts_learned, f"Requested approval to apply patch proposal {proposal.id}.")
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, status="waiting_approval", state=state)
        await self._event(run_id, "approval_required", f"Patch apply approval required for {proposal.id}.", approval)
        return run

    async def request_patch_rollback_approval(self, run_id: str, patch_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        application = next(
            (
                item
                for item in reversed(state.patch_applications)
                if item.patch_id == patch_id and item.status == "applied" and item.backup_id and item.manifest_path
            ),
            None,
        )
        if application is None:
            raise ValueError(f"Applied patch {patch_id} with rollback manifest was not found.")
        if any(item.status == "rolled_back" and item.patch_id == patch_id for item in state.patch_applications):
            raise ValueError(f"Patch {patch_id} has already been rolled back.")
        pending = [
            approval
            for approval in self.store.list_approvals(run_id, status="pending")
            if approval.get("action_kind") == "patch_rollback"
            and isinstance(approval.get("payload"), dict)
            and isinstance(approval["payload"].get("args"), dict)
            and (
                str(approval["payload"]["args"].get("patch_id") or "") == application.patch_id
                or str(approval["payload"]["args"].get("backup_id") or "") == application.backup_id
            )
        ]
        if pending:
            state.active_tool = "patch_rollback"
            state.next_step = f"Wait for existing patch rollback approval for `{application.patch_id}`."
            self._append_unique(state.facts_learned, f"Reused existing pending patch rollback approval for {application.patch_id}.")
            state.handoff_summary = self._make_handoff(run, state)
            run = self.store.update_run(run_id, status="waiting_approval", state=state)
            await self._event(run_id, "approval_required", f"Existing pending patch rollback approval for {application.patch_id} is still waiting.", pending[0])
            return run
        approval = self.store.create_approval(
            run_id,
            "patch_rollback",
            {
                "tool_name": "patch_rollback",
                "args": {
                    "patch_id": application.patch_id,
                    "backup_id": application.backup_id,
                    "manifest_path": application.manifest_path,
                },
                "preview": self._patch_rollback_approval_preview(application),
                "files": application.files,
                "summary": application.summary,
                "high_risk": True,
            },
            f"Rollback patch {application.patch_id} from backup {application.backup_id}.",
        )
        state.active_tool = "patch_rollback"
        state.next_step = f"Wait for approval to rollback patch `{application.patch_id}`."
        self._append_unique(state.facts_learned, f"Requested approval to rollback patch {application.patch_id}.")
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, status="waiting_approval", state=state)
        await self._event(run_id, "approval_required", f"Patch rollback approval required for {application.patch_id}.", approval)
        return run

    def _approval_is_high_risk(self, action_kind: str) -> bool:
        return action_kind in {"patch_apply", "patch_rollback", "workspace_promote", "shell", "desktop_click", "desktop_type"}

    def _patch_apply_approval_preview(self, proposal: PatchProposal) -> dict[str, Any]:
        redacted_diff = redact_secrets(proposal.diff)
        return {
            "summary": redact_secrets(proposal.summary or f"Patch proposal {proposal.id}: {proposal.title}"),
            "patch_id": proposal.id,
            "title": redact_secrets(proposal.title),
            "files": self._patch_diff_preview_files(redacted_diff, proposal.files),
            "diff_excerpt": redacted_diff[:4000],
            "truncated": len(redacted_diff) > 4000,
        }

    def _patch_rollback_approval_preview(self, application: PatchApplication) -> dict[str, Any]:
        return {
            "summary": redact_secrets(application.summary or f"Rollback patch {application.patch_id}"),
            "patch_id": application.patch_id,
            "backup_id": application.backup_id,
            "manifest_path": redact_secrets(application.manifest_path),
            "files": [{"path": redact_secrets(path), "status": "restore"} for path in application.files[:12]],
            "high_risk": True,
            "requires_approval": True,
            "mutation_automatic": False,
        }

    def _patch_diff_preview_files(self, diff: str, proposal_files: list[str]) -> list[dict[str, Any]]:
        paths = proposal_files or []
        return [
            {
                "path": redact_secrets(path),
                "diff_excerpt": diff[:1200],
                "truncated": len(diff) > 1200,
            }
            for path in paths[:12]
        ]
    async def resume_recovery(self, run_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        if state.recovery_plan.status != "active":
            state.facts_learned.append("Recovery resume requested, but no active recovery plan exists.")
            state.handoff_summary = self._make_handoff(run, state)
            self.store.update_run(run_id, state=state)
            return await self._resume_run_with_preflight(run_id, source="recovery")
        state.current_plan = state.recovery_plan.steps
        state.task_graph = self._tasks_from_plan(state.current_plan, [])
        state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
        state.milestone = "orient"
        state.next_step = state.recovery_plan.next_action
        state.failure_counts.pop(state.recovery_plan.tool, None)
        state.facts_learned.append(f"Resuming recovery plan: {state.recovery_plan.summary}")
        state.handoff_summary = self._make_handoff(run, state)
        self.store.update_run(run_id, state=state)
        await self._event(run_id, "recovery_resume", state.recovery_plan.summary, {"recovery_plan": state.recovery_plan.model_dump()})
        return await self._resume_run_with_preflight(run_id, source="recovery", allow_recovery=True)

    async def replan_recovery(self, run_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        if state.recovery_plan.status != "active":
            state.facts_learned.append("Recovery replan requested, but no active recovery plan exists.")
            state.handoff_summary = self._make_handoff(run, state)
            run = self.store.update_run(run_id, status="paused", state=state)
            await self._event(run_id, "recovery_replan", "No active recovery plan exists.")
            return run
        previous = state.recovery_plan.model_copy(deep=True)
        previous.status = "superseded"
        previous.resolved_at = utc_now()
        state.recovery_history.append(previous)
        state.recovery_history = state.recovery_history[-10:]
        base_steps = (
            self._readiness_recovery_steps_from_state(state)
            or self._objective_readiness_recovery_steps_from_state(state)
            or self._recovery_steps(previous.failure_kind, previous.tool)
        )
        steps = ["Review the latest replay export and handoff before retrying."] + base_steps
        state.recovery_plan = RecoveryPlan(
            id=f"recovery-{uuid4().hex[:8]}",
            status="active",
            trigger="manual_replan",
            failure_kind=previous.failure_kind,
            tool=previous.tool,
            attempts=previous.attempts,
            summary=self._recovery_replan_summary(previous, steps),
            next_action=steps[0],
            steps=steps,
            created_at=utc_now(),
        )
        state.current_plan = steps
        state.task_graph = self._tasks_from_plan(steps, [])
        state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
        state.milestone = "orient"
        state.next_step = state.recovery_plan.next_action
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, status="paused", state=state)
        await self._event(run_id, "recovery_replan", state.recovery_plan.summary, {"recovery_plan": state.recovery_plan.model_dump()})
        return run

    def get_supervisor_report(self) -> dict[str, Any]:
        return self.supervisor_report

    def get_operator_action_queue(self, limit: int = 12, queue_filter: str = "all") -> dict[str, Any]:
        return self._build_operator_action_queue(
            self.supervisor_report,
            limit=max(1, min(50, limit)),
            queue_filter=queue_filter,
        ).model_dump()

    def get_operator_dispatches(self, run_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        bounded_limit = max(1, min(100, limit))
        events: list[dict[str, Any]] = []
        if run_id:
            events = self.store.list_events(run_id, limit=max(100, bounded_limit * 4))
        else:
            for run in self.store.list_runs():
                events.extend(self.store.list_events(run.id, limit=max(50, bounded_limit * 2)))
            events.sort(key=lambda item: int(item.get("id") or 0), reverse=True)
        return build_operator_dispatch_ledger(events, run_id=run_id or "", limit=bounded_limit).model_dump()

    def get_ornith_preflight_actions(self, run_id: str, limit: int = 20) -> dict[str, Any]:
        self.store.get_run(run_id)
        bounded_limit = max(1, min(100, limit))
        events = self.store.list_events(run_id, limit=max(100, bounded_limit * 4))
        return build_ornith_preflight_action_ledger(events, run_id=run_id, limit=bounded_limit).model_dump()

    def get_source_evidence(self, run_id: str, limit: int = 20) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        bounded_limit = max(1, min(100, limit))
        return build_source_evidence_preview(run, limit=bounded_limit).model_dump()

    def get_goal_evolution(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        report = build_goal_evolution_report(run)
        run.state.goal_evolution = report
        return report.model_dump()

    async def dispatch_operator_action(
        self,
        request: OperatorActionDispatchRequest,
    ) -> OperatorActionDispatchResult:
        if self.supervisor_report.get("status") == "not_run":
            await self.recover_stale_runs()
        queue = self._build_operator_action_queue(self.supervisor_report, limit=50)
        item = next((entry for entry in queue.items if entry.id == request.item_id), None)
        if item is None:
            return OperatorActionDispatchResult(
                item_id=request.item_id,
                status="not_found",
                message="Operator action is no longer present in the current queue.",
                action_taken="none",
                queue=queue,
            )

        async def finish(
            status: str,
            message: str,
            *,
            action_taken: str,
            event_kind: str = "",
            result_run_id: str = "",
            refresh: bool = False,
        ) -> OperatorActionDispatchResult:
            refreshed_queue = queue
            if refresh:
                await self.recover_stale_runs()
                refreshed_queue = OperatorActionQueueReport.model_validate(
                    self.supervisor_report.get("operator_action_queue", self.get_operator_action_queue(limit=50))
                )
            return OperatorActionDispatchResult(
                item_id=item.id,
                run_id=item.run_id,
                status=status,  # type: ignore[arg-type]
                message=message,
                action_taken=action_taken,
                result_run_id=result_run_id or item.run_id,
                event_kind=event_kind,
                queue=refreshed_queue,
            )

        def event_data() -> dict[str, Any]:
            return {
                "operator_action": item.model_dump(),
                "decision": request.decision,
                "confirmed": request.confirmed,
                "note_supplied": bool(request.note.strip()),
            }

        if request.decision == "open":
            event_kind = "operator_action_reviewed"
            await self._event(item.run_id, event_kind, f"Operator opened queued action {item.reason}.", event_data())
            return await finish("reviewed", "Opened queued action for review.", action_taken="open", event_kind=event_kind)

        mutating = request.decision in {"approve", "reject"} or item.method.upper() == "POST"
        if mutating and not request.confirmed:
            event_kind = "operator_action_confirmation_required"
            await self._event(
                item.run_id,
                event_kind,
                f"Operator action {item.reason} requires explicit confirmation before dispatch.",
                event_data(),
            )
            return await finish(
                "requires_confirmation",
                "Explicit confirmation is required before dispatching this operator action.",
                action_taken="none",
                event_kind=event_kind,
            )

        if item.ui_target == "approval":
            if request.decision not in {"approve", "reject"}:
                event_kind = "operator_action_reviewed"
                await self._event(item.run_id, event_kind, f"Operator reviewed approval action {item.reason}.", event_data())
                return await finish("reviewed", "Approval opened for review.", action_taken="review_approval", event_kind=event_kind)
            pending = [
                approval
                for approval in self.store.list_approvals(item.run_id, status="pending")
                if int(approval.get("id") or 0) == item.approval_id
            ]
            if not pending:
                event_kind = "operator_action_blocked"
                await self._event(
                    item.run_id,
                    event_kind,
                    "Queued approval action is no longer pending.",
                    event_data(),
                )
                return await finish(
                    "blocked",
                    "Approval is no longer pending; refresh the queue.",
                    action_taken="none",
                    event_kind=event_kind,
                    refresh=True,
                )
            event_kind = "operator_action_dispatched"
            await self._event(
                item.run_id,
                event_kind,
                f"Operator {request.decision}ed queued approval {item.approval_id}.",
                event_data(),
            )
            if request.decision == "approve":
                await self.approve_action(item.run_id, item.approval_id)
                return await finish(
                    "dispatched",
                    "Approval was approved and dispatched through the existing approval path.",
                    action_taken="approve",
                    event_kind=event_kind,
                    refresh=True,
                )
            await self.reject_action(item.run_id, item.approval_id)
            return await finish(
                "dispatched",
                "Approval was rejected and logged through the existing approval path.",
                action_taken="reject",
                event_kind=event_kind,
                refresh=True,
            )

        if item.ui_target == "self_scaffold":
            event_kind = "operator_action_reviewed"
            run = self.store.get_run(item.run_id)
            scaffold_events = self.store.list_events(item.run_id, limit=300)
            review_report = build_self_scaffold_report(run, scaffold_events, limit=12)
            reviewable_changes = [change for change in review_report.changes if change.status == "needs_review"]
            if not reviewable_changes:
                reviewable_changes = [change for change in run.state.self_scaffold.changes if change.status == "needs_review"]
            data = {
                "operator_action": item.model_dump(),
                "self_scaffold_review": {
                    "status": review_report.status,
                    "change_count": review_report.change_count,
                    "guard_count": review_report.guard_count,
                    "reviewed_change_count": len(reviewable_changes),
                    "reviewed_change_ids": [change.id for change in reviewable_changes],
                    "remaining_goal_review": any(
                        change.status == "needs_review" and change.kind == "goal_evolution"
                        for change in review_report.changes
                    ),
                },
            }
            await self._event(item.run_id, event_kind, "Operator accepted self-scaffold change intent for current guard/reorient changes.", data)
            run = self.store.get_run(item.run_id)
            state = run.state
            review_events = self.store.list_events(item.run_id, limit=300)
            state.self_scaffold = build_self_scaffold_report(run, review_events, limit=12)
            state.self_scaffold_reviews = build_self_scaffold_review_report(run, review_events, limit=8)
            state.self_scaffold_rollback_intents = build_self_scaffold_rollback_intent_report(
                run,
                review_events,
                self_scaffold=state.self_scaffold,
                reviews=state.self_scaffold_reviews,
                limit=8,
            )
            state.latest_summary = state.self_scaffold.summary
            state.next_step = "Self-scaffold review accepted; resume from the compact handoff when ready."
            state.handoff_summary = self._make_handoff(run, state)
            updated = self.store.update_run(item.run_id, status=run.status, state=state)
            self.memory.append_checkpoint(updated, state, "self_scaffold_review")
            return await finish(
                "reviewed",
                "Self-scaffold review accepted and the operator queue was refreshed.",
                action_taken="self_scaffold_review",
                event_kind=event_kind,
                refresh=True,
            )

        if item.ui_target == "patch_apply_approval":
            patch_id = self._patch_id_from_apply_endpoint(item.endpoint)
            if not patch_id:
                event_kind = "operator_action_blocked"
                await self._event(item.run_id, event_kind, "Queued patch apply action had no patch id.", event_data())
                return await finish("blocked", "Patch apply action is missing a patch id; refresh the queue.", action_taken="none", event_kind=event_kind, refresh=True)
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, f"Operator requested patch apply approval {patch_id}.", event_data())
            updated = await self.request_patch_apply_approval(item.run_id, patch_id)
            return await finish(
                "dispatched",
                "Patch apply approval was requested for the promotion repair patch.",
                action_taken="patch_apply_approval",
                event_kind=event_kind,
                result_run_id=updated.id,
                refresh=True,
            )

        if item.ui_target == "patch_rollback_approval":
            patch_id = self._patch_id_from_rollback_endpoint(item.endpoint)
            if not patch_id:
                event_kind = "operator_action_blocked"
                await self._event(item.run_id, event_kind, "Queued patch rollback action had no patch id.", event_data())
                return await finish("blocked", "Patch rollback action is missing a patch id; refresh the queue.", action_taken="none", event_kind=event_kind, refresh=True)
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, f"Operator requested patch rollback approval {patch_id}.", event_data())
            updated = await self.request_patch_rollback_approval(item.run_id, patch_id)
            return await finish(
                "dispatched",
                "Patch rollback approval was requested; no rollback was executed.",
                action_taken="patch_rollback_approval",
                event_kind=event_kind,
                result_run_id=updated.id,
                refresh=True,
            )
        if item.ui_target == "readiness_rehearsal":
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, "Operator dispatched readiness-smoke rehearsal.", event_data())
            report = await self.run_readiness_rehearsal()
            return await finish(
                "dispatched",
                "Readiness rehearsal smoke was started and attached to its generated run.",
                action_taken="readiness_rehearsal",
                event_kind=event_kind,
                result_run_id=report.run_id,
                refresh=True,
            )

        if item.ui_target == "operator_dispatch_restart_smoke":
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, "Operator dispatched operator-dispatch restart smoke.", event_data())
            report = await self.run_operator_dispatch_restart_smoke()
            return await finish(
                "dispatched",
                "Operator-dispatch restart smoke was started and attached to its generated run.",
                action_taken="operator_dispatch_restart_smoke",
                event_kind=event_kind,
                result_run_id=report.run_id,
                refresh=True,
            )

        if item.ui_target in {"context_checkpoint", "handoff_refresh"}:
            event_kind = "operator_action_dispatched"
            action_name = "context checkpoint" if item.ui_target == "context_checkpoint" else "handoff refresh"
            await self._event(item.run_id, event_kind, f"Operator dispatched Ornith preflight {action_name}.", event_data())
            run = self.store.get_run(item.run_id)
            state = run.state
            self._reload_anchor_context(run, state)
            state.latest_summary = f"Operator refreshed compact context and handoff from Ornith preflight action: {item.reason}."
            state.next_step = "Resume from refreshed compact context and handoff."
            await self._event(
                item.run_id,
                "ornith_preflight_action",
                f"Completed Ornith preflight {action_name}.",
                {"operator_action": item.model_dump(), "context_budget": state.context_budget.model_dump()},
            )
            state.ornith_preflight_actions = OrnithPreflightActionLedgerReport.model_validate(
                self.get_ornith_preflight_actions(item.run_id, limit=12)
            )
            state.handoff_summary = self._make_handoff(run, state)
            updated = self.store.update_run(item.run_id, status=run.status, state=state)
            self.memory.append_checkpoint(updated, state, item.ui_target)
            return await finish(
                "dispatched",
                f"Ornith preflight {action_name} refreshed compact context, handoff, and Obsidian checkpoint.",
                action_taken=item.ui_target,
                event_kind=event_kind,
                refresh=True,
            )

        if item.ui_target == "recovery":
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, "Operator dispatched recovery resume.", event_data())
            await self.resume_recovery(item.run_id)
            return await finish(
                "dispatched",
                "Recovery resume was dispatched through recovery preflight.",
                action_taken="recovery_resume",
                event_kind=event_kind,
                refresh=True,
            )

        if item.ui_target == "resume":
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, "Operator dispatched run resume from queue.", event_data())
            await self.resume_run(item.run_id)
            return await finish(
                "dispatched",
                "Run resume was dispatched through resume preflight.",
                action_taken="resume",
                event_kind=event_kind,
                refresh=True,
            )

        if item.ui_target == "goal":
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, "Operator dispatched goal review from queue.", event_data())
            await self.review_goal(item.run_id)
            return await finish(
                "dispatched",
                "Goal review was dispatched; pending goal confirmation remains explicit.",
                action_taken="goal_review",
                event_kind=event_kind,
                refresh=True,
            )

        if item.ui_target == "steer" and request.note.strip():
            event_kind = "operator_action_dispatched"
            await self._event(item.run_id, event_kind, "Operator dispatched steering note from queue.", event_data())
            await self.steer_run(item.run_id, request.note.strip())
            return await finish(
                "dispatched",
                "Steering note was applied through the existing steer path.",
                action_taken="steer",
                event_kind=event_kind,
                refresh=True,
            )

        event_kind = "operator_action_reviewed"
        await self._event(item.run_id, event_kind, f"Operator reviewed queued action {item.reason}.", event_data())
        return await finish(
            "reviewed",
            "Action requires manual review in the selected run.",
            action_taken="review",
            event_kind=event_kind,
        )

    async def recover_stale_runs(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "status": "ok",
            "ran_at": utc_now(),
            "checked": 0,
            "recovered": 0,
            "auto_resumed": 0,
            "waiting_approval": 0,
            "live": 0,
            "stale": 0,
            "auto_resume_enabled": self.config.enable_supervisor_auto_resume,
            "auto_resume_max_runs": self.config.supervisor_auto_resume_max_runs,
            "readiness_rehearsal_ledger": self.get_readiness_rehearsal_ledger(limit=5),
            "operator_dispatch_restart_smoke_ledger": self.get_operator_dispatch_restart_smoke_ledger(limit=5),
            "readiness_smoke_attention_count": 0,
            "operator_dispatch_restart_smoke_attention_count": 0,
            "ornith_preflight_attention_count": 0,
            "source_evidence_attention_count": 0,
            "self_scaffold_attention_count": 0,
            "self_scaffold_rollback_attention_count": 0,
            "pending_approval_count": 0,
            "operator_recovery_count": 0,
            "operator_blocker_count": 0,
            "operator_attention_count": 0,
            "operator_attention_blocked_count": 0,
            "operator_attention_watch_count": 0,
            "operator_action_queue": OperatorActionQueueReport().model_dump(),
            "runs": [],
        }
        rehearsal_ledger = ReadinessRehearsalLedgerReport.model_validate(report["readiness_rehearsal_ledger"])
        dispatch_smoke_ledger = OperatorDispatchRestartSmokeLedgerReport.model_validate(
            report["operator_dispatch_restart_smoke_ledger"]
        )
        for run in self.store.list_runs():
            await asyncio.sleep(0)
            report["checked"] += 1
            state = run.state
            pending_approvals = self.store.list_approvals(run.id, status="pending")
            report["pending_approval_count"] += len(pending_approvals)
            lease_live = self._lease_is_live(run.state.run_lease)
            run_health = self._build_run_health(run, state)
            policy_simulation = self._build_policy_simulation(run, state)
            run_progress = self._build_run_progress(run, state, policy_simulation)
            objective_readiness = self._build_objective_readiness(run, state)
            source_evidence = SourceEvidencePreviewReport.model_validate(
                build_source_evidence_preview(run.model_copy(update={"state": state}), limit=12)
            )
            state.source_evidence = source_evidence
            source_evidence_requires_attention = bool(source_evidence.missing_labels) and run.status not in {"completed", "canceled"}
            scaffold_events = self.store.list_events(run.id, limit=300)
            self_scaffold = build_self_scaffold_report(run.model_copy(update={"state": state}), scaffold_events, limit=12)
            state.self_scaffold = self_scaffold
            self_scaffold_reviews = build_self_scaffold_review_report(run.model_copy(update={"state": state}), scaffold_events, limit=8)
            state.self_scaffold_reviews = self_scaffold_reviews
            self_scaffold_rollback_intents = build_self_scaffold_rollback_intent_report(
                run.model_copy(update={"state": state}),
                scaffold_events,
                self_scaffold=self_scaffold,
                reviews=self_scaffold_reviews,
                limit=8,
            )
            state.self_scaffold_rollback_intents = self_scaffold_rollback_intents
            self_scaffold_requires_attention = self_scaffold.status == "needs_review"
            self_scaffold_action = self_scaffold.recommended_action or "Review self-scaffold change intent before broad autonomy."
            self_scaffold_rollback_requires_attention = (
                self_scaffold_rollback_intents.status == "needs_approval"
                and self_scaffold_rollback_intents.patch_rollback_count > 0
            )
            self_scaffold_rollback_action = (
                self_scaffold_rollback_intents.recommended_action
                or "Review self-scaffold rollback intent before broad autonomy."
            )
            objective_readiness_action = self._objective_readiness_supervisor_action(run, state, objective_readiness)
            readiness_smoke = self._readiness_smoke_supervisor_signal(run, state, rehearsal_ledger)
            dispatch_restart_smoke = self._operator_dispatch_restart_smoke_supervisor_signal(
                run,
                state,
                dispatch_smoke_ledger,
            )
            ornith_preflight = OrnithLaunchChecklistReport.model_validate(
                self.get_ornith_launch_checklist(
                    run.id,
                    state=state,
                    operator_queue=OperatorActionQueueReport(),
                    include_operator_queue=False,
                )
            )
            ornith_preflight_queue_relevant = (
                self._is_harness_improvement_goal(run, state)
                and not self._is_readiness_rehearsal_run(run, state)
                and not self._is_operator_dispatch_restart_smoke_run(run, state)
                and run.status not in {"completed", "failed", "cancelled"}
            )
            ornith_preflight_requires_attention = ornith_preflight_queue_relevant and any(
                item.status != "pass" for item in ornith_preflight.items
            )
            if readiness_smoke["requires_attention"]:
                report["readiness_smoke_attention_count"] += 1
            if dispatch_restart_smoke["requires_attention"]:
                report["operator_dispatch_restart_smoke_attention_count"] += 1
            if ornith_preflight_requires_attention:
                report["ornith_preflight_attention_count"] += 1
            if source_evidence_requires_attention:
                report["source_evidence_attention_count"] += 1
            if self_scaffold_requires_attention:
                report["self_scaffold_attention_count"] += 1
            if self_scaffold_rollback_requires_attention:
                report["self_scaffold_rollback_attention_count"] += 1
            auto_resume_eligible, auto_resume_reason = self._auto_resume_decision(
                run,
                pending_approvals,
                policy_simulation,
                run_progress,
            )
            if self_scaffold_rollback_requires_attention:
                auto_resume_eligible = False
                auto_resume_reason = self_scaffold_rollback_action
            elif self_scaffold_requires_attention:
                auto_resume_eligible = False
                auto_resume_reason = self_scaffold_action
            run_entry = {
                "run_id": run.id,
                "title": run.title,
                "previous_status": run.status,
                "status": run.status,
                "action": "unchanged",
                "recovery_plan": run.state.recovery_plan.status,
                "pending_approvals": len(pending_approvals),
                "auto_resume_eligible": auto_resume_eligible,
                "auto_resume_reason": auto_resume_reason,
                "lease_status": run.state.run_lease.status,
                "lease_owner": run.state.run_lease.owner_id,
                "lease_live": lease_live,
                "lease_expires_at": run.state.run_lease.expires_at,
                "run_health": run_health.model_dump(),
                "policy_simulation": policy_simulation.model_dump(),
                "run_progress": run_progress.model_dump(),
                "objective_readiness": objective_readiness.model_dump(),
                "objective_readiness_action": objective_readiness_action,
                "source_evidence": source_evidence.model_dump(),
                "source_evidence_requires_attention": source_evidence_requires_attention,
                "source_evidence_action": source_evidence.recommended_action,
                "self_scaffold": self_scaffold.model_dump(),
                "self_scaffold_reviews": self_scaffold_reviews.model_dump(),
                "self_scaffold_rollback_intents": self_scaffold_rollback_intents.model_dump(),
                "self_scaffold_status": self_scaffold.status,
                "self_scaffold_requires_attention": self_scaffold_requires_attention,
                "self_scaffold_action": self_scaffold_action,
                "self_scaffold_latest_change": self_scaffold.latest_change,
                "self_scaffold_rollback_requires_attention": self_scaffold_rollback_requires_attention,
                "self_scaffold_rollback_action": self_scaffold_rollback_action,
                "self_scaffold_rollback_patch_count": self_scaffold_rollback_intents.patch_rollback_count,
                "self_scaffold_rollback_latest_review_event_id": self_scaffold_rollback_intents.latest_review_event_id,
                "readiness_smoke_required": readiness_smoke["required"],
                "readiness_smoke_status": readiness_smoke["status"],
                "readiness_smoke_action": readiness_smoke["action"],
                "readiness_smoke_latest_run_id": readiness_smoke["latest_run_id"],
                "readiness_smoke_requires_attention": readiness_smoke["requires_attention"],
                "operator_dispatch_restart_smoke_required": dispatch_restart_smoke["required"],
                "operator_dispatch_restart_smoke_status": dispatch_restart_smoke["status"],
                "operator_dispatch_restart_smoke_action": dispatch_restart_smoke["action"],
                "operator_dispatch_restart_smoke_latest_run_id": dispatch_restart_smoke["latest_run_id"],
                "operator_dispatch_restart_smoke_requires_attention": dispatch_restart_smoke["requires_attention"],
                "ornith_preflight": ornith_preflight.model_dump(),
                "ornith_preflight_status": ornith_preflight.status,
                "ornith_preflight_requires_attention": ornith_preflight_requires_attention,
                "operator_attention_required": False,
                "operator_attention_reasons": [],
                "operator_attention_action": "",
                "operator_attention_severity": "none",
                "supervisor_priority": 0,
            }
            if run.status in {"queued", "running"}:
                if lease_live and (
                    state.run_lease.owner_id != self.engine_id or self._has_active_task(run.id)
                ):
                    report["live"] += 1
                    run_entry["action"] = "live_lease_preserved"
                    self._finalize_supervisor_run_entry(report, run_entry, state)
                    report["runs"].append(run_entry)
                    continue
                previous_status = run.status
                if state.run_lease.status == "active":
                    state.run_lease.status = "stale"
                    state.run_lease.last_event = "Supervisor marked expired or orphaned lease stale."
                    report["stale"] += 1
                    run_entry["lease_status"] = state.run_lease.status
                    run_entry["lease_live"] = False
                if auto_resume_eligible and report["auto_resumed"] < self.config.supervisor_auto_resume_max_runs:
                    await self._record_resume_preflight(
                        run.id,
                        "supervisor",
                        policy_simulation,
                        True,
                        auto_resume_reason,
                    )
                    self._prepare_auto_resume_state(run, state, previous_status)
                    updated = self.store.update_run(run.id, status="queued", state=state)
                    await self._event(
                        run.id,
                        "supervisor_auto_resume",
                        "Supervisor auto-resumed safe queued run after startup.",
                        {
                            "previous_status": previous_status,
                            "reason": auto_resume_reason,
                            "policy_simulation": policy_simulation.model_dump(),
                        },
                    )
                    report["auto_resumed"] += 1
                    run_entry["status"] = updated.status
                    run_entry["action"] = "auto_resumed"
                    self._ensure_task(run.id)
                else:
                    if auto_resume_eligible:
                        run_entry["auto_resume_reason"] = "Auto-resume limit reached for this supervisor pass."
                    self._prepare_startup_resume_state(run, state, previous_status)
                    updated = self.store.update_run(run.id, status="paused", state=state)
                    await self._event(
                        run.id,
                        "supervisor",
                        f"Recovered stale {previous_status} run after backend startup; paused for explicit resume.",
                        {"previous_status": previous_status, "auto_resume_reason": run_entry["auto_resume_reason"]},
                    )
                    report["recovered"] += 1
                    run_entry["status"] = updated.status
                    run_entry["action"] = "paused_for_resume"
            elif run.status == "waiting_approval":
                if pending_approvals:
                    state.next_step = "Wait for pending dashboard approval."
                    state.handoff_summary = self._make_handoff(run, state)
                    updated = self.store.update_run(run.id, status="waiting_approval", state=state)
                    report["waiting_approval"] += 1
                    run_entry["status"] = updated.status
                    run_entry["action"] = "pending_approval_preserved"
                else:
                    self._append_unique(
                        state.blockers,
                        "Supervisor found waiting_approval status without a pending approval after startup.",
                    )
                    state.next_step = "Review replay and replan before continuing."
                    state.handoff_summary = self._make_handoff(run, state)
                    updated = self.store.update_run(run.id, status="paused", state=state)
                    await self._event(
                        run.id,
                        "supervisor",
                        "Recovered waiting_approval run with no pending approval; paused for review.",
                    )
                    report["recovered"] += 1
                    run_entry["status"] = updated.status
                    run_entry["action"] = "approval_state_repaired"
            self._finalize_supervisor_run_entry(report, run_entry, state)
            if run_entry["action"] != "unchanged" or run_entry["operator_attention_required"]:
                if run_entry["action"] == "unchanged":
                    reasons = set(run_entry["operator_attention_reasons"])
                    smoke_reasons = {"readiness_smoke", "operator_dispatch_restart_smoke"}
                    run_entry["action"] = "smoke_attention" if reasons and reasons <= smoke_reasons else "operator_attention"
                    run_entry["supervisor_priority"] = self._supervisor_run_priority(run_entry)
                report["runs"].append(run_entry)
        report["runs"].sort(key=lambda item: int(item.get("supervisor_priority") or 0), reverse=True)
        report["operator_action_queue"] = self._build_operator_action_queue(report).model_dump()
        self.supervisor_report = report
        return report

    async def approve_action(self, run_id: str, approval_id: int) -> RunRecord:
        approval = self.store.resolve_approval(approval_id, "approved")
        await self._event(run_id, "approval", f"Approved {approval['action_kind']}.", approval)
        if approval["action_kind"] == "goal_update":
            run = self.store.get_run(run_id)
            state = run.state
            proposed_goal = str(approval["payload"].get("proposed_goal") or state.proposed_goal or "").strip()
            if proposed_goal:
                previous_goal = state.goal
                resolve_goal_proposal(
                    state,
                    run,
                    proposed_goal=proposed_goal,
                    accepted=True,
                    approval_id=int(approval.get("id") or 0),
                    reason=str(approval["payload"].get("reason") or state.goal_revision_reason or "Goal update approved."),
                )
                state.goal = proposed_goal
                state.proposed_goal = None
                state.goal_revision_reason = ""
                state.current_plan = []
                state.milestone = "orient"
                state.completed_steps.append(f"Accepted updated goal: {proposed_goal}")
                self._append_unique(state.facts_learned, f"Goal evolved from '{previous_goal}' to '{proposed_goal}' after confirmation.")
                state.next_step = "Re-orient around accepted goal."
                state.goal_evolution = build_goal_evolution_report(run.model_copy(update={"state": state}))
                state.handoff_summary = self._make_handoff(run, state)
                self.store.update_run(run_id, state=state)
            return await self._resume_run_with_preflight(run_id, source="goal_confirmation")

        payload = approval["payload"]
        tool_name = str(payload.get("tool_name") or approval["action_kind"])
        args = payload.get("args") if isinstance(payload.get("args"), dict) else payload
        runner = ToolRunner(Path(self.store.get_run(run_id).workspace_path), self.config)
        result = await runner.execute(tool_name, args, approved=True)
        await self._record_tool_result(run_id, result)
        run = self.store.get_run(run_id)
        state = run.state
        state.blockers = [item for item in state.blockers if item != approval["reason"]]
        self._resolve_objective_readiness_approval(run, state, approval)
        state.objective_readiness = self._build_objective_readiness(run, state)
        state.handoff_summary = self._make_handoff(run, state)
        self.store.update_run(run_id, state=state)
        return await self._resume_run_with_preflight(run_id, source="approval")

    def _resolve_objective_readiness_approval(self, run: RunRecord, state: RunState, approval: dict[str, Any]) -> None:
        if approval.get("action_kind") != "ask_user":
            return
        text = f"{approval.get('reason') or ''} {approval.get('payload') or ''}"
        marker = "Objective readiness proof for "
        if marker not in text:
            return
        item_id = text.split(marker, 1)[1].split(" ", 1)[0].strip(" :`.,")
        if not item_id:
            return
        if any(
            outcome.item_id == item_id
            and outcome.outcome == "verified"
            and outcome.strategy == "approval_resolution"
            for outcome in state.objective_readiness_proof_outcomes
        ):
            return
        state.objective_readiness_proof_outcomes.append(
            ObjectiveReadinessProofOutcome(
                id=f"obj-proof-{uuid4().hex[:8]}",
                item_id=item_id,
                tool="ask_user",
                evidence_label="approval",
                strategy="approval_resolution",
                outcome="verified",
                ok=True,
                summary=f"Operator approved supervised objective-readiness proof path for {item_id}.",
                proof_action=str(approval.get("reason") or "")[:500],
                created_at=utc_now(),
            )
        )
        state.objective_readiness_proof_outcomes = state.objective_readiness_proof_outcomes[-40:]
        self._append_unique(
            state.facts_learned,
            f"Objective readiness approval resolved for {item_id}.",
        )

    def _reconcile_approved_objective_readiness_approvals(self, run_id: str, state: RunState) -> None:
        run = self.store.get_run(run_id)
        for approval in self.store.list_approvals(run_id, status="approved"):
            self._resolve_objective_readiness_approval(run, state, approval)

    async def reject_action(self, run_id: str, approval_id: int) -> RunRecord:
        approval = self.store.resolve_approval(approval_id, "rejected")
        run = self.store.get_run(run_id)
        state = run.state
        if approval["action_kind"] == "goal_update":
            proposed_goal = str(approval["payload"].get("proposed_goal") or state.proposed_goal or "").strip()
            resolve_goal_proposal(
                state,
                run,
                proposed_goal=proposed_goal,
                accepted=False,
                approval_id=int(approval.get("id") or 0),
                reason=str(approval["payload"].get("reason") or state.goal_revision_reason or "Goal update rejected."),
            )
            state.proposed_goal = None
            state.goal_revision_reason = ""
            state.goal_evolution = build_goal_evolution_report(run.model_copy(update={"state": state}))
            state.facts_learned.append("Rejected proposed goal update; keeping current goal.")
        else:
            state.blockers.append(f"Rejected approval: {approval['reason']}")
        state.next_step = "Revise plan around rejected action."
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, status="paused", state=state)
        await self._event(run_id, "approval", f"Rejected {approval['action_kind']}.", approval)
        self.memory.append_checkpoint(run, state, "paused")
        return run

    def get_tool_policy(self) -> dict[str, Any]:
        return self.registry.public_config()

    def get_completion_policy(self) -> dict[str, bool | list[str] | dict[str, list[str]]]:
        return self.config.completion_policy_dict()

    def get_model_profile(self) -> dict[str, Any]:
        profile = self.model_profile.public_dict()
        profile["configured_model"] = self.config.model_name
        profile["effective_context_target_tokens"] = self.context_compiler.target_tokens
        return profile

    def get_ornith_launch_checklist(
        self,
        run_id: str | None = None,
        *,
        state: RunState | None = None,
        operator_queue: OperatorActionQueueReport | None = None,
        include_operator_queue: bool = True,
    ) -> dict[str, Any]:
        run: RunRecord | None = self.store.get_run(run_id) if run_id else None
        if run and state:
            run = run.model_copy(update={"state": state})
        state = run.state if run else None
        mode = "resume" if run else "launch"
        readiness_ledger = ReadinessRehearsalLedgerReport.model_validate(self.get_readiness_rehearsal_ledger(limit=5))
        dispatch_ledger = OperatorDispatchRestartSmokeLedgerReport.model_validate(
            self.get_operator_dispatch_restart_smoke_ledger(limit=5)
        )
        queue = operator_queue or OperatorActionQueueReport()
        if include_operator_queue and operator_queue is None:
            queue = OperatorActionQueueReport.model_validate(self.get_operator_action_queue(limit=12))
        pending_approvals = len(self.store.list_approvals(run.id, status="pending")) if run else queue.approval_count
        web_enabled = state.web_enabled if state else self.config.enable_web_tools
        browser_enabled = state.browser_enabled if state else self.config.enable_browser_tools
        desktop_enabled = state.desktop_enabled if state else self.config.enable_desktop_control
        context_budget = state.context_budget if state else ContextBudget(target_tokens=self.context_compiler.target_tokens)
        tool_profile = state.tool_profile if state else self.model_profile.id
        run_health = self._build_run_health(run, state) if run and state else RunHealthReport()
        policy_simulation = self._build_policy_simulation(run, state) if run and state else None
        items: list[OrnithLaunchChecklistItem] = []

        def add_item(
            item_id: str,
            category: str,
            status: str,
            summary: str,
            evidence: list[str] | None = None,
            next_action: str = "",
        ) -> None:
            items.append(
                OrnithLaunchChecklistItem(
                    id=item_id,
                    category=category,
                    status=status,  # type: ignore[arg-type]
                    summary=summary,
                    evidence=evidence or [],
                    next_action=next_action,
                )
            )

        profile_status = "pass" if self.model_profile.id == "ornith" else "warn"
        add_item(
            "model_profile",
            "model",
            profile_status,
            "Ornith model profile is active." if profile_status == "pass" else "Model profile is not Ornith-specific.",
            [
                f"profile={self.model_profile.id}",
                f"model={self.config.model_name}",
                f"target_tokens={self.context_compiler.target_tokens}",
            ],
            "Use MODEL_PROFILE=ornith for Ornith-first long coding runs." if profile_status == "warn" else "",
        )
        tool_status = "pass" if web_enabled and browser_enabled else "warn"
        add_item(
            "tool_toggles",
            "tools",
            tool_status,
            "Web and browser tools are enabled." if tool_status == "pass" else "Web or browser tooling is disabled.",
            [f"web={web_enabled}", f"browser={browser_enabled}", f"desktop={desktop_enabled}"],
            "Enable web/browser tools before research-heavy Ornith runs." if tool_status == "warn" else "",
        )
        desktop_status = "pass" if desktop_enabled and self.config.desktop_mode == "visible_supervised" else "warn"
        add_item(
            "desktop_supervision",
            "tools",
            desktop_status,
            "Desktop control is visible and supervised." if desktop_status == "pass" else "Desktop control is disabled or not visibly supervised.",
            [f"desktop={desktop_enabled}", f"mode={self.config.desktop_mode}"],
            "Use DESKTOP_MODE=visible_supervised for supervised PC control." if desktop_status == "warn" else "",
        )
        workspace_status = "pass" if self.config.enable_workspace_isolation else "warn"
        if run and state:
            workspace_status = "pass" if state.workspace_isolation.enabled else "warn"
        add_item(
            "workspace_isolation",
            "workspace",
            workspace_status,
            "Workspace isolation is enabled." if workspace_status == "pass" else "Run may edit the source workspace directly.",
            [
                f"enabled={(state.workspace_isolation.enabled if state else self.config.enable_workspace_isolation)}",
                f"mode={(state.workspace_isolation.mode if state else self.config.workspace_isolation_mode)}",
            ],
            "Use isolated workspaces for long coding runs before promoting changes." if workspace_status == "warn" else "",
        )
        readiness_smoke_status = readiness_ledger.status
        dispatch_smoke_status = dispatch_ledger.status
        if run and state:
            readiness_signal = self._readiness_smoke_supervisor_signal(run, state, readiness_ledger)
            dispatch_signal = self._operator_dispatch_restart_smoke_supervisor_signal(run, state, dispatch_ledger)
            readiness_smoke_status = readiness_signal["status"]
            dispatch_smoke_status = dispatch_signal["status"]
            self._append_smoke_signal_checklist_item(items, "readiness_smoke", "smoke", readiness_signal)
            self._append_smoke_signal_checklist_item(
                items,
                "operator_dispatch_restart_smoke",
                "smoke",
                dispatch_signal,
            )
        else:
            self._append_smoke_checklist_item(
                items,
                "readiness_smoke",
                "smoke",
                readiness_ledger.status,
                readiness_ledger.latest,
                complete=self._readiness_smoke_entry_is_complete(readiness_ledger.latest) if readiness_ledger.latest else False,
                missing_action=readiness_ledger.next_action,
            )
            self._append_smoke_checklist_item(
                items,
                "operator_dispatch_restart_smoke",
                "smoke",
                dispatch_ledger.status,
                dispatch_ledger.latest,
                complete=(
                    self._operator_dispatch_restart_smoke_entry_is_complete(dispatch_ledger.latest)
                    if dispatch_ledger.latest
                    else False
                ),
                missing_action=dispatch_ledger.next_action,
            )

        if run and state:
            health_status = "pass"
            if run_health.level in {"stuck", "blocked"} or run_health.recommended_action in {"recover", "pause", "wait_approval", "ask_user"}:
                health_status = "block"
            elif run_health.level == "watch" or run_health.recommended_action != "continue":
                health_status = "warn"
            add_item(
                "run_health",
                "resume",
                health_status,
                f"Run health is {run_health.level}/{run_health.recommended_action}.",
                [f"score={run_health.score}", *[signal.id for signal in run_health.signals[:4]]],
                run_health.next_actions[0] if health_status != "pass" and run_health.next_actions else "",
            )
            policy_status = "pass" if policy_simulation and policy_simulation.safe_to_resume else "block"
            add_item(
                "resume_policy",
                "resume",
                policy_status,
                (
                    f"Resume policy is {policy_simulation.policy_action}."
                    if policy_simulation
                    else "Resume policy could not be computed."
                ),
                [
                    f"safe={policy_simulation.safe_to_resume if policy_simulation else False}",
                    f"predicted={policy_simulation.predicted_status if policy_simulation else ''}",
                ],
                policy_simulation.next_action if policy_status == "block" and policy_simulation else "",
            )
            context_status = "pass"
            if context_budget.pressure == "high":
                context_status = "block"
            elif context_budget.pressure == "medium":
                context_status = "warn"
            add_item(
                "context_budget",
                "context",
                context_status,
                f"Context pressure is {context_budget.pressure}.",
                [f"tokens={context_budget.estimated_tokens}", f"target={context_budget.target_tokens}"],
                "Checkpoint and compact context before resuming." if context_status != "pass" else "",
            )
            approval_status = "block" if pending_approvals else "pass"
            add_item(
                "approval_posture",
                "safety",
                approval_status,
                "Pending approvals must be resolved before autonomy continues." if pending_approvals else "No pending approvals for this run.",
                [f"pending={pending_approvals}"],
                "Resolve pending approvals in the dashboard." if pending_approvals else "",
            )
            handoff_ready = bool(state.handoff_summary.resume_prompt and state.handoff_summary.original_goal)
            add_item(
                "handoff_anchor",
                "memory",
                "pass" if handoff_ready else "warn",
                "Resume handoff is present." if handoff_ready else "Resume handoff is incomplete.",
                [f"memory_refs={len(state.memory_refs)}", f"resume_prompt={bool(state.handoff_summary.resume_prompt)}"],
                "Refresh/checkpoint the run handoff before resuming." if not handoff_ready else "",
            )
        else:
            attention_status = "pass" if queue.total_count == 0 else "warn"
            add_item(
                "operator_attention_queue",
                "supervisor",
                attention_status,
                "No existing operator attention queue items." if attention_status == "pass" else "Existing runs need operator attention.",
                [f"total={queue.total_count}", f"blocked={queue.blocked_count}", f"watch={queue.watch_count}"],
                queue.items[0].action if queue.items else "",
            )

        blocked = [item for item in items if item.status == "block"]
        warned = [item for item in items if item.status == "warn"]
        status = "blocked" if blocked else "attention" if warned else "ready"
        next_actions = [item.next_action for item in items if item.status in {"block", "warn"} and item.next_action]
        if not next_actions and status == "ready":
            next_actions = ["Start or resume the Ornith long-run loop with normal health and checkpoint gates."]
        summary = self._ornith_launch_summary(mode, status, blocked, warned)
        return OrnithLaunchChecklistReport(
            run_id=run.id if run else "",
            generated_at=utc_now(),
            mode=mode,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            ready_to_start=mode == "launch" and status != "blocked",
            ready_to_resume=mode == "resume" and status != "blocked",
            summary=summary,
            model_profile_id=self.model_profile.id,
            model_name=self.config.model_name,
            tool_profile=tool_profile,
            web_enabled=web_enabled,
            browser_enabled=browser_enabled,
            desktop_enabled=desktop_enabled,
            context_pressure=context_budget.pressure,
            context_tokens=context_budget.estimated_tokens,
            context_target_tokens=context_budget.target_tokens,
            pending_approval_count=pending_approvals,
            readiness_smoke_status=readiness_smoke_status,
            dispatch_restart_smoke_status=dispatch_smoke_status,
            run_health_level=run_health.level if run else "",
            run_health_action=run_health.recommended_action if run else "",
            supervisor_attention_count=queue.total_count,
            items=items,
            next_actions=list(dict.fromkeys(next_actions))[:8],
        ).model_dump()
    def _append_smoke_signal_checklist_item(
        self,
        items: list[OrnithLaunchChecklistItem],
        item_id: str,
        category: str,
        signal: dict[str, Any],
    ) -> None:
        signal_status = str(signal.get("status") or "unknown")
        requires_attention = bool(signal.get("requires_attention"))
        if not bool(signal.get("required")):
            status = "pass"
        elif requires_attention and signal_status in {"failed", "incomplete"}:
            status = "block"
        elif requires_attention:
            status = "warn"
        elif signal_status == "mixed":
            status = "warn"
        else:
            status = "pass"
        items.append(
            OrnithLaunchChecklistItem(
                id=item_id,
                category=category,
                status=status,  # type: ignore[arg-type]
                summary=str(signal.get("action") or f"{item_id} status is {signal_status}.").replace("_", " "),
                evidence=[
                    f"status={signal_status}",
                    f"required={bool(signal.get('required'))}",
                    f"latest={signal.get('latest_run_id') or 'none'}",
                ],
                next_action=str(signal.get("action") or "") if status in {"warn", "block"} else "",
            )
        )
    def _append_smoke_checklist_item(
        self,
        items: list[OrnithLaunchChecklistItem],
        item_id: str,
        category: str,
        ledger_status: str,
        latest: Any,
        *,
        complete: bool,
        missing_action: str,
    ) -> None:
        if latest is None or ledger_status == "never_run":
            status = "warn"
            summary = f"{item_id} has not run yet."
            evidence = ["status=never_run"]
            next_action = missing_action
        elif latest.status == "passed" and complete and ledger_status == "passed":
            status = "pass"
            summary = f"{item_id} is passed and complete."
            evidence = [f"run={latest.run_id}", f"steps={latest.passed_steps}/{latest.step_count}"]
            next_action = ""
        elif latest.status == "passed" and complete and ledger_status == "mixed":
            status = "warn"
            summary = f"{item_id} latest run passed, but recent history includes failures."
            evidence = [f"run={latest.run_id}", f"history={ledger_status}"]
            next_action = "Compare the latest passed smoke run against recent failed smoke evidence."
        elif latest.status in {"running", "failed"}:
            status = "block" if latest.status == "failed" else "warn"
            summary = f"{item_id} is {latest.status}."
            evidence = [f"run={latest.run_id}", f"status={latest.status}"]
            next_action = latest.next_action or missing_action
        else:
            status = "block"
            summary = f"{item_id} is incomplete."
            evidence = [
                f"run={latest.run_id}",
                f"status={latest.status}",
                f"steps={latest.passed_steps}/{latest.step_count}",
            ]
            next_action = "Rerun the smoke proof and inspect missing restart, handoff, replay, or context evidence."
        items.append(
            OrnithLaunchChecklistItem(
                id=item_id,
                category=category,
                status=status,  # type: ignore[arg-type]
                summary=summary.replace("_", " "),
                evidence=evidence,
                next_action=next_action,
            )
        )

    def _ornith_launch_summary(
        self,
        mode: str,
        status: str,
        blocked: list[OrnithLaunchChecklistItem],
        warned: list[OrnithLaunchChecklistItem],
    ) -> str:
        subject = "resume" if mode == "resume" else "launch"
        if status == "ready":
            return f"Ornith {subject} preflight is ready."
        if status == "blocked":
            return f"Ornith {subject} preflight is blocked by {len(blocked)} checklist item(s)."
        return f"Ornith {subject} preflight has {len(warned)} warning item(s) to review."

    def get_model_eval(self) -> dict[str, Any]:
        return run_ornith_fixture_eval(self.model_profile).model_dump()

    def get_model_quality_report(self) -> dict[str, Any]:
        return build_model_prompt_quality_report(self._runs_with_quality_inputs(), profile_id=self.model_profile.id).model_dump()

    def get_model_adaptation_proposal(self) -> dict[str, Any]:
        quality = build_model_prompt_quality_report(self._runs_with_quality_inputs(), profile_id=self.model_profile.id)
        eval_summary = run_ornith_fixture_eval(self.model_profile)
        return build_model_profile_adaptation_proposal(self.model_profile, quality, eval_summary).model_dump()

    def get_readiness_rehearsal(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return run.state.readiness_rehearsal.model_dump()

    def get_readiness_rehearsal_ledger(self, limit: int = 10) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 50))
        entries: list[ReadinessRehearsalLedgerEntry] = []
        for run in self.store.list_runs():
            report = run.state.readiness_rehearsal
            if report.status == "not_run":
                continue
            entries.append(self._readiness_rehearsal_ledger_entry(report, run_id=run.id))

        entries = entries[:bounded_limit]
        passed_count = sum(1 for entry in entries if entry.status == "passed")
        failed_count = sum(1 for entry in entries if entry.status == "failed")
        running_count = sum(1 for entry in entries if entry.status == "running")
        latest = entries[0] if entries else None
        if latest is None:
            status = "never_run"
            summary = "No readiness rehearsal has run yet."
            next_action = "Run the readiness-claim rehearsal smoke before trusting a milestone claim."
        elif latest.status == "running":
            status = "running"
            summary = f"Latest readiness rehearsal is still running for {latest.run_id}."
            next_action = "Wait for the latest readiness rehearsal to finish."
        elif latest.status == "failed":
            status = "failed"
            summary = f"Latest readiness rehearsal failed for {latest.run_id}."
            next_action = latest.next_action or "Inspect the failed rehearsal run before trusting readiness claims."
        elif failed_count:
            status = "mixed"
            summary = f"Latest readiness rehearsal passed, with {failed_count} failed rehearsal(s) in recent history."
            next_action = "Compare the latest passed rehearsal against recent failures before claiming a milestone."
        else:
            status = "passed"
            summary = f"Latest readiness rehearsal passed for {latest.run_id}."
            next_action = "Use the latest rehearsal run, replay, and handoff as smoke evidence."

        return ReadinessRehearsalLedgerReport(
            generated_at=utc_now(),
            status=status,
            summary=summary,
            total_count=len(entries),
            passed_count=passed_count,
            failed_count=failed_count,
            running_count=running_count,
            latest=latest,
            entries=entries,
            next_action=next_action,
        ).model_dump()

    def get_operator_dispatch_restart_smoke_ledger(self, limit: int = 10) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 50))
        entries: list[OperatorDispatchRestartSmokeLedgerEntry] = []
        for run in self.store.list_runs():
            report = run.state.operator_dispatch_restart_smoke
            if report.status == "not_run":
                continue
            entries.append(self._operator_dispatch_restart_smoke_ledger_entry(report, run_id=run.id))

        entries = entries[:bounded_limit]
        passed_count = sum(1 for entry in entries if entry.status == "passed")
        failed_count = sum(1 for entry in entries if entry.status == "failed")
        running_count = sum(1 for entry in entries if entry.status == "running")
        latest = entries[0] if entries else None
        if latest is None:
            status = "never_run"
            summary = "No operator-dispatch restart smoke has run yet."
            next_action = "Run the operator-dispatch restart smoke before trusting dispatch handoff evidence after restart."
        elif latest.status == "running":
            status = "running"
            summary = f"Latest operator-dispatch restart smoke is still running for {latest.run_id}."
            next_action = "Wait for the latest operator-dispatch restart smoke to finish."
        elif latest.status == "failed":
            status = "failed"
            summary = f"Latest operator-dispatch restart smoke failed for {latest.run_id}."
            next_action = latest.next_action or "Inspect the failed dispatch restart smoke before trusting supervision handoff."
        elif failed_count:
            status = "mixed"
            summary = f"Latest operator-dispatch restart smoke passed, with {failed_count} failed smoke run(s) in recent history."
            next_action = "Compare the latest passed dispatch restart smoke against recent failures."
        else:
            status = "passed"
            summary = f"Latest operator-dispatch restart smoke passed for {latest.run_id}."
            next_action = "Use the latest dispatch restart smoke as compact supervision-resume evidence."

        return OperatorDispatchRestartSmokeLedgerReport(
            generated_at=utc_now(),
            status=status,
            summary=summary,
            total_count=len(entries),
            passed_count=passed_count,
            failed_count=failed_count,
            running_count=running_count,
            latest=latest,
            entries=entries,
            next_action=next_action,
        ).model_dump()

    async def run_readiness_rehearsal(self) -> ReadinessRehearsalReport:
        run = self._create_readiness_rehearsal_run()
        report = run.state.readiness_rehearsal
        await self._event(run.id, "readiness_rehearsal_started", report.summary, {"readiness_rehearsal": report.model_dump()})
        steps: list[ReadinessRehearsalStep] = []
        restart_engine: AgentLoopEngine | None = None

        try:
            await self._run_one_milestone(run.id)
            refused = self.store.get_run(run.id)
            refused_event = self._latest_event(refused.id, "readiness_claim_blocked")
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    refused,
                    "refused_claim",
                    bool(refused_event)
                    and refused.status == "queued"
                    and refused.state.milestone == "act"
                    and not refused.state.readiness_completion.can_claim_milestone,
                    "Premature readiness claim is refused and routed back to act.",
                    [
                        f"event={refused_event.get('id') or 0}",
                        f"status={refused.status}",
                        f"milestone={refused.state.milestone}",
                        f"claim={refused.state.readiness_completion.can_claim_milestone}",
                    ],
                    event=refused_event,
                ),
            )

            await self._run_one_milestone(run.id)
            after_proof = self.store.get_run(run.id)
            latest_outcome = after_proof.state.objective_readiness_proof_outcomes[-1] if after_proof.state.objective_readiness_proof_outcomes else None
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    after_proof,
                    "routed_proof",
                    after_proof.state.milestone == "verify"
                    and latest_outcome is not None
                    and latest_outcome.item_id == "obsidian_handoffs"
                    and latest_outcome.tool == "obsidian_checkpoint",
                    "Routed readiness proof executes through the Obsidian checkpoint tool.",
                    [
                        f"milestone={after_proof.state.milestone}",
                        f"outcome={latest_outcome.item_id if latest_outcome else ''}:{latest_outcome.tool if latest_outcome else ''}",
                    ],
                ),
            )

            await self._run_one_milestone(run.id)
            after_verify = self.store.get_run(run.id)
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    after_verify,
                    "verify_after_proof",
                    after_verify.state.milestone == "checkpoint"
                    and bool(after_verify.state.commands_run)
                    and "git status --short" in after_verify.state.commands_run[-1],
                    "Verification milestone records a focused workspace command after the proof.",
                    [
                        f"milestone={after_verify.state.milestone}",
                        f"command={after_verify.state.commands_run[-1] if after_verify.state.commands_run else ''}",
                    ],
                ),
            )

            await self._run_one_milestone(run.id)
            checkpointed = self.store.get_run(run.id)
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    checkpointed,
                    "checkpoint_handoff",
                    checkpointed.state.milestone == "decide"
                    and bool(self.memory.read_run_note(run.id))
                    and "Resume AgentOrinth run" in checkpointed.state.handoff_summary.resume_prompt,
                    "Checkpoint writes the run note and compact handoff before restart.",
                    [
                        f"milestone={checkpointed.state.milestone}",
                        f"run_note={'yes' if self.memory.read_run_note(run.id) else 'no'}",
                    ],
                ),
            )

            scaffold_events = self.store.list_events(run.id, limit=300)
            checkpointed.state.self_scaffold = build_self_scaffold_report(checkpointed, scaffold_events, limit=12)
            reviewed_change_ids = [change.id for change in checkpointed.state.self_scaffold.changes[:3]]
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    checkpointed,
                    "self_scaffold_guard_seeded",
                    bool(reviewed_change_ids),
                    "Self-scaffold review has concrete compact change rows to accept before restart.",
                    [
                        f"changes={checkpointed.state.self_scaffold.change_count}",
                        f"review_ids={','.join(reviewed_change_ids[:3])}",
                    ],
                ),
            )
            await self._event(
                run.id,
                "operator_action_reviewed",
                "Operator accepted self-scaffold change intent for readiness rehearsal.",
                {
                    "operator_action": {
                        "reason": "self_scaffold",
                        "action": "Accept readiness rehearsal self-scaffold guard posture.",
                        "ui_target": "self_scaffold",
                    },
                    "self_scaffold_review": {
                        "status": "needs_review" if reviewed_change_ids else "none",
                        "change_count": checkpointed.state.self_scaffold.change_count,
                        "guard_count": checkpointed.state.self_scaffold.guard_count,
                        "reviewed_change_count": len(reviewed_change_ids),
                        "reviewed_change_ids": reviewed_change_ids,
                        "remaining_goal_review": False,
                    },
                },
            )
            review_event = self._latest_event(run.id, "operator_action_reviewed")
            review_events = self.store.list_events(run.id, limit=300)
            checkpointed.state.self_scaffold = build_self_scaffold_report(checkpointed, review_events, limit=12)
            checkpointed.state.self_scaffold_reviews = build_self_scaffold_review_report(checkpointed, review_events, limit=8)
            checkpointed.state.self_scaffold_rollback_intents = build_self_scaffold_rollback_intent_report(
                checkpointed,
                review_events,
                self_scaffold=checkpointed.state.self_scaffold,
                reviews=checkpointed.state.self_scaffold_reviews,
                limit=8,
            )
            checkpointed.state.handoff_summary = self._make_handoff(checkpointed, checkpointed.state)
            checkpointed = self.store.update_run(run.id, status=checkpointed.status, state=checkpointed.state)
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    checkpointed,
                    "self_scaffold_review",
                    checkpointed.state.self_scaffold_reviews.reviewed_change_count >= 1
                    and int(review_event.get("id") or 0) > 0,
                    "Self-scaffold review outcome is recorded before restart.",
                    [
                        f"event={review_event.get('id') or 0}",
                        f"reviewed={checkpointed.state.self_scaffold_reviews.reviewed_change_count}",
                    ],
                    event=review_event,
                ),
            )
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    checkpointed,
                    "post_review_handoff_alignment",
                    checkpointed.state.handoff_summary.current_objective == checkpointed.state.goal
                    and checkpointed.state.handoff_summary.next_action == checkpointed.state.next_step
                    and checkpointed.goal in checkpointed.state.handoff_summary.resume_prompt
                    and checkpointed.state.next_step in checkpointed.state.handoff_summary.resume_prompt,
                    "Post-review handoff preserves goal and next action before restart.",
                    [
                        f"goal_preserved={checkpointed.state.handoff_summary.current_objective == checkpointed.state.goal}",
                        f"next_preserved={checkpointed.state.handoff_summary.next_action == checkpointed.state.next_step}",
                    ],
                ),
            )

            self.store.update_run(run.id, status="paused", state=checkpointed.state)
            await self._event(run.id, "readiness_rehearsal_restart", "Simulated backend restart by recreating the engine over SQLite and Obsidian state.")
            restart_engine = AgentLoopEngine(
                self.config,
                RunStore(self.config.sqlite_path),
                ObsidianMemory(self.config.obsidian_vault_path),
                self.model,
                self.broker,
            )
            resumed = await restart_engine._resume_run_with_preflight(
                run.id,
                source="readiness_rehearsal",
                start_task=False,
            )
            resume_event = restart_engine._latest_event(run.id, "resume_preflight")
            self._append_rehearsal_step(
                steps,
                restart_engine._rehearsal_step(
                    resumed,
                    "restart_resume_preflight",
                    resumed.status == "queued"
                    and bool(resume_event)
                    and resume_event.get("data", {}).get("policy_simulation", {}).get("policy_action") == "complete",
                    "Fresh engine resumes from SQLite/Obsidian handoff with completion policy ready.",
                    [
                        f"event={resume_event.get('id') or 0}",
                        f"status={resumed.status}",
                        f"policy={resume_event.get('data', {}).get('policy_simulation', {}).get('policy_action', '')}",
                    ],
                    event=resume_event,
                ),
            )

            await restart_engine._run_one_milestone(run.id)
            completed = restart_engine.store.get_run(run.id)
            accepted_event = restart_engine._latest_event(run.id, "readiness_claim")
            completed_event = restart_engine._latest_event(run.id, "completed")
            self._append_rehearsal_step(
                steps,
                restart_engine._rehearsal_step(
                    completed,
                    "accepted_claim",
                    completed.status == "completed"
                    and bool(accepted_event)
                    and bool(completed_event)
                    and completed.state.readiness_completion.can_claim_milestone,
                    "Restarted run accepts the readiness claim and completes.",
                    [
                        f"claim_event={accepted_event.get('id') or 0}",
                        f"completed_event={completed_event.get('id') or 0}",
                        f"verified={completed.state.objective_readiness.verified_count}",
                    ],
                    event=accepted_event,
                ),
            )

            memory_context = restart_engine.memory.consult(completed.goal, run_id=completed.id)
            prompt, snapshot = restart_engine.context_compiler.compile(
                completed,
                completed.state,
                memory_context,
                restart_engine.store.list_events(completed.id, limit=20),
            )
            self._append_rehearsal_step(
                steps,
                restart_engine._rehearsal_step(
                    completed,
                    "compact_context",
                    snapshot.estimated_tokens <= restart_engine.context_compiler.target_tokens
                    and "## handoff" in prompt
                    and "## memory" in prompt,
                    "Compiled resume context stays bounded and uses handoff plus Obsidian memory.",
                    [
                        f"tokens={snapshot.estimated_tokens}/{restart_engine.context_compiler.target_tokens}",
                        "sections=" + ",".join(snapshot.sections[:12]),
                    ],
                ),
            )

            report = ReadinessRehearsalReport(
                run_id=completed.id,
                generated_at=utc_now(),
                status="passed",
                summary="Readiness rehearsal passed: refused claim, routed proof, checkpointed, resumed after restart, and accepted claim.",
                rehearsal_workspace=completed.workspace_path,
                restart_simulated=True,
                refused_event_id=int(refused_event.get("id") or 0),
                accepted_event_id=int(accepted_event.get("id") or 0),
                completed_event_id=int(completed_event.get("id") or 0),
                compact_context_tokens=snapshot.estimated_tokens,
                compact_context_sections=snapshot.sections,
                replay_attached=True,
                handoff_attached=True,
                self_scaffold_reviewed=checkpointed.state.self_scaffold_reviews.reviewed_change_count >= 1,
                self_scaffold_review_event_id=checkpointed.state.self_scaffold_reviews.latest_event_id,
                self_scaffold_reviewed_change_count=checkpointed.state.self_scaffold_reviews.reviewed_change_count,
                post_review_handoff_goal_preserved=checkpointed.state.handoff_summary.current_objective == checkpointed.state.goal,
                post_review_handoff_next_action_preserved=checkpointed.state.handoff_summary.next_action == checkpointed.state.next_step,
                post_review_resume_prompt_goal_preserved=checkpointed.goal in checkpointed.state.handoff_summary.resume_prompt,
                post_review_resume_prompt_next_action_preserved=checkpointed.state.next_step in checkpointed.state.handoff_summary.resume_prompt,
                next_action="Review replay or handoff for the rehearsal run.",
                steps=steps,
            )
            await restart_engine._event(completed.id, "readiness_rehearsal", report.summary, {"readiness_rehearsal": report.model_dump()})
            return restart_engine._store_readiness_rehearsal_report(completed.id, report)
        except Exception as exc:
            active_engine = restart_engine or self
            failed_run = active_engine.store.get_run(run.id)
            if not steps or steps[-1].status != "failed":
                steps.append(
                    active_engine._rehearsal_step(
                        failed_run,
                        "rehearsal_error",
                        False,
                        f"Readiness rehearsal failed: {exc}",
                        [str(exc)],
                    )
                )
            report = ReadinessRehearsalReport(
                run_id=failed_run.id,
                generated_at=utc_now(),
                status="failed",
                summary=f"Readiness rehearsal failed: {exc}",
                rehearsal_workspace=failed_run.workspace_path,
                restart_simulated=restart_engine is not None,
                next_action="Inspect the failed rehearsal step and replay before trusting readiness claims.",
                steps=steps,
            )
            await active_engine._event(failed_run.id, "readiness_rehearsal", report.summary, {"readiness_rehearsal": report.model_dump()})
            return active_engine._store_readiness_rehearsal_report(failed_run.id, report)

    def get_completion_audit(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_completion_audit(run, run.state).model_dump()

    def get_run_health(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_run_health(run, run.state).model_dump()

    def get_run_progress(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_run_progress(run, run.state).model_dump()

    def get_report_integrity(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        ornith_preflight = OrnithLaunchChecklistReport.model_validate(
            self.get_ornith_launch_checklist(run_id, state=run.state)
        )
        run.state.ornith_preflight = ornith_preflight
        run.state.handoff_summary.ornith_preflight = ornith_preflight
        return self._build_report_integrity(run, run.state).model_dump()

    def get_objective_readiness(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_objective_readiness(run, run.state).model_dump()

    def get_readiness_completion(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_readiness_completion(run, run.state).model_dump()

    def get_policy_simulation(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_policy_simulation(run, run.state).model_dump()

    def get_resume_decisions(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_resume_decision_report(run, run.state).model_dump()

    def get_action_readiness(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_action_readiness(run, run.state).model_dump()

    def get_action_readiness_decisions(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_action_readiness_decision_report(run, run.state).model_dump()

    def get_autonomy_decisions(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_autonomy_decision_report(run, run.state).model_dump()

    def get_recovery_decisions(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_recovery_decision_report(run, run.state).model_dump()

    def get_verification_outcomes(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return self._build_verification_outcome_report(run, run.state).model_dump()

    def get_resume_prompt_quality(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        report = build_resume_prompt_quality(run, handoff=run.state.handoff_summary)
        run.state.resume_prompt_quality = report
        run.state.handoff_summary.resume_prompt_quality = report
        self.store.update_run(run.id, state=run.state)
        return report.model_dump()

    def get_resume_handoff_diff(self, run_id: str) -> dict[str, Any]:
        return self.store.get_run(run_id).state.resume_handoff_diff.model_dump()

    def get_promotion_audit(self, run_id: str) -> dict[str, Any]:
        return self.store.get_run(run_id).state.promotion_audit.model_dump()

    def get_promotion_verification(self, run_id: str) -> dict[str, Any]:
        return self.store.get_run(run_id).state.promotion_verification.model_dump()

    def get_promotion_repair(self, run_id: str) -> dict[str, Any]:
        return self.store.get_run(run_id).state.promotion_repair.model_dump()

    def get_checkpoint_quality(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        note_text = self.memory.read_run_note(run.id)
        note_path = self.memory.vault_path / "Agent Runs" / f"{run.id}.md"
        report = build_checkpoint_quality(
            run,
            run.state,
            note_text=note_text,
            run_note_path=str(note_path),
            handoff=run.state.handoff_summary,
        )
        run.state.checkpoint_quality = report
        run.state.handoff_summary.checkpoint_quality = report
        self.store.update_run(run.id, state=run.state)
        return report.model_dump()

    def get_git_checkpoint(self, run_id: str) -> dict[str, Any]:
        return self.store.get_run(run_id).state.git_checkpoint.model_dump()

    def get_desktop_effect_proof_preview(self, run_id: str, limit: int = 8) -> dict[str, Any]:
        return self.store.get_run(run_id).state.desktop_effect_proof.model_dump()

    def get_readiness_source_ref_preview(self, run_id: str, limit: int = 20) -> dict[str, Any]:
        return self.store.get_run(run_id).state.readiness_source_ref_preview.model_dump()

    def _runs_with_quality_inputs(self) -> list[RunRecord]:
        runs: list[RunRecord] = []
        for run in self.store.list_runs():
            run_copy = run.model_copy(deep=True)
            self._build_verification_outcome_report(run_copy, run_copy.state)
            runs.append(run_copy)
        return runs

    def _ensure_task(self, run_id: str) -> None:
        existing = self._tasks.get(run_id)
        if existing and not existing.done():
            return
        try:
            run = self.store.get_run(run_id)
        except KeyError:
            return
        if self._lease_is_live(run.state.run_lease) and run.state.run_lease.owner_id != self.engine_id:
            return
        if run.status in {"queued", "running"}:
            self._acquire_run_lease(run_id, "task_scheduled")
        self._tasks[run_id] = asyncio.create_task(self._run_loop(run_id))

    def _cancel_task(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        heartbeat_task = self._heartbeat_tasks.get(run_id)
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()

    async def _run_loop(self, run_id: str) -> None:
        started = time.monotonic()
        heartbeat_task: asyncio.Task[None] | None = None
        try:
            leased = self._acquire_run_lease(run_id, "loop_start")
            self.store.update_run(run_id, status="running", state=leased.state)
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(run_id))
            self._heartbeat_tasks[run_id] = heartbeat_task
            await self._event(run_id, "status", "Milestone loop started.")
            await self._workstream(
                run_id,
                phase="orient",
                role="harness",
                title="Loop Started",
                summary="FlyOrnith started the milestone loop and is preparing compact project context.",
                next_action="Orient from Obsidian, SQLite state, handoff, and recent events.",
            )
            while True:
                self._heartbeat_run_lease(run_id, "loop_tick")
                run = self.store.get_run(run_id)
                if run.status in {"paused", "canceled", "completed", "blocked", "waiting_approval", "waiting_goal_confirmation"}:
                    return
                if run.state.step_count >= self.config.max_loop_steps:
                    await self._block(run_id, "Reached MAX_LOOP_STEPS.")
                    return
                if (time.monotonic() - started) > run.state.wall_clock_limit_minutes * 60:
                    await self._block(run_id, "Reached wall-clock loop budget.")
                    return

                await self._run_one_milestone(run_id)
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            run = self.store.get_run(run_id)
            state = run.state
            state.blockers.append(f"Engine error: {exc}")
            state.next_step = "Inspect backend error and decide recovery."
            state.handoff_summary = self._make_handoff(run, state)
            self.store.update_run(run_id, status="error", state=state)
            await self._event(run_id, "error", str(exc))
        finally:
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
            self._heartbeat_tasks.pop(run_id, None)
            try:
                current = self.store.get_run(run_id)
            except KeyError:
                return
            if current.status not in {"queued", "running"}:
                self._release_run_lease(run_id, current.status)

    async def _run_one_milestone(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        state = run.state
        memory_context = self._reload_anchor_context(run, state)

        if state.milestone == "orient":
            state.repo_map = build_repo_map(Path(run.workspace_path))
            self._ensure_task_graph(state)
            self._set_task_status(state, state.current_task_id or "task-orient", "in_progress", "Reloaded durable context.")
            state.latest_summary = "Reloaded Obsidian, current run note, SQLite state, handoff bundle, and latest events."
            state.next_step = "Review or create the current plan."
            state.completed_steps.append("Oriented from second-brain and durable state.")
            state.milestone = "plan"
            await self._save_state(run, state, "orient", state.latest_summary)
            return

        if state.milestone == "plan":
            if not state.current_plan:
                state.current_plan = await self._make_plan(run, state.context_snapshot.prompt_preview)
                objective_readiness = self._build_objective_readiness(run, state)
                state.current_plan = self._merge_objective_readiness_plan(run, state, state.current_plan, objective_readiness)
                state.task_graph = self._tasks_from_plan(state.current_plan, state.task_graph)
                state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
                state.completed_steps.append("Created milestone plan.")
                await self._workstream(
                    run_id,
                    phase="plan",
                    role="ornith",
                    title="Plan Created",
                    summary=f"Created a compact milestone plan with {len(state.current_plan)} step(s).",
                    next_action=state.current_plan[0] if state.current_plan else "Choose a safe tool action.",
                    refs={"plan_steps": len(state.current_plan)},
                )
            state.latest_summary = "Plan is ready for the next action."
            state.next_step = state.current_plan[0] if state.current_plan else "Choose a safe tool action."
            state.milestone = "act"
            await self._save_state(run, state, "plan", state.latest_summary)
            return

        if state.milestone == "act":
            if await self._apply_act_preflight_guard(run, state):
                return
            readiness_action = await self._apply_action_readiness_policy(run, state)
            if readiness_action is True:
                return
            self._set_task_status(state, state.current_task_id, "in_progress", "Selecting and executing next tool action.")
            action = readiness_action if isinstance(readiness_action, dict) else await self._choose_action(run, state.context_snapshot.prompt_preview)
            await self._workstream(
                run_id,
                phase="act",
                role="harness",
                title="Tool Selected",
                summary=f"Selected `{self._action_tool(action)}` for the next bounded action.",
                rationale=self._action_rationale(action),
                next_action="Execute the selected tool and record the result.",
                tool=self._action_tool(action),
                refs=self._action_refs(action),
            )
            run = self.store.update_run(run_id, state=state)
            result = await self._execute_action(run, action)
            await self._record_tool_result(run_id, result, action=action)
            run = self.store.get_run(run_id)
            state = run.state
            if self._prepare_post_action_retry_followup(run, state, result):
                updated = self.store.update_run(run_id, state=state)
                await self._event(
                    run_id,
                    "post_action_retry",
                    state.post_action_retries.summary,
                    {"post_action_retries": state.post_action_retries.model_dump()},
                )
                return
            if self._should_pause_for_recovery(state, result):
                state.latest_summary = state.recovery_plan.summary
                state.next_step = state.recovery_plan.next_action
                state.handoff_summary = self._make_handoff(run, state)
                run = self.store.update_run(run_id, status="paused", state=state)
                self.memory.append_checkpoint(run, state, "paused")
                await self._event(run_id, "recovery_plan", state.recovery_plan.summary, {"recovery_plan": state.recovery_plan.model_dump()})
                await self._workstream(
                    run_id,
                    phase="recovery",
                    role="harness",
                    title="Recovery Needed",
                    summary=state.recovery_plan.summary,
                    next_action=state.recovery_plan.next_action,
                    severity="blocked",
                    refs={"status": "paused"},
                )
                return
            if result.needs_approval:
                approval = self.store.create_approval(
                    run_id,
                    result.kind,
                    {"tool_name": result.kind, "args": result.data},
                    result.summary,
                )
                state.active_tool = result.kind
                state.blockers.append(result.summary)
                state.next_step = "Wait for user approval in the dashboard."
                state.handoff_summary = self._make_handoff(run, state)
                run = self.store.update_run(run_id, status="waiting_approval", state=state)
                self.memory.append_checkpoint(run, state, "waiting_approval")
                await self._event(run_id, "approval_required", result.summary, approval)
                await self._workstream(
                    run_id,
                    phase="approval",
                    role="operator",
                    title="Approval Required",
                    summary=result.summary,
                    rationale="The selected tool is approval-gated by FlyOrnith policy.",
                    next_action="Review and approve or reject this action in Focus Chat.",
                    tool=result.kind,
                    severity="blocked",
                    refs={"approval_id": approval.get("id"), "approval_kind": result.kind},
                )
                return

            state.latest_summary = self._summarize_result(result)
            state.next_step = "Verify the latest action."
            state.milestone = "verify"
            await self._save_state(run, state, "act", state.latest_summary)
            return

        if state.milestone == "verify":
            if self._should_defer_artifact_verification(run, state):
                state.latest_summary = "Verification deferred: the requested deliverable artifact does not exist yet."
                state.next_step = "Create the requested artifact before running verification."
                state.milestone = "act"
                await self._workstream(
                    run_id,
                    phase="verify",
                    role="harness",
                    title="Verification Deferred",
                    summary=state.latest_summary,
                    rationale="Artifact verification would only prove the workspace is still empty.",
                    next_action=state.next_step,
                    severity="watch",
                )
                await self._save_state(run, state, "verification_deferred", state.latest_summary)
                return
            result = await self._verify(run, state)
            await self._record_tool_result(run_id, result)
            run = self.store.get_run(run_id)
            state = run.state
            critic = await self._critic_review(run, state)
            if critic:
                state.risks.append(critic)
            state.latest_summary = self._summarize_result(result)
            state.next_step = "Write compact checkpoint and handoff."
            state.milestone = "checkpoint"
            await self._workstream(
                run_id,
                phase="verify",
                role="harness",
                title="Verification Checked",
                summary=state.latest_summary,
                next_action=state.next_step,
                tool=result.kind,
                result=result.summary,
                severity="normal" if result.ok else "watch",
            )
            await self._save_state(run, state, "verify", state.latest_summary)
            return

        if state.milestone == "checkpoint":
            self._record_acceptance_checkpoint(state)
            state.handoff_summary = self._make_handoff(run, state)
            state.next_step = "Decide whether to continue, replan, or finish."
            state.milestone = "decide"
            run = self.store.update_run(run_id, state=state)
            self.memory.append_checkpoint(run, state, "running")
            await self._event(run_id, "checkpoint", "Wrote compact checkpoint and refreshed handoff.", {"handoff": state.handoff_summary.model_dump()})
            await self._workstream(
                run_id,
                phase="checkpoint",
                role="harness",
                title="Checkpoint Written",
                summary="Wrote a compact Obsidian checkpoint and refreshed the handoff bundle.",
                next_action=state.next_step,
                refs={"milestone": state.milestone},
            )
            return

        if state.milestone == "decide":
            state.step_count += 1
            health_status = await self._apply_run_health_policy(run, state)
            if health_status:
                return

            drift = self._detect_drift(run, state)
            if drift:
                state.risks.append(drift)
                state.next_step = "Re-orient because drift was detected."
                state.milestone = "orient"
                await self._save_state(run, state, "drift", drift)
                return

            goal_proposal = await self._maybe_propose_goal_update(run, state)
            if goal_proposal:
                state.proposed_goal = goal_proposal["proposed_goal"]
                state.goal_revision_reason = goal_proposal["reason"]
                state.next_step = "Wait for goal revision confirmation."
                approval = self.store.create_approval(run_id, "goal_update", goal_proposal, goal_proposal["reason"])
                record_goal_proposal(
                    state,
                    run,
                    proposed_goal=goal_proposal["proposed_goal"],
                    reason=goal_proposal["reason"],
                    source="scheduled_review",
                    approval_id=int(approval.get("id") or 0),
                )
                state.handoff_summary = self._make_handoff(run, state)
                run = self.store.update_run(run_id, status="waiting_goal_confirmation", state=state)
                self.memory.append_checkpoint(run, state, "waiting_goal_confirmation")
                await self._event(
                    run_id,
                    "goal_proposed",
                    goal_proposal["reason"],
                    {**approval, "goal_evolution": state.goal_evolution.model_dump()},
                )
                await self._workstream(
                    run_id,
                    phase="approval",
                    role="operator",
                    title="Goal Confirmation Needed",
                    summary="Ornith proposed an updated goal and needs confirmation before continuing.",
                    rationale=goal_proposal["reason"],
                    next_action=state.next_step,
                    severity="blocked",
                    refs={"approval_id": approval.get("id"), "approval_kind": "goal_update"},
                )
                return

            completion_audit = self._completion_audit(run, state)
            if completion_audit.can_finish:
                readiness_claim = await self._apply_readiness_completion_claim_gate(run, state, completion_audit)
                if readiness_claim == "blocked":
                    return
                state.next_step = "Done."
                state.latest_summary = "Run finished after milestone decision."
                state.handoff_summary = self._make_handoff(run, state)
                run = self.store.update_run(run_id, status="completed", state=state)
                self.memory.append_final(run, state)
                await self._event(run_id, "completed", "Run completed.")
                await self._workstream(
                    run_id,
                    phase="completion",
                    role="harness",
                    title="Run Completed",
                    summary=state.latest_summary,
                    next_action=state.next_step,
                    refs={"status": "completed"},
                )
                return

            state.next_step = "Continue with the next safe action."
            state.milestone = "act"
            self._advance_task(state)
            await self._save_state(run, state, "decide", "Continuing to next action.")

    async def _apply_readiness_completion_claim_gate(
        self,
        run: RunRecord,
        state: RunState,
        completion_audit: Any,
    ) -> str:
        readiness_completion = self._build_readiness_completion(
            run,
            state,
            completion_audit=completion_audit,
        )
        if readiness_completion.status == "not_applicable":
            return "not_applicable"
        if readiness_completion.can_claim_milestone:
            state.readiness_completion = readiness_completion
            await self._event(
                run.id,
                "readiness_claim",
                readiness_completion.summary,
                {"accepted": True, "readiness_completion": readiness_completion.model_dump()},
            )
            return "ready"

        next_action, source_check = self._readiness_claim_next_action(readiness_completion)
        state.next_step = next_action
        state.latest_summary = readiness_completion.summary
        state.milestone = "act"
        state.readiness_completion = readiness_completion
        self._queue_readiness_completion_task(state, next_action)
        await self._event(
            run.id,
            "readiness_claim_blocked",
            readiness_completion.summary,
            {
                "accepted": False,
                "source_check": source_check,
                "next_action": next_action,
                "readiness_completion": readiness_completion.model_dump(),
            },
        )
        state.handoff_summary = self._make_handoff(run, state)
        self.store.update_run(run.id, state=state)
        return "blocked"

    def _readiness_claim_next_action(self, readiness_completion: Any) -> tuple[str, str]:
        preferred_checks = (
            "proof_preferences",
            "objective_readiness",
            "run_progress",
            "completion_audit",
            "readiness_rehearsal",
            "operator_dispatch_restart_smoke",
        )
        checks = list(getattr(readiness_completion, "checks", []) or [])
        for check_id in preferred_checks:
            check = next((item for item in checks if item.id == check_id and item.next_action), None)
            if check:
                return self._readiness_claim_action_text(check.next_action, check.id), check.id
        for action in getattr(readiness_completion, "next_actions", []) or []:
            if action:
                return self._readiness_claim_action_text(str(action), "readiness_completion"), "readiness_completion"
        return "Objective readiness: Run the smallest missing readiness proof before claiming completion.", "readiness_completion"

    def _readiness_claim_action_text(self, action: str, source_check: str) -> str:
        compact = " ".join(action.split())
        if source_check in {"proof_preferences", "objective_readiness"} and "objective readiness" not in compact.lower():
            return f"Objective readiness: {compact}"
        return compact or "Objective readiness: Run the smallest missing readiness proof before claiming completion."

    def _queue_readiness_completion_task(self, state: RunState, next_action: str) -> None:
        if not next_action:
            return
        if not any(self._same_plan_step(next_action, step) for step in state.current_plan):
            state.current_plan.insert(0, next_action)
            state.current_plan = state.current_plan[: max(1, self.model_profile.plan_max_steps)]
        for task in state.task_graph:
            if self._same_plan_step(next_action, task.title):
                task.status = "pending"
                task.notes = "Readiness completion claim routed back to this proof."
                state.current_task_id = task.id
                return
        lowered = next_action.lower()
        kind = "verify" if any(word in lowered for word in ("proof", "verify", "test", "check")) else "investigate"
        task = TaskNode(
            id=f"task-readiness-{uuid4().hex[:8]}",
            title=next_action,
            kind=kind,  # type: ignore[arg-type]
            status="pending",
            notes="Readiness completion claim routed back to the smallest missing proof.",
        )
        state.task_graph.insert(0, task)
        state.current_task_id = task.id

    async def _apply_run_health_policy(self, run: RunRecord, state: RunState) -> str:
        health = self._build_run_health(run, state)
        if health.recommended_action == "continue":
            return ""
        if health.recommended_action == "verify":
            state.next_step = health.next_actions[0] if health.next_actions else "Run focused acceptance verification."
            state.milestone = "act"
            self._advance_task(state)
            await self._save_state(run, state, "health_verify", health.summary)
            return "verify"
        if health.recommended_action == "recover":
            if state.recovery_plan.status != "active":
                self._activate_readiness_recovery_plan(state)
            if state.recovery_plan.status != "active":
                self._activate_objective_readiness_recovery_plan(state)
            state.next_step = (
                state.recovery_plan.next_action
                if state.recovery_plan.status == "active" and state.recovery_plan.next_action
                else health.next_actions[0]
                if health.next_actions
                else "Resume or replan recovery before continuing."
            )
            if state.recovery_plan.status == "active":
                state.current_plan = state.recovery_plan.steps or state.current_plan
                state.task_graph = self._tasks_from_plan(state.current_plan, state.task_graph)
                state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
            state.handoff_summary = self._make_handoff(run, state)
            paused = self.store.update_run(run.id, status="paused", state=state)
            self.memory.append_checkpoint(paused, state, "paused")
            await self._event(run.id, "health_policy", health.summary, {"run_health": health.model_dump()})
            return "recover"
        if health.recommended_action == "wait_approval":
            state.next_step = health.next_actions[0] if health.next_actions else "Resolve pending approvals in the dashboard."
            state.handoff_summary = self._make_handoff(run, state)
            waiting = self.store.update_run(run.id, status="waiting_approval", state=state)
            self.memory.append_checkpoint(waiting, state, "waiting_approval")
            await self._event(run.id, "health_policy", health.summary, {"run_health": health.model_dump()})
            return "wait_approval"
        if health.recommended_action in {"ask_user", "pause"}:
            state.next_step = health.next_actions[0] if health.next_actions else "Review run health before continuing."
            state.handoff_summary = self._make_handoff(run, state)
            paused = self.store.update_run(run.id, status="paused", state=state)
            self.memory.append_checkpoint(paused, state, "paused")
            await self._event(run.id, "health_policy", health.summary, {"run_health": health.model_dump()})
            return health.recommended_action
        return ""

    async def _apply_act_preflight_guard(self, run: RunRecord, state: RunState) -> bool:
        report = state.handoff_summary.resume_decisions
        latest_accepted = report.latest_accepted
        if not latest_accepted.id:
            return False
        if report.current_matches_last_accepted:
            return False
        if state.act_preflight_checked_decision_id == latest_accepted.id:
            return False

        state.act_preflight_checked_decision_id = latest_accepted.id
        summary = (
            "Act preflight detected current policy simulation differs from the latest "
            f"accepted resume snapshot #{latest_accepted.id}; re-orienting before acting."
        )
        self._append_unique(state.risks, summary)
        state.latest_summary = summary
        state.next_step = "Re-orient from durable context before selecting the next tool action."
        state.milestone = "orient"
        state.handoff_summary = self._make_handoff(run, state)
        self.store.update_run(run.id, state=state)
        await self._event(
            run.id,
            "act_preflight_reorient",
            summary,
            {
                "latest_accepted_resume_decision_id": latest_accepted.id,
                "resume_decisions": report.model_dump(),
            },
        )
        return True

    async def _apply_action_readiness_policy(self, run: RunRecord, state: RunState) -> bool | dict[str, Any]:
        readiness = self._build_action_readiness(run, state)
        if readiness.status == "ready":
            return False
        if readiness.status == "needs_proof":
            action = self._action_from_readiness(run, state, readiness)
            if action:
                state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=action)
                self._add_model_interaction(
                    state,
                    kind="action",
                    ok=True,
                    summary=f"Harness selected action-readiness tool: {action['tool']}.",
                    attempts=0,
                    output_keys=["tool", "args", "thought_summary"],
                )
                await self._event(
                    run.id,
                    "action_readiness_tool",
                    readiness.summary,
                    {"action_readiness": readiness.model_dump(), "selected_action": action},
                )
                await self._workstream(
                    run.id,
                    phase="act",
                    role="harness",
                    title="Readiness Tool Selected",
                    summary=readiness.summary,
                    rationale=readiness.recommended_action,
                    next_action="Execute the selected readiness proof tool.",
                    tool=self._action_tool(action),
                    refs={"status": readiness.status, "label": readiness.suggested_label},
                )
                return action
            return False

        if readiness.status == "reorient":
            state.latest_summary = readiness.summary
            state.next_step = readiness.recommended_action
            state.milestone = "orient"
            state.handoff_summary = self._make_handoff(run, state)
            self.store.update_run(run.id, state=state)
            await self._event(run.id, "action_readiness_reorient", readiness.summary, {"action_readiness": readiness.model_dump()})
            await self._workstream(
                run.id,
                phase="orient",
                role="harness",
                title="Action Readiness Hold",
                summary=readiness.summary,
                rationale="The run needs refreshed durable context before another tool action.",
                next_action=state.next_step,
                severity="watch",
                refs={"status": readiness.status},
            )
            return True

        if readiness.status == "needs_replan":
            state.latest_summary = readiness.summary
            state.next_step = readiness.recommended_action
            state.current_plan = []
            state.milestone = "plan"
            state.handoff_summary = self._make_handoff(run, state)
            self.store.update_run(run.id, state=state)
            await self._event(run.id, "action_readiness_replan", readiness.summary, {"action_readiness": readiness.model_dump()})
            await self._workstream(
                run.id,
                phase="plan",
                role="harness",
                title="Replan Needed",
                summary=readiness.summary,
                rationale="Action readiness policy found the current plan is no longer the safest next path.",
                next_action=state.next_step,
                severity="watch",
                refs={"status": readiness.status},
            )
            return True

        if readiness.status == "recover":
            state.latest_summary = readiness.summary
            state.next_step = readiness.recommended_action
            if state.recovery_plan.status == "active":
                state.current_plan = state.recovery_plan.steps or state.current_plan
                state.task_graph = self._tasks_from_plan(state.current_plan, state.task_graph)
                state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
            state.handoff_summary = self._make_handoff(run, state)
            paused = self.store.update_run(run.id, status="paused", state=state)
            self.memory.append_checkpoint(paused, state, "paused")
            await self._event(run.id, "action_readiness_policy", readiness.summary, {"action_readiness": readiness.model_dump()})
            await self._workstream(
                run.id,
                phase="recovery",
                role="harness",
                title="Recovery Hold",
                summary=readiness.summary,
                rationale="Action readiness policy paused the loop for recovery before continuing.",
                next_action=state.next_step,
                severity="blocked",
                refs={"status": readiness.status},
            )
            return True

        if readiness.status == "waiting_approval":
            state.latest_summary = readiness.summary
            state.next_step = readiness.recommended_action
            state.handoff_summary = self._make_handoff(run, state)
            waiting = self.store.update_run(run.id, status="waiting_approval", state=state)
            self.memory.append_checkpoint(waiting, state, "waiting_approval")
            await self._event(run.id, "action_readiness_policy", readiness.summary, {"action_readiness": readiness.model_dump()})
            await self._workstream(
                run.id,
                phase="approval",
                role="operator",
                title="Waiting For Approval",
                summary=readiness.summary,
                rationale="A pending approval must be resolved before FlyOrnith continues.",
                next_action=state.next_step,
                severity="blocked",
                refs={"status": readiness.status},
            )
            return True

        if readiness.status == "blocked":
            state.latest_summary = readiness.summary
            state.next_step = readiness.recommended_action
            state.handoff_summary = self._make_handoff(run, state)
            paused = self.store.update_run(run.id, status="paused", state=state)
            self.memory.append_checkpoint(paused, state, "paused")
            await self._event(run.id, "action_readiness_policy", readiness.summary, {"action_readiness": readiness.model_dump()})
            await self._workstream(
                run.id,
                phase="blocker",
                role="harness",
                title="Action Blocked",
                summary=readiness.summary,
                rationale="Action readiness policy found a blocker that needs operator attention.",
                next_action=state.next_step,
                severity="blocked",
                refs={"status": readiness.status},
            )
            return True

        return False

    def _action_from_readiness(self, run: RunRecord, state: RunState, readiness: Any) -> dict[str, Any] | None:
        tool = readiness.suggested_tool
        matching_recommendation = next(
            (
                item
                for item in rank_acceptance_recommendations(run)
                if item.tool_kind == tool and item.label == readiness.suggested_label
            ),
            None,
        )
        if matching_recommendation:
            recommended_action = self._action_from_recommendation(matching_recommendation)
            if recommended_action:
                return self._attach_recommendation_trace(state, matching_recommendation, recommended_action, source="harness")
        thought = f"Use action readiness recommendation for {readiness.suggested_label}: {readiness.recommended_action}"
        if tool == "run_tests":
            action = {
                "tool": "run_tests",
                "args": {"command": state.repo_map.test_commands[0] if state.repo_map.test_commands else "python -m pytest"},
                "thought_summary": thought,
            }
        elif tool == "browser_screenshot":
            return None
        elif tool == "desktop_screenshot":
            action = {"tool": "desktop_screenshot", "args": {}, "thought_summary": thought}
        elif tool == "obsidian_checkpoint":
            action = {"tool": "obsidian_checkpoint", "args": {"label": readiness.suggested_label}, "thought_summary": thought}
        elif tool == "web_search":
            action = {"tool": "web_search", "args": {"query": run.goal, "limit": 5}, "thought_summary": thought}
        elif tool == "ask_user":
            action = {"tool": "ask_user", "args": {"question": readiness.recommended_action}, "thought_summary": thought}
        else:
            return None
        return self._trace_action_if_recommended(state, action, source="harness")


    def _action_from_post_action_retry(self, run: RunRecord, state: RunState) -> dict[str, Any] | None:
        report = build_post_action_retry_report(run.model_copy(update={"state": state}))
        state.post_action_retries = report
        decision = report.latest_decision
        action = retry_action_from_decision(decision)
        if not action:
            return None
        mark_post_action_retry_selected(state, decision.id)
        return action
    def _action_from_objective_readiness_task(self, run: RunRecord, state: RunState) -> dict[str, Any] | None:
        task_text = self._objective_readiness_task_text(state)
        if "objective readiness" not in task_text.lower():
            return None
        report = state.objective_readiness if state.objective_readiness.run_id else self._build_objective_readiness(run, state)
        item = self._objective_readiness_item_for_task(report, task_text)
        if not item or item.status == "verified":
            return None
        proof = self._objective_readiness_proof_for_item(item)
        thought = f"Use objective-readiness proof for {item.id}: {proof.action or item.next_action}"
        metadata = {
            "thought_summary": thought,
            "objective_readiness_item_id": item.id,
            "objective_readiness_evidence_label": proof.evidence_label,
            "objective_readiness_proof_action": proof.action,
            "objective_readiness_proof_strategy": proof.strategy or "static_playbook",
        }
        if proof.requires_approval and proof.tool_kind not in {"ask_user"}:
            return {
                "tool": "ask_user",
                "args": {
                    "question": f"Objective readiness proof for {item.id} requires supervised approval: {proof.action}",
                    "reason": proof.success_signal or item.requirement,
                },
                **metadata,
            }
        if proof.tool_kind == "workspace_diff":
            return {
                "tool": "workspace_diff",
                "args": {"source_path": state.workspace_isolation.source_path or run.workspace_path},
                **metadata,
            }
        if proof.tool_kind == "run_tests":
            return {
                "tool": "run_tests",
                "args": {"command": self._objective_readiness_command(proof, state, default="python -m pytest")},
                **metadata,
            }
        if proof.tool_kind == "shell":
            return {
                "tool": "shell",
                "args": {
                    "command": self._objective_readiness_command(proof, state, default="python -m compileall backend\\app"),
                    "timeout": 120,
                },
                **metadata,
            }
        if proof.tool_kind == "obsidian_checkpoint":
            return {
                "tool": "obsidian_checkpoint",
                "args": {"label": proof.evidence_label or item.id, "objective_readiness_item": item.id},
                **metadata,
            }
        if proof.tool_kind == "ask_user":
            return {
                "tool": "ask_user",
                "args": {"question": proof.action or item.next_action, "reason": proof.success_signal or item.requirement},
                **metadata,
            }
        if proof.tool_kind == "file_read":
            return {
                "tool": "file_read",
                "args": {"path": self._objective_readiness_read_path(proof)},
                **metadata,
            }
        return None

    def _objective_readiness_proof_for_item(self, item: Any) -> ObjectiveReadinessProof:
        preferred = getattr(item, "preferred_proof", None)
        if preferred and (getattr(preferred, "tool_kind", "") or getattr(preferred, "action", "")):
            return ObjectiveReadinessProof(
                tool_kind=preferred.tool_kind,
                evidence_label=preferred.evidence_label,
                strategy=preferred.strategy,
                action=preferred.action,
                command_hint=preferred.command_hint,
                success_signal=preferred.reason,
            )
        return item.proof

    def _objective_readiness_command(
        self,
        proof: ObjectiveReadinessProof,
        state: RunState,
        *,
        default: str,
    ) -> str:
        hint = (proof.command_hint or "").strip()
        if hint and self._looks_like_workspace_command(hint):
            return hint
        if proof.tool_kind == "run_tests" and state.repo_map.test_commands:
            return state.repo_map.test_commands[0]
        return default

    def _looks_like_workspace_command(self, value: str) -> bool:
        lowered = value.strip().lower()
        return lowered.startswith(
            (
                "python ",
                "python -",
                "pytest",
                "npm ",
                "pnpm ",
                "yarn ",
                "node ",
                "npx ",
                "uv ",
                "ruff ",
                "mypy ",
                "tsc",
                ".\\",
            )
        )

    def _objective_readiness_read_path(self, proof: ObjectiveReadinessProof) -> str:
        hint = (proof.command_hint or "").strip()
        if hint and not hint.lower().startswith(("get ", "dashboard ")):
            return hint
        return "."

    def _objective_readiness_task_text(self, state: RunState) -> str:
        texts = [state.next_step]
        for task in state.task_graph:
            if task.id == state.current_task_id:
                texts.append(task.title)
                break
        return " ".join(text for text in texts if text)

    def _objective_readiness_item_for_task(self, report: Any, task_text: str) -> Any | None:
        lowered = task_text.lower()
        for item in getattr(report, "items", []):
            if item.status == "verified":
                continue
            proof = item.proof
            markers = [
                item.id,
                item.next_action,
                proof.tool_kind,
                proof.evidence_label,
            ]
            if any(marker and str(marker).lower() in lowered for marker in markers):
                return item
        return next((item for item in getattr(report, "items", []) if item.status != "verified"), None)

    def _reload_anchor_context(self, run: RunRecord, state: RunState) -> MemoryContext:
        memory_context = self.memory.consult(state.goal, run_id=run.id)
        state.memory_refs = [hit.path for hit in memory_context.hits]
        self._ensure_acceptance_evidence(state)
        self._build_run_health(run, state)
        state.handoff_summary = self._make_handoff(run, state)
        latest_events = self.store.list_events(run.id, limit=20)
        _prompt, snapshot = self.context_compiler.compile(run, state, memory_context, latest_events)
        state.context_snapshot = snapshot
        estimated_tokens = snapshot.estimated_tokens
        target_tokens = self.context_compiler.target_tokens
        pressure = "low"
        if estimated_tokens > target_tokens:
            pressure = "high"
        elif estimated_tokens > int(target_tokens * 0.75):
            pressure = "medium"
        state.context_budget = ContextBudget(
            target_tokens=target_tokens,
            estimated_tokens=estimated_tokens,
            last_compaction=utc_now() if pressure == "high" else state.context_budget.last_compaction,
            pressure=pressure,
        )
        if memory_context.warnings:
            state.risks.extend(warning for warning in memory_context.warnings if warning not in state.risks)
        return memory_context

    async def _make_plan(self, run: RunRecord, memory_text: str) -> list[str]:
        recommendation_text = self._recommendation_prompt_text(run.state)
        prompt = (
            "Plan for AgentOrinth running the Ornith local coding model. "
            f"Return 4 to {self.model_profile.plan_max_steps} short implementation/verification steps. "
            "Keep steps atomic because the harness will verify externally. Obsidian memory has already been read.\n\n"
            f"Original goal:\n{run.goal}\n\nActive goal:\n{run.state.goal}\n\n"
            f"Acceptance proof recommendations:\n{recommendation_text}\n\nObsidian context:\n{memory_text[:5000]}"
        )
        try:
            text = await self.model.chat(
                [
                    {"role": "system", "content": self.model_profile.planner_system},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.model_profile.default_temperature,
                max_tokens=700,
            )
            steps = [line.strip(" -0123456789.").strip() for line in text.splitlines() if line.strip()]
            steps = [step for step in steps if step]
            if steps:
                self._add_model_interaction(
                    run.state,
                    kind="plan",
                    ok=True,
                    summary=f"Model produced {min(len(steps), self.model_profile.plan_max_steps)} plan step(s).",
                    attempts=1,
                    raw_excerpt=text[:500],
                )
                return steps[: self.model_profile.plan_max_steps]
            self._add_model_interaction(
                run.state,
                kind="plan",
                ok=False,
                summary="Model plan was empty; deterministic fallback used.",
                attempts=1,
                fallback_used=True,
                raw_excerpt=text[:500],
            )
        except ModelError as exc:
            self._add_model_interaction(
                run.state,
                kind="plan",
                ok=False,
                summary="Model plan failed; deterministic fallback used.",
                attempts=1,
                fallback_used=True,
                error=str(exc),
            )
        return [
            "Consult Obsidian memory and current run note.",
            "Inspect the workspace before reading code.",
            "Use safe tool-gated actions for the next useful change or investigation.",
            "Verify with focused checks.",
            "Refresh the handoff bundle and compact Obsidian checkpoint.",
            "Decide whether to continue, replan, propose a goal update, or stop.",
        ]

    def _merge_objective_readiness_plan(
        self,
        run: RunRecord,
        state: RunState,
        plan: list[str],
        objective_readiness: Any,
    ) -> list[str]:
        if not self._is_harness_improvement_goal(run, state):
            return plan
        actions = self._objective_readiness_actions(objective_readiness, limit=2)
        if not actions:
            return plan
        merged = plan[:]
        added: list[str] = []
        for action in reversed(actions):
            step = f"Objective readiness: {action}"
            if any(self._same_plan_step(step, existing) for existing in merged):
                continue
            insert_at = 1 if merged else 0
            merged.insert(insert_at, step)
            added.append(action)
        if added:
            self._append_unique(
                state.facts_learned,
                "Objective readiness added plan action(s): " + "; ".join(reversed(added)),
            )
        return merged[: max(1, self.model_profile.plan_max_steps)]

    def _is_harness_improvement_goal(self, run: RunRecord, state: RunState) -> bool:
        return is_harness_improvement_goal(run.goal, state.goal)

    def _objective_readiness_actions(self, objective_readiness: Any, *, limit: int = 3) -> list[str]:
        actions = [
            str(action).strip()
            for action in getattr(objective_readiness, "next_actions", [])
            if str(action).strip()
        ]
        if not actions and getattr(objective_readiness, "recommended_action", ""):
            actions = [str(objective_readiness.recommended_action).strip()]
        unique: list[str] = []
        for action in actions:
            if action and action not in unique:
                unique.append(action)
        return unique[:limit]

    def _same_plan_step(self, first: str, second: str) -> bool:
        normalize = lambda value: " ".join(value.lower().replace("objective readiness:", "").split())
        return normalize(first) == normalize(second)

    async def _draft_missing_html_artifact_action(self, run: RunRecord, memory_text: str) -> dict[str, Any] | None:
        state = run.state
        if expected_artifact_suffix(run, state) != ".html":
            return None
        current_task = self._current_task(state)
        current_task_text = current_task.title if current_task else state.next_step
        criteria_text = "\n".join(f"- {item}" for item in state.acceptance_criteria[:8]) or "- Create the requested HTML deliverable."
        plan_text = "\n".join(f"{index}. {step}" for index, step in enumerate(state.current_plan[: self.model_profile.plan_max_steps], start=1))
        prompt = (
            "Author the missing browser deliverable for FlyOrnith. "
            "Return exactly one JSON object for a file_write tool call. "
            "Put the complete self-contained HTML document in args.content as a valid JSON string. "
            "Include compact inline CSS and JavaScript when the goal needs an interactive app. "
            "For computer-keyboard music apps, prefer a compact fully mapped playable range over an unlabeled full piano. "
            "Keep it complete but small enough for one local-model response.\n\n"
            f"Goal: {state.goal}\n"
            f"Current task: {current_task_text}\n"
            f"Acceptance criteria:\n{criteria_text}\n\n"
            f"Plan:\n{plan_text}\n\n"
            f"Compact context:\n{memory_text[: max(1200, self.model_profile.action_context_chars // 2)]}"
        )
        schema_hint = (
            '{"tool":"file_write","args":{"path":"index.html","content":"<!doctype html><html><head>'
            '<meta charset=\\"utf-8\\"><title>App</title></head><body><script></script></body></html>"},'
            '"thought_summary":"Authored a complete self-contained HTML app."}'
        )
        attempts = 0
        repaired = False
        raw_excerpt = ""
        try:
            action, metadata = await self._chat_json_with_metrics(prompt, max_tokens=5000, schema_hint=schema_hint)
            attempts = int(metadata.get("attempts") or 0)
            repaired = bool(metadata.get("repaired"))
            raw_excerpt = str(metadata.get("raw_excerpt") or "")
            normalized = normalize_model_action(action)
            if not normalized.action:
                raise ValueError(normalized.message)
            drafted = normalized.action
            if drafted["tool"] != "file_write":
                raise ValueError(f"Model returned {drafted['tool']} instead of file_write for missing HTML artifact.")
            args = drafted.get("args") if isinstance(drafted.get("args"), dict) else {}
            path = str(args.get("path") or "index.html").strip() or "index.html"
            content = str(args.get("content") or "")
            content_lines = args.get("content_lines")
            if not content and isinstance(content_lines, list):
                content = "\n".join(str(line) for line in content_lines)
                repaired = True
            if not path.lower().endswith(".html"):
                path = "index.html"
                repaired = True
            if len(content.strip()) < 500 or "<html" not in content.lower() or "</html>" not in content.lower():
                raise ValueError("Model did not provide a complete HTML document for file_write.")
            drafted["args"] = {"path": path, "content": content}
            drafted["thought_summary"] = drafted.get("thought_summary") or "Authored the missing HTML deliverable."
            self._add_model_interaction(
                state,
                kind="action",
                ok=True,
                summary=f"Model authored missing HTML artifact via file_write: {path}.",
                attempts=attempts,
                repaired=repaired or normalized.repaired,
                raw_excerpt=raw_excerpt,
                output_keys=sorted(str(key) for key in action.keys()),
            )
            return drafted
        except (ModelError, ValueError) as exc:
            error = str(exc)
            try:
                parsed_error = json.loads(error)
                attempts = int(parsed_error.get("attempts") or attempts)
                raw_excerpt = str(parsed_error.get("raw_excerpt") or raw_excerpt)
                error = str(parsed_error.get("error") or error)
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
            self._add_model_interaction(
                state,
                kind="action",
                ok=False,
                summary="Model failed to author the missing HTML artifact.",
                attempts=attempts,
                repaired=repaired,
                error=error,
                raw_excerpt=raw_excerpt,
                output_keys=[],
            )
            return None

    async def _chat_json(self, prompt: str, *, max_tokens: int, schema_hint: str) -> dict[str, Any]:
        payload, _metadata = await self._chat_json_with_metrics(prompt, max_tokens=max_tokens, schema_hint=schema_hint)
        return payload

    async def _chat_json_with_metrics(self, prompt: str, *, max_tokens: int, schema_hint: str) -> tuple[dict[str, Any], dict[str, Any]]:
        messages = [
            {"role": "system", "content": self.model_profile.json_system},
            {"role": "user", "content": f"{prompt}\n\nRequired JSON shape example:\n{schema_hint}"},
        ]
        last_error = "unknown JSON parse error"
        raw_excerpt = ""
        for attempt in range(self.model_profile.json_retries + 1):
            text = await self.model.chat(
                messages,
                temperature=self.model_profile.default_temperature,
                max_tokens=max_tokens,
            )
            raw_excerpt = text[:500]
            try:
                result = extract_json_object_result(text)
                return result.payload, {
                    "attempts": attempt + 1,
                    "repaired": result.repaired,
                    "repair_strategy": result.strategy,
                    "raw_excerpt": raw_excerpt,
                    "error": "",
                }
            except ValueError as exc:
                last_error = str(exc)
                messages = [
                    {
                        "role": "system",
                        "content": self.model_profile.json_system,
                    },
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was not valid JSON for AgentOrinth. "
                            f"Return exactly one JSON object matching this example and nothing else:\n{schema_hint}"
                        ),
                    },
                ]
                if attempt >= self.model_profile.json_retries:
                    break
        raise ValueError(json.dumps({"error": last_error, "attempts": self.model_profile.json_retries + 1, "raw_excerpt": raw_excerpt}))

    def _add_model_interaction(
        self,
        state: RunState,
        *,
        kind: str,
        ok: bool,
        summary: str,
        attempts: int = 0,
        repaired: bool = False,
        fallback_used: bool = False,
        error: str = "",
        raw_excerpt: str = "",
        output_keys: list[str] | None = None,
    ) -> None:
        state.model_interactions.append(
            ModelInteractionRecord(
                id=f"model-{uuid4().hex[:8]}",
                kind=kind,  # type: ignore[arg-type]
                ok=ok,
                attempts=attempts,
                repaired=repaired,
                fallback_used=fallback_used,
                summary=summary,
                error=error[:500],
                raw_excerpt=raw_excerpt[:500],
                output_keys=output_keys or [],
                created_at=utc_now(),
            )
        )
        state.model_interactions = state.model_interactions[-40:]

    async def _choose_action(self, run: RunRecord, memory_text: str) -> dict[str, Any]:
        state = run.state
        self._ensure_acceptance_evidence(state)
        state.action_context = build_action_context_pack(run.model_copy(update={"state": state}))
        artifact_pending = bool(expected_artifact_suffix(run, state) and not expected_artifact_exists(run, state))
        retry_action = self._action_from_post_action_retry(run, state)
        if retry_action:
            state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=retry_action)
            self._add_model_interaction(
                state,
                kind="action",
                ok=True,
                summary=f"Harness selected post-action retry tool: {retry_action['tool']}.",
                attempts=0,
                output_keys=["tool", "args", "thought_summary"],
            )
            return retry_action
        objective_action = None if artifact_pending else self._action_from_objective_readiness_task(run, state)
        if objective_action:
            state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=objective_action)
            self._add_model_interaction(
                state,
                kind="action",
                ok=True,
                summary=f"Harness selected objective-readiness proof tool: {objective_action['tool']}.",
                attempts=0,
                output_keys=["tool", "args", "thought_summary"],
            )
            return objective_action
        if artifact_pending and not self._has_workspace_material_for_browser_proof(state):
            artifact_action = await self._draft_missing_html_artifact_action(run, memory_text)
            if artifact_action:
                state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=artifact_action)
                return artifact_action
        if artifact_pending and (state.step_count > 0 or state.tool_calls or state.completed_steps):
            artifact_action = artifact_creation_action(run, state)
            if artifact_action:
                state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=artifact_action)
                self._add_model_interaction(
                    state,
                    kind="action",
                    ok=True,
                    summary=f"Harness selected artifact creation tool: {artifact_action['tool']}.",
                    attempts=0,
                    output_keys=["tool", "args", "thought_summary"],
                )
                return artifact_action
        recommended = self._recommended_tool_action(state, source="harness", suppress_verification=artifact_pending)
        if recommended and (state.step_count > 0 or state.tool_calls or state.completed_steps):
            state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=recommended)
            self._add_model_interaction(
                state,
                kind="action",
                ok=True,
                summary=f"Harness selected acceptance recommendation: {recommended['tool']}.",
                attempts=0,
                output_keys=["tool", "args", "thought_summary"],
            )
            return recommended
        if state.step_count == 0 and not state.tool_calls and not artifact_pending:
            initial_action = {"tool": "file_read", "args": {"path": "."}, "thought_summary": "Inspect workspace file list first."}
            state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=initial_action)
            return initial_action

        action_context_text = state.action_context.compact_prompt or build_action_context_pack(run.model_copy(update={"state": state})).compact_prompt
        recommendation_text = self._recommendation_prompt_text(state)
        artifact_instruction = (
            "artifact_missing: author the deliverable now with file_write or patch_apply; read-only proof waits for files.\n"
            if artifact_pending
            else ""
        )
        prompt = (
            "Choose the next safe tool action for AgentOrinth running Ornith. "
            "Return one strict JSON object with keys: tool, args, thought_summary. "
            f"Allowed tools: {', '.join(TOOL_NAMES)}. "
            "Do not request raw logs. Prefer compact, verifiable actions. "
            "If acceptance proof recommendations are available, choose the smallest recommended proof action before broad implementation work. "
            "Use file_read for orientation, patch_propose before patch_apply, and run_tests/git_diff for verification.\n\n"
            f"Original goal: {run.goal}\nActive goal: {state.goal}\n"
            f"Ornith action context:\n{action_context_text}\n\n"
            f"{artifact_instruction}"
            f"Acceptance proof recommendations:\n{recommendation_text}\n"
            f"Compiled context:\n{memory_text[: self.model_profile.action_context_chars]}"
        )
        attempts = 0
        repaired = False
        raw_excerpt = ""
        error = ""
        try:
            action, metadata = await self._chat_json_with_metrics(
                prompt,
                max_tokens=700,
                schema_hint='{"tool":"file_read","args":{"path":"."},"thought_summary":"Inspect workspace."}',
            )
            attempts = int(metadata.get("attempts") or 0)
            repaired = bool(metadata.get("repaired"))
            raw_excerpt = str(metadata.get("raw_excerpt") or "")
            normalized = normalize_model_action(action)
            if normalized.action:
                if artifact_pending and self._artifact_action_is_nonproductive_before_files(state, normalized.action):
                    error = f"Model chose {normalized.action.get('tool')} before creating the requested artifact."
                    raise ValueError(error)
                traced_action = self._trace_action_if_recommended(state, normalized.action, source="model")
                state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=traced_action)
                self._add_model_interaction(
                    state,
                    kind="action",
                    ok=True,
                    summary=f"Model selected tool {traced_action['tool']}.{(' ' + normalized.message) if normalized.message else ''}",
                    attempts=attempts,
                    repaired=repaired or normalized.repaired,
                    raw_excerpt=raw_excerpt,
                    output_keys=sorted(str(key) for key in action.keys()),
                )
                return traced_action
            error = normalized.message
        except (ModelError, ValueError) as exc:
            error = str(exc)
            try:
                parsed_error = json.loads(error)
                attempts = int(parsed_error.get("attempts") or attempts)
                raw_excerpt = str(parsed_error.get("raw_excerpt") or raw_excerpt)
                error = str(parsed_error.get("error") or error)
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        recommendation_fallback = self._recommended_tool_action(
            state,
            allow_ask_user=True,
            source="fallback",
            suppress_verification=artifact_pending,
        )
        if recommendation_fallback:
            fallback = recommendation_fallback
        elif artifact_pending:
            fallback = {
                "tool": "ask_user",
                "args": {
                    "question": "Ornith did not return a valid artifact-creation action. Ask it to create the requested files with file_write.",
                    "reason": error or "Artifact is missing and verification/read-only tools would not make progress.",
                },
                "thought_summary": "Pause instead of pretending read-only or verification tools created the requested artifact.",
            }
        elif state.web_enabled and any(term in state.goal.lower() for term in ("internet", "web", "latest", "search")):
            fallback = {"tool": "web_search", "args": {"query": state.goal, "limit": 5}}
        else:
            fallback = {"tool": "git_status", "args": {}}
        state.action_context = build_action_context_pack(run.model_copy(update={"state": state}), selected_action=fallback)
        self._add_model_interaction(
            state,
            kind="action",
            ok=False,
            summary=f"Model action fallback used: {fallback['tool']}.",
            attempts=attempts,
            repaired=repaired,
            fallback_used=True,
            error=error,
            raw_excerpt=raw_excerpt,
        )
        return fallback

    def _recommendation_prompt_text(self, state: RunState) -> str:
        if not state.acceptance_recommendations:
            return "None."
        lines: list[str] = []
        prompt_run = RunRecord(id="prompt", title="prompt", goal=state.goal, status="queued", workspace_path="", state=state, created_at="", updated_at="")
        for item in rank_acceptance_recommendations(prompt_run)[:8]:
            availability = "available" if item.available else "unavailable"
            hint = f" hint={item.command_hint}" if item.command_hint else ""
            lines.append(
                f"- {item.criterion} missing {item.label}: {item.tool_kind} ({availability}) {item.action}{hint}"
            )
        return "\n".join(lines)

    def _recommended_tool_action(
        self,
        state: RunState,
        *,
        allow_ask_user: bool = False,
        source: str = "harness",
        suppress_verification: bool = False,
    ) -> dict[str, Any] | None:
        rank_run = RunRecord(id="rank", title="rank", goal=state.goal, status="queued", workspace_path="", state=state, created_at="", updated_at="")
        for item in rank_acceptance_recommendations(rank_run):
            if suppress_verification and item.label == "verification":
                continue
            if item.label == "verification" and self._open_edit_required_without_evidence(state):
                continue
            if not item.available and not allow_ask_user:
                continue
            if item.tool_kind == "patch_propose":
                continue
            action = self._action_from_recommendation(item)
            if action:
                return self._attach_recommendation_trace(state, item, action, source=source)
        return None

    def _open_edit_required_without_evidence(self, state: RunState) -> bool:
        if self._has_workspace_material_for_browser_proof(state):
            return False
        return any(
            item.status != "verified"
            and "edit" in set(item.required_labels)
            and "edit" not in set(item.matched_labels)
            for item in state.acceptance_evidence
        )

    def _trace_action_if_recommended(
        self,
        state: RunState,
        action: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        if action.get("recommendation_trace_id"):
            return action
        tool = str(action.get("tool") or "")
        match = next(
            (
                item
                for item in state.acceptance_recommendations
                if item.tool_kind == tool and (item.available or tool == "ask_user")
            ),
            None,
        )
        if not match:
            return action
        return self._attach_recommendation_trace(state, match, action, source=source)

    def _attach_recommendation_trace(
        self,
        state: RunState,
        recommendation: AcceptanceEvidenceRecommendation,
        action: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        trace = AcceptanceRecommendationTrace(
            id=f"rec-trace-{uuid4().hex[:8]}",
            recommendation_id=recommendation.id,
            criterion_id=recommendation.criterion_id,
            criterion=recommendation.criterion,
            label=recommendation.label,
            recommended_tool=recommendation.tool_kind,
            selected_tool=str(action.get("tool") or ""),
            source=source if source in {"harness", "model", "fallback"} else "harness",  # type: ignore[arg-type]
            action_summary=str(action.get("thought_summary") or recommendation.action),
            selected_at=utc_now(),
        )
        state.acceptance_recommendation_traces.append(trace)
        state.acceptance_recommendation_traces = state.acceptance_recommendation_traces[-40:]
        traced_action = dict(action)
        traced_action["recommendation_trace_id"] = trace.id
        traced_action["recommendation_id"] = recommendation.id
        traced_action["recommendation_label"] = recommendation.label
        traced_action["recommendation_criterion_id"] = recommendation.criterion_id
        return traced_action

    def _action_from_recommendation(self, item: AcceptanceEvidenceRecommendation) -> dict[str, Any] | None:
        thought = f"Use acceptance recommendation for {item.label}: {item.reason or item.action}"
        if item.tool_kind == "run_tests":
            return {
                "tool": "run_tests",
                "args": {"command": item.command_hint or "python -m pytest"},
                "thought_summary": thought,
            }
        if item.tool_kind == "browser_screenshot":
            url = self._url_from_hint(item.command_hint)
            if not url:
                return None
            return {
                "tool": "browser_screenshot",
                "args": {"url": url},
                "thought_summary": thought,
            }
        if item.tool_kind == "desktop_screenshot":
            return {"tool": "desktop_screenshot", "args": {}, "thought_summary": thought}
        if item.tool_kind == "obsidian_checkpoint":
            return {
                "tool": "obsidian_checkpoint",
                "args": {"criterion": item.criterion, "label": item.label},
                "thought_summary": thought,
            }
        if item.tool_kind == "web_search":
            return {
                "tool": "web_search",
                "args": {"query": item.command_hint or item.criterion, "limit": 5},
                "thought_summary": thought,
            }
        if item.tool_kind == "ask_user":
            return {
                "tool": "ask_user",
                "args": {"question": item.action, "reason": item.reason},
                "thought_summary": thought,
            }
        return None

    def _url_from_hint(self, hint: str) -> str:
        marker = "url="
        if marker not in hint:
            return ""
        value = hint.split(marker, 1)[1].strip()
        return value.split()[0].strip(",;")

    async def _execute_action(self, run: RunRecord, action: dict[str, Any]) -> ToolResult:
        tool_name = str(action.get("tool") or action.get("action") or "file_read")
        if tool_name == "inspect_workspace":
            tool_name = "file_read"
            action["args"] = {"path": "."}
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        state = run.state
        if tool_name.startswith("web_") and not state.web_enabled:
            return ToolResult(False, tool_name, "Web tools are disabled for this run.", args)
        if tool_name.startswith("browser_") and not state.browser_enabled:
            return ToolResult(False, tool_name, "Browser tools are disabled for this run.", args)
        if tool_name.startswith("desktop_") and not state.desktop_enabled:
            return ToolResult(False, tool_name, "Desktop tools are disabled for this run.", args)
        runner = ToolRunner(Path(run.workspace_path), self.config, approval_mode=state.approval_mode)
        return await runner.execute(tool_name, args)

    async def _verify(self, run: RunRecord, state: RunState) -> ToolResult:
        runner = ToolRunner(Path(run.workspace_path), self.config, approval_mode=state.approval_mode)
        if state.files_touched:
            return await runner.execute("git_diff", {})
        if state.commands_run:
            return ToolResult(True, "run_tests", "Latest command result was recorded; no extra verification command selected.", {})
        return await runner.execute("git_status", {})

    def _should_defer_artifact_verification(self, run: RunRecord, state: RunState) -> bool:
        return bool(
            expected_artifact_suffix(run, state)
            and not expected_artifact_exists(run, state)
            and not state.files_touched
        )

    def _artifact_action_is_nonproductive_before_files(self, state: RunState, action: dict[str, Any]) -> bool:
        if self._has_workspace_material_for_browser_proof(state):
            return False
        tool = str(action.get("tool") or action.get("action") or "")
        return tool in {
            "browser_open",
            "browser_screenshot",
            "desktop_screenshot",
            "file_read",
            "git_diff",
            "git_status",
            "run_tests",
            "shell",
        }

    async def _critic_review(self, run: RunRecord, state: RunState) -> str:
        if not state.tool_calls:
            return ""
        prompt = (
            "You are a verifier for a local coding-agent harness. "
            "Find concrete risks only. Return JSON: {\"risk\": string}. Empty risk means no issue.\n\n"
            f"Goal: {state.goal}\nLatest handoff: {state.handoff_summary.model_dump_json()[: self.model_profile.critic_context_chars]}\n"
            f"Latest tools: {json.dumps([call.model_dump() for call in state.tool_calls[-5:]])[: self.model_profile.critic_context_chars]}"
        )
        try:
            payload, metadata = await self._chat_json_with_metrics(
                prompt,
                max_tokens=400,
                schema_hint='{"risk":""}',
            )
            self._add_model_interaction(
                state,
                kind="critic",
                ok=True,
                summary="Model critic JSON parsed.",
                attempts=int(metadata.get("attempts") or 0),
                repaired=bool(metadata.get("repaired")),
                raw_excerpt=str(metadata.get("raw_excerpt") or ""),
                output_keys=sorted(str(key) for key in payload.keys()),
            )
            return str(payload.get("risk") or "").strip()
        except (ModelError, ValueError) as exc:
            self._add_model_interaction(
                state,
                kind="critic",
                ok=False,
                summary="Model critic failed; no critic risk recorded.",
                fallback_used=True,
                error=str(exc),
            )
            return ""

    async def _record_tool_result(
        self,
        run_id: str,
        result: ToolResult,
        *,
        action: dict[str, Any] | None = None,
    ) -> None:
        run = self.store.get_run(run_id)
        state = run.state
        state.active_tool = result.kind
        state.tool_calls.append(
            ToolCallRecord(
                id=f"tool-{uuid4().hex[:8]}",
                name=result.kind,
                args=result.data,
                ok=result.ok,
                summary=result.summary,
                needs_approval=result.needs_approval,
                created_at=utc_now(),
            )
        )
        state.tool_calls = state.tool_calls[-40:]
        state.web_sources.extend(result.web_sources)
        state.web_sources = state.web_sources[-40:]
        state.desktop_snapshots.extend(result.desktop_snapshots)
        state.desktop_snapshots = state.desktop_snapshots[-20:]
        patch_proposals = getattr(result, "patch_proposals", [])
        patch_applications = getattr(result, "patch_applications", [])
        workspace_diff = getattr(result, "workspace_diff", None)
        workspace_promotions = getattr(result, "workspace_promotions", [])
        state.patch_proposals.extend(patch_proposals)
        state.patch_proposals = state.patch_proposals[-20:]
        state.patch_applications.extend(patch_applications)
        state.patch_applications = state.patch_applications[-20:]
        if workspace_diff:
            state.workspace_diff = workspace_diff
        state.workspace_promotions.extend(workspace_promotions)
        state.workspace_promotions = state.workspace_promotions[-20:]

        if result.ok:
            resolve_post_action_retry(state, action or {}, result)
            state.completed_steps.append(result.summary)
            state.facts_learned.append(result.summary)
            state.failure_counts.pop(result.kind, None)
            if state.recovery_plan.status == "active":
                state.recovery_plan.status = "resolved"
                state.recovery_plan.resolved_at = utc_now()
                state.recovery_history.append(state.recovery_plan)
                state.recovery_history = state.recovery_history[-10:]
                state.facts_learned.append(f"Resolved recovery plan: {state.recovery_plan.summary}")
            if result.kind == "shell" and result.data.get("command"):
                state.commands_run.append(str(result.data.get("command")))
            if result.kind == "file_write" and result.data.get("path"):
                state.files_touched.append(str(result.data.get("path")))
            if result.kind in {"patch_apply", "patch_rollback"}:
                touched = result.data.get("files")
                if isinstance(touched, list):
                    state.files_touched.extend(str(item) for item in touched)
            if result.kind == "workspace_promote":
                touched = result.data.get("files")
                if isinstance(touched, list):
                    state.files_touched.extend(str(item) for item in touched)
            if self._result_advances_current_task(state, result):
                self._set_task_status(state, state.current_task_id, "completed", result.summary)
        elif not result.needs_approval:
            failure_kind = self._classify_failure(result)
            count = state.failure_counts.get(result.kind, 0) + 1
            state.failure_counts[result.kind] = count
            self._record_failure(state, failure_kind, result)
            self._set_task_status(state, state.current_task_id, "failed", result.summary)
            state.risks.append(result.summary)
            if action and action.get("post_action_retry_id"):
                resolve_post_action_retry(state, action, result)
            elif count < 3:
                retry_decision = propose_post_action_retry(
                    run.model_copy(update={"state": state}),
                    result=result,
                    action=action or {},
                    failure_kind=failure_kind,
                    attempt_count=count,
                )
                if retry_decision:
                    state.post_action_retries.decisions.append(retry_decision)
                    state.post_action_retries.decisions = state.post_action_retries.decisions[-20:]
                    state.post_action_retries = build_post_action_retry_report(run.model_copy(update={"state": state}))
                    self._append_unique(state.facts_learned, f"Queued post-action retry: {retry_decision.selected_action}")
            if count >= 3:
                state.blockers.append(f"Repeated failure in {result.kind}: {result.summary}")
                self._activate_recovery_plan(state, failure_kind, result, count)
        if not result.needs_approval:
            state.active_tool = ""
        self._update_acceptance_evidence(state, result)
        objective_outcome = self._record_objective_readiness_proof_outcome(run, state, action or {}, result)
        self._resolve_recommendation_trace(state, action or {}, result)
        if objective_outcome:
            state.objective_readiness = self._build_objective_readiness(run, state)
        state.post_action_retries = build_post_action_retry_report(run.model_copy(update={"state": state}))
        state.handoff_summary = self._make_handoff(run, state)
        self.store.update_run(run_id, state=state)
        await self._event(
            run_id,
            result.kind,
            result.summary,
            {
                **result.data,
                "ok": result.ok,
                "needs_approval": result.needs_approval,
                "web_sources": [source.model_dump() for source in result.web_sources],
                "desktop_snapshots": [snapshot.model_dump() for snapshot in result.desktop_snapshots],
                "patch_proposals": [proposal.model_dump() for proposal in patch_proposals],
                "patch_applications": [application.model_dump() for application in patch_applications],
                "workspace_diff": workspace_diff.model_dump() if workspace_diff else None,
                "workspace_promotions": [promotion.model_dump() for promotion in workspace_promotions],
                "objective_readiness_proof_outcome": objective_outcome.model_dump() if objective_outcome else None,
            },
        )
        await self._workstream(
            run_id,
            phase="act",
            role="tool",
            title="Tool Result" if result.ok else "Tool Failed",
            summary=result.summary,
            rationale=self._action_rationale(action or {}),
            next_action=state.next_step or ("Wait for approval." if result.needs_approval else "Choose the next safe action."),
            tool=result.kind,
            result=result.summary,
            severity="blocked" if result.needs_approval else ("normal" if result.ok else "watch"),
            refs={
                **self._action_refs(action or {}),
                "ok": result.ok,
                "needs_approval": result.needs_approval,
                "web_sources": len(result.web_sources),
                "desktop_snapshots": len(result.desktop_snapshots),
            },
        )

    def _record_objective_readiness_proof_outcome(
        self,
        run: RunRecord,
        state: RunState,
        action: dict[str, Any],
        result: ToolResult,
    ) -> ObjectiveReadinessProofOutcome | None:
        item_id = str(action.get("objective_readiness_item_id") or "")
        if not item_id:
            return None
        outcome = self._objective_readiness_proof_result(run, state, item_id, result)
        record = ObjectiveReadinessProofOutcome(
            id=f"obj-proof-{uuid4().hex[:8]}",
            item_id=item_id,
            tool=result.kind,
            evidence_label=str(action.get("objective_readiness_evidence_label") or ""),
            strategy=str(action.get("objective_readiness_proof_strategy") or ""),
            outcome=outcome,  # type: ignore[arg-type]
            ok=result.ok,
            summary=result.summary[:500],
            proof_action=str(action.get("objective_readiness_proof_action") or action.get("thought_summary") or "")[:500],
            created_at=utc_now(),
        )
        state.objective_readiness_proof_outcomes.append(record)
        state.objective_readiness_proof_outcomes = state.objective_readiness_proof_outcomes[-40:]
        self._append_unique(
            state.facts_learned,
            f"Objective readiness proof {item_id} via {result.kind}: {record.outcome}.",
        )
        return record

    def _objective_readiness_proof_result(
        self,
        run: RunRecord,
        state: RunState,
        item_id: str,
        result: ToolResult,
    ) -> str:
        if result.needs_approval:
            return "waiting_approval"
        if not result.ok:
            return "failed"
        if self._objective_readiness_item_is_verified(run, state, item_id):
            return "verified"
        return "partial"

    def _objective_readiness_item_is_verified(self, run: RunRecord, state: RunState, item_id: str) -> bool:
        if item_id == "isolated_workspaces":
            isolation = state.workspace_isolation
            return bool(isolation.enabled and isolation.workspace_path and isolation.workspace_path != isolation.source_path)
        if item_id == "patch_first_editing":
            direct_source_writes = [call for call in state.tool_calls if call.name == "file_write" and call.ok]
            return bool((state.patch_proposals or state.patch_applications) and not direct_source_writes)
        if item_id == "durable_task_graph":
            return bool(state.task_graph and state.current_task_id)
        if item_id == "compact_context":
            return bool(state.context_snapshot.generated_at and state.context_budget.pressure != "high")
        if item_id == "repo_map":
            return bool(state.repo_map.generated_at and state.repo_map.summary)
        if item_id == "verification_critic_loop":
            return bool(
                state.verification_outcomes.outcome_count
                or any(item.status == "verified" for item in state.acceptance_evidence)
            )
        if item_id == "failure_recovery":
            return bool(state.failure_records or state.recovery_decisions.decision_count)
        if item_id == "replay_audit_trails":
            return bool(state.report_integrity.status == "ok" and state.autonomy_decisions.decision_count)
        if item_id == "obsidian_handoffs":
            checkpoint_recorded = any(call.name == "obsidian_checkpoint" and call.ok for call in state.tool_calls)
            return bool(state.handoff_summary.resume_prompt and state.memory_refs and checkpoint_recorded)
        if item_id == "goal_evolution":
            return bool(
                state.goal_evolution.decision_count
                or state.proposed_goal
                or any(item.kind == "goal" for item in state.model_interactions)
            )
        return False

    def _resolve_recommendation_trace(
        self,
        state: RunState,
        action: dict[str, Any],
        result: ToolResult,
    ) -> None:
        trace_id = str(action.get("recommendation_trace_id") or "")
        if not trace_id:
            return
        trace = next((item for item in state.acceptance_recommendation_traces if item.id == trace_id), None)
        if not trace:
            return
        trace.result_ok = result.ok
        trace.result_summary = result.summary[:500]
        trace.resolved_at = utc_now()
        evidence = next(
            (
                item
                for item in state.acceptance_evidence
                if item.id == trace.criterion_id or item.criterion == trace.criterion
            ),
            None,
        )
        if evidence:
            trace.evidence_status = evidence.status
        if result.needs_approval:
            trace.status = "waiting_approval"
            trace.notes = "Tool action needs approval before recommendation can be resolved."
            return
        if not result.ok:
            trace.status = "failed"
            trace.notes = "Recommended tool action failed."
            return
        if evidence and trace.label in set(evidence.matched_labels):
            trace.status = "satisfied"
            trace.notes = "Recommended action satisfied the intended evidence label."
            return
        trace.status = "executed"
        trace.notes = "Recommended action executed, but the intended evidence label is still open."

    async def _maybe_propose_goal_update(self, run: RunRecord, state: RunState, *, force: bool = False) -> dict[str, str] | None:
        if not force and (state.step_count == 0 or state.step_count % max(1, state.checkpoint_every_steps) != 0):
            return None
        review_reason = (
            "A dashboard /goal review was explicitly requested."
            if force
            else "This is the scheduled long-run goal review."
        )
        prompt = (
            "Review whether the active goal should be rewritten for a long-running local agent. "
            "Return strict JSON: {\"should_update\": boolean, \"proposed_goal\": string, \"reason\": string}. "
            "Only update if scope, acceptance criteria, blockers, or next action materially changed.\n\n"
            f"{review_reason}\n"
            f"Original goal: {run.goal}\nActive goal: {state.goal}\n"
            f"Handoff: {state.handoff_summary.model_dump_json()[: self.model_profile.goal_context_chars]}"
        )
        try:
            payload, metadata = await self._chat_json_with_metrics(
                prompt,
                max_tokens=500,
                schema_hint='{"should_update":false,"proposed_goal":"","reason":""}',
            )
            self._add_model_interaction(
                state,
                kind="goal",
                ok=True,
                summary="Model goal-review JSON parsed.",
                attempts=int(metadata.get("attempts") or 0),
                repaired=bool(metadata.get("repaired")),
                raw_excerpt=str(metadata.get("raw_excerpt") or ""),
                output_keys=sorted(str(key) for key in payload.keys()),
            )
            if payload.get("should_update") and str(payload.get("proposed_goal", "")).strip():
                proposed = str(payload["proposed_goal"]).strip()
                if proposed != state.goal:
                    return {"proposed_goal": proposed, "reason": str(payload.get("reason") or "Goal update proposed by model.")}
            record_goal_unchanged(
                state,
                run,
                reason=str(payload.get("reason") or "Goal review kept the active goal unchanged."),
                source="manual_review" if force else "scheduled_review",
            )
        except (ModelError, ValueError) as exc:
            self._add_model_interaction(
                state,
                kind="goal",
                ok=False,
                summary="Model goal review failed; keeping current goal.",
                fallback_used=True,
                error=str(exc),
            )
            return None
        return None

    def _detect_drift(self, run: RunRecord, state: RunState) -> str:
        next_step = (state.next_step or "").lower()
        framework_decision_steps = (
            "decide whether to continue, replan, or finish",
            "continue with the next safe action",
            "write compact checkpoint and handoff",
        )
        if any(step in next_step for step in framework_decision_steps):
            return ""
        goal_words = {word for word in re_words(state.goal) if len(word) > 4}
        if state.context_budget.pressure == "high":
            return "Context budget pressure is high; compact and re-orient before continuing."
        if state.failure_counts and max(state.failure_counts.values()) >= 3:
            return "A tool failed repeatedly; pause or replan instead of looping."
        if goal_words and next_step and not any(word in next_step for word in list(goal_words)[:12]):
            if state.step_count > 1:
                return "Next action appears weakly connected to the active goal."
        return ""

    def _should_finish(self, state: RunState) -> bool:
        if not state.acceptance_criteria:
            return state.step_count >= min(self.config.max_loop_steps, 4)
        self._ensure_acceptance_evidence(state)
        return bool(state.acceptance_evidence) and all(
            item.status == "verified" for item in state.acceptance_evidence
        )

    def _completion_audit(self, run: RunRecord, state: RunState) -> Any:
        return self._build_completion_audit(run, state)

    def _build_completion_audit(self, run: RunRecord, state: RunState) -> Any:
        self._build_verification_outcome_report(run, state)
        audit_run = run.model_copy(update={"state": state})
        return build_completion_audit(
            audit_run,
            self.store.list_approvals(run.id),
            strict_stale_evidence=self.config.completion_strict_stale_evidence,
            stale_edit_tools=set(self.config.completion_stale_edit_tools),
        )

    def _build_run_health(self, run: RunRecord, state: RunState) -> RunHealthReport:
        self._build_verification_outcome_report(run, state)
        self._build_objective_readiness(run, state)
        health_run = run.model_copy(update={"state": state})
        health = build_run_health(
            health_run,
            self.store.list_approvals(run.id),
            self._build_completion_audit(run, state),
            lease_live=self._lease_is_live(state.run_lease),
        )
        health = self._augment_run_health_with_readiness_smoke(run, state, health)
        health = self._augment_run_health_with_dispatch_restart_smoke(run, state, health)
        state.run_health = health
        return health

    def _build_policy_simulation(self, run: RunRecord, state: RunState) -> Any:
        completion_audit = self._build_completion_audit(run, state)
        run_health = self._build_run_health(run, state)
        simulation_run = run.model_copy(update={"state": state})
        return build_policy_simulation(simulation_run, completion_audit, run_health)

    def _build_run_progress(self, run: RunRecord, state: RunState, policy_simulation: Any | None = None) -> Any:
        progress_run = run.model_copy(update={"state": state})
        completion_audit = self._build_completion_audit(run, state)
        policy = policy_simulation or self._build_policy_simulation(run, state)
        report = build_run_progress(
            progress_run,
            self.store.list_approvals(run.id),
            completion_audit,
            policy,
        )
        state.run_progress = report
        return report

    def _build_report_integrity(self, run: RunRecord, state: RunState, handoff: HandoffBundle | None = None) -> Any:
        integrity_run = run.model_copy(update={"state": state})
        report = build_report_integrity(
            integrity_run,
            self.store.list_events(run.id, limit=300),
            handoff=handoff,
        )
        state.report_integrity = report
        return report

    def _build_objective_readiness(self, run: RunRecord, state: RunState) -> Any:
        readiness_run = run.model_copy(update={"state": state})
        report = build_objective_readiness(readiness_run, tool_names=set(TOOL_NAMES))
        state.objective_readiness = report
        return report

    def _build_readiness_completion(
        self,
        run: RunRecord,
        state: RunState,
        objective_readiness: Any | None = None,
        run_progress: Any | None = None,
        completion_audit: Any | None = None,
    ) -> Any:
        completion = completion_audit or self._build_completion_audit(run, state)
        progress = run_progress or self._build_run_progress(run, state)
        readiness = objective_readiness or self._build_objective_readiness(run, state)
        require_smoke_proofs = not self._is_readiness_rehearsal_run(
            run,
            state,
        ) and not self._is_operator_dispatch_restart_smoke_run(run, state)
        rehearsal_ledger = (
            ReadinessRehearsalLedgerReport.model_validate(self.get_readiness_rehearsal_ledger(limit=10))
            if require_smoke_proofs
            else None
        )
        dispatch_restart_smoke_ledger = (
            OperatorDispatchRestartSmokeLedgerReport.model_validate(
                self.get_operator_dispatch_restart_smoke_ledger(limit=10)
            )
            if require_smoke_proofs
            else None
        )
        report_run = run.model_copy(update={"state": state})
        report = build_readiness_completion(
            report_run,
            readiness,
            progress,
            completion,
            rehearsal_ledger,
            dispatch_restart_smoke_ledger,
            require_rehearsal_ledger=require_smoke_proofs,
            require_dispatch_restart_smoke_ledger=require_smoke_proofs,
        )
        state.readiness_completion = report
        return report

    def _build_resume_decision_report(self, run: RunRecord, state: RunState) -> Any:
        decision_run = run.model_copy(update={"state": state})
        policy_simulation = self._build_policy_simulation(run, state)
        return build_resume_decision_report(
            decision_run,
            self.store.list_events(run.id, limit=300),
            policy_simulation,
        )

    def _build_action_readiness(self, run: RunRecord, state: RunState, resume_decisions: Any | None = None) -> Any:
        source_run = run.model_copy(update={"state": state})
        state.source_evidence = SourceEvidencePreviewReport.model_validate(
            build_source_evidence_preview(source_run, limit=20)
        )
        readiness_run = run.model_copy(update={"state": state})
        resume_report = resume_decisions or self._build_resume_decision_report(run, state)
        readiness = build_action_readiness(readiness_run, resume_report)
        state.action_readiness = readiness
        return readiness

    def _build_action_readiness_decision_report(self, run: RunRecord, state: RunState) -> Any:
        decision_run = run.model_copy(update={"state": state})
        report = build_action_readiness_decision_report(
            decision_run,
            self.store.list_events(run.id, limit=300),
        )
        state.action_readiness_decisions = report
        return report

    def _build_autonomy_decision_report(self, run: RunRecord, state: RunState, policy_simulation: Any | None = None) -> Any:
        autonomy_run = run.model_copy(update={"state": state})
        policy = policy_simulation or self._build_policy_simulation(run, state)
        report = build_autonomy_decision_report(
            autonomy_run,
            self.store.list_events(run.id, limit=300),
            policy,
        )
        state.autonomy_decisions = report
        return report

    def _build_recovery_decision_report(self, run: RunRecord, state: RunState) -> Any:
        recovery_run = run.model_copy(update={"state": state})
        readiness_decisions = self._build_action_readiness_decision_report(run, state)
        report = build_recovery_decision_report(recovery_run, readiness_decisions)
        state.recovery_decisions = report
        return report

    def _build_verification_outcome_report(self, run: RunRecord, state: RunState) -> Any:
        outcome_run = run.model_copy(update={"state": state})
        recovery_decisions = self._build_recovery_decision_report(run, state)
        report = build_verification_outcome_report(
            outcome_run,
            self.store.list_events(run.id, limit=300),
            recovery_decisions,
        )
        state.verification_outcomes = report
        return report

    def _ensure_acceptance_evidence(self, state: RunState) -> None:
        existing = {item.criterion: item for item in state.acceptance_evidence}
        evidence: list[AcceptanceCriterionEvidence] = []
        for index, criterion in enumerate(state.acceptance_criteria):
            item = existing.get(criterion)
            if not item:
                item = AcceptanceCriterionEvidence(
                    id=f"criterion-{index + 1}",
                    criterion=criterion,
                    required_labels=infer_required_labels(criterion),
                    notes="Awaiting verification evidence.",
                )
            self._normalize_acceptance_labels(item)
            evidence.append(item)
        state.acceptance_evidence = evidence
        self._refresh_acceptance_recommendations(state)

    def _update_acceptance_evidence(self, state: RunState, result: ToolResult) -> None:
        if not state.acceptance_criteria:
            return
        self._ensure_acceptance_evidence(state)
        evidence_text = self._acceptance_evidence_text(result)
        result_labels = self._result_evidence_labels(result.kind)
        for item in state.acceptance_evidence:
            required_labels = item.required_labels
            supported_labels = [
                label
                for label in required_labels
                if label in result_labels and self._result_label_is_relevant_to_item(state, item, label, result)
            ]
            fallback_supported = not required_labels and self._result_supports_criterion(
                item.criterion,
                result,
                evidence_text,
                result_labels,
            )
            if not supported_labels and not fallback_supported:
                continue
            self._record_acceptance_item_evidence(
                item,
                result.kind,
                result.summary,
                ok=result.ok,
                labels=supported_labels or sorted(result_labels),
                can_fail=result.kind in set(self.config.completion_verification_tools),
            )
        self._refresh_acceptance_recommendations(state)

    def _result_label_is_relevant_to_item(
        self,
        state: RunState,
        item: AcceptanceCriterionEvidence,
        label: str,
        result: ToolResult,
    ) -> bool:
        if label != "browser" or result.kind != "browser_screenshot":
            return True
        criterion = item.criterion.lower()
        url = str(result.data.get("url") or "").lower() if isinstance(result.data, dict) else ""
        if self._is_dashboard_browser_url(url) and "dashboard" not in criterion:
            return False
        if "dashboard" in criterion:
            return True
        return self._has_workspace_material_for_browser_proof(state)

    def _is_dashboard_browser_url(self, url: str) -> bool:
        return "127.0.0.1:5173" in url or "localhost:5173" in url

    def _has_workspace_material_for_browser_proof(self, state: RunState) -> bool:
        if state.files_touched or state.patch_proposals or state.patch_applications:
            return True
        if getattr(state.workspace_diff, "total_files", 0):
            return True
        edit_tools = {"file_write", "patch_apply", "patch_propose", "workspace_promote"}
        if any(call.ok and call.name in edit_tools for call in state.tool_calls):
            return True
        workspace = Path(state.workspace_isolation.workspace_path or "")
        if not workspace.exists():
            return False
        ignored_parts = {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}
        ignored_suffixes = {".db", ".sqlite", ".sqlite3", ".pyc", ".log"}
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            if ignored_parts.intersection(path.parts):
                continue
            if path.suffix.lower() in ignored_suffixes:
                continue
            return True
        return False

    def _record_acceptance_checkpoint(self, state: RunState) -> None:
        if not state.acceptance_criteria:
            return
        if "checkpoint" not in set(self.config.completion_checkpoint_tools):
            return
        self._ensure_acceptance_evidence(state)
        for item in state.acceptance_evidence:
            self._normalize_acceptance_labels(item)
            if item.required_labels:
                if "checkpoint" not in item.required_labels:
                    continue
            else:
                continue
            self._record_acceptance_item_evidence(
                item,
                "checkpoint",
                "Wrote compact checkpoint and refreshed handoff.",
                ok=True,
                labels=["checkpoint"],
                can_fail=False,
            )
        self._refresh_acceptance_recommendations(state)

    def _acceptance_evidence_text(self, result: ToolResult) -> str:
        parts = [result.kind, result.summary]
        command = result.data.get("command") if isinstance(result.data, dict) else None
        if command:
            parts.append(str(command))
        path = result.data.get("path") if isinstance(result.data, dict) else None
        if path:
            parts.append(str(path))
        files = result.data.get("files") if isinstance(result.data, dict) else None
        if isinstance(files, list):
            parts.extend(str(item) for item in files[:8])
        return " ".join(parts).lower()

    def _result_evidence_labels(self, tool_kind: str) -> set[str]:
        labels: set[str] = set()
        if tool_kind in set(self.config.completion_verification_tools):
            labels.add("verification")
        if tool_kind in set(self.config.completion_checkpoint_tools):
            labels.add("checkpoint")
        if tool_kind in set(self.config.completion_browser_tools):
            labels.add("browser")
        if tool_kind in set(self.config.completion_edit_tools):
            labels.add("edit")
        if tool_kind in set(self.config.completion_web_tools):
            labels.add("web")
        return labels

    def _result_supports_criterion(
        self,
        criterion: str,
        result: Any,
        evidence_text: str,
        result_labels: set[str] | None = None,
    ) -> bool:
        required_labels = infer_required_labels(criterion)
        labels = result_labels if result_labels is not None else self._result_evidence_labels(result.kind)
        if required_labels:
            return bool(set(required_labels).intersection(labels))
        if not set(re_words(criterion)):
            return False
        significant = [word for word in re_words(criterion) if len(word) > 3][:4]
        return bool(significant) and all(word in evidence_text for word in significant[:3])

    def _normalize_acceptance_labels(self, item: AcceptanceCriterionEvidence) -> None:
        required = item.required_labels or infer_required_labels(item.criterion)
        required = list(dict.fromkeys(required))
        item.required_labels = required
        if required:
            item.matched_labels = [
                label
                for label in required
                if label in set(item.matched_labels)
            ]
            item.label_checked_at = {
                label: item.label_checked_at[label]
                for label in required
                if label in item.label_checked_at
            }
        else:
            item.matched_labels = []
            item.label_checked_at = {}

    def _record_acceptance_item_evidence(
        self,
        item: AcceptanceCriterionEvidence,
        tool_kind: str,
        summary: str,
        *,
        ok: bool,
        labels: list[str],
        can_fail: bool,
    ) -> None:
        now = utc_now()
        self._normalize_acceptance_labels(item)
        labels = list(dict.fromkeys(label for label in labels if not item.required_labels or label in item.required_labels))
        label_suffix = f" [{','.join(labels)}]" if labels else ""
        entry = f"{tool_kind}{label_suffix}: {summary}"
        if entry not in item.evidence:
            item.evidence.append(entry)
        item.evidence = item.evidence[-8:]
        if ok:
            if item.required_labels:
                matched = set(item.matched_labels)
                for label in labels:
                    matched.add(label)
                    item.label_checked_at[label] = now
                item.matched_labels = [label for label in item.required_labels if label in matched]
                missing = [label for label in item.required_labels if label not in matched]
                progress = compact_label_progress(item.required_labels, item.matched_labels)
                if missing:
                    item.status = "open"
                    item.notes = f"Partial evidence labels: {progress}."
                else:
                    item.status = "verified"
                    item.notes = f"Verified evidence labels: {progress}."
            else:
                item.status = "verified"
                item.notes = "Verified by direct evidence text match."
        elif can_fail:
            item.status = "failed"
            item.notes = "Verification evidence failed."
        else:
            item.status = "open"
            if labels:
                item.notes = f"Evidence labels attempted but not verified: {','.join(labels)}."
        item.last_tool = tool_kind
        item.last_checked = now

    def _refresh_acceptance_recommendations(self, state: RunState) -> None:
        recommendations: list[AcceptanceEvidenceRecommendation] = []
        for item in state.acceptance_evidence:
            if item.status == "verified":
                continue
            missing = [
                label
                for label in item.required_labels
                if label not in set(item.matched_labels)
            ]
            if not missing and not item.required_labels:
                missing = ["verification"]
            for label in missing[:4]:
                recommendations.append(self._recommendation_for_label(item, label, state))
        state.acceptance_recommendations = recommendations[:12]

    def _recommendation_for_label(
        self,
        item: AcceptanceCriterionEvidence,
        label: str,
        state: RunState,
    ) -> AcceptanceEvidenceRecommendation:
        artifact_command = artifact_verification_command(
            RunRecord(id="recommendation", title="", goal=state.goal, status="queued", workspace_path="", state=state, created_at="", updated_at=""),
            state,
            item.criterion,
        )
        test_command = artifact_command or (state.repo_map.test_commands[0] if state.repo_map.test_commands else "python -m pytest")
        if label == "verification":
            return AcceptanceEvidenceRecommendation(
                id=f"{item.id}-verification",
                criterion_id=item.id,
                criterion=item.criterion,
                label=label,
                tool_kind="run_tests",
                action=f"Run the smallest relevant verification command: {test_command}",
                command_hint=test_command,
                reason=(
                    "Criterion still needs artifact existence/load proof."
                    if artifact_command
                    else "Criterion still needs test/build/lint proof."
                ),
            )
        if label == "checkpoint":
            return AcceptanceEvidenceRecommendation(
                id=f"{item.id}-checkpoint",
                criterion_id=item.id,
                criterion=item.criterion,
                label=label,
                tool_kind="obsidian_checkpoint",
                action="Write a compact checkpoint and refresh the handoff bundle.",
                reason="Criterion still needs durable memory/handoff proof.",
            )
        if label == "browser":
            if state.browser_enabled:
                command_hint = (
                    "url=http://127.0.0.1:5173"
                    if self._criterion_allows_dashboard_proof(item.criterion)
                    else self._local_index_url(state)
                )
                return AcceptanceEvidenceRecommendation(
                    id=f"{item.id}-browser",
                    criterion_id=item.id,
                    criterion=item.criterion,
                    label=label,
                    tool_kind="browser_screenshot",
                    action="Capture a browser screenshot of the relevant local app page.",
                    command_hint=command_hint,
                    reason="Criterion still needs visible browser proof.",
                )
            if state.desktop_enabled:
                return AcceptanceEvidenceRecommendation(
                    id=f"{item.id}-browser",
                    criterion_id=item.id,
                    criterion=item.criterion,
                    label=label,
                    tool_kind="desktop_screenshot",
                    action="Capture a supervised desktop screenshot of the relevant UI.",
                    reason="Browser tools are disabled, but desktop inspection is available.",
                )
            return AcceptanceEvidenceRecommendation(
                id=f"{item.id}-browser",
                criterion_id=item.id,
                criterion=item.criterion,
                label=label,
                tool_kind="ask_user",
                action="Ask to enable browser or desktop tools, or revise the browser-facing criterion.",
                reason="No browser or desktop inspection tool is enabled for this run.",
                available=False,
            )
        if label == "web":
            if state.web_enabled:
                return AcceptanceEvidenceRecommendation(
                    id=f"{item.id}-web",
                    criterion_id=item.id,
                    criterion=item.criterion,
                    label=label,
                    tool_kind="web_search",
                    action="Search or fetch a cited source and store the citation with the result.",
                    command_hint=item.criterion,
                    reason="Criterion still needs web/source evidence.",
                )
            return AcceptanceEvidenceRecommendation(
                id=f"{item.id}-web",
                criterion_id=item.id,
                criterion=item.criterion,
                label=label,
                tool_kind="ask_user",
                action="Ask to enable web tools or provide an offline source.",
                reason="Web tools are disabled for this run.",
                available=False,
            )
        if label == "edit":
            return AcceptanceEvidenceRecommendation(
                id=f"{item.id}-edit",
                criterion_id=item.id,
                criterion=item.criterion,
                label=label,
                tool_kind="patch_propose",
                action="Propose a focused patch tied to this criterion before applying edits.",
                reason="Criterion still needs implementation or patch evidence.",
            )
        return AcceptanceEvidenceRecommendation(
            id=f"{item.id}-{label}",
            criterion_id=item.id,
            criterion=item.criterion,
            label=label,
            tool_kind="ask_user",
            action=f"Ask how to prove the missing evidence label: {label}.",
            reason="No built-in tool recommendation exists for this label.",
            available=False,
        )

    def _criterion_allows_dashboard_proof(self, criterion: str) -> bool:
        return "dashboard" in criterion.lower()

    def _local_index_url(self, state: RunState) -> str:
        workspace = Path(state.workspace_isolation.workspace_path or "")
        index_path = workspace / "index.html"
        if not index_path.exists():
            return ""
        return f"url={index_path.resolve().as_uri()}"

    async def run_operator_dispatch_restart_smoke(self) -> OperatorDispatchRestartSmokeReport:
        run: RunRecord | None = None
        steps: list[ReadinessRehearsalStep] = []
        active_engine: AgentLoopEngine = self
        try:
            run = self.store.create_run(
                "Exercise operator dispatch restart handoff for Ornith long runs",
                "Operator dispatch restart smoke",
                str(self.config.workspace_path),
                ["Operator dispatch ledger survives restart"],
                tool_profile="ornith_operator_smoke",
                web_enabled=False,
                browser_enabled=False,
                desktop_enabled=False,
                wall_clock_limit_minutes=10,
                checkpoint_every_steps=max(2, self.config.checkpoint_every_steps),
                context_target_tokens=self.context_compiler.target_tokens,
            )
            self.memory.append_run_started(run)
            state = run.state
            state.proposed_goal = "Operator dispatch restart smoke completed with preserved supervision ledger."
            state.goal_revision_reason = "Smoke queues a goal-update approval so operator dispatch can be exercised safely."
            state.next_step = "Wait for operator dispatch smoke approval."
            state.operator_dispatch_restart_smoke = OperatorDispatchRestartSmokeReport(
                run_id=run.id,
                generated_at=utc_now(),
                status="running",
                summary="Operator dispatch restart smoke is running.",
                next_action="Dispatch the queued approval and recreate the engine over durable state.",
            )
            self.store.create_approval(
                run.id,
                "goal_update",
                {"proposed_goal": state.proposed_goal, "reason": state.goal_revision_reason},
                "Confirm operator dispatch restart smoke goal update.",
            )
            state.handoff_summary = self._make_handoff(run, state)
            run = self.store.update_run(run.id, status="waiting_goal_confirmation", state=state)
            await self._event(
                run.id,
                "operator_dispatch_restart_smoke_started",
                state.operator_dispatch_restart_smoke.summary,
                {"operator_dispatch_restart_smoke": state.operator_dispatch_restart_smoke.model_dump()},
            )

            await self.recover_stale_runs()
            queue = OperatorActionQueueReport.model_validate(self.get_operator_action_queue(limit=50))
            item = next((entry for entry in queue.items if entry.run_id == run.id and entry.reason == "approval"), None)
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    run,
                    "queued_operator_action",
                    item is not None and item.approval_id > 0,
                    "Supervisor queue exposes the pending approval as an operator action.",
                    [f"queue_items={queue.total_count}", f"approval_id={item.approval_id if item else 0}"],
                ),
            )

            result = await self.dispatch_operator_action(
                OperatorActionDispatchRequest(
                    item_id=item.id if item else "missing",
                    decision="reject",
                    confirmed=True,
                )
            )
            dispatched = self._latest_event(run.id, "operator_action_dispatched")
            ledger = OperatorDispatchLedgerReport.model_validate(self.get_operator_dispatches(run.id, limit=10))
            dispatched_ok = result.status == "dispatched" and ledger.dispatched_count >= 1 and bool(dispatched)
            run = self.store.get_run(run.id)
            self._append_rehearsal_step(
                steps,
                self._rehearsal_step(
                    run,
                    "dispatch_logged",
                    dispatched_ok,
                    "Confirmed operator dispatch is logged in the durable dispatch ledger.",
                    [
                        f"result={result.status}",
                        f"dispatched={ledger.dispatched_count}",
                        f"event={dispatched.get('id') or 0}",
                    ],
                    event=dispatched,
                ),
            )

            restart_engine = AgentLoopEngine(
                self.config,
                RunStore(self.config.sqlite_path),
                ObsidianMemory(self.config.obsidian_vault_path),
                self.model,
                EventBroker(),
            )
            active_engine = restart_engine
            await restart_engine.recover_stale_runs()
            restarted = restart_engine.store.get_run(run.id)
            restart_ledger = OperatorDispatchLedgerReport.model_validate(
                restart_engine.get_operator_dispatches(restarted.id, limit=10)
            )
            self._append_rehearsal_step(
                steps,
                restart_engine._rehearsal_step(
                    restarted,
                    "restart_loaded_ledger",
                    restart_ledger.dispatched_count >= 1,
                    "A recreated engine loads the operator dispatch ledger from SQLite events.",
                    [f"dispatched={restart_ledger.dispatched_count}", f"events={restart_ledger.total_count}"],
                ),
            )

            state = restarted.state
            state.operator_dispatches = restart_ledger
            handoff = restart_engine._make_handoff(restarted, state)
            state.handoff_summary = handoff
            restarted = restart_engine.store.update_run(restarted.id, state=state)
            handoff_ok = handoff.operator_dispatches.dispatched_count >= 1
            self._append_rehearsal_step(
                steps,
                restart_engine._rehearsal_step(
                    restarted,
                    "handoff_attached_ledger",
                    handoff_ok,
                    "Restart-generated handoff includes the compact operator dispatch ledger.",
                    [handoff.operator_dispatches.summary],
                ),
            )

            events = restart_engine.store.list_events(restarted.id, limit=500)
            replay = build_replay_bundle(
                restarted,
                events=events,
                approvals=restart_engine.store.list_approvals(restarted.id),
                model_adaptation_reviews=restart_engine.store.list_model_adaptation_reviews(limit=10),
                strict_stale_evidence=self.config.completion_strict_stale_evidence,
                stale_edit_tools=set(self.config.completion_stale_edit_tools),
            )
            replay_ok = replay.operator_dispatches.dispatched_count >= 1 and "## Operator Dispatches" in replay.markdown
            self._append_rehearsal_step(
                steps,
                restart_engine._rehearsal_step(
                    restarted,
                    "replay_attached_ledger",
                    replay_ok,
                    "Replay JSON and markdown include the compact operator dispatch ledger.",
                    [
                        f"dispatched={replay.operator_dispatches.dispatched_count}",
                        f"markdown={'Operator Dispatches' in replay.markdown}",
                    ],
                ),
            )

            memory_context = restart_engine.memory.consult(restarted.state.goal, run_id=restarted.id)
            prompt, snapshot = restart_engine.context_compiler.compile(restarted, restarted.state, memory_context, events[-10:])
            context_ok = "operator_dispatches" in snapshot.sections and "Operator dispatches:" in prompt
            self._append_rehearsal_step(
                steps,
                restart_engine._rehearsal_step(
                    restarted,
                    "context_attached_ledger",
                    context_ok,
                    "Compact context includes the operator dispatch summary after restart.",
                    [
                        f"tokens={snapshot.estimated_tokens}/{restart_engine.context_compiler.target_tokens}",
                        "sections=" + ",".join(snapshot.sections),
                    ],
                ),
            )

            passed = all(step.status == "passed" for step in steps)
            report = OperatorDispatchRestartSmokeReport(
                run_id=restarted.id,
                generated_at=utc_now(),
                status="passed" if passed else "failed",
                summary=(
                    "Operator dispatch restart smoke passed: dispatch ledger survived restart into handoff, replay, and compact context."
                    if passed
                    else "Operator dispatch restart smoke failed: inspect the failed step before trusting restart handoff evidence."
                ),
                restart_simulated=True,
                dispatch_event_id=int(dispatched.get("id") or 0),
                compact_context_tokens=snapshot.estimated_tokens,
                compact_context_sections=snapshot.sections,
                ledger_attached=restart_ledger.dispatched_count >= 1,
                handoff_attached=handoff_ok,
                replay_attached=replay_ok,
                context_attached=context_ok,
                next_action=(
                    "Use the dispatch ledger as compact supervision evidence after restart and compaction."
                    if passed
                    else "Inspect the failed smoke step before relying on the operator dispatch ledger after restart."
                ),
                steps=steps,
            )
            await restart_engine._event(
                restarted.id,
                "operator_dispatch_restart_smoke",
                report.summary,
                {"operator_dispatch_restart_smoke": report.model_dump()},
            )
            stored_report = restart_engine._store_operator_dispatch_restart_smoke_report(restarted.id, report)
            await self.recover_stale_runs()
            return stored_report
        except Exception as exc:
            active = active_engine
            failed_run = active.store.get_run(run.id) if run else active.store.create_run(
                "Operator dispatch restart smoke failed before run creation",
                "Operator dispatch restart smoke failed",
                str(active.config.workspace_path),
                [],
            )
            if not steps or steps[-1].status != "failed":
                steps.append(
                    active._rehearsal_step(
                        failed_run,
                        "operator_dispatch_restart_smoke_error",
                        False,
                        f"Operator dispatch restart smoke failed: {exc}",
                        [type(exc).__name__],
                    )
                )
            report = OperatorDispatchRestartSmokeReport(
                run_id=failed_run.id,
                generated_at=utc_now(),
                status="failed",
                summary=f"Operator dispatch restart smoke failed: {exc}",
                next_action="Inspect the failed smoke step before trusting operator dispatch resume evidence.",
                steps=steps,
            )
            await active._event(
                failed_run.id,
                "operator_dispatch_restart_smoke",
                report.summary,
                {"operator_dispatch_restart_smoke": report.model_dump()},
            )
            stored_report = active._store_operator_dispatch_restart_smoke_report(failed_run.id, report)
            if active is not self:
                await self.recover_stale_runs()
            return stored_report

    def _create_readiness_rehearsal_run(self) -> RunRecord:
        run_id = make_run_id()
        workspace = self._prepare_readiness_rehearsal_workspace(run_id)
        now = utc_now()
        goal = "Improve Orinth into a Codex-like long-running local coding harness"
        isolation = WorkspaceIsolation(
            enabled=True,
            mode="copy",
            source_path=str(self.config.workspace_path),
            workspace_path=str(workspace),
            created_at=now,
            copied_files=1,
            summary="Readiness rehearsal workspace is isolated from the source workspace.",
        )
        run = self.store.create_run(
            goal,
            "Readiness claim smoke rehearsal",
            str(workspace),
            ["Harness readiness"],
            tool_profile="ornith_rehearsal",
            web_enabled=False,
            browser_enabled=False,
            desktop_enabled=False,
            wall_clock_limit_minutes=10,
            checkpoint_every_steps=max(2, self.config.checkpoint_every_steps),
            context_target_tokens=self.context_compiler.target_tokens,
            run_id=run_id,
            workspace_isolation=isolation,
        )
        self.memory.append_run_started(run)
        state = run.state
        state.milestone = "decide"
        state.next_step = "Decide whether the harness can claim readiness."
        state.acceptance_evidence = [
            AcceptanceCriterionEvidence(
                id="criterion-1",
                criterion="Harness readiness",
                status="verified",
                evidence=["Readiness rehearsal seeded a verified acceptance criterion."],
                last_tool="run_tests",
                last_checked=now,
            )
        ]
        state.objective_readiness_proof_outcomes = self._readiness_rehearsal_seed_outcomes(now)
        state.readiness_rehearsal = ReadinessRehearsalReport(
            run_id=run.id,
            generated_at=now,
            status="running",
            summary="Readiness claim smoke rehearsal is running.",
            rehearsal_workspace=str(workspace),
            next_action="Drive refused claim, proof, checkpoint, restart resume, and accepted claim.",
        )
        state.handoff_summary = self._make_handoff(run, state)
        return self.store.update_run(run.id, status="queued", state=state)

    def _prepare_readiness_rehearsal_workspace(self, run_id: str) -> Path:
        workspace = (self.config.workspace_root / "rehearsals" / run_id).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text(
            "# AgentOrinth Readiness Rehearsal\n\n"
            "This isolated workspace is created by the readiness-claim smoke route.\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "init", "-q"],
            cwd=workspace,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return workspace

    def _readiness_rehearsal_seed_outcomes(self, created_at: str) -> list[ObjectiveReadinessProofOutcome]:
        return [
            ObjectiveReadinessProofOutcome(
                id=f"obj-proof-{item_id}",
                item_id=item_id,
                tool="run_tests",
                evidence_label="objective",
                strategy="rehearsal_seed",
                outcome="verified",
                ok=True,
                summary=f"{item_id} verified by readiness smoke rehearsal seed.",
                proof_action="Seed all but the handoff and goal-evolution items so the first claim is refused.",
                created_at=created_at,
            )
            for item_id in READINESS_REHEARSAL_OBJECTIVE_ITEMS
            if item_id not in {"obsidian_handoffs", "goal_evolution"}
        ]

    def _append_rehearsal_step(
        self,
        steps: list[ReadinessRehearsalStep],
        step: ReadinessRehearsalStep,
    ) -> None:
        steps.append(step)
        if step.status == "failed":
            raise RuntimeError(step.summary)

    def _rehearsal_step(
        self,
        run: RunRecord,
        step_id: str,
        passed: bool,
        summary: str,
        evidence: list[str] | None = None,
        *,
        event: dict[str, Any] | None = None,
    ) -> ReadinessRehearsalStep:
        event = event or {}
        return ReadinessRehearsalStep(
            id=step_id,
            status="passed" if passed else "failed",
            summary=summary,
            evidence=[item for item in (evidence or []) if item],
            event_id=int(event.get("id") or 0),
            event_kind=str(event.get("kind") or ""),
            run_status=run.status,
            milestone=run.state.milestone,
        )

    def _latest_event(self, run_id: str, kind: str) -> dict[str, Any]:
        return next(
            (event for event in reversed(self.store.list_events(run_id, limit=300)) if event.get("kind") == kind),
            {},
        )

    def _store_readiness_rehearsal_report(
        self,
        run_id: str,
        report: ReadinessRehearsalReport,
    ) -> ReadinessRehearsalReport:
        run = self.store.get_run(run_id)
        state = run.state
        state.readiness_rehearsal = report
        state.handoff_summary = self._make_handoff(run, state)
        state.handoff_summary.readiness_rehearsal = report
        self.store.update_run(run_id, state=state)
        return report

    def _store_operator_dispatch_restart_smoke_report(
        self,
        run_id: str,
        report: OperatorDispatchRestartSmokeReport,
    ) -> OperatorDispatchRestartSmokeReport:
        run = self.store.get_run(run_id)
        state = run.state
        state.operator_dispatch_restart_smoke = report
        state.handoff_summary = self._make_handoff(run, state)
        state.handoff_summary.operator_dispatch_restart_smoke = report
        self.store.update_run(run_id, state=state)
        return report

    def _is_readiness_rehearsal_run(self, run: RunRecord, state: RunState) -> bool:
        report = state.readiness_rehearsal
        return (
            state.tool_profile == "ornith_rehearsal"
            or report.run_id == run.id
            and report.status in {"running", "passed", "failed"}
        )

    def _is_operator_dispatch_restart_smoke_run(self, run: RunRecord, state: RunState) -> bool:
        report = state.operator_dispatch_restart_smoke
        return (
            state.tool_profile == "ornith_operator_smoke"
            or report.run_id == run.id
            and report.status in {"running", "passed", "failed"}
        )

    def _readiness_rehearsal_ledger_entry(
        self,
        report: ReadinessRehearsalReport,
        *,
        run_id: str,
    ) -> ReadinessRehearsalLedgerEntry:
        status = "running" if report.status not in {"passed", "failed"} else report.status
        return ReadinessRehearsalLedgerEntry(
            run_id=report.run_id or run_id,
            generated_at=report.generated_at,
            status=status,
            scenario=report.scenario,
            summary=report.summary,
            rehearsal_workspace=report.rehearsal_workspace,
            restart_simulated=report.restart_simulated,
            replay_attached=report.replay_attached,
            handoff_attached=report.handoff_attached,
            compact_context_tokens=report.compact_context_tokens,
            refused_event_id=report.refused_event_id,
            accepted_event_id=report.accepted_event_id,
            completed_event_id=report.completed_event_id,
            self_scaffold_reviewed=report.self_scaffold_reviewed,
            self_scaffold_review_event_id=report.self_scaffold_review_event_id,
            self_scaffold_reviewed_change_count=report.self_scaffold_reviewed_change_count,
            post_review_handoff_goal_preserved=report.post_review_handoff_goal_preserved,
            post_review_handoff_next_action_preserved=report.post_review_handoff_next_action_preserved,
            post_review_resume_prompt_goal_preserved=report.post_review_resume_prompt_goal_preserved,
            post_review_resume_prompt_next_action_preserved=report.post_review_resume_prompt_next_action_preserved,
            step_count=len(report.steps),
            passed_steps=sum(1 for step in report.steps if step.status == "passed"),
            failed_steps=sum(1 for step in report.steps if step.status == "failed"),
            next_action=report.next_action,
        )

    def _operator_dispatch_restart_smoke_ledger_entry(
        self,
        report: OperatorDispatchRestartSmokeReport,
        *,
        run_id: str,
    ) -> OperatorDispatchRestartSmokeLedgerEntry:
        status = "running" if report.status not in {"passed", "failed"} else report.status
        return OperatorDispatchRestartSmokeLedgerEntry(
            run_id=report.run_id or run_id,
            generated_at=report.generated_at,
            status=status,
            scenario=report.scenario,
            summary=report.summary,
            restart_simulated=report.restart_simulated,
            dispatch_event_id=report.dispatch_event_id,
            compact_context_tokens=report.compact_context_tokens,
            ledger_attached=report.ledger_attached,
            handoff_attached=report.handoff_attached,
            replay_attached=report.replay_attached,
            context_attached=report.context_attached,
            step_count=len(report.steps),
            passed_steps=sum(1 for step in report.steps if step.status == "passed"),
            failed_steps=sum(1 for step in report.steps if step.status == "failed"),
            next_action=report.next_action,
        )

    async def _save_state(self, run: RunRecord, state: RunState, kind: str, message: str) -> None:
        state.handoff_summary = self._make_handoff(run, state)
        self.store.update_run(run.id, state=state)
        await self._event(run.id, kind, message, {"state": state.model_dump()})
        await self._workstream(
            run.id,
            phase=kind if kind in MILESTONES else state.milestone,
            role="harness",
            title=self._workstream_title(kind),
            summary=message,
            next_action=state.next_step,
            severity="watch" if kind in {"drift", "health_policy", "health_verify"} else "normal",
            refs={"milestone": state.milestone, "state_saved": True},
        )

    async def _block(self, run_id: str, reason: str) -> None:
        run = self.store.get_run(run_id)
        state = run.state
        state.blockers.append(reason)
        state.next_step = "Ask user whether to continue."
        state.handoff_summary = self._make_handoff(run, state)
        run = self.store.update_run(run_id, status="blocked", state=state)
        self.memory.append_checkpoint(run, state, "blocked")
        await self._event(run_id, "blocked", reason)
        await self._workstream(
            run_id,
            phase="blocker",
            role="harness",
            title="Run Blocked",
            summary=reason,
            next_action=state.next_step,
            severity="blocked",
            refs={"status": "blocked"},
        )

    def _make_handoff(self, run: RunRecord, state: RunState) -> HandoffBundle:
        approvals = [
            f"{approval['action_kind']}:{approval['status']}"
            for approval in self.store.list_approvals(run.id)
            if approval["status"] == "pending"
        ]
        adaptation_reviews = [
            compact_adaptation_review(review)
            for review in self.store.list_model_adaptation_reviews(limit=5)
        ]
        self._ensure_acceptance_evidence(state)
        completion_audit = self._completion_audit(run, state)
        run_health = self._build_run_health(run, state)
        policy_simulation = self._build_policy_simulation(run, state)
        resume_decisions = self._build_resume_decision_report(run, state)
        autonomy_decisions = self._build_autonomy_decision_report(run, state, policy_simulation)
        run_progress = self._build_run_progress(run, state, policy_simulation)
        action_readiness = self._build_action_readiness(run, state, resume_decisions)
        action_readiness_decisions = self._build_action_readiness_decision_report(run, state)
        recovery_decisions = self._build_recovery_decision_report(run, state)
        verification_outcomes = self._build_verification_outcome_report(run, state)
        state.goal_evolution = build_goal_evolution_report(run.model_copy(update={"state": state}))
        state.post_action_retries = build_post_action_retry_report(run.model_copy(update={"state": state}))
        operator_dispatches = OperatorDispatchLedgerReport.model_validate(self.get_operator_dispatches(run.id, limit=12))
        state.operator_dispatches = operator_dispatches
        ornith_preflight_actions = OrnithPreflightActionLedgerReport.model_validate(
            self.get_ornith_preflight_actions(run.id, limit=12)
        )
        state.ornith_preflight_actions = ornith_preflight_actions
        source_run = run.model_copy(update={"state": state})
        source_evidence = SourceEvidencePreviewReport.model_validate(
            build_source_evidence_preview(source_run, limit=12)
        )
        state.source_evidence = source_evidence
        action_context = build_action_context_pack(source_run)
        state.action_context = action_context
        resume_prompt = (
            f"Resume AgentOrinth run {run.id}. Read Obsidian first, preserve original goal: {run.goal}. "
            f"Active goal: {state.goal}. Next action: {state.next_step}. "
            f"Do not reload raw logs; use this handoff and latest compact events."
        )
        handoff = HandoffBundle(
            original_goal=run.goal,
            current_objective=state.goal,
            goal_evolution=state.goal_evolution,
            plan=state.current_plan[-8:],
            completed_work=state.completed_steps[-12:],
            next_action=state.next_step,
            files_touched=state.files_touched[-20:],
            commands_and_tests=state.commands_run[-20:],
            web_sources=state.web_sources[-10:],
            desktop_state=state.desktop_snapshots[-5:],
            source_evidence=source_evidence,
            self_scaffold=state.self_scaffold,
            self_scaffold_reviews=state.self_scaffold_reviews,
            self_scaffold_rollback_intents=state.self_scaffold_rollback_intents,
            action_context=action_context,
            current_task_id=state.current_task_id,
            task_graph=state.task_graph[-12:],
            repo_map_summary=state.repo_map.summary,
            workspace_summary=state.workspace_isolation.summary,
            workspace_diff_summary=state.workspace_diff.summary,
            workspace_promotions=state.workspace_promotions[-5:],
            patch_proposals=state.patch_proposals[-5:],
            patch_applications=state.patch_applications[-5:],
            recovery_summary=state.recovery_plan.summary if state.recovery_plan.status == "active" else "",
            recovery_steps=state.recovery_plan.steps if state.recovery_plan.status == "active" else [],
            model_profile_adaptation_reviews=adaptation_reviews,
            unresolved_blockers=state.blockers[-10:],
            approvals=approvals,
            acceptance_criteria=state.acceptance_criteria,
            acceptance_evidence=state.acceptance_evidence,
            acceptance_recommendations=state.acceptance_recommendations,
            acceptance_recommendation_traces=state.acceptance_recommendation_traces[-20:],
            run_health=run_health,
            completion_audit=completion_audit,
            policy_simulation=policy_simulation,
            resume_decisions=resume_decisions,
            run_progress=run_progress,
            report_integrity=state.report_integrity,
            objective_readiness=state.objective_readiness,
            objective_readiness_proof_outcomes=state.objective_readiness_proof_outcomes[-20:],
            readiness_rehearsal=state.readiness_rehearsal,
            action_readiness=action_readiness,
            action_readiness_decisions=action_readiness_decisions,
            autonomy_decisions=autonomy_decisions,
            recovery_decisions=recovery_decisions,
            verification_outcomes=verification_outcomes,
            post_action_retries=state.post_action_retries,
            operator_dispatches=operator_dispatches,
            operator_dispatch_restart_smoke=state.operator_dispatch_restart_smoke,
            ornith_preflight_actions=ornith_preflight_actions,
            resume_prompt=resume_prompt,
        )
        preflight_state = state.model_copy(deep=True)
        preflight_state.handoff_summary = handoff
        ornith_preflight = OrnithLaunchChecklistReport.model_validate(
            self.get_ornith_launch_checklist(run.id, state=preflight_state)
        )
        handoff.ornith_preflight = ornith_preflight
        state.ornith_preflight = ornith_preflight
        report_integrity = self._build_report_integrity(run, state, handoff)
        handoff.report_integrity = report_integrity
        objective_readiness = self._build_objective_readiness(run, state)
        handoff.objective_readiness = objective_readiness
        readiness_completion = self._build_readiness_completion(
            run,
            state,
            objective_readiness=objective_readiness,
            run_progress=run_progress,
            completion_audit=completion_audit,
        )
        handoff.readiness_completion = readiness_completion
        return handoff

    def _summarize_result(self, result: ToolResult) -> str:
        if result.web_sources:
            return f"{result.summary} Sources: " + "; ".join(source.citation for source in result.web_sources[:3])
        if result.desktop_snapshots:
            return f"{result.summary} Artifact: {result.desktop_snapshots[0].path}"
        return result.summary

    def _workspace_diff_preview(self, diff: Any) -> dict[str, Any]:
        return {
            "summary": diff.summary,
            "total_files": diff.total_files,
            "added": diff.added,
            "modified": diff.modified,
            "deleted": diff.deleted,
            "truncated": diff.truncated,
            "source_path": diff.source_path,
            "workspace_path": diff.workspace_path,
            "files": [
                {
                    "path": item.path,
                    "status": item.status,
                    "binary": item.binary,
                    "truncated": item.truncated,
                    "diff_excerpt": item.diff[:1200],
                }
                for item in diff.files[:8]
            ],
        }

    def _utc_datetime(self) -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0)

    def _iso_datetime(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")

    def _parse_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    def _lease_is_live(self, lease: RunLease) -> bool:
        if lease.status != "active":
            return False
        expires_at = self._parse_datetime(lease.expires_at)
        return bool(expires_at and expires_at > self._utc_datetime())

    def _has_active_task(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return bool(task and not task.done())

    def _acquire_run_lease(self, run_id: str, event: str) -> RunRecord:
        run = self.store.get_run(run_id)
        state = run.state
        now = self._utc_datetime()
        continuing = state.run_lease.status == "active" and state.run_lease.owner_id == self.engine_id
        lease = RunLease(
            id=state.run_lease.id if continuing and state.run_lease.id else f"lease-{uuid4().hex[:8]}",
            owner_id=self.engine_id,
            status="active",
            acquired_at=state.run_lease.acquired_at if continuing and state.run_lease.acquired_at else self._iso_datetime(now),
            heartbeat_at=self._iso_datetime(now),
            expires_at=self._iso_datetime(now + timedelta(seconds=self.config.run_lease_ttl_seconds)),
            heartbeat_count=state.run_lease.heartbeat_count if continuing else 0,
            heartbeat_interval_seconds=self.config.run_heartbeat_interval_seconds,
            ttl_seconds=self.config.run_lease_ttl_seconds,
            last_milestone=state.milestone,
            last_event=event,
        )
        return self.store.update_run_lease(run_id, lease)

    def _heartbeat_run_lease(self, run_id: str, event: str = "heartbeat") -> RunRecord | None:
        try:
            run = self.store.get_run(run_id)
        except KeyError:
            return None
        if run.status not in {"queued", "running"}:
            return None
        state = run.state
        if state.run_lease.status != "active" or state.run_lease.owner_id != self.engine_id:
            return None
        now = self._utc_datetime()
        lease = state.run_lease.model_copy(deep=True)
        lease.heartbeat_at = self._iso_datetime(now)
        lease.expires_at = self._iso_datetime(now + timedelta(seconds=self.config.run_lease_ttl_seconds))
        lease.heartbeat_count += 1
        lease.heartbeat_interval_seconds = self.config.run_heartbeat_interval_seconds
        lease.ttl_seconds = self.config.run_lease_ttl_seconds
        lease.last_milestone = state.milestone
        lease.last_event = event
        return self.store.update_run_lease(run_id, lease)

    async def _heartbeat_loop(self, run_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(self.config.run_heartbeat_interval_seconds)
                if self._heartbeat_run_lease(run_id) is None:
                    return
        except asyncio.CancelledError:
            return

    def _release_run_lease(self, run_id: str, event: str) -> None:
        try:
            run = self.store.get_run(run_id)
        except KeyError:
            return
        state = run.state
        if state.run_lease.status != "active" or state.run_lease.owner_id != self.engine_id:
            return
        lease = state.run_lease.model_copy(deep=True)
        lease.status = "released"
        lease.expires_at = ""
        lease.last_milestone = state.milestone
        lease.last_event = event
        self.store.update_run_lease(run_id, lease)

    def _auto_resume_decision(
        self,
        run: RunRecord,
        pending_approvals: list[dict[str, Any]],
        policy_simulation: Any,
        run_progress: Any | None = None,
    ) -> tuple[bool, str]:
        state = run.state
        if not self.config.enable_supervisor_auto_resume:
            return False, "Auto-resume is disabled."
        if self.config.supervisor_auto_resume_max_runs <= 0:
            return False, "Auto-resume max runs is zero."
        if run.status != "queued":
            return False, "Only stale queued runs are eligible for auto-resume."
        health = policy_simulation.run_health
        if not policy_simulation.auto_resume_eligible:
            return False, f"Policy simulation blocks auto-resume: {policy_simulation.summary} {policy_simulation.reason}".strip()
        if run_progress and run_progress.status in {"needs_recovery", "waiting", "blocked"}:
            return False, f"Run progress is {run_progress.status}: {run_progress.summary}"
        if health.recommended_action in {"wait_approval", "ask_user", "recover", "pause"}:
            return False, f"Run health recommends {health.recommended_action}: {health.summary}"
        if pending_approvals:
            return False, "Pending approvals require user review."
        if state.proposed_goal:
            return False, "Pending goal proposal requires confirmation."
        if state.recovery_plan.status == "active":
            return False, "Active recovery plans require explicit recovery resume."
        if state.blockers:
            return False, "Recorded blockers require user review."
        if state.active_tool:
            return False, "Active tool state requires user review."
        if state.context_budget.pressure == "high":
            return False, "High context pressure requires re-orientation before auto-resume."
        if state.failure_counts and max(state.failure_counts.values()) >= 3:
            return False, "Repeated failures require recovery planning before auto-resume."
        if state.step_count >= self.config.max_loop_steps:
            return False, "Run has reached the configured loop step limit."
        return True, "Safe stale queued run eligible under supervisor auto-resume policy."

    def _objective_readiness_supervisor_action(self, run: RunRecord, state: RunState, objective_readiness: Any) -> str:
        if not getattr(objective_readiness, "run_id", ""):
            return "Objective readiness has not been generated yet."
        if objective_readiness.status == "ready":
            return "Objective readiness is ready; keep normal progress and verification gates."
        action = self._objective_readiness_actions(objective_readiness, limit=1)
        next_action = action[0] if action else objective_readiness.recommended_action
        proof = self._first_objective_readiness_proof(objective_readiness)
        proof_text = f" proof {proof}" if proof else ""
        if self._is_harness_improvement_goal(run, state):
            return f"Objective readiness is {objective_readiness.status}:{proof_text} {next_action}".strip()
        return f"Objective readiness is {objective_readiness.status}{proof_text}; no harness-plan injection for this goal."

    def _readiness_smoke_supervisor_signal(
        self,
        run: RunRecord,
        state: RunState,
        ledger: ReadinessRehearsalLedgerReport,
    ) -> dict[str, Any]:
        if not self._is_harness_improvement_goal(run, state):
            return {
                "required": False,
                "status": "not_applicable",
                "action": "Readiness smoke applies only to harness-improvement runs.",
                "latest_run_id": ledger.latest.run_id if ledger.latest else "",
                "requires_attention": False,
            }
        if self._is_readiness_rehearsal_run(run, state):
            return {
                "required": False,
                "status": "exempt",
                "action": "This Ornith rehearsal run is producing readiness-smoke evidence.",
                "latest_run_id": ledger.latest.run_id if ledger.latest else "",
                "requires_attention": False,
            }
        latest = ledger.latest
        if latest is None or ledger.status == "never_run":
            return {
                "required": True,
                "status": "missing",
                "action": ledger.next_action,
                "latest_run_id": "",
                "requires_attention": True,
            }
        action = ledger.next_action or latest.next_action
        latest_run_id = latest.run_id
        if latest.status in {"running", "failed"}:
            return {
                "required": True,
                "status": latest.status,
                "action": action,
                "latest_run_id": latest_run_id,
                "requires_attention": True,
            }
        if not self._readiness_smoke_entry_is_complete(latest):
            return {
                "required": True,
                "status": "incomplete",
                "action": "Rerun the readiness-claim smoke rehearsal and inspect failed or missing evidence.",
                "latest_run_id": latest_run_id,
                "requires_attention": True,
            }
        smoke_time = self._parse_datetime(latest.generated_at)
        run_created = self._parse_datetime(run.created_at)
        if smoke_time and run_created and smoke_time < run_created:
            return {
                "required": True,
                "status": "stale",
                "action": "Run a fresh readiness-claim smoke rehearsal for this harness-improvement run.",
                "latest_run_id": latest_run_id,
                "requires_attention": True,
            }
        if ledger.failed_count:
            return {
                "required": True,
                "status": "mixed",
                "action": "Latest smoke passed, but compare it against recent failed rehearsal history before claiming readiness.",
                "latest_run_id": latest_run_id,
                "requires_attention": False,
            }
        return {
            "required": True,
            "status": "passed",
            "action": "Latest readiness smoke passed; keep normal verification and completion gates.",
            "latest_run_id": latest_run_id,
            "requires_attention": False,
        }

    def _readiness_smoke_entry_is_complete(self, latest: ReadinessRehearsalLedgerEntry) -> bool:
        return (
            latest.status == "passed"
            and latest.restart_simulated
            and latest.replay_attached
            and latest.handoff_attached
            and bool(latest.refused_event_id)
            and bool(latest.accepted_event_id)
            and bool(latest.completed_event_id)
            and latest.step_count > 0
            and latest.passed_steps == latest.step_count
            and latest.failed_steps == 0
        )

    def _operator_dispatch_restart_smoke_supervisor_signal(
        self,
        run: RunRecord,
        state: RunState,
        ledger: OperatorDispatchRestartSmokeLedgerReport,
    ) -> dict[str, Any]:
        if not self._is_harness_improvement_goal(run, state):
            return {
                "required": False,
                "status": "not_applicable",
                "action": "Operator-dispatch restart smoke applies only to harness-improvement runs.",
                "latest_run_id": ledger.latest.run_id if ledger.latest else "",
                "requires_attention": False,
            }
        if self._is_operator_dispatch_restart_smoke_run(run, state):
            return {
                "required": False,
                "status": "exempt",
                "action": "This Ornith operator smoke run is producing dispatch-restart evidence.",
                "latest_run_id": ledger.latest.run_id if ledger.latest else "",
                "requires_attention": False,
            }
        latest = ledger.latest
        if latest is None or ledger.status == "never_run":
            return {
                "required": True,
                "status": "missing",
                "action": ledger.next_action,
                "latest_run_id": "",
                "requires_attention": True,
            }
        action = ledger.next_action or latest.next_action
        latest_run_id = latest.run_id
        if latest.status in {"running", "failed"}:
            return {
                "required": True,
                "status": latest.status,
                "action": action,
                "latest_run_id": latest_run_id,
                "requires_attention": True,
            }
        if not self._operator_dispatch_restart_smoke_entry_is_complete(latest):
            return {
                "required": True,
                "status": "incomplete",
                "action": "Rerun the operator-dispatch restart smoke and inspect failed or missing evidence.",
                "latest_run_id": latest_run_id,
                "requires_attention": True,
            }
        smoke_time = self._parse_datetime(latest.generated_at)
        run_created = self._parse_datetime(run.created_at)
        if smoke_time and run_created and smoke_time < run_created:
            return {
                "required": True,
                "status": "stale",
                "action": "Run a fresh operator-dispatch restart smoke for this harness-improvement run.",
                "latest_run_id": latest_run_id,
                "requires_attention": True,
            }
        if ledger.failed_count:
            return {
                "required": True,
                "status": "mixed",
                "action": "Latest dispatch restart smoke passed, but compare it against recent failed smoke history.",
                "latest_run_id": latest_run_id,
                "requires_attention": False,
            }
        return {
            "required": True,
            "status": "passed",
            "action": "Latest operator-dispatch restart smoke passed; keep normal supervisor and handoff gates.",
            "latest_run_id": latest_run_id,
            "requires_attention": False,
        }

    def _operator_dispatch_restart_smoke_entry_is_complete(
        self,
        latest: OperatorDispatchRestartSmokeLedgerEntry,
    ) -> bool:
        return (
            latest.status == "passed"
            and latest.restart_simulated
            and latest.ledger_attached
            and latest.handoff_attached
            and latest.replay_attached
            and latest.context_attached
            and bool(latest.dispatch_event_id)
            and latest.step_count > 0
            and latest.passed_steps == latest.step_count
            and latest.failed_steps == 0
        )

    def _build_operator_action_queue(
        self,
        supervisor_report: dict[str, Any],
        *,
        limit: int = 12,
        queue_filter: str = "all",
    ) -> OperatorActionQueueReport:
        items: list[OperatorActionQueueItem] = []

        def add_item(
            run_entry: dict[str, Any],
            *,
            reason: str,
            action: str,
            endpoint: str,
            method: str,
            ui_target: str,
            approval_id: int = 0,
            approval_kind: str = "",
            details: list[str] | None = None,
        ) -> None:
            run_id = str(run_entry.get("run_id") or "")
            if not run_id:
                return
            severity = str(run_entry.get("operator_attention_severity") or "watch")
            if severity not in {"watch", "blocked"}:
                severity = "watch"
            suffix = str(approval_id) if approval_id else reason
            item_id = f"{run_id}:{reason}:{suffix}"
            queue_details = list(details or [])
            attention_action = str(run_entry.get("operator_attention_action") or "")
            if attention_action and attention_action not in queue_details:
                queue_details.append(attention_action)
            items.append(
                OperatorActionQueueItem(
                    id=item_id,
                    run_id=run_id,
                    title=str(run_entry.get("title") or run_id),
                    severity=severity,  # type: ignore[arg-type]
                    reason=reason,
                    action=action,
                    status=str(run_entry.get("status") or ""),
                    supervisor_action=str(run_entry.get("action") or ""),
                    priority=int(run_entry.get("supervisor_priority") or 0),
                    approval_id=approval_id,
                    approval_kind=approval_kind,
                    endpoint=endpoint,
                    method=method,
                    ui_target=ui_target,
                    details=queue_details[:4],
                )
            )

        for run_entry in supervisor_report.get("runs", []):
            if not isinstance(run_entry, dict) or not run_entry.get("operator_attention_required"):
                continue
            run_id = str(run_entry.get("run_id") or "")
            if not run_id:
                continue
            reasons = [
                str(reason)
                for reason in run_entry.get("operator_attention_reasons", [])
                if str(reason).strip()
            ]
            pending_approvals = self.store.list_approvals(run_id, status="pending")
            emitted_review_approval = False
            reason_set = set(reasons)
            for reason in reasons:
                if reason == "approval":
                    if pending_approvals:
                        for approval in pending_approvals:
                            approval_id = int(approval.get("id") or 0)
                            approval_kind = str(approval.get("action_kind") or "approval")
                            add_item(
                                run_entry,
                                reason="approval",
                                action=f"Review {approval_kind} approval, then approve or reject it in the dashboard.",
                                endpoint=f"/api/runs/{run_id}/approvals",
                                method="GET",
                                ui_target="approval",
                                approval_id=approval_id,
                                approval_kind=approval_kind,
                                details=[
                                    str(approval.get("reason") or ""),
                                    f"approval_id={approval_id}",
                                ],
                            )
                        emitted_review_approval = True
                    else:
                        add_item(
                            run_entry,
                            reason="approval",
                            action="Review approval state before resuming.",
                            endpoint=f"/api/runs/{run_id}/approvals",
                            method="GET",
                            ui_target="approval",
                        )
                        emitted_review_approval = True
                elif reason == "waiting_approval":
                    if emitted_review_approval:
                        continue
                    add_item(
                        run_entry,
                        reason=reason,
                        action="Open the run and resolve the approval wait state.",
                        endpoint=f"/api/runs/{run_id}/approvals",
                        method="GET",
                        ui_target="approval",
                    )
                elif reason == "readiness_smoke":
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(run_entry.get("readiness_smoke_action") or "Run the readiness smoke rehearsal."),
                        endpoint="/api/rehearsals/readiness-claim",
                        method="POST",
                        ui_target="readiness_rehearsal",
                        details=[
                            f"smoke_status={run_entry.get('readiness_smoke_status') or 'unknown'}",
                            f"latest_smoke={run_entry.get('readiness_smoke_latest_run_id') or 'none'}",
                        ],
                    )
                elif reason == "operator_dispatch_restart_smoke":
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(
                            run_entry.get("operator_dispatch_restart_smoke_action")
                            or "Run the operator-dispatch restart smoke."
                        ),
                        endpoint="/api/rehearsals/operator-dispatch-restart",
                        method="POST",
                        ui_target="operator_dispatch_restart_smoke",
                        details=[
                            f"dispatch_smoke_status={run_entry.get('operator_dispatch_restart_smoke_status') or 'unknown'}",
                            f"latest_dispatch_smoke={run_entry.get('operator_dispatch_restart_smoke_latest_run_id') or 'none'}",
                        ],
                    )
                elif reason == "ornith_preflight":
                    preflight = run_entry.get("ornith_preflight") if isinstance(run_entry.get("ornith_preflight"), dict) else {}
                    emitted_preflight_item = False
                    for checklist_item in preflight.get("items", []):
                        if not isinstance(checklist_item, dict) or checklist_item.get("status") == "pass":
                            continue
                        mapped = self._ornith_preflight_operator_action(run_id, checklist_item, reason_set)
                        if mapped is None:
                            continue
                        add_item(
                            run_entry,
                            reason=f"ornith_preflight_{mapped['item_id']}",
                            action=mapped["action"],
                            endpoint=mapped["endpoint"],
                            method=mapped["method"],
                            ui_target=mapped["ui_target"],
                            details=mapped["details"],
                        )
                        emitted_preflight_item = True
                    if not emitted_preflight_item:
                        add_item(
                            run_entry,
                            reason=reason,
                            action=str(preflight.get("summary") or "Review Ornith preflight before resuming."),
                            endpoint=f"/api/runs/{run_id}/ornith-preflight",
                            method="GET",
                            ui_target="ornith_preflight",
                        )
                elif reason == "source_evidence":
                    source_evidence = run_entry.get("source_evidence") if isinstance(run_entry.get("source_evidence"), dict) else {}
                    missing_labels = source_evidence.get("missing_labels") if isinstance(source_evidence.get("missing_labels"), list) else []
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(run_entry.get("source_evidence_action") or "Capture missing web/browser source evidence."),
                        endpoint=f"/api/runs/{run_id}/source-evidence",
                        method="GET",
                        ui_target="source_evidence",
                        details=[
                            "missing=" + ",".join(str(label) for label in missing_labels[:4]),
                            f"latest={source_evidence.get('latest_evidence') or 'none'}",
                        ],
                    )
                elif reason == "self_scaffold":
                    scaffold = run_entry.get("self_scaffold") if isinstance(run_entry.get("self_scaffold"), dict) else {}
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(run_entry.get("self_scaffold_action") or "Review self-scaffold change intent before broad autonomy."),
                        endpoint=f"/api/runs/{run_id}/replay",
                        method="GET",
                        ui_target="self_scaffold",
                        details=[
                            f"self_scaffold={scaffold.get('status') or 'unknown'}",
                            f"changes={scaffold.get('change_count') or 0}",
                            f"guards={scaffold.get('guard_count') or 0}",
                            str(scaffold.get("latest_change") or "latest=none")[:180],
                        ],
                    )
                elif reason == "self_scaffold_rollback":
                    rollback_action = self._self_scaffold_rollback_operator_action(run_entry)
                    if rollback_action:
                        add_item(
                            run_entry,
                            reason=rollback_action["reason"],
                            action=rollback_action["action"],
                            endpoint=rollback_action["endpoint"],
                            method=rollback_action["method"],
                            ui_target=rollback_action["ui_target"],
                            approval_kind=str(rollback_action.get("approval_kind") or ""),
                            details=rollback_action["details"],
                        )
                    else:
                        rollback_report = run_entry.get("self_scaffold_rollback_intents") if isinstance(run_entry.get("self_scaffold_rollback_intents"), dict) else {}
                        add_item(
                            run_entry,
                            reason=reason,
                            action=str(run_entry.get("self_scaffold_rollback_action") or "Review self-scaffold rollback intent before continuing."),
                            endpoint=f"/api/runs/{run_id}/self-scaffold-rollback-intents",
                            method="GET",
                            ui_target="self_scaffold_rollback",
                            details=[
                                f"rollback_status={rollback_report.get('status') or 'unknown'}",
                                f"intents={rollback_report.get('intent_count') or 0}",
                                f"patch_rollbacks={rollback_report.get('patch_rollback_count') or 0}",
                            ],
                        )
                elif reason == "health_wait_approval":
                    if emitted_review_approval or "approval" in reason_set or "waiting_approval" in reason_set:
                        continue
                    add_item(
                        run_entry,
                        reason=reason,
                        action="Open the run and resolve pending approval state.",
                        endpoint=f"/api/runs/{run_id}/approvals",
                        method="GET",
                        ui_target="approval",
                    )
                elif reason == "health_recover" and "recovery" in reason_set:
                    continue
                elif reason in {"recovery", "health_recover"}:
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(run_entry.get("operator_attention_action") or "Resume or replan active recovery."),
                        endpoint=f"/api/runs/{run_id}/recovery/resume",
                        method="POST",
                        ui_target="recovery",
                    )
                elif reason == "waiting_goal_confirmation":
                    add_item(
                        run_entry,
                        reason=reason,
                        action="Review the proposed goal update and accept or reject it.",
                        endpoint=f"/api/runs/{run_id}/goal/review",
                        method="POST",
                        ui_target="goal",
                    )
                elif reason in {"blocked", "error", "health_ask_user"} and "blocker" in reason_set:
                    continue
                elif reason in {"blocker", "blocked", "error", "health_ask_user"}:
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(run_entry.get("operator_attention_action") or "Open the run and steer around the blocker."),
                        endpoint=f"/api/runs/{run_id}/steer",
                        method="POST",
                        ui_target="steer",
                        details=[
                            str(blocker)
                            for blocker in self.store.get_run(run_id).state.blockers[:3]
                        ],
                    )
                elif reason == "health_pause":
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(run_entry.get("operator_attention_action") or "Review paused health state before resuming."),
                        endpoint=f"/api/runs/{run_id}/resume",
                        method="POST",
                        ui_target="resume",
                    )
                else:
                    add_item(
                        run_entry,
                        reason=reason,
                        action=str(run_entry.get("operator_attention_action") or "Open the run for operator review."),
                        endpoint=f"/api/runs/{run_id}",
                        method="GET",
                        ui_target="run",
                    )

        if queue_filter == "promotion_approvals":
            items = [item for item in items if item.ui_target == "patch_apply_approval" or item.reason.startswith("promotion")]
        elif queue_filter == "proof_reviews":
            proof_review_reasons = {
                "readiness_proof_history",
                "readiness_source_refs",
                "source_evidence",
                "desktop_effect_proof",
                "self_scaffold_rollback",
            }
            items = [item for item in items if item.reason in proof_review_reasons]

        items.sort(
            key=lambda item: (
                1 if item.severity == "blocked" else 0,
                item.priority,
                1 if item.reason == "approval" else 0,
            ),
            reverse=True,
        )
        total_count = len(items)
        blocked_count = sum(1 for item in items if item.severity == "blocked")
        watch_count = total_count - blocked_count
        summary = (
            "No operator actions require attention."
            if total_count == 0
            else f"{total_count} operator actions queued: {blocked_count} blocked / {watch_count} watch."
        )
        return OperatorActionQueueReport(
            generated_at=str(supervisor_report.get("ran_at") or utc_now()),
            total_count=total_count,
            blocked_count=blocked_count,
            watch_count=watch_count,
            approval_count=sum(
                1 for item in items if item.reason in {"approval", "waiting_approval", "health_wait_approval"}
            ),
            smoke_count=sum(
                1
                for item in items
                if item.reason in {"readiness_smoke", "operator_dispatch_restart_smoke"}
                or item.reason in {"ornith_preflight_readiness_smoke", "ornith_preflight_operator_dispatch_restart_smoke"}
            ),
            preflight_count=sum(1 for item in items if item.reason.startswith("ornith_preflight")),
            self_scaffold_count=sum(1 for item in items if item.reason == "self_scaffold"),
            self_scaffold_rollback_count=sum(1 for item in items if item.reason == "self_scaffold_rollback"),
            recovery_count=sum(1 for item in items if item.reason in {"recovery", "health_recover"}),
            blocker_count=sum(1 for item in items if item.reason in {"blocker", "blocked", "error", "health_ask_user"}),
            summary=summary,
            items=items[:limit],
        )

    def _self_scaffold_rollback_operator_action(self, run_entry: dict[str, Any]) -> dict[str, Any] | None:
        run_id = str(run_entry.get("run_id") or "")
        report = run_entry.get("self_scaffold_rollback_intents") if isinstance(run_entry.get("self_scaffold_rollback_intents"), dict) else {}
        entries = report.get("entries") if isinstance(report.get("entries"), list) else []
        rollback = next(
            (
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("action_kind") == "patch_rollback"
                and entry.get("status") == "needs_approval"
                and str(entry.get("patch_id") or "")
            ),
            None,
        )
        if rollback is None:
            return None
        patch_id = str(rollback.get("patch_id") or "")
        files = rollback.get("files") if isinstance(rollback.get("files"), list) else []
        details = [
            f"patch_id={patch_id}",
            f"backup_id={rollback.get('backup_id') or 'missing'}",
            f"review_event={rollback.get('source_review_event_id') or 0}",
            "no_auto_mutation=true",
            "files=" + ",".join(str(file) for file in files[:3]),
        ]
        return {
            "reason": "self_scaffold_rollback",
            "action": str(run_entry.get("self_scaffold_rollback_action") or f"Request approval to rollback patch {patch_id} from self-scaffold review."),
            "endpoint": f"/api/runs/{run_id}/patches/{patch_id}/rollback",
            "method": "POST",
            "ui_target": "patch_rollback_approval",
            "approval_kind": "patch_rollback",
            "details": details,
        }

    def _patch_id_from_apply_endpoint(self, endpoint: str) -> str:
        parts = str(endpoint or "").strip("/").split("/")
        if len(parts) >= 5 and parts[-1] == "apply" and parts[-3] == "patches":
            return parts[-2]
        return ""

    def _patch_id_from_rollback_endpoint(self, endpoint: str) -> str:
        parts = str(endpoint or "").strip("/").split("/")
        if len(parts) >= 5 and parts[-1] == "rollback" and parts[-3] == "patches":
            return parts[-2]
        return ""

    def _ornith_preflight_item_covered_by_reason(self, item_id: str, reason_set: set[str]) -> bool:
        if item_id == "readiness_smoke" and "readiness_smoke" in reason_set:
            return True
        if item_id == "operator_dispatch_restart_smoke" and "operator_dispatch_restart_smoke" in reason_set:
            return True
        if item_id == "approval_posture" and reason_set.intersection({"approval", "waiting_approval", "health_wait_approval"}):
            return True
        if item_id in {"run_health", "resume_policy"} and (
            any(reason.startswith("health_") for reason in reason_set)
            or reason_set.intersection({"readiness_smoke", "operator_dispatch_restart_smoke"})
        ):
            return True
        return False
    def _ornith_preflight_operator_action(
        self,
        run_id: str,
        item: dict[str, Any],
        reason_set: set[str],
    ) -> dict[str, Any] | None:
        item_id = str(item.get("id") or "preflight")
        status = str(item.get("status") or "warn")
        summary = str(item.get("summary") or "")
        next_action = str(item.get("next_action") or summary or "Review Ornith preflight before resuming.")
        evidence = [str(entry) for entry in item.get("evidence", []) if str(entry).strip()]
        details = [f"preflight_status={status}", summary, *evidence][:4]

        if self._ornith_preflight_item_covered_by_reason(item_id, reason_set):
            return None

        if item_id == "readiness_smoke":
            return {
                "item_id": item_id,
                "action": next_action or "Run the readiness smoke rehearsal.",
                "endpoint": "/api/rehearsals/readiness-claim",
                "method": "POST",
                "ui_target": "readiness_rehearsal",
                "details": details,
            }
        if item_id == "operator_dispatch_restart_smoke":
            return {
                "item_id": item_id,
                "action": next_action or "Run the operator-dispatch restart smoke.",
                "endpoint": "/api/rehearsals/operator-dispatch-restart",
                "method": "POST",
                "ui_target": "operator_dispatch_restart_smoke",
                "details": details,
            }
        if item_id == "context_budget":
            return {
                "item_id": item_id,
                "action": next_action or "Checkpoint and compact context before resuming.",
                "endpoint": f"/api/runs/{run_id}/context/checkpoint",
                "method": "POST",
                "ui_target": "context_checkpoint",
                "details": details,
            }
        if item_id == "handoff_anchor":
            return {
                "item_id": item_id,
                "action": next_action or "Refresh/checkpoint the run handoff before resuming.",
                "endpoint": f"/api/runs/{run_id}/handoff/refresh",
                "method": "POST",
                "ui_target": "handoff_refresh",
                "details": details,
            }
        if item_id == "approval_posture":
            return {
                "item_id": item_id,
                "action": next_action or "Resolve pending approvals in the dashboard.",
                "endpoint": f"/api/runs/{run_id}/approvals",
                "method": "GET",
                "ui_target": "approval",
                "details": details,
            }
        if item_id in {"resume_policy", "run_health"}:
            return {
                "item_id": item_id,
                "action": next_action,
                "endpoint": f"/api/runs/{run_id}",
                "method": "GET",
                "ui_target": "run",
                "details": details,
            }
        return {
            "item_id": item_id,
            "action": next_action,
            "endpoint": f"/api/runs/{run_id}/ornith-preflight",
            "method": "GET",
            "ui_target": "ornith_preflight",
            "details": details,
        }
    def _supervisor_run_priority(self, run_entry: dict[str, Any]) -> int:
        health = run_entry.get("run_health") if isinstance(run_entry.get("run_health"), dict) else {}
        score = int(health.get("score") or 0)
        if run_entry.get("operator_attention_required"):
            score += 25
        if run_entry.get("operator_attention_severity") == "blocked":
            score += 20
        if run_entry.get("readiness_smoke_requires_attention"):
            score += 45
        if run_entry.get("operator_dispatch_restart_smoke_requires_attention"):
            score += 40
        if run_entry.get("ornith_preflight_requires_attention"):
            score += 35
        if run_entry.get("source_evidence_requires_attention"):
            score += 18
        if run_entry.get("self_scaffold_requires_attention"):
            score += 30
        if run_entry.get("self_scaffold_rollback_requires_attention"):
            score += 34
        if run_entry.get("action") not in {"unchanged", "live_lease_preserved"}:
            score += 20
        if int(run_entry.get("pending_approvals") or 0):
            score += 15
        return min(100, score)

    def _finalize_supervisor_run_entry(
        self,
        report: dict[str, Any],
        run_entry: dict[str, Any],
        state: RunState,
    ) -> None:
        reasons: list[str] = []
        severity = "none"
        action = ""
        health = run_entry.get("run_health") if isinstance(run_entry.get("run_health"), dict) else {}
        health_action = str(health.get("recommended_action") or "")
        if int(run_entry.get("pending_approvals") or 0):
            reasons.append("approval")
            action = "Resolve pending approvals in the dashboard."
            severity = "blocked"
        if run_entry.get("readiness_smoke_requires_attention"):
            reasons.append("readiness_smoke")
            action = action or str(run_entry.get("readiness_smoke_action") or "")
            severity = "watch" if severity == "none" else severity
        if run_entry.get("operator_dispatch_restart_smoke_requires_attention"):
            reasons.append("operator_dispatch_restart_smoke")
            action = action or str(run_entry.get("operator_dispatch_restart_smoke_action") or "")
            severity = "watch" if severity == "none" else severity
        ornith_preflight = run_entry.get("ornith_preflight") if isinstance(run_entry.get("ornith_preflight"), dict) else {}
        preflight_items = [
            item
            for item in ornith_preflight.get("items", [])
            if isinstance(item, dict) and item.get("status") != "pass"
        ]
        existing_reason_set = set(reasons)
        preflight_items = [
            item
            for item in preflight_items
            if not self._ornith_preflight_item_covered_by_reason(str(item.get("id") or ""), existing_reason_set)
        ]
        if run_entry.get("ornith_preflight_requires_attention") and preflight_items:
            reasons.append("ornith_preflight")
            first_action = next((str(item.get("next_action") or "") for item in preflight_items if item.get("next_action")), "")
            action = action or first_action or str(ornith_preflight.get("summary") or "Review Ornith preflight before resuming.")
            if any(item.get("status") == "block" for item in preflight_items):
                severity = "blocked"
            elif severity == "none":
                severity = "watch"
        if run_entry.get("source_evidence_requires_attention"):
            reasons.append("source_evidence")
            action = action or str(run_entry.get("source_evidence_action") or "Capture missing web/browser source evidence.")
            if severity == "none":
                severity = "watch"
        if run_entry.get("self_scaffold_requires_attention"):
            reasons.append("self_scaffold")
            action = action or str(run_entry.get("self_scaffold_action") or "Review self-scaffold change intent before broad autonomy.")
            if severity == "none":
                severity = "watch"
        if run_entry.get("self_scaffold_rollback_requires_attention"):
            reasons.append("self_scaffold_rollback")
            action = action or str(run_entry.get("self_scaffold_rollback_action") or "Review self-scaffold rollback intent before broad autonomy.")
            if severity == "none":
                severity = "watch"
        if state.recovery_plan.status == "active":
            reasons.append("recovery")
            action = action or state.recovery_plan.next_action or "Resume or replan active recovery."
            severity = "blocked"
        if state.blockers:
            reasons.append("blocker")
            action = action or "Resolve blockers before continuing."
            severity = "blocked"
        if run_entry.get("status") in {"waiting_approval", "waiting_goal_confirmation", "blocked", "error"}:
            reasons.append(str(run_entry.get("status")))
            if not action:
                action = (
                    "Accept or reject the proposed goal update."
                    if run_entry.get("status") == "waiting_goal_confirmation"
                    else "Review the run before resuming."
                )
            severity = "blocked"
        if health_action in {"wait_approval", "ask_user", "recover", "pause"}:
            reasons.append(f"health_{health_action}")
            next_actions = health.get("next_actions") if isinstance(health.get("next_actions"), list) else []
            if not action:
                action = str(next_actions[0]) if next_actions else "Review run health before continuing."
            severity = "blocked" if health_action in {"wait_approval", "ask_user", "recover"} else "watch"

        reasons = list(dict.fromkeys(reasons))
        self_scaffold_attention_only = bool(
            (run_entry.get("self_scaffold_requires_attention") or run_entry.get("self_scaffold_rollback_requires_attention"))
            and not int(run_entry.get("pending_approvals") or 0)
            and run_entry.get("status") not in {"waiting_approval", "waiting_goal_confirmation", "blocked", "error"}
        )
        if self_scaffold_attention_only and severity == "blocked":
            severity = "watch"
        run_entry["operator_attention_required"] = bool(reasons)
        run_entry["operator_attention_reasons"] = reasons
        run_entry["operator_attention_action"] = action
        run_entry["operator_attention_severity"] = severity if reasons else "none"
        if reasons:
            report["operator_attention_count"] += 1
            if "recovery" in reasons:
                report["operator_recovery_count"] += 1
            if "blocker" in reasons or "blocked" in reasons:
                report["operator_blocker_count"] += 1
            if run_entry["operator_attention_severity"] == "blocked":
                report["operator_attention_blocked_count"] += 1
            else:
                report["operator_attention_watch_count"] += 1
        run_entry["supervisor_priority"] = self._supervisor_run_priority(run_entry)

    def _augment_run_health_with_readiness_smoke(
        self,
        run: RunRecord,
        state: RunState,
        health: RunHealthReport,
    ) -> RunHealthReport:
        ledger = ReadinessRehearsalLedgerReport.model_validate(self.get_readiness_rehearsal_ledger(limit=5))
        smoke = self._readiness_smoke_supervisor_signal(run, state, ledger)
        if not smoke["requires_attention"]:
            return health
        if any(signal.id == "readiness_smoke_attention" for signal in health.signals):
            return health
        health.signals.insert(
            0,
            RunHealthSignal(
                id="readiness_smoke_attention",
                severity="warning",
                summary=f"Readiness smoke needs attention: {smoke['status']}.",
                evidence=[
                    f"status={smoke['status']}",
                    f"latest={smoke['latest_run_id'] or 'none'}",
                    f"required={smoke['required']}",
                ],
            ),
        )
        health.score = min(100, max(health.score, 30))
        if health.level == "healthy":
            health.level = "watch"
        health.summary = f"{health.level}: {health.recommended_action} ({health.score}/100)"
        health.next_actions = list(dict.fromkeys([smoke["action"], *health.next_actions]))[:8]
        return health

    def _augment_run_health_with_dispatch_restart_smoke(
        self,
        run: RunRecord,
        state: RunState,
        health: RunHealthReport,
    ) -> RunHealthReport:
        ledger = OperatorDispatchRestartSmokeLedgerReport.model_validate(
            self.get_operator_dispatch_restart_smoke_ledger(limit=5)
        )
        smoke = self._operator_dispatch_restart_smoke_supervisor_signal(run, state, ledger)
        if not smoke["required"]:
            return health
        if smoke["requires_attention"]:
            if any(signal.id == "operator_dispatch_restart_smoke_attention" for signal in health.signals):
                return health
            health.signals.insert(
                0,
                RunHealthSignal(
                    id="operator_dispatch_restart_smoke_attention",
                    severity="warning",
                    summary=f"Operator-dispatch restart smoke needs attention: {smoke['status']}.",
                    evidence=[
                        f"status={smoke['status']}",
                        f"latest={smoke['latest_run_id'] or 'none'}",
                        f"required={smoke['required']}",
                    ],
                ),
            )
            health.score = min(100, max(health.score, 30))
            if health.level == "healthy":
                health.level = "watch"
            health.summary = f"{health.level}: {health.recommended_action} ({health.score}/100)"
            health.next_actions = list(dict.fromkeys([smoke["action"], *health.next_actions]))[:8]
            return health

        if smoke["status"] not in {"passed", "mixed"}:
            return health
        if any(signal.id == "operator_dispatch_restart_smoke_ready" for signal in health.signals):
            return health
        health.signals.append(
            RunHealthSignal(
                id="operator_dispatch_restart_smoke_ready",
                severity="info",
                summary=f"Operator-dispatch restart smoke evidence is current: {smoke['status']}.",
                evidence=[
                    f"status={smoke['status']}",
                    f"latest={smoke['latest_run_id'] or 'none'}",
                    "handoff=replay=context=attached",
                ],
            )
        )
        return health
    def _first_objective_readiness_proof(self, objective_readiness: Any) -> str:
        for item in getattr(objective_readiness, "items", []):
            if getattr(item, "status", "") == "verified":
                continue
            proof = getattr(item, "proof", None)
            if proof and (proof.tool_kind or proof.evidence_label):
                return f"{proof.tool_kind or 'tool'}/{proof.evidence_label or 'evidence'}"
        return ""

    def _prepare_auto_resume_state(self, run: RunRecord, state: RunState, previous_status: str) -> None:
        state.next_step = "Supervisor auto-resumed from durable handoff; re-orient before acting."
        state.milestone = "orient"
        self._append_unique(
            state.facts_learned,
            f"Supervisor auto-resumed stale {previous_status} run under bounded policy.",
        )
        state.handoff_summary = self._make_handoff(run, state)

    def _append_unique(self, items: list[str], message: str) -> None:
        if message not in items:
            items.append(message)

    def _prepare_startup_resume_state(self, run: RunRecord, state: RunState, previous_status: str) -> None:
        self._append_unique(
            state.blockers,
            f"Supervisor recovered stale {previous_status} status after backend restart; resume explicitly from handoff.",
        )
        if state.recovery_plan.status == "active":
            steps = state.recovery_plan.steps or self._recovery_steps(state.recovery_plan.failure_kind, state.recovery_plan.tool)
            state.recovery_plan.steps = steps
            state.recovery_plan.next_action = state.recovery_plan.next_action or (steps[0] if steps else "Review recovery plan.")
            state.current_plan = steps
            state.task_graph = self._tasks_from_plan(steps, [])
            state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
            if state.recovery_plan.tool:
                state.failure_counts.pop(state.recovery_plan.tool, None)
            state.next_step = state.recovery_plan.next_action
            state.milestone = "orient"
            self._append_unique(state.facts_learned, f"Startup restored active recovery plan: {state.recovery_plan.summary}")
        else:
            state.next_step = "Review latest replay and handoff, then resume if the run should continue."
        state.handoff_summary = self._make_handoff(run, state)


    def _prepare_post_action_retry_followup(self, run: RunRecord, state: RunState, result: ToolResult) -> bool:
        if result.ok or result.needs_approval:
            return False
        report = build_post_action_retry_report(run.model_copy(update={"state": state}))
        state.post_action_retries = report
        decision = report.latest_decision
        if decision.status != "pending":
            return False
        steps = [
            decision.selected_action,
            "Verify the post-action retry result with the narrowest relevant check.",
            "Checkpoint the retry decision and update handoff.",
        ]
        state.latest_summary = report.summary
        state.next_step = decision.selected_action
        state.current_plan = steps
        state.task_graph = self._tasks_from_plan(steps, [])
        state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
        state.milestone = "act"
        state.handoff_summary = self._make_handoff(run, state)
        return True
    def _should_pause_for_recovery(self, state: RunState, result: ToolResult) -> bool:
        return (
            not result.ok
            and not result.needs_approval
            and state.recovery_plan.status == "active"
            and state.failure_counts.get(result.kind, 0) >= 3
        )

    def _ensure_task_graph(self, state: RunState) -> None:
        if state.task_graph:
            return
        task = TaskNode(
            id="task-orient",
            title="Orient from Obsidian, repo map, and durable run state.",
            status="pending",
            kind="investigate",
        )
        state.task_graph = [task]
        state.current_task_id = task.id

    def _tasks_from_plan(self, plan: list[str], existing: list[TaskNode]) -> list[TaskNode]:
        if len(existing) > 1:
            return existing
        tasks: list[TaskNode] = []
        for index, step in enumerate(plan[:12], start=1):
            lowered = step.lower()
            kind = "verify" if "verify" in lowered or "test" in lowered or "check" in lowered else "investigate"
            if (
                "build" in lowered
                or "create" in lowered
                or "edit" in lowered
                or "implement" in lowered
                or "patch" in lowered
                or "write" in lowered
                or "change" in lowered
            ):
                kind = "edit"
            if "summar" in lowered or "checkpoint" in lowered or "handoff" in lowered:
                kind = "summarize"
            tasks.append(TaskNode(id=f"task-{index}", title=step, kind=kind, status="pending"))
        return tasks or existing

    def _set_task_status(self, state: RunState, task_id: str, status: str, evidence: str = "") -> None:
        if not task_id:
            return
        for task in state.task_graph:
            if task.id == task_id:
                task.status = status  # type: ignore[assignment]
                if evidence:
                    task.evidence.append(evidence)
                    task.evidence = task.evidence[-5:]
                return

    def _advance_task(self, state: RunState) -> None:
        for task in state.task_graph:
            if task.status in {"pending", "blocked", "failed"}:
                state.current_task_id = task.id
                return
        state.current_task_id = state.task_graph[-1].id if state.task_graph else ""

    def _current_task(self, state: RunState) -> TaskNode | None:
        for task in state.task_graph:
            if task.id == state.current_task_id:
                return task
        return None

    def _result_advances_current_task(self, state: RunState, result: ToolResult) -> bool:
        task = self._current_task(state)
        if not task:
            return True
        title = task.title.lower()
        if task.kind == "edit" or any(word in title for word in ("build", "create", "implement", "write")):
            return result.kind in {"file_write", "patch_apply", "patch_propose", "workspace_promote"}
        if task.kind == "verify":
            return result.kind in {"browser_screenshot", "desktop_screenshot", "git_diff", "git_status", "run_tests", "shell"}
        if task.kind == "summarize":
            return result.kind in {"checkpoint", "obsidian_checkpoint"}
        if task.kind == "investigate":
            return result.kind in {"browser_open", "browser_screenshot", "desktop_screenshot", "file_read", "web_fetch", "web_search"}
        return True

    def _classify_failure(self, result: ToolResult) -> str:
        summary = result.summary.lower()
        if "timed out" in summary:
            return "timeout"
        if "permission" in summary or "approval" in summary:
            return "permission"
        if "not found" in summary or "no module" in summary:
            return "missing_dependency"
        if result.kind in {"run_tests", "git_diff", "git_status", "shell"}:
            return "command_failure"
        return "tool_failure"

    def _record_failure(self, state: RunState, kind: str, result: ToolResult) -> None:
        for record in state.failure_records:
            if record.kind == kind and record.tool == result.kind:
                record.count += 1
                record.summary = result.summary
                record.last_seen = utc_now()
                record.recovery_hint = self._recovery_hint(kind)
                return
        state.failure_records.append(
            FailureRecord(
                id=f"failure-{uuid4().hex[:8]}",
                kind=kind,
                tool=result.kind,
                summary=result.summary,
                last_seen=utc_now(),
                recovery_hint=self._recovery_hint(kind),
            )
        )
        state.failure_records = state.failure_records[-20:]

    def _recovery_hint(self, kind: str) -> str:
        return {
            "timeout": "Reduce command scope, increase timeout, or checkpoint before retrying.",
            "permission": "Ask user approval or choose a lower-risk action.",
            "missing_dependency": "Inspect project setup and install only with approval.",
            "command_failure": "Read the focused error output and run the narrowest relevant check.",
            "tool_failure": "Try an alternate tool or re-orient from durable state.",
        }.get(kind, "Re-orient and choose a different action.")

    def _activate_recovery_plan(self, state: RunState, kind: str, result: ToolResult, attempts: int) -> None:
        steps = self._recovery_steps(kind, result.kind)
        plan = RecoveryPlan(
            id=f"recovery-{uuid4().hex[:8]}",
            status="active",
            trigger="repeated_failure",
            failure_kind=kind,
            tool=result.kind,
            attempts=attempts,
            summary=f"Repeated {result.kind} failure classified as {kind}: {result.summary}",
            next_action=steps[0],
            steps=steps,
            created_at=utc_now(),
        )
        state.recovery_plan = plan
        state.current_plan = steps
        state.task_graph = self._tasks_from_plan(steps, [])
        state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
        state.milestone = "orient"
        state.next_step = plan.next_action
        state.latest_summary = plan.summary
        state.open_questions.append("Recovery plan activated after repeated tool failure; inspect before retrying the same action.")

    def _activate_readiness_recovery_plan(self, state: RunState) -> None:
        candidate, attempts = self._readiness_recovery_candidate(state)
        if not candidate:
            return
        steps = self._readiness_recovery_steps(candidate)
        label = candidate.label or candidate.suggested_label or "proof"
        kind = "readiness_proof_unresolved" if candidate.status == "executed" else "readiness_proof_failure"
        plan = RecoveryPlan(
            id=f"recovery-{uuid4().hex[:8]}",
            status="active",
            trigger="readiness_decision_loop",
            failure_kind=kind,
            tool=candidate.selected_tool,
            attempts=attempts,
            summary=(
                f"Readiness proof loop for {label} via {candidate.selected_tool}: "
                f"{candidate.result_summary or candidate.summary}"
            ),
            next_action=steps[0],
            steps=steps,
            created_at=utc_now(),
        )
        state.recovery_plan = plan
        state.current_plan = steps
        state.task_graph = self._tasks_from_plan(steps, [])
        state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
        state.milestone = "orient"
        state.next_step = plan.next_action
        state.latest_summary = plan.summary
        self._append_unique(
            state.open_questions,
            "Recovery plan activated after repeated action-readiness proof attempts; choose an alternate proof strategy before retrying the same tool.",
        )

    def _activate_objective_readiness_recovery_plan(self, state: RunState) -> None:
        candidate, attempts = self._objective_readiness_recovery_candidate(state)
        if not candidate:
            return
        steps = self._objective_readiness_recovery_steps(candidate)
        label = candidate.evidence_label or candidate.item_id or "objective readiness"
        kind = "objective_readiness_proof_partial" if candidate.outcome == "partial" else "objective_readiness_proof_failure"
        plan = RecoveryPlan(
            id=f"recovery-{uuid4().hex[:8]}",
            status="active",
            trigger="objective_readiness_proof_loop",
            failure_kind=kind,
            tool=candidate.tool,
            attempts=attempts,
            summary=(
                f"Objective-readiness proof loop for {candidate.item_id} via {candidate.tool}: "
                f"{candidate.summary}"
            ),
            next_action=steps[0],
            steps=steps,
            created_at=utc_now(),
        )
        state.recovery_plan = plan
        state.current_plan = steps
        state.task_graph = self._tasks_from_plan(steps, [])
        state.current_task_id = state.task_graph[0].id if state.task_graph else state.current_task_id
        state.milestone = "orient"
        state.next_step = plan.next_action
        state.latest_summary = plan.summary
        self._append_unique(
            state.open_questions,
            (
                f"Recovery plan activated after repeated objective-readiness proof attempts for {label}; "
                "choose an alternate proof strategy before retrying the same tool."
            ),
        )

    def _readiness_recovery_candidate(self, state: RunState) -> tuple[ActionReadinessDecisionRecord | None, int]:
        counts: dict[tuple[str, str, str], int] = {}
        latest: dict[tuple[str, str, str], ActionReadinessDecisionRecord] = {}
        for decision in state.action_readiness_decisions.decisions[-12:]:
            if decision.status not in {"failed", "executed"} or not decision.selected_tool:
                continue
            label = decision.label or decision.suggested_label or "proof"
            key = (decision.status, label, decision.selected_tool)
            counts[key] = counts.get(key, 0) + 1
            latest[key] = decision
        repeated = [(key, count) for key, count in counts.items() if count >= 2]
        if not repeated:
            return None, 0
        key, count = sorted(repeated, key=lambda item: item[1])[-1]
        return latest[key], count

    def _readiness_recovery_steps_from_state(self, state: RunState) -> list[str]:
        candidate, _attempts = self._readiness_recovery_candidate(state)
        return self._readiness_recovery_steps(candidate) if candidate else []

    def _readiness_recovery_steps(self, decision: ActionReadinessDecisionRecord | None) -> list[str]:
        if not decision:
            return []
        label = decision.label or decision.suggested_label or "proof"
        tool = decision.selected_tool or decision.suggested_tool or "readiness tool"
        evidence = decision.result_summary or decision.summary or "No compact result summary recorded."
        return [
            f"Review the readiness decision ledger for {label} via {tool}: {evidence}",
            self._alternate_proof_step(label, tool, decision),
            "Update the active plan with the confirmed alternate proof or blocker before retrying the same readiness tool.",
            f"Verify {label} with the narrowest successful alternate proof and record the result in the handoff.",
        ]

    def _alternate_proof_step(self, label: str, tool: str, decision: ActionReadinessDecisionRecord) -> str:
        if label == "verification":
            if tool == "run_tests":
                return "Run a narrower diagnostic than the repeated test command, such as a single failing test, import check, or focused lint/build target."
            return "Use `run_tests` or a focused shell diagnostic to prove the verification label through a different command path."
        if label == "browser":
            if tool == "browser_screenshot":
                return "Use a desktop screenshot or inspect the dev-server/log output before repeating the browser screenshot."
            return "Use a browser screenshot against the exact local URL or inspect the rendered page before repeating the desktop proof."
        if label == "web":
            return "Fetch a specific cited URL or ask the user for an authoritative source before repeating broad search."
        if label == "checkpoint":
            return "Write a fresh Obsidian checkpoint and then verify the checkpoint appears in the current run handoff."
        if label == "edit":
            return "Inspect the current workspace diff and propose the smallest patch before applying another edit."
        criterion = decision.criterion or "the open criterion"
        return f"Ask which alternate proof should satisfy {label} for {criterion}, then record that proof path before retrying."

    def _objective_readiness_recovery_candidate(
        self,
        state: RunState,
    ) -> tuple[ObjectiveReadinessProofOutcome | None, int]:
        counts: dict[tuple[str, str, str], int] = {}
        latest: dict[tuple[str, str, str], ObjectiveReadinessProofOutcome] = {}
        for outcome in state.objective_readiness_proof_outcomes[-12:]:
            if outcome.outcome not in {"failed", "partial"} or not outcome.item_id or not outcome.tool:
                continue
            key = (outcome.outcome, outcome.item_id, outcome.tool)
            counts[key] = counts.get(key, 0) + 1
            latest[key] = outcome
        repeated = [(key, count) for key, count in counts.items() if count >= 2]
        if not repeated:
            return None, 0
        key, count = sorted(repeated, key=lambda item: item[1])[-1]
        return latest[key], count

    def _objective_readiness_recovery_steps_from_state(self, state: RunState) -> list[str]:
        candidate, _attempts = self._objective_readiness_recovery_candidate(state)
        return self._objective_readiness_recovery_steps(candidate) if candidate else []

    def _objective_readiness_recovery_steps(self, outcome: ObjectiveReadinessProofOutcome | None) -> list[str]:
        if not outcome:
            return []
        label = outcome.evidence_label or outcome.item_id or "objective readiness"
        return [
            f"Review the objective-readiness proof outcomes for {outcome.item_id} via {outcome.tool}: {outcome.summary}",
            self._alternate_objective_readiness_proof_step(label, outcome.tool, outcome),
            "Update the active plan with the alternate objective-readiness proof before retrying the same tool.",
            f"Run the narrowest proof that can verify {outcome.item_id} and record the new proof outcome.",
        ]

    def _alternate_objective_readiness_proof_step(
        self,
        label: str,
        tool: str,
        outcome: ObjectiveReadinessProofOutcome,
    ) -> str:
        if tool == "run_tests":
            return "Run a narrower single test, import check, compile check, or focused shell diagnostic instead of repeating the broad test proof."
        if tool == "workspace_diff":
            return "Inspect workspace isolation metadata, source path, and active workspace path before running workspace_diff again."
        if tool == "file_read":
            return "Use the dashboard, timeline, replay, or API surface that directly contains the required proof instead of reading a broad file path again."
        if tool == "obsidian_checkpoint":
            return "Refresh the run handoff and daily/run note, then verify memory_refs and resume_prompt before retrying the checkpoint proof."
        if tool == "ask_user":
            return "Resolve the pending user decision or rewrite the readiness proof so it no longer depends on the same approval."
        if tool.startswith("browser"):
            return "Use the exact local URL plus a screenshot or page text check before repeating the same browser proof."
        if tool.startswith("desktop"):
            return "Capture the targeted window/screenshot first and ask for approval before repeating the same desktop proof."
        return f"Select a different proof path for {label} that can verify {outcome.item_id} without repeating {tool}."

    def _recovery_replan_summary(self, previous: RecoveryPlan, steps: list[str]) -> str:
        if previous.trigger == "readiness_decision_loop":
            detail = steps[1] if len(steps) > 1 else previous.summary
            return f"Replanned readiness recovery for {previous.tool}: {detail}"
        if previous.trigger == "objective_readiness_proof_loop":
            detail = steps[1] if len(steps) > 1 else previous.summary
            return f"Replanned objective-readiness recovery for {previous.tool}: {detail}"
        return f"Replanned recovery for repeated {previous.tool} failure classified as {previous.failure_kind}."

    def _recovery_steps(self, kind: str, tool: str) -> list[str]:
        common = [
            "Checkpoint the failure and reload compact run context.",
            "Inspect the smallest relevant error output or artifact.",
            "Choose a different lower-risk tool action before retrying.",
            "Run the narrowest verification that can prove recovery.",
        ]
        if kind == "timeout":
            return [
                "Reduce command scope or timeout risk before retrying.",
                "Inspect partial output and recent events for the slow step.",
                "Retry with a narrower command, increased timeout, or alternate tool.",
                "Checkpoint the result before continuing the main plan.",
            ]
        if kind == "missing_dependency":
            return [
                "Inspect project manifests and existing environment before installing anything.",
                "Ask for approval before dependency installation or global changes.",
                "Use an existing local tool or fallback path if available.",
                "Verify with the narrowest import or command check.",
            ]
        if kind == "permission":
            return [
                "Stop retrying the approval-gated or blocked action.",
                "Ask user approval or choose a lower-risk alternative.",
                "Record the decision in the handoff bundle.",
                "Resume only after approval or a safe alternate path is selected.",
            ]
        if kind == "command_failure":
            return [
                f"Read focused output from the failed {tool} command.",
                "Inspect the related file or configuration before retrying.",
                "Run a narrower diagnostic command.",
                "Update the plan with the confirmed fix or blocker.",
            ]
        return common

    async def _workstream(
        self,
        run_id: str,
        *,
        phase: str,
        role: str,
        title: str,
        summary: str,
        rationale: str = "",
        next_action: str = "",
        tool: str = "",
        result: str = "",
        severity: str = "normal",
        refs: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "phase": self._public_text(phase, 40),
            "role": self._public_role(role),
            "title": self._public_text(title, 120),
            "summary": self._public_text(summary, 700),
            "rationale": self._public_text(rationale, 500),
            "next_action": self._public_text(next_action, 500),
            "tool": self._public_text(tool, 80),
            "result": self._public_text(result, 700),
            "severity": self._public_severity(severity),
            "refs": self._public_refs(refs or {}),
        }
        message = payload["summary"] or payload["title"] or "Workstream update."
        await self._event(run_id, "workstream", message, payload)

    def _workstream_title(self, kind: str) -> str:
        titles = {
            "orient": "Context Loaded",
            "plan": "Plan Ready",
            "act": "Action Recorded",
            "verify": "Verification Recorded",
            "checkpoint": "Checkpoint Recorded",
            "decide": "Decision Recorded",
            "drift": "Drift Check",
            "health_policy": "Health Policy Hold",
            "health_verify": "Health Verification",
        }
        return titles.get(kind, "Harness Update")

    def _action_tool(self, action: dict[str, Any]) -> str:
        return str(action.get("tool") or action.get("tool_name") or "unknown_tool")

    def _action_rationale(self, action: dict[str, Any]) -> str:
        for key in (
            "thought_summary",
            "reason",
            "rationale",
            "objective_readiness_proof_action",
            "action_summary",
        ):
            value = action.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _action_refs(self, action: dict[str, Any]) -> dict[str, Any]:
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        return {
            "source": action.get("source") or "",
            "recommendation_id": action.get("recommendation_id") or "",
            "post_action_retry_id": action.get("post_action_retry_id") or "",
            "arg_keys": ", ".join(sorted(str(key) for key in args.keys())[:8]),
        }

    def _public_text(self, value: Any, limit: int) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list, tuple)):
            try:
                text = json.dumps(value, ensure_ascii=True, default=str)
            except TypeError:
                text = str(value)
        else:
            text = str(value)
        text = " ".join(text.split())
        lowered = text.lower()
        prompt_markers = (
            "compiled context:",
            "required json shape example:",
            "system prompt",
            "raw_excerpt",
            "\"messages\"",
            "hidden chain-of-thought",
        )
        if any(marker in lowered for marker in prompt_markers):
            text = "Public summary omitted raw prompt detail."
        return redact_secrets(text)[:limit]

    def _public_refs(self, refs: dict[str, Any]) -> dict[str, Any]:
        public: dict[str, Any] = {}
        for key, value in refs.items():
            if value in (None, ""):
                continue
            key_text = redact_secrets(" ".join(str(key).split()))[:80]
            if not key_text:
                continue
            public[key_text] = self._public_text(value, 240)
        return public

    def _public_role(self, role: str) -> str:
        return role if role in {"ornith", "harness", "tool", "operator", "system"} else "system"

    def _public_severity(self, severity: str) -> str:
        return severity if severity in {"normal", "watch", "blocked"} else "normal"

    async def _event(self, run_id: str, kind: str, message: str, data: dict[str, Any] | None = None) -> None:
        event = self.store.append_event(run_id, kind, message, data)
        await self.broker.publish(event)

    def _title_from_goal(self, goal: str) -> str:
        compact = " ".join(goal.split())
        return compact[:60] or "Agent run"


def re_words(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9_-]{3,}", text.lower())
