from typing import Any
from mcp import ClientSession

from tool_framework.i_tool import ITool, ToolParameter, ToolResult


class MCPTool(ITool):
    """Adapter that wraps a single MCP server tool as an ITool."""

    def __init__(
        self,
        name: str,
        mcp_name: str,
        description: str,
        input_schema: dict,
        session: ClientSession,
    ):
        parameters = self._schema_to_parameters(input_schema)
        super().__init__(name=name, description=description, parameters=parameters)
        self.mcp_name = mcp_name
        self.input_schema = input_schema
        self._session = session

    async def run(self, args: dict[str, any]) -> ToolResult:
        """Call the MCP tool directly via await."""
        try:
            mcp_result = await self._session.call_tool(self.mcp_name, args)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                parameters=args,
                result=f"MCP call failed: {e}",
                is_error=True,
            )

        text_parts = []
        is_error = getattr(mcp_result, "isError", False)
        for item in mcp_result.content:
            if hasattr(item, "text"):
                text_parts.append(item.text)
            else:
                text_parts.append(str(item))

        return ToolResult(
            tool_name=self.name,
            parameters=args,
            result="\n".join(text_parts),
            is_error=is_error,
        )

    @staticmethod
    def _schema_to_parameters(schema: dict) -> list[ToolParameter]:
        """Best-effort conversion of JSON Schema to ToolParameter list."""
        params = []
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        for prop_name, prop_schema in properties.items():
            params.append(
                ToolParameter(
                    name=prop_name,
                    type=prop_schema.get("type", "any"),
                    required=prop_name in required,
                    default=prop_schema.get("default"),
                    description=prop_schema.get("description", ""),
                )
            )
        return params
