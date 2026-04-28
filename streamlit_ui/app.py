from __future__ import annotations

from concurrent.futures import CancelledError

import streamlit as st

from agent.agent_event import AgentEvent, AgentEventType
from config_service import config_service
from memory.long_term_memory import LongTermMemory
from personal_ops.agent_profiles import INBOX_TRIAGE_WORKFLOW_ID
from personal_ops.async_runtime import AsyncRuntime
from personal_ops.inbox_triage.report import append_inbox_triage_report
from streamlit_ui.chat_input import handle_chat_input
from streamlit_ui.chat_view import render_chat_history, render_live_agent_activity
from streamlit_ui.settings import render_password_dialog, render_settings_page
from streamlit_ui.sidebar import AGENT_LIVE_LOG_KEY, render_chat_sidebar, render_sidebar

LIVE_REFRESH_SECONDS = 0.5


def _ensure_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "agent_signature" not in st.session_state:
        st.session_state.agent_signature = None
    if "active_profile_id" not in st.session_state:
        st.session_state.active_profile_id = None
    if "prev_client_type" not in st.session_state:
        st.session_state.prev_client_type = None
    if "event_logs" not in st.session_state:
        st.session_state.event_logs = []
    if "long_term_memory" not in st.session_state:
        st.session_state.long_term_memory = LongTermMemory()
    if "short_term_memory" not in st.session_state:
        st.session_state.short_term_memory = None
    if "mcp_manager" not in st.session_state:
        st.session_state.mcp_manager = None
    if "pending_run" not in st.session_state:
        st.session_state.pending_run = None
    if "async_runtime" not in st.session_state:
        st.session_state.async_runtime = AsyncRuntime()


def _latest_status(events: list[AgentEvent], fallback: str = "running") -> str:
    for event in reversed(events):
        if event.event_type == AgentEventType.STATUS_CHANGE and event.data:
            return event.data.get("status", fallback)
        if event.event_type == AgentEventType.ERROR:
            return "error"
    return fallback


def _latest_plan(events: list[AgentEvent]) -> str | None:
    for event in reversed(events):
        if event.event_type in (
            AgentEventType.PLAN_UPDATED,
            AgentEventType.PLAN_CREATED,
        ) and event.data:
            return event.data.get("plan")
    return None


def _build_live_meta(
    events: list[AgentEvent],
    fallback_status: str = "running",
) -> dict:
    meta = {
        "status": _latest_status(events, fallback=fallback_status),
        "iterations": max((event.iteration for event in events), default=0),
    }
    plan = _latest_plan(events)
    if plan:
        meta["plan"] = plan
    return meta


def _sync_pending_run() -> bool:
    handle = st.session_state.get("pending_run")
    if handle is None:
        return False

    assistant_message = st.session_state.messages[handle.assistant_index]
    events = handle.subscriber.snapshot()
    st.session_state.event_logs[handle.event_log_index] = events
    assistant_message["meta"] = _build_live_meta(events)

    if not handle.future.done():
        assistant_message["status"] = "running"
        return False

    try:
        result = handle.future.result()
        st.session_state.event_logs[handle.event_log_index] = result.events
        assistant_message["content"] = result.response
        assistant_message["status"] = "complete"
        assistant_message["meta"] = _build_live_meta(
            result.events,
            fallback_status=result.status,
        )
        assistant_message["meta"]["status"] = result.status
        assistant_message["meta"]["iterations"] = result.iterations
        if result.log_path:
            assistant_message["meta"]["log_path"] = result.log_path
        if result.jsonl_path:
            assistant_message["meta"]["jsonl_path"] = result.jsonl_path

        if assistant_message.get("workflow_id") == INBOX_TRIAGE_WORKFLOW_ID:
            try:
                report_result = append_inbox_triage_report(
                    result.response,
                    params=assistant_message.get("workflow_params"),
                )
                assistant_message["meta"]["report_path"] = str(report_result.path)
                if report_result.structured_validation_warning:
                    assistant_message["meta"]["report_validation_warning"] = (
                        report_result.structured_validation_warning
                    )
            except Exception as exc:
                assistant_message["meta"]["report_error"] = str(exc)

        short_term_memory = st.session_state.get("short_term_memory")
        if short_term_memory is not None and result.usage:
            short_term_memory.record_usage(
                input_tokens=result.usage.get("input_tokens", 0),
                output_tokens=result.usage.get("output_tokens", 0),
            )
    except CancelledError:
        assistant_message["content"] = "Request cancelled."
        assistant_message["status"] = "error"
        assistant_message["meta"] = {"status": "cancelled", "iterations": 0}
    except Exception as exc:
        assistant_message["content"] = f"Error: {exc}"
        assistant_message["status"] = "error"
        assistant_message["meta"] = _build_live_meta(events, fallback_status="error")
    finally:
        st.session_state.pending_run = None

    return True


def _render_chat_panel() -> None:
    run_every = (
        LIVE_REFRESH_SECONDS
        if st.session_state.get("pending_run") is not None
        else None
    )

    @st.fragment(run_every=run_every)
    def _chat_panel_fragment() -> None:
        run_finished = _sync_pending_run()
        show_debug = st.session_state.get(AGENT_LIVE_LOG_KEY, False)
        render_chat_history(
            st.session_state.messages,
            st.session_state.event_logs,
            show_debug,
        )
        pending_run = st.session_state.get("pending_run")
        if pending_run is not None and show_debug:
            events = st.session_state.event_logs[pending_run.event_log_index]
            st.divider()
            render_live_agent_activity(events)
        handle_chat_input()
        if run_finished:
            st.rerun()

    _chat_panel_fragment()


def main():
    st.set_page_config(page_title="AI Agent", layout="wide")
    _ensure_session_state()

    page = render_sidebar()

    if page == "Settings":
        render_settings_page()
        return

    if config_service.is_locked():
        render_password_dialog()

    is_busy = st.session_state.get("pending_run") is not None

    title_col, btn_col = st.columns([6, 1])
    with title_col:
        st.title("AI Agent Chat")
    with btn_col:
        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        if st.button(
            "➕",
            help="New conversation",
            use_container_width=True,
            disabled=is_busy,
        ):
            st.session_state.messages = []
            st.session_state.event_logs = []
            short_term_memory = st.session_state.get("short_term_memory")
            if short_term_memory is not None:
                short_term_memory.clear()
            st.rerun()

    render_chat_sidebar()
    _render_chat_panel()
