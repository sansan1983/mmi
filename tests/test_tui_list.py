"""tests/test_tui_list.py —— SessionListScreen 测试。

覆盖：
  - 启动屏显示前 N 条
  - n 键新建 + 进入 chat
  - 空态文案
"""

from __future__ import annotations

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# 用 fixture 拿 ScriptedLLM（conftest.py 里的 scripted_llm_factory）


# ---------------------------------------------------------------------------
# 11 次 create → 列表只显示 10
# ---------------------------------------------------------------------------


def test_list_screen_shows_top_n(isolated_home, make_app, scripted_llm_factory):
    """11 个会话 → ListView 显示 10 条。"""
    pytest.importorskip("textual")
    from textual.widgets import ListView

    from mmi.core import manager as mgr_module

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    for _ in range(11):
        mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            lv = app.screen.query_one("#sessions-list", ListView)
            assert len(lv.children) == 10

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# n 键新建
# ---------------------------------------------------------------------------


def test_list_screen_n_creates_and_enters(isolated_home, make_app, scripted_llm_factory):
    """n 键 → 创建新会话 + 切到 ChatScreen。"""
    pytest.importorskip("textual")
    from mmi.tui.screens.chat import ChatScreen
    from mmi.core import manager as mgr_module
    from mmi.core.session import ULID_PATTERN
    import re

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            # 当前屏应该是 ChatScreen
            assert isinstance(app.screen, ChatScreen)
            # session_id 合法 ULID
            assert re.match(ULID_PATTERN, app.screen.session_id), app.screen.session_id

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# 空态
# ---------------------------------------------------------------------------


def test_list_screen_empty(isolated_home, make_app, scripted_llm_factory):
    """0 会话 → 看到空态文案。"""
    pytest.importorskip("textual")

    from mmi.core import manager as mgr_module

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            # 容器里应该有 empty-pane
            try:
                empty = app.screen.query_one(".empty-pane")
                assert empty is not None
            except Exception:
                # 或 fallback: 没 #sessions-list
                from textual.widgets import ListView
                try:
                    app.screen.query_one("#sessions-list", ListView)
                    pytest.fail("expected empty pane, got ListView")
                except Exception:
                    pass

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# BUG-1: 按 Enter/Space 应该能进入会话（不只是 n 新建）
# ---------------------------------------------------------------------------


def test_list_screen_enter_enters_existing_session(isolated_home, make_app, scripted_llm_factory):
    """↑↓ 选条目 + Enter → 进入 ChatScreen (不是新建)。"""
    pytest.importorskip("textual")
    from textual.widgets import ListView
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen


    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    # 预先创建一个会话（不要 n 触发新的）
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            # 列表里现在有 1 条；焦点应该在第 1 条
            lv = app.screen.query_one("#sessions-list", ListView)
            assert lv.index == 0
            # 按 Enter
            await pilot.press("enter")
            await pilot.pause()
            # 现在应当在 ChatScreen，并且 sid 是预创建的那个
            assert isinstance(app.screen, ChatScreen), type(app.screen).__name__
            assert app.screen.session_id == sid

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# BUG-2: ChatScreen 进入后，input 应当能拿焦点并接收字符
# ---------------------------------------------------------------------------


def test_chat_screen_input_can_focus(isolated_home, make_app, scripted_llm_factory):
    """进入 ChatScreen 后，#input 应当可拿焦点、键入字符能存到 .value。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            # 直接 push ChatScreen（绕过 ListScreen 的 BUG-1）
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            assert isinstance(app.screen, ChatScreen)
            inp = app.screen.query_one("#input", TextArea)
            # 焦点应当在 #input
            assert app.focused is inp, f"focused={app.focused!r} expected Input"
            # 键入字符
            await pilot.press(*"hello")
            await pilot.pause()
            assert inp.text == "hello", f"input.value={inp.text!r}"
            # input 应当至少占 1 行高度
            assert inp.outer_size.height >= 1, f"input height={inp.outer_size.height}, container too small"

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# BUG-2（小终端扩展）：<40 行下 ChatScreen Input 仍可获焦/键入
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rows", [30, 25, 20])
def test_chat_screen_input_visible_at_small_terminal(
    isolated_home, make_app, scripted_llm_factory, rows
):
    """BUG-2 修复在小终端（30/25/20 行）下仍有效。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, rows)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            assert isinstance(app.screen, ChatScreen)
            inp = app.screen.query_one("#input", TextArea)
            assert app.focused is inp, f"focused={app.focused!r} expected Input"
            await pilot.press(*"hello")
            await pilot.pause()
            assert inp.text == "hello", f"input.value={inp.text!r}"
            assert inp.outer_size.height >= 1, f"input height={inp.outer_size.height}"

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# Phase 6 P0 #1: ! / $ 前缀 → bash / python 模式（单元：_run_bash / _run_python）
# ---------------------------------------------------------------------------


def test_run_bash_echo():
    """!echo hello → 输出 'hello'。"""
    from mmi.tui.screens.chat import _run_bash
    out = _run_bash("echo hello")
    assert "hello" in out, f"got: {out!r}"


def test_run_bash_nonzero_exit():
    """!false → 输出带 [exit 1] 前缀。"""
    from mmi.tui.screens.chat import _run_bash
    out = _run_bash("false")
    assert "[exit 1]" in out, f"got: {out!r}"


def test_run_bash_not_found():
    """不存在的命令 → 'command not found'。"""
    from mmi.tui.screens.chat import _run_bash
    out = _run_bash("__ctrim_definitely_not_a_real_cmd_xyz__")
    assert "not found" in out.lower(), f"got: {out!r}"


def test_run_bash_empty():
    """空命令 → 空字符串。"""
    from mmi.tui.screens.chat import _run_bash
    assert _run_bash("") == ""
    assert _run_bash("   ") == ""


def test_run_python_print():
    """$print(1+1) → 输出 '2'。"""
    from mmi.tui.screens.chat import _run_python
    out = _run_python("print(1+1)")
    assert out == "2", f"got: {out!r}"


def test_run_python_error():
    """$1/0 → 输出带 [error] ZeroDivisionError。"""
    from mmi.tui.screens.chat import _run_python
    out = _run_python("1/0")
    assert "ZeroDivisionError" in out, f"got: {out!r}"
    assert "[error]" in out, f"got: {out!r}"


def test_run_python_empty():
    """空代码 → 空字符串。"""
    from mmi.tui.screens.chat import _run_python
    assert _run_python("") == ""


def test_run_python_multi_line():
    """多行代码：a=1; print(a) → '1'。"""
    from mmi.tui.screens.chat import _run_python
    out = _run_python("a = 1\nprint(a)")
    assert out == "1", f"got: {out!r}"


# ---------------------------------------------------------------------------
# Phase 6 P0 #1: ! / $ 前缀 → 边框色 class 切换
# ---------------------------------------------------------------------------


def test_input_class_toggles_bash(isolated_home, make_app, scripted_llm_factory):
    """输入 '!' → Input 获得 -bash class。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            inp = app.screen.query_one("#input", TextArea)
            inp.focus()
            await pilot.press("!")
            await pilot.pause()
            assert inp.has_class("-bash"), f"classes={inp.classes!r}"
            assert not inp.has_class("-python")

    import asyncio
    asyncio.run(_go())


def test_input_class_toggles_python(isolated_home, make_app, scripted_llm_factory):
    """输入 '$' → Input 获得 -python class。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            inp = app.screen.query_one("#input", TextArea)
            inp.focus()
            await pilot.press("$")
            await pilot.pause()
            assert inp.has_class("-python"), f"classes={inp.classes!r}"
            assert not inp.has_class("-bash")

    import asyncio
    asyncio.run(_go())


def test_input_class_clears_on_backspace(isolated_home, make_app, scripted_llm_factory):
    """输入 '!' 后删掉 → -bash class 消失。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            inp = app.screen.query_one("#input", TextArea)
            inp.focus()
            await pilot.press("!")
            await pilot.pause()
            assert inp.has_class("-bash")
            await pilot.press("backspace")
            await pilot.pause()
            assert not inp.has_class("-bash"), f"classes={inp.classes!r}"
            assert not inp.has_class("-python")

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# Phase 6 P0 #1: 端到端 dispatch 路由（input → worker → chat log）
# ---------------------------------------------------------------------------


def test_bash_dispatch_runs_command(isolated_home, make_app, scripted_llm_factory):
    """输入 '!echo hello' + Enter → chat log 出现 'hello'。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen
    from mmi.tui.widgets.chat_log import _AssistantBlock

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            inp = app.screen.query_one("#input", TextArea)
            inp.focus()
            await pilot.press(*"!echo hello")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            # 等 worker
            for _ in range(30):
                await pilot.pause(0.1)
                blocks = list(app.screen.query(_AssistantBlock))
                rendered = [str(b.render()) for b in blocks]
                if any("hello" in s for s in rendered):
                    return
            # 最后一次检查
            blocks = list(app.screen.query(_AssistantBlock))
            rendered = [str(b.render()) for b in blocks]
            assert any("hello" in s for s in rendered), f"blocks={rendered!r}"

    import asyncio
    asyncio.run(_go())


def test_python_dispatch_runs_code(isolated_home, make_app, scripted_llm_factory):
    """输入 '$print(1+1)' + Enter → chat log 出现 '2'。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen
    from mmi.tui.widgets.chat_log import _AssistantBlock

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            inp = app.screen.query_one("#input", TextArea)
            inp.focus()
            await pilot.press(*"$print(1+1)")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            for _ in range(30):
                await pilot.pause(0.1)
                blocks = list(app.screen.query(_AssistantBlock))
                rendered = [str(b.render()) for b in blocks]
                if any("2" in s for s in rendered):
                    return
            blocks = list(app.screen.query(_AssistantBlock))
            rendered = [str(b.render()) for b in blocks]
            assert any("2" in s for s in rendered), f"blocks={rendered!r}"

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# Phase 6 P0 #2: Ctrl+D 双击退出 / Ctrl+Z 占位
# ---------------------------------------------------------------------------


def test_ctrl_d_clears_input(isolated_home, make_app, scripted_llm_factory):
    """Ctrl+D 在有内容时清空输入（不退出）。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            inp = app.screen.query_one("#input", TextArea)
            inp.focus()
            await pilot.press(*"hello")
            await pilot.pause()
            assert inp.text == "hello"
            await pilot.press("ctrl+d")
            await pilot.pause()
            assert inp.text == "", f"input.value={inp.text!r}"

    import asyncio
    asyncio.run(_go())


def test_ctrl_d_shared_window_with_ctrl_c(
    isolated_home, make_app, scripted_llm_factory
):
    """Ctrl+C 后 1.5s 内按 Ctrl+D 应当退出（共享双击窗口）。"""
    pytest.importorskip("textual")
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            # 第一次 Ctrl+C（空输入，触发 hint 通知）
            await pilot.press("ctrl+c")
            await pilot.pause()
            # 1.5s 内按 Ctrl+D → 应触发退出
            await pilot.press("ctrl+d")
            await pilot.pause()
            # app.is_running 应为 False（已退出）
            # 但 run_test 会在 _exit 后等待；用内部状态检查
            assert app._exit is not None or not app._running, "app should be exiting"

    import asyncio
    asyncio.run(_go())


def test_ctrl_z_does_not_crash(isolated_home, make_app, scripted_llm_factory):
    """Ctrl+Z 在 TUI 中不支持，但不应该 crash；只是显示通知。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            inp = app.screen.query_one("#input", TextArea)
            inp.focus()
            await pilot.press(*"hello")
            await pilot.pause()
            # Ctrl+Z 不应清空输入
            await pilot.press("ctrl+z")
            await pilot.pause()
            assert inp.text == "hello", f"input.value={inp.text!r}"

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# Phase 6 P0 #4: 多行 Editor（TextArea，Enter 换行 / Ctrl+Enter 提交）
# ---------------------------------------------------------------------------


def test_textarea_enter_inserts_newline(isolated_home, make_app, scripted_llm_factory):
    """TextArea 内 Enter 应当插入换行，不触发提交。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            ed = app.screen.query_one("#input", TextArea)
            ed.focus()
            await pilot.press(*"line1")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press(*"line2")
            await pilot.pause()
            assert ed.text == "line1\nline2", f"text={ed.text!r}"

    import asyncio
    asyncio.run(_go())


def test_textarea_height_is_multi_line(isolated_home, make_app, scripted_llm_factory):
    """TextArea 应当是多行（高度 > 1）。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            ed = app.screen.query_one("#input", TextArea)
            assert ed.outer_size.height >= 3, f"height={ed.outer_size.height}, expected >= 3"

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# Phase 6 P0 #5: 思考 / 工具块解析 + 整行高亮
# ---------------------------------------------------------------------------


def test_parse_blocks_thinking():
    """> [thinking] 起始的行应被解析为 ThinkingBlock。"""
    from mmi.tui.parse_blocks import (
        parse_blocks,
    )
    blocks = parse_blocks("hello\n> [thinking] 我在想\n> 第二行\nworld")
    kinds = [type(b).__name__ for b in blocks]
    assert kinds == ["TextBlock", "ThinkingBlock", "TextBlock"]
    assert blocks[0].text == "hello"
    assert "我在想" in blocks[1].text
    assert "第二行" in blocks[1].text
    assert blocks[2].text == "world"


def test_parse_blocks_tool_call():
    """> [tool_call name=xxx] 起始的行应被解析为 ToolCallBlock。"""
    from mmi.tui.parse_blocks import ToolCallBlock, parse_blocks

    blocks = parse_blocks("> [tool_call name=search] 查 PG 集群\n> 返回 5 个节点")
    assert len(blocks) == 1
    assert isinstance(blocks[0], ToolCallBlock)
    assert blocks[0].name == "search"
    assert "查 PG 集群" in blocks[0].text
    assert "返回 5 个节点" in blocks[0].text


def test_parse_blocks_plain_text():
    """没有标记的行应被解析为 TextBlock。"""
    from mmi.tui.parse_blocks import TextBlock, parse_blocks

    blocks = parse_blocks("just plain text")
    assert len(blocks) == 1
    assert isinstance(blocks[0], TextBlock)
    assert blocks[0].text == "just plain text"


def test_parse_blocks_inline_thinking_ignored():
    """行中间的 [thinking] 不应被识别为块（只认行首）。"""
    from mmi.tui.parse_blocks import TextBlock, parse_blocks

    blocks = parse_blocks("inline [thinking] text")
    assert len(blocks) == 1
    assert isinstance(blocks[0], TextBlock)


def test_collapsible_static_thinking_class():
    """kind=thinking 应当给 widget 加 -thinking class。"""
    pytest.importorskip("textual")
    from mmi.tui.widgets.chat_log import CollapsibleStatic

    cs = CollapsibleStatic(kind="thinking", content="我在想")
    assert cs.has_class("-thinking"), f"classes={cs.classes!r}"
    assert not cs.has_class("-tool")


def test_collapsible_static_tool_class():
    """kind=tool 应当给 widget 加 -tool class。"""
    pytest.importorskip("textual")
    from mmi.tui.widgets.chat_log import CollapsibleStatic

    cs = CollapsibleStatic(kind="tool", name="search", content="查 PG")
    assert cs.has_class("-tool"), f"classes={cs.classes!r}"
    assert not cs.has_class("-thinking")


def test_chat_log_renders_thinking_block(isolated_home, make_app, scripted_llm_factory):
    """ChatLog._render_block(ThinkingBlock) 应当挂一个 CollapsibleStatic。"""
    pytest.importorskip("textual")
    from mmi.tui.screens.chat import ChatScreen
    from mmi.core import manager as mgr_module
    from mmi.tui.widgets.chat_log import ChatLog, CollapsibleStatic
    from mmi.tui.parse_blocks import ThinkingBlock

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            cl = app.screen.query_one("#chat-log", ChatLog)
            cl._render_block(ThinkingBlock(text="thinking content"))
            await pilot.pause()
            blocks = list(cl.query(CollapsibleStatic))
            assert len(blocks) == 1
            assert blocks[0].has_class("-thinking")

    import asyncio
    asyncio.run(_go())


# ---------------------------------------------------------------------------
# Phase 6 技术债: /archive 端到端测试
# ---------------------------------------------------------------------------


def test_archive_command_moves_to_trash(isolated_home, make_app, scripted_llm_factory):
    """在 ChatScreen 里输 /archive + Ctrl+Enter → 会话移到 trash + 屏 pop。"""
    pytest.importorskip("textual")
    from textual.widgets import TextArea
    from mmi.core import manager as mgr_module
    from mmi.tui.screens.chat import ChatScreen
    from mmi.tui.screens.list import SessionListScreen

    mgr = mgr_module.SessionManager(llm=scripted_llm_factory())
    sid = mgr.create()
    app = make_app(llm=scripted_llm_factory())
    app.mgr = mgr

    async def _go():
        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            app.push_screen(ChatScreen(sid))
            await pilot.pause()
            assert isinstance(app.screen, ChatScreen)

            # 输入 /archive 并提交
            ed = app.screen.query_one("#input", TextArea)
            ed.focus()
            await pilot.press(*"/archive")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            # 等 worker / pop
            for _ in range(30):
                await pilot.pause(0.1)
                # 屏应该 pop 回 SessionListScreen
                if isinstance(app.screen, SessionListScreen):
                    break

            assert isinstance(app.screen, SessionListScreen), (
                f"expected pop to SessionListScreen, got {type(app.screen).__name__}"
            )

            # 验证：会话不在 active 列表里
            active_ids = [m.session_id for m in mgr.list_sessions(limit=100)]
            assert sid not in active_ids, "session should be removed from active"

            # 验证：trash 目录有该会话文件
            from mmi.core.storage import trash_path
            assert trash_path(sid).exists(), f"trash file should exist: {trash_path(sid)}"

    import asyncio
    asyncio.run(_go())
