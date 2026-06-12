"""mmi.cli —— CLI 模块。

子命令拆分到 commands/ 目录，每个 cmd_*.py 一个子命令文件。
本包提供共享常量和工具函数。
"""

from __future__ import annotations

import os
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
# 共享常量
# ---------------------------------------------------------------------------

DEFAULT_LIMIT = 10