"""Tests for the `mmi tui` CLI subcommand."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mmi_tui_command_registered():
    """`mmi tui --help` should succeed and document the command.

    P9.4 修复:`mmi tui` 启动的是 Python Textual (`mmi.tui_v3.run_tui`),
    不是 TypeScript + Ink。旧测试用 ``skipif(not _have_node())`` 是误判
    —— 不需要 node。改无条件跑。
    """
    result = subprocess.run(
        [sys.executable, "-m", "mmi.cli", "tui", "--help"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "TUI" in result.stdout or "tui" in result.stdout
    # M7.1: new bundle launcher must expose --build
    assert "--build" in result.stdout, result.stdout
