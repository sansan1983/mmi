"""mmi.cli.main —— CLI 入口（已重构，每子命令独立文件）。

重构自 mmi/cli.py（1385 行 → ~200 行，死代码全部消除）。
子命令拆分到 mmi/cli/commands/ 目录。

设计原则（ARCHITECTURE.md §2）：
  - UI ≠ 推理 / 显示 ≠ 发送
  - 不直接读会话文件，全部走 SessionManager
  - 错误信息走 stderr（异常退出码非 0），成功输出走 stdout
  - 所有用户可见字符串走 t() i18n
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from mmi import __product_name__, __version__
from mmi.cli.parser import build_parser
from mmi.core import i18n
from mmi.core import manager as mgr_module

# 子命令名 → (模块, 公开函数名)；按字母排序便于检索。
# 懒加载在 _dispatch 内做，避免一次性 import 全部子命令（启动更轻）。
_COMMANDS: dict[str, tuple[str, str]] = {
    "agent": ("mmi.cli.commands.agent", "cmd_agent"),
    "archive": ("mmi.cli.commands.archive", "cmd_archive"),
    "chat": ("mmi.cli.commands.chat", "cmd_chat"),
    "config": ("mmi.cli.commands.config", "cmd_config"),
    "delete": ("mmi.cli.commands.delete", "cmd_delete"),
    "doctor": ("mmi.cli.commands.doctor", "cmd_doctor"),
    "export": ("mmi.cli.commands.export", "cmd_export"),
    "gc": ("mmi.cli.commands.gc", "cmd_gc"),
    "info": ("mmi.cli.commands.info", "cmd_info"),
    "inspect": ("mmi.cli.commands.inspect", "cmd_inspect"),
    "list": ("mmi.cli.commands.list", "cmd_list"),
    "memory": ("mmi.cli.commands.memory", "cmd_memory"),
    "new": ("mmi.cli.commands.new", "cmd_new"),
    "rename": ("mmi.cli.commands.rename", "cmd_rename"),
    "skill": ("mmi.cli.commands.skill", "cmd_skill"),
    "stat": ("mmi.cli.commands.stat", "cmd_stat"),
    "tui": ("mmi.cli.commands.tui", "cmd_tui"),
    "update": ("mmi.cli.commands.update", "cmd_update"),
}


def _load_command(name: str) -> Callable:
    """懒加载子命令模块并返回 cmd_<name> 函数。"""
    mod_path, attr = _COMMANDS[name]
    mod = importlib.import_module(mod_path)
    return getattr(mod, attr)


def _dispatch(args, mgr) -> int:
    """分发子命令到对应实现。未知/缺省子命令时打印提示。"""
    name = getattr(args, "command", None)
    if name in _COMMANDS:
        return _load_command(name)(args, mgr)

    print(i18n.t("cli.usage") + ":")
    print(f"  mmi {i18n.t('cli.command.new')}")
    print(f"  mmi {i18n.t('cli.command.list')}")
    print(f"  mmi {i18n.t('cli.command.chat')}")
    return 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：解析参数 + 分发到子命令。"""
    args = build_parser().parse_args(argv)

    # --version
    if args.version:
        print(f"{__product_name__} v{__version__}")
        return 0

    # --lang
    if args.lang:
        i18n.set_lang(args.lang)

    # 初始化 SessionManager
    mgr = mgr_module.SessionManager()

    return _dispatch(args, mgr)


if __name__ == "__main__":
    raise SystemExit(main())
