import streamlit as st

from agent.agent_event import AgentEvent, AgentEventType
from streamlit_ui.constants import _EVENT_ICONS


def render_event_log(events: list[AgentEvent]) -> None:
    for event in events:
        icon = _EVENT_ICONS.get(event.event_type, "\u2022")
        timestamp = event.timestamp.strftime("%H:%M:%S")
        st.markdown(
            f"**{icon} [{timestamp}] Iter {event.iteration}** — {event.message}"
        )
        if event.data and event.event_type in (
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
