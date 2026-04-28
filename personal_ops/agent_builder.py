from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from agent.simple_agent.simple_agent import AgentConfig, SimpleAgent
from personal_ops.agent_profiles import (
    AGENT_MODE_DRAFT,
    DEFAULT_AGENT_MODE,
    EXECUTIVE_TOOL_NAMES,
    AgentProfile,
    WorkflowPreset,
    build_system_prompt,
    get_agent_profile,
)
from llm.client_factory import create_client
from personal_ops.tools_registry import MEMORY_TOOL_NAMES, TOOL_NAME_TO_CLASS
from tool_framework.tool_collection import ToolCollection


@dataclass(frozen=True)
class AgentBuildRequest:
    client_type: str
    client_config: dict
    profile_id: str
    selected_tool_names: tuple[str, ...]
    max_iterations: int
    reflection_interval: int
    enable_self_reflection: bool
    enable_planning: bool
    mode: str = DEFAULT_AGENT_MODE


def resolve_effective_mode(
    request_mode: str,
    workflow: WorkflowPreset | None,
) -> str:
    if workflow is not None:
        return workflow.mode
    return request_mode


def resolve_effective_tool_names(
    selected_tool_names: Sequence[str],
    workflow: WorkflowPreset | None = None,
    mode: str = DEFAULT_AGENT_MODE,
) -> tuple[str, ...]:
    if workflow is not None:
        return tuple(
            tool_name
            for tool_name in workflow.allowed_tool_names
            if tool_name in TOOL_NAME_TO_CLASS
        )

    filtered = (
        tool_name for tool_name in selected_tool_names if tool_name in TOOL_NAME_TO_CLASS
    )
    if mode == AGENT_MODE_DRAFT:
        filtered = (
            tool_name for tool_name in filtered if tool_name not in EXECUTIVE_TOOL_NAMES
        )
    return tuple(filtered)


def build_agent_signature(
    request: AgentBuildRequest,
    mcp_tool_names: Sequence[str] | None = None,
) -> str:
    payload = {
        "client_type": request.client_type,
        "client_config": request.client_config,
        "profile_id": request.profile_id,
        "selected_tool_names": sorted(request.selected_tool_names),
        "max_iterations": request.max_iterations,
        "reflection_interval": request.reflection_interval,
        "enable_self_reflection": request.enable_self_reflection,
        "enable_planning": request.enable_planning,
        "mode": request.mode,
        "mcp_tool_names": sorted(mcp_tool_names or []),
    }
    return json.dumps(payload, sort_keys=True)


def build_agent(
    request: AgentBuildRequest,
    *,
    long_term_memory,
    mcp_tools: Sequence | None = None,
    workflow: WorkflowPreset | None = None,
) -> SimpleAgent:
    profile = get_agent_profile(request.profile_id)
    effective_mode = resolve_effective_mode(request.mode, workflow)
    effective_tool_names = resolve_effective_tool_names(
        request.selected_tool_names,
        workflow=workflow,
        mode=effective_mode,
    )

    tools = []
    for tool_name in effective_tool_names:
        tool_class = TOOL_NAME_TO_CLASS[tool_name]
        if tool_name in MEMORY_TOOL_NAMES:
            tools.append(tool_class(long_term_memory))
        else:
            tools.append(tool_class())

    combined_tools = list(tools)
    if mcp_tools:
        if workflow is not None:
            allowed_mcp_names = set(effective_tool_names)
            combined_tools.extend(
                tool for tool in mcp_tools if tool.name in allowed_mcp_names
            )
        elif effective_mode == AGENT_MODE_DRAFT:
            combined_tools.extend(
                tool for tool in mcp_tools if tool.name not in EXECUTIVE_TOOL_NAMES
            )
        else:
            combined_tools.extend(mcp_tools)

    include_memory_context = any(
        tool_name in MEMORY_TOOL_NAMES for tool_name in effective_tool_names
    )
    system_prompt = build_system_prompt(
        profile,
        workflow=workflow,
        mode=effective_mode,
        include_memory_context=include_memory_context,
    )

    agent_config = AgentConfig(
        max_iterations=request.max_iterations,
        reflection_interval=request.reflection_interval,
        enable_self_reflection=request.enable_self_reflection,
        enable_planning=request.enable_planning,
        agent_name=profile.label,
    )

    return SimpleAgent(
        system_prompt=system_prompt,
        tool_collection=ToolCollection(combined_tools) if combined_tools else None,
        llm_client=create_client(request.client_type, request.client_config),
        config=agent_config,
    )


def get_profile_label(profile: AgentProfile) -> str:
    return profile.label
