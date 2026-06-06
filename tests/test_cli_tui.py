"""Tests for the `mmi tui` CLI subcommand."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _have_node() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _have_node(), reason="node not installed")
def test_mmi_tui_command_registered():
    """`mmi tui --help` should succeed and document the command."""
    result = subprocess.run(
        [sys.executable, "-m", "mmi.cli", "tui", "--help"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "TUI" in result.stdout or "tui" in result.stdout
    # M7.1: new bundle launcher must expose --build
    assert "--build" in result.stdout, result.stdout
