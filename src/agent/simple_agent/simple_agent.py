from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, List, Type
from enum import Enum
from pydantic import BaseModel


from agent.i_agent import (
    IAgent,
    Message,
    TextContent,
    ThinkingContent,
    ToolUseContent,
    ToolResultContent,
)
from agent.message_factory import message_from_dict
from agent.agent_event import AgentEvent, AgentEventType
from agent.prompts.react_prompts import (
    REACT_SYSTEM_PROMPT,
    format_self_reflection_prompt,
    format_plan_update_prompt,
    format_plan_following_instructions,
    format_planning_prompt,
)
from agent.simple_agent.agent_plan import AgentPlan, PlanStep, PlanStepStatus
from llm.i_llm_client import ILLMClient, LLMResponse
from llm.anthropic_client import AnthropicClient
from tool_framework.tool_collection import ToolCollection
from tool_framework.i_tool import ITool, ToolResult
import asyncio
import json

try:
    from langfuse import observe, propagate_attributes

    _LANGFUSE_AVAILABLE = True
except ImportError:
    _LANGFUSE_AVAILABLE = False

    def observe(**kwargs):  # noqa: ARG001
        """No-op fallback when langfuse is not installed."""

        def decorator(fn):
            return fn

        return decorator

    def propagate_attributes(**kwargs):  # noqa: ARG001
        """No-op context manager fallback."""
        from contextlib import nullcontext

        return nullcontext()


class AgentStatus(Enum):
    RUNNING = "running"
    FINISHED = "finished"
    MAX_ITERATIONS = "max_iterations"
    STUCK = "stuck"
    ERROR = "error"


class ReflectionResult(BaseModel):
    """Structured output from self-reflection."""

    outcome: Literal["CONTINUE", "FINISH", "PIVOT", "STUCK"]
    reasoning: str
    suggestion: str = ""


class ReflectionOutcome(Enum):
    CONTINUE = "continue"
    FINISH = "finish"
    PIVOT = "pivot"
    STUCK = "stuck"


@dataclass
class AgentConfig:
    """Agent configuration."""

    max_iterations: int = 10
    reflection_interval: int = 3  # How often to check progress
    enable_self_reflection: bool = True
    enable_planning: bool = True
    max_tokens: int = 4096
    agent_name: Optional[str] = None
    session_id: Optional[str] = None  # Langfuse session ID for grouping traces


@dataclass
class IterationResult:
    """Result of a single iteration."""

    is_final_answer: bool = False
    final_answer: Optional[str] = None
    structured_data: Optional[dict] = None


class SimpleAgent(IAgent):
    """ReAct pattern agent implementation."""

    def __init__(
        self,
        system_prompt: str = REACT_SYSTEM_PROMPT,
        llm_client: Optional[ILLMClient] = None,
        tool_collection: Optional[ToolCollection] = None,
        config: Optional[AgentConfig] = None,
    ):
        config = config or AgentConfig()
        super().__init__(system_prompt, name=config.agent_name, session_id=config.session_id)
        self.llm_client = llm_client or AnthropicClient()
        self.tool_collection = tool_collection
        self.config = config
        self._actions_history: List[str] = []
        self._event_log: List[AgentEvent] = []
        self._status = AgentStatus.RUNNING
        self._plan: Optional[AgentPlan] = None
        self._structured_data: Optional[dict] = None
        self._response_schema: Optional[Type[BaseModel]] = None
        self._stuck_count: int = 0

    @observe(name="agent-run")
    async def run(
        self,
        user_query: str | List[dict],
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> str | dict:
        """
        Main ReAct agent loop.

        Executes Thought -> Action -> Observation cycle
        until final answer or iteration limit.
        """
        # Initialize
        self._iteration_count = 0
        self._actions_history = []
        self._event_log = []
        self._status = AgentStatus.RUNNING
        self._plan = None
        self._structured_data = None
        self._response_schema = response_schema
        self._stuck_count = 0
        self.clear_messages()

        # Build Langfuse propagation kwargs (session_id, agent_name)
        _lf_attrs = {}
        _lf_attrs["session_id"] = self.session_id
        if self.config.agent_name:
            _lf_attrs["tags"] = [self.config.agent_name]

        with propagate_attributes(**_lf_attrs):
            return await self._run_inner(user_query, response_schema)

    async def _run_inner(
        self,
        user_query: str | List[dict],
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> str | dict:
        if isinstance(user_query, list):
            for msg in user_query:
                if isinstance(msg, Message):
                    self.add_message(msg)
                else:
                    self.add_message(message_from_dict(msg))
            last = user_query[-1] if user_query else None
            query_str = (
                str(
                    last.content
                    if isinstance(last, Message)
                    else last.get("content", "")
                )
                if last
                else ""
            )
        else:
            self.add_message(Message(role="user", content=user_query))
            query_str = user_query

        if len(query_str) > 1000:
            query_str = query_str[:500] + "...[TRUNCATED]..." + query_str[-500:]

        self._emit_event(
            AgentEventType.USER_MESSAGE,
            "User query received",
            {"query": query_str},
        )

        # Create initial plan before entering the main loop
        if self.config.enable_planning:
            await self._create_initial_plan(query_str)

        while self._status == AgentStatus.RUNNING:
            self._iteration_count += 1

            # Check iteration limit
            if self._iteration_count > self.config.max_iterations:
                self._status = AgentStatus.MAX_ITERATIONS
                self._emit_event(
                    AgentEventType.STATUS_CHANGE,
                    f"Status: {self._status.value}",
                    {"status": self._status.value},
                )
                return self._handle_max_iterations()

            # Self-reflection every N iterations
            if (
                self.config.enable_self_reflection
                and self._iteration_count > 1
                and self._iteration_count % self.config.reflection_interval == 0
            ):
                reflection_outcome = await self._perform_self_reflection()

                if reflection_outcome == ReflectionOutcome.FINISH:
                    self._status = AgentStatus.FINISHED
                    self._emit_event(
                        AgentEventType.STATUS_CHANGE,
                        f"Status: {self._status.value}",
                        {"status": self._status.value},
                    )
                    finish_result = await self._handle_reflection_finish()
                    if finish_result is not None:
                        return finish_result
                    # Agent made tool calls — continue the main loop

                elif reflection_outcome == ReflectionOutcome.STUCK:
                    self._status = AgentStatus.STUCK
                    self._emit_event(
                        AgentEventType.STATUS_CHANGE,
                        f"Status: {self._status.value}",
                        {"status": self._status.value},
                    )
                    return self._handle_stuck()

                # PIVOT and CONTINUE just proceed to next iteration

            # Execute ReAct iteration
            try:
                result: IterationResult = await self._execute_iteration()

                if result.is_final_answer:
                    self._status = AgentStatus.FINISHED
                    self._emit_event(
                        AgentEventType.STATUS_CHANGE,
                        f"Status: {self._status.value}",
                        {"status": self._status.value},
                    )
                    if result.structured_data is not None:
                        self._structured_data = result.structured_data
                        return result.structured_data
                    return result.final_answer

            except Exception as e:
                self._status = AgentStatus.ERROR
                self._emit_event(
                    AgentEventType.STATUS_CHANGE,
                    f"Status: {self._status.value}",
                    {"status": self._status.value},
                )
                return self._handle_error(e)

        return self._get_fallback_response()

    @observe(name="agent-iteration")
    async def _execute_iteration(self) -> IterationResult:
        """Execute single ReAct iteration."""

        # Get tools schema if available
        tools: Optional[List[ITool]] = self._get_tools()

        response: LLMResponse = await self.llm_client.chat(
            messages=self.get_messages(),
            system=self._build_system_prompt_with_plan(),
            tools=tools,
            max_tokens=self.config.max_tokens,
        )

        self._emit_event(
            AgentEventType.LLM_RESPONSE,
            f"LLM responded (stop_reason={response.stop_reason})",
            {
                "stop_reason": response.stop_reason,
                "usage": response.usage,
                "has_tool_use": response.has_tool_use,
                "tools_to_be_used": [
                    block.name for block in response.content if hasattr(block, "name")
                ],
            },
        )

        # Analyze response
        if response.has_tool_use:
            result = await self._handle_tool_use(response)
            if self.config.enable_planning and self._plan is not None:
                await self._update_plan()
            return result
        else:
            return await self._handle_text_response(response)

    async def _handle_tool_use(self, response: LLMResponse) -> IterationResult:
        """Handle response with tool use. Executes multiple tools in parallel."""

        content_blocks = []
        tool_use_blocks = []

        for block in response.content:
            if hasattr(block, "thinking"):
                # Thinking/reasoning block from Anthropic or Gemini
                content_blocks.append(
                    ThinkingContent(
                        thinking=block.thinking,
                        signature=getattr(block, "signature", None),
                    )
                )
                self._emit_event(
                    AgentEventType.REASONING,
                    f"Agent reasoning: {block.thinking[:200]}...",
                    {"text": block.thinking},
                )
            elif hasattr(block, "text"):
                content_blocks.append(TextContent(text=block.text))
                self._emit_event(
                    AgentEventType.REASONING,
                    f"Agent reasoning: {block.text}",
                    {"text": block.text},
                )
            elif hasattr(block, "name"):
                content_blocks.append(
                    ToolUseContent(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                        extra=getattr(block, "extra", None) or {},
                    )
                )
                self._emit_event(
                    AgentEventType.TOOL_CALL,
                    f"Calling tool: {block.name}",
                    {"tool_name": block.name, "args": block.input},
                )
                tool_use_blocks.append(block)

        # Execute all tools in parallel
        results: list[ToolResult] = [None] * len(tool_use_blocks)

        async with asyncio.TaskGroup() as tg:
            for i, block in enumerate(tool_use_blocks):

                async def run(idx=i, block=block):
                    results[idx] = await self._execute_tool(block.name, block.input)

                tg.create_task(run())

        # Collect results in original order
        tool_results = []
        for i, block in enumerate(tool_use_blocks):
            result = results[i]
            self._emit_event(
                AgentEventType.TOOL_RESULT,
                f"Tool result: {result.result}",
                {
                    "tool_name": block.name,
                    "result": result.result,
                    "is_error": result.is_error,
                },
            )
            tool_results.append(
                ToolResultContent(
                    tool_use_id=block.id,
                    content=result.result,
                    is_error=result.is_error,
                )
            )
            self._actions_history.append(
                f"Tool '{block.name}' with args: {block.input}"
            )

        # Add messages in correct order
        self.add_message(Message(role="assistant", content=content_blocks))
        self.add_message(Message(role="user", content=tool_results))

        return IterationResult(is_final_answer=False)

    async def _handle_text_response(self, response: LLMResponse) -> IterationResult:
        """Handle text response (no tools = final answer)."""

        text = response.text_content
        self._emit_event(
            AgentEventType.ASSISTANT_MESSAGE,
            "Assistant text response",
            {
                "text": text,
                "stop_reason": response.stop_reason,
            },
        )
        self.add_text_message("assistant", text)

        if response.stop_reason == "max_tokens":
            self.add_text_message(
                "user",
                "Continue from exactly where you stopped. Do not restart the analysis, "
                "do not repeat previous text unless needed, and finish the task.",
            )
            return IterationResult(is_final_answer=False)

        if self._response_schema:
            structured = await self._get_structured_output()
            return IterationResult(
                is_final_answer=True, final_answer=text, structured_data=structured
            )

        return IterationResult(is_final_answer=True, final_answer=text)

    async def _get_structured_output(self) -> Optional[dict]:
        """Make one final LLM call with response_schema to produce structured output."""
        self.add_text_message(
            "user",
            "Please provide your answer in the required structured format.",
        )
        response = await self.llm_client.chat(
            messages=self.get_messages(),
            system=self._build_system_prompt_with_plan(),
            tools=None,
            response_schema=self._response_schema,
        )
        return response.structured_data

    @observe(name="tool-execution")
    async def _execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        """Execute tool with error handling."""
        try:
            tool = self.tool_collection.get_tool(tool_name)
            tool.validate_parameters(args)
            return await tool.run(args)
        except ValueError as e:
            return ToolResult(
                tool_name=tool_name,
                parameters=args,
                result=f"Error: {str(e)}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_name=tool_name,
                parameters=args,
                result=f"Error: Unexpected error - {str(e)}",
                is_error=True,
            )

    @observe(name="self-reflection")
    async def _perform_self_reflection(self) -> ReflectionOutcome:
        """
        Check if agent is making progress using structured output.
        Returns ReflectionOutcome indicating what the agent should do next.
        Applies strike count: first STUCK is downgraded to PIVOT.
        """
        actions_summary = "\n".join(self._actions_history[-5:])
        plan_context = self._plan.to_text() if self._plan else ""
        reflection_prompt = format_self_reflection_prompt(
            iterations=self._iteration_count,
            actions_summary=actions_summary,
            plan_context=plan_context,
        )

        # Send reflection query with structured output
        response = await self.llm_client.chat(
            messages=self.get_messages()
            + [Message(role="user", content=reflection_prompt)],
            system=self._build_system_prompt_with_plan(),
            tools=None,
            response_schema=ReflectionResult,
        )

        # Parse structured response
        data = response.structured_data
        if data and "outcome" in data:
            raw_outcome = data["outcome"].upper()
            reasoning = data.get("reasoning", "")
            suggestion = data.get("suggestion", "")
        else:
            # Fallback: if structured output fails, default to CONTINUE
            raw_outcome = "CONTINUE"
            reasoning = response.text_content
            suggestion = ""

        # Map to ReflectionOutcome
        outcome_map = {
            "CONTINUE": ReflectionOutcome.CONTINUE,
            "FINISH": ReflectionOutcome.FINISH,
            "PIVOT": ReflectionOutcome.PIVOT,
            "STUCK": ReflectionOutcome.STUCK,
        }
        outcome = outcome_map.get(raw_outcome, ReflectionOutcome.CONTINUE)

        # Strike count: first STUCK is downgraded to PIVOT
        if outcome == ReflectionOutcome.STUCK:
            self._stuck_count += 1
            if self._stuck_count < 2:
                outcome = ReflectionOutcome.PIVOT
                suggestion = suggestion or "Try a completely different approach."
        else:
            self._stuck_count = 0

        # For PIVOT: inject suggestion into conversation
        if outcome == ReflectionOutcome.PIVOT and suggestion:
            self.add_text_message(
                "user",
                f"Reflection: your current approach isn't working. "
                f"Try this instead: {suggestion}",
            )

        self._emit_event(
            AgentEventType.SELF_REFLECTION,
            f"Self-reflection: {outcome.value}",
            {
                "reasoning": reasoning,
                "suggestion": suggestion,
                "outcome": outcome.value,
                "stuck_count": self._stuck_count,
                "actions_reviewed": self._actions_history[-5:],
            },
        )

        return outcome

    def _build_system_prompt_with_plan(self) -> str:
        """Build system prompt, optionally appending the current plan as a directive."""
        if self._plan is None:
            return self.system_prompt
        return (
            f"{self.system_prompt}\n\n{format_plan_following_instructions(self._plan)}"
        )

    @observe(name="create-plan")
    async def _create_initial_plan(self, query: str) -> None:
        """Create an initial plan before entering the main ReAct loop."""
        tools = self.tool_collection.get_tools() if self.tool_collection else None
        planning_prompt = format_planning_prompt(tools)
        response = await self.llm_client.chat(
            messages=[
                Message(
                    role="user", content=f"{planning_prompt}\n\nUser request: {query}"
                )
            ],
            system=self.system_prompt,
            tools=None,
        )

        plan_text = response.text_content
        steps = self._parse_plan_steps(plan_text)
        self._plan = AgentPlan(goal=query[:200], steps=steps)

        self._emit_event(
            AgentEventType.PLAN_CREATED,
            "Initial plan created",
            {"plan": self._plan.to_text(), "steps_count": len(steps)},
        )

    @observe(name="update-plan")
    async def _update_plan(self) -> None:
        """Update plan based on actions taken so far."""
        if self._plan is None:
            return

        recent_actions = self._actions_history[-5:]
        actions_summary = (
            "\n".join(f"- {entry}" for entry in recent_actions)
            if recent_actions
            else "No actions yet."
        )
        update_prompt = format_plan_update_prompt(
            current_plan=self._plan.to_text(),
            actions_summary=actions_summary,
        )

        response = await self.llm_client.chat(
            messages=self.get_messages()
            + [Message(role="user", content=update_prompt)],
            system=self.system_prompt,
            tools=None,
        )

        updated_steps = self._parse_plan_steps(response.text_content)

        if updated_steps:
            from datetime import datetime

            self._plan.steps = updated_steps
            self._plan.last_updated_at = datetime.now()

        self._emit_event(
            AgentEventType.PLAN_UPDATED,
            "Plan updated",
            {
                "plan": self._plan.to_text(),
                "updated_steps": [step.to_text() for step in updated_steps],
            },
        )

    def _parse_plan_steps(self, plan_text: str) -> List[PlanStep]:
        """Parse numbered list from LLM response into PlanStep objects."""
        import re

        steps = []
        step_number = 0

        for line in plan_text.splitlines():
            line = line.strip()
            match = re.match(r"^(\d+)\.\s+(.+)$", line)
            if match:
                step_number += 1
                description = match.group(2).strip()
                status = PlanStepStatus.PENDING

                if description.startswith("[DONE]"):
                    status = PlanStepStatus.COMPLETED
                    description = description[6:].strip()
                elif description.startswith("[SKIP]"):
                    status = PlanStepStatus.SKIPPED
                    description = description[6:].strip()

                steps.append(
                    PlanStep(
                        step_number=step_number,
                        description=description,
                        status=status,
                    )
                )

        return steps

    def _get_tools(self) -> Optional[List[ITool]]:
        """Get tools list for LLM."""
        if self.tool_collection:
            return self.tool_collection.get_tools()
        return None

    def _handle_max_iterations(self) -> str:
        """Handle iteration limit reached."""
        return (
            f"I've reached the maximum number of iterations ({self.config.max_iterations}) "
            f"without finding a complete answer. Based on my progress so far, "
            f"here's what I've learned:\n\n"
            f"{self._summarize_progress()}"
        )

    async def _handle_reflection_finish(self) -> str:
        """Handle FINISH outcome from self-reflection by generating a final answer.

        Tools are provided so the agent can take final actions (e.g., submit answers).
        If the agent makes tool calls, execution continues in the main loop.
        """
        self.add_text_message(
            "user",
            "Based on all the information you've gathered, provide your final answer now. "
            "If you still need to take actions (e.g., submit an answer), use the appropriate tools.",
        )

        tools = self._get_tools()
        response: LLMResponse = await self.llm_client.chat(
            messages=self.get_messages(),
            system=self._build_system_prompt_with_plan(),
            tools=tools,
        )

        # If the agent wants to use tools, let it — resume the main loop
        if response.has_tool_use:
            await self._handle_tool_use(response)
            if self.config.enable_planning and self._plan is not None:
                await self._update_plan()
            # Don't finish yet — re-enter the main loop
            self._status = AgentStatus.RUNNING
            return None  # sentinel: caller checks for None to continue

        final_answer: str = response.text_content
        self.add_text_message("assistant", final_answer)

        if self._response_schema:
            structured = await self._get_structured_output()
            self._structured_data = structured
            return structured

        return final_answer

    def _handle_stuck(self) -> str:
        """Handle stuck state."""
        return (
            "I noticed I'm not making meaningful progress on this task. "
            "Here's what I've attempted and learned:\n\n"
            f"{self._summarize_progress()}\n\n"
            "Would you like me to try a different approach or provide "
            "more specific guidance?"
        )

    def _handle_error(self, error: Exception) -> str:
        """Handle errors."""
        self._emit_event(
            AgentEventType.ERROR,
            f"Error: {str(error)}",
            {"error_type": type(error).__name__, "error_message": str(error)},
        )
        return f"I encountered an error while processing your request: {str(error)}"

    def _summarize_progress(self) -> str:
        """Summarize agent progress."""
        if not self._actions_history:
            return "No actions were taken."

        return "Actions taken:\n" + "\n".join(
            f"- {action}" for action in self._actions_history
        )

    def _get_fallback_response(self) -> str:
        """Fallback response."""
        return "I was unable to complete the task. Please try rephrasing your request."

    def get_conversation_summary(self) -> str:
        """Return conversation summary."""
        return "\n".join(
            f"{message.role}: {message.content if isinstance(message.content, str) else '[complex content]'}"
            for message in self.get_messages()
        )

    @property
    def status(self) -> AgentStatus:
        """Get current agent status."""
        return self._status

    @property
    def iteration_count(self) -> int:
        """Get current iteration count."""
        return self._iteration_count

    @property
    def event_log(self) -> List[AgentEvent]:
        """Get the event log from the last run."""
        return self._event_log

    @property
    def plan(self) -> Optional[AgentPlan]:
        """Get the current agent plan."""
        return self._plan

    @property
    def structured_data(self) -> Optional[dict]:
        """Structured output from the last run, if response_schema was provided."""
        return self._structured_data
