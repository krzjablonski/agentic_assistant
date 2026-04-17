import base64
import copy

import streamlit as st

from streamlit_ui.async_runtime import (
    AgentRunHandle,
    EventBufferSubscriber,
    run_agent_turn,
)


def _build_message_content(chat_input) -> str | list[dict] | None:
    prompt = chat_input.text or ""
    uploaded_file = chat_input.files[0] if chat_input.files else None

    if uploaded_file is None:
        return prompt or None

    file_bytes = uploaded_file.read()
    base64_img = base64.b64encode(file_bytes).decode("utf-8")
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": uploaded_file.type,
                "data": base64_img,
            },
        }
    ]
    if prompt:
        content.append({"type": "text", "text": prompt})
    return content


def handle_chat_input() -> None:
    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
    chat_input = st.chat_input(
        "Enter your message...",
        accept_file=True,
        file_type=["png", "jpg", "jpeg", "webp", "gif"],
        disabled=st.session_state.get("pending_run") is not None,
    )
    if not chat_input:
        return

    if st.session_state.agent is None:
        st.error("Please initialize the agent first!")
        return

    content = _build_message_content(chat_input)
    if content is None:
        return

    st.session_state.messages.append({"role": "user", "content": content})

    assistant_index = len(st.session_state.messages)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": "",
            "status": "running",
            "meta": {"status": "running", "iterations": 0},
        }
    )

    event_log_index = len(st.session_state.event_logs)
    st.session_state.event_logs.append([])

    subscriber = EventBufferSubscriber()
    messages_snapshot = copy.deepcopy(st.session_state.messages[:-1])
    try:
        future = st.session_state.async_runtime.submit(
            run_agent_turn(
                agent=st.session_state.agent,
                messages=messages_snapshot,
                short_term_memory=st.session_state.get("short_term_memory"),
                subscriber=subscriber,
            )
        )
    except Exception as exc:
        st.session_state.messages[assistant_index]["content"] = f"Error: {exc}"
        st.session_state.messages[assistant_index]["status"] = "error"
        st.session_state.messages[assistant_index]["meta"] = {
            "status": "error",
            "iterations": 0,
        }
        st.rerun()

    st.session_state.pending_run = AgentRunHandle(
        future=future,
        subscriber=subscriber,
        assistant_index=assistant_index,
        event_log_index=event_log_index,
    )
    st.rerun()
