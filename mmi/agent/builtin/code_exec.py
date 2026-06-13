"""P0-2: Code execution tool (code_run).

参考GA的tools_schema.json中对应的定义。
使用 @tool 装饰器自动注册。
"""

from __future__ import annotations

import subprocess
import tempfile

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# tool: code_run
# ---------------------------------------------------------------------------


@tool(
    name="code_run",
    description="Code executor. Prefer python. Multi-call OK, use script param. "
    "Reply code block is executed if no script arg; prefer for single call to "
    "avoid escaping. No hardcoding bulk data",
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
                "description": "Code type",
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
    """Execute code (python or bash) and return output."""
    try:
        if not script or not script.strip():
            return "Error: empty script"

        # Use venv python for mmi
        if type == "python":
            exec_args = ["/home/ubuntu/mmi/.venv/bin/python3", "-c", script]
        elif type == "bash":
            exec_args = ["/bin/bash", "-c", script]
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
