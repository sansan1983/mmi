"""P0-3: Web browsing tools (web_scan, web_execute_js).

参考GA的tools_schema.json中对应的定义。
使用 @tool 装饰器自动注册。
跨平台兼容：自动检测 Python 解释器和浏览器控制脚本路径。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# 跨平台路径解析
# ---------------------------------------------------------------------------

# browser_ctl.py 可能的路径（从 agent/builtin/ 向上推算）
_BCTL_RELATIVE_PATHS = [
    # 标准结构: mmi/agent/builtin/web_browser.py → mmi/scripts/browser_ctl.py
    os.path.join("..", "..", "..", "scripts", "browser_ctl.py"),
    # 开发结构: mmi/agent/builtin/ → scripts/browser_ctl.py
    os.path.join("..", "..", "scripts", "browser_ctl.py"),
    # 如果直接放在项目根目录
    os.path.join("..", "browser_ctl.py"),
]


def _find_browser_ctl() -> str | None:
    """Find browser_ctl.py script (cross-platform). Returns None if not found."""
    builtin_dir = os.path.dirname(__file__)
    for rel in _BCTL_RELATIVE_PATHS:
        path = os.path.normpath(os.path.join(builtin_dir, rel))
        if os.path.isfile(path):
            return path
    return None


def _find_python() -> str:
    """Find Python executable (prefer current interpreter, then PATH)."""
    if hasattr(sys, "exec_prefix"):
        exe = os.path.join(sys.prefix, "python")
        if os.path.isfile(exe):
            return exe
    return sys.executable


# ---------------------------------------------------------------------------
# tool: web_scan
# ---------------------------------------------------------------------------


@tool(
    name="web_scan",
    description="Get simplified HTML and tab list. "
    "Removes hidden/floating/covered elements. Call after switching pages. "
    "Cross-platform: auto-detects browser controller script and Python.",
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
    If neither is available, returns minimal info via fallback HTTP fetch.
    """
    try:
        # 1) Try playwright-based browser controller
        script_path = _find_browser_ctl()
        if script_path:
            python_exe = _find_python()
            cmd = [python_exe, script_path]
            if url:
                cmd.extend(["--url", url])
            if tabs_only:
                cmd.append("--tabs-only")
            if switch_tab_id:
                cmd.extend(["--switch-tab", switch_tab_id])
            if text_only:
                cmd.append("--text-only")

            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                return result.stdout

        # 2) Fallback: use urllib for basic page fetch (no browser needed)
        if url and not switch_tab_id and not tabs_only:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                # Simple extraction: remove script/style tags
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

        return "Web scan: no browser controller found and no URL provided. " \
               "Install playwright or provide a URL for basic fetch."

    except urllib.error.HTTPError as e:
        return f"Web scan HTTP error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"Web scan URL error: {e.reason}"
    except subprocess.TimeoutExpired:
        return "Web scan: timed out after 30s"
    except Exception as e:
        return f"Web scan error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# tool: web_execute_js
# ---------------------------------------------------------------------------


@tool(
    name="web_execute_js",
    description="Execute JavaScript in the browser. Multi-call OK. "
    "Use for page manipulation or data extraction. "
    "Cross-platform: auto-detects browser controller script.",
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
    """Execute JavaScript in the browser session. Cross-platform."""
    try:
        # Check if browser controller script exists
        script_path = _find_browser_ctl()
        if script_path:
            python_exe = _find_python()
            cmd = [python_exe, script_path, "--exec-js", script]
            if save_to_file:
                cmd.extend(["--save-to", save_to_file])
            if no_monitor:
                cmd.append("--no-monitor")
            if switch_tab_id:
                cmd.extend(["--switch-tab", switch_tab_id])

            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                return result.stdout

        return "JS execution: no browser controller found. " \
               "Install playwright and place browser_ctl.py in scripts/ directory."

    except subprocess.TimeoutExpired:
        return "Error: JS execution timed out after 30s"
    except Exception as e:
        return f"JS execution error: {type(e).__name__}: {e}"
