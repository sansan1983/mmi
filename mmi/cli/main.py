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

import argparse
import sys
from pathlib import Path

# 允许从仓库根直接 `python mmi/cli/main.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Windows console 默认 GBK 会把 UTF-8 中文打成乱码；强制重配 stdout/stderr。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

from mmi.core import i18n  # noqa: E402
from mmi.core import manager as mgr_module  # noqa: E402
from mmi.core import paths  # noqa: E402
from mmi import __product_name__, __version__  # noqa: E402

# 仓库根目录（用于 tui 子命令定位 tui-ts/dist/mmi-tui.js）
REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Sub-commands import（集中导入，去掉循环 import 风险）
# ---------------------------------------------------------------------------
from mmi.cli.commands.new import cmd_new  # noqa: E402
from mmi.cli.commands.list import cmd_list  # noqa: E402
from mmi.cli.commands.stat import cmd_stat  # noqa: E402
from mmi.cli.commands.chat import cmd_chat  # noqa: E402
from mmi.cli.commands.export import cmd_export  # noqa: E402
from mmi.cli.commands.archive import cmd_archive  # noqa: E402
from mmi.cli.commands.delete import cmd_delete  # noqa: E402
from mmi.cli.commands.gc import cmd_gc  # noqa: E402
from mmi.cli.commands.tui import cmd_tui  # noqa: E402
from mmi.cli.commands.tui_python import cmd_tui_python  # noqa: E402
from mmi.cli.commands.rename import cmd_rename  # noqa: E402
from mmi.cli.commands.info import cmd_info  # noqa: E402
from mmi.cli.commands.inspect import cmd_inspect  # noqa: E402
from mmi.cli.commands.update import cmd_update  # noqa: E402
from mmi.cli.commands.memory import cmd_memory  # noqa: E402
from mmi.cli.commands.config import cmd_config  # noqa: E402
from mmi.cli.commands.agent import cmd_agent  # noqa: E402
from mmi.cli.commands.skill import cmd_skill  # noqa: E402


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

DEFAULT_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmi",
        description=f"{__product_name__} — 带记忆的智能体主板（Context Trim）",
    )
    parser.add_argument(
        "--lang",
        choices=i18n.SUPPORTED_LANGS,
        default=None,
        help="界面语言（默认根据 LANG 环境变量自动选择）",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="显示版本并退出",
    )

    sub = parser.add_subparsers(dest="command")

    # new
    p_new = sub.add_parser("new", help="新建会话（可选标题参数）")
    p_new.add_argument("title", nargs="?", default=None, help="会话标题")

    # list
    p_list = sub.add_parser("list", help="列出最近会话")
    p_list.add_argument("--limit", type=int, default=DEFAULT_LIMIT, metavar="N")
    p_list.add_argument(
        "--state",
        choices=["active", "warm", "cold", "zombie", "all"],
        default="all",
    )

    # chat
    p_chat = sub.add_parser("chat", help="继续指定会话")
    p_chat.add_argument("session_id", help="会话 ID（ULID）")
    p_chat.add_argument("--inspect", action="store_true", help="预览 prompt 诊断信息")

    # archive
    p_archive = sub.add_parser("archive", help="归档会话到 trash")
    p_archive.add_argument("session_id", help="会话 ID")

    # delete
    p_delete = sub.add_parser("delete", help="硬删会话（不可恢复）")
    p_delete.add_argument("session_id", help="会话 ID")

    # gc
    p_gc = sub.add_parser("gc", help="清理 trash 目录中超期的会话")
    p_gc.add_argument("--ttl-days", type=int, default=7, metavar="N")
    p_gc.add_argument("--dry-run", action="store_true")
    p_gc.add_argument(
        "--gc-only",
        choices=["cold", "zombie", "trash", "all"],
        default="all",
    )

    # tui
    p_tui = sub.add_parser("tui", help="启动 TUI（TypeScript + Ink）")
    p_tui.add_argument("--build", action="store_true", help="强制重新构建 tui-ts bundle")

    # tui-python
    sub.add_parser("tui-python", help="启动新版 Python TUI（Textual）")

    # doctor
    sub.add_parser("doctor", help="系统诊断")

    # stat
    sub.add_parser("stat", help="显示会话统计")

    # export
    p_export = sub.add_parser("export", help="导出会话")
    p_export.add_argument("session_id", help="会话 ID")
    p_export.add_argument("output", help="输出文件路径")
    p_export.add_argument("--format", choices=["json", "markdown"], default=None)
    p_export.add_argument("--compact", action="store_true")

    # rename
    p_rename = sub.add_parser("rename", help="重命名会话标题")
    p_rename.add_argument("session_id", help="会话 ID")
    p_rename.add_argument("title", help="新标题")
    p_rename.add_argument("-f", "--force", action="store_true")

    # info
    p_info = sub.add_parser("info", help="显示会话详细信息")
    p_info.add_argument("session_id", help="会话 ID")

    # inspect
    p_inspect = sub.add_parser("inspect", help="预览上下文裁剪结果（诊断）")
    p_inspect.add_argument("session_id", help="会话 ID")
    p_inspect.add_argument("--text", default=None)

    # update
    p_update = sub.add_parser("update", help="更新会话热度（不触发 LLM）")
    p_update.add_argument("session_id", help="会话 ID")

    # memory
    p_memory = sub.add_parser("memory", help="跨会话记忆检索")
    p_memory_sub = p_memory.add_subparsers(dest="memory_cmd")
    p_memory_search = p_memory_sub.add_parser("search", help="语义检索")
    p_memory_search.add_argument("query", nargs="+")
    p_memory_search.add_argument("-k", "--top-k", type=int, default=5)
    p_memory_sub.add_parser("count", help="显示记忆总数")
    p_memory_clear = p_memory_sub.add_parser("clear", help="清空所有记忆")
    p_memory_clear.add_argument("--yes", action="store_true")

    # config
    p_config = sub.add_parser("config", help="配置 LLM")
    p_config_sub = p_config.add_subparsers(dest="config_cmd")
    p_config_sub.add_parser("show", help="显示当前配置")
    p_config_wizard = p_config_sub.add_parser("wizard", help="交互式配置向导")
    p_config_wizard.add_argument("--provider")
    p_config_wizard.add_argument("--api-key")
    p_config_wizard.add_argument("--model")
    p_config_wizard.add_argument("--no-fetch", action="store_true")

    # agent
    p_agent = sub.add_parser("agent", help="管理 Agent")
    p_agent_sub = p_agent.add_subparsers(dest="agent_cmd")
    p_agent_list = p_agent_sub.add_parser("list", help="列出所有 Agent")
    p_agent_list.add_argument("--tag")
    p_agent_invoke = p_agent_sub.add_parser("invoke", help="调用 Agent")
    p_agent_invoke.add_argument("agent_id")
    p_agent_invoke.add_argument("message")
    p_agent_invoke.add_argument("--session", required=True)
    p_agent_invoke.add_argument("--mode", choices=["STANDARD", "BRAINSTORM", "AUDIT"])

    # skill
    p_skill = sub.add_parser("skill", help="管理 Skill")
    p_skill_sub = p_skill.add_subparsers(dest="skill_cmd")
    p_skill_sub.add_parser("list", help="列出所有 Skill")
    p_skill_search = p_skill_sub.add_parser("search", help="搜索 Skill")
    p_skill_search.add_argument("query")
    p_skill_create = p_skill_sub.add_parser("create", help="创建 Skill")
    p_skill_create.add_argument("skill_id")
    p_skill_create.add_argument("name")
    p_skill_create.add_argument("content")
    p_skill_create.add_argument("--apply-scene", default="")
    p_skill_create.add_argument("--tags", default="")

    return parser


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

_VERSION = __version__


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1) 启动时确定语言
    lang = i18n.detect_lang(args.lang)
    i18n.set_lang(lang)

    # 2) --version
    if args.version:
        print(i18n.t("cli.banner"))
        print(i18n.t("cli.version", version=_VERSION))
        return 0

    # 3) 确保数据目录存在
    try:
        paths.ensure_dirs()
    except OSError as e:
        print(i18n.t("cli.init_failed", error=str(e)), file=sys.stderr)
        return 3

    # 4) 启动 banner（chat 子命令除外）
    show_banner = args.command not in ("chat",)
    if show_banner:
        print(i18n.t("cli.banner"))
        print(i18n.t("cli.banner.subtitle"))
        print(f"  [lang: {i18n.get_lang()}]")
        print()

    # 5) 子命令分发
    mgr = mgr_module.SessionManager()
    if args.command == "new":
        return cmd_new(args, mgr)
    if args.command == "list":
        return cmd_list(args, mgr)
    if args.command == "stat":
        return cmd_stat(args, mgr)
    if args.command == "export":
        return cmd_export(args, mgr)
    if args.command == "rename":
        return cmd_rename(args, mgr)
    if args.command == "info":
        return cmd_info(args, mgr)
    if args.command == "inspect":
        return cmd_inspect(args, mgr)
    if args.command == "chat":
        return cmd_chat(args, mgr)
    if args.command == "archive":
        return cmd_archive(args, mgr)
    if args.command == "delete":
        return cmd_delete(args, mgr)
    if args.command == "gc":
        return cmd_gc(args, mgr)
    if args.command == "doctor":
        from mmi.tools.doctor import run as run_doctor
        return run_doctor()
    if args.command == "update":
        return cmd_update(args, mgr)
    if args.command == "memory":
        return cmd_memory(args, mgr)
    if args.command == "config":
        return cmd_config(args, mgr)
    if args.command == "agent":
        return cmd_agent(args, mgr)
    if args.command == "skill":
        return cmd_skill(args, mgr)
    if args.command == "tui":
        return cmd_tui(args, mgr)
    if args.command == "tui-python":
        return cmd_tui_python(args, mgr)

    # 6) 无子命令：显示帮助
    print(i18n.t("cli.usage") + ":")
    print(f"  mmi {i18n.t('cli.command.new')}")
    print(f"  mmi {i18n.t('cli.command.list')}")
    print(f"  mmi {i18n.t('cli.command.chat')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())