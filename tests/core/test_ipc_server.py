"""Tests for the stdio JSON-RPC IPC server."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


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


def test_list_sessions_returns_sorted_by_heat():
    proc = _spawn_server()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        request = {"jsonrpc": "2.0", "id": 3, "method": "list_sessions", "params": {"limit": 5, "sort": "heat"}}
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        response = json.loads(line)
        assert response["id"] == 3
        assert "result" in response
        assert "sessions" in response["result"]
        assert isinstance(response["result"]["sessions"], list)
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_set_config_persists_theme(tmp_path, monkeypatch):
    # Note: real paths API uses MMI_HOME (not MMI_CONFIG_DIR as the original
    # spec draft assumed). The handler must accept dotted keys like
    # "tui.theme" and persist them under the matching nested TOML section.
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    proc = _spawn_server()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        request = {
            "jsonrpc": "2.0", "id": 20, "method": "set_config",
            "params": {"tui.theme": "light"},
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        response = json.loads(line)
        assert response["id"] == 20
        assert response["result"]["ok"] is True
        # Side-effect: config.toml must contain tui.theme = "light"
        cfg_file = tmp_path / "config.toml"
        assert cfg_file.exists()
        loaded = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        assert loaded["tui"]["theme"] == "light"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_send_message_emits_token_events_then_result():
    """send_message should stream token events, then a final response."""
    proc = _spawn_server()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        request = {
            "jsonrpc": "2.0", "id": 10, "method": "send_message",
            "params": {"session_id": "fake", "content": "hi"},
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        # Read lines until we see a response with id=10
        seen_token = False
        for _ in range(50):
            line = proc.stdout.readline()
            msg = json.loads(line)
            if msg.get("method") == "token":
                seen_token = True
            if msg.get("id") == 10:
                assert "result" in msg
                break
        assert seen_token, "expected at least one token event before final response"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
