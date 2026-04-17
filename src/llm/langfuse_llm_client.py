from typing import List, Optional, TYPE_CHECKING

from llm.i_llm_client import ILLMClient, LLMResponse

try:
    from langfuse import get_client as get_langfuse

    _LANGFUSE_AVAILABLE = True
except ImportError:
    _LANGFUSE_AVAILABLE = False

if TYPE_CHECKING:
    from typing import Type
    from pydantic import BaseModel
    from tool_framework.i_tool import ITool
    from agent.i_agent import Message


class LangfuseTrackedLLMClient(ILLMClient):
    """Wrapper around any ILLMClient that logs each chat() call as a Langfuse generation."""

    def __init__(self, inner: ILLMClient, model_name: str):
        self._inner = inner
        self._model_name = model_name

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    async def chat(
        self,
        messages: List["Message"],
        system: str,
        tools: Optional[List["ITool"]] = None,
        max_tokens: int = 4096,
        response_schema: Optional["Type[BaseModel]"] = None,
    ) -> LLMResponse:
        if not _LANGFUSE_AVAILABLE:
            return await self._inner.chat(
                messages, system, tools, max_tokens, response_schema
            )

        langfuse = get_langfuse()
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="llm-chat",
            model=self._model_name,
            input={"system": system, "messages": [m.to_dict() for m in messages]},
        ) as generation:
            response = await self._inner.chat(
                messages, system, tools, max_tokens, response_schema
            )
            generation.update(
                output=response.text_content,
                usage_details={
                    "input": response.usage.get("input_tokens", 0),
                    "output": response.usage.get("output_tokens", 0),
                },
            )
            return response
