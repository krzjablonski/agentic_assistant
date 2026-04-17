import json
import uuid
from typing import List, Optional, Type, TYPE_CHECKING

from openai import AsyncOpenAI

from llm.i_llm_client import ILLMClient, LLMResponse
from llm.tool_schema_builder import tools_to_openai_format
from agent.i_agent import (
    TextContent,
    ImageContent,
    ToolUseContent,
    ToolResultContent,
    ThinkingContent,
    ContentBlock,
)

if TYPE_CHECKING:
    from pydantic import BaseModel
    from tool_framework.i_tool import ITool
    from agent.i_agent import Message


_OPENAI_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4-turbo-preview": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "gpt-3.5-turbo-16k": 16_385,
}
_OPENAI_FALLBACK_CONTEXT_WINDOW = 8_192


class OpenAICompatibleClient(ILLMClient):
    """Client for OpenAI-compatible APIs (OpenAI, OpenRouter, Ollama, LM Studio, etc.).

    Uses the official `openai` SDK with configurable base_url for compatibility.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.1",
        api_key: str = "not-needed",
        context_window: Optional[int] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=120.0,
        )
        self._context_window_override = context_window

    @property
    def context_window(self) -> int:
        if self._context_window_override is not None:
            return self._context_window_override
        return _OPENAI_CONTEXT_WINDOWS.get(self.model, _OPENAI_FALLBACK_CONTEXT_WINDOW)

    async def chat(
        self,
        messages: List["Message"],
        system: str,
        tools: Optional[List["ITool"]] = None,
        max_tokens: int = 4096,
        response_schema: Optional[Type["BaseModel"]] = None,
    ) -> LLMResponse:
        """Send messages to OpenAI-compatible API."""
        openai_messages = self._convert_messages(messages, system)

        kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools_to_openai_format(tools)

        if response_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": response_schema.model_json_schema(),
                    "strict": True,
                },
            }

        response = await self.client.chat.completions.create(**kwargs)

        result = self._parse_response(response)
        if response_schema and result.text_content:
            try:
                result.structured_data = json.loads(result.text_content)
            except (json.JSONDecodeError, ValueError):
                result.structured_data = None
        return result

    # ── Message conversion ──────────────────────────────────────────

    def _convert_messages(self, messages: List["Message"], system: str) -> List[dict]:
        """Convert Message list to OpenAI format."""
        openai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg.role
            content = msg.content

            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                blocks = (
                    self._convert_user_blocks(content)
                    if role == "user"
                    else self._convert_assistant_blocks(role, content)
                )
                openai_messages.extend(blocks)
        return openai_messages

    def _convert_user_blocks(self, blocks: List[ContentBlock]) -> List[dict]:
        """Convert user content blocks (text, images, and tool results)."""
        user_content = []
        messages = []
        for block in blocks:
            if isinstance(block, TextContent):
                user_content.append({"type": "text", "text": block.text})
            elif isinstance(block, ImageContent):
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{block.media_type};base64,{block.data}"
                        },
                    }
                )
            elif isinstance(block, ToolResultContent):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.tool_use_id,
                        "content": str(block.content),
                    }
                )
        else:
            if user_content:
                user_content.sort(key=lambda b: 0 if b["type"] == "text" else 1)
                messages.append({"role": "user", "content": user_content})

        return messages

    def _convert_assistant_blocks(
        self, role: str, blocks: List[ContentBlock]
    ) -> List[dict]:
        """Convert non-user content blocks (text and tool interactions)."""
        text_content = []
        tool_calls = []
        messages = []

        for block in blocks:
            if isinstance(block, ThinkingContent):
                # Skip thinking blocks — OpenAI format doesn't support them
                continue
            elif isinstance(block, TextContent):
                text_content.append(block.text)
            elif isinstance(block, ToolUseContent):
                tc = {
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                }
                if block.extra:
                    tc["extra_content"] = block.extra
                tool_calls.append(tc)
            elif isinstance(block, ToolResultContent):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.tool_use_id,
                        "content": str(block.content),
                    }
                )

        if text_content or tool_calls:
            msg = {"role": "assistant"}
            msg["content"] = "\n".join(text_content) if text_content else None
            if tool_calls:
                msg["tool_calls"] = tool_calls
            messages.insert(0, msg)

        return messages

    # ── Response parsing ────────────────────────────────────────────

    def _parse_response(self, response) -> LLMResponse:
        """Parse OpenAI SDK ChatCompletion response to LLMResponse."""
        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason or "stop"

        content_blocks: List[ContentBlock] = []

        if message.content:
            content_blocks.append(TextContent(text=message.content))

        if message.tool_calls:
            for tool_call in message.tool_calls:
                func = tool_call.function
                try:
                    args = json.loads(func.arguments)
                except json.JSONDecodeError:
                    args = {}

                content_blocks.append(
                    ToolUseContent(
                        id=tool_call.id or str(uuid.uuid4()),
                        name=func.name,
                        input=args,
                    )
                )

        stop_reason = "end_turn"
        if finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif finish_reason == "length":
            stop_reason = "max_tokens"

        usage_data = response.usage
        usage = {
            "input_tokens": getattr(usage_data, "prompt_tokens", 0) if usage_data else 0,
            "output_tokens": getattr(usage_data, "completion_tokens", 0) if usage_data else 0,
        }

        return LLMResponse(
            content=content_blocks,
            stop_reason=stop_reason,
            usage=usage,
        )
