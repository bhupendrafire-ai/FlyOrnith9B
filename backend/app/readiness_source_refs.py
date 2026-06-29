from __future__ import annotations

from typing import Any

from .readiness_completion import SOURCE_VISIBLE_LABELS
from .persistence import utc_now
from .schemas import (
    ReadinessCompletionReport,
    ReadinessProofHistoryReport,
    ReadinessProofSourceRef,
    ReadinessSourceRefLabelPreview,
    ReadinessSourceRefPreviewReport,
    RunRecord,
    SourceEvidencePreviewEntry,
    SourceEvidencePreviewReport,
)


def build_readiness_source_ref_preview(
    run: RunRecord,
    source_evidence: SourceEvidencePreviewReport,
    readiness_proof_history: ReadinessProofHistoryReport,
    readiness_completion: ReadinessCompletionReport,
    *,
    limit: int = 12,
) -> ReadinessSourceRefPreviewReport:
    bounded_limit = max(1, min(limit, 50))
    acceptance_required_labels = _source_visible_acceptance_labels(run, "required_labels")
    acceptance_matched_labels = _source_visible_acceptance_labels(run, "matched_labels")
    source_visible_labels = sorted(
        set(acceptance_required_labels)
        | set(acceptance_matched_labels)
        | set(readiness_completion.source_visible_missing_ref_labels)
    )
    source_entries_by_label: dict[str, list[SourceEvidencePreviewEntry]] = {}
    for entry in source_evidence.entries:
        label = str(entry.evidence_label or "")
        if label:
            source_entries_by_label.setdefault(label, []).append(entry)
    proof_refs = _compact_proof_refs(readiness_proof_history, limit=bounded_limit)
    proof_refs_by_label: dict[str, list[ReadinessProofSourceRef]] = {}
    for ref in proof_refs:
        label = str(ref.evidence_label or "")
        if label:
            proof_refs_by_label.setdefault(label, []).append(ref)
    source_evidence_labels = sorted(source_entries_by_label)
    proof_ref_labels = sorted(proof_refs_by_label)
    missing_source_evidence_labels = [label for label in source_visible_labels if label not in source_entries_by_label]
    missing_proof_ref_labels = [label for label in source_visible_labels if label not in proof_refs_by_label]
    all_labels = sorted(set(source_visible_labels) | set(source_evidence_labels) | set(proof_ref_labels))

    label_reports = [
        _label_preview(
            label,
            source_entries_by_label.get(label, []),
            proof_refs_by_label.get(label, []),
            source_visible_labels,
            acceptance_required_labels,
            acceptance_matched_labels,
            missing_source_evidence_labels,
            missing_proof_ref_labels,
        )
        for label in all_labels
    ]
    status, summary, recommended_action = _status_summary(
        source_visible_labels,
        missing_source_evidence_labels,
        missing_proof_ref_labels,
    )
    return ReadinessSourceRefPreviewReport(
        run_id=run.id,
        generated_at=utc_now(),
        status=status,  # type: ignore[arg-type]
        summary=summary,
        recommended_action=recommended_action,
        readiness_completion_status=readiness_completion.status,
        readiness_proof_history_status=readiness_proof_history.status,
        source_visible_labels=source_visible_labels,
        acceptance_required_labels=acceptance_required_labels,
        acceptance_matched_labels=acceptance_matched_labels,
        source_evidence_labels=source_evidence_labels,
        proof_ref_labels=proof_ref_labels,
        missing_source_evidence_labels=missing_source_evidence_labels,
        missing_proof_ref_labels=missing_proof_ref_labels,
        source_evidence_entry_count=source_evidence.total_count,
        proof_ref_count=len(proof_refs),
        labels=label_reports,
        source_evidence_entries=source_evidence.entries[:bounded_limit],
        proof_refs=proof_refs[:bounded_limit],
    )


def _source_visible_acceptance_labels(run: RunRecord, field: str) -> list[str]:
    labels: set[str] = set()
    for item in run.state.acceptance_evidence:
        for label in getattr(item, field, []) or []:
            compact = str(label or "").strip()
            if compact in SOURCE_VISIBLE_LABELS:
                labels.add(compact)
    return sorted(labels)


def _compact_proof_refs(
    readiness_proof_history: ReadinessProofHistoryReport,
    *,
    limit: int,
) -> list[ReadinessProofSourceRef]:
    refs: list[ReadinessProofSourceRef] = []
    seen: set[str] = set()
    for entry in readiness_proof_history.entries:
        for ref in entry.source_refs:
            key = f"{ref.kind}:{ref.id or ref.target}:{ref.evidence_label}"
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
            if len(refs) >= limit:
                return refs
    return refs


def _label_preview(
    label: str,
    source_entries: list[SourceEvidencePreviewEntry],
    refs: list[ReadinessProofSourceRef],
    source_visible_labels: list[str],
    acceptance_required_labels: list[str],
    acceptance_matched_labels: list[str],
    missing_source_evidence_labels: list[str],
    missing_proof_ref_labels: list[str],
) -> ReadinessSourceRefLabelPreview:
    linked_criteria = sorted(
        {
            str(criterion)
            for entry in source_entries
            for criterion in entry.linked_criteria
            if str(criterion).strip()
        }
    )
    return ReadinessSourceRefLabelPreview(
        label=label,
        source_visible=label in source_visible_labels,
        acceptance_required=label in acceptance_required_labels,
        acceptance_matched=label in acceptance_matched_labels,
        present_in_source_evidence=bool(source_entries),
        present_in_proof_history=bool(refs),
        missing_from_source_evidence=label in missing_source_evidence_labels,
        missing_from_proof_history=label in missing_proof_ref_labels,
        source_evidence_count=len(source_entries),
        proof_ref_count=len(refs),
        linked_criteria=linked_criteria[:4],
        source_evidence_titles=[
            _compact_text(entry.title or entry.url or entry.path, 140)
            for entry in source_entries[:4]
        ],
        proof_ref_titles=[
            _compact_text(ref.title or ref.target or ref.id, 140)
            for ref in refs[:4]
        ],
    )


def _status_summary(
    source_visible_labels: list[str],
    missing_source_evidence_labels: list[str],
    missing_proof_ref_labels: list[str],
) -> tuple[str, str, str]:
    if not source_visible_labels:
        return (
            "not_applicable",
            "No source-visible readiness labels require proof refs for this run.",
            "Use source-ref preview when readiness acceptance evidence requires web or browser proof.",
        )
    if missing_proof_ref_labels:
        summary = "Readiness proof history is missing source refs for: " + ", ".join(missing_proof_ref_labels)
        if missing_source_evidence_labels:
            return (
                "missing_proof_refs",
                summary,
                "Capture missing source evidence, then refresh readiness source refs: "
                + ", ".join(missing_source_evidence_labels),
            )
        return (
            "missing_proof_refs",
            summary,
            "Dispatch the readiness source-ref refresh to rebuild proof history and handoff refs.",
        )
    if missing_source_evidence_labels:
        return (
            "missing_source_evidence",
            "Source-visible readiness proof is missing compact source evidence for: "
            + ", ".join(missing_source_evidence_labels),
            "Capture the missing source evidence before claiming readiness.",
        )
    return (
        "ready",
        "Readiness proof history carries source refs for required source-visible labels: "
        + ", ".join(source_visible_labels),
        "Use these compact refs in handoff/replay instead of raw page or screenshot logs.",
    )


def _compact_text(value: Any, limit: int) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."
