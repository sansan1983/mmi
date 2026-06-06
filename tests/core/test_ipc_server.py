"""Tests for the stdio JSON-RPC IPC server."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _spawn_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "mmi.core.ipc_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered
    )


def test_hello_round_trip():
    """Server echoes a hello request with protocol version."""
    proc = _spawn_server()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "hello",
            "params": {"protocol_version": 1},
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        response = json.loads(line)
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert response["result"]["protocol_version"] == 1
        assert response["result"]["server"] == "mmi-core"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_unknown_method_returns_error():
    proc = _spawn_server()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        request = {"jsonrpc": "2.0", "id": 2, "method": "does_not_exist", "params": {}}
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        response = json.loads(line)
        assert response["id"] == 2
        assert "error" in response
        assert response["error"]["code"] == -32601  # Method not found
    finally:
        proc.terminate()
        proc.wait(timeout=5)
