"""mmi cli doctor — 系统诊断命令入口。

转发到 mmi.tools.doctor，保持命令行接口一致。
"""

from __future__ import annotations

import os
import sys
from argparse import Namespace

from mmi.cli import ensure_mmi_home
from mmi.core.manager import SessionManager


def cmd_doctor(args: Namespace, mgr: SessionManager) -> int:
    """系统诊断：转发到 mmi.tools.doctor。"""
    ensure_mmi_home()

    # 确保工具模块可导入
    _mmi_root = os.environ.get("MMI_ROOT", "")
    if _mmi_root and _mmi_root not in sys.path:
        sys.path.insert(0, _mmi_root)

    from mmi.tools.doctor import run as run_doctor  # noqa: E402

    return run_doctor()
