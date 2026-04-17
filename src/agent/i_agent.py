from agent.agent_event import AgentEventType, AgentEvent
from message_logger.agent_event_subscriber import AgentEventSubscriber
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Union, List
import uuid


@dataclass
class TextContent:
    """Text content block for Anthropic API."""

    text: str
    type: str = field(default="text", init=False)

    def to_dict(self) -> dict:
        return {"type": self.type, "text": self.text}


@dataclass
class ImageContent:
    """Image content block (base64 encoded)."""

    data: str
    media_type: str
    type: str = field(default="image", init=False)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "source": {
                "type": "base64",
                "media_type": self.media_type,
                "data": self.data,
            },
        }


@dataclass
class ToolUseContent:
    """Tool use content block (assistant's tool call)."""

    id: str
    name: str
    input: dict
    type: str = field(default="tool_use", init=False)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


@dataclass
class ToolResultContent:
    """Tool result content block (response to tool use)."""

    tool_use_id: str
    content: str
    is_error: bool = False
    type: str = field(default="tool_result", init=False)

    def to_dict(self) -> dict:
        result = {
            "type": self.type,
            "tool_use_id": self.tool_use_id,
            "content": self.content,
        }
        if self.is_error:
            result["is_error"] = True
        return result


@dataclass
class ThinkingContent:
    """Thinking/reasoning content block from LLM (Anthropic, Gemini)."""

    thinking: str
    type: str = field(default="thinking", init=False)
    signature: Optional[str] = None  # Anthropic uses signatures for verification

    def to_dict(self) -> dict:
        result = {"type": self.type, "thinking": self.thinking}
        if self.signature:
            result["signature"] = self.signature
        return result


ContentBlock = Union[
    TextContent, ImageContent, ToolUseContent, ToolResultContent, ThinkingContent
]


@dataclass
class Message:
    """Message compatible with Anthropic Messages API."""

    role: str  # "user" or "assistant"
    content: Union[str, List[ContentBlock]]

    def to_dict(self) -> dict:
        if isinstance(self.content, str):
            return {"role": self.role, "content": self.content}
        return {
            "role": self.role,
            "content": [
                block.to_dict() if hasattr(block, "to_dict") else block
                for block in self.content
            ],
        }


class IAgent(ABC):
    def __init__(
        self,
        system_prompt: str,
        name: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.system_prompt = system_prompt
        self.name: Optional[str] = name
        self.session_id: str = session_id or uuid.uuid4().hex[:8]
        self._messages: List[Message] = []
        self._subscribers: List[AgentEventSubscriber] = []
        self._iteration_count: int = 0

    @abstractmethod
    async def run(self, user_query: str | List[dict]) -> str:
        pass

    def get_messages(self) -> List[Message]:
        return self._messages

    def add_message(self, message: Message) -> None:
        """Add a Message object to the conversation."""
        self._messages.append(message)

    def add_text_message(self, role: str, content: str) -> None:
        """Add a simple text message to the conversation."""
        msg = Message(role=role, content=content)
        self._messages.append(msg)

    def clear_messages(self) -> None:
        """Clear conversation history."""
        self._messages = []

    def subscribe(self, subscriber: AgentEventSubscriber) -> None:
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: AgentEventSubscriber) -> None:
        self._subscribers.remove(subscriber)

    def _emit_event(
        self,
        event_type: AgentEventType,
        message: str,
        data: Optional[dict] = None,
    ) -> None:
        event = AgentEvent(
            event_type=event_type,
            session_id=self.session_id,
            message=message,
            data=data,
            agent_name=self.name,
            timestamp=datetime.now(),
            iteration=self._iteration_count,
        )
        event_log = getattr(self, "_event_log", None)
        if isinstance(event_log, list):
            event_log.append(event)
        for subscriber in self._subscribers:
            subscriber.on_event(event)
