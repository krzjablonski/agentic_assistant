from memory.long_term_memory import LongTermMemory, MEMORY_CATEGORIES
from tool_framework.i_tool import ITool, ToolParameter, ToolResult


class SaveMemoryTool(ITool):
    """Tool for saving information to long-term memory."""

    def __init__(self, long_term_memory: LongTermMemory):
        self._memory = long_term_memory
        super().__init__(
            name="save_memory",
            description=(
                "Save an important fact, user preference, or piece of information "
                "to long-term memory so it can be recalled in future conversations. "
                "Use this when the user shares personal preferences, important facts, "
                "or explicitly asks you to remember something."
            ),
            parameters=[
                ToolParameter(
                    name="content",
                    type="string",
                    required=True,
                    default=None,
                    description=(
                        "The information to remember. Be specific and self-contained, "
                        "e.g. 'User prefers morning meetings before 10 AM'."
                    ),
                ),
                ToolParameter(
                    name="category",
                    type="string",
                    required=False,
                    default="general",
                    description=(
                        f"Category for the memory. "
                        f"Allowed values: {', '.join(MEMORY_CATEGORIES)}."
                    ),
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)
        content = args["content"]
        category = args.get("category", "general")

        try:
            memory_id = self._memory.save(content=content, category=category)
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Memory saved successfully (id={memory_id}, category='{category}').",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to save memory - {str(e)}",
            )
