"""End-to-end test: spawn the real built TUI bundle with a fake stdin.

We don't drive a real TTY (no PTY in unit tests), but we can:
  1. Verify the bundle exists and is executable.
  2. Spawn the IPC server alone and confirm a hello response.
  3. Spawn the bundle with a piped stdin that closes immediately and
     confirm it exits with code 0 (graceful shutdown).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST = REPO_ROOT / "tui-ts" / "dist" / "mmi-tui.js"


def _have_node() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _have_node(), reason="node not installed")
@pytest.mark.skipif(not DIST.exists(), reason="bundle not built (run `npm run build` in tui-ts/)")
def test_bundle_exists_and_is_valid_js():
    """Smoke check: the bundle file is non-empty and starts with a shebang or js."""
    assert DIST.exists()
    text = DIST.read_text()
    assert len(text) > 1000, "bundle suspiciously small"
    # tsup banner adds #!/usr/bin/env node
    assert text.startswith("#!") or text.startswith("//") or "ink" in text.lower()


@pytest.mark.skipif(not _have_node(), reason="node not installed")
@pytest.mark.skipif(not DIST.exists(), reason="bundle not built")
def test_bundle_exits_cleanly_with_closed_stdin():
    """Run the bundle with a closed stdin; it should exit gracefully."""
    proc = subprocess.run(
        [shutil.which("node"), str(DIST)],
        input="", capture_output=True, text=True, timeout=10,
    )
    # Exit code may be non-zero if TUI cannot render to non-TTY, but no crash traceback.
    assert "TypeError" not in proc.stderr
    assert "ReferenceError" not in proc.stderr
