"""End-to-end test: spawn the real built TUI bundle with a fake stdin.

We don't drive a real TTY (no PTY in unit tests), but we can:
  1. Verify the bundle exists and is executable.
  2. Spawn the bundle, let Ink start rendering, then kill it. Verify:
     - No TypeError / ReferenceError in stderr.
     - The SessionHub content ("MMI", "Sessions", etc.) appears in stdout,
       proving the router actually wires up the screen (not the placeholder).
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
def test_bundle_renders_sessionhub_and_does_not_crash():
    """Spawn the bundle, give Ink a moment to render, then kill it.

    Asserts the SessionHub content actually appears in stdout (so the
    router wiring is real) and that there is no TypeError / ReferenceError
    anywhere in the output (Ink's raw-mode warning is fine — it only fires
    under non-TTY stdin, which is what we use here).
    """
    proc = subprocess.Popen(
        [shutil.which("node"), str(DIST)],  # type: ignore[list-item]
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, err = proc.communicate(input=b"", timeout=3)
    except subprocess.TimeoutExpired:
        # TUI is alive and listening for input — expected. Kill it and read
        # whatever Ink managed to render so far.
        proc.kill()
        out, err = proc.communicate()

    combined = (out + err).decode("utf-8", errors="replace")

    # The router must actually render the SessionHub, not the placeholder.
    assert "MMI" in combined, "SessionHub 'MMI' header not found in bundle output"
    assert "Sessions" in combined, "SessionHub 'Sessions' divider not found in bundle output"
    assert "Multimodal Intelligence" in combined, (
        "SessionHub tagline not found — router may still be showing the placeholder"
    )

    # No JS crash tracebacks allowed.
    assert "TypeError" not in combined
    assert "ReferenceError" not in combined
