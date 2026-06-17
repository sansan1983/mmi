"""mmi.core.mcp_server —— Model Context Protocol (MCP) Server 实现。

P4-3: 让 MMI 作为 MCP Server，为 Cursor / Claude Desktop 等工具提供工具调用能力。

暴露的能力（MCP Tools）:
  - mmi_list_sessions: 列出所有会话
  - mmi_get_session: 获取会话详情
  - mmi_chat: 发送消息并获取回复
  - mmi_list_skills: 列出已注册技能
  - mmi_search_memory: 搜索记忆
  - mmi_get_stats: 获取系统统计信息

协议参考: https://modelcontextprotocol.io/
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, ClassVar

__all__ = [
    "MCPTool",
    "MCPRequest",
    "MCPResponse",
    "MCPServer",
]


@dataclass
class MCPTool:
    """An MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
    })
    handler: Any | None = None
    """Callable(tool_input: dict) -> Any"""


@dataclass
class MCPRequest:
    """Incoming MCP request."""

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None


@dataclass
class MCPResponse:
    """Outgoing MCP response."""

    id: int | str | None = None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


class MCPServer:
    """MCP Server implementation (stdio transport).

    Usage::

        server = MCPServer()
        server.register_tool(my_tool)

        # Process a JSON-RPC request:
        response = server.handle_request(request_dict)

    For stdio transport with Claude Desktop, register in config.json::

        {
            "mcpServers": {
                "mmi": {
                    "command": "python",
                    "args": ["-m", "mmi.core.mcp_server"]
                }
            }
        }
    """

    _instance: ClassVar[MCPServer | None] = None

    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}
        self._lock = threading.RLock()
        self._server_info = {
            "name": "mmi",
            "version": "0.1.0",
        }
        self._setup_default_tools()

    @classmethod
    def get_instance(cls: type[MCPServer]) -> MCPServer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls: type[MCPServer]) -> None:
        cls._instance = None

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool."""
        with self._lock:
            self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> None:
        """Remove a tool."""
        with self._lock:
            self._tools.pop(name, None)

    def list_tools(self) -> list[MCPTool]:
        """Return all registered tools."""
        with self._lock:
            return list(self._tools.values())

    # ------------------------------------------------------------------
    # Default tools (stubs)
    # ------------------------------------------------------------------

    def _setup_default_tools(self) -> None:
        """Register built-in MCP tools (stub implementations)."""

        self.register_tool(MCPTool(
            name="mmi_list_sessions",
            description="List all MMI sessions",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max sessions to return"},
                },
            },
            handler=lambda params: {"sessions": [], "total": 0},
        ))

        self.register_tool(MCPTool(
            name="mmi_get_session",
            description="Get details of a specific session",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                },
                "required": ["session_id"],
            },
            handler=lambda params: {"session_id": params.get("session_id"), "found": False},
        ))

        self.register_tool(MCPTool(
            name="mmi_chat",
            description="Send a message to MMI and get a response",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID (optional, creates new if empty)"},
                    "message": {"type": "string", "description": "User message"},
                },
                "required": ["message"],
            },
            handler=lambda params: {"reply": "[echo] " + params.get("message", "")},
        ))

        self.register_tool(MCPTool(
            name="mmi_list_skills",
            description="List registered skills in the SkillLibrary",
            input_schema={"type": "object", "properties": {}},
            handler=lambda params: {"skills": []},
        ))

        self.register_tool(MCPTool(
            name="mmi_search_memory",
            description="Search MMI memory/knowledge base",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"],
            },
            handler=lambda params: {"results": [], "query": params.get("query", "")},
        ))

        self.register_tool(MCPTool(
            name="mmi_get_stats",
            description="Get MMI system statistics",
            input_schema={"type": "object", "properties": {}},
            handler=lambda params: {
                "total_sessions": 0,
                "total_skills": 0,
                "total_memories": 0,
            },
        ))

    # ------------------------------------------------------------------
    # Request handling (JSON-RPC 2.0)
    # ------------------------------------------------------------------

    def handle_request(self, raw: dict[str, Any]) -> MCPResponse:
        """Handle a JSON-RPC 2.0 request.

        Parameters
        ----------
        raw : dict
            Parsed JSON-RPC request.

        Returns
        -------
        MCPResponse
        """
        method = raw.get("method", "")
        params = raw.get("params", {})
        req_id = raw.get("id")

        # --- initialize ---
        if method == "initialize":
            return MCPResponse(
                id=req_id,
                result={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": self._server_info,
                },
            )

        # --- tools/list ---
        if method == "tools/list":
            tools_info = []
            for tool in self.list_tools():
                tools_info.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                })
            return MCPResponse(id=req_id, result={"tools": tools_info})

        # --- tools/call ---
        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_input = params.get("arguments", {})

            with self._lock:
                tool = self._tools.get(tool_name)

            if tool is None:
                return MCPResponse(
                    id=req_id,
                    error={"code": -32601, "message": f"Tool not found: {tool_name}"},
                )

            try:
                result = tool.handler(tool_input) if tool.handler else {"error": "No handler registered"}
                return MCPResponse(
                    id=req_id,
                    result={
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                        ],
                    },
                )
            except Exception as e:
                return MCPResponse(
                    id=req_id,
                    error={"code": -32000, "message": str(e)},
                )

        # --- notifications (no response needed) ---
        if req_id is None:
            return MCPResponse()

        # --- unknown method ---
        return MCPResponse(
            id=req_id,
            error={"code": -32601, "message": f"Method not found: {method}"},
        )
