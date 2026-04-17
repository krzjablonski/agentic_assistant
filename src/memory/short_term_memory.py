from dataclasses import dataclass, field
from typing import List, Optional

from agent.i_agent import Message
from llm.i_llm_client import ILLMClient


SUMMARIZATION_PROMPT = """Summarize the following conversation into a concise paragraphs.
Preserve key facts, decisions, user preferences, and any important context.
Do not include pleasantries or filler. Focus on information that would be useful
for continuing the conversation.

Conversation:
{conversation}"""

# Characters per token heuristic used only as fallback on the first request
# (before any real usage data is available). Slightly conservative (~3.5 vs ~4.0)
# so we tend to over-estimate rather than under-estimate token usage.
_CHARS_PER_TOKEN: float = 3.5


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _estimate_message_tokens(message: dict) -> int:
    """Estimate token count for a single message dict."""
    content = message.get("content", "")
    if isinstance(content, str):
        return _estimate_tokens(content) + 4  # +4 for role/formatting overhead
    if isinstance(content, list):
        total = 0
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                total += _estimate_tokens(block.get("text", "")) + 4
            elif block.get("type") == "image":
                # Images can't be summarized away — count them conservatively.
                data_len = len(block.get("source", {}).get("data", ""))
                total += max(1_600, int(data_len / _CHARS_PER_TOKEN))
        return total
    return _estimate_tokens(str(content)) + 4


@dataclass
class ShortTermMemoryConfig:
    """Configuration for token-aware short-term memory."""

    # Fraction of the usable context at which summarization is triggered.
    summarization_threshold: float = 0.80

    # Minimum number of recent messages to always keep verbatim.
    min_recent_messages: int = 4

    # Token budget reserved for the model's response.
    # System prompt and tools are already accounted for in input_tokens from usage.
    response_token_reserve: int = 4_096

    # Max tokens for the generated summary.
    summary_max_tokens: int = 500

    # Kept for backwards-compatibility with any callers passing window_size=.
    # Ignored internally.
    window_size: int = field(default=10, repr=False)


class ShortTermMemory:
    """Token-aware sliding window + summary manager for session conversation history.

    Operates on the clean message list (list of {"role": str, "content": ...} dicts)
    used by the Streamlit UI, NOT the agent's internal message list.

    Summarization is triggered only when the estimated token count approaches
    a configurable threshold of the model's context window. Token counts are
    derived from real usage data (input_tokens + output_tokens) reported by the
    model after each response, falling back to a character-based heuristic on
    the very first request.

    Call record_usage() after each agent.run() to feed actual token counts.
    """

    def __init__(
        self,
        llm_client: ILLMClient,
        config: Optional[ShortTermMemoryConfig] = None,
    ):
        self._llm_client = llm_client
        self._config = config or ShortTermMemoryConfig()
        self._summary: Optional[str] = None
        self._last_input_tokens: Optional[int] = None
        self._last_output_tokens: Optional[int] = None

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Update token usage from the last LLM response.

        Call this after each agent.run() with the usage from the final
        LLM_RESPONSE event so that the next process_messages() call has
        accurate data to work with.
        """
        self._last_input_tokens = input_tokens
        self._last_output_tokens = output_tokens

    async def process_messages(self, messages: List[dict]) -> List[dict]:
        """Apply token-aware summarization to a message list.

        Returns messages unchanged if within budget, otherwise summarizes
        the oldest messages and prepends the summary.
        """
        if not self._should_summarize(messages):
            return messages

        split_point = self._find_split_point(messages)

        # Edge case: even the minimum recent messages exceed budget.
        # Return as-is and let the API enforce its own limit.
        if split_point == 0:
            return messages

        old_messages = messages[:split_point]
        recent_messages = messages[split_point:]

        self._summary = await self._summarize(old_messages)
        summary_prefix = f"[Summary of prior conversation]\n{self._summary}"

        # Avoid two consecutive user messages (Anthropic API requirement).
        if recent_messages and recent_messages[0]["role"] == "user":
            merged_first = {
                "role": "user",
                "content": f"{summary_prefix}\n\n{recent_messages[0]['content']}",
            }
            return [merged_first] + recent_messages[1:]

        return [{"role": "user", "content": summary_prefix}] + recent_messages

    @property
    def current_summary(self) -> Optional[str]:
        """Get the most recent summary, if any."""
        return self._summary

    def clear(self) -> None:
        """Reset stored summary and usage data."""
        self._summary = None
        self._last_input_tokens = None
        self._last_output_tokens = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _usable_token_budget(self) -> int:
        cfg = self._config
        usable = self._llm_client.context_window - cfg.response_token_reserve
        return max(1, int(usable * cfg.summarization_threshold))

    def _estimate_current_tokens(self, messages: List[dict]) -> int:
        """Estimate total tokens for the next request.

        If real usage data is available from a previous request, use it:
          estimated = last_input_tokens + last_output_tokens + new_user_msg_estimate

        last_input_tokens already includes all messages + system + tools from the
        previous call. Adding last_output_tokens (the assistant reply that's now
        in the history) and an estimate for the new user message gives a good
        approximation of what the next request will cost.

        Falls back to a character-based heuristic for the very first request.
        """
        if self._last_input_tokens is not None:
            new_msg_estimate = _estimate_message_tokens(messages[-1]) if messages else 0
            return (
                self._last_input_tokens
                + (self._last_output_tokens or 0)
                + new_msg_estimate
            )
        return sum(_estimate_message_tokens(m) for m in messages)

    def _should_summarize(self, messages: List[dict]) -> bool:
        if len(messages) <= self._config.min_recent_messages:
            return False
        return self._estimate_current_tokens(messages) > self._usable_token_budget()

    def _find_split_point(self, messages: List[dict]) -> int:
        """Find the index at which to split old vs. recent messages.

        Always locks in min_recent_messages from the tail, then greedily pulls
        in more messages (going backwards from the lock-in point) until adding
        the next older message would exceed the token budget. Uses the character
        heuristic for per-message sizing (the overall count comes from usage data).

        Returns 0 if even the minimum recent window exceeds the budget.
        """
        budget = self._usable_token_budget()
        min_keep_start = max(0, len(messages) - self._config.min_recent_messages)
        recent_tokens = sum(
            _estimate_message_tokens(m) for m in messages[min_keep_start:]
        )

        if recent_tokens >= budget:
            return 0

        split = min_keep_start
        for i in range(min_keep_start - 1, -1, -1):
            candidate = recent_tokens + _estimate_message_tokens(messages[i])
            if candidate > budget:
                break
            recent_tokens = candidate
            split = i

        return split

    async def _summarize(self, messages: List[dict]) -> str:
        """Use LLM to summarize a list of messages."""
        conversation_text = "\n".join(
            f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages
        )
        prompt = SUMMARIZATION_PROMPT.format(conversation=conversation_text)

        response = await self._llm_client.chat(
            messages=[Message(role="user", content=prompt)],
            system="You are a helpful assistant that summarizes conversations concisely.",
            tools=None,
            max_tokens=self._config.summary_max_tokens,
        )
        return response.text_content
