"""mmi.core.ipc_server —— stdio JSON-RPC 2.0 server for the TUI.

The TUI (TypeScript + Ink) spawns this module as a child process and
exchanges JSON-RPC messages one per line over stdin/stdout. stderr is
reserved for logs and never enters the protocol stream.

Protocol version: see PROTOCOL_VERSION. Bump on breaking changes.
"""
from __future__ import annotations

import json
import sys
from typing import Any

PROTOCOL_VERSION = 1
SERVER_NAME = "mmi-core"


def _write_response(payload: dict[str, Any]) -> None:
    """Write one JSON response line and flush. line_buffering=True is set on stdout."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle_request(request: dict[str, Any]) -> None:
    """Dispatch a single JSON-RPC request and write a response."""
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})  # noqa: F841 — reserved for future handlers

    if method == "hello":
        _write_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocol_version": PROTOCOL_VERSION,
                "server": SERVER_NAME,
            },
        })
        return

    _write_response({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    })


def main() -> int:
    """Read requests line by line from stdin, dispatch, write responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _write_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            })
            continue
        if not isinstance(request, dict) or "method" not in request:
            _write_response({
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32600, "message": "Invalid Request"},
            })
            continue
        _handle_request(request)
    return 0


if __name__ == "__main__":
    sys.exit(main())
