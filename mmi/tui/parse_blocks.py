"""mmi.tui.parse_blocks —— Markdown → 折叠块解析。

ARCHITECTURE §3 + Phase 5 决策：折叠协议是 TUI 私有，**不动 core.body 契约**。
约定 LLM 输出可用以下两种块（默认折叠）：

    > [thinking] ...思考过程...
    > [tool_call name=xxx] ...参数/结果...

其它内容走 TextBlock（正常显示）。

设计原则：
  - 协议是单向的：解析不到就静默退化（不报错）
  - 只解析"行首"的标记（避免误命中正文里的 [thinking] 字样）
  - 折叠/展开状态在 widget 层维护（不存这里）；parse_blocks 只产出"块"
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "Block",
    "TextBlock",
    "ThinkingBlock",
    "ToolCallBlock",
    "parse_blocks",
]


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class Block:
    """折叠块基类。"""


@dataclass
class TextBlock(Block):
    """普通文本块（正常显示，不折叠）。"""

    text: str = ""


@dataclass
class ThinkingBlock(Block):
    """AI 思考过程（默认折叠）。

    协议：`> [thinking] <content>`
    允许多行：`> [thinking] line1\n> line2\n> line3`
    后续行必须以 `> ` 开头才算同一块。
    """

    text: str = ""


@dataclass
class ToolCallBlock(Block):
    """AI 工具调用（默认折叠）。

    协议：`> [tool_call name=<word>] <content>`
    允许多行（同 ThinkingBlock）
    """

    name: str = ""
    text: str = ""


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

# 块起始行（单行匹配；MULTILINE 让 ^ 匹配每行起始）
_THINKING_HEAD = re.compile(r"^>\s*\[thinking\]\s*(.*)$")
_TOOL_HEAD = re.compile(r"^>\s*\[tool_call\s+name=([A-Za-z0-9_\-]+)\]\s*(.*)$")
_CONTINUATION = re.compile(r"^>\s?(.*)$")  # 块的后续行：以 > 开头


def parse_blocks(md: str) -> list[Block]:
    """把一段 Markdown 文本解析成 Block 列表。

    解析规则：
      - 行首 `> [thinking] ...` 起 ThinkingBlock，后续 `> xxx` 行同块
      - 行首 `> [tool_call name=xxx] ...` 起 ToolCallBlock，后续 `> xxx` 行同块
      - 其它行累加成 TextBlock（连续非标记行合一段，段间空行不强制分段）

    Args:
        md: 任意 Markdown 文本

    Returns:
        list[Block]，按出现顺序
    """
    blocks: list[Block] = []
    text_buf: list[str] = []

    def _flush_text():
        if text_buf:
            blocks.append(TextBlock(text="\n".join(text_buf)))
            text_buf.clear()

    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        m_think = _THINKING_HEAD.match(line)
        m_tool = _TOOL_HEAD.match(line)

        if m_think:
            _flush_text()
            content_lines = [m_think.group(1)]
            i += 1
            while i < len(lines) and _CONTINUATION.match(lines[i]):
                content_lines.append(_CONTINUATION.match(lines[i]).group(1))
                i += 1
            blocks.append(ThinkingBlock(text="\n".join(content_lines).rstrip()))
            continue

        if m_tool:
            _flush_text()
            name = m_tool.group(1)
            content_lines = [m_tool.group(2)]
            i += 1
            while i < len(lines) and _CONTINUATION.match(lines[i]):
                content_lines.append(_CONTINUATION.match(lines[i]).group(1))
                i += 1
            blocks.append(ToolCallBlock(name=name, text="\n".join(content_lines).rstrip()))
            continue

        # 普通行：累积到 text_buf
        text_buf.append(line)
        i += 1

    _flush_text()
    return blocks
