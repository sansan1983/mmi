"""mmi.cli.parser —— Argument parser（从 main.py 提取）。"""

from __future__ import annotations

import argparse

from mmi import __product_name__, __version__
from mmi.core import i18n

DEFAULT_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    """构建完整CLI参数解析器。"""
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
