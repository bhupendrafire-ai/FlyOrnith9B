from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .schemas import RunRecord, RunState


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
]


@dataclass(frozen=True)
class MemoryHit:
    path: str
    title: str
    excerpt: str


@dataclass(frozen=True)
class MemoryContext:
    hits: list[MemoryHit]
    warnings: list[str]

    def as_prompt_text(self) -> str:
        if not self.hits:
            return "No matching Obsidian context found."
        chunks = []
        for hit in self.hits:
            chunks.append(f"Source: {hit.path}\nTitle: {hit.title}\nExcerpt:\n{hit.excerpt}")
        return "\n\n---\n\n".join(chunks)


class ObsidianMemory:
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path

    def consult(self, goal: str, run_id: str | None = None) -> MemoryContext:
        warnings: list[str] = []
        if not self.vault_path.exists():
            return MemoryContext([], [f"Vault not found: {self.vault_path}"])

        candidate_paths = self._candidate_paths(run_id)
        terms = self._terms(goal)
        scored: list[tuple[int, Path, str]] = []

        for path in candidate_paths:
            text = self._read_text(path, limit=16000)
            if not text:
                continue
            score = self._score(path, text, terms)
            if score > 0:
                scored.append((score, path, text))

        scored.sort(key=lambda item: item[0], reverse=True)
        hits = [self._to_hit(path, text, terms) for _, path, text in scored[:8]]
        if not hits:
            warnings.append("No highly relevant vault notes were found; continuing with general workflow notes.")
        return MemoryContext(hits, warnings)

    def append_run_started(self, run: RunRecord) -> None:
        started = datetime.now().isoformat(timespec="seconds")
        section = (
            f"\n\n## Agent Run: {self._sanitize_title(run.title)}\n"
            f"- Started: {started}\n"
            f"- Workspace: {run.workspace_path}\n"
            f"- Goal: {self._sanitize_text(run.goal)}\n"
            "- Status: running\n"
            "- Current step: Consult Obsidian memory before code inspection.\n"
            "- Key findings: []\n"
            "- Files touched: []\n"
            "- Commands run: []\n"
            "- Next action: Plan first loop step.\n"
        )
        self._append_daily(section)

        run_note = (
            f"# Agent Run: {self._sanitize_title(run.title)}\n\n"
            f"- Run ID: `{run.id}`\n"
            f"- Started: {started}\n"
            f"- Workspace: `{run.workspace_path}`\n"
            f"- Goal: {self._sanitize_text(run.goal)}\n"
            "- Status: running\n\n"
            "## Checkpoints\n"
        )
        self._write_run_note(run.id, run_note, mode="w")

    def append_checkpoint(self, run: RunRecord, state: RunState, status: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        section = (
            f"\n\n### Checkpoint: {now}\n"
            f"- Status: {status}\n"
            f"- Active goal: {self._sanitize_text(state.goal)}\n"
            f"- Current step: {self._sanitize_text(state.next_step or 'Not set')}\n"
            f"- Key findings: {self._list_line(state.facts_learned[-5:])}\n"
            f"- Files touched: {self._list_line(state.files_touched[-10:])}\n"
            f"- Commands run: {self._list_line(state.commands_run[-10:])}\n"
            f"- Blockers: {self._list_line(state.blockers[-5:])}\n"
            f"- Next action: {self._sanitize_text(state.next_step or 'Decide next action')}\n"
            f"- Latest summary: {self._sanitize_text(state.latest_summary)}\n"
            f"- Report integrity refresh: {self._report_integrity_refresh_line(state)}\n"
            f"- Checkpoint-quality resume repair: {self._checkpoint_quality_resume_line(state)}\n"
            f"- Failure context: {self._failure_context_line(state)}\n"
            f"- Task transitions: {self._task_transition_line(state)}\n"
            f"- Model guards: {self._model_guard_line(state)}\n"
            f"- Edit evidence: {self._edit_evidence_line(state)}\n"
            f"- Self scaffold: {self._self_scaffold_line(state)}\n"
            f"- Resume prompt: {self._sanitize_text(state.handoff_summary.resume_prompt)}\n"
        )
        self._write_run_note(run.id, section, mode="a")

        daily_section = (
            f"\n\n## Agent Run: {self._sanitize_title(run.title)}\n"
            f"- Started: {run.created_at}\n"
            f"- Workspace: {run.workspace_path}\n"
            f"- Goal: {self._sanitize_text(run.goal)}\n"
            f"- Status: {status}\n"
            f"- Active goal: {self._sanitize_text(state.goal)}\n"
            f"- Current step: {self._sanitize_text(state.next_step or 'Not set')}\n"
            f"- Key findings: {self._list_line(state.facts_learned[-3:])}\n"
            f"- Files touched: {self._list_line(state.files_touched[-8:])}\n"
            f"- Commands run: {self._list_line(state.commands_run[-8:])}\n"
            f"- Next action: {self._sanitize_text(state.next_step or 'Decide next action')}\n"
            f"- Report integrity refresh: {self._report_integrity_refresh_line(state)}\n"
            f"- Checkpoint-quality resume repair: {self._checkpoint_quality_resume_line(state)}\n"
            f"- Failure context: {self._failure_context_line(state)}\n"
            f"- Task transitions: {self._task_transition_line(state)}\n"
            f"- Model guards: {self._model_guard_line(state)}\n"
            f"- Edit evidence: {self._edit_evidence_line(state)}\n"
            f"- Self scaffold: {self._self_scaffold_line(state)}\n"
        )
        self._append_daily(daily_section)

    def append_final(self, run: RunRecord, state: RunState) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        section = (
            f"\n\n## Final Summary: {now}\n"
            f"- Status: {run.status}\n"
            f"- Active goal: {self._sanitize_text(state.goal)}\n"
            f"- Completed steps: {self._list_line(state.completed_steps)}\n"
            f"- Files touched: {self._list_line(state.files_touched)}\n"
            f"- Commands run: {self._list_line(state.commands_run)}\n"
            f"- Blockers: {self._list_line(state.blockers)}\n"
            f"- Summary: {self._sanitize_text(state.latest_summary)}\n"
            f"- Report integrity refresh: {self._report_integrity_refresh_line(state)}\n"
            f"- Checkpoint-quality resume repair: {self._checkpoint_quality_resume_line(state)}\n"
            f"- Failure context: {self._failure_context_line(state)}\n"
            f"- Task transitions: {self._task_transition_line(state)}\n"
            f"- Model guards: {self._model_guard_line(state)}\n"
            f"- Edit evidence: {self._edit_evidence_line(state)}\n"
            f"- Self scaffold: {self._self_scaffold_line(state)}\n"
            f"- Resume prompt: {self._sanitize_text(state.handoff_summary.resume_prompt)}\n"
        )
        self._write_run_note(run.id, section, mode="a")

    def read_run_note(self, run_id: str, limit: int = 20000) -> str:
        return self._read_text(self._run_note_path(run_id), limit=limit)

    def _candidate_paths(self, run_id: str | None) -> list[Path]:
        paths: list[Path] = []
        priority = [
            self.vault_path / "20-Areas" / "Coding Projects.md",
            self.vault_path / "30-Resources" / "Agentic Coding Workflow.md",
            self.vault_path / "Daily" / f"{datetime.now():%Y-%m-%d}.md",
        ]
        if run_id:
            priority.append(self._run_note_path(run_id))

        for path in priority:
            if path.exists():
                paths.append(path)

        for folder_name in ("30-Resources", "20-Areas", "Daily", "Agent Runs"):
            folder = self.vault_path / folder_name
            if not folder.exists():
                continue
            candidates = sorted(folder.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)
            for path in candidates[:25]:
                if path not in paths:
                    paths.append(path)
        return paths[:90]

    def _terms(self, goal: str) -> list[str]:
        words = re.findall(r"[A-Za-z0-9_-]{4,}", goal.lower())
        base = [
            "agent",
            "agentic",
            "coding",
            "local-ai",
            "ornith",
            "obsidian",
            "checkpoint",
            "second-brain",
            "workflow",
        ]
        return sorted(set(base + words))

    def _score(self, path: Path, text: str, terms: list[str]) -> int:
        lower = text.lower()
        path_lower = str(path).lower()
        score = 0
        for term in terms:
            score += lower.count(term)
            if term in path_lower:
                score += 5
        if "coding projects.md" in path_lower or "agentic coding workflow.md" in path_lower:
            score += 20
        return score

    def _to_hit(self, path: Path, text: str, terms: list[str]) -> MemoryHit:
        title = path.stem
        lower = text.lower()
        first_index = min((lower.find(term) for term in terms if lower.find(term) >= 0), default=0)
        start = max(0, first_index - 500)
        excerpt = text[start : start + 1800].strip()
        return MemoryHit(path=str(path), title=title, excerpt=self._sanitize_text(excerpt))

    def _append_daily(self, section: str) -> None:
        daily = self.vault_path / "Daily" / f"{datetime.now():%Y-%m-%d}.md"
        daily.parent.mkdir(parents=True, exist_ok=True)
        if not daily.exists():
            daily.write_text(f"# Daily Log - {datetime.now():%A %d %B %Y}\n", encoding="utf-8")
        with daily.open("a", encoding="utf-8") as handle:
            handle.write(self._sanitize_text(section))

    def _write_run_note(self, run_id: str, content: str, mode: str) -> None:
        path = self._run_note_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(self._sanitize_text(content))

    def _run_note_path(self, run_id: str) -> Path:
        return self.vault_path / "Agent Runs" / f"{run_id}.md"

    def _read_text(self, path: Path, limit: int) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
        except OSError:
            return ""

    def _sanitize_title(self, value: str) -> str:
        return self._sanitize_text(value).replace("\n", " ")[:120]

    def _sanitize_text(self, value: str) -> str:
        sanitized = value or ""
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub(lambda match: f"{match.group(1) if match.groups() else 'secret'}=[REDACTED]", sanitized)
        return sanitized

    def _report_integrity_refresh_line(self, state: RunState) -> str:
        refreshes = state.report_integrity_refreshes or state.handoff_summary.report_integrity_refreshes
        if not refreshes:
            return "[]"
        latest = refreshes[0]
        transition = f"{latest.previous_report_status or 'unknown'}->{latest.report_status or 'unknown'}"
        preflight = (
            f" preflight=#{latest.preflight_event_id}:{latest.preflight_event_kind}"
            if latest.preflight_event_id
            else ""
        )
        reason = self._select_report_integrity_refresh_reason(latest.reasons)
        reason_text = f"; reason={reason}" if reason else ""
        line = f"#{latest.event_id} {transition} reasons={latest.reason_count}{preflight}{reason_text}"
        return self._sanitize_text(line).replace("\n", " ")[:600]

    def _checkpoint_quality_resume_line(self, state: RunState) -> str:
        report = state.checkpoint_quality_resumes
        if not report.run_id:
            report = state.handoff_summary.checkpoint_quality_resumes
        if not report.run_id or report.status == "none":
            return "[]"
        latest = report.latest
        repair = (
            f" repair=#{latest.repair_completed_event_id}:{latest.repair_reason}:{latest.repair_ui_target}"
            if latest.repair_completed_event_id
            else " repair=none"
        )
        if latest.resume_event_id:
            accepted = "accepted" if latest.resume_accepted else "blocked"
            policy = latest.resume_policy_action or "unknown"
            resume = f" resume=#{latest.resume_event_id}:{policy}:{accepted}"
        else:
            resume = " resume=awaiting"
        checkpoint = f" checkpoint={latest.checkpoint_quality_status or 'unknown'}:{latest.checkpoint_quality_ready}"
        line = (
            f"{report.status} repairs={report.repair_count} resumed={report.resumed_after_repair_count} "
            f"blocked={report.blocked_after_repair_count} awaiting={report.awaiting_resume_count}"
            f"{repair}{resume}{checkpoint}"
        )
        return self._sanitize_text(line).replace("\n", " ")[:600]

    def _task_transition_line(self, state: RunState) -> str:
        ledger = list(state.action_context.task_transition_ledger or [])
        if not ledger:
            ledger = list(state.handoff_summary.action_context.task_transition_ledger or [])
        if not ledger and state.task_graph:
            ledger = self._task_transition_line_from_graph(state)
        return self._list_line(ledger[-6:])

    def _model_guard_line(self, state: RunState) -> str:
        ledger = list(state.action_context.model_guard_ledger or [])
        if not ledger:
            ledger = list(state.handoff_summary.action_context.model_guard_ledger or [])
        return self._list_line(ledger[-6:])

    def _edit_evidence_line(self, state: RunState) -> str:
        ledger = list(state.action_context.edit_evidence_ledger or [])
        if not ledger:
            ledger = list(state.handoff_summary.action_context.edit_evidence_ledger or [])
        return self._list_line(ledger[-6:])

    def _self_scaffold_line(self, state: RunState) -> str:
        report = state.self_scaffold
        if not report.generated_at:
            report = state.handoff_summary.self_scaffold
        if not report.generated_at or not report.changes:
            return "[]"
        items = [
            f"{change.kind}:{change.status}:{change.summary}; reverse={change.reverse_hint}"
            for change in report.changes[-4:]
        ]
        review = f" reviewed={report.reviewed_change_count}/{report.review_count}"
        if report.latest_review_event_id:
            review += f" review_event=#{report.latest_review_event_id}"
        prefix = f"{report.status} changes={report.change_count} reversible={report.reversible_count}{review}"
        return self._sanitize_text(f"{prefix} {self._list_line(items)}").replace("\n", " ")[:900]
    def _task_transition_line_from_graph(self, state: RunState) -> list[str]:
        ledger: list[str] = []
        current_index = -1
        for index, task in enumerate(state.task_graph):
            if task.id == state.current_task_id:
                current_index = index
            if task.status in {"completed", "failed", "blocked", "skipped"}:
                evidence = task.evidence[-1] if task.evidence else task.notes
                detail = f" evidence={evidence}" if evidence else ""
                ledger.append(f"{task.status}:{task.id}:{task.title}{detail}")
        current = state.task_graph[current_index] if current_index >= 0 else None
        if current:
            ledger.append(f"current:{current.status}:{current.id}:{current.title}")
            next_task = next(
                (
                    task
                    for task in state.task_graph[current_index + 1 :]
                    if task.status in {"pending", "in_progress"}
                ),
                None,
            )
        else:
            next_task = next((task for task in state.task_graph if task.status in {"pending", "in_progress"}), None)
        if next_task and (not current or next_task.id != current.id):
            ledger.append(f"next:{next_task.status}:{next_task.id}:{next_task.title}")
        return ledger[-6:]

    def _failure_context_line(self, state: RunState) -> str:
        if not state.failure_records:
            return "[]"
        latest = state.failure_records[-1]
        parts = [f"latest={latest.kind}:{latest.tool}:x{latest.count}"]
        if latest.command:
            parts.append(f"cmd={latest.command}")
        if latest.target:
            parts.append(f"target={latest.target}")
        if latest.returncode is not None:
            parts.append(f"rc={latest.returncode}")
        if latest.recovery_hint:
            parts.append(f"hint={latest.recovery_hint}")
        if latest.evidence_excerpt:
            parts.append(f"evidence={latest.evidence_excerpt}")
        return self._sanitize_text(" ".join(parts)).replace("\n", " ")[:600]

    def _select_report_integrity_refresh_reason(self, reasons: list[str]) -> str:
        if not reasons:
            return ""
        preferred_markers = (
            "handoff.approval_reviews",
            "handoff.operator_dispatches",
            "handoff.current_objective",
            "handoff.next_action",
            "handoff.approvals",
            "promotion",
        )
        selected = next(
            (reason for reason in reasons if any(marker in reason for marker in preferred_markers)),
            reasons[0],
        )
        return self._sanitize_text(selected).replace("\n", " ")[:320]

    def _list_line(self, values: list[str]) -> str:
        if not values:
            return "[]"
        cleaned = [self._sanitize_text(str(value)).replace("\n", " ")[:180] for value in values]
        return "[" + "; ".join(cleaned) + "]"
