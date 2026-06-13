"""P0-3: Web browsing tools (web_scan, web_execute_js).

参考GA的tools_schema.json中对应的定义。
使用 @tool 装饰器自动注册。
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# tool: web_scan
# ---------------------------------------------------------------------------


@tool(
    name="web_scan",
    description="Get simplified HTML and tab list. "
    "Removes hidden/floating/covered elements. Call after switching pages",
    schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to open (if not provided, refreshes current page)",
            },
            "tabs_only": {
                "type": "boolean",
                "description": "Show tab list only, no HTML",
                "default": False,
            },
            "switch_tab_id": {
                "type": "string",
                "description": "[Optional] Tab ID to switch to",
            },
            "text_only": {
                "type": "boolean",
                "description": "Plain text only, no HTML",
                "default": False,
            },
        },
    },
)
def web_scan(
    url: str | None = None,
    tabs_only: bool = False,
    switch_tab_id: str | None = None,
    text_only: bool = False,
) -> str:
    """Control a headless browser: navigate, list tabs, get page content.

    Uses a lightweight browser automation script (playwright or selenium).
    If neither is available, returns minimal info.
    """
    try:
        # Try to use playwright-based browser controller
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "scripts", "browser_ctl.py"
        )
        if os.path.exists(script_path):
            cmd = [script_path]
            if url:
                cmd.extend(["--url", url])
            if tabs_only:
                cmd.append("--tabs-only")
            if switch_tab_id:
                cmd.extend(["--switch-tab", switch_tab_id])
            if text_only:
                cmd.append("--text-only")

            result = subprocess.run(
                ["/home/ubuntu/mmi/.venv/bin/python3", *cmd],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                return result.stdout

        # Fallback: use curl for basic page fetch
        if url and not switch_tab_id and not tabs_only:
            import urllib.request

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                # Simple extraction: remove script/style tags
                import re

                html = re.sub(
                    r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL
                )
                html = re.sub(r"<[^>]+>", " ", html)
                html = re.sub(r"\s+", " ", html).strip()
                # Truncate
                max_len = 5000
                if len(html) > max_len:
                    html = html[:max_len] + f"\n... [truncated, {len(html)} total]"
                return html

        return "Web scan: no content available (consider installing playwright)"
    except Exception as e:
        return f"Web scan error: {e}"


# ---------------------------------------------------------------------------
# tool: web_execute_js
# ---------------------------------------------------------------------------


@tool(
    name="web_execute_js",
    description="Execute JavaScript in the browser. Multi-call OK. "
    "Use for page manipulation or data extraction.",
    schema={
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "JavaScript code to execute",
            },
            "save_to_file": {
                "type": "string",
                "description": "file path; **only** for long result",
            },
            "no_monitor": {
                "type": "boolean",
                "description": "Skip page change monitoring, saves 2-3s. "
                "Only for reads, not for page actions",
                "default": False,
            },
            "switch_tab_id": {
                "type": "string",
                "description": "[Optional] Tab ID to switch to before executing",
            },
        },
    },
)
def web_execute_js(
    script: str,
    save_to_file: str | None = None,
    no_monitor: bool = False,
    switch_tab_id: str | None = None,
) -> str:
    """Execute JavaScript in the browser session."""
    try:
        # Check if browser controller script exists
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "scripts", "browser_ctl.py"
        )
        if os.path.exists(script_path):
            cmd = [
                script_path,
                "--exec-js",
                script,
            ]
            if save_to_file:
                cmd.extend(["--save-to", save_to_file])
            if no_monitor:
                cmd.append("--no-monitor")
            if switch_tab_id:
                cmd.extend(["--switch-tab", switch_tab_id])

            result = subprocess.run(
                ["/home/ubuntu/mmi/.venv/bin/python3", *cmd],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                return result.stdout

        return "JS execution: no browser available (install playwright or browser_ctl.py)"
    except subprocess.TimeoutExpired:
        return "Error: JS execution timed out after 30s"
    except Exception as e:
        return f"JS execution error: {e}"
