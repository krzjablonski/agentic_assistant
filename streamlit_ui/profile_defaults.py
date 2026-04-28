from __future__ import annotations

from typing import Any, MutableMapping

from personal_ops.agent_profiles import (
    AGENT_MODE_STATE_KEY,
    AGENT_SETTING_WIDGET_KEYS,
    APPLIED_PROFILE_STATE_KEY,
    AgentProfile,
)
from streamlit_ui.constants import TOOL_CHECKBOX_KEYS


def apply_profile_defaults(
    session_state: MutableMapping[str, Any],
    profile: AgentProfile,
) -> bool:
    if session_state.get(APPLIED_PROFILE_STATE_KEY) == profile.id:
        return False

    profile_tool_names = set(profile.default_tool_names)
    for tool_name, widget_key in TOOL_CHECKBOX_KEYS.items():
        session_state[widget_key] = tool_name in profile_tool_names

    for config_key, widget_key in AGENT_SETTING_WIDGET_KEYS.items():
        if config_key in profile.recommended_agent_config:
            session_state[widget_key] = profile.recommended_agent_config[config_key]

    session_state[AGENT_MODE_STATE_KEY] = profile.default_mode
    session_state[APPLIED_PROFILE_STATE_KEY] = profile.id
    return True
