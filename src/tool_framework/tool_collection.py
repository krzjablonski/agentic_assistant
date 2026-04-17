from typing import List
from tool_framework.i_tool import ITool


class ToolCollection:
    def __init__(self, tools: List[ITool]):
        self.tools = tools

    def get_tool(self, tool_name: str) -> ITool:
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        raise ValueError(f"Tool {tool_name} not found")

    def get_tools(self) -> List[ITool]:
        return self.tools

    def add_tool(self, tool: ITool):
        self.tools.append(tool)

    def remove_tool(self, tool_name: str):
        for tool in self.tools:
            if tool.name == tool_name:
                self.tools.remove(tool)
                return
        raise ValueError(f"Tool {tool_name} not found")
