"""mmi.tui.commands —— 斜杠命令注册表。

ARCHITECTURE Phase 5：注册所有斜杠命令（/new /list /search /archive /model /quit）。
设计：
  - COMMANDS 列表是有序候选（也用于 SlashMenu 自动补全）
  - dispatch 解析用户输入，分发到 ChatScreen 的回调
  - 命令解析的容错：未知命令 / 参数缺失 → 返回错误（由调用方显示）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..screens.chat import ChatScreen

__all__ = ["COMMANDS", "SlashCommandResult", "dispatch"]


# 命令候选（有序，SlashMenu 弹出时按此顺序）
COMMANDS: list[str] = [
    "/new",
    "/list",
    "/search",
    "/archive",
    "/model",
    "/quit",
]


# 命令处理器的签名：拿 ChatScreen 实例 + 命令后面的参数；返回 SlashCommandResult
#   action: "stay" | "pop" | "push_search" | "pop_after_archive" | "refresh_model" | "exit"
#   msg: 可选 i18n 提示（None 不提示）


@dataclass
class SlashCommandResult:
    action: str = "stay"
    msg: str = ""


# 实际命令表（key: 命令名不含前缀 /；value: 处理函数）
Handlers = dict[str, Callable[["ChatScreen", str], SlashCommandResult]]


def _cmd_new(screen: "ChatScreen", arg: str) -> SlashCommandResult:
    """回 list 屏（不创建会话；要新建回 list 按 n）。"""
    return SlashCommandResult(action="pop", msg="")


def _cmd_list(screen: "ChatScreen", arg: str) -> SlashCommandResult:
    return SlashCommandResult(action="pop", msg="")


def _cmd_search(screen: "ChatScreen", arg: str) -> SlashCommandResult:
    # push search screen 由 ChatScreen 处理（这里只标记）
    return SlashCommandResult(action="push_search", msg="")


def _cmd_archive(screen: "ChatScreen", arg: str) -> SlashCommandResult:
    """归档当前会话。"""
    try:
        screen.app.mgr.archive(screen.session_id)
    except Exception as e:
        return SlashCommandResult(action="stay", msg=f"archive failed: {e}")
    return SlashCommandResult(action="pop_after_archive", msg="")


def _cmd_model(screen: "ChatScreen", arg: str) -> SlashCommandResult:
    """/model <name> —— 切换默认模型。"""
    from ..core import config as cfg_module

    name = arg.strip()
    if not name:
        return SlashCommandResult(action="stay", msg="/model <name>")
    if not cfg_module.validate_model_name(name):
        return SlashCommandResult(
            action="stay",
            msg="model name must be 1-128 chars (letters / digits / ._:/+-)",
        )
    if not cfg_module.set_default_model(name):
        return SlashCommandResult(action="stay", msg="config write failed")
    return SlashCommandResult(action="refresh_model", msg="")


def _cmd_quit(screen: "ChatScreen", arg: str) -> SlashCommandResult:
    return SlashCommandResult(action="exit", msg="")


HANDLERS: Handlers = {
    "new": _cmd_new,
    "list": _cmd_list,
    "search": _cmd_search,
    "archive": _cmd_archive,
    "model": _cmd_model,
    "quit": _cmd_quit,
}


def parse(text: str) -> tuple[str, str] | None:
    """把 'model gpt-4o' 解析成 ('model', 'gpt-4o')。不是命令返回 None。"""
    text = text.strip()
    if not text.startswith("/"):
        return None
    body = text[1:]
    if " " in body:
        cmd, arg = body.split(" ", 1)
        return cmd.strip(), arg.strip()
    return body.strip(), ""


def dispatch(screen: "ChatScreen", text: str) -> SlashCommandResult:
    """分发一条斜杠命令。返回 SlashCommandResult 让 ChatScreen 决定下一步动作。"""
    parsed = parse(text)
    if parsed is None:
        return SlashCommandResult(action="stay", msg="not a command")
    cmd, arg = parsed
    handler = HANDLERS.get(cmd)
    if handler is None:
        return SlashCommandResult(action="stay", msg=f"unknown command: /{cmd}")
    return handler(screen, arg)
