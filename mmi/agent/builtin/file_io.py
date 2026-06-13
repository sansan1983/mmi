"""P0-1: File I/O tools (file_read, file_write, file_patch).

参考GA的tools_schema.json中对应的定义。
使用 @tool 装饰器自动注册。
"""

from __future__ import annotations

import os

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# tool: file_read
# ---------------------------------------------------------------------------


@tool(
    name="file_read",
    description="Read file. Read before modify for latest context and line numbers",
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative or absolute",
            },
            "start": {
                "type": "integer",
                "description": "Start line number (1-based)",
                "default": 1,
            },
            "count": {
                "type": "integer",
                "description": "Number of lines to read",
                "default": 200,
            },
            "keyword": {
                "type": "string",
                "description": "[Optional] If provided, returns first match (case-insensitive) with context",
            },
            "show_linenos": {
                "type": "boolean",
                "description": "Show line numbers",
                "default": True,
            },
        },
    },
)
def file_read(
    path: str,
    start: int = 1,
    count: int = 200,
    keyword: str | None = None,
    show_linenos: bool = True,
) -> str:
    """Read file content with optional line numbering and keyword search."""
    try:
        if not os.path.exists(path):
            return f"Error: file not found: {path}"

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Keyword search
        if keyword:
            kw_lower = keyword.lower()
            for i, line in enumerate(lines):
                if kw_lower in line.lower():
                    s = max(0, i - 5)
                    e = min(len(lines), i + 5)
                    return "".join(lines[s:e])
            return f"Keyword '{keyword}' not found in {path}"

        # Read from start with count
        if start < 1:
            start = 1
        actual_start = start - 1
        end = min(actual_start + count, len(lines))
        result_lines = lines[actual_start:end]

        if show_linenos:
            formatted = "\n".join(
                f"{actual_start + i + 1}|{line}" for i, line in enumerate(result_lines)
            )
        else:
            formatted = "".join(result_lines)

        total = len(lines)
        return f"[{total} lines total, showing {actual_start+1}-{end}]\n{formatted}"

    except Exception as e:
        return f"Error reading file: {e}"


# ---------------------------------------------------------------------------
# tool: file_write
# ---------------------------------------------------------------------------


@tool(
    name="file_write",
    description="Create/overwrite/append files. HUGE edits ONLY.",
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path",
            },
            "content": {
                "type": "string",
            },
            "mode": {
                "type": "string",
                "enum": ["overwrite", "append", "prepend"],
                "description": "Write mode",
                "default": "overwrite",
            },
        },
    },
)
def file_write(path: str, content: str, mode: str = "overwrite") -> str:
    """Write content to file (overwrite / append / prepend)."""
    try:
        if mode not in ("overwrite", "append", "prepend"):
            return f"Error: invalid mode '{mode}'"

        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if mode == "prepend":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = f.read()
                content = content + existing
            except FileNotFoundError:
                pass
            flag = "w"
        elif mode == "append":
            flag = "a"
        else:
            flag = "w"

        with open(path, flag, encoding="utf-8") as f:
            f.write(content)

        lines_written = content.count("\n") + 1
        return f"OK: wrote {lines_written} lines to {path}"

    except Exception as e:
        return f"Error writing file: {e}"


# ---------------------------------------------------------------------------
# tool: file_patch
# ---------------------------------------------------------------------------


@tool(
    name="file_patch",
    description="Replace unique old_content with new_content in a file. "
    "Exact match required (whitespace/indentation). "
    "On failure, use file_read to recheck.",
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path",
            },
            "old_content": {
                "type": "string",
                "description": "Original text block to replace (must be unique)",
            },
            "new_content": {
                "type": "string",
                "description": "New content. Supports {{file:path:startLine:endLine}} to ref file lines",
            },
        },
    },
)
def file_patch(path: str, old_content: str, new_content: str) -> str:
    """Replace unique old_content with new_content in a file."""
    try:
        if not os.path.exists(path):
            return f"Error: file not found: {path}"

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if old_content not in content:
            return (
                f"Error: old_content not found in {path}\n"
                "Hint: use file_read to get the exact content first."
            )

        if content.count(old_content) > 1:
            return (
                f"Error: old_content found {content.count(old_content)} times "
                "(must be unique)\n"
                "Hint: provide more context."
            )

        new_full = content.replace(old_content, new_content, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_full)

        return f"OK: patched {path} (1 replacement)"

    except Exception as e:
        return f"Error patching file: {e}"
