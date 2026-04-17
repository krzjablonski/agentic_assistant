from datetime import datetime
from tool_framework.i_tool import ToolResult, ITool


class CurrentDateTool(ITool):
    def __init__(self):
        super().__init__(
            name="current_date",
            description="Get current date",
            parameters=[],
        )

    def validate_parameters(self, args: dict) -> None:
        # LLMs often hallucinate arguments when the schema is empty.
        # Since this tool requires no parameters, we intentionally ignore any passed arguments.
        pass

    async def run(self, args: dict) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            result=f"Current date: {datetime.now().strftime('%Y-%m-%d')}",
            parameters=[],
        )
