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

from mmi import __product_name__, __version__
from mmi.cli.parser import build_parser
from mmi.core import i18n
from mmi.core import manager as mgr_module


# 每个子命令通过直接模块导入，避免循环 import
def _dispatch(args, mgr) -> int:
    """分发子命令到对应实现。"""
    if args.command == "new":
        from mmi.cli.commands.new import cmd_new as cmd_new_func  # noqa: E402
        return cmd_new_func(args, mgr)
    elif args.command == "list":
        from mmi.cli.commands.list import cmd_list as cmd_list_func  # noqa: E402
        return cmd_list_func(args, mgr)
    elif args.command == "chat":
        from mmi.cli.commands.chat import cmd_chat as cmd_chat_func  # noqa: E402
        return cmd_chat_func(args, mgr)
    elif args.command == "archive":
        from mmi.cli.commands.archive import cmd_archive as cmd_archive_func  # noqa: E402
        return cmd_archive_func(args, mgr)
    elif args.command == "delete":
        from mmi.cli.commands.delete import cmd_delete as cmd_delete_func  # noqa: E402
        return cmd_delete_func(args, mgr)
    elif args.command == "gc":
        from mmi.cli.commands.gc import cmd_gc as cmd_gc_func  # noqa: E402
        return cmd_gc_func(args, mgr)
    elif args.command == "tui":
        from mmi.cli.commands.tui import cmd_tui as cmd_tui_func  # noqa: E402
        return cmd_tui_func(args, mgr)
    elif args.command == "tui-python":
        from mmi.cli.commands.tui_python import (  # noqa: E402
            cmd_tui_python as cmd_tui_python_func,
        )
        return cmd_tui_python_func(args, mgr)
    elif args.command == "doctor":
        from mmi.cli.commands.doctor import (  # noqa: E402
            cmd_doctor as cmd_doctor_func,
        )
        return cmd_doctor_func(args, mgr)
    elif args.command == "stat":
        from mmi.cli.commands.stat import cmd_stat as cmd_stat_func  # noqa: E402
        return cmd_stat_func(args, mgr)
    elif args.command == "export":
        from mmi.cli.commands.export import cmd_export as cmd_export_func  # noqa: E402
        return cmd_export_func(args, mgr)
    elif args.command == "rename":
        from mmi.cli.commands.rename import cmd_rename as cmd_rename_func  # noqa: E402
        return cmd_rename_func(args, mgr)
    elif args.command == "info":
        from mmi.cli.commands.info import cmd_info as cmd_info_func  # noqa: E402
        return cmd_info_func(args, mgr)
    elif args.command == "inspect":
        from mmi.cli.commands.inspect import cmd_inspect as cmd_inspect_func  # noqa: E402
        return cmd_inspect_func(args, mgr)
    elif args.command == "update":
        from mmi.cli.commands.update import cmd_update as cmd_update_func  # noqa: E402
        return cmd_update_func(args, mgr)
    elif args.command == "memory":
        from mmi.cli.commands.memory import cmd_memory as cmd_memory_func  # noqa: E402
        return cmd_memory_func(args, mgr)
    elif args.command == "config":
        from mmi.cli.commands.config import cmd_config as cmd_config_func  # noqa: E402
        return cmd_config_func(args, mgr)
    elif args.command == "agent":
        from mmi.cli.commands.agent import cmd_agent as cmd_agent_func  # noqa: E402
        return cmd_agent_func(args, mgr)
    elif args.command == "skill":
        from mmi.cli.commands.skill import cmd_skill as cmd_skill_func  # noqa: E402
        return cmd_skill_func(args, mgr)

    # 无子命令：显示帮助
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
        i18n.init(args.lang)

    # 初始化 SessionManager
    mgr = mgr_module.SessionManager()

    return _dispatch(args, mgr)


if __name__ == "__main__":
    raise SystemExit(main())
