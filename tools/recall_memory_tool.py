from memory.long_term_memory import LongTermMemory, MEMORY_CATEGORIES
from tool_framework.i_tool import ITool, ToolParameter, ToolResult


class RecallMemoryTool(ITool):
    """Tool for searching and recalling information from long-term memory."""

    def __init__(self, long_term_memory: LongTermMemory):
        self._memory = long_term_memory
        super().__init__(
            name="recall_memory",
            description=(
                "Search long-term memory for previously saved information. "
                "Use this when you need to recall facts, user preferences, "
                "or other information that was saved in a previous conversation."
            ),
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    required=True,
                    default=None,
                    description="Search query to find relevant memories. Use keywords.",
                ),
                ToolParameter(
                    name="category",
                    type="string",
                    required=False,
                    default=None,
                    description=(
                        "Optional category filter. "
                        f"Allowed values: {', '.join(MEMORY_CATEGORIES)}."
                    ),
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    required=False,
                    default=5,
                    description="Maximum number of memories to return (default: 5).",
                ),
            ],
        )

    async def run(self, args: dict) -> ToolResult:
        self.validate_parameters(args)
        query = args["query"]
        category = args.get("category")
        limit = args.get("limit", 5)

        try:
            entries = self._memory.recall(
                query=query, category=category, limit=limit
            )

            if not entries:
                return ToolResult(
                    tool_name=self.name,
                    parameters=args,
                    result=f"No memories found matching '{query}'.",
                )

            lines = [f"Found {len(entries)} memory/memories:\n"]
            for entry in entries:
                lines.append(
                    f"- [{entry.category}] (id={entry.id}, saved={entry.created_at}): "
                    f"{entry.content}"
                )

            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result="\n".join(lines),
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"Error: Failed to recall memories - {str(e)}",
            )
