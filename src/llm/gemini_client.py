from config_service import config_service
import json
import os
import uuid
from typing import List, Optional, Type, TYPE_CHECKING

from google import genai
from google.genai import types as genai_types

from llm.i_llm_client import ILLMClient, LLMResponse
from llm.tool_schema_builder import build_parameters_schema
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

_GEMINI_CONTEXT_WINDOWS: dict[str, int] = {
    "gemini-3-flash-preview": 1_048_576,
    "gemini-3.1-pro": 1_048_576,
    "gemini-3.1-pro-preview": 1_048_576,
    "gemini-3.1-flash-lite": 1_048_576,
    "gemini-2.5-flash-preview": 1_048_576,
    "gemini-2.5-pro-preview": 1_048_576,
}
_GEMINI_FALLBACK_CONTEXT_WINDOW = 1_048_576


class GeminiClient(ILLMClient):
    """Client for Google Gemini API using the native google-genai SDK."""

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_key: Optional[str] = None,
        context_window: Optional[int] = None,
    ):
        self._config_service = config_service
        resolved_key = api_key or self._config_service.get("llm.google_gemini_api_key")
        if not resolved_key:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")
        self.model = model
        self.client = genai.Client(api_key=resolved_key)
        self._context_window_override = context_window

    @property
    def context_window(self) -> int:
        if self._context_window_override is not None:
            return self._context_window_override
        return _GEMINI_CONTEXT_WINDOWS.get(self.model, _GEMINI_FALLBACK_CONTEXT_WINDOW)

    async def chat(
        self,
        messages: List["Message"],
        system: str,
        tools: Optional[List["ITool"]] = None,
        max_tokens: int = 4096,
        response_schema: Optional[Type["BaseModel"]] = None,
    ) -> LLMResponse:
        """Send messages to Gemini and return response."""
        contents = self._convert_messages(messages, tools_active=bool(tools))

        config_kwargs: dict = {
            "system_instruction": system,
            "max_output_tokens": max_tokens,
            "thinking_config": genai_types.ThinkingConfig(include_thoughts=True),
        }

        if tools:
            config_kwargs["tools"] = self._convert_tools(tools)
            config_kwargs["automatic_function_calling"] = (
                genai_types.AutomaticFunctionCallingConfig(
                    disable=True,
                )
            )

        if response_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema.model_json_schema()

        config = genai_types.GenerateContentConfig(**config_kwargs)

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        result = self._parse_response(response)

        if response_schema and result.text_content:
            try:
                result.structured_data = json.loads(result.text_content)
            except (json.JSONDecodeError, ValueError):
                result.structured_data = None

        return result

    # ── Message conversion ──────────────────────────────────────────

    def _convert_messages(
        self, messages: List["Message"], tools_active: bool = True
    ) -> List[genai_types.Content]:
        """Convert Message list to Gemini Content format."""
        # First pass: build tool_use_id -> tool_name mapping across all messages
        tool_id_to_name: dict[str, str] = {}
        for msg in messages:
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolUseContent):
                        tool_id_to_name[block.id] = block.name

        # Second pass: convert messages
        contents: List[genai_types.Content] = []
        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            parts = self._convert_content_to_parts(
                msg.content, msg.role, tool_id_to_name, tools_active
            )
            if parts:
                contents.append(genai_types.Content(role=role, parts=parts))

        return contents

    def _convert_content_to_parts(
        self,
        content,
        role: str,
        tool_id_to_name: dict[str, str],
        tools_active: bool = True,
    ) -> List[genai_types.Part]:
        """Convert message content to Gemini Part list."""
        if isinstance(content, str):
            return [genai_types.Part(text=content)]

        parts: List[genai_types.Part] = []
        for block in content:
            if isinstance(block, TextContent):
                parts.append(genai_types.Part(text=block.text))
            elif isinstance(block, ThinkingContent):
                # Gemini requires thinking blocks echoed back with thought=True
                parts.append(genai_types.Part(text=block.thinking, thought=True))
            elif isinstance(block, ImageContent):
                parts.append(
                    genai_types.Part(
                        inline_data=genai_types.Blob(
                            mime_type=block.media_type,
                            data=block.data,
                        )
                    )
                )
            elif isinstance(block, ToolUseContent):
                if tools_active:
                    part_kwargs = {
                        "function_call": genai_types.FunctionCall(
                            id=block.id,
                            name=block.name,
                            args=block.input,
                        )
                    }
                    thought_sig = (block.extra or {}).get("thought_signature")
                    if thought_sig:
                        part_kwargs["thought_signature"] = thought_sig
                    parts.append(genai_types.Part(**part_kwargs))
                else:
                    args_str = (
                        json.dumps(block.input, indent=2) if block.input else "{}"
                    )
                    parts.append(
                        genai_types.Part(
                            text=f"[Tool Call: {block.name}]\nArguments: {args_str}"
                        )
                    )
            elif isinstance(block, ToolResultContent):
                tool_name = tool_id_to_name.get(block.tool_use_id, "unknown")
                if tools_active:
                    parts.append(
                        genai_types.Part(
                            function_response=genai_types.FunctionResponse(
                                id=block.tool_use_id,
                                name=tool_name,
                                response={"result": block.content},
                            )
                        )
                    )
                else:
                    prefix = "[Tool Error" if block.is_error else "[Tool Result"
                    parts.append(
                        genai_types.Part(
                            text=f"{prefix}: {tool_name}]\n{block.content}"
                        )
                    )

        return parts

    # ── Tool conversion ─────────────────────────────────────────────

    def _convert_tools(self, tools: List["ITool"]) -> List[genai_types.Tool]:
        """Convert ITool list to Gemini Tool format."""
        declarations = []
        for tool in tools:
            schema = build_parameters_schema(tool)
            schema = self._sanitize_schema_for_gemini(schema)
            declarations.append(
                genai_types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=schema,
                )
            )
        return [genai_types.Tool(function_declarations=declarations)]

    def _sanitize_schema_for_gemini(
        self, schema: dict, *, in_properties: bool = False
    ) -> dict:
        """Remove JSON Schema fields not supported by Gemini API.

        Gemini doesn't support: additionalProperties, $defs, anyOf, oneOf,
        allOf, $ref, $schema, title, default, examples, const, etc.
        Also flattens simple anyOf patterns (e.g. anyOf with null for Optional).
        """
        _UNSUPPORTED_KEYS = {
            "additionalProperties",
            "additional_properties",
            "$defs",
            "$ref",
            "$schema",
            "allOf",
            "oneOf",
            "title",
            "default",
            "examples",
            "const",
        }

        if not isinstance(schema, dict):
            return schema

        result = {}
        for key, value in schema.items():
            # Inside `properties`, dict keys are user-defined property names,
            # so they must not be filtered as JSON Schema metadata.
            if not in_properties and key in _UNSUPPORTED_KEYS:
                continue

            if key == "anyOf" and isinstance(value, list):
                # Flatten simple Optional patterns: anyOf[{type: X}, {type: null}]
                non_null = [
                    v
                    for v in value
                    if not (isinstance(v, dict) and v.get("type") == "null")
                ]
                if len(non_null) == 1:
                    result.update(self._sanitize_schema_for_gemini(non_null[0]))
                # else: drop anyOf entirely — Gemini can't handle it
                continue

            if key == "properties" and isinstance(value, dict):
                result[key] = self._sanitize_schema_for_gemini(
                    value, in_properties=True
                )
                continue

            if isinstance(value, dict):
                result[key] = self._sanitize_schema_for_gemini(
                    value, in_properties=False
                )
            elif isinstance(value, list):
                result[key] = [
                    (
                        self._sanitize_schema_for_gemini(item, in_properties=False)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                ]
            else:
                result[key] = value

        return result

    # ── Response parsing ────────────────────────────────────────────

    def _parse_response(self, response) -> LLMResponse:
        """Parse Gemini SDK response to LLMResponse."""
        candidate = response.candidates[0]
        content_blocks: List[ContentBlock] = []
        has_function_call = False

        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.thought and part.text:
                    # Thinking/reasoning block
                    content_blocks.append(ThinkingContent(thinking=part.text))
                elif part.text:
                    content_blocks.append(TextContent(text=part.text))
                elif part.function_call:
                    has_function_call = True
                    fc = part.function_call
                    extra = {}
                    thought_sig = getattr(part, "thought_signature", None)
                    if thought_sig:
                        extra["thought_signature"] = thought_sig
                    content_blocks.append(
                        ToolUseContent(
                            id=getattr(fc, "id", None) or str(uuid.uuid4()),
                            name=fc.name,
                            input=dict(fc.args) if fc.args else {},
                            extra=extra,
                        )
                    )

        # Determine stop reason
        finish_reason = getattr(candidate, "finish_reason", None)
        if has_function_call:
            stop_reason = "tool_use"
        elif finish_reason and str(finish_reason) == "MAX_TOKENS":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"

        # Usage
        usage_meta = getattr(response, "usage_metadata", None)
        usage = {
            "input_tokens": (
                getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0
            ),
            "output_tokens": (
                getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0
            ),
        }
        if usage_meta and hasattr(usage_meta, "thoughts_token_count"):
            usage["thinking_tokens"] = usage_meta.thoughts_token_count

        return LLMResponse(
            content=content_blocks,
            stop_reason=stop_reason,
            usage=usage,
        )
