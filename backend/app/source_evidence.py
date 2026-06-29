from __future__ import annotations

from datetime import datetime, timezone

from .schemas import RunRecord, SourceEvidencePreviewEntry, SourceEvidencePreviewReport

_SOURCE_LABELS = {"web", "browser"}


def build_source_evidence_preview(run: RunRecord, *, limit: int = 20) -> SourceEvidencePreviewReport:
    state = run.state
    criteria_by_label = _criteria_by_label(run)
    required_labels = sorted(
        {
            label
            for item in state.acceptance_evidence
            for label in item.required_labels
            if label in _SOURCE_LABELS
        }
    )
    matched_labels = sorted(
        {
            label
            for item in state.acceptance_evidence
            for label in item.matched_labels
            if label in _SOURCE_LABELS
        }
    )
    entries: list[SourceEvidencePreviewEntry] = []

    for source in state.web_sources[-limit:]:
        entries.append(
            SourceEvidencePreviewEntry(
                id=source.id,
                kind="web_source",
                timestamp=source.timestamp,
                title=_single_line(source.title, 180),
                url=source.url,
                tool_kind="web_search_or_fetch",
                evidence_label="web",
                linked_criteria=criteria_by_label.get("web", [])[:6],
                excerpt=_single_line(source.excerpt, 320),
                summary=_single_line(source.excerpt, 220),
                citation=source.citation,
            )
        )

    for snapshot in state.desktop_snapshots[-limit:]:
        kind = "browser_snapshot" if _looks_like_browser_snapshot(snapshot.title, snapshot.id) else "desktop_snapshot"
        tool_kind = "browser_screenshot" if kind == "browser_snapshot" else "desktop_screenshot"
        entries.append(
            SourceEvidencePreviewEntry(
                id=snapshot.id,
                kind=kind,  # type: ignore[arg-type]
                timestamp=snapshot.timestamp,
                title=_single_line(snapshot.title, 180),
                path=snapshot.path,
                tool_kind=tool_kind,
                evidence_label="browser",
                linked_criteria=criteria_by_label.get("browser", [])[:6],
                summary=_single_line(snapshot.summary, 260),
            )
        )

    entries = sorted(entries, key=lambda item: (item.timestamp, item.id), reverse=True)
    bounded_limit = max(1, min(limit, 100))
    bounded = entries[:bounded_limit]
    web_count = sum(1 for item in entries if item.kind == "web_source")
    browser_count = sum(1 for item in entries if item.kind == "browser_snapshot")
    desktop_count = sum(1 for item in entries if item.kind == "desktop_snapshot")
    linked_criteria = sorted({criterion for entry in entries for criterion in entry.linked_criteria})
    missing_labels = [label for label in required_labels if label not in matched_labels]
    latest = entries[0] if entries else None

    if not entries:
        summary = "No web or browser source evidence has been captured for this run."
        recommended_action = "Use web_search, web_fetch, browser_screenshot, or desktop_screenshot when a criterion needs source-visible proof."
        latest_evidence = ""
    else:
        summary = (
            f"{len(entries)} source evidence item(s): {web_count} web source(s), "
            f"{browser_count} browser screenshot(s), {desktop_count} desktop screenshot(s)."
        )
        if missing_labels:
            recommended_action = "Capture missing source evidence labels before claiming related criteria: " + ", ".join(missing_labels)
        elif linked_criteria:
            recommended_action = "Use these compact previews as source evidence in handoff, replay, and operator review."
        else:
            recommended_action = "Review previews and link source-visible proof to acceptance criteria when relevant."
        latest_evidence = f"{latest.kind}:{latest.title or latest.url or latest.path}" if latest else ""

    return SourceEvidencePreviewReport(
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        total_count=len(entries),
        web_source_count=web_count,
        browser_snapshot_count=browser_count,
        desktop_snapshot_count=desktop_count,
        linked_criterion_count=len(linked_criteria),
        required_label_count=len(required_labels),
        matched_label_count=len(matched_labels),
        missing_labels=missing_labels,
        latest_evidence=_single_line(latest_evidence, 260),
        summary=summary,
        recommended_action=recommended_action,
        entries=bounded,
    )


def _criteria_by_label(run: RunRecord) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"web": [], "browser": []}
    for item in run.state.acceptance_evidence:
        labels = set(item.required_labels) | set(item.matched_labels)
        for label in labels & _SOURCE_LABELS:
            if item.criterion and item.criterion not in result[label]:
                result[label].append(item.criterion)
    return result


def _looks_like_browser_snapshot(title: str, snapshot_id: str) -> bool:
    compact = f"{title} {snapshot_id}".lower()
    return "browser" in compact


def _single_line(value: str, limit: int) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."
