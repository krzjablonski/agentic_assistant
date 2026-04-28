import streamlit as st

from agent.agent_event import AgentEvent, AgentEventType
from streamlit_ui.constants import _EVENT_ICONS


def get_recent_events(events: list[AgentEvent], limit: int) -> list[AgentEvent]:
    if limit <= 0:
        return []
    return events[-limit:]


def _truncate_message(message: str, max_chars: int | None) -> str:
    if max_chars is None or len(message) <= max_chars:
        return message
    if max_chars <= 3:
        return message[:max_chars]
    return message[: max_chars - 3] + "..."


def render_event_log(
    events: list[AgentEvent],
    *,
    show_details: bool = True,
    max_message_chars: int | None = None,
) -> None:
    for event in events:
        icon = _EVENT_ICONS.get(event.event_type, "\u2022")
        timestamp = event.timestamp.strftime("%H:%M:%S")
        message = _truncate_message(event.message, max_message_chars)
        st.markdown(
            f"**{icon} [{timestamp}] Iter {event.iteration}** — {message}"
        )
        if show_details and event.data and event.event_type in (
            AgentEventType.TOOL_CALL,
            AgentEventType.TOOL_RESULT,
            AgentEventType.SELF_REFLECTION,
            AgentEventType.LLM_RESPONSE,
            AgentEventType.REASONING,
            AgentEventType.PLAN_CREATED,
            AgentEventType.PLAN_UPDATED,
        ):
            with st.expander("Details", expanded=False):
                st.json(event.data)
