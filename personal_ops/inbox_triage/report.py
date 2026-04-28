from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from personal_ops.inbox_triage.schema import (
    InboxTriageResponse,
    render_inbox_triage_response,
    structured_response_to_json,
    structured_validation_notice,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INBOX_TRIAGE_REPORT_PATH = REPO_ROOT / ".ai" / "inbox-triage.md"
REPORT_HEADER = "# Inbox Triage Report\n"


@dataclass(frozen=True)
class ReportAppendResult:
    path: Path
    structured_validation_warning: str | None = None


def _coerce_response_to_text(response: object) -> str:
    if isinstance(response, (dict, InboxTriageResponse)):
        try:
            return render_inbox_triage_response(response)
        except Exception:
            return structured_response_to_json(response)
    if isinstance(response, str):
        return response
    if isinstance(response, list):
        parts: list[str] = []
        for block in response:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        if parts:
            return "\n".join(parts)
    return str(response)


def _format_params(params: Mapping[str, object]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in params.items())


def _ensure_header(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(REPORT_HEADER, encoding="utf-8")


def append_inbox_triage_report(
    response: object,
    *,
    params: Mapping[str, object] | None = None,
    report_path: Path = DEFAULT_INBOX_TRIAGE_REPORT_PATH,
    timestamp: datetime | None = None,
) -> ReportAppendResult:
    """Append a timestamped Inbox Triage section to the report file.

    Never overwrites prior content. Creates the file (with header) on first use.
    Structured responses are rendered to the Markdown report format. If a
    structured payload fails validation, a short notice is prepended between
    the params line and the raw body. The raw body is always preserved verbatim.
    """
    path = Path(report_path)
    _ensure_header(path)

    when = timestamp or datetime.now()
    body = _coerce_response_to_text(response).strip()
    structured_warning = (
        structured_validation_notice(response)
        if isinstance(response, (dict, InboxTriageResponse))
        else None
    )
    params_line = _format_params(params or {})

    lines: list[str] = ["", when.strftime("## %Y-%m-%d %H:%M"), ""]
    if params_line:
        lines.append(f"- params: {params_line}")
        lines.append("")
    if structured_warning:
        lines.append(structured_warning)
        lines.append("")
    if body:
        lines.append(body)
        lines.append("")
    lines.append("---")
    lines.append("")

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    return ReportAppendResult(
        path=path,
        structured_validation_warning=structured_warning,
    )
