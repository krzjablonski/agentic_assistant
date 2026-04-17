from config_service import config_service
from agent import IAgent
import os
from enum import Enum
from typing import Optional, List

from tool_framework.i_tool import ITool
from tool_framework.tool_collection import ToolCollection
from llm.anthropic_client import AnthropicClient
from llm.gemini_client import GeminiClient
from llm.openai_compatible_client import OpenAICompatibleClient
from llm.langfuse_llm_client import LangfuseTrackedLLMClient
from llm.i_llm_client import ILLMClient
from agent.simple_agent.simple_agent import SimpleAgent, AgentConfig
from message_logger.agent_event_subscriber import AgentEventSubscriber


class LlmClientType(Enum):
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


_DEFAULT_MODELS = {
    LlmClientType.ANTHROPIC: "claude-sonnet-4-6",
    LlmClientType.GEMINI: "gemini-3-flash-preview",
    LlmClientType.OPENROUTER: "openai/gpt-5.4",
    LlmClientType.OPENAI: "gpt-5.4",
}


class AgentBuilder:
    def __init__(self):
        self._config_service = config_service
        self._llm_client_type: Optional[LlmClientType] = None
        self._model: Optional[str] = None
        self._langfuse: bool = False
        self._tools: List[ITool] = []
        self._system_prompt: str = ""
        self._logger: Optional[AgentEventSubscriber] = None
        self._config: Optional[AgentConfig] = None
        # Individual config overrides
        self._name: Optional[str] = None
        self._session_id: Optional[str] = None
        self._max_iterations: Optional[int] = None
        self._max_tokens: Optional[int] = None
        self._enable_self_reflection: Optional[bool] = None
        self._enable_planning: Optional[bool] = None

    def with_llm_client(self, llm_client_type: LlmClientType) -> "AgentBuilder":
        self._llm_client_type = llm_client_type
        return self

    def with_model(self, model: str) -> "AgentBuilder":
        self._model = model
        return self

    def with_langfuse(self, enabled: bool = True) -> "AgentBuilder":
        self._langfuse = enabled
        return self

    def with_tools(self, tools: List[ITool]) -> "AgentBuilder":
        self._tools = tools
        return self

    def with_system_prompt(self, system_prompt: str) -> "AgentBuilder":
        self._system_prompt = system_prompt
        return self

    def with_logger(self, logger: AgentEventSubscriber) -> "AgentBuilder":
        self._logger = logger
        return self

    def with_config(self, config: AgentConfig) -> "AgentBuilder":
        self._config = config
        return self

    def with_name(self, name: str) -> "AgentBuilder":
        self._name = name
        return self

    def with_session_id(self, session_id: str) -> "AgentBuilder":
        self._session_id = session_id
        return self

    def with_max_iterations(self, max_iterations: int) -> "AgentBuilder":
        self._max_iterations = max_iterations
        return self

    def with_max_tokens(self, max_tokens: int) -> "AgentBuilder":
        self._max_tokens = max_tokens
        return self

    def with_self_reflection(self, enabled: bool) -> "AgentBuilder":
        self._enable_self_reflection = enabled
        return self

    def with_planning(self, enabled: bool) -> "AgentBuilder":
        self._enable_planning = enabled
        return self

    def _create_llm_client(self) -> ILLMClient:
        client_type = self._llm_client_type or LlmClientType.ANTHROPIC
        model = self._model or _DEFAULT_MODELS[client_type]

        if client_type == LlmClientType.ANTHROPIC:
            client = AnthropicClient(model=model)
        elif client_type == LlmClientType.GEMINI:
            client = GeminiClient(model=model)
        elif client_type == LlmClientType.OPENAI:
            client = OpenAICompatibleClient(
                base_url="https://api.openai.com/v1",
                model=model,
                api_key=config_service.get("llm.openai_api_key") or "",
            )
        elif client_type == LlmClientType.OPENROUTER:
            client = OpenAICompatibleClient(
                base_url="https://openrouter.ai/api/v1",
                model=model,
                api_key=self._config_service.get("llm.openrouter_api_key") or "",
            )
        else:
            raise ValueError(f"Unknown LLM client type: {client_type}")

        if self._langfuse:
            client = LangfuseTrackedLLMClient(inner=client, model_name=model)

        return client

    def _create_config(self) -> AgentConfig:
        if self._config:
            config = self._config
        else:
            config = AgentConfig()

        if self._name is not None:
            config.agent_name = self._name
        if self._session_id is not None:
            config.session_id = self._session_id
        if self._max_iterations is not None:
            config.max_iterations = self._max_iterations
        if self._max_tokens is not None:
            config.max_tokens = self._max_tokens
        if self._enable_self_reflection is not None:
            config.enable_self_reflection = self._enable_self_reflection
        if self._enable_planning is not None:
            config.enable_planning = self._enable_planning

        return config

    def build(self) -> IAgent:
        llm_client = self._create_llm_client()
        config = self._create_config()
        tool_collection = ToolCollection(tools=self._tools) if self._tools else None

        agent = SimpleAgent(
            system_prompt=self._system_prompt,
            llm_client=llm_client,
            tool_collection=tool_collection,
            config=config,
        )

        if self._logger:
            agent.subscribe(self._logger)

        return agent
