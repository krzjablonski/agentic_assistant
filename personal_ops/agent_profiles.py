from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agent.prompts.react_prompts import (
    REACT_SYSTEM_PROMPT,
    format_system_prompt_with_memory,
)
from personal_ops.tools_registry import TOOL_NAME_TO_CLASS

DEFAULT_PROFILE_ID = "default"
PERSONAL_OPS_PROFILE_ID = "personal_ops"
INBOX_TRIAGE_WORKFLOW_ID = "inbox_triage"

APPLIED_PROFILE_STATE_KEY = "applied_profile_id"
AGENT_MODE_STATE_KEY = "ui_agent_mode"

AGENT_MODE_DRAFT = "draft"
AGENT_MODE_EXECUTE = "execute"
AGENT_MODES = (AGENT_MODE_DRAFT, AGENT_MODE_EXECUTE)
DEFAULT_AGENT_MODE = AGENT_MODE_DRAFT

EXECUTIVE_TOOL_NAMES = frozenset(
    {
        "send_email",
        "create_calendar_event",
        "edit_calendar_event",
    }
)

AGENT_SETTING_WIDGET_KEYS = {
    "max_iterations": "ui_max_iterations",
    "reflection_interval": "ui_reflection_interval",
    "enable_self_reflection": "ui_enable_reflection",
    "enable_planning": "ui_enable_planning",
}


@dataclass(frozen=True)
class WorkflowPreset:
    id: str
    label: str
    description: str
    mode: str
    allowed_tool_names: tuple[str, ...]
    default_params: dict[str, Any] = field(default_factory=dict)
    prompt_template: str = ""

    def build_prompt(self, overrides: Mapping[str, Any] | None = None) -> str:
        params = dict(self.default_params)
        if overrides:
            params.update(
                {
                    key: value
                    for key, value in overrides.items()
                    if value is not None and value != ""
                }
            )
        return self.prompt_template.format(**params).strip()


@dataclass(frozen=True)
class AgentProfile:
    id: str
    label: str
    description: str
    system_prompt_addendum: str = ""
    default_tool_names: tuple[str, ...] = field(default_factory=tuple)
    recommended_agent_config: dict[str, Any] = field(default_factory=dict)
    workflows: tuple[WorkflowPreset, ...] = field(default_factory=tuple)
    default_mode: str = DEFAULT_AGENT_MODE


INBOX_TRIAGE_WORKFLOW = WorkflowPreset(
    id=INBOX_TRIAGE_WORKFLOW_ID,
    label="Inbox Triage",
    description="Inbox review and reply drafts without executing actions.",
    mode="draft",
    allowed_tool_names=(
        "read_email",
        "create_draft_email",
        "download_attachments",
        "current_date",
        "read_file",
        "list_directory",
        "write_file",
    ),
    default_params={
        "folder": "INBOX",
        "search_flag": "UNSEEN",
        "date_from": "",
        "date_to": "",
        "search_criteria": "UNSEEN",
    },
    prompt_template="""
Run the `Inbox triage` workflow for Personal Ops.

Starting parameters:
- folder: {folder}
- date range: {date_from} to {date_to}
- search_criteria: {search_criteria}

Instructions:
- Work in `Draft` mode. Do not send anything, and do not describe proposals as completed actions.
- First read the emails using the parameters above, then classify them.
- Explicitly and briefly skip lower-priority messages instead of making the report verbose.
- Prepare reply drafts only where a reply is actually needed.
- For every `Draft reply` item, after preparing the content, use the `create_draft_email` tool to create a physical draft in Gmail. This tool creates a draft but does not send it.
- Call `create_draft_email` with `to` set to the sender address from the `From` field, `subject` as `Re: <full Subject>` (do not duplicate `Re:` if it already exists), and `body` as the full draft text.
- If an email describes an event that has already happened, note the fact and any operational follow-up, but do not propose a reply to the sender without a clear reason.
- Do not propose asking for more details if the email does not expect a reply and does not block any action.
- If you are unsure whether a reply is needed, default to `No reply needed`.

Deterministic classification order (apply top-down to each email and stop at the first matching step):
1. Is the email purely informational, automated, a confirmation, receipt, invoice, security alert, newsletter, status update, or system notification? -> `No reply needed`.
2. Does the email describe an event that has already happened and contain no request for a reply or decision? -> `No reply needed` (record an operational follow-up as `Follow-up task` only when there is a real action to take).
3. Does the email block a decision, have a deadline, include a direct question, or contain a request that requires a reply from you? -> `Critical` (if urgent or a bottleneck) or `Quick Reply` (if it requires a response within the day but is not critical).
4. Otherwise -> `Deferred`.

Rationale contract:
- Every item with `priority: critical` must include a short 1 sentence `rationale` explaining why it is critical. Without a concrete rationale, the item must not be placed in `critical`.
- Items with `priority: quick_reply` and `priority: deferred` must also include a short descriptive `rationale`.

Coverage contract:
- Every email returned by the `read_email` call (using the provided `folder`, `search_criteria`, and date range) must appear in exactly one structured `items` entry. No silent omissions.
- Copy `sender` from the full `From` field and `subject` from the full `Subject` field 1:1 from the `read_email` output. `From` has the form `First Last <address@email>`, and `Subject` must be taken in full without shortening.
- The same `sender` + `subject` pair must not appear more than once.

Reply draft contract:
- Create drafts only for emails assigned to `action: draft_reply`; emails assigned to `action: follow_up_task` and `action: no_reply_needed` must have `draft: null`.
- Every draft must be complete, ready-to-edit reply text: a short professional tone, clear purpose, concrete answer/decision, and proposed next step.
- For every `draft_reply` item, first try to create a physical draft with the `create_draft_email` tool. In `draft.status`, use `created` or `not_created`; put the tool reason in `draft.reason` when it was not created.
- Do not use placeholders such as `[fill in]`, `<insert>`, `TODO`, `...`, or generic filler without a decision.
- Do not write that the email was sent or that an action was completed; a draft is only a proposal for manual approval.

Structured response contract:
- Return the final answer through the provided structured schema, not as a handmade Markdown report.
- The `items` array is the source of truth. Include exactly one item for every email returned by `read_email`; do not silently omit emails.
- Use `priority` values exactly as `critical`, `quick_reply`, or `deferred`.
- Use `action` values exactly as `draft_reply`, `follow_up_task`, or `no_reply_needed`.
- For `draft_reply`, include a complete `draft` object with `to`, `subject`, `body`, `status`, and `reason`. Use `reason: null` when the draft was created successfully.
- For `follow_up_task`, set `follow_up_task` to the exact action to take outside email and set `draft: null`.
- For `no_reply_needed`, set both `draft` and `follow_up_task` to null.
- Include a short `summary` and a `warnings` array. Use `warnings: []` when there are no warnings.
- The UI and report writer will render Critical, Quick Reply, Deferred, Proposed Actions, and Draft Replies from this structure.
""",
)

DEFAULT_PROFILE = AgentProfile(
    id=DEFAULT_PROFILE_ID,
    label="Default",
    description="Default agent profile with full editable UI configuration.",
    default_tool_names=tuple(TOOL_NAME_TO_CLASS.keys()),
    recommended_agent_config={
        "max_iterations": 10,
        "reflection_interval": 3,
        "enable_self_reflection": True,
        "enable_planning": True,
    },
    default_mode=AGENT_MODE_DRAFT,
)

PERSONAL_OPS_PROFILE = AgentProfile(
    id=PERSONAL_OPS_PROFILE_ID,
    label="Personal Ops",
    description=(
        "- Reads and triages your email inbox, drafts replies\n"
        "- Reads calendar events and local files\n"
        "- Draft mode by default: no emails sent, no calendar changes without your approval\n"
        "- Tool selection is managed by this profile\n"
        "- Use Inbox Triage to start a guided workflow"
    ),
    system_prompt_addendum="""
You are operating as a Personal Ops Assistant.

- Focus on operational clarity, prioritization, and concrete next steps.
- Separate what you found from what you recommend doing next.
- Prefer crisp, work-ready drafts over generic suggestions.
- Treat drafts, notes, and checklists as proposals unless a tool result confirms execution.
- During inbox triage, default to `no reply needed` for informational emails unless the message clearly requests an action, decision, confirmation, or answer.
""".strip(),
    default_tool_names=(
        "read_email",
        "create_draft_email",
        "download_attachments",
        "google_calendar",
        "current_date",
        "read_file",
        "write_file",
        "list_directory",
        "save_memory",
        "recall_memory",
    ),
    recommended_agent_config={
        "max_iterations": 10,
        "reflection_interval": 3,
        "enable_self_reflection": True,
        "enable_planning": True,
    },
    workflows=(INBOX_TRIAGE_WORKFLOW,),
    default_mode=AGENT_MODE_DRAFT,
)

AGENT_PROFILES = {
    DEFAULT_PROFILE.id: DEFAULT_PROFILE,
    PERSONAL_OPS_PROFILE.id: PERSONAL_OPS_PROFILE,
}


def get_agent_profile(profile_id: str | None) -> AgentProfile:
    if profile_id and profile_id in AGENT_PROFILES:
        return AGENT_PROFILES[profile_id]
    return DEFAULT_PROFILE


def get_workflow_preset(profile: AgentProfile, workflow_id: str) -> WorkflowPreset | None:
    for workflow in profile.workflows:
        if workflow.id == workflow_id:
            return workflow
    return None


DRAFT_MODE_SYSTEM_BLOCK = """
## Work Mode: Draft

You are currently running in `draft` mode.

- Treat every suggested email reply, next step, note, or file update as a draft proposal unless a tool result confirms the action happened.
- Never imply that an email was sent, a calendar event was changed, or any other side effect was executed when you only prepared a draft.
- Creating an editable Gmail draft with `create_draft_email` is allowed when the tool is available; it creates a draft only and does not send.
- Tools that send email or modify the calendar are not available in this mode; if the user asks for such an action, prepare the proposal and explain that execution requires switching out of Draft mode.
- Keep analysis and execution clearly separated in your replies.
""".strip()


def build_system_prompt(
    profile: AgentProfile,
    *,
    workflow: WorkflowPreset | None = None,
    mode: str = DEFAULT_AGENT_MODE,
    include_memory_context: bool = False,
) -> str:
    prompt = REACT_SYSTEM_PROMPT

    if profile.system_prompt_addendum:
        prompt = f"{prompt}\n\n{profile.system_prompt_addendum}"

    if workflow is not None:
        workflow_instructions = f"""
## Active Workflow

You are currently running the `{workflow.label}` workflow in `{workflow.mode}` mode.

- Stay within the tools and constraints of this workflow.
- Treat every suggested email reply, next step, note, or file update as a draft proposal unless a tool result confirms the action happened.
- Never imply that an email was sent, a calendar event was changed, or any other side effect was executed when you only prepared a draft.
- If `create_draft_email` is available, you may create editable Gmail drafts; this is not email sending.
- The workflow final answer is structured data. The UI will render `Proposed Actions` and draft replies from the structured items, so keep each item's priority, action, rationale, and intentionally skipped messages precise.
""".strip()
        prompt = f"{prompt}\n\n{workflow_instructions}"
    elif mode == AGENT_MODE_DRAFT:
        prompt = f"{prompt}\n\n{DRAFT_MODE_SYSTEM_BLOCK}"

    if include_memory_context:
        prompt = format_system_prompt_with_memory(prompt)

    return prompt
