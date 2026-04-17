import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_client.mcp_tool import MCPTool
from tool_framework.i_tool import ITool

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: Optional[dict[str, str]] = None


class MCPManager:
    """Manages MCP server connections and provides tools as ITool instances."""

    def __init__(self, config_path: str = "mcp_config.json"):
        self._config_path = config_path
        self._tools: list[ITool] = []
        self._exit_stack: Optional[AsyncExitStack] = None
        self._started = False

    async def start(self) -> list[ITool]:
        """Start all MCP servers and return discovered tools."""
        if self._started:
            return self._tools

        configs = self._load_config()
        if not configs:
            return []

        self._tools = await self._connect_all(configs)
        self._started = True
        return self._tools

    async def stop(self) -> None:
        """Shut down all MCP connections."""
        if not self._started:
            return
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                logger.warning("Error closing MCP sessions", exc_info=True)
        self._started = False
        self._tools = []

    async def _connect_all(self, configs: list[MCPServerConfig]) -> list[ITool]:
        """Connect to all configured MCP servers."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        all_tools: list[ITool] = []

        for cfg in configs:
            try:
                tools = await self._connect_server(cfg)
                all_tools.extend(tools)
                logger.info(f"MCP server '{cfg.name}': {len(tools)} tool(s) loaded")
            except Exception as e:
                logger.error(f"Failed to connect to MCP server '{cfg.name}': {e}")

        return all_tools

    async def _connect_server(self, cfg: MCPServerConfig) -> list[ITool]:
        """Connect to a single MCP server and return its tools as ITool instances."""
        server_params = StdioServerParameters(
            command=cfg.command, args=cfg.args, env=cfg.env
        )
        read, write = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        session: ClientSession = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await session.initialize()

        response = await session.list_tools()
        tools: list[ITool] = []
        for mcp_tool in response.tools:
            prefixed_name = f"{cfg.name}__{mcp_tool.name}"
            tool = MCPTool(
                name=prefixed_name,
                mcp_name=mcp_tool.name,
                description=f"[{cfg.name}] {mcp_tool.description}",
                input_schema=mcp_tool.inputSchema,
                session=session,
            )
            tools.append(tool)
        return tools

    def _load_config(self) -> list[MCPServerConfig]:
        """Load MCP server configurations from JSON file."""
        path = Path(self._config_path)
        if not path.exists():
            logger.info(f"No MCP config found at {path}")
            return []

        with open(path, "r") as f:
            data = json.load(f)

        configs = []
        for name, server_data in data.get("mcpServers", {}).items():
            configs.append(
                MCPServerConfig(
                    name=name,
                    command=server_data["command"],
                    args=server_data.get("args", []),
                    env=server_data.get("env"),
                )
            )
        return configs

    @property
    def tools(self) -> list[ITool]:
        return self._tools

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
