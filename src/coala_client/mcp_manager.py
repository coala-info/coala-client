"""MCP server manager for handling multiple MCP servers."""

import os
import json
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool
from openai.types.chat import ChatCompletionToolParam

from .config import Config, MCPServerConfig


class MCPServerConnection:
    """Represents a connection to an MCP server."""

    def __init__(self, name: str, session: ClientSession) -> None:
        """Initialize the connection.

        Args:
            name: Server name.
            session: Client session.
        """
        self.name = name
        self.session = session
        self.tools: list[Tool] = []

    async def initialize(self) -> None:
        """Initialize the connection and fetch available tools."""
        await self.session.initialize()
        tools_result = await self.session.list_tools()
        self.tools = tools_result.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on this server.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result as string.
        """
        result = await self.session.call_tool(name, arguments)

        # Extract text content from result
        contents = []
        for content in result.content:
            if hasattr(content, "text"):
                contents.append(content.text)
            elif hasattr(content, "data"):
                contents.append(f"[Binary data: {content.mime_type}]")
            else:
                contents.append(str(content))

        return "\n".join(contents)


class MCPManager:
    """Manager for multiple MCP server connections."""

    def __init__(self, config: Config) -> None:
        """Initialize the MCP manager.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.connections: dict[str, MCPServerConnection] = {}
        self._exit_stack: AsyncExitStack | None = None
        # Map tool names to server names
        self._tool_to_server: dict[str, str] = {}

    async def __aenter__(self) -> "MCPManager":
        """Enter async context."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        if self._exit_stack:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)

    async def connect_server(
        self,
        name: str,
        server_config: MCPServerConfig,
    ) -> MCPServerConnection:
        """Connect to an MCP server.

        Args:
            name: Server name.
            server_config: Server configuration.

        Returns:
            The server connection.
        """
        if self._exit_stack is None:
            raise RuntimeError("MCPManager must be used as async context manager")

        # Merge server-specific env with current environment
        # Start with current environment, then override with server-specific
        merged_env = dict(os.environ)
        if server_config.env:
            merged_env.update(server_config.env)

        params = StdioServerParameters(
            command=server_config.command,
            args=server_config.args,
            env=merged_env,
        )

        read, write = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        connection = MCPServerConnection(name, session)
        await connection.initialize()

        self.connections[name] = connection

        # Map tools to this server
        for tool in connection.tools:
            self._tool_to_server[tool.name] = name

        return connection

    async def connect_all_servers(self) -> dict[str, MCPServerConnection]:
        """Connect to all configured MCP servers.

        Returns:
            Dictionary of server connections.
        """
        from rich.console import Console
        console = Console()

        servers = self.config.get_mcp_servers()

        for name, server_config in servers.items():
            try:
                console.print(f"[dim]Connecting to MCP server '{name}'...[/dim]")
                await self.connect_server(name, server_config)
                console.print(f"[green]✓ Connected to '{name}' ({len(self.connections[name].tools)} tools)[/green]")
            except Exception as e:
                # Log error but continue with other servers
                console.print(f"[red]✗ Failed to connect to MCP server '{name}': {e}[/red]")

        return self.connections

    def get_all_tools(self) -> list[Tool]:
        """Get all tools from all connected servers.

        Returns:
            List of all available tools.
        """
        tools = []
        for connection in self.connections.values():
            tools.extend(connection.tools)
        return tools

    def get_openai_tools(self) -> list[ChatCompletionToolParam]:
        """Get all tools in OpenAI tool format.

        Returns:
            List of tools in OpenAI format.
        """
        openai_tools: list[ChatCompletionToolParam] = []

        for tool in self.get_all_tools():
            openai_tool: ChatCompletionToolParam = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool by name.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result as string.
        """
        server_name = self._tool_to_server.get(name)
        if not server_name:
            return f"Error: Tool '{name}' not found"

        connection = self.connections.get(server_name)
        if not connection:
            return f"Error: Server '{server_name}' not connected"

        try:
            return await connection.call_tool(name, arguments)
        except Exception as e:
            return f"Error calling tool '{name}': {e}"

    def execute_tool_sync(self, name: str, arguments: dict[str, Any]) -> str:
        """Synchronous wrapper for tool execution (for use with LLM client).

        Note: This is a placeholder that will be replaced with actual async
        execution in the chat loop.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result as string.
        """
        # This will be overridden in the chat implementation
        return json.dumps({"tool": name, "arguments": arguments, "status": "pending"})
