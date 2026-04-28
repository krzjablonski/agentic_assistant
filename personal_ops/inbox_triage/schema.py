from __future__ import annotations

import json
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


TriagePriority = Literal["critical", "quick_reply", "deferred"]
TriageAction = Literal["draft_reply", "follow_up_task", "no_reply_needed"]
DraftStatus = Literal["created", "not_created"]

PRIORITY_LABELS: dict[str, str] = {
    "critical": "Critical",
    "quick_reply": "Quick Reply",
    "deferred": "Deferred",
}

ACTION_LABELS: dict[str, str] = {
    "draft_reply": "Draft reply",
    "follow_up_task": "Follow-up task",
    "no_reply_needed": "No reply needed",
}


class DraftReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(description="Recipient email address copied from the sender.")
    subject: str = Field(description="Draft subject, usually Re: <original subject>.")
    body: str = Field(description="Complete ready-to-edit draft reply body.")
    status: DraftStatus = Field(
        description="Whether the Gmail draft was created with create_draft_email."
    )
    reason: str | None = Field(
        description="Tool error or short reason when status is not_created."
    )


class TriageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: str = Field(description="Full From value from read_email.")
    subject: str = Field(description="Full Subject value from read_email.")
    priority: TriagePriority = Field(
        description="Priority bucket for rendering and review."
    )
    action: TriageAction = Field(description="Exactly one proposed action category.")
    rationale: str = Field(description="Short reason for the priority and action.")
    draft: DraftReply | None = Field(
        description="Required only when action is draft_reply; otherwise null."
    )
    follow_up_task: str | None = Field(
        description="Required only when action is follow_up_task; otherwise null."
    )

    @model_validator(mode="after")
    def validate_action_payload(self) -> "TriageItem":
        if self.action == "draft_reply":
            if self.draft is None:
                raise ValueError("draft_reply items require draft")
            if self.follow_up_task:
                raise ValueError("draft_reply items must not include follow_up_task")
        elif self.action == "follow_up_task":
            if not self.follow_up_task:
                raise ValueError("follow_up_task items require follow_up_task")
            if self.draft is not None:
                raise ValueError("follow_up_task items must not include draft")
        elif self.action == "no_reply_needed":
            if self.draft is not None:
                raise ValueError("no_reply_needed items must not include draft")
            if self.follow_up_task:
                raise ValueError("no_reply_needed items must not include follow_up_task")
        return self


class InboxTriageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Brief summary of the inbox triage result.")
    items: list[TriageItem] = Field(
        description="One item for every email read by the workflow."
    )
    warnings: list[str] = Field(
        description="Operational warnings or uncertainty notes. Use [] when none."
    )

    @model_validator(mode="after")
    def validate_unique_items(self) -> "InboxTriageResponse":
        seen: set[str] = set()
        duplicates: list[str] = []
        for item in self.items:
            key = _canonical_identifier(item.sender, item.subject)
            if key in seen:
                duplicates.append(_identifier(item.sender, item.subject))
            seen.add(key)
        if duplicates:
            joined = ", ".join(duplicates)
            raise ValueError(f"duplicate triage items: {joined}")
        return self


def coerce_inbox_triage_response(value: object) -> InboxTriageResponse:
    if isinstance(value, InboxTriageResponse):
        return value
    if isinstance(value, Mapping):
        return InboxTriageResponse.model_validate(dict(value))
    raise TypeError("response is not an InboxTriageResponse payload")


def is_inbox_triage_response(value: object) -> bool:
    try:
        coerce_inbox_triage_response(value)
    except (TypeError, ValidationError, ValueError):
        return False
    return True


def render_inbox_triage_response(value: object) -> str:
    response = coerce_inbox_triage_response(value)
    lines: list[str] = []

    if response.summary:
        lines.append(f"_Summary:_ {_clean_inline(response.summary)}")
        lines.append("")

    if response.warnings:
        lines.append("_Warnings:_")
        for warning in response.warnings:
            lines.append(f"- {_clean_inline(warning)}")
        lines.append("")

    for number, priority in enumerate(PRIORITY_LABELS, start=1):
        label = PRIORITY_LABELS[priority]
        lines.append(f"**{number}. {label}**")
        priority_items = [item for item in response.items if item.priority == priority]
        if not priority_items:
            lines.append("- none")
        else:
            for item in priority_items:
                rationale = _clean_inline(item.rationale)
                prefix = _identifier(item.sender, item.subject)
                if item.priority == "critical":
                    lines.append(f"- {prefix} - Rationale: {rationale}")
                else:
                    lines.append(f"- {prefix} - {rationale}")
        lines.append("")

    lines.append("**4. Proposed Actions**")
    for action, label in ACTION_LABELS.items():
        action_items = [item for item in response.items if item.action == action]
        if not action_items:
            lines.append(f"- `{label}` - none")
            continue
        for item in action_items:
            lines.append(f"- `{label}` - {_format_action_item(item)}")
    lines.append("")

    lines.append("**5. Draft Replies**")
    draft_items = [item for item in response.items if item.action == "draft_reply"]
    if not draft_items:
        lines.append("- none")
    else:
        for item in draft_items:
            assert item.draft is not None
            draft = item.draft
            reason = f": {_clean_inline(draft.reason)}" if draft.reason else ""
            lines.append(
                f"- {_identifier(item.sender, item.subject)} - "
                f"draft status: {draft.status}{reason}"
            )
            lines.append(f"  To: {draft.to}")
            lines.append(f"  Subject: {draft.subject}")
            lines.append("  Body:")
            for body_line in draft.body.splitlines() or [""]:
                lines.append(f"  {_clean_body_line(body_line)}")

    return "\n".join(lines).strip()


def structured_validation_notice(value: object) -> str | None:
    try:
        coerce_inbox_triage_response(value)
    except (TypeError, ValidationError, ValueError) as exc:
        return f"> [!] Structured validation: {exc}"
    return None


def structured_response_to_json(value: object) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2)
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _format_action_item(item: TriageItem) -> str:
    prefix = _identifier(item.sender, item.subject)
    rationale = _clean_inline(item.rationale)
    if item.action == "draft_reply":
        status = item.draft.status if item.draft else "not_created"
        return (
            f"{prefix} - proposal: draft reply waiting for manual approval; "
            f"draft status: {status}; {rationale}"
        )
    if item.action == "follow_up_task":
        return (
            f"{prefix} - proposal: {item.follow_up_task}; "
            f"rationale: {rationale}"
        )
    return f"{prefix} - proposal: no reply needed; rationale: {rationale}"


def _identifier(sender: str, subject: str) -> str:
    return f"From: {sender.strip()} | Subject: {subject.strip()}"


def _canonical_identifier(sender: str, subject: str) -> str:
    return re.sub(r"\s+", " ", _identifier(sender, subject)).strip().lower()


def _clean_inline(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_body_line(value: str) -> str:
    return value.rstrip()
