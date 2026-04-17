import json

import streamlit as st

from agent.agent_event import AgentEvent, AgentEventType
from streamlit_ui.event_log import render_event_log


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


def render_chat_history(
    messages: list[dict], event_logs: list[list[AgentEvent]]
) -> None:
    assistant_idx = 0
    for msg in messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and msg.get("status") == "running":
                if msg.get("content"):
                    _render_content(msg["content"])
                else:
                    st.markdown("_Agent is working..._")
            elif msg["role"] == "assistant" and msg.get("status") == "error":
                st.error(str(msg.get("content", "Unknown error")))
            else:
                _render_content(msg["content"])

            meta = msg.get("meta") or {}
            caption = _build_caption(meta)
            if caption:
                st.caption(caption)

            if msg["role"] == "assistant" and assistant_idx < len(event_logs):
                events = event_logs[assistant_idx]
                plan_text = _extract_latest_plan(events)
                if plan_text:
                    with st.expander("Current plan", expanded=False):
                        st.markdown(plan_text)
                if events:
                    with st.expander(
                        f"Agent Log ({len(events)} events)", expanded=False
                    ):
                        render_event_log(events)
        if msg["role"] == "assistant":
            assistant_idx += 1
