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

import anyio  # noqa: E402  (keep with imports)

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
    params = request.get("params", {})

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

    if method == "list_sessions":
        from .manager import SessionManager  # lazy import to keep startup fast
        mgr = SessionManager()
        # NOTE: SessionManager.list_sessions currently only accepts `limit` and
        # always sorts by heat (manager.py:230-231). We still accept `sort` in
        # the IPC params for forward-compat (TUI may pass "heat" | "last_access")
        # and silently ignore unknown sort keys — keeps the wire contract stable
        # if manager.py later adds sort options.
        sessions = mgr.list_sessions(
            limit=int(params.get("limit", 20)),
        )
        _write_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "sessions": [
                    {"id": s.session_id, "title": s.title, "heat": s.heat}
                    for s in sessions
                ],
            },
        })
        return

    if method == "send_message":
        from .llm import stream_chat  # TODO: real implementation in M4 wiring

        async def _run() -> None:
            async for delta in stream_chat(
                session_id=params.get("session_id", ""),
                content=params.get("content", ""),
            ):
                _write_response({
                    "jsonrpc": "2.0",
                    "method": "token",
                    "params": {"session_id": params.get("session_id", ""), "delta": delta},
                })
            _write_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"ok": True},
            })
        anyio.run(_run)  # run async loop in this (sync) thread; output is line-buffered
        return

    if method == "set_config":
        # Persist arbitrary dotted keys into ~/.mmi/config.toml. The real
        # mmi.core.config API is save_config(dict)/load_config() — there is no
        # generic `set(key, value)` that takes dotted keys, so we expand
        # "tui.theme" -> {"tui": {"theme": ...}} and merge with existing cfg.
        # Spec note: original draft assumed `cfg_module.set(key, value)`; that
        # helper does not exist, so we do the merge here.
        from . import config as cfg_module
        cfg = cfg_module.load_config()
        for dotted_key, value in params.items():
            parts = dotted_key.split(".")
            if not parts or not all(parts):
                _write_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"Invalid config key: {dotted_key!r}"},
                })
                return
            cursor = cfg
            for part in parts[:-1]:
                if part not in cursor or not isinstance(cursor[part], dict):
                    cursor[part] = {}
                cursor = cursor[part]
            cursor[parts[-1]] = value
        ok = cfg_module.save_config(cfg)
        _write_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"ok": ok},
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
