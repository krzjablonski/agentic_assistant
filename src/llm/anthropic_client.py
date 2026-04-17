import json
import anthropic
from anthropic.types import (
    Message as AnthropicMessage,
    MessageParam as AnthropicMessageParam,
    OutputConfigParam,
    TextBlockParam,
    ToolUnionParam,
)
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from typing import List, Optional, Type, TYPE_CHECKING, cast

from llm.i_llm_client import ILLMClient, LLMResponse
from llm.tool_schema_builder import tools_to_anthropic_format
from config_service import config_service
from agent.i_agent import (
    TextContent,
    ThinkingContent,
    ToolUseContent,
    ContentBlock,
)

if TYPE_CHECKING:
    from pydantic import BaseModel
    from tool_framework.i_tool import ITool
    from agent.i_agent import Message


_ANTHROPIC_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
}
_ANTHROPIC_FALLBACK_CONTEXT_WINDOW = 100_000


class AnthropicClient(ILLMClient):
    """Anthropic Claude API client."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        context_window: Optional[int] = None,
    ):
        self.client = anthropic.AsyncAnthropic(
            api_key=config_service.get("llm.anthropic_api_key")
        )
        self.model = model
        self._context_window_override = context_window

    @property
    def context_window(self) -> int:
        if self._context_window_override is not None:
            return self._context_window_override
        return _ANTHROPIC_CONTEXT_WINDOWS.get(
            self.model, _ANTHROPIC_FALLBACK_CONTEXT_WINDOW
        )

    async def chat(
        self,
        messages: List["Message"],
        system: str,
        tools: Optional[List["ITool"]] = None,
        max_tokens: int = 4096,
        response_schema: Optional[Type["BaseModel"]] = None,
    ) -> LLMResponse:
        """Send messages to Claude and return response."""
        msg_dicts: list[AnthropicMessageParam] = []
        for msg in messages:
            msg_dict = cast(AnthropicMessageParam, msg.to_dict())
            if msg.role == "user" and isinstance(msg_dict.get("content"), list):
                msg_dict["content"] = sorted(
                    msg_dict["content"],
                    key=lambda b: 0 if b.get("type") == "image" else 1,
                )
            msg_dicts.append(msg_dict)

        kwargs: MessageCreateParamsNonStreaming = {
            "model": self.model,
            "max_tokens": max_tokens,
            "stream": False,
            "system": cast(
                list[TextBlockParam],
                [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            ),
            "messages": msg_dicts,
        }

        if tools:
            converted = cast(
                list[ToolUnionParam], tools_to_anthropic_format(tools)
            )
            if converted:
                converted[-1]["cache_control"] = {"type": "ephemeral"}
            kwargs["tools"] = converted

        if response_schema:
            output_config: OutputConfigParam = {
                "format": {
                    "type": "json_schema",
                    "schema": {
                        **response_schema.model_json_schema(),
                        "additionalProperties": False,
                    },
                }
            }
            kwargs["output_config"] = output_config

        response: AnthropicMessage = await self.client.messages.create(**kwargs)

        # Parse response content into our ContentBlock types
        content_blocks = self._parse_content_blocks(response.content)

        structured_data = None
        if response_schema:
            raw = "".join(
                block.text for block in content_blocks if isinstance(block, TextContent)
            )
            try:
                structured_data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                structured_data = None

        usage: dict[str, int] = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        cache_creation_input_tokens = response.usage.cache_creation_input_tokens
        if cache_creation_input_tokens is not None:
            usage["cache_creation_input_tokens"] = cache_creation_input_tokens

        cache_read_input_tokens = response.usage.cache_read_input_tokens
        if cache_read_input_tokens is not None:
            usage["cache_read_input_tokens"] = cache_read_input_tokens

        stop_reason = response.stop_reason or "end_turn"

        return LLMResponse(
            content=content_blocks,
            stop_reason=stop_reason,
            usage=usage,
            structured_data=structured_data,
        )

    def _parse_content_blocks(self, sdk_content) -> List[ContentBlock]:
        """Convert Anthropic SDK content blocks to our ContentBlock types.

        Handles text, tool_use, and thinking blocks from the SDK response.
        """
        blocks: List[ContentBlock] = []
        for block in sdk_content:
            block_type = getattr(block, "type", None)
            if block_type == "thinking":
                blocks.append(
                    ThinkingContent(
                        thinking=block.thinking,
                        signature=getattr(block, "signature", None),
                    )
                )
            elif block_type == "text":
                blocks.append(TextContent(text=block.text))
            elif block_type == "tool_use":
                blocks.append(
                    ToolUseContent(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )
            else:
                # Pass through any unknown block types from SDK directly
                blocks.append(block)
        return blocks
