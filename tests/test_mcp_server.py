"""tests/test_mcp_server.py —— P4-3 MCP Server 测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.mcp_server import MCPServer, MCPTool, MCPResponse


def _server() -> MCPServer:
    MCPServer.reset_instance()
    return MCPServer()


# ---------------------------------------------------------------------------
# Initialize
# ---------------------------------------------------------------------------

def test_initialize():
    s = _server()
    resp = s.handle_request({"method": "initialize", "id": 1})
    assert resp.result is not None
    assert resp.result["protocolVersion"] == "2024-11-05"
    assert resp.result["serverInfo"]["name"] == "mmi"
    assert resp.error is None


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------

def test_tools_list():
    s = _server()
    resp = s.handle_request({"method": "tools/list", "id": 2})
    tools = resp.result["tools"]
    assert len(tools) >= 6
    names = {t["name"] for t in tools}
    assert "mmi_list_sessions" in names
    assert "mmi_chat" in names
    assert "mmi_search_memory" in names


def test_tools_list_includes_custom():
    s = _server()
    s.register_tool(MCPTool(
        name="custom_tool",
        description="A custom tool",
        handler=lambda p: {"ok": True},
    ))
    resp = s.handle_request({"method": "tools/list", "id": 3})
    names = {t["name"] for t in resp.result["tools"]}
    assert "custom_tool" in names


# ---------------------------------------------------------------------------
# tools/call
# ---------------------------------------------------------------------------

def test_call_builtin_tool():
    s = _server()
    resp = s.handle_request({
        "method": "tools/call",
        "id": 4,
        "params": {
            "name": "mmi_list_sessions",
            "arguments": {"limit": 10},
        },
    })
    assert resp.error is None
    content = resp.result["content"]
    assert len(content) == 1
    data = json.loads(content[0]["text"])
    assert "sessions" in data


def test_call_chat_tool():
    s = _server()
    resp = s.handle_request({
        "method": "tools/call",
        "id": 5,
        "params": {
            "name": "mmi_chat",
            "arguments": {"message": "hello"},
        },
    })
    data = json.loads(resp.result["content"][0]["text"])
    assert "echo" in data["reply"]


def test_call_unknown_tool():
    s = _server()
    resp = s.handle_request({
        "method": "tools/call",
        "id": 6,
        "params": {"name": "nonexistent", "arguments": {}},
    })
    assert resp.error is not None
    assert resp.error["code"] == -32601


def test_call_tool_handler_error():
    s = _server()
    s.register_tool(MCPTool(
        name="boom",
        description="Raises error",
        handler=lambda p: (_ for _ in ()).throw(ValueError("test error")),
    ))
    resp = s.handle_request({
        "method": "tools/call",
        "id": 7,
        "params": {"name": "boom", "arguments": {}},
    })
    assert resp.error is not None
    assert "test error" in resp.error["message"]


# ---------------------------------------------------------------------------
# Unknown method
# ---------------------------------------------------------------------------

def test_unknown_method():
    s = _server()
    resp = s.handle_request({"method": "foo/bar", "id": 8})
    assert resp.error is not None
    assert resp.error["code"] == -32601


# ---------------------------------------------------------------------------
# Notification (no id)
# ---------------------------------------------------------------------------

def test_notification_no_response():
    s = _server()
    resp = s.handle_request({"method": "notifications/initialized"})
    # Notifications have no id, response should be empty
    assert resp.id is None


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def test_register_and_unregister():
    s = _server()
    s.register_tool(MCPTool(name="temp", description="x", handler=lambda p: None))
    assert any(t.name == "temp" for t in s.list_tools())
    s.unregister_tool("temp")
    assert not any(t.name == "temp" for t in s.list_tools())


# ---------------------------------------------------------------------------
# MCPResponse
# ---------------------------------------------------------------------------

def test_response_to_dict_success():
    resp = MCPResponse(id=1, result={"ok": True})
    d = resp.to_dict()
    assert d["jsonrpc"] == "2.0"
    assert d["id"] == 1
    assert d["result"]["ok"] is True
    assert "error" not in d


def test_response_to_dict_error():
    resp = MCPResponse(id=1, error={"code": -1, "message": "bad"})
    d = resp.to_dict()
    assert d["error"]["code"] == -1
    assert "result" not in d
