import base64
import copy
from typing import TYPE_CHECKING

import streamlit as st

from personal_ops.inbox_triage.schema import (
    render_inbox_triage_response,
    structured_response_to_json,
)
from personal_ops.async_runtime import (
    AgentRunHandle,
    EventBufferSubscriber,
    run_agent_turn,
)

if TYPE_CHECKING:
    from typing import Type

    from pydantic import BaseModel


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


def _messages_for_agent(messages: list[dict]) -> list[dict]:
    payload = copy.deepcopy(messages)
    for message in payload:
        if "agent_content" in message:
            message["content"] = message["agent_content"]
            message.pop("agent_content", None)
        elif isinstance(message.get("content"), dict):
            try:
                message["content"] = render_inbox_triage_response(message["content"])
            except Exception:
                message["content"] = structured_response_to_json(message["content"])
    return payload


def queue_agent_turn(
    content: str | list[dict],
    *,
    agent=None,
    display_content: str | list[dict] | None = None,
    session_state=None,
    workflow_id: str | None = None,
    workflow_params: dict | None = None,
    response_schema: "Type[BaseModel] | None" = None,
) -> None:
    state = session_state or st.session_state
    target_agent = agent or state.get("agent")
    if target_agent is None:
        raise RuntimeError("Please initialize the agent first!")

    user_message = {"role": "user", "content": content}
    if display_content is not None:
        user_message["display_content"] = display_content
        user_message["agent_content"] = content
    state["messages"].append(user_message)

    assistant_index = len(state["messages"])
    assistant_message: dict = {
        "role": "assistant",
        "content": "",
        "status": "running",
        "meta": {"status": "running", "iterations": 0},
    }
    if workflow_id:
        assistant_message["workflow_id"] = workflow_id
        assistant_message["workflow_params"] = dict(workflow_params or {})
    state["messages"].append(assistant_message)

    event_log_index = len(state["event_logs"])
    state["event_logs"].append([])

    subscriber = EventBufferSubscriber()
    messages_snapshot = _messages_for_agent(state["messages"][:-1])
    try:
        future = state["async_runtime"].submit(
            run_agent_turn(
                agent=target_agent,
                messages=messages_snapshot,
                short_term_memory=state.get("short_term_memory"),
                subscriber=subscriber,
                response_schema=response_schema,
            )
        )
    except Exception as exc:
        state["messages"][assistant_index]["content"] = f"Error: {exc}"
        state["messages"][assistant_index]["status"] = "error"
        state["messages"][assistant_index]["meta"] = {
            "status": "error",
            "iterations": 0,
        }
        raise

    state["pending_run"] = AgentRunHandle(
        future=future,
        subscriber=subscriber,
        assistant_index=assistant_index,
        event_log_index=event_log_index,
    )


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

    try:
        queue_agent_turn(content)
    except Exception as exc:
        st.error(str(exc))
        st.rerun()

    st.rerun()
