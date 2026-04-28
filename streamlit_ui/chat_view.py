import json

import streamlit as st

from agent.agent_event import AgentEvent, AgentEventType
from personal_ops.inbox_triage.schema import (
    ACTION_LABELS,
    PRIORITY_LABELS,
    coerce_inbox_triage_response,
)
from streamlit_ui.event_log import get_recent_events, render_event_log

LIVE_EVENT_PREVIEW_LIMIT = 8


def build_structured_inbox_triage_groups(content) -> dict[str, list[dict]] | None:
    try:
        response = coerce_inbox_triage_response(content)
    except Exception:
        return None
    return {
        label: [
            item.model_dump()
            for item in response.items
            if item.priority == priority
        ]
        for priority, label in PRIORITY_LABELS.items()
    }


def _render_structured_inbox_triage_content(content) -> bool:
    try:
        response = coerce_inbox_triage_response(content)
    except Exception:
        return False

    if response.summary:
        st.markdown(response.summary)

    for priority, label in PRIORITY_LABELS.items():
        items = [item for item in response.items if item.priority == priority]
        with st.expander(f"{label} ({len(items)})", expanded=bool(items)):
            if not items:
                st.caption("none")
                continue
            for item in items:
                action = ACTION_LABELS[item.action]
                st.markdown(
                    f"**From:** {item.sender}  \n"
                    f"**Subject:** {item.subject}  \n"
                    f"**Action:** {action}  \n"
                    f"**Rationale:** {item.rationale}"
                )
                if item.follow_up_task:
                    st.markdown(f"**Follow-up task:** {item.follow_up_task}")
                if item.draft:
                    with st.expander(
                        f"Draft reply ({item.draft.status})",
                        expanded=False,
                    ):
                        st.markdown(
                            f"**To:** {item.draft.to}  \n"
                            f"**Subject:** {item.draft.subject}"
                        )
                        st.markdown(item.draft.body)
                        if item.draft.reason:
                            st.caption(item.draft.reason)
                st.divider()

    if response.warnings:
        st.warning("\n".join(f"- {warning}" for warning in response.warnings))

    return True


def _render_content(content) -> None:
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                st.markdown(block["text"])
            elif block.get("type") == "image":
                source = block.get("source", {})
                media_type = source.get("media_type", "image/png")
                data = source.get("data", "")
                st.image(f"data:{media_type};base64,{data}")
        return

    if isinstance(content, dict):
        if _render_structured_inbox_triage_content(content):
            return
        st.code(json.dumps(content, ensure_ascii=False, indent=2), language="json")
        return

    if content:
        st.markdown(str(content))


def _build_caption(meta: dict) -> str | None:
    parts: list[str] = []
    status = meta.get("status")
    if status:
        parts.append(f"Status: {status}")
    iterations = meta.get("iterations")
    if iterations is not None:
        parts.append(f"Iterations: {iterations}")
    return " | ".join(parts) if parts else None


def _extract_latest_plan(events: list[AgentEvent]) -> str | None:
    for event in reversed(events):
        if event.event_type in (
            AgentEventType.PLAN_UPDATED,
            AgentEventType.PLAN_CREATED,
        ) and event.data:
            return event.data.get("plan")
    return None


def render_live_agent_activity(events: list[AgentEvent]) -> None:
    st.markdown("#### Live Agent Activity")

    if not events:
        st.caption("Waiting for the first agent event...")
        return

    st.caption("This panel refreshes automatically while the agent is running.")

    plan_text = _extract_latest_plan(events)
    if plan_text:
        with st.expander("Current plan", expanded=True):
            st.markdown(plan_text)

    recent_events = get_recent_events(events, LIVE_EVENT_PREVIEW_LIMIT)
    if len(recent_events) < len(events):
        st.caption(f"Showing the last {len(recent_events)} of {len(events)} events.")

    render_event_log(
        recent_events,
        show_details=False,
        max_message_chars=220,
    )


def render_chat_history(
    messages: list[dict],
    event_logs: list[list[AgentEvent]],
    show_debug: bool,
) -> None:
    assistant_idx = 0
    for msg in messages:
        with st.chat_message(msg["role"]):
            rendered_content = msg.get("display_content", msg["content"])
            if msg["role"] == "assistant" and msg.get("status") == "running":
                if msg.get("content"):
                    _render_content(rendered_content)
                else:
                    st.markdown("_Agent is working..._")
            elif msg["role"] == "assistant" and msg.get("status") == "error":
                st.error(str(msg.get("content", "Unknown error")))
            else:
                _render_content(rendered_content)

            meta = msg.get("meta") or {}
            caption = _build_caption(meta)
            if caption:
                st.caption(caption)
            log_path = meta.get("log_path")
            jsonl_path = meta.get("jsonl_path")
            report_path = meta.get("report_path")
            report_error = meta.get("report_error")
            report_validation_warning = meta.get("report_validation_warning")
            if report_validation_warning:
                st.warning(report_validation_warning)
            if show_debug and (log_path or jsonl_path or report_path or report_error):
                with st.expander("Saved Run Logs", expanded=False):
                    if report_path:
                        st.caption("Inbox Triage report")
                        st.code(str(report_path), language="text")
                    if report_error:
                        st.warning(f"Report not saved: {report_error}")
                    if log_path:
                        st.code(str(log_path), language="text")
                    if jsonl_path:
                        st.code(str(jsonl_path), language="text")

            if (
                show_debug
                and msg["role"] == "assistant"
                and assistant_idx < len(event_logs)
            ):
                events = event_logs[assistant_idx]
                is_running = msg.get("status") == "running"
                if events and not is_running:
                    plan_text = _extract_latest_plan(events)
                    if plan_text:
                        with st.expander("Current plan", expanded=False):
                            st.markdown(plan_text)
                    with st.expander(
                        f"Agent Log ({len(events)} events)", expanded=False
                    ):
                        render_event_log(events)
        if msg["role"] == "assistant":
            assistant_idx += 1
