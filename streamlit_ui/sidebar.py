from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from mcp_client.mcp_manager import MCPManager
from memory.short_term_memory import ShortTermMemory
from agent.simple_agent.simple_agent import SimpleAgent
from personal_ops.agent_builder import AgentBuildRequest, build_agent
from personal_ops.agent_profiles import (
    AGENT_MODE_STATE_KEY,
    AGENT_MODES,
    AGENT_PROFILES,
    DEFAULT_PROFILE_ID,
    INBOX_TRIAGE_WORKFLOW_ID,
    PERSONAL_OPS_PROFILE_ID,
    get_agent_profile,
    get_workflow_preset,
)
from personal_ops.inbox_triage import InboxTriageResponse
from personal_ops.tools_registry import TOOL_REGISTRY
from streamlit_ui.agent_session import ensure_cached_agent
from streamlit_ui.chat_input import queue_agent_turn
from streamlit_ui.constants import TOOL_CHECKBOX_KEYS
from streamlit_ui.profile_defaults import apply_profile_defaults

PROFILE_KEY = "ui_agent_profile"
CLIENT_TYPE_KEY = "ui_client_type"

OPENAI_MODEL_KEY = "ui_openai_model"
ANTHROPIC_MODEL_KEY = "ui_anthropic_model"
GEMINI_MODEL_KEY = "ui_gemini_model"
LOCAL_BASE_URL_KEY = "ui_local_base_url"
LOCAL_MODEL_KEY = "ui_local_model"
LOCAL_CONTEXT_WINDOW_KEY = "ui_local_context_window"

MAX_ITERATIONS_KEY = "ui_max_iterations"
REFLECTION_INTERVAL_KEY = "ui_reflection_interval"
ENABLE_REFLECTION_KEY = "ui_enable_reflection"
ENABLE_PLANNING_KEY = "ui_enable_planning"

AGENT_LIVE_LOG_KEY = "ui_agent_live_log"

INBOX_DATE_FROM_KEY = "workflow_inbox_date_from"
INBOX_DATE_TO_KEY = "workflow_inbox_date_to"
INBOX_FOLDER_KEY = "workflow_inbox_folder"
INBOX_SEARCH_KEY = "workflow_inbox_search"

INBOX_SEARCH_OPTIONS = ("UNSEEN", "ALL", "SEEN", "FLAGGED", "ANSWERED")
IMAP_DATE_FORMAT = "%d-%b-%Y"


def render_sidebar() -> str:
    """Render the sidebar and return the selected page ('Chat' or 'Settings')."""
    with st.sidebar:
        page = st.radio(
            "Navigation",
            ["Chat", "Settings"],
            horizontal=True,
            label_visibility="collapsed",
        )

    return page


def _reset_chat_state() -> None:
    short_term_memory = st.session_state.get("short_term_memory")

    st.session_state.messages = []
    st.session_state.event_logs = []
    st.session_state.pending_run = None
    st.session_state.agent = None
    st.session_state.agent_signature = None
    st.session_state.short_term_memory = None

    if short_term_memory is not None:
        short_term_memory.clear()


def _ensure_mcp_tools() -> list:
    runtime = st.session_state.async_runtime
    mcp_manager = st.session_state.get("mcp_manager")
    if mcp_manager is None:
        mcp_config_path = Path(__file__).parent / "mcp_config.json"
        mcp_manager = MCPManager(config_path=str(mcp_config_path))
        st.session_state.mcp_manager = mcp_manager

    return runtime.run(mcp_manager.start(), timeout=30)


def _build_agent_request(
    *,
    client_type: str,
    client_config: dict,
    profile_id: str,
    selected_tool_names: list[str],
    max_iterations: int,
    reflection_interval: int,
    enable_reflection: bool,
    enable_planning: bool,
    mode: str,
) -> AgentBuildRequest:
    return AgentBuildRequest(
        client_type=client_type,
        client_config=dict(client_config),
        profile_id=profile_id,
        selected_tool_names=tuple(selected_tool_names),
        max_iterations=max_iterations,
        reflection_interval=reflection_interval,
        enable_self_reflection=enable_reflection,
        enable_planning=enable_planning,
        mode=mode,
    )


def _ensure_base_agent(
    request: AgentBuildRequest,
    mcp_tools: list,
) -> tuple[SimpleAgent, bool]:
    agent, rebuilt = ensure_cached_agent(
        st.session_state,
        request,
        long_term_memory=st.session_state.long_term_memory,
        mcp_tools=mcp_tools,
    )
    if rebuilt or st.session_state.get("short_term_memory") is None:
        st.session_state.short_term_memory = ShortTermMemory(
            llm_client=agent.llm_client
        )
    return agent, rebuilt


def _build_workflow_display_content(workflow_label: str, params: dict) -> str:
    return "\n".join(
        [
            f"{workflow_label}",
            f"- date range: {params['date_from']} → {params['date_to']}",
            f"- folder: {params['folder']}",
            f"- search_criteria: {params['search_criteria']}",
        ]
    )


def render_chat_sidebar() -> None:
    """Render the chat configuration sidebar (client, agent settings, tools, init)."""
    is_busy = st.session_state.get("pending_run") is not None

    if PROFILE_KEY not in st.session_state:
        st.session_state[PROFILE_KEY] = DEFAULT_PROFILE_ID
    if CLIENT_TYPE_KEY not in st.session_state:
        st.session_state[CLIENT_TYPE_KEY] = "OpenAI"

    with st.sidebar:
        st.header("Configuration")

        st.checkbox(
            "Agent Live Log",
            value=False,
            key=AGENT_LIVE_LOG_KEY,
            help="Show live agent activity, plan, saved run logs, and event log. Useful for debugging.",
        )

        selected_profile_id = st.selectbox(
            "Profile",
            options=list(AGENT_PROFILES.keys()),
            format_func=lambda profile_id: AGENT_PROFILES[profile_id].label,
            key=PROFILE_KEY,
            disabled=is_busy,
        )
        profile = get_agent_profile(selected_profile_id)
        is_personal_ops = selected_profile_id == PERSONAL_OPS_PROFILE_ID
        apply_profile_defaults(st.session_state, profile)
        st.caption(profile.description)

        if AGENT_MODE_STATE_KEY not in st.session_state:
            st.session_state[AGENT_MODE_STATE_KEY] = profile.default_mode
        selected_mode = st.selectbox(
            "Agent Mode",
            options=list(AGENT_MODES),
            format_func=str.capitalize,
            key=AGENT_MODE_STATE_KEY,
            disabled=is_busy,
            help=(
                "Draft: propose actions only; email-send and calendar-write tools are disabled."
                "Execute: all selected tools are available."
            ),
        )

        st.info(f"Active profile: {profile.label} · Mode: {selected_mode.capitalize()}")

        client_type = st.selectbox(
            "Client",
            ["OpenAI", "Local", "Anthropic", "Google Gemini"],
            key=CLIENT_TYPE_KEY,
            disabled=is_busy,
        )

        if client_type != st.session_state.prev_client_type:
            if st.session_state.get("mcp_manager"):
                st.session_state.async_runtime.run(
                    st.session_state.mcp_manager.stop(),
                    timeout=15,
                )
                st.session_state.mcp_manager = None
            _reset_chat_state()
            st.session_state.prev_client_type = client_type

        client_config: dict = {}
        if client_type == "OpenAI":
            client_config["model"] = st.selectbox(
                "Model",
                ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"],
                key=OPENAI_MODEL_KEY,
                disabled=is_busy,
            )
        elif client_type == "Anthropic":
            client_config["model"] = st.selectbox(
                "Model",
                ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
                key=ANTHROPIC_MODEL_KEY,
                disabled=is_busy,
            )
        elif client_type == "Google Gemini":
            client_config["model"] = st.selectbox(
                "Model",
                [
                    "gemini-3.1-pro-preview",
                    "gemini-3-flash-preview",
                    "gemini-2.5-flash",
                ],
                key=GEMINI_MODEL_KEY,
                disabled=is_busy,
            )
        else:
            client_config["base_url"] = st.text_input(
                "Base URL",
                "http://127.0.0.1:1234/v1",
                key=LOCAL_BASE_URL_KEY,
                disabled=is_busy,
            )
            client_config["model"] = st.text_input(
                "Model",
                "openai/gpt-oss-20b",
                key=LOCAL_MODEL_KEY,
                disabled=is_busy,
            )
            client_config["context_window"] = st.number_input(
                "Context Window (tokens)",
                min_value=1024,
                max_value=1_000_000,
                value=8192,
                step=1024,
                key=LOCAL_CONTEXT_WINDOW_KEY,
                help="Set the context window size configured for your local model.",
                disabled=is_busy,
            )

        if is_personal_ops:
            cfg = profile.recommended_agent_config
            max_iterations = cfg.get("max_iterations", 10)
            reflection_interval = cfg.get("reflection_interval", 3)
            enable_reflection = cfg.get("enable_self_reflection", True)
            enable_planning = cfg.get("enable_planning", True)
            selected_tool_names = list(profile.default_tool_names)
        else:
            st.divider()

            st.subheader("Agent Settings")
            max_iterations = st.slider(
                "Max Iterations",
                1,
                20,
                10,
                key=MAX_ITERATIONS_KEY,
                disabled=is_busy,
            )
            reflection_interval = st.slider(
                "Reflection Interval",
                1,
                10,
                3,
                key=REFLECTION_INTERVAL_KEY,
                disabled=is_busy,
            )
            enable_reflection = st.checkbox(
                "Enable Self-Reflection",
                True,
                key=ENABLE_REFLECTION_KEY,
                disabled=is_busy,
            )
            enable_planning = st.checkbox(
                "Enable Planning",
                True,
                key=ENABLE_PLANNING_KEY,
                disabled=is_busy,
            )

            st.divider()

            st.subheader("Tool Selection")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(
                    "All",
                    key="select_all_tools",
                    use_container_width=True,
                    disabled=is_busy,
                ):
                    for widget_key in TOOL_CHECKBOX_KEYS.values():
                        st.session_state[widget_key] = True
                    st.rerun()
            with col2:
                if st.button(
                    "None",
                    key="deselect_all_tools",
                    use_container_width=True,
                    disabled=is_busy,
                ):
                    for widget_key in TOOL_CHECKBOX_KEYS.values():
                        st.session_state[widget_key] = False
                    st.rerun()

            selected_tool_names = []
            for category, tool_entries in TOOL_REGISTRY.items():
                st.caption(category)
                for tool_definition in tool_entries:
                    widget_key = TOOL_CHECKBOX_KEYS[tool_definition.tool_name]
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = True
                    if st.checkbox(
                        tool_definition.label,
                        key=widget_key,
                        disabled=is_busy,
                    ):
                        selected_tool_names.append(tool_definition.tool_name)

        base_request = _build_agent_request(
            client_type=client_type,
            client_config=client_config,
            profile_id=selected_profile_id,
            selected_tool_names=selected_tool_names,
            max_iterations=max_iterations,
            reflection_interval=reflection_interval,
            enable_reflection=enable_reflection,
            enable_planning=enable_planning,
            mode=selected_mode,
        )

        if not is_personal_ops:
            st.divider()

            if st.button(
                "Initialize Agent",
                type="primary",
                use_container_width=True,
                disabled=is_busy,
            ):
                if not selected_tool_names:
                    st.warning("Please select at least one tool.")
                else:
                    try:
                        mcp_tools = _ensure_mcp_tools()
                        agent, _ = _ensure_base_agent(base_request, mcp_tools)
                        st.session_state.short_term_memory = ShortTermMemory(
                            llm_client=agent.llm_client
                        )
                        st.session_state.messages = []
                        st.session_state.event_logs = []
                        total_tools = len(selected_tool_names) + len(mcp_tools)
                        mcp_info = f" + {len(mcp_tools)} MCP" if mcp_tools else ""
                        st.success(
                            f"Agent initialized with {total_tools} tool(s)!{mcp_info}"
                        )
                    except Exception as exc:
                        st.error(f"Failed to initialize agent: {exc}")

        workflow = get_workflow_preset(profile, INBOX_TRIAGE_WORKFLOW_ID)
        if workflow is not None:
            st.divider()
            st.subheader(workflow.label)
            st.caption(workflow.description)
            with st.form("workflow_inbox_triage"):
                today = date.today()
                date_from = st.date_input(
                    "Date from",
                    value=today,
                    key=INBOX_DATE_FROM_KEY,
                    disabled=is_busy,
                )
                date_to = st.date_input(
                    "Date to",
                    value=today,
                    key=INBOX_DATE_TO_KEY,
                    disabled=is_busy,
                )
                folder = st.text_input(
                    "Folder",
                    value=str(workflow.default_params["folder"]),
                    key=INBOX_FOLDER_KEY,
                    disabled=is_busy,
                )
                search_flag = st.selectbox(
                    "Search criteria",
                    options=INBOX_SEARCH_OPTIONS,
                    index=0,
                    key=INBOX_SEARCH_KEY,
                    disabled=is_busy,
                )
                start_workflow = st.form_submit_button(
                    "Start Inbox Triage",
                    use_container_width=True,
                    disabled=is_busy,
                )

            if start_workflow and date_to < date_from:
                st.error("`Date to` must be on or after `Date from`.")
                start_workflow = False

            if start_workflow:
                try:
                    since_str = date_from.strftime(IMAP_DATE_FORMAT)
                    before_str = (date_to + timedelta(days=1)).strftime(
                        IMAP_DATE_FORMAT
                    )
                    search_criteria = (
                        f"{search_flag} SINCE {since_str} BEFORE {before_str}"
                    )
                    params = {
                        "folder": folder,
                        "search_flag": search_flag,
                        "date_from": date_from.isoformat(),
                        "date_to": date_to.isoformat(),
                        "search_criteria": search_criteria,
                    }
                    mcp_tools = _ensure_mcp_tools()
                    _ensure_base_agent(base_request, mcp_tools)
                    workflow_agent = build_agent(
                        base_request,
                        long_term_memory=st.session_state.long_term_memory,
                        mcp_tools=mcp_tools,
                        workflow=workflow,
                    )
                    queue_agent_turn(
                        workflow.build_prompt(params),
                        agent=workflow_agent,
                        display_content=_build_workflow_display_content(
                            workflow.label,
                            params,
                        ),
                        workflow_id=workflow.id,
                        workflow_params=params,
                        response_schema=InboxTriageResponse,
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to start {workflow.label}: {exc}")

        if is_busy:
            st.info("Agent is processing a request.")
        elif st.session_state.agent is not None:
            st.info("Agent is ready.")

        ltm = st.session_state.get("long_term_memory")
        if ltm:
            memories = ltm.get_all()
            if memories:
                st.divider()
                st.subheader(f"Long-term Memory ({len(memories)})")
                if st.button(
                    "Clear all memories",
                    type="secondary",
                    use_container_width=True,
                    disabled=is_busy,
                ):
                    for memory in memories:
                        ltm.delete(memory.id)
                    st.success("All memories cleared.")
                    st.rerun()
