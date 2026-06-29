from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .acceptance import infer_required_labels
from .repo_map import build_repo_map
from .schemas import (
    AcceptanceCriterionEvidence,
    ContextBudget,
    HandoffBundle,
    ModelProfileAdaptationProposal,
    ModelProfileAdaptationReview,
    RunLease,
    RunRecord,
    RunState,
    TaskNode,
    WorkspaceIsolation,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_run_id() -> str:
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class RunStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    action_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS model_profile_adaptation_reviews (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reviewer_note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_run(
        self,
        goal: str,
        title: str,
        workspace_path: str,
        acceptance_criteria: list[str],
        *,
        tool_profile: str = "balanced",
        approval_mode: str = "balanced",
        web_enabled: bool = True,
        browser_enabled: bool = True,
        desktop_enabled: bool = True,
        wall_clock_limit_minutes: int = 90,
        checkpoint_every_steps: int = 3,
        context_target_tokens: int = 24000,
        run_id: str | None = None,
        workspace_isolation: WorkspaceIsolation | None = None,
    ) -> RunRecord:
        run_id = run_id or make_run_id()
        now = utc_now()
        workspace_isolation = workspace_isolation or WorkspaceIsolation(
            enabled=False,
            mode="source",
            source_path=workspace_path,
            workspace_path=workspace_path,
            created_at=now,
            summary="Workspace isolation not configured for this run.",
        )
        repo_map = build_repo_map(Path(workspace_path))
        initial_task = TaskNode(
            id="task-orient",
            title="Orient from Obsidian, repo map, and durable run state.",
            status="pending",
            kind="investigate",
        )
        acceptance_evidence = [
            AcceptanceCriterionEvidence(
                id=f"criterion-{index + 1}",
                criterion=criterion,
                status="open",
                required_labels=infer_required_labels(criterion),
                notes="Awaiting verification evidence.",
            )
            for index, criterion in enumerate(acceptance_criteria)
        ]
        state = RunState(
            goal=goal,
            acceptance_criteria=acceptance_criteria,
            acceptance_evidence=acceptance_evidence,
            next_step="Consult Obsidian memory before inspecting code.",
            tool_profile=tool_profile,
            approval_mode=approval_mode,
            web_enabled=web_enabled,
            browser_enabled=browser_enabled,
            desktop_enabled=desktop_enabled,
            wall_clock_limit_minutes=wall_clock_limit_minutes,
            checkpoint_every_steps=checkpoint_every_steps,
            context_budget=ContextBudget(target_tokens=context_target_tokens),
            repo_map=repo_map,
            workspace_isolation=workspace_isolation,
            task_graph=[initial_task],
            current_task_id=initial_task.id,
            handoff_summary=HandoffBundle(
                original_goal=goal,
                current_objective=goal,
                next_action="Consult Obsidian memory before inspecting code.",
                current_task_id=initial_task.id,
                task_graph=[initial_task],
                repo_map_summary=repo_map.summary,
                workspace_summary=workspace_isolation.summary,
                acceptance_criteria=acceptance_criteria,
                acceptance_evidence=acceptance_evidence,
                resume_prompt=f"Resume run {run_id}: consult Obsidian first, then continue toward: {goal}",
            ),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, title, goal, status, workspace_path, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, title, goal, "queued", workspace_path, state.model_dump_json(), now, now),
            )
        return self.get_run(run_id)

    def list_runs(self) -> list[RunRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM runs ORDER BY updated_at DESC").fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_run(self, run_id: str) -> RunRecord:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return self._row_to_run(row)

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        state: RunState | None = None,
        workspace_path: str | None = None,
    ) -> RunRecord:
        current = self.get_run(run_id)
        next_status = status or current.status
        next_state = state or current.state
        next_workspace = workspace_path or current.workspace_path
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                   SET status = ?, state_json = ?, workspace_path = ?, updated_at = ?
                 WHERE id = ?
                """,
                (next_status, next_state.model_dump_json(), next_workspace, now, run_id),
            )
        return self.get_run(run_id)

    def update_run_lease(self, run_id: str, lease: RunLease) -> RunRecord:
        now = utc_now()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            state = RunState.model_validate(_json_load(row["state_json"], {}))
            state.run_lease = lease
            conn.execute(
                """
                UPDATE runs
                   SET state_json = ?, updated_at = ?
                 WHERE id = ?
                """,
                (state.model_dump_json(), now, run_id),
            )
        return self.get_run(run_id)

    def append_event(
        self,
        run_id: str,
        kind: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (run_id, timestamp, kind, message, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, now, kind, message, _json_dump(data or {})),
            )
            event_id = int(cursor.lastrowid)
        return {
            "id": event_id,
            "run_id": run_id,
            "timestamp": now,
            "kind": kind,
            "message": message,
            "data": data or {},
        }

    def list_events(self, run_id: str, limit: int = 250) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                 WHERE run_id = ?
                 ORDER BY id DESC
                 LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        events = [self._row_to_event(row) for row in rows]
        return list(reversed(events))

    def create_approval(
        self,
        run_id: str,
        action_kind: str,
        payload: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO approvals (run_id, status, action_kind, payload_json, reason, created_at)
                VALUES (?, 'pending', ?, ?, ?, ?)
                """,
                (run_id, action_kind, _json_dump(payload), reason, now),
            )
            approval_id = int(cursor.lastrowid)
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(str(approval_id))
        return self._row_to_approval(row)

    def list_approvals(self, run_id: str, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM approvals WHERE run_id = ?"
        params: list[Any] = [run_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_approval(row) for row in rows]

    def resolve_approval(self, approval_id: int, status: str) -> dict[str, Any]:
        if status not in {"approved", "rejected"}:
            raise ValueError("approval status must be approved or rejected")
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
                (status, utc_now(), approval_id),
            )
        return self.get_approval(approval_id)

    def create_model_adaptation_review(
        self,
        proposal: ModelProfileAdaptationProposal,
        decision: str,
        reviewer_note: str = "",
    ) -> ModelProfileAdaptationReview:
        if decision not in {"accepted", "rejected"}:
            raise ValueError("adaptation review decision must be accepted or rejected")
        review_id = f"adapt-review-{uuid4().hex[:8]}"
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_profile_adaptation_reviews
                    (id, profile_id, proposal_json, decision, reviewer_note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    proposal.profile_id,
                    proposal.model_dump_json(),
                    decision,
                    reviewer_note[:1000],
                    now,
                ),
            )
        return self.get_model_adaptation_review(review_id)

    def get_model_adaptation_review(self, review_id: str) -> ModelProfileAdaptationReview:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM model_profile_adaptation_reviews WHERE id = ?", (review_id,)).fetchone()
        if row is None:
            raise KeyError(review_id)
        return self._row_to_model_adaptation_review(row)

    def list_model_adaptation_reviews(self, limit: int = 50) -> list[ModelProfileAdaptationReview]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM model_profile_adaptation_reviews
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_model_adaptation_review(row) for row in rows]

    def _row_to_run(self, row: sqlite3.Row) -> RunRecord:
        state = RunState.model_validate(_json_load(row["state_json"], {}))
        return RunRecord(
            id=row["id"],
            title=row["title"],
            goal=row["goal"],
            status=row["status"],
            workspace_path=row["workspace_path"],
            state=state,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "timestamp": row["timestamp"],
            "kind": row["kind"],
            "message": row["message"],
            "data": _json_load(row["data_json"], {}),
        }

    def _row_to_approval(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "status": row["status"],
            "action_kind": row["action_kind"],
            "payload": _json_load(row["payload_json"], {}),
            "reason": row["reason"],
            "created_at": row["created_at"],
            "resolved_at": row["resolved_at"],
        }

    def _row_to_model_adaptation_review(self, row: sqlite3.Row) -> ModelProfileAdaptationReview:
        return ModelProfileAdaptationReview(
            id=row["id"],
            profile_id=row["profile_id"],
            proposal=ModelProfileAdaptationProposal.model_validate(_json_load(row["proposal_json"], {})),
            decision=row["decision"],
            reviewer_note=row["reviewer_note"],
            created_at=row["created_at"],
        )
