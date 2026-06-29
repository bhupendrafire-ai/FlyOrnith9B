from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .schemas import PromotionVerificationAttemptRecord, PromotionVerificationReport, RunRecord


FILE_LINE_PATTERNS = (
    re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)'),
    re.compile(r'(?P<file>[^\s:()]+\.(?:py|ts|tsx|js|jsx))\((?P<line>\d+),(?P<column>\d+)\)\s*:\s*(?P<message>error\s+[^\n]+)', re.IGNORECASE),
    re.compile(r'(?P<file>[^\s:()]+\.(?:py|ts|tsx|js|jsx)):(?P<line>\d+):(?:(?P<column>\d+):)?\s*(?P<message>[^\n]+)', re.IGNORECASE),
)
ERROR_LINE_PATTERN = re.compile(
    r'(?P<kind>SyntaxError|IndentationError|TabError|ImportError|ModuleNotFoundError|NameError|TypeError|AssertionError|Error|Failed):\s*(?P<message>[^\n]+)',
    re.IGNORECASE,
)
MISSING_FILE_PATTERNS = (
    re.compile(r"No such file or directory: ['\"](?P<file>[^'\"]+)['\"]", re.IGNORECASE),
    re.compile(r"can't open file ['\"](?P<file>[^'\"]+)['\"]", re.IGNORECASE),
    re.compile(r"Cannot find module ['\"](?P<file>[^'\"]+)['\"]", re.IGNORECASE),
)
NPM_MISSING_SCRIPT = re.compile(r"Missing script:\s*['\"]?(?P<script>[^'\"\n]+)", re.IGNORECASE)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_promotion_verification_report(
    run: RunRecord,
    events: list[dict[str, Any]],
    *,
    preferred_command: str,
    alternate_command: str = "",
) -> PromotionVerificationReport:
    attempts = [_attempt_from_event(event, preferred_command, alternate_command) for event in events]
    attempts = [attempt for attempt in attempts if attempt.command][-20:]
    latest = attempts[-1] if attempts else PromotionVerificationAttemptRecord()
    failed = [attempt for attempt in attempts if not attempt.ok]
    succeeded = [attempt for attempt in attempts if attempt.ok]
    latest_failed = next((attempt for attempt in reversed(attempts) if not attempt.ok), None)
    latest_failed_command = latest_failed.command if latest_failed else ""
    repeated_failure_count = (
        sum(1 for attempt in attempts if attempt.command == latest_failed_command and not attempt.ok)
        if latest_failed_command
        else 0
    )
    repair_attempts = [attempt for attempt in attempts if attempt.repair_hint]

    next_command = preferred_command
    should_use_alternate = False
    status = "none"
    if latest.command:
        if latest.ok:
            status = "ready"
        elif alternate_command and latest.command != alternate_command:
            next_command = alternate_command
            should_use_alternate = True
            status = "repeated_failure" if repeated_failure_count > 1 else "needs_retry"
        else:
            status = "repeated_failure"

    latest_repair = latest_failed or latest
    summary = _summary(status, attempts, latest_failed_command, next_command, latest_repair)
    return PromotionVerificationReport(
        run_id=run.id,
        generated_at=utc_stamp(),
        status=status,  # type: ignore[arg-type]
        attempt_count=len(attempts),
        failed_count=len(failed),
        success_count=len(succeeded),
        repeated_failure_count=repeated_failure_count,
        repair_hint_count=len(repair_attempts),
        latest_attempt=latest,
        latest_failed_command=latest_failed_command,
        latest_failure_kind=latest_repair.failure_kind,
        latest_suspected_file=latest_repair.suspected_file,
        latest_repair_hint=latest_repair.repair_hint,
        next_command=next_command,
        should_use_alternate=should_use_alternate,
        failure_kinds=_unique([attempt.failure_kind for attempt in attempts if attempt.failure_kind]),
        summary=summary,
        recommended_action=_recommended_action(status, next_command, latest_repair),
        attempts=attempts,
    )


def _attempt_from_event(
    event: dict[str, Any],
    preferred_command: str,
    alternate_command: str,
) -> PromotionVerificationAttemptRecord:
    if event.get("kind") != "promotion_audit_verification":
        return PromotionVerificationAttemptRecord()
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    audit = data.get("promotion_audit") if isinstance(data.get("promotion_audit"), dict) else {}
    command = str(data.get("command") or "")
    tool_ok = bool(data.get("tool_ok"))
    audit_status = str(audit.get("status") or "")
    summary = str(data.get("tool_summary") or audit.get("summary") or event.get("message") or "")[:600]
    selected_alternate = bool(data.get("selected_alternate"))
    if not selected_alternate and alternate_command:
        selected_alternate = command == alternate_command and command != preferred_command
    returncode = _int_value(data.get("returncode"))
    failure = _classify_failure(
        command=command,
        returncode=returncode,
        summary=summary,
        stderr=str(data.get("stderr_excerpt") or ""),
        stdout=str(data.get("stdout_excerpt") or ""),
        ok=tool_ok,
    )
    return PromotionVerificationAttemptRecord(
        event_id=int(event.get("id") or 0),
        timestamp=str(event.get("timestamp") or ""),
        command=command,
        ok=tool_ok,
        audit_status=audit_status,
        summary=summary,
        tool_ok=tool_ok,
        selected_alternate=selected_alternate,
        returncode=returncode,
        failure_kind=failure["failure_kind"],
        suspected_file=failure["suspected_file"],
        suspected_line=_int_value(failure["suspected_line"]),
        repair_hint=failure["repair_hint"],
        evidence_excerpt=failure["evidence_excerpt"],
    )


def _classify_failure(
    *,
    command: str,
    returncode: int,
    summary: str,
    stderr: str,
    stdout: str,
    ok: bool,
) -> dict[str, str | int]:
    if ok:
        return _failure_result("", "", 0, "", "")
    text = _compact_text("\n".join([stderr, stdout, summary]), limit=5000)
    lowered = text.lower()
    file_path, line, message = _extract_file_line(text)
    error_kind, error_message = _extract_error_line(text)

    missing_file = _extract_missing_file(text)
    if missing_file:
        hint = f"Check whether `{missing_file}` exists, or update the promotion verification command to target an existing file."
        return _failure_result("missing_file", missing_file, 0, hint, _evidence_excerpt(text, missing_file))

    if error_kind in {"syntaxerror", "indentationerror", "taberror"} or "syntaxerror" in lowered:
        kind = "syntax_error" if error_kind != "indentationerror" else "indentation_error"
        target = _format_target(file_path, line)
        detail = error_message or message or error_kind or "syntax error"
        hint = f"Open `{target or file_path or 'the failing file'}` and fix {detail} before rerunning promotion verification."
        return _failure_result(kind, file_path, line, hint, _evidence_excerpt(text, file_path or detail))

    if "modulenotfounderror" in lowered or "cannot find module" in lowered or "importerror" in lowered:
        target = _format_target(file_path, line)
        detail = error_message or message or "missing import/module"
        hint = f"Inspect `{target or file_path or 'the import site'}` and fix the missing import or dependency: {detail}."
        return _failure_result("import_error", file_path, line, hint, _evidence_excerpt(text, file_path or detail))

    npm_script = NPM_MISSING_SCRIPT.search(text)
    if npm_script:
        script = npm_script.group("script").strip()
        hint = f"Add or correct the `{script}` package script, or choose an existing repo-map verification command."
        return _failure_result("missing_npm_script", "package.json", 0, hint, _evidence_excerpt(text, script))

    if file_path and ("error" in lowered or "failed" in lowered or "assert" in lowered):
        target = _format_target(file_path, line)
        detail = error_message or message or "test/build failure"
        hint = f"Inspect `{target}` for the focused promotion verification failure: {detail}."
        return _failure_result("test_or_build_failure", file_path, line, hint, _evidence_excerpt(text, file_path))

    if "timed out" in lowered or "timeout" in lowered:
        hint = "Reduce promotion verification scope or run a narrower diagnostic before retrying the timed-out command."
        return _failure_result("timeout", "", 0, hint, _evidence_excerpt(text, "timeout"))

    if returncode:
        hint = "Read the compact promotion verification excerpt and choose the narrowest file-focused diagnostic before retrying."
        return _failure_result("command_failure", file_path, line, hint, _evidence_excerpt(text, file_path or "error"))
    return _failure_result("tool_failure", file_path, line, "Inspect the tool failure summary before retrying promotion verification.", _evidence_excerpt(text, file_path or ""))


def _extract_file_line(text: str) -> tuple[str, int, str]:
    for pattern in FILE_LINE_PATTERNS:
        match = pattern.search(text)
        if match:
            file_path = str(match.groupdict().get("file") or "")
            line = _int_value(match.groupdict().get("line"))
            message = str(match.groupdict().get("message") or "").strip()
            return file_path, line, message
    return "", 0, ""


def _extract_error_line(text: str) -> tuple[str, str]:
    match = ERROR_LINE_PATTERN.search(text)
    if not match:
        return "", ""
    return match.group("kind").lower(), match.group("message").strip()


def _extract_missing_file(text: str) -> str:
    for pattern in MISSING_FILE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group("file").strip()
    return ""


def _failure_result(kind: str, file_path: str, line: int, hint: str, excerpt: str) -> dict[str, str | int]:
    return {
        "failure_kind": kind,
        "suspected_file": file_path,
        "suspected_line": line,
        "repair_hint": hint[:500],
        "evidence_excerpt": excerpt[:700],
    }


def _summary(
    status: str,
    attempts: list[PromotionVerificationAttemptRecord],
    latest_failed: str,
    next_command: str,
    latest_repair: PromotionVerificationAttemptRecord,
) -> str:
    hint = f" Repair hint: {latest_repair.repair_hint}" if latest_repair.repair_hint else ""
    if status == "none":
        return f"No promotion verification attempt has run yet; next proof command is `{next_command}`."
    if status == "ready":
        latest = attempts[-1]
        return f"Promotion verification passed with `{latest.command}`; audit status is `{latest.audit_status or 'unknown'}`."
    if status == "needs_retry":
        return f"Latest promotion verification failed with `{latest_failed}`; retry with narrower diagnostic `{next_command}`.{hint}"
    return f"Promotion verification has repeated failure evidence for `{latest_failed}`; pause or replan after `{next_command}`.{hint}"


def _recommended_action(status: str, next_command: str, latest_repair: PromotionVerificationAttemptRecord) -> str:
    if status == "ready":
        return "Use the refreshed promotion audit before asking for source promotion approval."
    if latest_repair.repair_hint:
        return latest_repair.repair_hint
    if status == "needs_retry":
        return f"Run the alternate promotion verification diagnostic: {next_command}"
    if status == "repeated_failure":
        return "Do not repeat the same promotion verification command; inspect the latest failure and choose a narrower fix or diagnostic."
    return f"Run promotion verification: {next_command}"


def _format_target(file_path: str, line: int) -> str:
    if file_path and line:
        return f"{file_path}:{line}"
    return file_path


def _evidence_excerpt(text: str, needle: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    needle_lower = needle.lower()
    interesting = [
        line
        for line in lines
        if (needle_lower and needle_lower in line.lower())
        or any(marker in line.lower() for marker in ("error", "failed", "traceback", "syntax", "no such", "cannot find", "missing script"))
    ]
    selected = interesting[:8] or lines[-6:]
    return _compact_text("\n".join(selected), limit=700)


def _compact_text(text: str, *, limit: int) -> str:
    compact = "\n".join(line.rstrip() for line in str(text or "").splitlines() if line.strip())
    return compact[:limit]


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result[:8]
