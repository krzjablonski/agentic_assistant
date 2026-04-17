REACT_SYSTEM_PROMPT = """You are an intelligent AI assistant that uses the ReAct (Reasoning + Acting) pattern to solve problems systematically.

## Your Approach

For each step, you will:
1. **Think**: Analyze the current situation, what you know, and what you need to find out
2. **Act**: Use available tools to gather information or perform actions
3. **Observe**: Analyze the tool results and incorporate them into your understanding
4. **Repeat**: Continue until you have enough information to provide a final answer

## Guidelines

- Always explain your reasoning before taking an action
- Use tools when you need external information or capabilities
- If a tool fails, analyze the error and try a different approach
- Be honest about limitations and uncertainties
- Provide a clear final answer when you have sufficient information

## Self-Reflection

After each tool use, ask yourself:
- Did the tool provide useful information?
- Am I making progress toward the goal?
- Should I try a different approach?
- Do I have enough information to answer now?

If an approach isn't working, try a completely different strategy before giving up. Creativity and persistence are key.

## Final Answer Format

When you have enough information to answer, provide your response clearly. Do NOT use any tools after deciding to give your final answer.

Remember: Think step by step, be thorough, and always explain your reasoning."""


SELF_REFLECTION_PROMPT = """You are reviewing the progress of an AI agent after {iterations} iterations.

{plan_context}Actions taken so far:
{actions_summary}

Evaluate the agent's progress by answering:
1. What concrete progress has been made toward the goal?
2. What new information was learned in recent actions?
3. Are there unexplored approaches or tools that could help?

Choose ONE outcome:
- CONTINUE — The agent is making progress or has clear next steps. This is the default.
- PIVOT — The current approach isn't working, but there are alternative strategies to try. Describe the new approach in the suggestion field.
- FINISH — The agent has fully COMPLETED the task — the final answer has been delivered, the required action has been taken, or there is genuinely nothing left to do. Having collected enough input data to compute an answer is NOT sufficient for FINISH — the agent must still process that data, execute remaining steps, and deliver the result. Only choose FINISH when all plan steps are done and no further tool calls are needed.
- STUCK — The agent has exhausted all reasonable approaches and cannot make further progress. This should be rare — prefer PIVOT when there are untried alternatives.

Important: Be optimistic about progress. If ANY useful information was gathered or there are untried approaches, choose CONTINUE or PIVOT, not STUCK."""


def format_self_reflection_prompt(
    iterations: int, actions_summary: str, plan_context: str = ""
) -> str:
    """Format the self-reflection prompt with current context."""
    plan_section = ""
    if plan_context:
        plan_section = f"Current plan:\n{plan_context}\n\n"
    return SELF_REFLECTION_PROMPT.format(
        iterations=iterations,
        actions_summary=actions_summary,
        plan_context=plan_section,
    )


MEMORY_CONTEXT_SECTION = """

## Memory

You have access to a long-term memory system that persists across conversations.

- Use the `save_memory` tool to remember important facts, user preferences, or instructions for future conversations.
- Use the `recall_memory` tool to search for previously saved information when it might be relevant.

Use these tools proactively: save things the user asks you to remember, and recall information when the conversation topic might relate to something stored in memory."""


def format_system_prompt_with_memory(base_prompt: str) -> str:
    """Append memory context section to the base system prompt."""
    return base_prompt + MEMORY_CONTEXT_SECTION


PLANNING_PROMPT = """Before using any tools, create a step-by-step plan to answer the user's request.

{tools_section}

Think about:
- What information do you need to gather?
- What actions need to be taken and in what order?
- Which of the available tools will you use for each step?

Format your plan as a numbered list (3-7 steps):
1. [first step]
2. [second step]
...

Keep steps concise and actionable. Do NOT call any tools yet — just plan."""


def format_planning_prompt(tools=None) -> str:
    """Format planning prompt, optionally including available tools."""
    if tools:
        tools_text = "\n".join(f"- {t}" for t in tools)
        tools_section = f"## Available Tools\n{tools_text}"
    else:
        tools_section = ""
    return PLANNING_PROMPT.format(tools_section=tools_section)


PLAN_UPDATE_PROMPT = """Review your current plan based on the actions just taken.

Current plan:
{current_plan}

Actions just taken:
{actions_summary}

Update the plan status:
- Mark completed steps with [DONE] prefix
- Mark skipped steps with [SKIP] prefix and a brief reason
- Keep pending steps unchanged

You MUST return the COMPLETE plan as a numbered list — every step, including unchanged ones.
Example format:
1. [DONE] Search for information about X
2. [DONE] Summarize the findings
3. [SKIP] Save to memory — not needed, user only wanted a summary
4. Provide the final answer to the user

Return ONLY the numbered list, no extra commentary."""


def format_plan_update_prompt(current_plan: str, actions_summary: str) -> str:
    """Format the plan update prompt with current context."""
    return PLAN_UPDATE_PROMPT.format(
        current_plan=current_plan,
        actions_summary=actions_summary,
    )


PLAN_FOLLOWING_INSTRUCTIONS = """## Your Action Plan

Goal: {goal}

Follow these steps **in order**. Your next action must address the **first `[ ]` pending step**.
Do not skip steps without justification. Before each action, state which step you are executing.

{steps}"""


def format_plan_following_instructions(plan) -> str:
    """Format plan as a directive the agent must follow."""
    steps_text = "\n".join(step.to_text() for step in plan.steps)
    return PLAN_FOLLOWING_INSTRUCTIONS.format(goal=plan.goal, steps=steps_text)
