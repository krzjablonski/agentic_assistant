from __future__ import annotations

from typing import Sequence

from agent.simple_agent.simple_agent import SimpleAgent
from personal_ops.agent_builder import (
    AgentBuildRequest,
    build_agent,
    build_agent_signature,
)


def ensure_cached_agent(
    session_state,
    request: AgentBuildRequest,
    *,
    long_term_memory,
    mcp_tools: Sequence | None = None,
) -> tuple[SimpleAgent, bool]:
    mcp_tool_names = [tool.name for tool in mcp_tools or []]
    signature = build_agent_signature(request, mcp_tool_names=mcp_tool_names)

    existing_agent = session_state.get("agent")
    if existing_agent is not None and session_state.get("agent_signature") == signature:
        return existing_agent, False

    agent = build_agent(
        request,
        long_term_memory=long_term_memory,
        mcp_tools=mcp_tools,
    )
    session_state["agent"] = agent
    session_state["agent_signature"] = signature
    session_state["active_profile_id"] = request.profile_id
    return agent, True
