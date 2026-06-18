"""mmi.cli —— CLI 模块。

子命令拆分到 commands/ 目录，每个 cmd_*.py 一个子命令文件。
本包提供共享常量和工具函数。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

# 仓库根目录（mmi/cli/__init__.py → mmi/cli/ → mmi/ → REPO_ROOT）
REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# MMI_HOME 注入（Round 0.x 遗留：多个命令重复注入，现集中管理）
# ---------------------------------------------------------------------------

MMI_HOME_DEFAULT = str(Path.home() / ".mmi")


def ensure_mmi_home() -> None:
    """确保 MMI_HOME 环境变量已设置（多进程隔离用）。"""
    if "MMI_HOME" not in os.environ:
        os.environ["MMI_HOME"] = MMI_HOME_DEFAULT


# ---------------------------------------------------------------------------
# 共享：session 校验（7 个子命令共用,消除重复模板）
# ---------------------------------------------------------------------------


def require_session(sid: str, mgr, *, code: int = 1, err_key: str = "cli.unknown_session"):
    """Load session; on miss, print i18n error to stderr and return exit code.

    Returns:
        (sess, None) on success.
        (None, exit_code) on miss — caller should `return exit_code`.
    """
    from mmi.core import i18n
    from mmi.core import manager as mgr_module

    try:
        return mgr.get(sid), None
    except mgr_module.SessionNotFound:
        print(i18n.t(err_key, session_id=sid), file=sys.stderr)
        return None, code


# ---------------------------------------------------------------------------
# 共享：子命令 dispatch（4 个命令共用,消除 get sub / if-elif / unknown 模板）
# ---------------------------------------------------------------------------


def dispatch_subcommand(
    args: object,
    sub_attr: str,
    mapping: dict[str, Callable[[], int]],
    *,
    usage: str,
) -> int:
    """统一的子命令 dispatch 模板。

    Args:
        args: argparse Namespace,从它读 args.<sub_attr>。
        sub_attr: 子命令字段名(如 'memory_cmd' / 'agent_cmd')。
        mapping: 子命令名 -> handler 的 dict;handler 必须返回 exit code。
        usage: 没传子命令时打印的 usage 字符串。

    Returns:
        handler 的 return code,或 1 (无子命令 / 未知子命令)。
    """
    sub = getattr(args, sub_attr, None)
    if sub is None:
        print(usage)
        return 1
    handler = mapping.get(sub)
    if handler is None:
        tool = sub_attr.removesuffix("_cmd")
        print(f"unknown {tool} subcommand: {sub}")
        return 1
    return handler()


# ---------------------------------------------------------------------------
# 共享常量
# ---------------------------------------------------------------------------

DEFAULT_LIMIT = 10
