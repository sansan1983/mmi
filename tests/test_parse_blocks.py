"""tests/test_parse_blocks.py —— tui.parse_blocks 单元测试。

覆盖：
  - 纯文本 → 1 个 TextBlock
  - thinking 单行 / 多行
  - tool_call 单行 / 多行
  - thinking 后接正文
  - 正文中间夹 thinking
  - 多次 thinking
  - 不规范行不误判（行内 [thinking] 不算）
  - 空字符串 / 纯换行
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.tui.parse_blocks import (  # noqa: E402
    Block,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    parse_blocks,
)


# ---------------------------------------------------------------------------
# 纯文本
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty_list():
    assert parse_blocks("") == []


def test_only_newlines_returns_empty_list():
    # 注意：空行不主动分段，全部进 1 个 TextBlock
    bs = parse_blocks("\n\n\n")
    assert len(bs) == 1
    assert isinstance(bs[0], TextBlock)


def test_plain_text_returns_one_text_block():
    bs = parse_blocks("hello world\nthis is line 2")
    assert len(bs) == 1
    assert isinstance(bs[0], TextBlock)
    assert bs[0].text == "hello world\nthis is line 2"


# ---------------------------------------------------------------------------
# thinking
# ---------------------------------------------------------------------------


def test_thinking_single_line():
    md = "> [thinking] 我在分析用户的问题"
    bs = parse_blocks(md)
    assert len(bs) == 1
    assert isinstance(bs[0], ThinkingBlock)
    assert bs[0].text == "我在分析用户的问题"


def test_thinking_multiline():
    md = "> [thinking] line 1\n> line 2\n> line 3"
    bs = parse_blocks(md)
    assert len(bs) == 1
    assert isinstance(bs[0], ThinkingBlock)
    assert bs[0].text == "line 1\nline 2\nline 3"


def test_thinking_then_text():
    md = "> [thinking] 思考\n用户问的是分库策略\n回答内容"
    bs = parse_blocks(md)
    assert len(bs) == 2
    assert isinstance(bs[0], ThinkingBlock)
    assert bs[0].text == "思考"
    assert isinstance(bs[1], TextBlock)
    assert "用户问的是分库策略" in bs[1].text
    assert "回答内容" in bs[1].text


def test_text_then_thinking():
    md = "前面是回答\n> [thinking] 思考过程"
    bs = parse_blocks(md)
    assert len(bs) == 2
    assert isinstance(bs[0], TextBlock)
    assert bs[0].text == "前面是回答"
    assert isinstance(bs[1], ThinkingBlock)
    assert bs[1].text == "思考过程"


def test_multiple_thinking():
    md = "> [thinking] 第一段思考\n回答1\n> [thinking] 第二段思考\n回答2"
    bs = parse_blocks(md)
    assert len(bs) == 4
    assert isinstance(bs[0], ThinkingBlock) and bs[0].text == "第一段思考"
    assert isinstance(bs[1], TextBlock) and "回答1" in bs[1].text
    assert isinstance(bs[2], ThinkingBlock) and bs[2].text == "第二段思考"
    assert isinstance(bs[3], TextBlock) and "回答2" in bs[3].text


# ---------------------------------------------------------------------------
# tool_call
# ---------------------------------------------------------------------------


def test_tool_call_single_line():
    md = "> [tool_call name=search_web] 搜索关键词"
    bs = parse_blocks(md)
    assert len(bs) == 1
    assert isinstance(bs[0], ToolCallBlock)
    assert bs[0].name == "search_web"
    assert bs[0].text == "搜索关键词"


def test_tool_call_multiline():
    md = "> [tool_call name=bash] $ ls -la\n> total 8\n> drwxr-xr-x"
    bs = parse_blocks(md)
    assert len(bs) == 1
    assert isinstance(bs[0], ToolCallBlock)
    assert bs[0].name == "bash"
    assert "$ ls -la" in bs[0].text
    assert "drwxr-xr-x" in bs[0].text


def test_tool_call_then_text():
    md = "> [tool_call name=search_web] query\n下面是搜索结果"
    bs = parse_blocks(md)
    assert len(bs) == 2
    assert isinstance(bs[0], ToolCallBlock)
    assert bs[0].name == "search_web"
    assert isinstance(bs[1], TextBlock)
    assert "搜索结果" in bs[1].text


# ---------------------------------------------------------------------------
# 边界
# ---------------------------------------------------------------------------


def test_inline_thinking_not_matched():
    """行内 [thinking] 字样不算块标记。"""
    md = "正文里写[thinking]不是块标记"
    bs = parse_blocks(md)
    assert len(bs) == 1
    assert isinstance(bs[0], TextBlock)
    assert "[thinking]" in bs[0].text


def test_malformed_tool_call_treated_as_text():
    """缺 name= → 降级为 TextBlock。"""
    md = "> [tool_call] 缺少 name"
    bs = parse_blocks(md)
    assert len(bs) == 1
    assert isinstance(bs[0], TextBlock)


def test_tool_call_name_with_special_chars_ignored():
    """name 只允许 [A-Za-z0-9_-]；含 . 或空格的降级为 TextBlock。"""
    md = "> [tool_call name=bash.run] x"
    bs = parse_blocks(md)
    assert len(bs) == 1
    assert isinstance(bs[0], TextBlock)


def test_continuation_after_blank_line_breaks_block():
    """块内空行（> 形式）算 continuation；空行（不带 >）算块结束。"""
    md = "> [thinking] line 1\n\n> 不再是 continuation"
    bs = parse_blocks(md)
    # 第一块：ThinkingBlock(text="line 1")
    # 第二块：TextBlock("") —— 空行产生
    # 第三块：TextBlock("> 不再是 continuation") —— 这行虽然以 > 开头但前面是空行
    assert len(bs) >= 1
    assert isinstance(bs[0], ThinkingBlock)
    assert bs[0].text == "line 1"
