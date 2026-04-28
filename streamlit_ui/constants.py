from agent.agent_event import AgentEventType
from personal_ops.tools_registry import TOOL_REGISTRY

TOOL_CHECKBOX_KEYS = {
    tool.tool_name: f"tool_{category}_{tool.label}"
    for category, tool_entries in TOOL_REGISTRY.items()
    for tool in tool_entries
}

_EVENT_ICONS = {
    AgentEventType.USER_MESSAGE: "\U0001f4ac",
    AgentEventType.ASSISTANT_MESSAGE: "\U0001f5e3",
    AgentEventType.LLM_RESPONSE: "\U0001f916",
    AgentEventType.TOOL_CALL: "\U0001f527",
    AgentEventType.TOOL_RESULT: "\U0001f4cb",
    AgentEventType.SELF_REFLECTION: "\U0001fa9e",
    AgentEventType.STATUS_CHANGE: "\U0001f504",
    AgentEventType.ERROR: "❌",
    AgentEventType.REASONING: "\U0001f9e0",
    AgentEventType.PLAN_CREATED: "\U0001f5fa",
    AgentEventType.PLAN_UPDATED: "\U0001f4dd",
}
