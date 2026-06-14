"""P0-2: Code execution tool (code_run).

参考GA的tools_schema.json中对应的定义。
使用 @tool 装饰器自动注册。
跨平台兼容：自动检测 Python 解释器和 Shell。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# 跨平台执行器查找
# ---------------------------------------------------------------------------


def _find_python() -> str:
    """Find Python executable (prefer current interpreter, then PATH)."""
    # 优先使用当前 Python（保证使用同一个 venv）
    if hasattr(sys, "exec_prefix"):
        exe = os.path.join(sys.prefix, "python")
        if os.path.isfile(exe):
            return exe
    return sys.executable


def _find_shell() -> str:
    """Find a shell executable (bash/sh/cmd)."""
    if os.name == "nt":
        # Windows: try cmd.exe first, then powershell, then sh
        for candidate in ["cmd.exe", "powershell.exe", "sh", "bash"]:
            path = shutil.which(candidate)
            if path:
                return path
        return "cmd.exe"
    # Unix: bash -> sh
    path = shutil.which("bash") or shutil.which("sh")
    return path or "/bin/sh"


_PYTHON_EXE = _find_python()
_SHELL_EXE = _find_shell()

# ---------------------------------------------------------------------------
# tool: code_run
# ---------------------------------------------------------------------------


@tool(
    name="code_run",
    description="Code executor. Prefer python. Multi-call OK, use script param. "
    "Reply code block is executed if no script arg; prefer for single call to "
    "avoid escaping. No hardcoding bulk data. "
    "Cross-platform: auto-detects Python and Shell.",
    schema={
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "[Mutually exclusive] NEVER use when using reply code block",
            },
            "type": {
                "type": "string",
                "enum": ["python", "bash"],
                "description": "Code type (python or bash/sh/cmd)",
                "default": "python",
            },
            "timeout": {
                "type": "integer",
                "description": "in seconds",
                "default": 60,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory, defaults to current",
            },
        },
    },
)
def code_run(
    script: str | None = None,
    type: str = "python",
    timeout: int = 60,
    cwd: str | None = None,
) -> str:
    """Execute code (python or bash) and return output. Cross-platform."""
    try:
        if not script or not script.strip():
            return "Error: empty script"

        if type == "python":
            exec_args = [_PYTHON_EXE, "-c", script]
        elif type == "bash":
            # Windows PowerShell 需要不同语法，bash 类型在 Windows 上回退到 cmd
            if os.name == "nt" and not shutil.which("bash"):
                # PowerShell 用 -Command 而非 -c
                exec_args = [shutil.which("powershell.exe") or "powershell", "-Command", script]
            else:
                exec_args = [_SHELL_EXE, "-c", script]
        else:
            return f"Error: unsupported type '{type}'"

        result = subprocess.run(
            exec_args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or ".",
        )

        parts = []
        if result.stdout:
            parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr}")
        parts.append(f"RC: {result.returncode}")

        return "\n\n".join(parts)

    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {timeout}s"
    except Exception as e:
        return f"Error executing code: {e}"
