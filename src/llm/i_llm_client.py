from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Type
    from pydantic import BaseModel
    from tool_framework.i_tool import ITool
    from agent.i_agent import Message, ContentBlock


@dataclass
class LLMResponse:
    """Response from LLM."""

    content: List["ContentBlock"]  # List of content blocks (text/tool_use/thinking)
    stop_reason: str  # "end_turn", "tool_use", "max_tokens"
    usage: dict  # {"input_tokens": int, "output_tokens": int}
    structured_data: Optional[dict] = field(default=None)

    @property
    def has_tool_use(self) -> bool:
        """Check if response contains tool use."""
        return self.stop_reason == "tool_use"

    @property
    def text_content(self) -> str:
        """Extract combined text from all text blocks, excluding thinking blocks."""
        texts = []
        for block in self.content:
            # Skip thinking blocks — they have 'thinking' attr but not 'text'
            if hasattr(block, "thinking"):
                continue
            if hasattr(block, "text"):
                texts.append(block.text)
        return "\n".join(texts).strip()

    @property
    def tool_uses(self) -> List["ContentBlock"]:
        """Extract all tool use blocks."""
        return [b for b in self.content if hasattr(b, "name")]


class ILLMClient(ABC):
    @property
    @abstractmethod
    def context_window(self) -> int:
        """Return the model's context window size in tokens."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List["Message"],
        system: str,
        tools: Optional[List["ITool"]] = None,
        max_tokens: int = 4096,
        response_schema: Optional["Type[BaseModel]"] = None,
    ) -> LLMResponse:
        """Send messages to LLM and return response.

        Args:
            messages: List of Message objects
            system: System prompt
            tools: Optional list of ITool instances
            max_tokens: Maximum tokens in response
            response_schema: Optional Pydantic model class. When provided,
                the client enforces structured JSON output matching the schema.
                The result is available in LLMResponse.structured_data.

        Returns:
            LLMResponse with content blocks and metadata
        """
        pass
