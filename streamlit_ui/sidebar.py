from pathlib import Path
import streamlit as st

from agent.prompts.react_prompts import (
    REACT_SYSTEM_PROMPT,
    format_system_prompt_with_memory,
)
from agent.simple_agent.simple_agent import AgentConfig, SimpleAgent
from mcp_client.mcp_manager import MCPManager
from memory.short_term_memory import ShortTermMemory
from streamlit_ui.client_factory import create_client
from streamlit_ui.constants import MEMORY_TOOL_CLASSES, TOOL_REGISTRY
from tool_framework.tool_collection import ToolCollection


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
    st.session_state.short_term_memory = None

    if short_term_memory is not None:
        short_term_memory.clear()


def render_chat_sidebar() -> None:
    """Render the chat configuration sidebar (client, agent settings, tools, init)."""
    is_busy = st.session_state.get("pending_run") is not None

    with st.sidebar:
        st.header("Configuration")

        client_type = st.selectbox(
            "Client",
            ["OpenAI", "Local", "Anthropic", "Google Gemini"],
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
                disabled=is_busy,
            )
        elif client_type == "Anthropic":
            client_config["model"] = st.selectbox(
                "Model",
                ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
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
                disabled=is_busy,
            )
        else:
            client_config["base_url"] = st.text_input(
                "Base URL",
                "http://127.0.0.1:1234/v1",
                disabled=is_busy,
            )
            client_config["model"] = st.text_input(
                "Model",
                "openai/gpt-oss-20b",
                disabled=is_busy,
            )
            client_config["context_window"] = st.number_input(
                "Context Window (tokens)",
                min_value=1024,
                max_value=1_000_000,
                value=8192,
                step=1024,
                help="Set the context window size configured for your local model.",
                disabled=is_busy,
            )

        st.divider()

        st.subheader("Agent Settings")
        max_iterations = st.slider("Max Iterations", 1, 20, 10, disabled=is_busy)
        reflection_interval = st.slider(
            "Reflection Interval", 1, 10, 3, disabled=is_busy
        )
        enable_reflection = st.checkbox(
            "Enable Self-Reflection",
            True,
            disabled=is_busy,
        )
        enable_planning = st.checkbox(
            "Enable Planning",
            True,
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
                for cat, entries in TOOL_REGISTRY.items():
                    for label, _ in entries:
                        st.session_state[f"tool_{cat}_{label}"] = True
                st.rerun()
        with col2:
            if st.button(
                "None",
                key="deselect_all_tools",
                use_container_width=True,
                disabled=is_busy,
            ):
                for cat, entries in TOOL_REGISTRY.items():
                    for label, _ in entries:
                        st.session_state[f"tool_{cat}_{label}"] = False
                st.rerun()

        selected_tool_classes: list[type] = []
        for category, tool_entries in TOOL_REGISTRY.items():
            st.caption(category)
            for label, tool_class in tool_entries:
                key = f"tool_{category}_{label}"
                if key not in st.session_state:
                    st.session_state[key] = True
                if st.checkbox(label, key=key, disabled=is_busy):
                    selected_tool_classes.append(tool_class)

        st.divider()

        if st.button(
            "Initialize Agent",
            type="primary",
            use_container_width=True,
            disabled=is_busy,
        ):
            if not selected_tool_classes:
                st.warning("Please select at least one tool.")
            else:
                try:
                    runtime = st.session_state.async_runtime
                    client = create_client(client_type, client_config)
                    tools = []
                    for cls in selected_tool_classes:
                        if cls in MEMORY_TOOL_CLASSES:
                            tools.append(cls(st.session_state.long_term_memory))
                        else:
                            tools.append(cls())
                    tool_collection = ToolCollection(tools)

                    if st.session_state.get("mcp_manager"):
                        runtime.run(st.session_state.mcp_manager.stop(), timeout=15)

                    mcp_config_path = Path(__file__).parent / "mcp_config.json"
                    mcp_manager = MCPManager(config_path=str(mcp_config_path))
                    mcp_tools = runtime.run(mcp_manager.start(), timeout=30)
                    for tool in mcp_tools:
                        tool_collection.add_tool(tool)
                    st.session_state.mcp_manager = mcp_manager

                    has_memory_tools = any(
                        cls in MEMORY_TOOL_CLASSES for cls in selected_tool_classes
                    )
                    system_prompt = (
                        format_system_prompt_with_memory(REACT_SYSTEM_PROMPT)
                        if has_memory_tools
                        else REACT_SYSTEM_PROMPT
                    )
                    st.session_state.agent = SimpleAgent(
                        system_prompt=system_prompt,
                        tool_collection=tool_collection,
                        llm_client=client,
                        config=AgentConfig(
                            max_iterations=max_iterations,
                            reflection_interval=reflection_interval,
                            enable_self_reflection=enable_reflection,
                            enable_planning=enable_planning,
                        ),
                    )
                    st.session_state.short_term_memory = ShortTermMemory(
                        llm_client=client
                    )
                    st.session_state.messages = []
                    st.session_state.event_logs = []
                    total_tools = len(selected_tool_classes) + len(mcp_tools)
                    mcp_info = f" + {len(mcp_tools)} MCP" if mcp_tools else ""
                    st.success(
                        f"Agent initialized with {total_tools} tool(s)!{mcp_info}"
                    )
                except Exception as e:
                    st.error(f"Failed to initialize agent: {str(e)}")

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
